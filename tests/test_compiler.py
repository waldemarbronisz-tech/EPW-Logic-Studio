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
