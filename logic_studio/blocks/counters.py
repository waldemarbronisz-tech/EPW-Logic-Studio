from logic_studio.blocks.base import BaseLogicBlock
from logic_studio.blocks.pin import Pin
from logic_studio.blocks.registry import BlockRegistry

class CounterBase(BaseLogicBlock):
    def __init__(self, name, category, description):
        super().__init__(name, category, description)
        self.color = "#008080" # Classic Teal (similar to Timers)
        self.width = 100
        self.height = 120
        self.properties["Preset"] = 10
        self.simulation_state["count"] = 0
        self.simulation_state["last_cu"] = False
        self.simulation_state["last_cd"] = False

    def get_preset(self):
        return int(self.properties.get("Preset", 10))

@BlockRegistry.register
class CTU(CounterBase):
    def __init__(self, name="CTU", category="Counters", description="Count Up"):
        super().__init__(name, category, description)
        self.inputs.append(Pin("CU", Pin.DIR_INPUT, Pin.TYPE_BOOLEAN))
        self.inputs.append(Pin("R", Pin.DIR_INPUT, Pin.TYPE_BOOLEAN))
        self.inputs.append(Pin("PV", Pin.DIR_INPUT, Pin.TYPE_INTEGER))

        self.outputs.append(Pin("Q", Pin.DIR_OUTPUT, Pin.TYPE_BOOLEAN))
        self.outputs.append(Pin("CV", Pin.DIR_OUTPUT, Pin.TYPE_INTEGER))

    def evaluate(self):
        cu = bool(self.inputs[0].value)
        r = bool(self.inputs[1].value)
        pv = int(self.inputs[2].value) if self.inputs[2].value is not None else self.get_preset()

        if r:
            self.simulation_state["count"] = 0
        elif cu and not self.simulation_state["last_cu"]:
            self.simulation_state["count"] += 1

        self.simulation_state["last_cu"] = cu

        cv = self.simulation_state["count"]
        self.outputs[1].value = cv
        self.outputs[0].value = (cv >= pv)

@BlockRegistry.register
class CTD(CounterBase):
    def __init__(self, name="CTD", category="Counters", description="Count Down"):
        super().__init__(name, category, description)
        self.inputs.append(Pin("CD", Pin.DIR_INPUT, Pin.TYPE_BOOLEAN))
        self.inputs.append(Pin("LD", Pin.DIR_INPUT, Pin.TYPE_BOOLEAN))
        self.inputs.append(Pin("PV", Pin.DIR_INPUT, Pin.TYPE_INTEGER))

        self.outputs.append(Pin("Q", Pin.DIR_OUTPUT, Pin.TYPE_BOOLEAN))
        self.outputs.append(Pin("CV", Pin.DIR_OUTPUT, Pin.TYPE_INTEGER))

    def evaluate(self):
        cd = bool(self.inputs[0].value)
        ld = bool(self.inputs[1].value)
        pv = int(self.inputs[2].value) if self.inputs[2].value is not None else self.get_preset()

        if ld:
            self.simulation_state["count"] = pv
        elif cd and not self.simulation_state["last_cd"]:
            self.simulation_state["count"] -= 1

        self.simulation_state["last_cd"] = cd

        cv = self.simulation_state["count"]
        self.outputs[1].value = cv
        self.outputs[0].value = (cv <= 0)

@BlockRegistry.register
class CTUD(CounterBase):
    def __init__(self, name="CTUD", category="Counters", description="Count Up Down"):
        super().__init__(name, category, description)
        self.height = 140
        self.inputs.append(Pin("CU", Pin.DIR_INPUT, Pin.TYPE_BOOLEAN))
        self.inputs.append(Pin("CD", Pin.DIR_INPUT, Pin.TYPE_BOOLEAN))
        self.inputs.append(Pin("R", Pin.DIR_INPUT, Pin.TYPE_BOOLEAN))
        self.inputs.append(Pin("LD", Pin.DIR_INPUT, Pin.TYPE_BOOLEAN))
        self.inputs.append(Pin("PV", Pin.DIR_INPUT, Pin.TYPE_INTEGER))

        self.outputs.append(Pin("QU", Pin.DIR_OUTPUT, Pin.TYPE_BOOLEAN))
        self.outputs.append(Pin("QD", Pin.DIR_OUTPUT, Pin.TYPE_BOOLEAN))
        self.outputs.append(Pin("CV", Pin.DIR_OUTPUT, Pin.TYPE_INTEGER))

    def evaluate(self):
        cu = bool(self.inputs[0].value)
        cd = bool(self.inputs[1].value)
        r = bool(self.inputs[2].value)
        ld = bool(self.inputs[3].value)
        pv = int(self.inputs[4].value) if self.inputs[4].value is not None else self.get_preset()

        if r:
            self.simulation_state["count"] = 0
        elif ld:
            self.simulation_state["count"] = pv
        else:
            if cu and not self.simulation_state["last_cu"]:
                self.simulation_state["count"] += 1
            if cd and not self.simulation_state["last_cd"]:
                self.simulation_state["count"] -= 1

        self.simulation_state["last_cu"] = cu
        self.simulation_state["last_cd"] = cd

        cv = self.simulation_state["count"]
        self.outputs[2].value = cv
        self.outputs[0].value = (cv >= pv)
        self.outputs[1].value = (cv <= 0)
