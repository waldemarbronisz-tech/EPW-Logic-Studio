"""feat/editor-modes-and-geometry §2 — disabled ("zaślepione") input stubs.

Covers §2.6's four required cases: an AND-4 with one input disabled behaves
identically to an AND-3 across every combination of the remaining three
inputs; a multi-input gate with fewer than two active inputs warns; a block
with every input disabled fails compilation; and the disabled flag survives
a save/load round-trip.
"""
import itertools

import pytest

from logic_studio.core.project import Project
from logic_studio.compiler.core import Compiler
from logic_studio.compiler.validator import Validator
from logic_studio.blocks.logic_gates import (
    AndGate, And3Gate, And4Gate, OrGate, Or3Gate, NotGate, BufferGate,
)
from logic_studio.blocks import register_builtin_blocks

register_builtin_blocks()


# ---- §2.4: allows_disabled_inputs is opt-in, gate-only, 2+ inputs only ----

def test_allows_disabled_inputs_true_for_multi_input_gates():
    for cls in (AndGate, And3Gate, And4Gate, OrGate, Or3Gate):
        assert cls().allows_disabled_inputs is True

def test_allows_disabled_inputs_false_for_single_input_gates():
    for cls in (NotGate, BufferGate):
        assert cls().allows_disabled_inputs is False

def test_allows_disabled_inputs_false_by_default_on_base_block():
    from logic_studio.blocks.io_blocks import DigitalOutputBlock
    assert DigitalOutputBlock().allows_disabled_inputs is False


# ---- §2.6.1: AND-4/1-disabled === AND-3 across every input combination ----

def test_and4_with_one_disabled_input_matches_and3_for_every_combination():
    for combo in itertools.product([False, True], repeat=3):
        and3 = And3Gate()
        for pin, v in zip(and3.inputs, combo):
            pin.value = v
        and3.evaluate()

        and4 = And4Gate()
        for pin, v in zip(and4.inputs[:3], combo):
            pin.value = v
        and4.inputs[3].disabled = True
        and4.inputs[3].value = None  # never wired, never fed a value
        and4.evaluate()

        assert and4.outputs[0].value == and3.outputs[0].value, combo

def test_disabled_input_excluded_regardless_of_its_own_stale_value():
    """A disabled input must be excluded from evaluate() entirely — even if
    it somehow still carries a leftover True value (e.g. from before it was
    disabled), it must not participate. This is what distinguishes
    exclusion semantics from "treat as False"."""
    and4 = And4Gate()
    for pin in and4.inputs[:3]:
        pin.value = True
    and4.inputs[3].disabled = True
    and4.inputs[3].value = True  # stale/leftover — must be ignored, not counted
    and4.evaluate()
    assert and4.outputs[0].value is True  # 3 active, all True -> True


# ---- §2.6.2: fewer than two active inputs -> warning ----

def test_or3_with_two_disabled_inputs_warns_with_exact_message():
    p = Project()
    gate = Or3Gate()
    gate.inputs[1].disabled = True
    gate.inputs[2].disabled = True
    p.add_block(gate)

    errors, warnings = [], []
    Validator(p).run(errors, warnings)

    assert errors == []
    # feat/io-labels-and-ids §4.3: compiler/validator messages identify a
    # block by its short_id now, not the possibly-shared display_name.
    expected = f"Bramka {gate.short_id} ma tylko 1 aktywne wejście — działa jak przekaźnik powtarzający."
    assert expected in warnings

def test_disabled_input_generates_no_unconnected_warning():
    p = Project()
    gate = And3Gate()
    gate.inputs[0].disabled = True
    # inputs[1]/[2] deliberately left unconnected -> those two still warn
    p.add_block(gate)

    errors, warnings = [], []
    Validator(p).run(errors, warnings)

    assert not any("In1" in w for w in warnings)
    assert any("In2" in w for w in warnings)
    assert any("In3" in w for w in warnings)


# ---- §2.6.3: every input disabled -> compile error ----

def test_all_inputs_disabled_is_a_compile_error():
    p = Project()
    gate = AndGate()
    for pin in gate.inputs:
        pin.disabled = True
    p.add_block(gate)

    c = Compiler(p)
    res = c.compile()

    assert res is None
    assert any("zaślepione" in e for e in c.errors)

def test_disabling_input_on_non_opted_in_block_is_a_compile_error():
    """Defensive: a NotGate (1 input, allows_disabled_inputs=False) with its
    input's disabled flag hand-set (e.g. an edited file, or a future UI
    bug) must be rejected, not silently accepted."""
    p = Project()
    n = NotGate()
    n.inputs[0].disabled = True
    p.add_block(n)

    errors, warnings = [], []
    Validator(p).run(errors, warnings)

    assert any("nie zezwala na zaślepianie" in e for e in errors)


# ---- §2.6.4: round-trip (save/load) preserves the flag ----

def test_disabled_flag_survives_serialize_deserialize_roundtrip():
    p = Project()
    gate = And3Gate()
    gate.inputs[1].disabled = True
    p.add_block(gate)

    data = p.serialize()
    p2 = Project.deserialize(data)

    reloaded = p2.blocks[0]
    assert reloaded.inputs[0].disabled is False
    assert reloaded.inputs[1].disabled is True
    assert reloaded.inputs[2].disabled is False

def test_disabled_flag_survives_clone():
    gate = And3Gate()
    gate.inputs[1].disabled = True
    clone = gate.clone()
    assert clone.inputs[1].disabled is True
    assert clone.inputs[0].disabled is False


# ---- §2.5: export carries the flag, checksum-covered ----

def test_export_carries_disabled_flag_and_checksum_changes_with_it():
    from logic_studio.compiler.exporter import Exporter, verify_checksum

    p = Project()
    gate = And3Gate()
    p.add_block(gate)
    c = Compiler(p)
    res = c.compile()
    assert res is not None
    baseline = Exporter(p, res["program"].execution_order).export()
    assert verify_checksum(baseline) is True

    exported_pin = baseline["blocks"][gate.uuid]["inputs"][1]
    assert exported_pin["disabled"] is False

    gate.inputs[1].disabled = True
    c2 = Compiler(p)
    res2 = c2.compile()
    assert res2 is not None
    changed = Exporter(p, res2["program"].execution_order).export()
    changed_pin = changed["blocks"][gate.uuid]["inputs"][1]
    assert changed_pin["disabled"] is True
    assert changed["checksum"] != baseline["checksum"]
