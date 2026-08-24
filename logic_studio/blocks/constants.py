from logic_studio.blocks.base import BaseLogicBlock
from logic_studio.blocks.pin import Pin
from logic_studio.blocks.registry import BlockRegistry

class ConstantBase(BaseLogicBlock):
    def __init__(self, type_id, default_name, category, description, pin_type):
        super().__init__(type_id, default_name, category, description)
        self.color = "#555555" # Dark grey for constants
        self.width = 60
        self.height = 60
        self.outputs = [Pin("Out", Pin.DIR_OUTPUT, pin_type)]

@BlockRegistry.register
class TrueConstant(ConstantBase):
    def __init__(self, type_id="const.true", default_name="TRUE", category="Inne", description="Boolean TRUE"):
        super().__init__(type_id, default_name, category, description, Pin.TYPE_BOOLEAN)

    def evaluate(self, engine=None):
        self.outputs[0].value = True

@BlockRegistry.register
class FalseConstant(ConstantBase):
    def __init__(self, type_id="const.false", default_name="FALSE", category="Inne", description="Boolean FALSE"):
        super().__init__(type_id, default_name, category, description, Pin.TYPE_BOOLEAN)

    def evaluate(self, engine=None):
        self.outputs[0].value = False

@BlockRegistry.register
class RealConstant(ConstantBase):
    def __init__(self, type_id="const.real", default_name="REAL", category="Inne", description="Real Constant"):
        super().__init__(type_id, default_name, category, description, Pin.TYPE_FLOAT)
        self.properties["Value"] = 0.0

    def evaluate(self, engine=None):
        try:
            self.outputs[0].value = float(self.properties.get("Value", 0.0))
        except ValueError:
            self.outputs[0].value = 0.0

@BlockRegistry.register
class IntConstant(ConstantBase):
    def __init__(self, type_id="const.int", default_name="INT", category="Inne", description="Integer Constant"):
        super().__init__(type_id, default_name, category, description, Pin.TYPE_INTEGER)
        self.properties["Value"] = 0

    def evaluate(self, engine=None):
        try:
            self.outputs[0].value = int(self.properties.get("Value", 0))
        except ValueError:
            self.outputs[0].value = 0

@BlockRegistry.register
class TimeConstant(ConstantBase):
    def __init__(self, type_id="const.time", default_name="TIME", category="Inne", description="Time Constant (ms)"):
        super().__init__(type_id, default_name, category, description, Pin.TYPE_INTEGER)
        self.properties["Time (ms)"] = 1000

    def evaluate(self, engine=None):
        try:
            self.outputs[0].value = int(self.properties.get("Time (ms)", 1000))
        except ValueError:
            self.outputs[0].value = 1000

@BlockRegistry.register
class StringConstant(ConstantBase):
    def __init__(self, type_id="const.string", default_name="STRING", category="Inne", description="String Constant"):
        super().__init__(type_id, default_name, category, description, Pin.TYPE_STRING)
        self.properties["Text"] = ""

    def evaluate(self, engine=None):
        self.outputs[0].value = str(self.properties.get("Text", ""))
