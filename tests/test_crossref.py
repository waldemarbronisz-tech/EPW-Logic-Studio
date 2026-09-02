"""feat/signal-crossref §1 — logic_studio/core/crossref.py. Pure logic, no
Qt, headless. Deliberately does NOT go through Compiler/Validator — see
crossref.py's own docstring for why.
"""
import pytest

from logic_studio.core.project import Project
from logic_studio.core.device_model import DeviceModel
from logic_studio.blocks import register_builtin_blocks
from logic_studio.blocks.registry import BlockRegistry
from logic_studio.core import crossref
from logic_studio.core.crossref import (
    build_crossref, find_issues, KIND_PHYSICAL_DI, KIND_PHYSICAL_DO,
    KIND_ANALOG_IN, KIND_ANALOG_OUT, KIND_INTERNAL_BIT, KIND_INTERNAL_REG,
    KIND_SYSTEM, KIND_UNASSIGNED, UNASSIGNED_SIGNAL_ID,
)

register_builtin_blocks()


def _block(type_id, address=None, bit=None, sygnal=None):
    b = BlockRegistry.create_block(type_id)
    if address is not None:
        b.properties["Address"] = address
    if bit is not None:
        b.properties["Bit"] = bit
    if sygnal is not None:
        b.properties["Sygnał"] = sygnal
    return b


# ---- empty project --------------------------------------------------------

def test_empty_project_has_empty_index():
    p = Project()
    index = build_crossref(p)
    assert index == {}
    assert find_issues(index) == []


# ---- one block of each kind ------------------------------------------------

def test_di_block_is_a_reader_of_a_physical_di_signal():
    p = Project()
    di = _block("input.di", address="ELA01.DI01")
    p.add_block(di)

    index = build_crossref(p)
    usage = index["ELA01.DI01"]
    assert usage.kind == KIND_PHYSICAL_DI
    assert usage.data_type == "BOOL"
    assert usage.defined is True
    assert (di.uuid, di.short_id, "State") in usage.readers
    assert usage.writers == []

def test_do_block_is_a_writer_of_a_physical_do_signal():
    p = Project()
    do = _block("output.do", address="ADA01.DO01")
    p.add_block(do)

    index = build_crossref(p)
    usage = index["ADA01.DO01"]
    assert usage.kind == KIND_PHYSICAL_DO
    assert (do.uuid, do.short_id, "Cmd") in usage.writers
    assert usage.readers == []

def test_ai_block_is_a_reader_of_an_analog_in_signal():
    p = Project()
    p.settings["analog_points"] = [
        {"address": "AI.TEMP", "name": "Temp", "unit": "°C", "min": -40.0, "max": 150.0, "direction": "input"},
    ]
    ai = _block("input.ai", address="AI.TEMP")
    p.add_block(ai)

    index = build_crossref(p)
    usage = index["AI.TEMP"]
    assert usage.kind == KIND_ANALOG_IN
    assert usage.data_type == "REAL"
    assert (ai.uuid, ai.short_id, "Value") in usage.readers

def test_ao_block_is_a_writer_of_an_analog_out_signal():
    p = Project()
    p.settings["analog_points"] = [
        {"address": "AO.OUT", "name": "Out", "unit": "", "min": 0.0, "max": 10.0, "direction": "output"},
    ]
    ao = _block("output.ao", address="AO.OUT")
    p.add_block(ao)

    index = build_crossref(p)
    usage = index["AO.OUT"]
    assert usage.kind == KIND_ANALOG_OUT
    assert (ao.uuid, ao.short_id, "Value") in usage.writers

def test_virtual_input_reads_an_internal_bool_bit():
    p = Project()
    p.settings["internal_bits"] = [{"name": "BLOKADA_ZS", "type": "BOOL", "retentive": False, "description": "Blokada"}]
    vi = _block("virtual.input", bit="BLOKADA_ZS")
    p.add_block(vi)

    index = build_crossref(p)
    usage = index["M.BLOKADA_ZS"]
    assert usage.kind == KIND_INTERNAL_BIT
    assert usage.label == "Blokada"
    assert (vi.uuid, vi.short_id, "State") in usage.readers

def test_virtual_output_writes_an_internal_bool_bit():
    p = Project()
    p.settings["internal_bits"] = [{"name": "BLOKADA_ZS", "type": "BOOL", "retentive": False}]
    vo = _block("virtual.output", bit="BLOKADA_ZS")
    p.add_block(vo)

    index = build_crossref(p)
    usage = index["M.BLOKADA_ZS"]
    assert (vo.uuid, vo.short_id, "Cmd") in usage.writers

def test_reg_in_reads_an_internal_real_register_with_prefix():
    p = Project()
    p.settings["internal_bits"] = [{"name": "USTAWA", "type": "REAL", "retentive": True}]
    ri = _block("internal.reg_in", bit="USTAWA")
    p.add_block(ri)

    index = build_crossref(p)
    assert "MWR.USTAWA" in index
    assert index["MWR.USTAWA"].kind == KIND_INTERNAL_REG
    assert index["MWR.USTAWA"].data_type == "REAL"

def test_system_signal_block_reads_a_catalog_signal():
    p = Project()
    from logic_studio.core import system_signals
    any_signal = system_signals.get_all_signals()[0]
    sig = _block("system.signal", sygnal=any_signal["id"])
    p.add_block(sig)

    index = build_crossref(p)
    usage = index[any_signal["id"]]
    assert usage.kind == KIND_SYSTEM
    assert usage.defined is True
    assert (sig.uuid, sig.short_id, "Out") in usage.readers

def test_gate_is_never_indexed():
    """A gate's Address property exists (empty, from BaseLogicBlock) but is
    never meaningful — it must never be scanned as a physical/analog
    signal reference."""
    p = Project()
    p.add_block(BlockRegistry.create_block("logic.and"))
    index = build_crossref(p)
    assert index == {}


# ---- signal with two writers -----------------------------------------------

def test_internal_bit_with_two_writers_is_an_error():
    p = Project()
    p.settings["internal_bits"] = [{"name": "X", "type": "BOOL", "retentive": False}]
    vo1 = _block("virtual.output", bit="X")
    vo2 = _block("virtual.output", bit="X")
    p.add_block(vo1)
    p.add_block(vo2)

    index = build_crossref(p)
    usage = index["M.X"]
    assert len(usage.writers) == 2

    issues = find_issues(index)
    errors = [i for i in issues if i.severity == "error" and i.signal_id == "M.X"]
    assert len(errors) == 1
    assert "więcej niż jeden" in errors[0].text


# ---- orphaned signal --------------------------------------------------------

def test_reference_to_unregistered_internal_bit_is_an_error_and_stays_indexed():
    p = Project()
    vi = _block("virtual.input", bit="GHOST")
    p.add_block(vi)

    index = build_crossref(p)
    assert "GHOST" in index
    usage = index["GHOST"]
    assert usage.defined is False
    assert (vi.uuid, vi.short_id, "State") in usage.readers

    issues = find_issues(index)
    errors = [i for i in issues if i.severity == "error" and i.signal_id == "GHOST"]
    assert len(errors) == 1
    assert "nie istnieje" in errors[0].text

def test_reference_to_unregistered_address_is_an_error():
    p = Project()
    do = _block("output.do", address="ADA01.DO99")  # not a real ADA address in DeviceModel? actually within range
    # Use an address structurally invalid instead, to guarantee "not found".
    do.properties["Address"] = "ADA99.DO01"
    p.add_block(do)

    index = build_crossref(p)
    usage = index["ADA99.DO01"]
    assert usage.defined is False

    issues = find_issues(index)
    assert any(i.severity == "error" and i.signal_id == "ADA99.DO01" for i in issues)

def test_orphaned_signal_does_not_also_report_unused_or_writer_count_rules():
    """An undefined signal short-circuits find_issues() — the "unused"/
    "multiple writers" rules aren't meaningful for something that doesn't
    exist in any registry."""
    p = Project()
    vo1 = _block("virtual.output", bit="GHOST")
    vo2 = _block("virtual.output", bit="GHOST")
    p.add_block(vo1)
    p.add_block(vo2)

    issues = find_issues(build_crossref(p))
    ghost_issues = [i for i in issues if i.signal_id == "GHOST"]
    assert len(ghost_issues) == 1
    assert ghost_issues[0].severity == "error"


# ---- unassigned address -----------------------------------------------------

def test_di_block_with_no_address_is_flagged():
    p = Project()
    di = BlockRegistry.create_block("input.di")
    di.properties["Address"] = ""
    p.add_block(di)

    index = build_crossref(p)
    assert UNASSIGNED_SIGNAL_ID in index
    usage = index[UNASSIGNED_SIGNAL_ID]
    assert usage.kind == KIND_UNASSIGNED
    assert any(short_id == di.short_id for (_uuid, short_id, _pin) in usage.readers)

    issues = find_issues(index)
    warnings = [i for i in issues if i.severity == "warning" and i.signal_id == di.short_id]
    assert len(warnings) == 1
    assert "nie ma przypisanego adresu" in warnings[0].text

def test_gate_with_empty_address_is_not_flagged_unassigned():
    """A gate's Address is always "" too, but it's not an addressable
    block type — must not trigger the unassigned-address rule."""
    p = Project()
    p.add_block(BlockRegistry.create_block("logic.and"))
    index = build_crossref(p)
    assert UNASSIGNED_SIGNAL_ID not in index


# ---- same address in three blocks (info) -----------------------------------

def test_same_input_address_read_by_three_blocks_is_info_not_error():
    p = Project()
    for _ in range(3):
        p.add_block(_block("input.di", address="ELA01.DI05"))

    index = build_crossref(p)
    usage = index["ELA01.DI05"]
    assert len(usage.readers) == 3

    issues = find_issues(index)
    matching = [i for i in issues if i.signal_id == "ELA01.DI05"]
    assert len(matching) == 1
    assert matching[0].severity == "info"
    assert "3" in matching[0].text


# ---- other §1.4 rules -------------------------------------------------------

def test_analog_point_defined_but_unused_is_a_warning():
    p = Project()
    p.settings["analog_points"] = [
        {"address": "AI.UNUSED", "name": "Unused", "unit": "", "min": 0.0, "max": 1.0, "direction": "input"},
    ]
    index = build_crossref(p)
    assert "AI.UNUSED" in index
    issues = find_issues(index)
    assert any(i.severity == "warning" and i.signal_id == "AI.UNUSED" and "nieużywany" in i.text for i in issues)

def test_internal_bit_defined_but_unused_is_a_warning():
    p = Project()
    p.settings["internal_bits"] = [{"name": "UNUSED", "type": "BOOL", "retentive": False}]
    index = build_crossref(p)
    issues = find_issues(index)
    assert any(i.severity == "warning" and i.signal_id == "M.UNUSED" and "nieużywany" in i.text for i in issues)

def test_internal_bit_read_but_never_written_is_a_warning():
    p = Project()
    p.settings["internal_bits"] = [{"name": "X", "type": "BOOL", "retentive": False}]
    p.add_block(_block("virtual.input", bit="X"))

    issues = find_issues(build_crossref(p))
    assert any(i.severity == "warning" and i.signal_id == "M.X" and "niezapisywany" in i.text for i in issues)

def test_multiple_addresses_do_not_cross_contaminate():
    p = Project()
    p.add_block(_block("input.di", address="ELA01.DI01"))
    p.add_block(_block("input.di", address="ELA01.DI02"))
    index = build_crossref(p)
    assert len(index["ELA01.DI01"].readers) == 1
    assert len(index["ELA01.DI02"].readers) == 1
