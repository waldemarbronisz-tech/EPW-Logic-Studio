"""feat/signal-watch — logic_studio/core/watch.py. Pure logic, no Qt,
headless — see ui/panels/watch.py for the panel built on top of this, the
same split as core/crossref.py vs. ui/panels/signals.py.
"""
from logic_studio.core.project import Project
from logic_studio.core.device_model import DeviceModel
from logic_studio.engine.io_provider import SimulationIOProvider
from logic_studio.core import watch
from logic_studio.core.watch import (
    get_watches, is_watched, add_watch, remove_watch, describe_watch,
    is_boolean_kind, read_value,
)
from logic_studio.core.crossref import (
    KIND_PHYSICAL_DI, KIND_PHYSICAL_DO, KIND_ANALOG_IN, KIND_ANALOG_OUT,
    KIND_INTERNAL_BIT, KIND_INTERNAL_REG, KIND_SYSTEM,
)


# ---- add/remove/list -------------------------------------------------------

def test_new_project_has_no_watches():
    p = Project()
    assert get_watches(p) == []

def test_add_watch_appends_and_reports_added():
    p = Project()
    assert add_watch(p, KIND_PHYSICAL_DI, "ELA01.DI01") is True
    assert get_watches(p) == [{"kind": KIND_PHYSICAL_DI, "signal_id": "ELA01.DI01"}]

def test_add_watch_rejects_empty_signal_id():
    p = Project()
    assert add_watch(p, KIND_PHYSICAL_DI, "") is False
    assert get_watches(p) == []

def test_add_watch_is_idempotent_for_the_same_kind_and_id():
    p = Project()
    add_watch(p, KIND_PHYSICAL_DI, "ELA01.DI01")
    assert add_watch(p, KIND_PHYSICAL_DI, "ELA01.DI01") is False
    assert len(get_watches(p)) == 1

def test_same_signal_id_different_kind_is_a_separate_watch():
    p = Project()
    add_watch(p, KIND_PHYSICAL_DI, "SYS.READY")
    assert add_watch(p, KIND_SYSTEM, "SYS.READY") is True
    assert len(get_watches(p)) == 2

def test_is_watched():
    p = Project()
    assert is_watched(p, KIND_PHYSICAL_DI, "ELA01.DI01") is False
    add_watch(p, KIND_PHYSICAL_DI, "ELA01.DI01")
    assert is_watched(p, KIND_PHYSICAL_DI, "ELA01.DI01") is True

def test_remove_watch_reports_removed():
    p = Project()
    add_watch(p, KIND_PHYSICAL_DI, "ELA01.DI01")
    assert remove_watch(p, KIND_PHYSICAL_DI, "ELA01.DI01") is True
    assert get_watches(p) == []

def test_remove_watch_no_op_when_absent():
    p = Project()
    assert remove_watch(p, KIND_PHYSICAL_DI, "ELA01.DI01") is False

def test_get_watches_returns_a_copy_not_the_live_list():
    p = Project()
    add_watch(p, KIND_PHYSICAL_DI, "ELA01.DI01")
    watches = get_watches(p)
    watches.append({"kind": KIND_PHYSICAL_DI, "signal_id": "ELA01.DI02"})
    assert len(get_watches(p)) == 1  # the live list is untouched

def test_watches_survive_serialize_deserialize():
    p = Project()
    add_watch(p, KIND_PHYSICAL_DI, "ELA01.DI01")
    add_watch(p, KIND_SYSTEM, "SYS.READY")
    reloaded = Project.deserialize(p.serialize())
    assert get_watches(reloaded) == get_watches(p)


# ---- schema migration -------------------------------------------------------

def test_v5_project_migrates_with_empty_watch_list():
    data = {
        "format": "EPW_LOGIC", "schema_version": 5,
        "settings": {"ela_devices": ["ELA01"], "ada_devices": ["ADA01"]},
        "blocks": [],
    }
    p = Project.deserialize(data)
    assert get_watches(p) == []
    assert p.settings.get("watched_signals") == []


# ---- describe_watch ---------------------------------------------------------

def test_describe_watch_physical_uses_io_label():
    p = Project()
    DeviceModel.set_io_label(p, "ELA01.DI01", "Wyłącznik Q1 zamknięty")
    assert describe_watch(p, KIND_PHYSICAL_DI, "ELA01.DI01") == "Wyłącznik Q1 zamknięty"

def test_describe_watch_physical_empty_when_no_label():
    p = Project()
    assert describe_watch(p, KIND_PHYSICAL_DI, "ELA01.DI01") == ""

def test_describe_watch_analog_prefers_label_falls_back_to_point_name():
    p = Project()
    p.settings["analog_points"] = [
        {"address": "AI01", "name": "Temperatura silnika", "unit": "°C",
         "min": 0.0, "max": 150.0, "direction": "input"},
    ]
    assert describe_watch(p, KIND_ANALOG_IN, "AI01") == "Temperatura silnika"
    DeviceModel.set_io_label(p, "AI01", "T. uzwojenia")
    assert describe_watch(p, KIND_ANALOG_IN, "AI01") == "T. uzwojenia"

def test_describe_watch_internal_uses_registry_description():
    p = Project()
    p.settings["internal_bits"] = [
        {"name": "BLOKADA_ZS", "type": "BOOL", "retentive": False, "description": "Blokada zbiornika"},
    ]
    assert describe_watch(p, KIND_INTERNAL_BIT, "BLOKADA_ZS") == "Blokada zbiornika"

def test_describe_watch_internal_empty_when_deleted_from_registry():
    p = Project()
    assert describe_watch(p, KIND_INTERNAL_BIT, "GONE") == ""

def test_describe_watch_system_uses_catalog_description():
    p = Project()
    assert describe_watch(p, KIND_SYSTEM, "SYS.READY") == "Sterownik gotowy do pracy"


# ---- is_boolean_kind ---------------------------------------------------------

def test_is_boolean_kind_physical_always_true():
    p = Project()
    assert is_boolean_kind(p, KIND_PHYSICAL_DI, "ELA01.DI01") is True
    assert is_boolean_kind(p, KIND_PHYSICAL_DO, "ADA01.DO01") is True

def test_is_boolean_kind_analog_always_false():
    p = Project()
    assert is_boolean_kind(p, KIND_ANALOG_IN, "AI01") is False

def test_is_boolean_kind_internal_follows_registry_type():
    p = Project()
    p.settings["internal_bits"] = [
        {"name": "M_BIT", "type": "BOOL", "retentive": False},
        {"name": "M_REG", "type": "REAL", "retentive": False},
    ]
    assert is_boolean_kind(p, KIND_INTERNAL_BIT, "M_BIT") is True
    assert is_boolean_kind(p, KIND_INTERNAL_REG, "M_REG") is False

def test_is_boolean_kind_system_follows_catalog_type():
    p = Project()
    assert is_boolean_kind(p, KIND_SYSTEM, "SYS.READY") is True
    assert is_boolean_kind(p, KIND_SYSTEM, "SYS.SCAN_TIME") is False


# ---- read_value --------------------------------------------------------------

def test_read_value_physical_di_do():
    p = Project()
    io = SimulationIOProvider()
    io.set_digital_input("ELA01.DI01", True)
    io.write_digital_output("ADA01.DO01", True)
    assert read_value(p, io, KIND_PHYSICAL_DI, "ELA01.DI01") is True
    assert read_value(p, io, KIND_PHYSICAL_DO, "ADA01.DO01") is True

def test_read_value_analog_in_out():
    p = Project()
    io = SimulationIOProvider()
    io.set_analog_input("AI01", 42.5)
    io.write_analog_output("AO01", 7.5)
    assert read_value(p, io, KIND_ANALOG_IN, "AI01") == 42.5
    assert read_value(p, io, KIND_ANALOG_OUT, "AO01") == 7.5

def test_read_value_internal_bit_resolves_bare_name_to_derived_id():
    p = Project()
    p.settings["internal_bits"] = [
        {"name": "BLOKADA_ZS", "type": "BOOL", "retentive": False},
    ]
    io = SimulationIOProvider()
    io.write_internal("M.BLOKADA_ZS", True)  # what a real writer block would write
    assert read_value(p, io, KIND_INTERNAL_BIT, "BLOKADA_ZS") is True

def test_read_value_internal_reg_retentive_prefix():
    p = Project()
    p.settings["internal_bits"] = [
        {"name": "TOTAL", "type": "REAL", "retentive": True},
    ]
    io = SimulationIOProvider()
    io.write_internal("MWR.TOTAL", 12.5)
    assert read_value(p, io, KIND_INTERNAL_REG, "TOTAL") == 12.5

def test_read_value_internal_none_when_deleted_from_registry():
    p = Project()
    io = SimulationIOProvider()
    assert read_value(p, io, KIND_INTERNAL_BIT, "GONE") is None

def test_read_value_system_signal():
    p = Project()
    io = SimulationIOProvider()
    io.system_signal_overrides["SYS.READY"] = True
    assert read_value(p, io, KIND_SYSTEM, "SYS.READY") is True

def test_read_value_system_signal_uses_now_ms_for_pulse_generators():
    p = Project()
    io = SimulationIOProvider()
    assert read_value(p, io, KIND_SYSTEM, "SYS.BLINK_SLOW", now_ms=0) is True
    assert read_value(p, io, KIND_SYSTEM, "SYS.BLINK_SLOW", now_ms=600) is False
