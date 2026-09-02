"""feat/io-labels-and-ids §1 — descriptive labels for I/O addresses.

project.settings["io_labels"]: address -> label, always read/written
through DeviceModel.get_io_label()/set_io_label()/get_labelled_addresses(),
never the dict directly (§1.4). Reference: e²TANGO's "Etykiety i LED"
configuration category (DTR §2.7.7).
"""
import pytest

from logic_studio.core.project import Project
from logic_studio.core.device_model import DeviceModel
from logic_studio.compiler.core import Compiler
from logic_studio.compiler.validator import Validator
from logic_studio.blocks import register_builtin_blocks
from logic_studio.blocks.registry import BlockRegistry

register_builtin_blocks()


# ---- §1.1 model ------------------------------------------------------------

def test_io_labels_defaults_to_empty_dict():
    p = Project()
    assert p.settings["io_labels"] == {}

def test_io_labels_survives_serialize_deserialize():
    p = Project()
    DeviceModel.set_io_label(p, "ELA01.DI01", "Wyłącznik Q1 zamknięty")

    data = p.serialize()
    p2 = Project.deserialize(data)

    assert DeviceModel.get_io_label(p2, "ELA01.DI01") == "Wyłącznik Q1 zamknięty"


# ---- §1.2 validation ---------------------------------------------------

def test_get_io_label_returns_empty_string_when_absent():
    p = Project()
    assert DeviceModel.get_io_label(p, "ELA01.DI01") == ""

def test_set_io_label_empty_removes_the_entry_rather_than_storing_empty():
    p = Project()
    DeviceModel.set_io_label(p, "ELA01.DI01", "Something")
    assert "ELA01.DI01" in p.settings["io_labels"]

    DeviceModel.set_io_label(p, "ELA01.DI01", "")
    assert "ELA01.DI01" not in p.settings["io_labels"]

def test_set_io_label_strips_whitespace_before_checking_emptiness():
    p = Project()
    DeviceModel.set_io_label(p, "ELA01.DI01", "   ")
    assert "ELA01.DI01" not in p.settings["io_labels"]

def test_set_io_label_truncates_to_max_length():
    p = Project()
    long_text = "x" * 200
    DeviceModel.set_io_label(p, "ELA01.DI01", long_text)
    assert len(DeviceModel.get_io_label(p, "ELA01.DI01")) == DeviceModel.MAX_IO_LABEL_LENGTH

def test_set_io_label_allows_polish_characters_and_spaces():
    p = Project()
    DeviceModel.set_io_label(p, "ELA01.DI01", "Wyłącznik Q1 zamknięty — Łąka")
    assert DeviceModel.get_io_label(p, "ELA01.DI01") == "Wyłącznik Q1 zamknięty — Łąka"

def test_get_labelled_addresses_returns_a_copy_not_the_live_dict():
    p = Project()
    DeviceModel.set_io_label(p, "ELA01.DI01", "X")
    snapshot = DeviceModel.get_labelled_addresses(p)
    snapshot["ELA01.DI02"] = "should not leak back"
    assert "ELA01.DI02" not in p.settings["io_labels"]

def test_unknown_address_label_warns_not_errors():
    p = Project()
    DeviceModel.set_io_label(p, "ELA01.DI99", "Nonexistent channel")

    errors, warnings = [], []
    Validator(p).run(errors, warnings)

    assert errors == []
    assert any("ELA01.DI99" in w for w in warnings)

def test_known_ela_address_label_does_not_warn():
    p = Project()
    DeviceModel.set_io_label(p, "ELA01.DI01", "Real channel")

    errors, warnings = [], []
    Validator(p).run(errors, warnings)

    assert not any("ELA01.DI01" in w and "nie istnieje" in w for w in warnings)

def test_analog_point_address_label_does_not_warn():
    p = Project()
    p.settings["analog_points"] = [
        {"address": "AI.TEMP", "name": "Temp", "unit": "°C", "min": -40.0, "max": 150.0, "direction": "input"},
    ]
    DeviceModel.set_io_label(p, "AI.TEMP", "Temperatura kotła")

    errors, warnings = [], []
    Validator(p).run(errors, warnings)

    assert errors == []
    assert not any("AI.TEMP" in w and "nie istnieje" in w for w in warnings)


# ---- §1.3 migration ---------------------------------------------------

def test_v3_project_migrates_with_empty_io_labels():
    from logic_studio.core.project import EPWLOGIC_SCHEMA_VERSION
    assert EPWLOGIC_SCHEMA_VERSION == 4

    old_data = {
        "format": "EPW_LOGIC",
        "schema_version": 3,
        "settings": {"name": "Old Project", "version": "1.0", "cycle_time_ms": 100,
                     "analog_points": [], "internal_bits": []},
        "blocks": [],
    }
    p = Project.deserialize(old_data)
    assert p.settings["io_labels"] == {}


# ---- §1.5 export --------------------------------------------------------

def test_io_labels_reach_the_runtime_export_and_checksum():
    from logic_studio.compiler.exporter import Exporter, verify_checksum, CHECKSUM_FIELDS

    assert "io_labels" in CHECKSUM_FIELDS

    p = Project()
    di = BlockRegistry.create_block("input.di")
    di.properties["Address"] = "ELA01.DI01"
    p.add_block(di)
    DeviceModel.set_io_label(p, "ELA01.DI01", "Wyłącznik Q1 zamknięty")

    c = Compiler(p)
    res = c.compile()
    assert res is not None, c.errors

    data = Exporter(p, res["program"].execution_order).export()
    assert data["io_labels"] == {"ELA01.DI01": "Wyłącznik Q1 zamknięty"}
    assert verify_checksum(data) is True

    tampered = dict(data)
    tampered["io_labels"] = {"ELA01.DI01": "Tampered"}
    assert verify_checksum(tampered) is False
