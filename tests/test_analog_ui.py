import pytest
from PySide6.QtWidgets import QApplication
from logic_studio.blocks import register_builtin_blocks
from logic_studio.core.project import Project


def _app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_project_settings_dialog_validates_rows():
    """AUDIT_REPORT.md §1.3: address non-empty/unique/no-spaces, min<max,
    direction must be input/output."""
    _app()
    from logic_studio.ui.dialogs import ProjectSettingsDialog

    p = Project()
    dialog = ProjectSettingsDialog(p)

    # Empty table -> valid, no points.
    points, error = dialog._collect_points()
    assert error is None
    assert points == []

    dialog._add_row({"address": "AI.TEMP", "name": "Temp", "unit": "°C", "min": -40.0, "max": 150.0, "direction": "input"})
    points, error = dialog._collect_points()
    assert error is None
    assert points == [{"address": "AI.TEMP", "name": "Temp", "unit": "°C", "min": -40.0, "max": 150.0, "direction": "input"}]

    # Duplicate address.
    dialog._add_row({"address": "AI.TEMP", "name": "Temp2", "unit": "", "min": 0.0, "max": 1.0, "direction": "input"})
    points, error = dialog._collect_points()
    assert points is None
    assert "powtarza" in error

    # Fix duplicate, break min<max instead.
    dialog.table.item(1, 0).setText("AI.OTHER")
    dialog.table.item(1, 3).setText("10.0")
    dialog.table.item(1, 4).setText("5.0")
    points, error = dialog._collect_points()
    assert points is None
    assert "mniejsze" in error

    # Fix range, break with a space in the address.
    dialog.table.item(1, 3).setText("0.0")
    dialog.table.item(1, 4).setText("10.0")
    dialog.table.item(1, 0).setText("AI. OTHER")
    points, error = dialog._collect_points()
    assert points is None
    assert "spacji" in error

    # Empty address.
    dialog.table.item(1, 0).setText("")
    points, error = dialog._collect_points()
    assert points is None
    assert "pusty" in error

def test_project_settings_dialog_apply_pushes_undo_and_sets_analog_points():
    _app()
    from logic_studio.ui.dialogs import ProjectSettingsDialog

    p = Project()
    assert len(p.undo_stack) == 0

    dialog = ProjectSettingsDialog(p)
    dialog.name_edit.setText("Renamed")
    dialog.cycle_spin.setValue(250)
    dialog._add_row({"address": "AO.X", "name": "X", "unit": "bar", "min": 0.0, "max": 10.0, "direction": "output"})
    dialog._result_points, error = dialog._collect_points()
    assert error is None

    dialog.apply_to_project()

    assert p.settings["name"] == "Renamed"
    assert p.settings["cycle_time_ms"] == 250
    assert p.settings["analog_points"] == [{"address": "AO.X", "name": "X", "unit": "bar", "min": 0.0, "max": 10.0, "direction": "output"}]
    assert len(p.undo_stack) == 1  # one snapshot pushed before applying

def test_device_explorer_analog_branch_empty_and_populated():
    _app()
    from logic_studio.ui.panels.device_explorer import DeviceExplorerPanel

    p = Project()
    panel = DeviceExplorerPanel()
    panel.set_project(p)

    # Root -> [ELA-01, ADA-01, Analog]; Analog has no children yet.
    root = panel.tree.topLevelItem(0)
    analog_branch = None
    for i in range(root.childCount()):
        if root.child(i).text(0) == "Analog":
            analog_branch = root.child(i)
    assert analog_branch is not None
    assert analog_branch.childCount() == 0

    p.settings["analog_points"] = [
        {"address": "AI.TEMP", "name": "Temp", "unit": "°C", "min": -40.0, "max": 150.0, "direction": "input"},
    ]
    panel.set_project(p)

    root = panel.tree.topLevelItem(0)
    analog_branch = next(root.child(i) for i in range(root.childCount()) if root.child(i).text(0) == "Analog")
    assert analog_branch.childCount() == 1
    assert "AI.TEMP" in analog_branch.child(0).text(0)

def test_simulation_panel_analog_widgets_rebuild_on_set_project():
    _app()
    from logic_studio.ui.panels.simulation import SimulationPanel

    p = Project()
    p.settings["analog_points"] = [
        {"address": "AI.A", "name": "A", "unit": "", "min": 0.0, "max": 100.0, "direction": "input"},
        {"address": "AO.B", "name": "B", "unit": "", "min": 0.0, "max": 10.0, "direction": "output"},
    ]

    panel = SimulationPanel()
    panel.set_project(p)

    assert "AI.A" in panel.ai_spinboxes
    assert "AO.B" in panel.ao_labels
    assert "AO.B" not in panel.ai_spinboxes

    panel.ai_spinboxes["AI.A"].setValue(42.5)
    assert panel.get_analog_input_value("AI.A") == 42.5

    panel.set_analog_output_value("AO.B", 3.75)
    assert panel.ao_labels["AO.B"].text() == "3.75"

    # Rebuild with a different point set: old widgets must be gone.
    p2 = Project()
    p2.settings["analog_points"] = []
    panel.set_project(p2)
    assert panel.ai_spinboxes == {}
    assert panel.ao_labels == {}

def test_simulation_panel_slider_spinbox_sync():
    _app()
    from logic_studio.ui.panels.simulation import SimulationPanel

    p = Project()
    p.settings["analog_points"] = [
        {"address": "AI.A", "name": "A", "unit": "", "min": -10.0, "max": 10.0, "direction": "input"},
    ]
    panel = SimulationPanel()
    panel.set_project(p)

    slider = panel.ai_sliders["AI.A"]
    spin = panel.ai_spinboxes["AI.A"]

    slider.setValue(500)  # midpoint of 0..1000 -> value 0.0 (midpoint of -10..10)
    assert spin.value() == pytest.approx(0.0, abs=0.05)

    spin.setValue(10.0)
    assert slider.value() == 1000

def test_analog_chain_full_scan_through_main_window(qsettings):
    """End-to-end: AI (project analog point) -> AO, driven entirely through
    SimulationPanel widgets and MainWindow's push/pull, matching what
    _on_sim_tick / manual step do."""
    _app()
    from logic_studio.ui.main_window import MainWindow

    register_builtin_blocks()
    m = MainWindow(settings=qsettings)
    m.scene.clear()
    m.project.settings["analog_points"] = [
        {"address": "AI.TEMP", "name": "Temp", "unit": "°C", "min": -40.0, "max": 150.0, "direction": "input"},
        {"address": "AO.OUT", "name": "Out", "unit": "°C", "min": -40.0, "max": 150.0, "direction": "output"},
    ]
    m._refresh_project_dependent_panels()

    m.scene.add_block_from_library('input.ai', 0, 0)
    m.scene.add_block_from_library('output.ao', 200, 0)

    ai = m.project.blocks[0]
    ao = m.project.blocks[1]
    ai.properties["Address"] = "AI.TEMP"
    ao.properties["Address"] = "AO.OUT"
    ai.outputs[0].connect(ao.inputs[0])

    m.compile_project()
    assert m.engine.program is not None
    assert len(m.engine.program.execution_order) == 2

    m.simulation_panel.ai_spinboxes["AI.TEMP"].setValue(23.5)
    m._run_scan()

    assert m.simulation_panel.ao_labels["AO.OUT"].text() == "23.50"

    m.is_dirty = False
    m.close()

def test_step_buttons_enabled_state_transitions(qsettings):
    _app()
    from logic_studio.ui.main_window import MainWindow
    from logic_studio.engine.execution import ExecutionState

    register_builtin_blocks()
    m = MainWindow(settings=qsettings)
    m.scene.clear()

    # No compiled program yet -> disabled.
    assert m.simulation_panel.step_btn.isEnabled() is False

    m.scene.add_block_from_library('const.true', 0, 0)
    m.compile_project()
    # STOPPED with a loaded program -> enabled.
    assert m.simulation_panel.step_btn.isEnabled() is True

    m.start_simulation()
    assert m.engine.state == ExecutionState.RUNNING
    assert m.simulation_panel.step_btn.isEnabled() is False

    m._pause_simulation()
    assert m.engine.state == ExecutionState.PAUSED
    assert m.simulation_panel.step_btn.isEnabled() is True

    m.stop_simulation()
    assert m.simulation_panel.step_btn.isEnabled() is True

    m.is_dirty = False
    m.close()

def test_step_requested_ignored_while_running(qsettings):
    _app()
    from logic_studio.ui.main_window import MainWindow

    register_builtin_blocks()
    m = MainWindow(settings=qsettings)
    m.scene.clear()
    m.scene.add_block_from_library('const.true', 0, 0)
    m.compile_project()
    m.start_simulation()

    cycles_before = m.engine.cycle_counter
    m._on_step_requested(5)  # must be a no-op while RUNNING
    assert m.engine.cycle_counter == cycles_before

    m.is_dirty = False
    m.close()

def test_property_grid_analog_address_combobox():
    _app()
    from PySide6.QtWidgets import QComboBox
    from logic_studio.ui.panels.property_grid import PropertyGridPanel
    from logic_studio.blocks.analog_io import AnalogInputBlock

    p = Project()
    p.settings["analog_points"] = [
        {"address": "AI.A", "name": "A", "unit": "", "min": 0.0, "max": 1.0, "direction": "input"},
        {"address": "AI.B", "name": "B", "unit": "", "min": 0.0, "max": 1.0, "direction": "input"},
    ]

    panel = PropertyGridPanel()
    ai = AnalogInputBlock()
    panel.load_block_properties(ai, p)

    address_row = None
    for row in range(panel.table.rowCount()):
        if panel.table.item(row, 0) and panel.table.item(row, 0).text() == "Address":
            address_row = row
    assert address_row is not None
    combo = panel.table.cellWidget(address_row, 1)
    assert isinstance(combo, QComboBox)
    assert [combo.itemText(i) for i in range(combo.count())] == ["AI.A", "AI.B"]
