from logic_studio.blocks.base import BaseLogicBlock
from logic_studio.blocks.pin import Pin
from logic_studio.blocks.registry import BlockRegistry

class AnalogBase(BaseLogicBlock):
    def __init__(self, type_id, default_name, category, description):
        super().__init__(type_id, default_name, category, description)
        self.color = "#FF8C00" # DarkOrange
        self.width = 100
        self.height = 80

@BlockRegistry.register
class ScaleBlock(AnalogBase):
    def __init__(self, type_id="analog.scale", default_name="SCALE", category="Analog Processing", description="Linear Scaling"):
        super().__init__(type_id, default_name, category, description)
        self.inputs = [Pin("In", Pin.DIR_INPUT, Pin.TYPE_FLOAT)]
        self.outputs = [Pin("Out", Pin.DIR_OUTPUT, Pin.TYPE_FLOAT)]

        self.properties.update({
            "In Min": 0.0,
            "In Max": 100.0,
            "Out Min": 0.0,
            "Out Max": 10.0
        })

    def evaluate(self):
        val = float(self.inputs[0].value) if self.inputs[0].value is not None else 0.0

        in_min = float(self.properties.get("In Min", 0.0))
        in_max = float(self.properties.get("In Max", 100.0))
        out_min = float(self.properties.get("Out Min", 0.0))
        out_max = float(self.properties.get("Out Max", 10.0))

        if in_max == in_min:
            self.outputs[0].value = out_min
        else:
            scaled = (val - in_min) / (in_max - in_min) * (out_max - out_min) + out_min
            self.outputs[0].value = scaled

@BlockRegistry.register
class LimitBlock(AnalogBase):
    def __init__(self, type_id="analog.limit", default_name="LIMIT", category="Analog Processing", description="Clamp Value"):
        super().__init__(type_id, default_name, category, description)
        self.inputs = [Pin("In", Pin.DIR_INPUT, Pin.TYPE_FLOAT)]
        self.outputs = [Pin("Out", Pin.DIR_OUTPUT, Pin.TYPE_FLOAT)]
        self.properties.update({"Min": 0.0, "Max": 100.0})

    def evaluate(self):
        val = float(self.inputs[0].value) if self.inputs[0].value is not None else 0.0
        v_min = float(self.properties.get("Min", 0.0))
        v_max = float(self.properties.get("Max", 100.0))
        self.outputs[0].value = max(v_min, min(val, v_max))

@BlockRegistry.register
class HysteresisBlock(AnalogBase):
    def __init__(self, type_id="analog.hysteresis", default_name="HYSTERESIS", category="Analog Processing", description="Boolean Hysteresis"):
        super().__init__(type_id, default_name, category, description)
        self.inputs = [Pin("In", Pin.DIR_INPUT, Pin.TYPE_FLOAT)]
        self.outputs = [Pin("Out", Pin.DIR_OUTPUT, Pin.TYPE_BOOLEAN)]
        self.properties.update({"High Threshold": 80.0, "Low Threshold": 20.0})
        self.simulation_state["state"] = False

    def evaluate(self):
        val = float(self.inputs[0].value) if self.inputs[0].value is not None else 0.0
        high = float(self.properties.get("High Threshold", 80.0))
        low = float(self.properties.get("Low Threshold", 20.0))

        if val >= high:
            self.simulation_state["state"] = True
        elif val <= low:
            self.simulation_state["state"] = False

        self.outputs[0].value = self.simulation_state["state"]

@BlockRegistry.register
class MovingAverageBlock(AnalogBase):
    def __init__(self, type_id="analog.mov_avg", default_name="MOVING AVG", category="Analog Processing", description="Moving Average Filter"):
        super().__init__(type_id, default_name, category, description)
        self.inputs = [Pin("In", Pin.DIR_INPUT, Pin.TYPE_FLOAT)]
        self.outputs = [Pin("Out", Pin.DIR_OUTPUT, Pin.TYPE_FLOAT)]
        self.properties.update({"Window Size": 5})
        self.simulation_state["buffer"] = []

    def evaluate(self):
        val = float(self.inputs[0].value) if self.inputs[0].value is not None else 0.0
        window = max(1, int(self.properties.get("Window Size", 5)))

        buf = self.simulation_state["buffer"]
        buf.append(val)
        if len(buf) > window:
            buf.pop(0)

        self.outputs[0].value = sum(buf) / len(buf)
