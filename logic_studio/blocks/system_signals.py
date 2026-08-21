from logic_studio.blocks.base import BaseLogicBlock
from logic_studio.blocks.pin import Pin
from logic_studio.blocks.registry import BlockRegistry

@BlockRegistry.register
class SystemBooleanSignalBlock(BaseLogicBlock):
    def __init__(self, type_id="system.signal", default_name="SYS SIG", category="Inne", description="System Boolean Signal"):
        super().__init__(type_id, default_name, category, description)

        self.color = "#800080" # Purple
        self.outputs.append(Pin("Out", Pin.DIR_OUTPUT, Pin.TYPE_BOOLEAN))

        self.properties["Signal"] = "Sys.Ready"
        self.properties["Tag"] = "SYS_READY"

    def evaluate(self, engine=None):
        # Stub for system signals, in actual implementation would read from runtime engine
        self.outputs[0].value = True

@BlockRegistry.register
class ButtonBlock(BaseLogicBlock):
    def __init__(self, type_id="system.button", default_name="Przycisk", category="Przyciski", description="Przycisk interfejsu"):
        super().__init__(type_id, default_name, category, description)
        self.color = "#000000"
        self.outputs.append(Pin("Out", Pin.DIR_OUTPUT, Pin.TYPE_BOOLEAN))
        self.properties["Tag"] = ""

    def evaluate(self, engine=None):
        self.outputs[0].value = True

@BlockRegistry.register
class LedBlock(BaseLogicBlock):
    def __init__(self, type_id="system.led", default_name="LED", category="LED", description="Dioda sygnalizacyjna"):
        super().__init__(type_id, default_name, category, description)
        self.color = "#000000"
        self.inputs.append(Pin("In", Pin.DIR_INPUT, Pin.TYPE_BOOLEAN))
        self.properties["Tag"] = ""

    def evaluate(self, engine=None):
        self.outputs[0].value = True

@BlockRegistry.register
class UserMessageBlock(BaseLogicBlock):
    def __init__(self, type_id="system.message", default_name="Komunikat użytkownika", category="Liczniki", description="Wiadomość tekstowa dla operatora"):
        super().__init__(type_id, default_name, category, description)
        self.color = "#000000"
        self.width = 120
        self.height = 40
        self.inputs.append(Pin("In", Pin.DIR_INPUT, Pin.TYPE_BOOLEAN))
        self.properties["Message 0"] = "Brak alarmu"
        self.properties["Message 1"] = "Aktywny alarm"

    def evaluate(self, engine=None):
        self.outputs[0].value = True

@BlockRegistry.register
class SignalGeneratorBlock(BaseLogicBlock):
    def __init__(self, type_id="system.generator", default_name="Generator sygnału", category="Inne", description="Generator przebiegu prostokątnego"):
        super().__init__(type_id, default_name, category, description)
        self.color = "#000000"
        self.outputs.append(Pin("Out", Pin.DIR_OUTPUT, Pin.TYPE_BOOLEAN))
        self.properties["Period (s)"] = 1.0

    def evaluate(self, engine=None):
        # Simple flip-flop stub based on OS time or similar logic for simulation
        self.outputs[0].value = True
