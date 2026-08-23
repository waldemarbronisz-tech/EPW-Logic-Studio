from logic_studio.blocks.base import BaseLogicBlock
from logic_studio.blocks.pin import Pin
from logic_studio.blocks.registry import BlockRegistry
import time

class TimerBase(BaseLogicBlock):
    def __init__(self, type_id, default_name, category, description):
        super().__init__(type_id, default_name, category, description)
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
        self.is_stateful = True

    def _get_time(self, engine):
        if engine and hasattr(engine, 'time') and engine.time:
            return engine.time.current_time_ms()
        raise RuntimeError("TimeProvider missing. ExecutionEngine must inject deterministic time.")

    def reset_runtime_state(self):
        self.start_time = 0
        self.running = False
        if "last_in" in self.simulation_state:
            self.simulation_state["last_in"] = False

    def get_preset(self):
        # Prefer pin value, fallback to property
        if self.inputs[1].value is not None:
            return int(self.inputs[1].value)
        return int(self.properties.get("Preset (ms)", 1000))

@BlockRegistry.register
class TON(TimerBase):
    def __init__(self, type_id="timer.ton", default_name="TON", category="Timery", description="Timer On Delay"):
        super().__init__(type_id, default_name, category, description)

    def evaluate(self, engine=None):
        in_state = bool(self.inputs[0].value)
        pt = self.get_preset()

        if in_state:
            if not self.running:
                self.running = True
                self.start_time = self._get_time(engine)
                self.outputs[1].value = 0
                self.outputs[0].value = False
            else:
                elapsed = (self._get_time(engine)) - self.start_time
                self.outputs[1].value = int(min(elapsed, pt))
                if elapsed >= pt:
                    self.outputs[0].value = True
        else:
            self.running = False
            self.outputs[1].value = 0
            self.outputs[0].value = False

@BlockRegistry.register
class TOF(TimerBase):
    def __init__(self, type_id="timer.tof", default_name="TOF", category="Timery", description="Timer Off Delay"):
        super().__init__(type_id, default_name, category, description)
        self.outputs[0].value = False

    def evaluate(self, engine=None):
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
                    self.start_time = self._get_time(engine)
                else:
                    elapsed = (self._get_time(engine)) - self.start_time
                    self.outputs[1].value = int(min(elapsed, pt))
                    if elapsed >= pt:
                        self.outputs[0].value = False
                        self.running = False

@BlockRegistry.register
class TP(TimerBase):
    def __init__(self, type_id="timer.tp", default_name="TP", category="Timery", description="Pulse Timer"):
        super().__init__(type_id, default_name, category, description)
        self.simulation_state["last_in"] = False

    def evaluate(self, engine=None):
        in_state = bool(self.inputs[0].value)
        pt = self.get_preset()

        # Rising edge detection
        rising_edge = in_state and not self.simulation_state["last_in"]
        self.simulation_state["last_in"] = in_state

        if rising_edge and not self.running:
            # Trigger
            self.running = True
            self.start_time = self._get_time(engine)
            self.outputs[0].value = True

        if self.running:
            elapsed = (self._get_time(engine)) - self.start_time
            self.outputs[1].value = int(min(elapsed, pt))
            if elapsed >= pt:
                self.outputs[0].value = False
                self.running = False
        else:
            self.outputs[1].value = 0
            self.outputs[0].value = False
