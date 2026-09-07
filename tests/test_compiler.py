import pytest
from logic_studio.core.project import Project
from logic_studio.compiler.core import Compiler
from logic_studio.blocks.logic_gates import AndGate, OrGate
from logic_studio.blocks.io_blocks import DigitalOutputBlock
from logic_studio.blocks import register_builtin_blocks

register_builtin_blocks()

def test_compiler_cycle_detection():
    p = Project()
    b1 = AndGate()
    b2 = OrGate()

    # Create cycle
    b1.outputs[0].connect(b2.inputs[0])
    b2.outputs[0].connect(b1.inputs[0])

    p.add_block(b1)
    p.add_block(b2)

    c = Compiler(p)
    res = c.compile()

    assert res is None # Must fail compilation
    assert len(c.errors) > 0
    assert "Execution Loop Detected" in c.errors[0]

def test_duplicate_ada_output():
    p = Project()
    do1 = DigitalOutputBlock()
    do1.properties["Address"] = "ADA1"

    do2 = DigitalOutputBlock()
    do2.properties["Address"] = "ADA1"

    p.add_block(do1)
    p.add_block(do2)

    c = Compiler(p)
    res = c.compile()

    assert res is None # Compilation fails
    assert any("Multiple outputs assigned to address: ADA1" in e for e in c.errors)

def test_export_checksum_roundtrip():
    """AUDIT_REPORT.md §5.2: verify_checksum must accept a freshly exported
    payload and reject one that was tampered with afterwards."""
    from logic_studio.compiler.exporter import Exporter, verify_checksum

    p = Project()
    a = AndGate()
    p.add_block(a)

    c = Compiler(p)
    res = c.compile()
    assert res is not None

    runtime_data = Exporter(p, res["program"].execution_order).export()

    assert "checksum" in runtime_data
    assert verify_checksum(runtime_data) is True

    tampered = dict(runtime_data)
    tampered["cycle_time_ms"] = tampered["cycle_time_ms"] + 1
    assert verify_checksum(tampered) is False

    missing_checksum = dict(runtime_data)
    del missing_checksum["checksum"]
    assert verify_checksum(missing_checksum) is False

def test_verify_checksum_ignores_non_schema_keys():
    """AUDIT_REPORT.md §0.2: Compiler.compile() attaches a non-serializable
    "program" (CompiledProgram) key on top of the exported payload.
    verify_checksum() must ignore it (and any other key outside
    CHECKSUM_FIELDS) instead of raising TypeError."""
    from logic_studio.compiler.exporter import verify_checksum

    p = Project()
    a = AndGate()
    p.add_block(a)

    c = Compiler(p)
    res = c.compile()
    assert res is not None
    assert "program" in res  # non-serializable CompiledProgram instance

    # Handing verify_checksum() the compile() result directly (not export())
    # must not raise, and must still validate correctly.
    assert verify_checksum(res) is True

    # Tampering with a field that IS part of the schema must still be caught.
    tampered = dict(res)
    tampered["block_count"] = tampered["block_count"] + 1
    assert verify_checksum(tampered) is False

def test_analog_point_validation_and_range_resolution():
    """AUDIT_REPORT.md §2.1/§2.3/§2.4: a valid AI/AO pair against a declared
    analog point compiles, and the Compiler resolves the AI block's [min, max]
    onto the isolated runtime instance (the engine has no live Project ref)."""
    from logic_studio.blocks.analog_io import AnalogInputBlock, AnalogOutputBlock

    p = Project()
    p.settings["analog_points"] = [
        {"address": "AI.TEMP", "name": "Temp", "unit": "°C", "min": -40.0, "max": 150.0, "direction": "input"},
        {"address": "AO.SETPOINT", "name": "Setpoint", "unit": "°C", "min": 0.0, "max": 100.0, "direction": "output"},
    ]

    ai = AnalogInputBlock()
    ai.properties["Address"] = "AI.TEMP"
    ao = AnalogOutputBlock()
    ao.properties["Address"] = "AO.SETPOINT"
    ai.outputs[0].connect(ao.inputs[0])

    p.add_block(ai)
    p.add_block(ao)

    c = Compiler(p)
    res = c.compile()
    assert res is not None, f"Compile failed: {c.errors}"

    compiled_ai = res["program"].block_map[ai.uuid]
    assert compiled_ai._range_min == -40.0
    assert compiled_ai._range_max == 150.0

def test_quality_stuck_zero_tolerance_warns():
    """fix/safety-block-semantics §1.4: Stuck Scans configured with the
    tolerance left at its bit-exact default is a compile WARNING, not an
    error -- it's a real hazard on live hardware but a legitimate setup
    for a purely digital/simulated signal source."""
    from logic_studio.blocks.analog_processing import QualityBlock

    p = Project()
    q = QualityBlock()
    q.properties["Stuck Scans"] = 3
    q.properties["Range Source"] = "Własny"  # §4: unrelated to this test, avoid its own unconnected-AI error
    p.add_block(q)

    c = Compiler(p)
    res = c.compile()
    assert res is not None
    assert any("Stuck Tolerance" in w for w in c.warnings)

def test_quality_stuck_nonzero_tolerance_does_not_warn():
    from logic_studio.blocks.analog_processing import QualityBlock

    p = Project()
    q = QualityBlock()
    q.properties["Stuck Scans"] = 3
    q.properties["Stuck Tolerance"] = 0.05
    q.properties["Range Source"] = "Własny"  # §4: unrelated to this test, avoid its own unconnected-AI error
    p.add_block(q)

    c = Compiler(p)
    res = c.compile()
    assert res is not None
    assert not any("Stuck Tolerance" in w for w in c.warnings)

# ---- fix/safety-block-semantics §4: QUALITY range from the analog point --

def test_quality_range_source_from_analog_point_resolves_and_exports():
    from logic_studio.blocks.analog_io import AnalogInputBlock
    from logic_studio.blocks.analog_processing import QualityBlock

    p = Project()
    p.settings["analog_points"] = [
        {"address": "AI.TEMP", "name": "Temp", "unit": "°C", "min": -40.0, "max": 150.0, "direction": "input"},
    ]
    ai = AnalogInputBlock()
    ai.properties["Address"] = "AI.TEMP"
    q = QualityBlock()
    assert q.properties["Range Source"] == "Z punktu analogowego"  # default for a NEW block
    ai.outputs[0].connect(q.inputs[0])
    p.add_block(ai)
    p.add_block(q)

    c = Compiler(p)
    res = c.compile()
    assert res is not None, f"Compile failed: {c.errors}"

    compiled_q = res["program"].block_map[q.uuid]
    assert compiled_q._range_min == -40.0
    assert compiled_q._range_max == 150.0

    assert res["blocks"][q.uuid]["properties"]["_resolved_range_min"] == -40.0
    assert res["blocks"][q.uuid]["properties"]["_resolved_range_max"] == 150.0

def test_quality_range_source_from_analog_point_ignores_own_min_max():
    """The resolved AI range must WIN over this block's own (stale/
    disagreeing) Min/Max properties -- the exact schematic §4's DOWÓD
    describes: AI(-40..150) -> QUALITY(Min=0, Max=100)."""
    from logic_studio.blocks.analog_io import AnalogInputBlock
    from logic_studio.blocks.analog_processing import QualityBlock

    p = Project()
    p.settings["analog_points"] = [
        {"address": "AI.TEMP", "name": "Temp", "unit": "°C", "min": -40.0, "max": 150.0, "direction": "input"},
    ]
    ai = AnalogInputBlock()
    ai.properties["Address"] = "AI.TEMP"
    q = QualityBlock()
    q.properties["Min"] = 0.0
    q.properties["Max"] = 100.0
    ai.outputs[0].connect(q.inputs[0])
    p.add_block(ai)
    p.add_block(q)

    c = Compiler(p)
    res = c.compile()
    assert res is not None

    compiled_q = res["program"].block_map[q.uuid]
    compiled_q.inputs[0].value = 120.0  # inside Min/Max=0..100 -- would be Out Of Range there
    compiled_q.evaluate()
    assert compiled_q.outputs[1].value is False  # Out Of Range -- inside the AI's -40..150

def test_quality_range_source_requires_direct_ai_input():
    """§4.2: In not wired directly to an input.ai block (unconnected, or
    wired through something else) is a compile ERROR while Range Source ==
    "Z punktu analogowego"."""
    from logic_studio.blocks.analog_processing import QualityBlock

    p = Project()
    q = QualityBlock()  # default Range Source, In left unconnected
    p.add_block(q)

    c = Compiler(p)
    res = c.compile()
    assert res is None
    assert any("Range Source" in e for e in c.errors)

def test_quality_range_source_wlasny_uses_own_min_max_unaffected():
    from logic_studio.blocks.analog_processing import QualityBlock

    p = Project()
    q = QualityBlock()
    q.properties["Range Source"] = "Własny"
    q.properties["Min"] = 0.0
    q.properties["Max"] = 100.0
    p.add_block(q)

    c = Compiler(p)
    res = c.compile()
    assert res is not None, f"Compile failed: {c.errors}"

    compiled_q = res["program"].block_map[q.uuid]
    compiled_q.inputs[0].value = 150.0
    compiled_q.evaluate()
    assert compiled_q.outputs[1].value is True  # Out Of Range against its OWN 0..100

def test_invalid_analog_input_address_fails_compilation():
    from logic_studio.blocks.analog_io import AnalogInputBlock

    p = Project()
    ai = AnalogInputBlock()
    ai.properties["Address"] = "AI.DOES_NOT_EXIST"
    p.add_block(ai)

    c = Compiler(p)
    res = c.compile()
    assert res is None
    assert any("Invalid AI Address" in e for e in c.errors)

def test_duplicate_analog_output_address_fails():
    from logic_studio.blocks.analog_io import AnalogOutputBlock

    p = Project()
    p.settings["analog_points"] = [
        {"address": "AO.X", "name": "X", "unit": "", "min": 0.0, "max": 10.0, "direction": "output"},
    ]
    ao1 = AnalogOutputBlock()
    ao1.properties["Address"] = "AO.X"
    ao2 = AnalogOutputBlock()
    ao2.properties["Address"] = "AO.X"
    p.add_block(ao1)
    p.add_block(ao2)

    c = Compiler(p)
    res = c.compile()
    assert res is None
    assert any("Multiple analog outputs" in e for e in c.errors)

def test_duplicate_analog_input_address_warns_not_fails():
    from logic_studio.blocks.analog_io import AnalogInputBlock

    p = Project()
    p.settings["analog_points"] = [
        {"address": "AI.X", "name": "X", "unit": "", "min": 0.0, "max": 10.0, "direction": "input"},
    ]
    ai1 = AnalogInputBlock()
    ai1.properties["Address"] = "AI.X"
    ai2 = AnalogInputBlock()
    ai2.properties["Address"] = "AI.X"
    p.add_block(ai1)
    p.add_block(ai2)

    c = Compiler(p)
    res = c.compile()
    assert res is not None, f"Compile failed: {c.errors}"
    assert any("Multiple AI blocks read address" in w for w in c.warnings)

def test_compiler_deterministic_execution_order():
    """AUDIT_REPORT.md §6: recompiling the same graph (same blocks, same UUIDs)
    must give the same execution_order regardless of the order blocks were
    added to the project."""
    from logic_studio.blocks.timers import TON

    # Same block instances (and therefore the same UUIDs) reused across every
    # project below — only the insertion order into `blocks` changes.
    di = DigitalOutputBlock()  # stand-in leaf; not actually wired
    gate1 = AndGate()
    gate2 = OrGate()
    timer = TON()

    gate1.outputs[0].connect(timer.inputs[0])
    timer.outputs[0].connect(gate2.inputs[0])
    gate2.outputs[0].connect(gate1.inputs[1])  # feedback through the stateful timer

    blocks_by_name = {"gate1": gate1, "gate2": gate2, "timer": timer, "di": di}
    orderings = [
        ["gate1", "gate2", "timer", "di"],
        ["di", "timer", "gate2", "gate1"],
        ["timer", "di", "gate1", "gate2"],
        ["gate2", "gate1", "di", "timer"],
        ["di", "gate2", "timer", "gate1"],
    ]

    results = []
    for ordering in orderings:
        p = Project()
        for name in ordering:
            p.add_block(blocks_by_name[name])

        c = Compiler(p)
        res = c.compile()
        assert res is not None, f"Compile failed for ordering {ordering}: {c.errors}"
        results.append(res["program"].execution_order)

    assert all(r == results[0] for r in results), f"execution_order not deterministic: {results}"

def test_compiler_allows_stateful_cycles():
    p = Project()
    from logic_studio.blocks.timers import TON

    b1 = AndGate()
    b2 = TON()

    b1.outputs[0].connect(b2.inputs[0])
    b2.outputs[0].connect(b1.inputs[0])

    p.add_block(b1)
    p.add_block(b2)

    c = Compiler(p)
    res = c.compile()

    assert res is not None # Should pass because TonBlock is stateful
    assert len(c.errors) == 0


# ---- feat/macro-blocks: Compiler.compile() runs against the macro-
# expanded block list (core/macros.py::expand_project()) instead of the
# live project — see that module's docstring for the overall design. ----

def test_compile_expands_a_macro_instance_before_validating():
    """A macro instance's own type_id ("macro.<def_id>") must never reach
    Validator/GraphBuilder/Exporter — only the flattened blocks it expands
    to. If expansion didn't run, Validator would reject the unknown
    type_id outright."""
    from logic_studio.blocks.io_blocks import DigitalInputBlock
    from logic_studio.blocks.macro_instance import MacroInstanceBlock
    from logic_studio.core.macros import build_definition, set_definition, get_definition

    gate = AndGate()
    dummy_di1, dummy_di2, dummy_do = DigitalInputBlock(), DigitalInputBlock(), DigitalOutputBlock()
    dummy_di1.outputs[0].connect(gate.inputs[0])
    dummy_di2.outputs[0].connect(gate.inputs[1])
    gate.outputs[0].connect(dummy_do.inputs[0])
    definition, _ = build_definition("AndMacro", [gate])

    p = Project()
    set_definition(p, "andmacro", definition)

    di1, di2 = DigitalInputBlock(), DigitalInputBlock()
    do = DigitalOutputBlock()
    inst = MacroInstanceBlock(def_id="andmacro")
    inst.configure(get_definition(p, "andmacro"))
    di1.outputs[0].connect(inst.inputs[0])
    di2.outputs[0].connect(inst.inputs[1])
    inst.outputs[0].connect(do.inputs[0])
    for b in (di1, di2, do, inst):
        p.add_block(b)

    c = Compiler(p)
    res = c.compile()

    assert res is not None, c.errors
    program = res["program"]
    type_ids = {b.type_id for b in program.blocks}
    assert "macro.andmacro" not in type_ids
    assert "logic.and" in type_ids
    # execution_order must reference the expanded inner gate, never the
    # (never-compiled) macro instance's own uuid.
    assert inst.uuid not in program.execution_order

def test_compile_reports_missing_macro_definition_like_a_validator_error():
    from logic_studio.blocks.macro_instance import MacroInstanceBlock

    p = Project()
    p.add_block(MacroInstanceBlock(def_id="doesnotexist"))

    c = Compiler(p)
    res = c.compile()

    assert res is None
    assert any("doesnotexist" in e for e in c.errors)
    assert c.status == "COMPILE_FAILED"

def test_compile_never_mutates_the_live_project_with_a_macro_instance():
    from logic_studio.blocks.io_blocks import DigitalInputBlock
    from logic_studio.blocks.macro_instance import MacroInstanceBlock
    from logic_studio.core.macros import build_definition, set_definition, get_definition

    gate = AndGate()
    dummy_di1, dummy_di2, dummy_do = DigitalInputBlock(), DigitalInputBlock(), DigitalOutputBlock()
    dummy_di1.outputs[0].connect(gate.inputs[0])
    dummy_di2.outputs[0].connect(gate.inputs[1])
    gate.outputs[0].connect(dummy_do.inputs[0])
    definition, _ = build_definition("AndMacro", [gate])

    p = Project()
    set_definition(p, "andmacro", definition)
    inst = MacroInstanceBlock(def_id="andmacro")
    inst.configure(get_definition(p, "andmacro"))
    p.add_block(inst)

    Compiler(p).compile()

    assert p.blocks == [inst]
    assert p.blocks[0].type_id == "macro.andmacro"
