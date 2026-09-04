"""feat/multi-device-io — DeviceModel's ELA/ADA module list is now
project-defined (project.settings["ela_devices"]/["ada_devices"]),
previously permanently fixed at one of each. Covers the core model,
schema migration, and the design/compile-time consumers (Validator,
core/crossref.py, property_grid's Address combobox) — the live
Simulation panel grid and per-device system diagnostic signals
(ELA01.ONLINE etc.) are a deliberately separate, tracked follow-up, not
covered here (see MEMORY.md / AUDIT_REPORT.md).
"""
import pytest
from PySide6.QtWidgets import QApplication

from logic_studio.blocks import register_builtin_blocks
from logic_studio.blocks.registry import BlockRegistry
from logic_studio.core.project import Project
from logic_studio.core.device_model import DeviceModel

register_builtin_blocks()


def _app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


# ---- DeviceModel: defaults, project-awareness ----------------------------

def test_no_project_defaults_to_a_single_device():
    assert DeviceModel.get_ela_devices() == ["ELA01"]
    assert DeviceModel.get_ada_devices() == ["ADA01"]
    assert DeviceModel.get_ela_addresses() == [f"ELA01.DI{i:02d}" for i in range(1, 33)]
    assert DeviceModel.get_ada_addresses() == [f"ADA01.DO{i:02d}" for i in range(1, 33)]

def test_new_project_defaults_to_a_single_device():
    """A brand-new Project() must behave EXACTLY like every pre-multi-
    device project — this is the regression test for that."""
    p = Project()
    assert DeviceModel.get_ela_devices(p) == ["ELA01"]
    assert DeviceModel.get_ada_devices(p) == ["ADA01"]
    assert len(DeviceModel.get_ela_addresses(p)) == 32
    assert len(DeviceModel.get_ada_addresses(p)) == 32

def test_addresses_span_every_defined_device():
    p = Project()
    p.settings["ela_devices"] = ["ELA01", "ELA02"]
    addrs = DeviceModel.get_ela_addresses(p)
    assert len(addrs) == 64
    assert "ELA01.DI01" in addrs and "ELA01.DI32" in addrs
    assert "ELA02.DI01" in addrs and "ELA02.DI32" in addrs

def test_devices_setting_survives_serialize_deserialize():
    p = Project()
    p.settings["ela_devices"] = ["ELA01", "ELA02", "ELA03"]
    p.settings["ada_devices"] = ["ADA01", "ADA02"]
    data = p.serialize()
    p2 = Project.deserialize(data)
    assert p2.settings["ela_devices"] == ["ELA01", "ELA02", "ELA03"]
    assert p2.settings["ada_devices"] == ["ADA01", "ADA02"]


# ---- device name validation / add / suggestion ----------------------------

def test_is_valid_device_name():
    assert DeviceModel.is_valid_device_name("ELA", "ELA01") is True
    assert DeviceModel.is_valid_device_name("ELA", "ELA99") is True
    assert DeviceModel.is_valid_device_name("ELA", "ADA01") is False  # wrong prefix
    assert DeviceModel.is_valid_device_name("ELA", "ELA1") is False  # not zero-padded
    assert DeviceModel.is_valid_device_name("ELA", "ELA001") is False  # too many digits
    assert DeviceModel.is_valid_device_name("ELA", "") is False
    assert DeviceModel.is_valid_device_name("ELA", None) is False

def test_next_device_name_fills_the_first_gap_and_extends():
    assert DeviceModel.next_device_name("ELA", []) == "ELA01"
    assert DeviceModel.next_device_name("ELA", ["ELA01"]) == "ELA02"
    assert DeviceModel.next_device_name("ELA", ["ELA01", "ELA02"]) == "ELA03"
    assert DeviceModel.next_device_name("ELA", ["ELA02"]) == "ELA01"  # fills the gap, doesn't just append

def test_set_ela_devices_validates_dedupes_and_normalizes(qsettings=None):
    p = Project()
    result = DeviceModel.set_ela_devices(p, ["ela01", " ELA02 ", "ELA01", "not-valid", ""])
    # lowercased/whitespace normalized to uppercase/stripped, duplicate
    # dropped, invalid entry dropped, order of first occurrence kept
    assert result == ["ELA01", "ELA02"]
    assert p.settings["ela_devices"] == ["ELA01", "ELA02"]

def test_set_ela_devices_falls_back_to_default_when_everything_invalid():
    p = Project()
    result = DeviceModel.set_ela_devices(p, ["", "garbage", "ADA01"])
    assert result == ["ELA01"]


# ---- schema migration -----------------------------------------------------

def test_v4_project_migrates_with_default_single_device():
    old_data = {
        "format": "EPW_LOGIC",
        "schema_version": 4,
        "settings": {
            "name": "Old Project", "version": "1.0", "cycle_time_ms": 100,
            "analog_points": [], "internal_bits": [], "io_labels": {},
        },
        "blocks": [],
    }
    p = Project.deserialize(old_data)
    assert p.settings["ela_devices"] == ["ELA01"]
    assert p.settings["ada_devices"] == ["ADA01"]

def test_v1_project_migrates_all_the_way_through_to_ela_ada_devices():
    """The full v1->v5 migration chain in one load — the earliest format
    still ends up with the exact same default device list a brand-new
    project gets."""
    old_data = {
        "format": "EPW_LOGIC",
        "schema_version": 1,
        "settings": {"name": "Ancient Project", "version": "1.0", "cycle_time_ms": 100},
        "blocks": [],
    }
    p = Project.deserialize(old_data)
    assert p.settings["ela_devices"] == ["ELA01"]
    assert p.settings["ada_devices"] == ["ADA01"]


# ---- Validator: accepts an address only on a device the project defines --

def test_validator_rejects_address_on_an_undefined_device():
    from logic_studio.compiler.validator import Validator
    p = Project()
    di = BlockRegistry.create_block("input.di")
    di.properties["Address"] = "ELA02.DI01"  # ELA02 doesn't exist yet
    p.add_block(di)

    errors, warnings = [], []
    Validator(p).run(errors, warnings)
    assert any("ELA02.DI01" in e for e in errors)

def test_validator_accepts_address_once_the_device_is_defined():
    from logic_studio.compiler.validator import Validator
    p = Project()
    p.settings["ela_devices"] = ["ELA01", "ELA02"]
    di = BlockRegistry.create_block("input.di")
    di.properties["Address"] = "ELA02.DI01"
    p.add_block(di)

    errors, warnings = [], []
    Validator(p).run(errors, warnings)
    assert not any("ELA02.DI01" in e for e in errors)


# ---- core/crossref.py: classifies an address on any defined device --------

def test_crossref_classifies_second_device_address_as_physical_di():
    from logic_studio.core.crossref import build_crossref, KIND_PHYSICAL_DI
    p = Project()
    p.settings["ela_devices"] = ["ELA01", "ELA02"]
    di = BlockRegistry.create_block("input.di")
    di.properties["Address"] = "ELA02.DI05"
    p.add_block(di)

    crossref = build_crossref(p)
    assert crossref["ELA02.DI05"].kind == KIND_PHYSICAL_DI
    assert crossref["ELA02.DI05"].defined is True


# ---- property_grid.py: Address combobox spans every defined device --------

def test_property_grid_address_combobox_includes_every_device(qsettings):
    _app()
    from logic_studio.ui.panels.property_grid import PropertyGridPanel

    p = Project()
    p.settings["ela_devices"] = ["ELA01", "ELA02"]
    di = BlockRegistry.create_block("input.di")
    panel = PropertyGridPanel(settings=qsettings)
    panel.load_block_properties(di, p)

    combo = panel.field_widget("Address")
    items = [combo.itemText(i) for i in range(combo.count())]
    assert "ELA01.DI01" in items
    assert "ELA02.DI01" in items
    assert len(items) == 64


# ---- Project Settings dialog: device list editing (ui/dialogs.py) ---------

def test_dialog_starts_with_the_projects_current_devices(qsettings):
    _app()
    from logic_studio.ui.dialogs import ProjectSettingsDialog
    p = Project()
    p.settings["ela_devices"] = ["ELA01", "ELA02"]
    dialog = ProjectSettingsDialog(p)
    assert [dialog.ela_list.item(i).text() for i in range(dialog.ela_list.count())] == ["ELA01", "ELA02"]

def test_add_device_button_suggests_the_next_free_name(qsettings):
    _app()
    from logic_studio.ui.dialogs import ProjectSettingsDialog
    p = Project()
    dialog = ProjectSettingsDialog(p)
    dialog._add_device(dialog.ela_list, "ELA")
    assert [dialog.ela_list.item(i).text() for i in range(dialog.ela_list.count())] == ["ELA01", "ELA02"]

def test_cannot_remove_the_last_remaining_device(qsettings):
    _app()
    from logic_studio.ui.dialogs import ProjectSettingsDialog
    p = Project()
    dialog = ProjectSettingsDialog(p)
    dialog.ela_list.item(0).setSelected(True)
    dialog._remove_selected_devices(dialog.ela_list)
    assert dialog.ela_list.count() == 1  # refused — would leave zero devices

def test_removing_a_non_last_device_works(qsettings):
    _app()
    from logic_studio.ui.dialogs import ProjectSettingsDialog
    p = Project()
    dialog = ProjectSettingsDialog(p)
    dialog._add_device(dialog.ela_list, "ELA")  # ELA01, ELA02
    dialog.ela_list.item(1).setSelected(True)
    dialog._remove_selected_devices(dialog.ela_list)
    assert [dialog.ela_list.item(i).text() for i in range(dialog.ela_list.count())] == ["ELA01"]

def test_apply_to_project_stores_the_edited_device_lists(qsettings):
    _app()
    from logic_studio.ui.dialogs import ProjectSettingsDialog
    p = Project()
    dialog = ProjectSettingsDialog(p)
    dialog._add_device(dialog.ela_list, "ELA")
    dialog._on_accept()

    dialog.apply_to_project()
    assert p.settings["ela_devices"] == ["ELA01", "ELA02"]

def test_removing_a_used_device_prompts_for_confirmation(qsettings, monkeypatch):
    """Mirrors the existing used-internal-signal-deletion confirmation —
    removing ELA01 while a DI block still addresses it must ask first,
    naming the block, not silently orphan the block's Address."""
    _app()
    from logic_studio.ui.dialogs import ProjectSettingsDialog
    from PySide6.QtWidgets import QMessageBox, QDialog

    p = Project()
    p.settings["ela_devices"] = ["ELA01", "ELA02"]
    di = BlockRegistry.create_block("input.di")
    di.properties["Address"] = "ELA02.DI01"
    p.add_block(di)

    dialog = ProjectSettingsDialog(p)
    # Remove ELA02 (still used by `di`) from the list widget.
    for i in range(dialog.ela_list.count()):
        if dialog.ela_list.item(i).text() == "ELA02":
            dialog.ela_list.item(i).setSelected(True)
    dialog._remove_selected_devices(dialog.ela_list)

    asked = {"count": 0}
    def fake_question(*args, **kwargs):
        asked["count"] += 1
        return QMessageBox.No  # decline -> accept must abort
    monkeypatch.setattr(QMessageBox, "question", staticmethod(fake_question))

    before_ela_devices = p.settings["ela_devices"]
    dialog._on_accept()  # should return early, never call self.accept()

    assert asked["count"] == 1
    assert dialog.result() != QDialog.Accepted
    assert p.settings["ela_devices"] == before_ela_devices  # nothing applied yet either way
