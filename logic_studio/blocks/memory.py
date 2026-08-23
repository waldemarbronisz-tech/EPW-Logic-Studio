from logic_studio.blocks.base import BaseLogicBlock
from logic_studio.blocks.pin import Pin
from logic_studio.blocks.registry import BlockRegistry

class MemoryBase(BaseLogicBlock):
    def __init__(self, type_id, default_name, category, description):
        super().__init__(type_id, default_name, category, description)
        self.color = "#808000" # Classic Olive for memory
        self.width = 80
        self.height = 80

        self.outputs.append(Pin("Q", Pin.DIR_OUTPUT, Pin.TYPE_BOOLEAN))
        # Internal state memory
        self.simulation_state["memory"] = False
        self.is_stateful = True

    def reset_runtime_state(self):
        self.simulation_state["memory"] = False

@BlockRegistry.register
class SR(MemoryBase):
    def __init__(self, type_id="memory.sr", default_name="SR", category="Przerzutniki", description="Set Dominant Latch"):
        super().__init__(type_id, default_name, category, description)
        self.inputs.append(Pin("S1", Pin.DIR_INPUT, Pin.TYPE_BOOLEAN))
        self.inputs.append(Pin("R", Pin.DIR_INPUT, Pin.TYPE_BOOLEAN))

    def evaluate(self, engine=None):
        s = bool(self.inputs[0].value)
        r = bool(self.inputs[1].value)

        if s: # Set dominant
            self.simulation_state["memory"] = True
        elif r:
            self.simulation_state["memory"] = False

        self.outputs[0].value = self.simulation_state["memory"]

@BlockRegistry.register
class RS(MemoryBase):
    def __init__(self, type_id="memory.rs", default_name="RS", category="Przerzutniki", description="Reset Dominant Latch"):
        super().__init__(type_id, default_name, category, description)
        self.inputs.append(Pin("R1", Pin.DIR_INPUT, Pin.TYPE_BOOLEAN))
        self.inputs.append(Pin("S", Pin.DIR_INPUT, Pin.TYPE_BOOLEAN))

    def evaluate(self, engine=None):
        r = bool(self.inputs[0].value)
        s = bool(self.inputs[1].value)

        if r: # Reset dominant
            self.simulation_state["memory"] = False
        elif s:
            self.simulation_state["memory"] = True

        self.outputs[0].value = self.simulation_state["memory"]
