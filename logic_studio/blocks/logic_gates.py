from logic_studio.blocks.base import BaseLogicBlock
from logic_studio.blocks.pin import Pin
from logic_studio.blocks.registry import BlockRegistry

# Helper to support dynamic inputs
class LogicGateBase(BaseLogicBlock):
    def __init__(self, type_id, default_name, category, description, default_inputs=2):
        super().__init__(type_id, default_name, category, description)
        self.color = "#00557f" # Industrial deep blue
        self.width = 60
        self.height = max(60, 20 + default_inputs * 20)

        for i in range(default_inputs):
            self.inputs.append(Pin(f"In{i+1}", Pin.DIR_INPUT, Pin.TYPE_BOOLEAN))

        self.outputs.append(Pin("Out", Pin.DIR_OUTPUT, Pin.TYPE_BOOLEAN))

@BlockRegistry.register
class AndGate(LogicGateBase):
    def __init__(self, type_id="logic.and", default_name="AND", category="Bramki logiczne", description="Logical AND operator"):
        super().__init__(type_id, default_name, category, description, default_inputs=2)

    def evaluate(self, engine=None):
        result = True
        for p in self.inputs:
            v = p.value if p.value is not None else False
            result = result and bool(v)
        self.outputs[0].value = result

@BlockRegistry.register
class And3Gate(LogicGateBase):
    def __init__(self, type_id="logic.and3", default_name="AND-3", category="Bramki logiczne", description="Logical AND 3 inputs"):
        super().__init__(type_id, default_name, category, description, default_inputs=3)

    def evaluate(self, engine=None):
        result = True
        for p in self.inputs:
            v = p.value if p.value is not None else False
            result = result and bool(v)
        self.outputs[0].value = result

@BlockRegistry.register
class And4Gate(LogicGateBase):
    def __init__(self, type_id="logic.and4", default_name="AND-4", category="Bramki logiczne", description="Logical AND 4 inputs"):
        super().__init__(type_id, default_name, category, description, default_inputs=4)

    def evaluate(self, engine=None):
        result = True
        for p in self.inputs:
            v = p.value if p.value is not None else False
            result = result and bool(v)
        self.outputs[0].value = result

@BlockRegistry.register
class OrGate(LogicGateBase):
    def __init__(self, type_id="logic.or", default_name="OR", category="Bramki logiczne", description="Logical OR operator"):
        super().__init__(type_id, default_name, category, description, default_inputs=2)

    def evaluate(self, engine=None):
        result = False
        for p in self.inputs:
            v = p.value if p.value is not None else False
            result = result or bool(v)
        self.outputs[0].value = result

@BlockRegistry.register
class Or3Gate(LogicGateBase):
    def __init__(self, type_id="logic.or3", default_name="OR-3", category="Bramki logiczne", description="Logical OR 3 inputs"):
        super().__init__(type_id, default_name, category, description, default_inputs=3)

    def evaluate(self, engine=None):
        result = False
        for p in self.inputs:
            v = p.value if p.value is not None else False
            result = result or bool(v)
        self.outputs[0].value = result

@BlockRegistry.register
class Or4Gate(LogicGateBase):
    def __init__(self, type_id="logic.or4", default_name="OR-4", category="Bramki logiczne", description="Logical OR 4 inputs"):
        super().__init__(type_id, default_name, category, description, default_inputs=4)

    def evaluate(self, engine=None):
        result = False
        for p in self.inputs:
            v = p.value if p.value is not None else False
            result = result or bool(v)
        self.outputs[0].value = result

@BlockRegistry.register
class NotGate(LogicGateBase):
    def __init__(self, type_id="logic.not", default_name="NOT", category="Bramki logiczne", description="Logical NOT operator"):
        super().__init__(type_id, default_name, category, description, default_inputs=1)

    def evaluate(self, engine=None):
        v1 = self.inputs[0].value
        if v1 is not None:
            self.outputs[0].value = not bool(v1)
        else:
            self.outputs[0].value = True # NOT False -> True

@BlockRegistry.register
class XorGate(LogicGateBase):
    def __init__(self, type_id="logic.xor", default_name="XOR", category="Bramki logiczne", description="Logical Exclusive OR"):
        super().__init__(type_id, default_name, category, description, default_inputs=2)

    def evaluate(self, engine=None):
        # XOR is true if odd number of true inputs
        trues = sum([1 for p in self.inputs if p.value])
        self.outputs[0].value = (trues % 2 != 0)

@BlockRegistry.register
class NandGate(LogicGateBase):
    def __init__(self, type_id="logic.nand", default_name="NAND", category="Bramki logiczne", description="Logical NAND"):
        super().__init__(type_id, default_name, category, description, default_inputs=2)

    def evaluate(self, engine=None):
        result = True
        for p in self.inputs:
            v = p.value if p.value is not None else False
            result = result and bool(v)
        self.outputs[0].value = not result

@BlockRegistry.register
class Nand3Gate(LogicGateBase):
    def __init__(self, type_id="logic.nand3", default_name="NAND-3", category="Bramki logiczne", description="Logical NAND 3 inputs"):
        super().__init__(type_id, default_name, category, description, default_inputs=3)

    def evaluate(self, engine=None):
        result = True
        for p in self.inputs:
            v = p.value if p.value is not None else False
            result = result and bool(v)
        self.outputs[0].value = not result

@BlockRegistry.register
class Nand4Gate(LogicGateBase):
    def __init__(self, type_id="logic.nand4", default_name="NAND-4", category="Bramki logiczne", description="Logical NAND 4 inputs"):
        super().__init__(type_id, default_name, category, description, default_inputs=4)

    def evaluate(self, engine=None):
        result = True
        for p in self.inputs:
            v = p.value if p.value is not None else False
            result = result and bool(v)
        self.outputs[0].value = not result

@BlockRegistry.register
class NorGate(LogicGateBase):
    def __init__(self, type_id="logic.nor", default_name="NOR", category="Bramki logiczne", description="Logical NOR"):
        super().__init__(type_id, default_name, category, description, default_inputs=2)

    def evaluate(self, engine=None):
        result = False
        for p in self.inputs:
            v = p.value if p.value is not None else False
            result = result or bool(v)
        self.outputs[0].value = not result

@BlockRegistry.register
class Nor3Gate(LogicGateBase):
    def __init__(self, type_id="logic.nor3", default_name="NOR-3", category="Bramki logiczne", description="Logical NOR 3 inputs"):
        super().__init__(type_id, default_name, category, description, default_inputs=3)

    def evaluate(self, engine=None):
        result = False
        for p in self.inputs:
            v = p.value if p.value is not None else False
            result = result or bool(v)
        self.outputs[0].value = not result

@BlockRegistry.register
class Nor4Gate(LogicGateBase):
    def __init__(self, type_id="logic.nor4", default_name="NOR-4", category="Bramki logiczne", description="Logical NOR 4 inputs"):
        super().__init__(type_id, default_name, category, description, default_inputs=4)

    def evaluate(self, engine=None):
        result = False
        for p in self.inputs:
            v = p.value if p.value is not None else False
            result = result or bool(v)
        self.outputs[0].value = not result

@BlockRegistry.register
class XnorGate(LogicGateBase):
    def __init__(self, type_id="logic.xnor", default_name="XNOR", category="Bramki logiczne", description="Logical Exclusive NOR"):
        super().__init__(type_id, default_name, category, description, default_inputs=2)

    def evaluate(self, engine=None):
        trues = sum([1 for p in self.inputs if p.value])
        self.outputs[0].value = (trues % 2 == 0)

@BlockRegistry.register
class BufferGate(LogicGateBase):
    def __init__(self, type_id="logic.buffer", default_name="BUFFER", category="Bramki logiczne", description="Logical BUFFER"):
        super().__init__(type_id, default_name, category, description, default_inputs=1)

    def evaluate(self, engine=None):
        self.outputs[0].value = self.inputs[0].value if self.inputs[0].value is not None else False
