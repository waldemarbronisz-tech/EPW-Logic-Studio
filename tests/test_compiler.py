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
