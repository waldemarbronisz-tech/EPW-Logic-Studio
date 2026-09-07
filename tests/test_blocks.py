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

# ---- fix/safety-block-semantics §5: AI Max Hold (ms) -----------------------

class _FakeAnalogIO:
    def __init__(self, value=25.0):
        self.value = value
    def read_analog_input(self, address):
        return self.value

def test_analog_input_default_max_hold_is_unlimited_like_before():
    """§5.6: default 0 = no limit, IDENTICAL to this block's behavior
    before Max Hold existed -- needs no engine.time at all."""
    from logic_studio.blocks.analog_io import AnalogInputBlock

    class FakeEngine:
        def __init__(self, io):
            self.io = io

    ai = AnalogInputBlock()
    ai.set_range(0.0, 100.0)
    engine = FakeEngine(_FakeAnalogIO(50.0))
    ai.evaluate(engine)

    engine.io.value = None  # quality drops
    for _ in range(100000):
        ai.evaluate(engine)  # §5 DOWÓD's own reproduction: unlimited hold
    assert ai.outputs[0].value == 50.0
    assert ai.outputs[1].value is False
    assert ai.outputs[2].value is False  # Hold Expired never trips

def test_analog_input_hold_expires_and_falls_back_to_zero():
    from logic_studio.blocks.analog_io import AnalogInputBlock

    ai = AnalogInputBlock()
    ai.set_range(0.0, 100.0)
    ai.properties["Max Hold (ms)"] = 5000
    engine = MockEngine()
    engine.io = _FakeAnalogIO(50.0)

    ai.evaluate(engine)
    assert ai.outputs[0].value == 50.0
    assert ai.outputs[2].value is False

    engine.io.value = None  # measurement disappears
    engine.time.advance(4999)
    ai.evaluate(engine)
    assert ai.outputs[2].value is False  # not yet expired
    assert ai.outputs[0].value == 50.0  # still holding

    engine.time.advance(2)  # now 5001ms since the last good reading
    ai.evaluate(engine)
    assert ai.outputs[2].value is True  # Hold Expired
    assert ai.outputs[0].value == 0.0   # "Zero" (default)
    assert ai.outputs[1].value is False  # Quality still False regardless

def test_analog_input_hold_timeout_value_last_good():
    from logic_studio.blocks.analog_io import AnalogInputBlock

    ai = AnalogInputBlock()
    ai.set_range(0.0, 100.0)
    ai.properties["Max Hold (ms)"] = 1000
    ai.properties["Hold Timeout Value"] = "Ostatnia dobra"
    engine = MockEngine()
    engine.io = _FakeAnalogIO(42.0)

    ai.evaluate(engine)
    engine.io.value = None
    engine.time.advance(1500)
    ai.evaluate(engine)
    assert ai.outputs[2].value is True
    assert ai.outputs[0].value == 42.0  # holds at the last good value, not 0

def test_analog_input_hold_timeout_value_range_floor():
    from logic_studio.blocks.analog_io import AnalogInputBlock

    ai = AnalogInputBlock()
    ai.set_range(-40.0, 150.0)
    ai.properties["Max Hold (ms)"] = 1000
    ai.properties["Hold Timeout Value"] = "Dolna granica zakresu"
    engine = MockEngine()
    engine.io = _FakeAnalogIO(50.0)

    ai.evaluate(engine)
    engine.io.value = None
    engine.time.advance(1500)
    ai.evaluate(engine)
    assert ai.outputs[2].value is True
    assert ai.outputs[0].value == -40.0

def test_analog_input_good_reading_before_expiry_resets_the_hold_clock():
    from logic_studio.blocks.analog_io import AnalogInputBlock

    ai = AnalogInputBlock()
    ai.set_range(0.0, 100.0)
    ai.properties["Max Hold (ms)"] = 1000
    engine = MockEngine()
    engine.io = _FakeAnalogIO(10.0)

    ai.evaluate(engine)
    engine.io.value = None
    engine.time.advance(900)
    ai.evaluate(engine)
    assert ai.outputs[2].value is False

    engine.io.value = 20.0  # a good reading arrives just before expiry
    ai.evaluate(engine)
    assert ai.outputs[2].value is False
    assert ai.outputs[0].value == 20.0

    engine.io.value = None
    engine.time.advance(900)  # < 1000ms since the FRESH good reading above
    ai.evaluate(engine)
    assert ai.outputs[2].value is False  # clock restarted, not expired yet

def test_analog_input_hold_check_requires_a_time_provider():
    from logic_studio.blocks.analog_io import AnalogInputBlock

    class FakeEngine:
        def __init__(self, io):
            self.io = io

    ai = AnalogInputBlock()
    ai.properties["Max Hold (ms)"] = 1000
    engine = FakeEngine(_FakeAnalogIO(10.0))
    with pytest.raises(RuntimeError):
        ai.evaluate(engine)

def test_analog_input_new_outputs_are_defined_from_the_start():
    """Hold Expired must never be None -- see also §8's "every output
    defined" audit."""
    from logic_studio.blocks.analog_io import AnalogInputBlock

    ai = AnalogInputBlock()
    ai.reset_runtime_state()
    ai.evaluate(engine=None)
    assert ai.outputs[2].value is False


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

# ---- fix/safety-block-semantics §8.2: audit found and fixed these too ---

def test_scale_no_signal_defines_output():
    from logic_studio.blocks.analog_processing import ScaleBlock

    s = ScaleBlock()
    s.evaluate()
    assert s.outputs[0].value == 0.0

def test_limit_no_signal_defines_output():
    from logic_studio.blocks.analog_processing import LimitBlock

    l = LimitBlock()
    l.evaluate()
    assert l.outputs[0].value == 0.0

def test_hysteresis_no_signal_holds_last_latched_state():
    from logic_studio.blocks.analog_processing import HysteresisBlock

    h = HysteresisBlock()
    h.evaluate()
    assert h.outputs[0].value is False  # __init__'s default _last_state

    h.inputs[0].value = 90.0  # above High Threshold (80) -> latches True
    h.evaluate()
    assert h.outputs[0].value is True

    h.inputs[0].value = None  # signal disappears
    h.evaluate()
    assert h.outputs[0].value is True  # holds the latch, doesn't reset

def test_moving_average_no_signal_ever_defines_output():
    from logic_studio.blocks.analog_processing import MovingAverageBlock

    m = MovingAverageBlock()
    m.evaluate()
    assert m.outputs[0].value == 0.0

def test_moving_average_holds_last_value_if_signal_drops_after_data():
    from logic_studio.blocks.analog_processing import MovingAverageBlock

    m = MovingAverageBlock()
    m.inputs[0].value = 10.0
    m.evaluate()
    assert m.outputs[0].value == 10.0

    m.inputs[0].value = None
    m.evaluate()
    assert m.outputs[0].value == 10.0  # holds, doesn't reset to 0.0

def test_tof_et_never_none_before_first_trigger():
    """fix/safety-block-semantics §8.2: ET (outputs[1]) was previously
    only ever set inside branches that require having been triggered
    (in_state True) at least once."""
    from logic_studio.blocks.timers import TOF

    engine = MockEngine()
    t = TOF()
    t.evaluate(engine)  # in_state False, never triggered
    assert t.outputs[1].value == 0
    assert t.outputs[0].value is False


def test_deadband_no_signal_defines_both_outputs():
    """fix/safety-block-semantics §8.1: previously left Out/Changed as
    None when In was never connected."""
    from logic_studio.blocks.analog_processing import DeadbandBlock

    d = DeadbandBlock()
    d.evaluate()
    assert d.outputs[0].value == 0.0
    assert d.outputs[1].value is False

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
    """fix/safety-block-semantics §2: Max Rate is now Max Rate (/s) —
    physical units per SECOND, computed from engine.time, not a bare
    per-scan delta. SimulationTimeProvider.advance() steps the clock
    explicitly, same as every timer test above."""
    from logic_studio.blocks.analog_processing import QualityBlock

    engine = MockEngine()
    q = QualityBlock()
    q.properties["Max Rate (/s)"] = 5.0  # 5 units/second

    q.inputs[0].value = 10.0
    q.evaluate(engine)
    assert q.outputs[2].value is False  # no previous value to compare yet

    engine.time.advance(1000)  # exactly 1 second later
    q.inputs[0].value = 20.0  # 10 units in 1s == 10/s, > 5/s limit
    q.evaluate(engine)
    assert q.outputs[2].value is True
    assert q.outputs[0].value is False

def test_quality_block_rate_fault_is_independent_of_cycle_time():
    """§2's own stated purpose: the SAME Max Rate (/s) setting must give
    the SAME Rate Fault verdict for the SAME physical rate of change,
    regardless of how often the engine happens to scan."""
    from logic_studio.blocks.analog_processing import QualityBlock

    for dt_ms, rate_faults in ((100, False), (50, True)):
        engine = MockEngine()
        q = QualityBlock()
        q.properties["Max Rate (/s)"] = 50.0

        q.inputs[0].value = 0.0
        q.evaluate(engine)

        engine.time.advance(dt_ms)
        q.inputs[0].value = 4.0  # 4 units per scan, regardless of dt
        q.evaluate(engine)
        assert q.outputs[2].value is rate_faults, f"dt_ms={dt_ms}"

def test_quality_block_rate_check_requires_a_time_provider():
    """§2.3: mirrors TimerBase — silently degrading to per-scan semantics
    for lack of a TimeProvider would reintroduce exactly the bug this
    section fixes, just invisibly. Must raise, not default to False."""
    from logic_studio.blocks.analog_processing import QualityBlock

    q = QualityBlock()
    q.properties["Max Rate (/s)"] = 5.0
    q.inputs[0].value = 10.0
    with pytest.raises(RuntimeError):
        q.evaluate(engine=None)

def test_quality_block_rate_check_disabled_needs_no_time_provider():
    """The default (Max Rate (/s)=0) must keep working with no engine at
    all -- backward compatibility for every existing bare evaluate() call
    that never touches this property."""
    from logic_studio.blocks.analog_processing import QualityBlock

    q = QualityBlock()
    q.inputs[0].value = 10.0
    q.evaluate(engine=None)  # must not raise
    assert q.outputs[2].value is False

def test_quality_block_zero_dt_skips_rate_check_without_crashing():
    from logic_studio.blocks.analog_processing import QualityBlock

    engine = MockEngine()
    q = QualityBlock()
    q.properties["Max Rate (/s)"] = 5.0

    q.inputs[0].value = 10.0
    q.evaluate(engine)
    q.inputs[0].value = 999.0  # huge jump, but same scan (dt=0)
    q.evaluate(engine)
    assert q.outputs[2].value is False

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

# ---- fix/safety-block-semantics §3: reset on a bad measurement ------------

def test_quality_block_signal_dropout_resets_rate_and_stuck_history():
    """§3 DOWÓD: a signal that vanished for a while and came back must not
    be compared (rate or stuck) against whatever was seen BEFORE the gap."""
    from logic_studio.blocks.analog_processing import QualityBlock

    engine = MockEngine()
    q = QualityBlock()
    q.properties["Max Rate (/s)"] = 5.0
    q.properties["Stuck Scans"] = 2

    q.inputs[0].value = 10.0
    q.evaluate(engine)

    # Signal drops out for a while (None comes through, e.g. a comms fault).
    for _ in range(5):
        engine.time.advance(100)
        q.inputs[0].value = None
        q.evaluate(engine)
        assert q.outputs[0].value is False  # not good while missing

    # Comes back FAR from the pre-dropout value -- must NOT be flagged as a
    # rate fault (nothing to legitimately compare against) or as stuck.
    engine.time.advance(100)
    q.inputs[0].value = 500.0
    q.evaluate(engine)
    assert q.outputs[2].value is False  # Rate Fault
    assert q.outputs[3].value is False  # Stuck


# ---- fix/safety-block-semantics §2.4: schema v8->v9 migration -------------

def test_v8_project_migrates_max_rate_to_per_second():
    from logic_studio.core.project import Project

    data = {
        "format": "EPW_LOGIC", "schema_version": 8,
        "settings": {"ela_devices": ["ELA01"], "ada_devices": ["ADA01"], "cycle_time_ms": 50},
        "blocks": [{
            "type_id": "analog.quality", "uuid": "q1",
            "properties": {"Max Rate": 5.0},
            "inputs": [], "outputs": [],
        }],
    }
    p = Project.deserialize(data)
    q = p.blocks[0]
    assert "Max Rate" not in q.properties
    assert q.properties["Max Rate (/s)"] == pytest.approx(100.0)  # 5.0 * 1000 / 50

def test_v8_project_with_max_rate_zero_migrates_cleanly_with_no_notice():
    from logic_studio.core.project import Project

    data = {
        "format": "EPW_LOGIC", "schema_version": 8,
        "settings": {"ela_devices": ["ELA01"], "ada_devices": ["ADA01"], "cycle_time_ms": 100},
        "blocks": [{
            "type_id": "analog.quality", "uuid": "q1",
            "properties": {"Max Rate": 0.0},
            "inputs": [], "outputs": [],
        }],
    }
    p = Project.deserialize(data)
    q = p.blocks[0]
    assert q.properties["Max Rate (/s)"] == 0.0
    assert "_max_rate_migration_notice" not in q.simulation_state

def test_v8_migration_flags_a_compile_warning_with_old_and_new_values():
    from logic_studio.core.project import Project
    from logic_studio.compiler.core import Compiler

    data = {
        "format": "EPW_LOGIC", "schema_version": 8,
        "settings": {"ela_devices": ["ELA01"], "ada_devices": ["ADA01"], "cycle_time_ms": 100},
        "blocks": [{
            "type_id": "analog.quality", "uuid": "q1",
            "properties": {"Max Rate": 5.0},
            "inputs": [], "outputs": [],
        }],
    }
    p = Project.deserialize(data)
    c = Compiler(p)
    res = c.compile()
    assert res is not None
    assert any("5" in w and "50" in w and "Max Rate" in w for w in c.warnings), c.warnings

    # Fires exactly once -- a second compile in the same session must not
    # repeat the same migration notice.
    c2 = Compiler(p)
    c2.compile()
    assert not any("Max Rate przeliczono" in w for w in c2.warnings)


# ---- fix/safety-block-semantics §4.4/§4.1: v9->v10 property backfill -----

def test_v9_project_analog_quality_defaults_to_wlasny_range_source():
    """§4.1/§4.4: an EXISTING project's analog.quality block must default
    to "Własny" (its own Min/Max, the pre-existing behavior) -- NEVER the
    new "Z punktu analogowego" default, which only makes sense for a
    freshly-placed block."""
    from logic_studio.core.project import Project

    data = {
        "format": "EPW_LOGIC", "schema_version": 9,
        "settings": {"ela_devices": ["ELA01"], "ada_devices": ["ADA01"], "cycle_time_ms": 100},
        "blocks": [{
            "type_id": "analog.quality", "uuid": "q1",
            "properties": {"Min": 0.0, "Max": 100.0},
            "inputs": [], "outputs": [],
        }],
    }
    p = Project.deserialize(data)
    q = p.blocks[0]
    assert q.properties["Range Source"] == "Własny"
    assert q.properties["Stuck Tolerance"] == 0.0

def test_v9_project_property_grid_row_actually_shows_up_after_migration():
    """The bug this migration exists to fix, made concrete: without the
    backfill, "Range Source"/"Stuck Tolerance" would be ABSENT from
    q.properties entirely (not just defaulted) for a project saved before
    those properties existed -- invisible in the property grid, which
    iterates block.properties.items()."""
    from logic_studio.core.project import Project

    data = {
        "format": "EPW_LOGIC", "schema_version": 9,
        "settings": {"ela_devices": ["ELA01"], "ada_devices": ["ADA01"], "cycle_time_ms": 100},
        "blocks": [{
            "type_id": "analog.quality", "uuid": "q1",
            "properties": {"Min": 0.0, "Max": 100.0},
            "inputs": [], "outputs": [],
        }],
    }
    p = Project.deserialize(data)
    assert "Range Source" in p.blocks[0].properties
    assert "Stuck Tolerance" in p.blocks[0].properties

def test_new_project_default_is_z_punktu_analogowego():
    """Contrast case for the migration tests above: a block placed FRESH
    (never round-tripped through a save file) keeps the new default."""
    from logic_studio.blocks.analog_processing import QualityBlock

    q = QualityBlock()
    assert q.properties["Range Source"] == "Z punktu analogowego"


# ---- fix/safety-block-semantics §5: v10->v11 property backfill -----------

def test_v10_project_input_ai_gets_max_hold_properties_backfilled():
    from logic_studio.core.project import Project

    data = {
        "format": "EPW_LOGIC", "schema_version": 10,
        "settings": {"ela_devices": ["ELA01"], "ada_devices": ["ADA01"], "cycle_time_ms": 100},
        "blocks": [{
            "type_id": "input.ai", "uuid": "ai1",
            "properties": {"Address": ""},
            "inputs": [], "outputs": [
                {"uuid": "p1", "name": "Value", "direction": "output", "data_type": "REAL", "connections": [], "disabled": False, "safety_relevant": False},
                {"uuid": "p2", "name": "Quality", "direction": "output", "data_type": "BOOL", "connections": [], "disabled": False, "safety_relevant": True},
            ],
        }],
    }
    p = Project.deserialize(data)
    ai = p.blocks[0]
    assert ai.properties["Max Hold (ms)"] == 0
    assert ai.properties["Hold Timeout Value"] == "Zero"
    # The new 3rd pin simply keeps its __init__ defaults -- nothing in the
    # 2-entry file "outputs" list to restore it FROM.
    assert len(ai.outputs) == 3
    assert ai.outputs[2].name == "Hold Expired"
    assert ai.outputs[2].safety_relevant is True


# ---- fix/safety-block-semantics §6: safety_relevant resync on load --------

def test_quality_good_resyncs_to_true_even_from_a_stale_saved_false():
    """§6.1: EVERY project saved before this PR has "false" stored for
    Good's safety_relevant (nothing ever set it) -- Pin.restore_fields()
    would otherwise trust that stale value forever, permanently hiding
    the new §6.2 warning on every existing project's quality blocks."""
    from logic_studio.core.project import Project

    data = {
        "format": "EPW_LOGIC", "schema_version": 10,
        "settings": {"ela_devices": ["ELA01"], "ada_devices": ["ADA01"], "cycle_time_ms": 100},
        "blocks": [{
            "type_id": "analog.quality", "uuid": "q1",
            "properties": {"Min": 0.0, "Max": 100.0, "Range Source": "Własny"},
            "inputs": [], "outputs": [
                {"uuid": "p1", "name": "Good", "direction": "output", "data_type": "BOOL", "connections": [], "disabled": False, "safety_relevant": False},
            ],
        }],
    }
    p = Project.deserialize(data)
    assert p.blocks[0].outputs[0].safety_relevant is True

def test_ai_quality_resyncs_to_true_even_from_a_stale_saved_false():
    from logic_studio.core.project import Project

    data = {
        "format": "EPW_LOGIC", "schema_version": 10,
        "settings": {"ela_devices": ["ELA01"], "ada_devices": ["ADA01"], "cycle_time_ms": 100},
        "blocks": [{
            "type_id": "input.ai", "uuid": "ai1",
            "properties": {"Address": ""},
            "inputs": [], "outputs": [
                {"uuid": "p1", "name": "Value", "direction": "output", "data_type": "REAL", "connections": [], "disabled": False, "safety_relevant": False},
                {"uuid": "p2", "name": "Quality", "direction": "output", "data_type": "BOOL", "connections": [], "disabled": False, "safety_relevant": False},
            ],
        }],
    }
    p = Project.deserialize(data)
    assert p.blocks[0].outputs[1].safety_relevant is True


# ---- fix/safety-block-semantics §1: Stuck Tolerance ------------------------

def test_quality_block_stuck_tolerance_zero_never_fires_on_realistic_noise():
    """§1 DOWÓD, reproduced as a test: a frozen sensor with last-bit noise
    (50.000/50.001 alternating) never trips Stuck at the pre-existing
    exact-equality default — this is the bug, and the backward-
    compatibility guarantee (default 0.0 behaves EXACTLY like before this
    property existed) in the same assertion."""
    from logic_studio.blocks.analog_processing import QualityBlock

    q = QualityBlock()
    q.properties["Stuck Scans"] = 3
    assert q.properties["Stuck Tolerance"] == 0.0  # default

    readings = [50.000, 50.001, 50.000, 50.001, 50.000, 50.001]
    for v in readings:
        q.inputs[0].value = v
        q.evaluate()
    assert q.outputs[3].value is False  # Stuck never fires

def test_quality_block_stuck_tolerance_above_zero_catches_realistic_noise():
    """Same frozen-sensor-with-noise series, but with a tolerance sized for
    real ADC noise -- Stuck MUST fire."""
    from logic_studio.blocks.analog_processing import QualityBlock

    q = QualityBlock()
    q.properties["Stuck Scans"] = 3
    q.properties["Stuck Tolerance"] = 0.01

    readings = [50.000, 50.001, 50.000, 50.001]
    for v in readings:
        q.inputs[0].value = v
        q.evaluate()
    assert q.outputs[3].value is True

def test_quality_block_stuck_tolerance_streak_resets_on_a_real_change():
    from logic_studio.blocks.analog_processing import QualityBlock

    q = QualityBlock()
    q.properties["Stuck Scans"] = 2
    q.properties["Stuck Tolerance"] = 0.01

    q.inputs[0].value = 50.000
    q.evaluate()  # baseline sample, nothing to compare yet
    q.inputs[0].value = 50.001
    q.evaluate()  # unchanged scan #1
    q.inputs[0].value = 50.000
    q.evaluate()  # unchanged scan #2
    assert q.outputs[3].value is True

    q.inputs[0].value = 52.0  # genuine change, well outside tolerance
    q.evaluate()
    assert q.outputs[3].value is False

    q.inputs[0].value = 52.001
    q.evaluate()
    assert q.outputs[3].value is False  # streak restarted, only 1 so far

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
