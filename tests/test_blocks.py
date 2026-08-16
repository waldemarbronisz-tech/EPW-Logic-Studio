import pytest
import time
from logic_studio.blocks.timers import TON, TOF, TP
from logic_studio.blocks.counters import CTU, CTD, CTUD
from logic_studio.blocks.memory import SR, RS
from logic_studio.blocks.math_blocks import DivBlock
from logic_studio.blocks import register_builtin_blocks

register_builtin_blocks()

def test_ton():
    t = TON()
    t.inputs[1].value = 50 # 50ms PT
    t.inputs[0].value = True
    t.evaluate()
    assert t.outputs[0].value is False

    time.sleep(0.06) # wait > 50ms
    t.evaluate()
    assert t.outputs[0].value is True

    t.inputs[0].value = False
    t.evaluate()
    assert t.outputs[0].value is False
    assert t.outputs[1].value == 0

def test_tof():
    t = TOF()
    t.inputs[1].value = 50
    t.inputs[0].value = True
    t.evaluate()
    assert t.outputs[0].value is True

    t.inputs[0].value = False
    t.evaluate()
    assert t.outputs[0].value is True # Still true, timing off

    time.sleep(0.06)
    t.evaluate()
    assert t.outputs[0].value is False # Turned off

def test_tp():
    t = TP()
    t.inputs[1].value = 50
    t.inputs[0].value = True # Rising edge
    t.evaluate()
    assert t.outputs[0].value is True

    t.inputs[0].value = True # Static high
    time.sleep(0.06)
    t.evaluate()
    assert t.outputs[0].value is False # Done pulsing

    t.evaluate() # Should not restart pulse
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
