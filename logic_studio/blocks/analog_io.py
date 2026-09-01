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

    def __init__(self, type_id="input.ai", default_name="AI", category="Wejścia / Wyjścia", description="Analog Input"):
        super().__init__(type_id, default_name, category, description)
        self.color = "#006400"  # Same family as DI, distinguishable on canvas
        self.width = 100
        self.height = 60
        self.properties["Address"] = ""
        self.is_source = True

        self.outputs = [
            Pin("Value", Pin.DIR_OUTPUT, Pin.TYPE_FLOAT),
            Pin("Quality", Pin.DIR_OUTPUT, Pin.TYPE_BOOLEAN),
        ]

        # Last value judged trustworthy — held across bad-quality scans
        # (fail-safe: downstream logic runs on stale-but-good data, never on
        # garbage). Range bounds are resolved once at compile time from the
        # project's analog point definition (see Compiler.compile()) rather
        # than looked up live, since the runtime engine is deliberately
        # decoupled from the UI Project.
        self._last_good = None
        self._range_min = None
        self._range_max = None

    def set_range(self, range_min, range_max):
        """Called by the Compiler at compile time with this block's analog
        point [min, max], used for the out-of-range quality check below."""
        self._range_min = range_min
        self._range_max = range_max

    def reset_runtime_state(self):
        self._last_good = None
        self.outputs[0].value = 0.0
        self.outputs[1].value = False

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

    def evaluate(self, engine=None):
        addr = self.properties.get("Address", "")
        raw = None
        if engine and hasattr(engine, 'io') and engine.io is not None:
            raw = engine.io.read_analog_input(addr)

        quality = self._is_good(raw)
        if quality:
            self._last_good = float(raw)

        self.outputs[0].value = self._last_good if self._last_good is not None else 0.0
        self.outputs[1].value = quality
        self.simulation_state["sim_value"] = self.outputs[0].value
        self.simulation_state["quality"] = quality


@BlockRegistry.register
class AnalogOutputBlock(BaseLogicBlock):
    """Analog counterpart of DigitalOutputBlock. Writes are buffered on the
    engine (queue_analog_output) and flushed atomically at end-of-scan, same
    as digital outputs — see engine/execution.py."""

    def __init__(self, type_id="output.ao", default_name="AO", category="Wejścia / Wyjścia", description="Analog Output"):
        super().__init__(type_id, default_name, category, description)
        self.color = "#8B0000"
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
