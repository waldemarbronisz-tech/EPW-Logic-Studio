from logic_studio.blocks.base import BaseLogicBlock
from logic_studio.blocks.pin import Pin
from logic_studio.blocks.registry import BlockRegistry

class ComparatorBase(BaseLogicBlock):
    def __init__(self, type_id, default_name, category, description):
        super().__init__(type_id, default_name, category, description)
        self.color = "#000080" # Classic Navy for comparators
        self.width = 80
        self.height = 80

        self.inputs.append(Pin("In1", Pin.DIR_INPUT, Pin.TYPE_FLOAT))
        self.inputs.append(Pin("In2", Pin.DIR_INPUT, Pin.TYPE_FLOAT))
        self.outputs.append(Pin("Out", Pin.DIR_OUTPUT, Pin.TYPE_BOOLEAN))

    def _get_vals(self):
        v1 = float(self.inputs[0].value) if self.inputs[0].value is not None else 0.0
        v2 = float(self.inputs[1].value) if self.inputs[1].value is not None else 0.0
        return v1, v2

@BlockRegistry.register
class GreaterBlock(ComparatorBase):
    def __init__(self, type_id="compare.gt", default_name=">", category="Comparators", description="Greater Than"):
        super().__init__(type_id, default_name, category, description)

    def evaluate(self):
        v1, v2 = self._get_vals()
        self.outputs[0].value = (v1 > v2)

@BlockRegistry.register
class LessBlock(ComparatorBase):
    def __init__(self, type_id="compare.lt", default_name="<", category="Comparators", description="Less Than"):
        super().__init__(type_id, default_name, category, description)

    def evaluate(self):
        v1, v2 = self._get_vals()
        self.outputs[0].value = (v1 < v2)

@BlockRegistry.register
class GreaterEqBlock(ComparatorBase):
    def __init__(self, type_id="compare.gte", default_name=">=", category="Comparators", description="Greater Than or Equal"):
        super().__init__(type_id, default_name, category, description)

    def evaluate(self):
        v1, v2 = self._get_vals()
        self.outputs[0].value = (v1 >= v2)

@BlockRegistry.register
class LessEqBlock(ComparatorBase):
    def __init__(self, type_id="compare.lte", default_name="<=", category="Comparators", description="Less Than or Equal"):
        super().__init__(type_id, default_name, category, description)

    def evaluate(self):
        v1, v2 = self._get_vals()
        self.outputs[0].value = (v1 <= v2)

@BlockRegistry.register
class EqualBlock(ComparatorBase):
    def __init__(self, type_id="compare.eq", default_name="==", category="Comparators", description="Equal"):
        super().__init__(type_id, default_name, category, description)

    def evaluate(self):
        v1, v2 = self._get_vals()
        self.outputs[0].value = (v1 == v2)

@BlockRegistry.register
class NotEqualBlock(ComparatorBase):
    def __init__(self, type_id="compare.neq", default_name="!=", category="Comparators", description="Not Equal"):
        super().__init__(type_id, default_name, category, description)

    def evaluate(self):
        v1, v2 = self._get_vals()
        self.outputs[0].value = (v1 != v2)

@BlockRegistry.register
class BetweenBlock(BaseLogicBlock):
    def __init__(self, type_id="compare.between", default_name="Between", category="Comparators", description="Between Limits"):
        super().__init__(type_id, default_name, category, description)
        self.color = "#000080"
        self.width = 80
        self.height = 100

        self.inputs.append(Pin("Min", Pin.DIR_INPUT, Pin.TYPE_FLOAT))
        self.inputs.append(Pin("Val", Pin.DIR_INPUT, Pin.TYPE_FLOAT))
        self.inputs.append(Pin("Max", Pin.DIR_INPUT, Pin.TYPE_FLOAT))
        self.outputs.append(Pin("Out", Pin.DIR_OUTPUT, Pin.TYPE_BOOLEAN))

    def evaluate(self):
        vmin = float(self.inputs[0].value) if self.inputs[0].value is not None else 0.0
        vval = float(self.inputs[1].value) if self.inputs[1].value is not None else 0.0
        vmax = float(self.inputs[2].value) if self.inputs[2].value is not None else 0.0

        self.outputs[0].value = (vmin <= vval <= vmax)
