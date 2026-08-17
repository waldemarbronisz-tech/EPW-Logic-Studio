from logic_studio.blocks.base import BaseLogicBlock
from logic_studio.blocks.pin import Pin
from logic_studio.blocks.registry import BlockRegistry

@BlockRegistry.register
class VirtualInputBlock(BaseLogicBlock):
    def __init__(self, type_id="virtual.input", default_name="Virtual IN", category="Wejścia / Wyjścia", description="Virtual Boolean Input"):
        super().__init__(type_id, default_name, category, description)
        self.color = "#006400" # Slightly different green from ELA
        self.width = 100
        self.height = 60
        self.properties["Tag"] = "VI.NEW_INPUT"
        self.properties["Force Value"] = False

        self.outputs = [Pin("State", Pin.DIR_OUTPUT, Pin.TYPE_BOOLEAN)]

    def evaluate(self):
        if self.properties.get("Force Value", False) in [True, "True", "true", "1"]:
            self.outputs[0].value = True
        elif "sim_value" in self.simulation_state:
            self.outputs[0].value = self.simulation_state["sim_value"]
        else:
            self.outputs[0].value = False

@BlockRegistry.register
class VirtualOutputBlock(BaseLogicBlock):
    def __init__(self, type_id="virtual.output", default_name="Virtual OUT", category="Wejścia / Wyjścia", description="Virtual Boolean Output"):
        super().__init__(type_id, default_name, category, description)
        self.color = "#8B0000" # Slightly different red from ADA
        self.width = 100
        self.height = 60
        self.properties["Tag"] = "VO.NEW_OUTPUT"

        self.inputs = [Pin("Cmd", Pin.DIR_INPUT, Pin.TYPE_BOOLEAN)]

    def evaluate(self):
        v = self.inputs[0].value
        self.simulation_state["sim_value"] = v if v is not None else False
