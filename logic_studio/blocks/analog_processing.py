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
    damaged, frozen or stale-but-plausible measurement."""

    def __init__(self, type_id="analog.quality", default_name="QUALITY", category="Elementy Analogowe", description="Signal Quality Supervision"):
        super().__init__(type_id, default_name, category, description)
        self.aliases = ["jakość sygnału", "nadzór pomiaru"]
        self.height = 100

        self.inputs.append(Pin("In", Pin.DIR_INPUT, Pin.TYPE_FLOAT))
        self.outputs.append(Pin("Good", Pin.DIR_OUTPUT, Pin.TYPE_BOOLEAN))
        self.outputs.append(Pin("Out Of Range", Pin.DIR_OUTPUT, Pin.TYPE_BOOLEAN))
        self.outputs.append(Pin("Rate Fault", Pin.DIR_OUTPUT, Pin.TYPE_BOOLEAN))
        self.outputs.append(Pin("Stuck", Pin.DIR_OUTPUT, Pin.TYPE_BOOLEAN))

        self.properties["Min"] = 0.0
        self.properties["Max"] = 100.0
        self.properties["Max Rate"] = 0.0    # max change per scan; 0 = check disabled
        self.properties["Stuck Scans"] = 0   # consecutive unchanged scans; 0 = check disabled

        self.is_stateful = True

        self._last_value = None
        # Count of consecutive scans where the value did NOT change relative
        # to the scan before it. Reaching "Stuck Scans" trips Stuck.
        self._unchanged_streak = 0

    def reset_runtime_state(self):
        self._last_value = None
        self._unchanged_streak = 0

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
            min_v = float(self.properties.get("Min", 0.0))
            max_v = float(self.properties.get("Max", 100.0))
            out_of_range = fval < min_v or fval > max_v

            max_rate = float(self.properties.get("Max Rate", 0.0))
            if max_rate > 0 and self._last_value is not None:
                rate_fault = abs(fval - self._last_value) > max_rate

            stuck_scans = int(self.properties.get("Stuck Scans", 0))
            if stuck_scans > 0:
                if self._last_value is not None and fval == self._last_value:
                    self._unchanged_streak += 1
                else:
                    self._unchanged_streak = 0
                stuck = self._unchanged_streak >= stuck_scans

            self._last_value = fval

        self.outputs[0].value = is_number and not out_of_range and not rate_fault and not stuck
        self.outputs[1].value = out_of_range
        self.outputs[2].value = rate_fault
        self.outputs[3].value = stuck
