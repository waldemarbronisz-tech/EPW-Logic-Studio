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
        if engine and hasattr(engine, 'io'):
            # Fetch from IO provider or simulation memory. E.g., simulated system states
            self.outputs[0].value = engine.io.read_digital_input(self.properties.get("Tag", "SYS_READY"))
        else:
            self.outputs[0].value = False

@BlockRegistry.register
class ButtonBlock(BaseLogicBlock):
    def __init__(self, type_id="system.button", default_name="Przycisk", category="Przyciski", description="Przycisk interfejsu"):
        super().__init__(type_id, default_name, category, description)
        self.color = "#000000"
        self.outputs.append(Pin("Out", Pin.DIR_OUTPUT, Pin.TYPE_BOOLEAN))
        self.properties["Tag"] = ""

    def evaluate(self, engine=None):
        # User message is a sink. Store message string in simulation state based on input.
        val = bool(self.inputs[0].value) if self.inputs and self.inputs[0].value is not None else False
        msg = self.properties.get("Message 1", "") if val else self.properties.get("Message 0", "")
        self.simulation_state["display_message"] = msg
        self.simulation_state["sim_value"] = val

@BlockRegistry.register
class LedBlock(BaseLogicBlock):
    def __init__(self, type_id="system.led", default_name="LED", category="LED", description="Dioda sygnalizacyjna"):
        super().__init__(type_id, default_name, category, description)
        self.color = "#000000"
        self.inputs.append(Pin("In", Pin.DIR_INPUT, Pin.TYPE_BOOLEAN))
        self.properties["Tag"] = ""

    def evaluate(self, engine=None):
        # LED is a sink. Store state for UI visualization.
        val = bool(self.inputs[0].value) if self.inputs and self.inputs[0].value is not None else False
        self.simulation_state["sim_value"] = val

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
        # User message is a sink. Store message string in simulation state based on input.
        val = bool(self.inputs[0].value) if self.inputs and self.inputs[0].value is not None else False
        msg = self.properties.get("Message 1", "") if val else self.properties.get("Message 0", "")
        self.simulation_state["display_message"] = msg
        self.simulation_state["sim_value"] = val

@BlockRegistry.register
class SignalGeneratorBlock(BaseLogicBlock):
    def __init__(self, type_id="system.generator", default_name="Generator sygnału", category="Inne", description="Generator przebiegu prostokątnego"):
        super().__init__(type_id, default_name, category, description)
        self.color = "#000000"
        self.outputs.append(Pin("Out", Pin.DIR_OUTPUT, Pin.TYPE_BOOLEAN))
        self.properties["Period (s)"] = 1.0
        self.is_stateful = True

    def reset_runtime_state(self):
        pass # relies strictly on global engine clock for deterministic frequency, not local memory

    def evaluate(self, engine=None):
        period_ms = float(self.properties.get("Period (s)", 1.0)) * 1000.0
        if period_ms <= 0:
            self.outputs[0].value = False
            return

        if engine and hasattr(engine, 'time') and engine.time is not None:
            now = engine.time.current_time_ms()
            # Simple 50% duty cycle
            cycle_pos = now % period_ms
            self.outputs[0].value = cycle_pos >= (period_ms / 2.0)
        else:
            self.outputs[0].value = False
