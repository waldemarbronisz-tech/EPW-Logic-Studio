from logic_studio.blocks.base import BaseLogicBlock
from logic_studio.blocks.pin import Pin
from logic_studio.blocks.registry import BlockRegistry

@BlockRegistry.register
class SystemSignalBlock(BaseLogicBlock):
    def __init__(self, type_id="system.signal", default_name="SYS SIG", category="System", description="System Boolean Signal"):
        super().__init__(type_id, default_name, category, description)
        self.color = "#4B0082" # Indigo
        self.width = 120
        self.height = 60
        self.properties["Tag"] = "SYSTEM.CORE_ONLINE"

        self.outputs = [Pin("State", Pin.DIR_OUTPUT, Pin.TYPE_BOOLEAN)]

    def evaluate(self):
        if "sim_value" in self.simulation_state:
            self.outputs[0].value = self.simulation_state["sim_value"]
        else:
            tag = self.properties.get("Tag", "")
            if tag.endswith("ONLINE") or tag.endswith("OK") or tag.endswith("COMPLETE"):
                self.outputs[0].value = True
            else:
                self.outputs[0].value = False
