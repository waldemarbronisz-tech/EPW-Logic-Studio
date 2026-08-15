from logic_studio.blocks.base import BaseLogicBlock
from logic_studio.blocks.pin import Pin
from logic_studio.blocks.registry import BlockRegistry

@BlockRegistry.register
class AndGate(BaseLogicBlock):
    def __init__(self, name="AND", category="Logic Gates", description="Logical AND operator"):
        super().__init__(name, category, description)
        self.color = "#00557f" # Industrial deep blue

        # Default sizes for standard gate
        self.width = 60
        self.height = 80

        in1 = Pin("In1", Pin.DIR_INPUT, Pin.TYPE_BOOLEAN)
        in2 = Pin("In2", Pin.DIR_INPUT, Pin.TYPE_BOOLEAN)
        out1 = Pin("Out", Pin.DIR_OUTPUT, Pin.TYPE_BOOLEAN)

        self.inputs = [in1, in2]
        self.outputs = [out1]

    def evaluate(self):
        v1 = self.inputs[0].value
        v2 = self.inputs[1].value
        if v1 is not None and v2 is not None:
            self.outputs[0].value = bool(v1 and v2)

@BlockRegistry.register
class OrGate(BaseLogicBlock):
    def __init__(self, name="OR", category="Logic Gates", description="Logical OR operator"):
        super().__init__(name, category, description)
        self.color = "#00557f"
        self.width = 60
        self.height = 80

        in1 = Pin("In1", Pin.DIR_INPUT, Pin.TYPE_BOOLEAN)
        in2 = Pin("In2", Pin.DIR_INPUT, Pin.TYPE_BOOLEAN)
        out1 = Pin("Out", Pin.DIR_OUTPUT, Pin.TYPE_BOOLEAN)

        self.inputs = [in1, in2]
        self.outputs = [out1]

    def evaluate(self):
        v1 = self.inputs[0].value
        v2 = self.inputs[1].value
        if v1 is not None and v2 is not None:
            self.outputs[0].value = bool(v1 or v2)

@BlockRegistry.register
class NotGate(BaseLogicBlock):
    def __init__(self, name="NOT", category="Logic Gates", description="Logical NOT operator"):
        super().__init__(name, category, description)
        self.color = "#00557f"
        self.width = 60
        self.height = 60

        in1 = Pin("In", Pin.DIR_INPUT, Pin.TYPE_BOOLEAN)
        out1 = Pin("Out", Pin.DIR_OUTPUT, Pin.TYPE_BOOLEAN)

        self.inputs = [in1]
        self.outputs = [out1]

    def evaluate(self):
        v1 = self.inputs[0].value
        if v1 is not None:
            self.outputs[0].value = not bool(v1)
