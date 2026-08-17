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
        self.height = 100

        self.inputs.append(Pin("In", Pin.DIR_INPUT, Pin.TYPE_FLOAT))
        self.outputs.append(Pin("Out", Pin.DIR_OUTPUT, Pin.TYPE_FLOAT))

        self.properties["In Min"] = 0.0
        self.properties["In Max"] = 100.0
        self.properties["Out Min"] = 0.0
        self.properties["Out Max"] = 100.0

    def evaluate(self):
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

    def evaluate(self):
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

    def evaluate(self):
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

    def evaluate(self):
        val = self.inputs[0].value
        if val is not None:
            self._buffer.append(float(val))
            max_samples = int(self.properties["Samples"])

            if len(self._buffer) > max_samples:
                self._buffer.pop(0)

            if len(self._buffer) > 0:
                self.outputs[0].value = sum(self._buffer) / len(self._buffer)
