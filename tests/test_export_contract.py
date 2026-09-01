"""Contract tests for the EPW_RUNTIME_LOGIC export (AUDIT_REPORT.md §3).

The rest of the suite checks that the code does what the code says. These
tests check the other side: that the *exported file itself* — the only thing
EPW-OS ever actually sees — carries everything needed to reproduce what the
simulation does, with nothing left implicit in a live Project or
CompiledProgram that never leaves this process.
"""
import json

import pytest

from logic_studio.blocks import register_builtin_blocks
from logic_studio.blocks.registry import BlockRegistry
from logic_studio.blocks.analog_io import AnalogInputBlock
from logic_studio.compiler.core import Compiler
from logic_studio.compiler.exporter import Exporter, verify_checksum, CHECKSUM_FIELDS
from logic_studio.core.project import Project

register_builtin_blocks()


def _project_with_one_of_every_block():
    """One instance of every registered, executable block type, with valid
    addresses for the four address-bound types and zero connections (the
    validator only warns on unconnected inputs, it doesn't fail compilation
    over them)."""
    p = Project()
    p.settings["analog_points"] = [
        {"address": "AI.CONTRACT", "name": "Contract In", "unit": "u", "min": 0.0, "max": 100.0, "direction": "input"},
        {"address": "AO.CONTRACT", "name": "Contract Out", "unit": "u", "min": 0.0, "max": 100.0, "direction": "output"},
    ]

    blocks_by_type = {}
    for category in BlockRegistry.get_categories():
        if category == "Dokumentacja":
            continue
        for type_id in BlockRegistry.get_blocks_in_category(category):
            block = BlockRegistry.create_block(type_id)
            if type_id == "input.di":
                block.properties["Address"] = "ELA01.DI01"
            elif type_id == "output.do":
                block.properties["Address"] = "ADA01.DO01"
            elif type_id == "input.ai":
                block.properties["Address"] = "AI.CONTRACT"
            elif type_id == "output.ao":
                block.properties["Address"] = "AO.CONTRACT"

            blocks_by_type[type_id] = block
            p.add_block(block)

    return p, blocks_by_type


def test_export_contract_completeness():
    """§3.1: every registered (non-documentation) block type must be exported
    with everything needed to execute it standalone — type_id, every pin with
    its data type, every configured property, plus any compiler-resolved data
    a block specifically needs (input.ai's analog point range/unit — this is
    exactly the bug this PR fixes). Fails if a new block type is added whose
    evaluate() depends on data living outside {type_id, pins, properties}
    that isn't exported for it.
    """
    p, blocks_by_type = _project_with_one_of_every_block()

    c = Compiler(p)
    res = c.compile()
    assert res is not None, f"Compile failed: {c.errors}"

    data = Exporter(p, res["program"].execution_order).export()

    assert len(data["blocks"]) == len(blocks_by_type)

    for type_id, block in blocks_by_type.items():
        entry = data["blocks"][block.uuid]
        assert entry["type_id"] == type_id

        exported_inputs = {pin["name"]: pin for pin in entry["inputs"]}
        assert set(exported_inputs) == {pin.name for pin in block.inputs}
        for pin in exported_inputs.values():
            assert pin["type"], f"{type_id}: an input pin is missing its data type"

        exported_outputs = {pin["name"]: pin for pin in entry["outputs"]}
        assert set(exported_outputs) == {pin.name for pin in block.outputs}
        for pin in exported_outputs.values():
            assert pin["type"], f"{type_id}: an output pin is missing its data type"

        missing_properties = set(block.properties) - set(entry["properties"])
        assert not missing_properties, f"{type_id}: properties {missing_properties} missing from export"

        if type_id == "input.ai":
            for key in ("_resolved_range_min", "_resolved_range_max", "_resolved_unit"):
                assert key in entry["properties"], f"input.ai export is missing {key}"

def test_runtime_reconstructable_without_project():
    """§3.2: this test represents exactly what EPW-OS does — it receives only
    the exported EPW_RUNTIME_LOGIC dict, never a Project object and never the
    in-memory analog_points list. From that dict alone it must be able to
    reconstruct an input.ai block's quality-check range and unit."""
    p = Project()
    p.settings["analog_points"] = [
        {"address": "AI.STANDALONE", "name": "Standalone", "unit": "°C", "min": -10.0, "max": 60.0, "direction": "input"},
    ]
    ai = AnalogInputBlock()
    ai.properties["Address"] = "AI.STANDALONE"
    p.add_block(ai)

    c = Compiler(p)
    res = c.compile()
    assert res is not None, f"Compile failed: {c.errors}"

    data = Exporter(p, res["program"].execution_order).export()

    # Hand it off to "EPW-OS": round-trip through plain JSON, then drop every
    # reference to the Project — only the dict may be used from here on.
    data = json.loads(json.dumps(data))
    del p, ai

    exported_ai = next(b for b in data["blocks"].values() if b["type_id"] == "input.ai")
    props = exported_ai["properties"]

    assert props["_resolved_range_min"] == -10.0
    assert props["_resolved_range_max"] == 60.0
    assert props["_resolved_unit"] == "°C"

    # Also available at the top level for a consumer that wants the full
    # point definition rather than just what one block resolved from it.
    point = next(pt for pt in data["analog_points"] if pt["address"] == "AI.STANDALONE")
    assert point["min"] == -10.0
    assert point["max"] == 60.0
    assert point["unit"] == "°C"

def _exported_data_with_populated_fields():
    """A project deliberately shaped so every CHECKSUM_FIELDS entry has a
    non-trivial, tamperable value (a real execution_order, a real analog
    point, contains_forced_io actually True, ...)."""
    p = Project()
    p.settings["name"] = "Contract Project"
    p.settings["analog_points"] = [
        {"address": "AI.X", "name": "X", "unit": "bar", "min": 0.0, "max": 10.0, "direction": "input"},
    ]

    ai = AnalogInputBlock()
    ai.properties["Address"] = "AI.X"
    ai.simulation_state["force_state"] = "FORCE TRUE"  # -> contains_forced_io True
    p.add_block(ai)

    c = Compiler(p)
    res = c.compile()
    assert res is not None, f"Compile failed: {c.errors}"
    return Exporter(p, res["program"].execution_order).export()

def _tamper(value):
    if isinstance(value, bool):
        return not value
    if isinstance(value, (int, float)):
        return value + 1
    if isinstance(value, str):
        return value + "_TAMPERED"
    if isinstance(value, list):
        return value + (list(value[:1]) if value else ["_tampered"])
    if isinstance(value, dict):
        tampered = dict(value)
        tampered["_tampered"] = True
        return tampered
    raise TypeError(f"Don't know how to tamper with {type(value)}")

@pytest.mark.parametrize("field", CHECKSUM_FIELDS)
def test_checksum_protects_every_field(field):
    """§3.3: every field in CHECKSUM_FIELDS must be covered by the checksum —
    tampering with any one of them, alone, must flip verify_checksum() to
    False."""
    data = _exported_data_with_populated_fields()
    assert verify_checksum(data) is True

    tampered = json.loads(json.dumps(data))
    tampered[field] = _tamper(tampered[field])

    assert verify_checksum(tampered) is False, f"Tampering with '{field}' was not detected"

def test_export_checksum_protects_analog_points():
    """§1.4: modifying an analog point's definition in the exported dict
    (e.g. its "min") must be caught by verify_checksum(), even though no
    block property changed."""
    data = _exported_data_with_populated_fields()
    assert verify_checksum(data) is True

    tampered = json.loads(json.dumps(data))
    tampered["analog_points"][0]["min"] = tampered["analog_points"][0]["min"] + 5.0

    assert verify_checksum(tampered) is False

def test_export_roundtrip_through_disk_preserves_checksum(tmp_path):
    """§3.4: export -> verify True -> json.dump to disk -> json.load back ->
    verify still True. Uses a point name with Polish diacritics to also cover
    non-ASCII handling through the default (ensure_ascii=True) json.dump used
    by MainWindow._export_runtime()."""
    p = Project()
    p.settings["analog_points"] = [
        {"address": "AI.TR1", "name": "Temperatura uzwojeń TR1", "unit": "°C", "min": -40.0, "max": 150.0, "direction": "input"},
    ]
    ai = AnalogInputBlock()
    ai.properties["Address"] = "AI.TR1"
    p.add_block(ai)

    c = Compiler(p)
    res = c.compile()
    assert res is not None, f"Compile failed: {c.errors}"

    data = Exporter(p, res["program"].execution_order).export()
    assert verify_checksum(data) is True

    out_path = tmp_path / "export.epwlogic.runtime.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)  # default ensure_ascii=True, matches MainWindow

    with open(out_path, "r", encoding="utf-8") as f:
        loaded = json.load(f)

    assert verify_checksum(loaded) is True
    assert loaded["analog_points"][0]["name"] == "Temperatura uzwojeń TR1"

def test_examples_migrate_and_export_without_mass_rewrite(tmp_path):
    """§2.3: an examples/ fixture (schema_version 1 on disk) loads, migrates
    in-flight to EPWLOGIC_SCHEMA_VERSION, and round-trips through a tmp_path
    save/reload with no data loss — the tracked examples/ file itself is
    never written to."""
    from logic_studio.core.project import EPWLOGIC_SCHEMA_VERSION

    src = "examples/EPW_LOGIC_PRIORITY_A_TEST.epwlogic"
    with open(src, "r", encoding="utf-8") as f:
        on_disk = json.load(f)
    assert on_disk["schema_version"] == 1, "fixture assumption: still v1 on disk"

    p = Project.load_from_file(src)
    assert p.settings["analog_points"] == []  # v1 file had none; migrated in, not lost

    out_path = tmp_path / "migrated.epwlogic"
    p.save_to_file(str(out_path))

    with open(out_path, "r", encoding="utf-8") as f:
        saved = json.load(f)
    assert saved["schema_version"] == EPWLOGIC_SCHEMA_VERSION
    assert len(saved["blocks"]) == len(on_disk["blocks"])

    p2 = Project.load_from_file(str(out_path))
    assert len(p2.blocks) == len(p.blocks)
