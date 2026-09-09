import math

from logic_studio.blocks.base import BaseLogicBlock
from logic_studio.blocks.pin import Pin
from logic_studio.blocks.registry import BlockRegistry


@BlockRegistry.register
class AnalogInputBlock(BaseLogicBlock):
    """Analog counterpart of DigitalInputBlock. Unlike DI, its Address is not
    one of a fixed set of physical channels — it names an entry in the
    project's dynamic analog_points list (see core/device_model.py and
    AUDIT_REPORT.md §1/§2)."""

    PIN_DESCRIPTIONS = {
        "Value": "Ostatnia zaufana wartość pomiarowa — trzymana z poprzedniego dobrego odczytu, gdy Quality jest fałszywe.",
        "Quality": "Prawda, gdy ostatni odczyt jest wiarygodny (w zakresie, nie NaN/Inf). Istotne dla bezpieczeństwa.",
        "Hold Expired": "Prawda, gdy Value jest trzymane dłużej niż pozwala Max Hold (ms). Istotne dla bezpieczeństwa.",
    }
    PROPERTY_DESCRIPTIONS = {
        "Address": "Identyfikator punktu analogowego zdefiniowanego w ustawieniach projektu (Analog Points).",
        "Max Hold (ms)": "Ile czasu Value może trzymać ostatnią dobrą wartość przy złej jakości odczytu, zanim Hold Expired się uaktywni. 0 = bez limitu.",
        "Hold Timeout Value": "Co Value pokazuje po przekroczeniu Max Hold (ms): \"Zero\", \"Ostatnia dobra\" wartość, albo \"Dolna granica zakresu\".",
    }
    PROPERTY_UNITS = {"Max Hold (ms)": "ms"}

    def __init__(self, type_id="input.ai", default_name="AI", category="Wejścia / Wyjścia", description="Wejście analogowe — odczyt punktu pomiarowego z kontrolą jakości sygnału."):
        super().__init__(type_id, default_name, category, description)
        self.color = "#CC8400"  # Amber — visually distinct from DI/VI green
        self.width = 100
        self.height = 60
        self.properties["Address"] = ""
        self.is_source = True

        self.outputs = [
            Pin("Value", Pin.DIR_OUTPUT, Pin.TYPE_FLOAT),
            Pin("Quality", Pin.DIR_OUTPUT, Pin.TYPE_BOOLEAN),
            # fix/safety-block-semantics §5.4: True once a good reading has
            # been missing longer than "Max Hold (ms)" — a plain BOOL,
            # separate from Quality, so logic can react specifically to
            # "held past its limit" rather than every momentary bad scan.
            Pin("Hold Expired", Pin.DIR_OUTPUT, Pin.TYPE_BOOLEAN),
        ]
        # A stale/bad reading masquerading as good data is exactly the kind
        # of failure a safety interlock needs to see — mark it accordingly.
        self.outputs[1].safety_relevant = True
        self.outputs[2].safety_relevant = True

        # Last value judged trustworthy — held across bad-quality scans
        # (fail-safe: downstream logic runs on stale-but-good data, never on
        # garbage). Range bounds are resolved once at compile time from the
        # project's analog point definition (see Compiler.compile()) rather
        # than looked up live, since the runtime engine is deliberately
        # decoupled from the UI Project.
        self._last_good = None
        self._range_min = None
        self._range_max = None

        # fix/safety-block-semantics §5: holding the last good value FOREVER
        # while quality stays bad is a correct fail-safe decision on its
        # own, but with no time limit it lets logic downstream keep running
        # on a measurement that could be hours or days stale, as long as
        # nothing happens to be watching Quality. "Max Hold (ms)" bounds
        # that — 0 (default) means unlimited, IDENTICAL to this block's
        # behavior before this property existed.
        self.properties["Max Hold (ms)"] = 0
        # §5.2: what Value becomes once the hold limit is exceeded. Quality
        # stays False regardless of this choice — this property only picks
        # a defined fallback NUMBER for the (likely already actively
        # unsafe) case where downstream logic isn't wired to Quality at all.
        self.properties["Hold Timeout Value"] = "Zero"  # "Zero" | "Ostatnia dobra" | "Dolna granica zakresu"

        # Engine time (ms) at the last GOOD reading — only tracked while
        # Max Hold (ms) > 0 (see evaluate()), same "don't require a
        # TimeProvider for a disabled check" reasoning as QualityBlock's
        # Max Rate (/s) (analog_processing.py).
        self._last_good_time_ms = None

    def set_range(self, range_min, range_max):
        """Called by the Compiler at compile time with this block's analog
        point [min, max], used for the out-of-range quality check below."""
        self._range_min = range_min
        self._range_max = range_max

    def reset_runtime_state(self):
        self._last_good = None
        self._last_good_time_ms = None
        self.outputs[0].value = 0.0
        self.outputs[1].value = False
        self.outputs[2].value = False

    def resync_derived_pin_metadata(self):
        """fix/safety-block-semantics §6.1: Quality/Hold Expired's
        safety_relevant is a fact about this block TYPE, never user/file
        data — reasserted here in case an old/hand-edited file's saved
        value ever disagreed (Pin.restore_fields() would otherwise trust
        it). Hold Expired itself needs no such defense in practice (a file
        old enough to lack that pin entirely never gets this far — see
        core/project.py's Project.deserialize() pin-restore loop), but
        this stays cheap, explicit insurance rather than an assumption."""
        self.outputs[1].safety_relevant = True
        self.outputs[2].safety_relevant = True

    def _is_good(self, raw) -> bool:
        if raw is None:
            return False
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return False
        if math.isnan(value) or math.isinf(value):
            return False

        if self._range_min is not None and self._range_max is not None:
            span = self._range_max - self._range_min
            margin = abs(span) * 0.1
            if value < self._range_min - margin or value > self._range_max + margin:
                return False

        return True

    def _get_time_ms(self, engine):
        """§5.5: mirrors analog_processing.py's QualityBlock._get_time_ms()
        / blocks/timers.py's TimerBase._get_time() — silently degrading to
        "hold forever" for lack of a TimeProvider would reintroduce the
        exact risk Max Hold exists to bound, just invisibly."""
        if engine and hasattr(engine, 'time') and engine.time:
            return engine.time.current_time_ms()
        raise RuntimeError("TimeProvider missing. ExecutionEngine must inject deterministic time.")

    def evaluate(self, engine=None):
        addr = self.properties.get("Address", "")
        raw = None
        if engine and hasattr(engine, 'io') and engine.io is not None:
            raw = engine.io.read_analog_input(addr)

        quality = self._is_good(raw)
        max_hold_ms = int(self.properties.get("Max Hold (ms)", 0) or 0)
        now_ms = self._get_time_ms(engine) if max_hold_ms > 0 else None

        if quality:
            self._last_good = float(raw)
            if max_hold_ms > 0:
                self._last_good_time_ms = now_ms

        # §5.3: expired only once Max Hold (ms) is actually exceeded, not
        # merely "quality is bad right now" — a single missed scan is
        # exactly what holding the last good value is FOR.
        hold_expired = (
            max_hold_ms > 0
            and self._last_good_time_ms is not None
            and (now_ms - self._last_good_time_ms) >= max_hold_ms
        )

        if hold_expired:
            timeout_mode = self.properties.get("Hold Timeout Value", "Zero")
            if timeout_mode == "Ostatnia dobra":
                value = self._last_good if self._last_good is not None else 0.0
            elif timeout_mode == "Dolna granica zakresu":
                value = self._range_min if self._range_min is not None else 0.0
            else:  # "Zero"
                value = 0.0
        else:
            value = self._last_good if self._last_good is not None else 0.0

        self.outputs[0].value = value
        self.outputs[1].value = quality
        self.outputs[2].value = hold_expired
        self.simulation_state["sim_value"] = value
        self.simulation_state["quality"] = quality


@BlockRegistry.register
class AnalogOutputBlock(BaseLogicBlock):
    """Analog counterpart of DigitalOutputBlock. Writes are buffered on the
    engine (queue_analog_output) and flushed atomically at end-of-scan, same
    as digital outputs — see engine/execution.py."""

    PIN_DESCRIPTIONS = {"Value": "Wartość zapisywana na fizyczne/wirtualne wyjście analogowe."}
    PROPERTY_DESCRIPTIONS = {
        "Address": "Identyfikator punktu analogowego zdefiniowanego w ustawieniach projektu (Analog Points).",
    }

    def __init__(self, type_id="output.ao", default_name="AO", category="Wejścia / Wyjścia", description="Wyjście analogowe."):
        super().__init__(type_id, default_name, category, description)
        self.color = "#4682B4"  # Steel blue — visually distinct from DO/VO red
        self.width = 100
        self.height = 60
        self.properties["Address"] = ""

        self.inputs = [Pin("Value", Pin.DIR_INPUT, Pin.TYPE_FLOAT)]

    def evaluate(self, engine=None):
        v = self.inputs[0].value
        val = float(v) if v is not None else 0.0

        if engine and hasattr(engine, 'queue_analog_output'):
            addr = self.properties.get("Address", "")
            engine.queue_analog_output(addr, val)

        self.simulation_state["sim_value"] = val
