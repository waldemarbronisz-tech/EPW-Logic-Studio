from logic_studio.blocks.base import BaseLogicBlock
from logic_studio.blocks.pin import Pin
from logic_studio.blocks.registry import BlockRegistry

@BlockRegistry.register
class DigitalInputBlock(BaseLogicBlock):
    def __init__(self, type_id="input.di", default_name="DI", category="Wejścia / Wyjścia", description="Electrical Digital Input (ELA)"):
        super().__init__(type_id, default_name, category, description)
        self.color = "#008000" # Classic dark green
        self.width = 100
        self.height = 60
        self.properties["Address"] = "ELA01.DI01"
        self.properties["Force State"] = "NO FORCE"

        out1 = Pin("State", Pin.DIR_OUTPUT, Pin.TYPE_BOOLEAN)
        self.outputs = [out1]

    def evaluate(self, engine=None):
        addr = self.properties.get("Address", "")
        force_state = self.properties.get("Force State", "NO FORCE")

        if force_state == "FORCE TRUE":
            self.outputs[0].value = True
        elif force_state == "FORCE FALSE":
            self.outputs[0].value = False
        else:
            if engine and hasattr(engine, 'io') and engine.io is not None:
                self.outputs[0].value = engine.io.read_digital(addr)
            else:
                self.outputs[0].value = False

@BlockRegistry.register
class DigitalOutputBlock(BaseLogicBlock):
    def __init__(self, type_id="output.do", default_name="DO", category="Wejścia / Wyjścia", description="Automation Digital Output (ADA)"):
        super().__init__(type_id, default_name, category, description)
        self.color = "#800000" # Classic dark red
        self.width = 100
        self.height = 60
        self.properties["Address"] = "ADA01.DO01"

        in1 = Pin("Cmd", Pin.DIR_INPUT, Pin.TYPE_BOOLEAN)
        self.inputs = [in1]

    def evaluate(self, engine=None):
        v = self.inputs[0].value
        val = v if v is not None else False

        if engine and hasattr(engine, 'io') and engine.io is not None:
            addr = self.properties.get("Address", "")
            engine.io.write_digital(addr, val)

        self.simulation_state["sim_value"] = val
