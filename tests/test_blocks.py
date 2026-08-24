import pytest
import time
from logic_studio.blocks.timers import TON, TOF, TP
from logic_studio.blocks.counters import CTU, CTD, CTUD
from logic_studio.blocks.memory import SR, RS
from logic_studio.blocks.math_blocks import DivBlock
from logic_studio.blocks import register_builtin_blocks
from logic_studio.engine.time_provider import SimulationTimeProvider

class MockEngine:
    def __init__(self):
        self.time = SimulationTimeProvider()


register_builtin_blocks()

def test_ton():
    engine = MockEngine()
    t = TON()
    t.inputs[1].value = 50 # 50ms PT
    t.inputs[0].value = True
    t.evaluate(engine)
    assert t.outputs[0].value is False

    engine.time.advance(60) # wait > 50ms
    t.evaluate(engine)
    assert t.outputs[0].value is True

    t.inputs[0].value = False
    t.evaluate(engine)
    assert t.outputs[0].value is False
    assert t.outputs[1].value == 0

def test_tof():
    engine = MockEngine()
    t = TOF()
    t.inputs[1].value = 50
    t.inputs[0].value = True
    t.evaluate(engine)
    assert t.outputs[0].value is True

    t.inputs[0].value = False
    t.evaluate(engine)
    assert t.outputs[0].value is True # Still true, timing off

    engine.time.advance(60)
    t.evaluate(engine)
    assert t.outputs[0].value is False # Turned off

def test_tp():
    engine = MockEngine()
    t = TP()
    t.inputs[1].value = 50
    t.inputs[0].value = True # Rising edge
    t.evaluate(engine)
    assert t.outputs[0].value is True

    t.inputs[0].value = True # Static high
    engine.time.advance(60)
    t.evaluate(engine)
    assert t.outputs[0].value is False # Done pulsing

    t.evaluate(engine) # Should not restart pulse
    assert t.outputs[0].value is False

def test_ctu():
    c = CTU()
    c.inputs[2].value = 3 # PV

    # Needs edges
    for _ in range(3):
        c.inputs[0].value = True
        c.evaluate()
        c.inputs[0].value = False
        c.evaluate()

    assert c.outputs[0].value is True # Reached 3
    assert c.outputs[1].value == 3

    # Static high should not double count
    c.inputs[0].value = True
    c.evaluate()
    c.evaluate()
    assert c.outputs[1].value == 4

def test_ctd():
    c = CTD()
    c.inputs[2].value = 2 # PV
    c.inputs[1].value = True # Load
    c.evaluate()
    assert c.outputs[1].value == 2

    c.inputs[1].value = False
    c.inputs[0].value = True
    c.evaluate()
    c.inputs[0].value = False
    c.evaluate()

    assert c.outputs[0].value is False
    c.inputs[0].value = True
    c.evaluate()

    assert c.outputs[1].value == 0
    assert c.outputs[0].value is True

def test_sr_rs_priority():
    sr = SR()
    sr.inputs[0].value = True # Set
    sr.inputs[1].value = True # Reset
    sr.evaluate()
    assert sr.outputs[0].value is True # Set dominant

    rs = RS()
    rs.inputs[0].value = True # Reset
    rs.inputs[1].value = True # Set
    rs.evaluate()
    assert rs.outputs[0].value is False # Reset dominant

def test_div_by_zero():
    d = DivBlock()
    d.inputs[0].value = 10
    d.inputs[1].value = 0
    d.evaluate()
    # Must not crash, should output safe 0.0
    assert d.outputs[0].value == 0.0

def test_pin_single_driver():
    from logic_studio.blocks.logic_gates import AndGate, OrGate
    a = AndGate()
    b = OrGate()
    c = AndGate()

    # Connect a to b's input 0
    assert a.outputs[0].connect(b.inputs[0]) is True

    # Try to connect c to b's input 0 - MUST FAIL
    assert c.outputs[0].connect(b.inputs[0]) is False

    # But a can connect to b's input 1
    assert a.outputs[0].connect(b.inputs[1]) is True

def test_pin_type_checking():
    from logic_studio.blocks.logic_gates import AndGate
    from logic_studio.blocks.math_blocks import AddBlock

    a = AndGate()
    add = AddBlock()

    # Try to connect Add output (REAL) to AND input (BOOL)
    assert add.outputs[0].connect(a.inputs[0]) is False

    # Try to connect AND output (BOOL) to Add input (REAL)
    assert a.outputs[0].connect(add.inputs[0]) is False
