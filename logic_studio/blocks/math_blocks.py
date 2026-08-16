from logic_studio.blocks.base import BaseLogicBlock
from logic_studio.blocks.pin import Pin
from logic_studio.blocks.registry import BlockRegistry

class MathBase(BaseLogicBlock):
    def __init__(self, type_id, default_name, category, description):
        super().__init__(type_id, default_name, category, description)
        self.color = "#800080" # Classic Purple for math
        self.width = 80
        self.height = 80

        self.inputs.append(Pin("In1", Pin.DIR_INPUT, Pin.TYPE_FLOAT))
        self.inputs.append(Pin("In2", Pin.DIR_INPUT, Pin.TYPE_FLOAT))
        self.outputs.append(Pin("Out", Pin.DIR_OUTPUT, Pin.TYPE_FLOAT))

    def _get_vals(self):
        v1 = float(self.inputs[0].value) if self.inputs[0].value is not None else 0.0
        v2 = float(self.inputs[1].value) if self.inputs[1].value is not None else 0.0
        return v1, v2

@BlockRegistry.register
class AddBlock(MathBase):
    def __init__(self, type_id="math.add", default_name="ADD", category="Mathematics", description="Addition"):
        super().__init__(type_id, default_name, category, description)

    def evaluate(self):
        v1, v2 = self._get_vals()
        self.outputs[0].value = v1 + v2

@BlockRegistry.register
class SubBlock(MathBase):
    def __init__(self, type_id="math.sub", default_name="SUB", category="Mathematics", description="Subtraction"):
        super().__init__(type_id, default_name, category, description)

    def evaluate(self):
        v1, v2 = self._get_vals()
        self.outputs[0].value = v1 - v2

@BlockRegistry.register
class MulBlock(MathBase):
    def __init__(self, type_id="math.mul", default_name="MUL", category="Mathematics", description="Multiplication"):
        super().__init__(type_id, default_name, category, description)

    def evaluate(self):
        v1, v2 = self._get_vals()
        self.outputs[0].value = v1 * v2

@BlockRegistry.register
class DivBlock(MathBase):
    def __init__(self, type_id="math.div", default_name="DIV", category="Mathematics", description="Division"):
        super().__init__(type_id, default_name, category, description)

    def evaluate(self):
        v1, v2 = self._get_vals()
        if v2 != 0:
            self.outputs[0].value = v1 / v2
        else:
            # Deterministic safe value on div/0
            self.outputs[0].value = 0.0

@BlockRegistry.register
class AbsBlock(MathBase):
    def __init__(self, type_id="math.abs", default_name="ABS", category="Mathematics", description="Absolute Value"):
        super().__init__(type_id, default_name, category, description)
        self.inputs.pop() # Only 1 input

    def evaluate(self):
        v1 = float(self.inputs[0].value) if self.inputs[0].value is not None else 0.0
        self.outputs[0].value = abs(v1)

@BlockRegistry.register
class MinBlock(MathBase):
    def __init__(self, type_id="math.min", default_name="MIN", category="Mathematics", description="Minimum"):
        super().__init__(type_id, default_name, category, description)

    def evaluate(self):
        v1, v2 = self._get_vals()
        self.outputs[0].value = min(v1, v2)

@BlockRegistry.register
class MaxBlock(MathBase):
    def __init__(self, type_id="math.max", default_name="MAX", category="Mathematics", description="Maximum"):
        super().__init__(type_id, default_name, category, description)

    def evaluate(self):
        v1, v2 = self._get_vals()
        self.outputs[0].value = max(v1, v2)
