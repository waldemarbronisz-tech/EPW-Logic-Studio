from logic_studio.blocks.base import BaseLogicBlock
from logic_studio.blocks.pin import Pin
from logic_studio.blocks.registry import BlockRegistry

# Helper to support dynamic inputs
class LogicGateBase(BaseLogicBlock):
    def __init__(self, name, category, description, default_inputs=2):
        super().__init__(name, category, description)
        self.color = "#00557f" # Industrial deep blue
        self.width = 60
        self.height = max(60, 20 + default_inputs * 20)

        for i in range(default_inputs):
            self.inputs.append(Pin(f"In{i+1}", Pin.DIR_INPUT, Pin.TYPE_BOOLEAN))

        self.outputs.append(Pin("Out", Pin.DIR_OUTPUT, Pin.TYPE_BOOLEAN))

@BlockRegistry.register
class AndGate(LogicGateBase):
    def __init__(self, name="AND", category="Logic Gates", description="Logical AND operator"):
        super().__init__(name, category, description)

    def evaluate(self):
        result = True
        for p in self.inputs:
            v = p.value if p.value is not None else False
            result = result and bool(v)
        self.outputs[0].value = result

@BlockRegistry.register
class OrGate(LogicGateBase):
    def __init__(self, name="OR", category="Logic Gates", description="Logical OR operator"):
        super().__init__(name, category, description)

    def evaluate(self):
        result = False
        for p in self.inputs:
            v = p.value if p.value is not None else False
            result = result or bool(v)
        self.outputs[0].value = result

@BlockRegistry.register
class NotGate(LogicGateBase):
    def __init__(self, name="NOT", category="Logic Gates", description="Logical NOT operator"):
        super().__init__(name, category, description, default_inputs=1)

    def evaluate(self):
        v1 = self.inputs[0].value
        if v1 is not None:
            self.outputs[0].value = not bool(v1)
        else:
            self.outputs[0].value = True # NOT False -> True

@BlockRegistry.register
class XorGate(LogicGateBase):
    def __init__(self, name="XOR", category="Logic Gates", description="Logical Exclusive OR"):
        super().__init__(name, category, description, default_inputs=2)

    def evaluate(self):
        # XOR is true if odd number of true inputs
        trues = sum([1 for p in self.inputs if p.value])
        self.outputs[0].value = (trues % 2 != 0)

@BlockRegistry.register
class NandGate(LogicGateBase):
    def __init__(self, name="NAND", category="Logic Gates", description="Logical NAND"):
        super().__init__(name, category, description)

    def evaluate(self):
        result = True
        for p in self.inputs:
            v = p.value if p.value is not None else False
            result = result and bool(v)
        self.outputs[0].value = not result

@BlockRegistry.register
class NorGate(LogicGateBase):
    def __init__(self, name="NOR", category="Logic Gates", description="Logical NOR"):
        super().__init__(name, category, description)

    def evaluate(self):
        result = False
        for p in self.inputs:
            v = p.value if p.value is not None else False
            result = result or bool(v)
        self.outputs[0].value = not result

@BlockRegistry.register
class XnorGate(LogicGateBase):
    def __init__(self, name="XNOR", category="Logic Gates", description="Logical Exclusive NOR"):
        super().__init__(name, category, description, default_inputs=2)

    def evaluate(self):
        trues = sum([1 for p in self.inputs if p.value])
        self.outputs[0].value = (trues % 2 == 0)

@BlockRegistry.register
class BufferGate(LogicGateBase):
    def __init__(self, name="BUFFER", category="Logic Gates", description="Logical BUFFER"):
        super().__init__(name, category, description, default_inputs=1)

    def evaluate(self):
        self.outputs[0].value = self.inputs[0].value if self.inputs[0].value is not None else False
