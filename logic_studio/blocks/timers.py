from logic_studio.blocks.base import BaseLogicBlock
from logic_studio.blocks.pin import Pin
from logic_studio.blocks.registry import BlockRegistry
import time

class TimerBase(BaseLogicBlock):
    def __init__(self, name, category, description):
        super().__init__(name, category, description)
        self.color = "#008080" # Classic Teal for timers
        self.width = 100
        self.height = 100

        self.inputs.append(Pin("IN", Pin.DIR_INPUT, Pin.TYPE_BOOLEAN))
        self.inputs.append(Pin("PT", Pin.DIR_INPUT, Pin.TYPE_INTEGER)) # Preset Time ms

        self.outputs.append(Pin("Q", Pin.DIR_OUTPUT, Pin.TYPE_BOOLEAN))
        self.outputs.append(Pin("ET", Pin.DIR_OUTPUT, Pin.TYPE_INTEGER)) # Elapsed Time ms

        # Internal state
        self.start_time = 0
        self.running = False
        self.properties["Preset (ms)"] = 1000

    def get_preset(self):
        # Prefer pin value, fallback to property
        if self.inputs[1].value is not None:
            return int(self.inputs[1].value)
        return int(self.properties.get("Preset (ms)", 1000))

@BlockRegistry.register
class TON(TimerBase):
    def __init__(self, name="TON", category="Timers", description="Timer On Delay"):
        super().__init__(name, category, description)

    def evaluate(self):
        in_state = bool(self.inputs[0].value)
        pt = self.get_preset()

        if in_state:
            if not self.running:
                self.running = True
                self.start_time = time.time() * 1000
                self.outputs[1].value = 0
                self.outputs[0].value = False
            else:
                elapsed = (time.time() * 1000) - self.start_time
                self.outputs[1].value = int(min(elapsed, pt))
                if elapsed >= pt:
                    self.outputs[0].value = True
        else:
            self.running = False
            self.outputs[1].value = 0
            self.outputs[0].value = False

@BlockRegistry.register
class TOF(TimerBase):
    def __init__(self, name="TOF", category="Timers", description="Timer Off Delay"):
        super().__init__(name, category, description)
        self.outputs[0].value = False

    def evaluate(self):
        in_state = bool(self.inputs[0].value)
        pt = self.get_preset()

        if in_state:
            self.running = False
            self.outputs[1].value = 0
            self.outputs[0].value = True
        else:
            if self.outputs[0].value: # It was ON, start timing OFF
                if not self.running:
                    self.running = True
                    self.start_time = time.time() * 1000
                else:
                    elapsed = (time.time() * 1000) - self.start_time
                    self.outputs[1].value = int(min(elapsed, pt))
                    if elapsed >= pt:
                        self.outputs[0].value = False
                        self.running = False

@BlockRegistry.register
class TP(TimerBase):
    def __init__(self, name="TP", category="Timers", description="Pulse Timer"):
        super().__init__(name, category, description)

    def evaluate(self):
        in_state = bool(self.inputs[0].value)
        pt = self.get_preset()

        if in_state and not self.running and not self.outputs[0].value:
            # Trigger
            self.running = True
            self.start_time = time.time() * 1000
            self.outputs[0].value = True

        if self.running:
            elapsed = (time.time() * 1000) - self.start_time
            self.outputs[1].value = int(min(elapsed, pt))
            if elapsed >= pt:
                self.outputs[0].value = False
                self.running = False
        else:
            self.outputs[1].value = 0
