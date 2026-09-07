import math

from logic_studio.blocks.base import BaseLogicBlock
from logic_studio.blocks.pin import Pin
from logic_studio.blocks.registry import BlockRegistry

class BaseAnalogBlock(BaseLogicBlock):
    def __init__(self, type_id, default_name, category, description):
        super().__init__(type_id, default_name, category, description)
        self.color = "#808000" # Olive
        self.width = 100

@BlockRegistry.register
class ScaleBlock(BaseAnalogBlock):
    def __init__(self, type_id="analog.scale", default_name="SCALE", category="Elementy Analogowe", description="Linear Scaling"):
        super().__init__(type_id, default_name, category, description)
        self.aliases = ["skalowanie", "przeliczenie"]
        self.height = 100

        self.inputs.append(Pin("In", Pin.DIR_INPUT, Pin.TYPE_FLOAT))
        self.outputs.append(Pin("Out", Pin.DIR_OUTPUT, Pin.TYPE_FLOAT))

        self.properties["In Min"] = 0.0
        self.properties["In Max"] = 100.0
        self.properties["Out Min"] = 0.0
        self.properties["Out Max"] = 100.0

    def evaluate(self, engine=None):
        in_val = self.inputs[0].value
        if in_val is not None:
            in_min = float(self.properties["In Min"])
            in_max = float(self.properties["In Max"])
            out_min = float(self.properties["Out Min"])
            out_max = float(self.properties["Out Max"])

            # Prevent divide by zero
            if in_max == in_min:
                self.outputs[0].value = out_min
                return

            norm = (float(in_val) - in_min) / (in_max - in_min)
            # clamp
            norm = max(0.0, min(1.0, norm))

            scaled = out_min + norm * (out_max - out_min)
            self.outputs[0].value = scaled

@BlockRegistry.register
class LimitBlock(BaseAnalogBlock):
    def __init__(self, type_id="analog.limit", default_name="LIMIT", category="Elementy Analogowe", description="Clamp Value"):
        super().__init__(type_id, default_name, category, description)
        self.height = 80
        self.inputs.append(Pin("In", Pin.DIR_INPUT, Pin.TYPE_FLOAT))
        self.outputs.append(Pin("Out", Pin.DIR_OUTPUT, Pin.TYPE_FLOAT))

        self.properties["Min"] = 0.0
        self.properties["Max"] = 100.0

    def evaluate(self, engine=None):
        val = self.inputs[0].value
        if val is not None:
            self.outputs[0].value = max(float(self.properties["Min"]),
                                        min(float(self.properties["Max"]), float(val)))

@BlockRegistry.register
class HysteresisBlock(BaseAnalogBlock):
    def __init__(self, type_id="analog.hysteresis", default_name="HYSTERESIS", category="Elementy Analogowe", description="Boolean Hysteresis"):
        super().__init__(type_id, default_name, category, description)
        self.height = 80

        self.inputs.append(Pin("In", Pin.DIR_INPUT, Pin.TYPE_FLOAT))
        self.outputs.append(Pin("Out", Pin.DIR_OUTPUT, Pin.TYPE_BOOLEAN))

        self.properties["High Threshold"] = 80.0
        self.properties["Low Threshold"] = 70.0

        self._last_state = False
        self.is_stateful = True

    def reset_runtime_state(self):
        self._last_state = False

    def evaluate(self, engine=None):
        val = self.inputs[0].value
        if val is not None:
            high = float(self.properties["High Threshold"])
            low = float(self.properties["Low Threshold"])

            if val >= high:
                self._last_state = True
            elif val <= low:
                self._last_state = False

            self.outputs[0].value = self._last_state

@BlockRegistry.register
class MovingAverageBlock(BaseAnalogBlock):
    def __init__(self, type_id="analog.mov_avg", default_name="MOVING AVG", category="Elementy Analogowe", description="Moving Average Filter"):
        super().__init__(type_id, default_name, category, description)
        self.height = 60
        self.inputs.append(Pin("In", Pin.DIR_INPUT, Pin.TYPE_FLOAT))
        self.outputs.append(Pin("Out", Pin.DIR_OUTPUT, Pin.TYPE_FLOAT))
        self.properties["Samples"] = 10
        self._buffer = []
        self.is_stateful = True

    def reset_runtime_state(self):
        self._buffer.clear()

    def evaluate(self, engine=None):
        val = self.inputs[0].value
        if val is not None:
            self._buffer.append(float(val))
            max_samples = int(self.properties["Samples"])

            if len(self._buffer) > max_samples:
                self._buffer.pop(0)

            if len(self._buffer) > 0:
                self.outputs[0].value = sum(self._buffer) / len(self._buffer)


@BlockRegistry.register
class DeadbandBlock(BaseAnalogBlock):
    """Report-by-exception filter: freezes Out at the last reported value
    until In moves far enough to matter, so noise on a slowly-drifting signal
    doesn't spam downstream logic/alarms/history with meaningless churn."""

    def __init__(self, type_id="analog.deadband", default_name="DEADBAND", category="Elementy Analogowe", description="Report-by-Exception Deadband"):
        super().__init__(type_id, default_name, category, description)
        self.aliases = ["strefa nieczułości", "martwa strefa"]
        self.height = 80

        self.inputs.append(Pin("In", Pin.DIR_INPUT, Pin.TYPE_FLOAT))
        self.outputs.append(Pin("Out", Pin.DIR_OUTPUT, Pin.TYPE_FLOAT))
        self.outputs.append(Pin("Changed", Pin.DIR_OUTPUT, Pin.TYPE_BOOLEAN))

        self.properties["Mode"] = "Bezwzględny"  # "Bezwzględny" | "Procentowy"
        self.properties["Deadband"] = 1.0
        self.properties["Range"] = 100.0  # reference span for "Procentowy" mode

        self._last_reported = None
        self.is_stateful = True

    def reset_runtime_state(self):
        self._last_reported = None

    def _threshold(self) -> float:
        if self.properties.get("Mode", "Bezwzględny") == "Procentowy":
            rng = float(self.properties.get("Range", 100.0))
            return abs(rng) * float(self.properties.get("Deadband", 1.0)) / 100.0
        return float(self.properties.get("Deadband", 1.0))

    def evaluate(self, engine=None):
        val = self.inputs[0].value
        if val is None:
            return
        val = float(val)

        if self._last_reported is None:
            # First scan after (re)start always passes the value through —
            # there is nothing yet to compare it against.
            self._last_reported = val
            self.outputs[0].value = val
            self.outputs[1].value = True
            return

        if abs(val - self._last_reported) >= self._threshold():
            self._last_reported = val
            self.outputs[0].value = val
            self.outputs[1].value = True
        else:
            self.outputs[0].value = self._last_reported
            self.outputs[1].value = False


@BlockRegistry.register
class QualityBlock(BaseAnalogBlock):
    """Supervises a raw analog reading for range, rate-of-change and
    stuck-signal faults so downstream safety logic never silently trusts a
    damaged, frozen or stale-but-plausible measurement.

    fix/safety-block-semantics §1: stuck-signal detection compares two
    consecutive readings for EXACT equality by default (Stuck Tolerance =
    0.0, preserved for backward compatibility) — a real measurement chain
    (ADC, cable, transmitter) essentially never produces bit-identical
    samples even from a genuinely frozen sensor, because there is always
    some least-significant-bit noise. For Stuck detection to mean anything
    on real hardware, Stuck Tolerance MUST be set above 0 — a starting
    point around 0,1% of the measurement's engineering range is
    reasonable (tight enough to still catch a truly frozen signal, loose
    enough that normal ADC noise doesn't defeat it every scan)."""

    PROPERTY_TOOLTIPS = {
        "Stuck Tolerance": (
            "Dla realnego sygnału z przetwornika ta wartość MUSI być większa "
            "od zera — szum ostatniego bitu przetwornika sprawia, że dwie "
            "kolejne próbki prawie nigdy nie są identyczne bit-w-bit. "
            "Punkt startowy: około 0,1% zakresu pomiarowego."
        ),
    }

    def __init__(self, type_id="analog.quality", default_name="QUALITY", category="Elementy Analogowe", description="Nadzór jakości sygnału analogowego: zakres, szybkość zmiany, zamrożenie. UWAGA: dla realnego przetwornika ustaw Stuck Tolerance > 0 (rząd wielkości: ok. 0,1% zakresu pomiarowego) — przy tolerancji 0.0 detekcja zamrożenia nie zadziała na sygnale z prawdziwego toru pomiarowego."):
        super().__init__(type_id, default_name, category, description)
        self.aliases = ["jakość sygnału", "nadzór pomiaru"]
        self.height = 100
        # fix/safety-block-semantics §7.4: the inherited 100px (BaseAnalog
        # Block) truncated "Out Of Range"/"Rate Fault" to "Out Of…"/
        # "Rate F…" — PortItem.paint() reserves PIN_LABEL_SIDE_FRACTION
        # (45%) of the block's OWN width for each pin's label, and "Out Of
        # Range" alone measures ~132px at FONT_SIZE_PIN_LABEL, needing
        # >=~293px of block width (132 / 0.45) to render unclipped;
        # "Out Of…" gave no hint whether it meant range or something else.
        # This can't be computed from font metrics here (logic_studio.blocks
        # is deliberately Qt-free — see ui/canvas/block_item.py for where
        # that measurement DOES happen, for IO-shaped blocks) — a fixed,
        # comfortably-rounded width instead, wide enough with margin.
        self.width = 300

        self.inputs.append(Pin("In", Pin.DIR_INPUT, Pin.TYPE_FLOAT))
        self.outputs.append(Pin("Good", Pin.DIR_OUTPUT, Pin.TYPE_BOOLEAN))
        self.outputs.append(Pin("Out Of Range", Pin.DIR_OUTPUT, Pin.TYPE_BOOLEAN))
        self.outputs.append(Pin("Rate Fault", Pin.DIR_OUTPUT, Pin.TYPE_BOOLEAN))
        self.outputs.append(Pin("Stuck", Pin.DIR_OUTPUT, Pin.TYPE_BOOLEAN))
        # fix/safety-block-semantics §6.1: this is the entire reason the
        # block exists — logic downstream needs to see whether the
        # measurement it's built on can be trusted. See
        # resync_derived_pin_metadata() below for why __init__ alone isn't
        # enough for an EXISTING project's block.
        self.outputs[0].safety_relevant = True

        self.properties["Min"] = 0.0
        self.properties["Max"] = 100.0
        # §4.1: "Z punktu analogowego" resolves Min/Max from the analog
        # point of the input.ai block feeding In (Compiler.compile(), like
        # AnalogInputBlock's own range already does) instead of trusting
        # this block's OWN, independently-editable Min/Max — a schematic
        # wiring AI(-40..150) into QUALITY(Min=0, Max=100) previously ran
        # two silently-disagreeing range checks with nothing flagging it.
        # "Własny" is the pre-existing behavior (this block's own Min/Max)
        # — the default for blocks loaded from a project that predates
        # this property (core/project.py's _migrate_v9_to_v10), since only
        # a NEWLY PLACED block is guaranteed to have its In pin wired up
        # (or not yet at all) in a way Range Source can safely assume.
        self.properties["Range Source"] = "Z punktu analogowego"
        # §2.1: physical units PER SECOND, not per scan — see the class
        # docstring/migration note (core/project.py's _migrate_v8_to_v9)
        # for why "per scan" silently changed meaning with cycle_time_ms.
        self.properties["Max Rate (/s)"] = 0.0    # 0 = check disabled
        self.properties["Stuck Scans"] = 0   # consecutive unchanged scans; 0 = check disabled
        # §1.1: 0.0 = bit-exact equality, i.e. IDENTICAL to this block's
        # behavior before this property existed — see the class docstring
        # for why this is unsafe on a real measurement chain.
        self.properties["Stuck Tolerance"] = 0.0

        self.is_stateful = True

        self._last_value = None
        # §2.2: engine time (ms) at the last VALID measurement — paired
        # with _last_value, both reset together (§3) so a rate/stuck check
        # never compares across a bad-quality gap.
        self._last_measurement_time_ms = None
        # Count of consecutive scans where the value did NOT change relative
        # to the scan before it. Reaching "Stuck Scans" trips Stuck.
        self._unchanged_streak = 0
        # §4.2: [min, max] resolved by the Compiler when Range Source ==
        # "Z punktu analogowego" — mirrors AnalogInputBlock._range_min/max
        # (analog_io.py) exactly, including WHY: the runtime engine is
        # deliberately decoupled from the UI Project, so this can't be
        # looked up live at evaluate() time.
        self._range_min = None
        self._range_max = None

    def reset_runtime_state(self):
        self._last_value = None
        self._last_measurement_time_ms = None
        self._unchanged_streak = 0

    def resync_derived_pin_metadata(self):
        """§6.1: Good's safety_relevant is a fact about this block TYPE,
        not user/file data — every project saved before §6 has "false"
        stored for it (nothing ever set it before now), which
        Pin.restore_fields() would otherwise restore right on top of
        __init__'s fresh True, silently hiding the new unused-output
        warning (§6.2) on every EXISTING project's quality blocks."""
        self.outputs[0].safety_relevant = True

    def set_range(self, range_min, range_max):
        """§4.2: called by the Compiler at compile time, exactly like
        AnalogInputBlock.set_range() — only meaningful while Range Source
        == "Z punktu analogowego" (see _effective_range())."""
        self._range_min = range_min
        self._range_max = range_max

    def _effective_range(self):
        """§4.3: the [min, max] this block's own Out Of Range check
        actually uses — the compiler-resolved analog-point range when
        Range Source == "Z punktu analogowego" AND the Compiler actually
        resolved one (Validator's own check, §4.2, guarantees this for
        anything that reaches evaluate() — but a block never run through
        Compiler.compile() at all, e.g. a bare unit test, falls back to
        its own Min/Max rather than silently using None/None)."""
        if self.properties.get("Range Source", "Własny") == "Z punktu analogowego" and self._range_min is not None and self._range_max is not None:
            return self._range_min, self._range_max
        return float(self.properties.get("Min", 0.0)), float(self.properties.get("Max", 100.0))

    def _get_time_ms(self, engine):
        """§2.3: mirrors blocks/timers.py's TimerBase._get_time() exactly —
        a rate-of-change check silently degrading to "per scan" because no
        TimeProvider was wired up would reintroduce the exact bug §2 fixes,
        just less visibly. Loud failure instead."""
        if engine and hasattr(engine, 'time') and engine.time:
            return engine.time.current_time_ms()
        raise RuntimeError("TimeProvider missing. ExecutionEngine must inject deterministic time.")

    def evaluate(self, engine=None):
        val = self.inputs[0].value

        is_number = False
        fval = None
        if val is not None:
            try:
                fval = float(val)
                is_number = not (math.isnan(fval) or math.isinf(fval))
            except (TypeError, ValueError):
                is_number = False

        out_of_range = False
        rate_fault = False
        stuck = False

        if is_number:
            min_v, max_v = self._effective_range()
            out_of_range = fval < min_v or fval > max_v

            max_rate = float(self.properties.get("Max Rate (/s)", 0.0))
            if max_rate > 0:
                # §2.3: only require a TimeProvider when this check is
                # actually enabled — a block with Max Rate (/s)=0 (the
                # default) must keep working with engine=None, exactly as
                # every existing evaluate()-with-no-engine test expects.
                now_ms = self._get_time_ms(engine)
                if self._last_value is not None and self._last_measurement_time_ms is not None:
                    dt_ms = now_ms - self._last_measurement_time_ms
                    if dt_ms > 0:  # §2.2: guard divide-by-zero; skip this scan's check
                        rate = abs(fval - self._last_value) / (dt_ms / 1000.0)
                        rate_fault = rate > max_rate
                self._last_measurement_time_ms = now_ms

            stuck_scans = int(self.properties.get("Stuck Scans", 0))
            if stuck_scans > 0:
                # §1.2: within `tolerance` counts as "unchanged" — at the
                # default 0.0 this is exact equality, identical to this
                # block's behavior before Stuck Tolerance existed.
                tolerance = float(self.properties.get("Stuck Tolerance", 0.0))
                if self._last_value is not None and abs(fval - self._last_value) <= tolerance:
                    self._unchanged_streak += 1
                else:
                    self._unchanged_streak = 0
                stuck = self._unchanged_streak >= stuck_scans

            self._last_value = fval
        else:
            # §3.1: a bad/missing measurement invalidates any history — a
            # signal that vanished for 200 scans and came back must not be
            # compared (rate or stuck) against whatever was seen BEFORE the
            # gap. Every check starts fresh, exactly like after a restart.
            self._last_value = None
            self._last_measurement_time_ms = None
            self._unchanged_streak = 0

        self.outputs[0].value = is_number and not out_of_range and not rate_fault and not stuck
        self.outputs[1].value = out_of_range
        self.outputs[2].value = rate_fault
        self.outputs[3].value = stuck
