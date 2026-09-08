from logic_studio.blocks.base import BaseLogicBlock
from logic_studio.blocks.pin import Pin
from logic_studio.blocks.registry import BlockRegistry

class MemoryBase(BaseLogicBlock):
    PIN_DESCRIPTIONS = {"Q": "Aktualny stan zatrzasku."}

    def __init__(self, type_id, default_name, category, description):
        super().__init__(type_id, default_name, category, description)
        self.color = "#808000" # Classic Olive for memory
        self.width = 80
        self.height = 80

        self.outputs.append(Pin("Q", Pin.DIR_OUTPUT, Pin.TYPE_BOOLEAN))
        # Internal state memory
        self._memory = False
        self.is_stateful = True

    def reset_runtime_state(self):
        self._memory = False

@BlockRegistry.register
class SR(MemoryBase):
    PIN_DESCRIPTIONS = {
        "S1": "Wejście ustawiające (Set) — nadrzędne: gdy S1 i R są jednocześnie aktywne, wygrywa Set.",
        "R": "Wejście kasujące (Reset).",
    }

    def __init__(self, type_id="memory.sr", default_name="SR", category="Przerzutniki", description="Zatrzask z nadrzędnym ustawianiem (Set dominuje nad Reset)."):
        super().__init__(type_id, default_name, category, description)
        self.aliases = ["przerzutnik", "zatrzask", "pamięć"]
        self.inputs.append(Pin("S1", Pin.DIR_INPUT, Pin.TYPE_BOOLEAN))
        self.inputs.append(Pin("R", Pin.DIR_INPUT, Pin.TYPE_BOOLEAN))

    def evaluate(self, engine=None):
        s = bool(self.inputs[0].value)
        r = bool(self.inputs[1].value)

        if s: # Set dominant
            self._memory = True
        elif r:
            self._memory = False

        self.outputs[0].value = self._memory

@BlockRegistry.register
class RS(MemoryBase):
    PIN_DESCRIPTIONS = {
        "R1": "Wejście kasujące (Reset) — nadrzędne: gdy R1 i S są jednocześnie aktywne, wygrywa Reset.",
        "S": "Wejście ustawiające (Set).",
    }

    def __init__(self, type_id="memory.rs", default_name="RS", category="Przerzutniki", description="Zatrzask z nadrzędnym kasowaniem (Reset dominuje nad Set)."):
        super().__init__(type_id, default_name, category, description)
        self.aliases = ["przerzutnik", "zatrzask", "pamięć"]
        self.inputs.append(Pin("R1", Pin.DIR_INPUT, Pin.TYPE_BOOLEAN))
        self.inputs.append(Pin("S", Pin.DIR_INPUT, Pin.TYPE_BOOLEAN))

    def evaluate(self, engine=None):
        r = bool(self.inputs[0].value)
        s = bool(self.inputs[1].value)

        if r: # Reset dominant
            self._memory = False
        elif s:
            self._memory = True

        self.outputs[0].value = self._memory
