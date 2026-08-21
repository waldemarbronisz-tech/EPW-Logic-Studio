from logic_studio.blocks.base import BaseLogicBlock
from logic_studio.blocks.pin import Pin
from logic_studio.blocks.registry import BlockRegistry

@BlockRegistry.register
class DigitalInputBlock(BaseLogicBlock):
    def __init__(self, type_id="input.di", default_name="DI", category="Wejścia / Wyjścia", description="Electrical Digital Input (ELA)"):
        super().__init__(type_id, default_name, category, description)
        self.color = "#008000" # Classic dark green
        self.width = 100
        self.height = 60
        self.properties["Address"] = "DI01"
        self.properties["Force Value"] = False

        out1 = Pin("State", Pin.DIR_OUTPUT, Pin.TYPE_BOOLEAN)
        self.outputs = [out1]

    def evaluate(self, engine=None):
        # The execution engine or SimulationPanel will inject real ELA state.
        # This is a placeholder for the block's internal logic.
        if "sim_value" in self.simulation_state:
            self.outputs[0].value = self.simulation_state["sim_value"]
        else:
            self.outputs[0].value = False

@BlockRegistry.register
class DigitalOutputBlock(BaseLogicBlock):
    def __init__(self, type_id="output.do", default_name="DO", category="Wejścia / Wyjścia", description="Automation Digital Output (ADA)"):
        super().__init__(type_id, default_name, category, description)
        self.color = "#800000" # Classic dark red
        self.width = 100
        self.height = 60
        self.properties["Address"] = "DO01"

        in1 = Pin("Cmd", Pin.DIR_INPUT, Pin.TYPE_BOOLEAN)
        self.inputs = [in1]

    def evaluate(self, engine=None):
        v = self.inputs[0].value
        self.simulation_state["sim_value"] = v if v is not None else False
