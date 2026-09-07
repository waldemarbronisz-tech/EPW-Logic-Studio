"""fix/safety-block-semantics §10: the missing test category this whole
branch's findings exposed. The other 829 (now 1300+) tests in this suite
check block logic against clean, synthetic values set directly on a pin
— every finding in sections 1-3 and 9 passed all of them. These tests
drive the SAME blocks with data shaped like a real measurement chain
instead: last-bit noise, drift, dropouts, oscillation around a
threshold, and scan-by-scan simulated time rather than one large
advance() jump — much closer to what actually crosses the wire from an
ADC/transmitter/HMI than a test fixture ever bothers to be.
"""
import math

import pytest

from logic_studio.blocks import register_builtin_blocks
from logic_studio.blocks.registry import BlockRegistry
from logic_studio.core.project import Project
from logic_studio.compiler.core import Compiler
from logic_studio.engine.execution import ExecutionEngine
from logic_studio.engine.io_provider import SimulationIOProvider
from logic_studio.engine.time_provider import SimulationTimeProvider

register_builtin_blocks()


def _adc_noise(sample_index: int, amplitude: float = 0.001) -> float:
    """A small, deterministic, non-repeating-looking jitter -- stands in
    for real ADC least-significant-bit noise without pulling in a random
    module and losing test reproducibility. Never exactly 0 for two
    consecutive samples, which is the entire point (see §1's DOWÓD)."""
    return amplitude * math.sin(sample_index * 2.617993877991494)  # ~150 degrees/sample


# ---- §10.1: frozen sensor with realistic last-bit noise -------------------

def test_frozen_sensor_with_realistic_noise_needs_tolerance_to_detect():
    from logic_studio.blocks.analog_processing import QualityBlock

    base = 50.0
    q_no_tolerance = QualityBlock()
    q_no_tolerance.properties["Stuck Scans"] = 10
    q_with_tolerance = QualityBlock()
    q_with_tolerance.properties["Stuck Scans"] = 10
    q_with_tolerance.properties["Stuck Tolerance"] = 0.01  # sized for this noise amplitude

    for i in range(30):
        reading = base + _adc_noise(i)
        q_no_tolerance.inputs[0].value = reading
        q_no_tolerance.evaluate()
        q_with_tolerance.inputs[0].value = reading
        q_with_tolerance.evaluate()

    assert q_no_tolerance.outputs[3].value is False   # never detects the freeze
    assert q_with_tolerance.outputs[3].value is True  # correctly does


# ---- §10.2: same Max Rate (/s), two cycle_time_ms, through the real pipeline

def _step_n_scans(engine: ExecutionEngine, io: SimulationIOProvider, address: str, values, dt_ms: int):
    """Feeds `values` one per scan, advancing the SimulationTimeProvider by
    `dt_ms` before each scan -- the actual per-scan cadence a real
    ExecutionEngine runs at, not one large time jump."""
    for v in values:
        io.set_analog_input(address, v)
        engine.time.advance(dt_ms)
        engine.step()


def test_max_rate_per_second_is_independent_of_cycle_time_end_to_end():
    """§2's own reproduction, through Compiler/ExecutionEngine this time
    (cycle_time_ms actually comes from project.settings, and the engine
    is stepped scan-by-scan at that real cadence) rather than calling
    QualityBlock.evaluate() directly."""
    from logic_studio.blocks.analog_io import AnalogInputBlock
    from logic_studio.blocks.analog_processing import QualityBlock

    results = {}
    for cycle_time_ms in (100, 50):
        project = Project()
        project.settings["cycle_time_ms"] = cycle_time_ms
        project.settings["analog_points"] = [
            {"address": "AI.LEVEL", "name": "Level", "unit": "m", "min": 0.0, "max": 100.0, "direction": "input"},
        ]
        ai = AnalogInputBlock()
        ai.properties["Address"] = "AI.LEVEL"
        q = QualityBlock()
        q.properties["Range Source"] = "Własny"
        q.properties["Min"] = 0.0
        q.properties["Max"] = 100.0
        q.properties["Max Rate (/s)"] = 50.0  # 50 units/s limit
        ai.outputs[0].connect(q.inputs[0])
        project.add_block(ai)
        project.add_block(q)

        compiler = Compiler(project)
        res = compiler.compile()
        assert res is not None, f"Compile failed: {compiler.errors}"

        io = SimulationIOProvider()
        time_provider = SimulationTimeProvider()
        engine = ExecutionEngine(res["program"], io, time_provider)
        engine.start()

        io.set_analog_input("AI.LEVEL", 10.0)
        engine.step()  # baseline sample
        # A realistic slow ramp: +4 units EVERY SCAN, regardless of dt --
        # the physical rate this represents depends entirely on how much
        # wall-clock time each scan actually spans.
        _step_n_scans(engine, io, "AI.LEVEL", [14.0, 18.0, 22.0], cycle_time_ms)

        q_block = next(b for b in engine.program.blocks if b.type_id == "analog.quality")
        results[cycle_time_ms] = q_block.outputs[2].value  # Rate Fault

    # 4 units/scan at 100ms/scan == 40 units/s -- under the 50/s limit.
    assert results[100] is False
    # The SAME 4 units/scan at 50ms/scan == 80 units/s -- over the limit.
    assert results[50] is True


# ---- §10.3: signal dropout and return, through the real IOProvider --------

def test_signal_dropout_and_return_end_to_end():
    """Drives QualityBlock's own In pin directly (unconnected -- nothing
    in the compiled graph overwrites it between steps) rather than
    through an upstream input.ai: AI's OWN fail-safe hold-last-good means
    a dropout NEVER actually reaches a downstream Quality block as a raw
    None in the first place (§5's own behavior) -- the interesting,
    genuinely realistic case for §3 specifically is a source that CAN
    report a missing/bad reading as None (a comms-aware IOProvider, a
    virtual signal, a bare Quality block reading something upstream of
    an AI's own holdover), which this reproduces end-to-end through
    Compiler/ExecutionEngine rather than a bare evaluate() call."""
    from logic_studio.blocks.analog_processing import QualityBlock

    project = Project()
    q = QualityBlock()
    q.properties["Range Source"] = "Własny"
    q.properties["Min"] = 0.0
    q.properties["Max"] = 100.0
    q.properties["Max Rate (/s)"] = 5.0
    q.properties["Stuck Scans"] = 3
    project.add_block(q)

    compiler = Compiler(project)
    res = compiler.compile()
    assert res is not None
    io = SimulationIOProvider()
    engine = ExecutionEngine(res["program"], io, SimulationTimeProvider())
    engine.start()
    q_block = next(b for b in engine.program.blocks if b.type_id == "analog.quality")

    q_block.inputs[0].value = 20.0
    engine.step()

    # A comms fault: the reading goes missing for 200 scans (a realistic
    # dropout duration, not just one missed scan).
    for _ in range(200):
        q_block.inputs[0].value = None
        engine.time.advance(100)
        engine.step()

    # Comes back far from the pre-dropout value.
    q_block.inputs[0].value = 90.0
    engine.time.advance(100)
    engine.step()

    assert q_block.outputs[2].value is False  # Rate Fault must not fire
    assert q_block.outputs[3].value is False  # Stuck must not fire

def test_ai_holdover_means_a_downstream_quality_never_sees_the_raw_dropout():
    """The AI-in-front case, made explicit rather than silently assumed:
    AI's fail-safe holdover (§5) means the LONG-HELD value looks, to
    everything downstream, like a perfectly ordinary steady reading --
    Quality only ever finds out about the eventual real jump once the
    signal actually returns, and correctly treats THAT as the anomaly."""
    from logic_studio.blocks.analog_io import AnalogInputBlock
    from logic_studio.blocks.analog_processing import QualityBlock

    project = Project()
    project.settings["analog_points"] = [
        {"address": "AI.LEVEL", "name": "Level", "unit": "m", "min": 0.0, "max": 100.0, "direction": "input"},
    ]
    ai = AnalogInputBlock()
    ai.properties["Address"] = "AI.LEVEL"
    q = QualityBlock()
    q.properties["Range Source"] = "Własny"
    q.properties["Min"] = 0.0
    q.properties["Max"] = 100.0
    q.properties["Max Rate (/s)"] = 5.0
    ai.outputs[0].connect(q.inputs[0])
    project.add_block(ai)
    project.add_block(q)

    compiler = Compiler(project)
    res = compiler.compile()
    assert res is not None
    io = SimulationIOProvider()
    engine = ExecutionEngine(res["program"], io, SimulationTimeProvider())
    engine.start()

    io.set_analog_input("AI.LEVEL", 20.0)
    engine.step()
    for _ in range(200):
        io.set_analog_input("AI.LEVEL", None)
        engine.time.advance(100)
        engine.step()

    ai_block = next(b for b in engine.program.blocks if b.type_id == "input.ai")
    q_block = next(b for b in engine.program.blocks if b.type_id == "analog.quality")
    assert ai_block.outputs[0].value == 20.0  # still holding -- looks like a normal reading
    assert q_block.outputs[2].value is False  # nothing anomalous from Quality's point of view yet

    io.set_analog_input("AI.LEVEL", 90.0)  # the real, large jump
    engine.time.advance(100)
    engine.step()
    assert q_block.outputs[2].value is True  # correctly flagged once it actually arrives


# ---- §10.4: slow drift through DEADBAND ------------------------------------

def test_deadband_change_count_matches_expected_for_a_slow_drift():
    from logic_studio.blocks.analog_processing import DeadbandBlock

    d = DeadbandBlock()
    d.properties["Deadband"] = 1.0  # absolute

    drift_per_scan = 0.05  # a slow, realistic temperature drift
    value = 20.0
    changed_count = 0
    for i in range(1000):
        value += drift_per_scan
        d.inputs[0].value = value
        d.evaluate()
        if d.outputs[1].value:
            changed_count += 1

    total_drift = drift_per_scan * 1000
    expected = total_drift / d.properties["Deadband"]
    # First scan always reports (§ existing DeadbandBlock behavior) plus
    # roughly one report per threshold crossing -- allow +/-2 for the
    # boundary/rounding scans, tight enough to catch a broken threshold.
    assert abs(changed_count - expected) <= 2, f"expected ~{expected}, got {changed_count}"

def test_deadband_pure_noise_with_no_drift_barely_reports():
    """The companion case: noise alone (no real trend) around a threshold
    comfortably larger than the noise amplitude must report only once
    (the mandatory first scan) -- report-by-exception doing its job."""
    from logic_studio.blocks.analog_processing import DeadbandBlock

    d = DeadbandBlock()
    d.properties["Deadband"] = 1.0
    changed_count = 0
    for i in range(200):
        d.inputs[0].value = 50.0 + _adc_noise(i, amplitude=0.05)
        d.evaluate()
        if d.outputs[1].value:
            changed_count += 1
    assert changed_count == 1  # only the mandatory first scan


# ---- §10.5: signal oscillating at a hysteresis comparator's threshold -----

def test_comparator_hysteresis_settles_with_at_most_one_switch_in_100_scans():
    from logic_studio.blocks.comparators import GreaterBlock

    g = GreaterBlock()
    g.properties["Hysteresis"] = 1.0  # +/-1.0 Schmitt-trigger band around the threshold

    switches = 0
    last_out = None
    for i in range(100):
        # Oscillates tightly around the threshold (0.0 here -- In2 stays
        # at 0), well within the hysteresis band, with realistic noise.
        g.inputs[0].value = _adc_noise(i, amplitude=0.3)
        g.inputs[1].value = 0.0
        g.evaluate()
        out = g.outputs[0].value
        if last_out is not None and out != last_out:
            switches += 1
        last_out = out

    assert switches <= 1


# ---- §10.6: AI range checks across the 10% margin --------------------------

@pytest.mark.parametrize("value,expect_good", [
    (-60.0, False),  # under range, beyond the 10% margin
    (200.0, False),  # over range, beyond the 10% margin
    (-45.0, True),   # under the nominal range but within the 10% margin
    (160.0, True),   # over the nominal range but within the 10% margin
    (75.0, True),    # comfortably inside
])
def test_ai_range_margin_matrix(value, expect_good):
    """input.ai's -40..150 range, 10% margin == 19 either side (AUDIT_
    REPORT.md's own quality-check contract) -- every boundary case in one
    parametrized sweep instead of one-off assertions."""
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
    ai.set_range(-40.0, 150.0)
    engine = FakeEngine(FakeIO(value))
    ai.evaluate(engine)
    assert ai.outputs[1].value is expect_good, f"value={value}"


# ---- §10.7: AI Max Hold, stepped scan-by-scan like a real PLC -------------

def test_ai_max_hold_expires_after_5_seconds_of_simulated_scan_time():
    from logic_studio.blocks.analog_io import AnalogInputBlock

    project = Project()
    project.settings["analog_points"] = [
        {"address": "AI.LEVEL", "name": "Level", "unit": "m", "min": 0.0, "max": 100.0, "direction": "input"},
    ]
    ai = AnalogInputBlock()
    ai.properties["Address"] = "AI.LEVEL"
    ai.properties["Max Hold (ms)"] = 5000
    project.add_block(ai)

    compiler = Compiler(project)
    res = compiler.compile()
    assert res is not None
    io = SimulationIOProvider()
    engine = ExecutionEngine(res["program"], io, SimulationTimeProvider())
    engine.start()

    io.set_analog_input("AI.LEVEL", 42.0)
    engine.step()
    ai_block = next(b for b in engine.program.blocks if b.type_id == "input.ai")
    assert ai_block.outputs[2].value is False  # Hold Expired

    # A realistic 100ms scan cadence, 49 scans == 4900ms -- not yet expired.
    io.set_analog_input("AI.LEVEL", None)
    for _ in range(49):
        engine.time.advance(100)
        engine.step()
    assert ai_block.outputs[2].value is False
    assert ai_block.outputs[0].value == 42.0  # still holding

    # One more scan crosses 5000ms.
    engine.time.advance(100)
    engine.step()
    assert ai_block.outputs[2].value is True
    assert ai_block.outputs[1].value is False  # Quality
