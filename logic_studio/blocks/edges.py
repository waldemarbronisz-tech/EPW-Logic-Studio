from logic_studio.blocks.base import BaseLogicBlock
from logic_studio.blocks.pin import Pin
from logic_studio.blocks.registry import BlockRegistry

class EdgeBase(BaseLogicBlock):
    def __init__(self, type_id, default_name, category, description):
        super().__init__(type_id, default_name, category, description)
        self.color = "#8A2BE2" # BlueViolet for edge processing
        self.width = 60
        self.height = 60

        self.inputs = [Pin("In", Pin.DIR_INPUT, Pin.TYPE_BOOLEAN)]
        self.outputs = [Pin("Out", Pin.DIR_OUTPUT, Pin.TYPE_BOOLEAN)]

        self.simulation_state["last_in"] = False

@BlockRegistry.register
class RTrigBlock(EdgeBase):
    def __init__(self, type_id="edge.rtrig", default_name="R_TRIG", category="Bramki logiczne", description="Rising Edge Trigger"):
        super().__init__(type_id, default_name, category, description)

    def evaluate(self, engine=None):
        current = bool(self.inputs[0].value)
        self.outputs[0].value = (current and not self.simulation_state["last_in"])
        self.simulation_state["last_in"] = current

@BlockRegistry.register
class FTrigBlock(EdgeBase):
    def __init__(self, type_id="edge.ftrig", default_name="F_TRIG", category="Bramki logiczne", description="Falling Edge Trigger"):
        super().__init__(type_id, default_name, category, description)
        self.simulation_state["last_in"] = True # Assume stable high if evaluating

    def evaluate(self, engine=None):
        current = bool(self.inputs[0].value)
        self.outputs[0].value = (not current and self.simulation_state["last_in"])
        self.simulation_state["last_in"] = current

@BlockRegistry.register
class ChangeBlock(EdgeBase):
    def __init__(self, type_id="edge.change", default_name="CHANGE", category="Bramki logiczne", description="Value Change Trigger"):
        super().__init__(type_id, default_name, category, description)

    def evaluate(self, engine=None):
        # Trigger on either edge
        current = bool(self.inputs[0].value)
        self.outputs[0].value = (current != self.simulation_state["last_in"])
        self.simulation_state["last_in"] = current
