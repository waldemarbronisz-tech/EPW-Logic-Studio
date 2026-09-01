import pytest
import os
from PySide6.QtWidgets import QApplication
from logic_studio.ui.main_window import MainWindow
from logic_studio.blocks import register_builtin_blocks

def test_priority_a_audit(qsettings):
    # 9. REGISTRY / 1. LIBRARY
    # Verify clean startup registration
    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    register_builtin_blocks()
    m = MainWindow(settings=qsettings)
    from logic_studio.engine.time_provider import SimulationTimeProvider
    m.engine.time = SimulationTimeProvider()

    # Verify Library categories
    from logic_studio.blocks.registry import BlockRegistry
    cats = BlockRegistry.get_categories()
    assert "Wejścia / Wyjścia" in cats
    assert "Inne" in cats
    assert "Liczniki" in cats
    # assert "Edges" in cats
    assert "Elementy Analogowe" in cats
    assert "Timery" in cats
    assert "Elementy Analogowe" in cats
    assert "Elementy Analogowe" in cats

    # 2. PLACEMENT
    m.scene.clear()

    # Network A
    m.scene.add_block_from_library("virtual.input", 0, 0)
    m.scene.add_block_from_library("edge.rtrig", 100, 0)
    m.scene.add_block_from_library("system.signal", 0, 100)
    m.scene.add_block_from_library("logic.and", 200, 0)
    m.scene.add_block_from_library("virtual.output", 300, 0)

    # Network B
    m.scene.add_block_from_library("const.real", 0, 200)
    m.scene.add_block_from_library("analog.scale", 100, 200)
    m.scene.add_block_from_library("analog.mov_avg", 200, 200)
    m.scene.add_block_from_library("analog.hysteresis", 300, 200)
    m.scene.add_block_from_library("timer.ton", 400, 200)
    m.scene.add_block_from_library("virtual.output", 500, 200)

    # Map blocks
    def get_block(index):
        return m.project.blocks[index]

    vi_a = get_block(0)
    rtrig = get_block(1)
    sys_sig = get_block(2)
    and_gate = get_block(3)
    vo_a = get_block(4)

    analog_src = get_block(5)
    scale = get_block(6)
    mov_avg = get_block(7)
    hyst = get_block(8)
    ton = get_block(9)
    vo_b = get_block(10)

    # 3. PROPERTIES
    # feat/internal-bits §2.1: virtual.input's free-text "Tag" was replaced
    # by "Bit" (a registry entry name, normally picked via
    # SignalPickerDialog — set directly here since this test predates that
    # UI).
    vi_a.update_property("Bit", "VI_PULSE_REQUEST")
    assert vi_a.properties["Bit"] == "VI_PULSE_REQUEST"

    # feat/internal-bits §3.4: system.signal's free-text "Tag" (which read
    # through read_digital_input(), sharing an address space with physical
    # DI) was replaced by "Sygnał", a fixed catalog signal id read via
    # IOProvider.read_system_signal().
    sys_sig.update_property("Sygnał", "SYS.COMMS_OK")

    analog_src.update_property("Value", "5.0")
    assert float(analog_src.properties["Value"]) == 5.0

    scale.update_property("In Min", "0.0")
    scale.update_property("In Max", "10.0")
    scale.update_property("Out Min", "0.0")
    scale.update_property("Out Max", "100.0")

    hyst.update_property("High Threshold", "40.0")
    hyst.update_property("Low Threshold", "10.0")

    ton.update_property("Preset (ms)", "200") # 2 ticks

    # 4. CONNECTIONS
    # Network A
    assert vi_a.outputs[0].connect(rtrig.inputs[0]) is True
    assert rtrig.outputs[0].connect(and_gate.inputs[0]) is True
    assert sys_sig.outputs[0].connect(and_gate.inputs[1]) is True
    assert and_gate.outputs[0].connect(vo_a.inputs[0]) is True

    # Network B
    assert analog_src.outputs[0].connect(scale.inputs[0]) is True
    assert scale.outputs[0].connect(mov_avg.inputs[0]) is True
    assert mov_avg.outputs[0].connect(hyst.inputs[0]) is True
    assert hyst.outputs[0].connect(ton.inputs[0]) is True
    assert ton.outputs[0].connect(vo_b.inputs[0]) is True

    # 5. TYPE VALIDATION
    # Analog output to boolean input should fail
    assert scale.outputs[0].connect(vo_b.inputs[0]) is False

    # 6. SIMULATION
    m.compile_project()
    assert len(m.engine.program.execution_order) == 11

    # Tick 1: Pulse input high
    # Force is runtime-only (AUDIT_REPORT.md §5.1): lives in simulation_state, not properties.
    m.engine.program.block_map[vi_a.uuid].simulation_state["force_state"] = "FORCE TRUE"
    m.engine.io.system_signal_overrides["SYS.COMMS_OK"] = True
    m.engine.step()

    # Network A Checks
    assert m.engine.get_block_state(sys_sig.uuid).outputs["Out"].value is True
    assert m.engine.get_block_state(rtrig.uuid).outputs["Out"].value is True
    assert m.engine.get_block_state(and_gate.uuid).outputs["Out"].value is True
    assert m.engine.get_block_state(vo_a.uuid).simulation_state["sim_value"] is True

    # Network B Checks
    assert m.engine.get_block_state(analog_src.uuid).outputs["Out"].value == 5.0
    assert m.engine.get_block_state(scale.uuid).outputs["Out"].value == 50.0
    assert m.engine.get_block_state(mov_avg.uuid).outputs["Out"].value == 50.0 # window fills
    assert m.engine.get_block_state(hyst.uuid).outputs["Out"].value is True # 50 >= 40 High Threshold
    assert m.engine.get_block_state(ton.uuid).outputs["Q"].value is False # Needs 200ms

    # Tick 2: Pulse goes low
    m.engine.program.block_map[vi_a.uuid].simulation_state["force_state"] = "FORCE FALSE"

    m.engine.time.advance(150) # Simulate real engine sleep delay for TON
    m.engine.step()

    assert m.engine.get_block_state(rtrig.uuid).outputs["Out"].value is False
    assert m.engine.get_block_state(vo_a.uuid).simulation_state["sim_value"] is False
    assert m.engine.get_block_state(ton.uuid).outputs["Q"].value is False # Only 100ms passed

    # Tick 3:
    m.engine.time.advance(150)
    m.engine.step()

    assert m.engine.get_block_state(ton.uuid).outputs["Q"].value is True # 200ms passed, Output goes high
    assert m.engine.get_block_state(vo_b.uuid).simulation_state["sim_value"] is True

    # 10. EXAMPLE PROJECT / 7. SAVE OPEN
    # Write to a scratch path, never back over the tracked examples/ fixture
    # (that file is committed as a reference project, not a test output).
    import tempfile
    save_path = os.path.join(tempfile.gettempdir(), "EPW_LOGIC_PRIORITY_A_TEST.epwlogic")
    m.project.save_to_file(save_path)
    assert os.path.exists(save_path)

    # Reopen
    m._open_project_headless(save_path)
    assert len(m.project.blocks) == 11
    os.remove(save_path)

    # Find scale
    loaded_scale = None
    for b in m.project.blocks:
        if b.type_id == "analog.scale":
            loaded_scale = b
            break

    assert loaded_scale is not None
    assert len(loaded_scale.inputs[0].connections) == 1 # still wired

    # 8. RUNTIME EXPORT
    from logic_studio.compiler.exporter import Exporter
    runtime_data = Exporter(m.project, m.engine.program.execution_order).export()

    assert "format" in runtime_data
    assert len(runtime_data["blocks"]) == 11
    # Check that scale block is in the runtime data
    assert loaded_scale.uuid in runtime_data["blocks"]

    m.is_dirty = False
    m.close()
