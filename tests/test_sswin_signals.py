"""feat/sswin-signals — the EPW-OS alarm/intrusion subsystem's fixed
part: catalog 1.1.0 (SSWIN.STATE/ALARM/OUT/CMD), the first source=="logic"
system signals, system.signal_out (the write direction), the compiler
validation around it, and the "Minimalny poziom dostępu" access-level gate
on safety_relevant writes. See ARCHITECTURE.md "System alarmowy".
"""
import re

import pytest
from PySide6.QtWidgets import QApplication

from logic_studio.blocks import register_builtin_blocks
from logic_studio.blocks.registry import BlockRegistry
from logic_studio.blocks.pin import Pin
from logic_studio.core.project import Project
from logic_studio.core import system_signals
from logic_studio.compiler.core import Compiler
from logic_studio.compiler.exporter import Exporter, verify_checksum

register_builtin_blocks()


def _app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


# ---- §4.1: catalog correctness (guards future entries too) -----------------

def test_catalog_version_is_1_1_0():
    assert system_signals.get_catalog_version() == "1.1.0"

def test_every_catalog_entry_has_the_required_fields():
    required = {"id", "description", "label", "type", "source", "safety_relevant"}
    for sig in system_signals.get_all_signals():
        missing = required - set(sig.keys())
        assert not missing, f"{sig.get('id', '?')} missing fields: {missing}"

def test_catalog_ids_are_unique():
    ids = [s["id"] for s in system_signals.get_all_signals()]
    assert len(ids) == len(set(ids)), "duplicate id(s) in the catalog"

def test_catalog_types_are_from_the_allowed_set():
    allowed = {"BOOL", "REAL"}
    for sig in system_signals.get_all_signals():
        assert sig["type"] in allowed, f"{sig['id']}: unexpected type {sig['type']!r}"

def test_catalog_sources_are_from_the_allowed_set():
    allowed = {"runtime", "logic"}
    for sig in system_signals.get_all_signals():
        assert sig["source"] in allowed, f"{sig['id']}: unexpected source {sig['source']!r}"

def test_catalog_version_is_valid_semver():
    assert re.match(r"^\d+\.\d+\.\d+$", system_signals.get_catalog_version())

def test_sswin_cmd_signals_are_the_only_logic_sourced_ones_so_far():
    """Documents the current, deliberately small set — catches an
    accidental source flip on an unrelated signal as much as it checks
    the CMD_* ones are what's expected."""
    logic_sourced = {s["id"] for s in system_signals.get_all_signals() if s["source"] == "logic"}
    assert logic_sourced == {
        "SSWIN.CMD_ARM", "SSWIN.CMD_ARM_PARTIAL", "SSWIN.CMD_DISARM",
        "SSWIN.CMD_RESET", "SSWIN.CMD_SILENCE",
    }


# ---- §4.2: write direction ---------------------------------------------------

def _out_block(signal_id, access_level=None):
    b = BlockRegistry.create_block("system.signal_out")
    b.update_property("Sygnał", signal_id)
    if access_level is not None:
        b.update_property("Minimalny poziom dostępu", access_level)
    return b

def _in_block(signal_id):
    b = BlockRegistry.create_block("system.signal")
    b.update_property("Sygnał", signal_id)
    return b

def test_writing_a_runtime_sourced_signal_is_a_compile_error():
    p = Project()
    p.add_block(_out_block("SSWIN.ARMED"))  # source == "runtime"

    res = Compiler(p).compile()

    assert res is None

def test_writing_a_logic_sourced_signal_compiles():
    p = Project()
    p.add_block(_out_block("SSWIN.CMD_ARM"))

    c = Compiler(p)
    res = c.compile()

    assert res is not None, f"Compile failed: {c.errors}"

def test_reading_a_logic_sourced_signal_compiles():
    """Reading one's own (or another block's) command is legal — a
    schematic that echoes SSWIN.CMD_ARM onto an indicator, say."""
    p = Project()
    p.add_block(_in_block("SSWIN.CMD_ARM"))

    c = Compiler(p)
    res = c.compile()

    assert res is not None, f"Compile failed: {c.errors}"

def test_write_then_read_roundtrips_across_two_scans():
    from logic_studio.engine.execution import ExecutionEngine
    from logic_studio.engine.io_provider import SimulationIOProvider
    from logic_studio.engine.time_provider import SystemTimeProvider

    p = Project()
    out = _out_block("SSWIN.CMD_ARM")
    p.add_block(out)
    inp = _in_block("SSWIN.CMD_ARM")
    p.add_block(inp)

    c = Compiler(p)
    res = c.compile()
    assert res is not None, f"Compile failed: {c.errors}"

    eng = ExecutionEngine(res["program"], SimulationIOProvider(), SystemTimeProvider())
    eng.start()
    out_clone = res["program"].block_map[out.uuid]
    out_clone.inputs[0].value = True

    eng.step()  # scan 1: the write is flushed at the end of this scan
    assert eng.io.system_signal_overrides.get("SSWIN.CMD_ARM") is True

    eng.step()  # scan 2: system.signal now reads the freshly-written value
    inp_clone = res["program"].block_map[inp.uuid]
    assert inp_clone.outputs[0].value is True

def test_writing_an_unrecognized_system_signal_is_a_compile_error():
    p = Project()
    b = BlockRegistry.create_block("system.signal_out")
    b.properties["Sygnał"] = "SSWIN.NOT_A_REAL_SIGNAL"  # bypass update_property's own resync, matches a corrupted file
    p.add_block(b)

    res = Compiler(p).compile()

    assert res is None

def test_unconfigured_output_block_does_not_error():
    """An output block with no signal picked yet — mid-edit — must not
    fail the compile the way an addressless DI/DO block does not either."""
    p = Project()
    p.add_block(BlockRegistry.create_block("system.signal_out"))

    c = Compiler(p)
    res = c.compile()

    assert res is not None, f"Compile failed: {c.errors}"

def test_unused_logic_signal_is_a_warning_not_an_error():
    p = Project()
    p.add_block(_out_block("SSWIN.CMD_ARM"))  # every OTHER CMD_* signal is unused

    c = Compiler(p)
    res = c.compile()

    assert res is not None, f"Compile failed: {c.errors}"
    assert any("SSWIN.CMD_RESET" in w and "nie jest używany" in w for w in c.warnings)

def test_a_logic_signal_read_but_not_written_still_counts_as_used():
    """§2.3's own "unused" warning covers "neither read nor written" — a
    signal only ever READ (e.g. echoed onto an indicator before its writer
    exists yet) must not also warn as unused."""
    p = Project()
    p.add_block(_in_block("SSWIN.CMD_ARM"))

    c = Compiler(p)
    res = c.compile()

    assert res is not None, f"Compile failed: {c.errors}"
    # "'SSWIN.CMD_ARM'" (quoted, exact) rather than a bare substring check —
    # "SSWIN.CMD_ARM" is also a substring of "SSWIN.CMD_ARM_PARTIAL", which
    # genuinely IS unused here and must still warn.
    assert not any("'SSWIN.CMD_ARM'" in w and "nie jest używany" in w for w in c.warnings)


# ---- §4.3: two writers ------------------------------------------------------

def test_two_writers_for_the_same_command_is_a_compile_error_naming_both():
    p = Project()
    o1 = _out_block("SSWIN.CMD_ARM")
    o2 = _out_block("SSWIN.CMD_ARM")
    p.add_block(o1)
    p.add_block(o2)

    c = Compiler(p)
    res = c.compile()

    assert res is None
    matching = [e for e in c.errors if "SSWIN.CMD_ARM" in e and "więcej niż jeden" in e]
    assert len(matching) == 1
    assert o1.short_id in matching[0]
    assert o2.short_id in matching[0]


# ---- §4.4: access level ------------------------------------------------------

def test_safety_relevant_write_with_no_access_level_warns():
    p = Project()
    p.add_block(_out_block("SSWIN.CMD_DISARM", access_level="Brak"))

    c = Compiler(p)
    res = c.compile()

    assert res is not None, f"Compile failed: {c.errors}"
    assert any("krytycznym" in w and "SSWIN.CMD_DISARM" in w for w in c.warnings)

def test_safety_relevant_write_with_engineer_level_does_not_warn():
    p = Project()
    p.add_block(_out_block("SSWIN.CMD_DISARM", access_level="Engineer"))

    c = Compiler(p)
    res = c.compile()

    assert res is not None, f"Compile failed: {c.errors}"
    assert not any("krytycznym" in w for w in c.warnings)

def test_non_safety_write_with_no_access_level_does_not_warn():
    p = Project()
    p.add_block(_out_block("SSWIN.CMD_ARM", access_level="Brak"))

    c = Compiler(p)
    res = c.compile()

    assert res is not None, f"Compile failed: {c.errors}"
    assert not any("krytycznym" in w for w in c.warnings)

def test_access_level_defaults_to_engineer_for_a_safety_relevant_signal():
    b = BlockRegistry.create_block("system.signal_out")
    b.update_property("Sygnał", "SSWIN.CMD_DISARM")
    assert b.properties["Minimalny poziom dostępu"] == "Engineer"

def test_access_level_defaults_to_brak_for_a_non_safety_signal():
    b = BlockRegistry.create_block("system.signal_out")
    b.update_property("Sygnał", "SSWIN.CMD_ARM")
    assert b.properties["Minimalny poziom dostępu"] == "Brak"

def test_manual_access_level_override_survives_reselecting_the_same_signal():
    """§3.1's default only applies when "Sygnał" actually CHANGES value —
    reassigning the same value it already has must not clobber a manual
    override (update_property() itself is a no-op path many callers use
    defensively; the property grid's own §5.4 already skips the commit
    when old==new, but the block-level guarantee should hold regardless)."""
    b = BlockRegistry.create_block("system.signal_out")
    b.update_property("Sygnał", "SSWIN.CMD_DISARM")
    assert b.properties["Minimalny poziom dostępu"] == "Engineer"
    b.update_property("Minimalny poziom dostępu", "User")
    assert b.properties["Minimalny poziom dostępu"] == "User"


# ---- §4.5: export --------------------------------------------------------

def test_export_carries_catalog_version_1_1_0():
    p = Project()
    c = Compiler(p)
    res = c.compile()
    data = Exporter(p, res["program"].execution_order).export()
    assert data["system_catalog_version"] == "1.1.0"

def test_export_checksum_covers_the_catalog_version_field():
    p = Project()
    c = Compiler(p)
    res = c.compile()
    data = Exporter(p, res["program"].execution_order).export()
    assert verify_checksum(data) is True

    tampered = dict(data)
    tampered["system_catalog_version"] = "9.9.9"
    assert verify_checksum(tampered) is False

def test_export_carries_the_access_level_property():
    p = Project()
    o = _out_block("SSWIN.CMD_DISARM")
    p.add_block(o)
    c = Compiler(p)
    res = c.compile()
    data = Exporter(p, res["program"].execution_order).export()
    assert data["blocks"][o.uuid]["properties"]["Minimalny poziom dostępu"] == "Engineer"


# ---- §4.6: backward compatibility -------------------------------------------

def test_a_project_using_only_pre_1_1_0_signals_loads_and_compiles_cleanly():
    """A project built against catalog 1.0.0 (before SSWIN existed)
    references only signals that are STILL in 1.1.0, unchanged — nothing
    was renamed or removed, only added. Must load/compile with no
    "unrecognized signal" warning."""
    p = Project()
    p.add_block(_in_block("SYS.READY"))

    c = Compiler(p)
    res = c.compile()

    assert res is not None, f"Compile failed: {c.errors}"
    assert not any("Nierozpoznany" in w for w in c.warnings)

def test_serialized_pre_1_1_0_project_round_trips():
    p = Project()
    p.add_block(_in_block("SYS.READY"))
    data = p.serialize()

    reloaded = Project.deserialize(data)

    c = Compiler(reloaded)
    res = c.compile()
    assert res is not None, f"Compile failed: {c.errors}"
    assert not any("Nierozpoznany" in w for w in c.warnings)


# ---- signal picker filtering (§2.4) -----------------------------------------

def test_output_block_signal_picker_shows_only_logic_sourced_signals():
    _app()
    from logic_studio.ui.signal_picker import SignalPickerDialog
    p = Project()
    dlg = SignalPickerDialog(p, value_type=None, sections=("system",), system_source_filter="logic")
    sys_root = dlg.tree.topLevelItem(0)
    cats = {sys_root.child(i).text(0) for i in range(sys_root.childCount())}
    assert cats == {"Komendy"}

def test_input_block_signal_picker_shows_every_category():
    _app()
    from logic_studio.ui.signal_picker import SignalPickerDialog
    p = Project()
    dlg = SignalPickerDialog(p, value_type=None, sections=("system",))
    sys_root = dlg.tree.topLevelItem(0)
    cats = {sys_root.child(i).text(0) for i in range(sys_root.childCount())}
    assert "Komendy" in cats
    assert "Stan dozoru" in cats
    assert "Alarmy" in cats


# ---- signals panel "Zapisuje" column (§2.5) ---------------------------------

def test_signals_panel_shows_writer_block_for_a_logic_sourced_signal():
    _app()
    from logic_studio.ui.panels.signals import SignalsPanel
    from logic_studio.core.crossref import build_crossref

    p = Project()
    out = _out_block("SSWIN.CMD_ARM")
    p.add_block(out)

    panel = SignalsPanel()
    panel.project = p
    usage = build_crossref(p)["SSWIN.CMD_ARM"]

    text, tooltip = panel._writers_text("SSWIN.CMD_ARM", usage)
    assert text == out.short_id

def test_signals_panel_still_shows_urzadzenie_for_a_runtime_sourced_signal():
    _app()
    from logic_studio.ui.panels.signals import SignalsPanel
    from logic_studio.core.crossref import build_crossref

    p = Project()
    p.add_block(_in_block("SYS.READY"))

    panel = SignalsPanel()
    panel.project = p
    usage = build_crossref(p)["SYS.READY"]

    text, _tooltip = panel._writers_text("SYS.READY", usage)
    assert text == "urządzenie"

def test_signals_panel_shows_dash_for_an_unwritten_logic_signal():
    _app()
    from logic_studio.ui.panels.signals import SignalsPanel
    from logic_studio.core.crossref import SignalUsage, KIND_SYSTEM

    p = Project()
    panel = SignalsPanel()
    panel.project = p
    usage = SignalUsage(signal_id="SSWIN.CMD_RESET", kind=KIND_SYSTEM, data_type="BOOL")

    text, _tooltip = panel._writers_text("SSWIN.CMD_RESET", usage)
    assert text == "—"
