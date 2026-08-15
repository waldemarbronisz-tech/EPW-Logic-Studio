from logic_studio.blocks.base import BaseLogicBlock
from logic_studio.blocks.pin import Pin
from logic_studio.blocks.registry import BlockRegistry

class MathBase(BaseLogicBlock):
    def __init__(self, name, category, description):
        super().__init__(name, category, description)
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
    def __init__(self, name="ADD", category="Mathematics", description="Addition"):
        super().__init__(name, category, description)

    def evaluate(self):
        v1, v2 = self._get_vals()
        self.outputs[0].value = v1 + v2

@BlockRegistry.register
class SubBlock(MathBase):
    def __init__(self, name="SUB", category="Mathematics", description="Subtraction"):
        super().__init__(name, category, description)

    def evaluate(self):
        v1, v2 = self._get_vals()
        self.outputs[0].value = v1 - v2

@BlockRegistry.register
class MulBlock(MathBase):
    def __init__(self, name="MUL", category="Mathematics", description="Multiplication"):
        super().__init__(name, category, description)

    def evaluate(self):
        v1, v2 = self._get_vals()
        self.outputs[0].value = v1 * v2

@BlockRegistry.register
class DivBlock(MathBase):
    def __init__(self, name="DIV", category="Mathematics", description="Division"):
        super().__init__(name, category, description)

    def evaluate(self):
        v1, v2 = self._get_vals()
        if v2 != 0:
            self.outputs[0].value = v1 / v2
        else:
            self.outputs[0].value = 0.0 # Standard PLC fallback for division by zero

@BlockRegistry.register
class AbsBlock(MathBase):
    def __init__(self, name="ABS", category="Mathematics", description="Absolute Value"):
        super().__init__(name, category, description)
        self.inputs.pop() # Only 1 input

    def evaluate(self):
        v1 = float(self.inputs[0].value) if self.inputs[0].value is not None else 0.0
        self.outputs[0].value = abs(v1)

@BlockRegistry.register
class MinBlock(MathBase):
    def __init__(self, name="MIN", category="Mathematics", description="Minimum"):
        super().__init__(name, category, description)

    def evaluate(self):
        v1, v2 = self._get_vals()
        self.outputs[0].value = min(v1, v2)

@BlockRegistry.register
class MaxBlock(MathBase):
    def __init__(self, name="MAX", category="Mathematics", description="Maximum"):
        super().__init__(name, category, description)

    def evaluate(self):
        v1, v2 = self._get_vals()
        self.outputs[0].value = max(v1, v2)
