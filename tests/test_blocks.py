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

def test_tp_start_with_active_input_no_keyerror():
    """Regression for AUDIT_REPORT.md §1.1: ExecutionEngine.start() clears
    simulation_state before calling reset_runtime_state(). TP must not depend
    on a key surviving that clear() to evaluate safely on the very first scan."""
    from logic_studio.core.project import Project
    from logic_studio.compiler.core import Compiler
    from logic_studio.engine.execution import ExecutionEngine
    from logic_studio.engine.io_provider import SimulationIOProvider
    from logic_studio.engine.time_provider import SimulationTimeProvider
    from logic_studio.blocks.io_blocks import DigitalInputBlock

    project = Project()
    di = DigitalInputBlock()
    di.properties["Address"] = "ELA01.DI01"
    tp = TP()
    di.outputs[0].connect(tp.inputs[0])
    project.add_block(di)
    project.add_block(tp)

    compiler = Compiler(project)
    res = compiler.compile()
    assert res is not None, f"Compile failed: {compiler.errors}"

    io = SimulationIOProvider()
    io.set_digital_input("ELA01.DI01", True)  # IN already True before start()
    engine = ExecutionEngine(res.get("program"), io, SimulationTimeProvider())

    engine.start()
    engine.step()  # Must not raise KeyError('last_in')

    assert engine.state != "FAULT"

def test_button_monostable():
    from logic_studio.blocks.system_signals import ButtonBlock

    b = ButtonBlock()
    b.properties["Mode"] = "Monostabilny"

    b.simulation_state["pressed"] = False
    b.evaluate()
    assert b.outputs[0].value is False

    b.simulation_state["pressed"] = True
    b.evaluate()
    assert b.outputs[0].value is True

    b.simulation_state["pressed"] = False
    b.evaluate()
    assert b.outputs[0].value is False

def test_button_bistable():
    from logic_studio.blocks.system_signals import ButtonBlock

    b = ButtonBlock()
    b.properties["Mode"] = "Bistabilny"

    b.simulation_state["pressed"] = False
    b.evaluate()
    assert b.outputs[0].value is False

    b.simulation_state["pressed"] = True
    b.evaluate()
    assert b.outputs[0].value is True  # rising edge toggles latch ON

    b.evaluate()  # held pressed, no new edge
    assert b.outputs[0].value is True

    b.simulation_state["pressed"] = False
    b.evaluate()
    assert b.outputs[0].value is True  # released, latch holds

    b.simulation_state["pressed"] = True
    b.evaluate()
    assert b.outputs[0].value is False  # second rising edge toggles latch OFF

def test_analog_input_quality_and_holdover():
    """AUDIT_REPORT.md §2.1: AI holds the last good value across a bad-quality
    scan instead of passing garbage downstream."""
    from logic_studio.blocks.analog_io import AnalogInputBlock

    class FakeIO:
        def __init__(self):
            self.value = 25.0
        def read_analog_input(self, address):
            return self.value

    class FakeEngine:
        def __init__(self, io):
            self.io = io

    ai = AnalogInputBlock()
    ai.set_range(-40.0, 150.0)
    io = FakeIO()
    engine = FakeEngine(io)

    ai.evaluate(engine)
    assert ai.outputs[0].value == 25.0
    assert ai.outputs[1].value is True

    # Out of range beyond the 10% margin -> quality False, value held.
    io.value = 1000.0
    ai.evaluate(engine)
    assert ai.outputs[1].value is False
    assert ai.outputs[0].value == 25.0

    # Back in range -> resumes tracking.
    io.value = 30.0
    ai.evaluate(engine)
    assert ai.outputs[1].value is True
    assert ai.outputs[0].value == 30.0

def test_analog_input_no_good_value_yet():
    from logic_studio.blocks.analog_io import AnalogInputBlock

    ai = AnalogInputBlock()
    ai.set_range(0.0, 100.0)
    ai.evaluate(engine=None)  # no IOProvider -> raw stays None
    assert ai.outputs[0].value == 0.0
    assert ai.outputs[1].value is False

def test_analog_input_nan_and_range_margin():
    import math
    from logic_studio.blocks.analog_io import AnalogInputBlock

    class FakeIO:
        def __init__(self, v):
            self.v = v
        def read_analog_input(self, address):
            return self.v

    class FakeEngine:
        def __init__(self, io):
            self.io = io

    ai = AnalogInputBlock()
    ai.set_range(0.0, 100.0)  # 10% margin == 10 units either side

    engine = FakeEngine(FakeIO(math.nan))
    ai.evaluate(engine)
    assert ai.outputs[1].value is False

    engine.io.v = -5.0  # inside the margin -> still good
    ai.evaluate(engine)
    assert ai.outputs[1].value is True
    assert ai.outputs[0].value == -5.0

    engine.io.v = -20.0  # beyond the margin -> bad, holds last good
    ai.evaluate(engine)
    assert ai.outputs[1].value is False
    assert ai.outputs[0].value == -5.0

def test_analog_output_buffers_and_flushes():
    from logic_studio.blocks.analog_io import AnalogOutputBlock

    class FakeEngine:
        def __init__(self):
            self.buffered = {}
        def queue_analog_output(self, address, value):
            self.buffered[address] = value

    ao = AnalogOutputBlock()
    ao.properties["Address"] = "AI.TEST"
    engine = FakeEngine()

    ao.inputs[0].value = 12.5
    ao.evaluate(engine)
    assert engine.buffered["AI.TEST"] == 12.5

    ao.inputs[0].value = None
    ao.evaluate(engine)
    assert engine.buffered["AI.TEST"] == 0.0

def test_deadband_first_scan_always_passes():
    from logic_studio.blocks.analog_processing import DeadbandBlock

    d = DeadbandBlock()
    d.properties["Deadband"] = 1.0
    d.inputs[0].value = 42.0
    d.evaluate()
    assert d.outputs[0].value == 42.0
    assert d.outputs[1].value is True

def test_deadband_absolute_mode_holds_below_threshold():
    from logic_studio.blocks.analog_processing import DeadbandBlock

    d = DeadbandBlock()
    d.properties["Mode"] = "Bezwzględny"
    d.properties["Deadband"] = 1.0

    d.inputs[0].value = 10.0
    d.evaluate()  # first scan, passes through
    assert d.outputs[0].value == 10.0

    for v in [10.3, 10.6, 10.9]:  # each step < 1.0 away from last REPORTED value
        d.inputs[0].value = v
        d.evaluate()
        assert d.outputs[0].value == 10.0, f"Out should stay frozen at 10.0 for In={v}"
        assert d.outputs[1].value is False

def test_deadband_absolute_mode_passes_on_threshold_crossed():
    from logic_studio.blocks.analog_processing import DeadbandBlock

    d = DeadbandBlock()
    d.properties["Mode"] = "Bezwzględny"
    d.properties["Deadband"] = 1.0

    d.inputs[0].value = 10.0
    d.evaluate()  # first scan

    d.inputs[0].value = 11.5  # 1.5 away -> crosses the 1.0 threshold
    d.evaluate()
    assert d.outputs[0].value == 11.5
    assert d.outputs[1].value is True

    # Changed pulses for exactly this one scan, not the next.
    d.inputs[0].value = 11.5
    d.evaluate()
    assert d.outputs[1].value is False

def test_deadband_percent_mode_uses_range():
    from logic_studio.blocks.analog_processing import DeadbandBlock

    d = DeadbandBlock()
    d.properties["Mode"] = "Procentowy"
    d.properties["Range"] = 200.0
    d.properties["Deadband"] = 5.0  # 5% of 200 == 10.0 absolute

    d.inputs[0].value = 100.0
    d.evaluate()  # first scan

    d.inputs[0].value = 108.0  # 8 < 10 threshold -> held
    d.evaluate()
    assert d.outputs[0].value == 100.0
    assert d.outputs[1].value is False

    d.inputs[0].value = 111.0  # 11 >= 10 threshold -> passes
    d.evaluate()
    assert d.outputs[0].value == 111.0
    assert d.outputs[1].value is True

def test_quality_block_out_of_range_and_good():
    from logic_studio.blocks.analog_processing import QualityBlock

    q = QualityBlock()
    q.properties["Min"] = 0.0
    q.properties["Max"] = 100.0

    q.inputs[0].value = 50.0
    q.evaluate()
    assert q.outputs[0].value is True   # Good
    assert q.outputs[1].value is False  # Out Of Range

    q.inputs[0].value = 150.0
    q.evaluate()
    assert q.outputs[0].value is False
    assert q.outputs[1].value is True

def test_quality_block_rate_fault():
    from logic_studio.blocks.analog_processing import QualityBlock

    q = QualityBlock()
    q.properties["Max Rate"] = 5.0

    q.inputs[0].value = 10.0
    q.evaluate()
    assert q.outputs[2].value is False  # no previous value to compare yet

    q.inputs[0].value = 20.0  # jumped 10 in one scan, > Max Rate 5
    q.evaluate()
    assert q.outputs[2].value is True
    assert q.outputs[0].value is False

def test_quality_block_stuck_signal():
    from logic_studio.blocks.analog_processing import QualityBlock

    q = QualityBlock()
    q.properties["Stuck Scans"] = 2

    q.inputs[0].value = 7.0
    q.evaluate()
    assert q.outputs[3].value is False  # only one sample so far

    q.inputs[0].value = 7.0
    q.evaluate()
    assert q.outputs[3].value is False  # one unchanged scan, threshold is 2

    q.inputs[0].value = 7.0
    q.evaluate()
    assert q.outputs[3].value is True   # two unchanged scans in a row
    assert q.outputs[0].value is False

    q.inputs[0].value = 8.0  # value moves -> Stuck clears
    q.evaluate()
    assert q.outputs[3].value is False

def test_quality_block_non_numeric_input_is_not_good():
    from logic_studio.blocks.analog_processing import QualityBlock

    q = QualityBlock()
    q.evaluate()  # no input connected -> value is None
    assert q.outputs[0].value is False

def test_comparator_default_behavior_unchanged():
    """AUDIT_REPORT.md §5: Hysteresis=T On=T Off=0 must behave exactly like
    before this feature existed, and is_stateful must be False."""
    from logic_studio.blocks.comparators import GreaterBlock, BetweenBlock

    g = GreaterBlock()
    assert g.is_stateful is False
    g.inputs[0].value = 5.0
    g.inputs[1].value = 5.0
    g.evaluate()
    assert g.outputs[0].value is False  # 5 > 5 is False, no hysteresis lag

    g.inputs[0].value = 5.0001
    g.evaluate()
    assert g.outputs[0].value is True

    b = BetweenBlock()
    assert b.is_stateful is False

def test_comparator_hysteresis_suppresses_chatter():
    from logic_studio.blocks.comparators import GreaterBlock

    g = GreaterBlock()
    g.properties["Hysteresis"] = 2.0
    assert g.is_stateful is True

    g.inputs[1].value = 10.0  # threshold

    g.inputs[0].value = 11.0  # above threshold -> True
    g.evaluate()
    assert g.outputs[0].value is True

    g.inputs[0].value = 9.0  # dropped below 10 but still within the 2.0 band -> stays True
    g.evaluate()
    assert g.outputs[0].value is True

    g.inputs[0].value = 7.5  # more than 2.0 below the threshold -> now False
    g.evaluate()
    assert g.outputs[0].value is False

    g.inputs[0].value = 10.5  # rising edge is NOT delayed by hysteresis
    g.evaluate()
    assert g.outputs[0].value is True

def test_comparator_equal_hysteresis_is_a_tolerance_band():
    from logic_studio.blocks.comparators import EqualBlock

    eq = EqualBlock()
    eq.properties["Hysteresis"] = 0.5

    eq.inputs[0].value = 10.0
    eq.inputs[1].value = 10.0
    eq.evaluate()
    assert eq.outputs[0].value is True

    eq.inputs[0].value = 10.3  # within the 0.5 tolerance band -> still True
    eq.evaluate()
    assert eq.outputs[0].value is True

    eq.inputs[0].value = 11.0  # beyond the band -> False
    eq.evaluate()
    assert eq.outputs[0].value is False

def test_comparator_t_on_delay():
    from logic_studio.blocks.comparators import GreaterBlock

    engine = MockEngine()
    g = GreaterBlock()
    g.properties["T On (ms)"] = 300
    assert g.is_stateful is True

    g.inputs[0].value = 10.0
    g.inputs[1].value = 5.0  # 10 > 5 -> raw True immediately

    g.evaluate(engine)
    assert g.outputs[0].value is False  # not yet held for 300ms

    engine.time.advance(200)
    g.evaluate(engine)
    assert g.outputs[0].value is False  # only 200ms elapsed

    engine.time.advance(150)  # total 350ms
    g.evaluate(engine)
    assert g.outputs[0].value is True

def test_comparator_t_off_delay():
    from logic_studio.blocks.comparators import GreaterBlock

    engine = MockEngine()
    g = GreaterBlock()
    g.properties["T Off (ms)"] = 300

    g.inputs[0].value = 10.0
    g.inputs[1].value = 5.0
    g.evaluate(engine)
    assert g.outputs[0].value is True  # T On is 0 -> immediate

    g.inputs[0].value = 1.0  # now False, but T Off must elapse first
    g.evaluate(engine)
    assert g.outputs[0].value is True

    engine.time.advance(350)
    g.evaluate(engine)
    assert g.outputs[0].value is False

def test_comparator_t_on_requires_engine_time():
    from logic_studio.blocks.comparators import GreaterBlock

    g = GreaterBlock()
    g.properties["T On (ms)"] = 100
    g.inputs[0].value = 10.0
    g.inputs[1].value = 5.0

    with pytest.raises(RuntimeError):
        g.evaluate(engine=None)

def test_between_hysteresis_widens_window():
    from logic_studio.blocks.comparators import BetweenBlock

    b = BetweenBlock()
    b.properties["Hysteresis"] = 1.0
    b.inputs[0].value = 10.0  # Min
    b.inputs[2].value = 20.0  # Max

    b.inputs[1].value = 15.0  # inside
    b.evaluate()
    assert b.outputs[0].value is True

    b.inputs[1].value = 20.5  # just outside raw window but within +1 margin
    b.evaluate()
    assert b.outputs[0].value is True

    b.inputs[1].value = 22.0  # beyond the widened window
    b.evaluate()
    assert b.outputs[0].value is False

def test_pin_type_checking():
    from logic_studio.blocks.logic_gates import AndGate
    from logic_studio.blocks.math_blocks import AddBlock

    a = AndGate()
    add = AddBlock()

    # Try to connect Add output (REAL) to AND input (BOOL)
    assert add.outputs[0].connect(a.inputs[0]) is False

    # Try to connect AND output (BOOL) to Add input (REAL)
    assert a.outputs[0].connect(add.inputs[0]) is False
