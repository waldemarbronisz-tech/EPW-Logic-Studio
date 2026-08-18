from logic_studio.blocks.base import BaseLogicBlock
from logic_studio.blocks.registry import BlockRegistry

@BlockRegistry.register
class TextBlock(BaseLogicBlock):
    def __init__(self, type_id="doc.text", default_name="Text", category="Dokumentacja", description="Free text for documentation"):
        super().__init__(type_id, default_name, category, description)
        self.width = 150
        self.height = 40
        self.properties["Text"] = "Enter text here"

        # Doc blocks don't execute logic and have no pins
        self.inputs = []
        self.outputs = []

    def evaluate(self):
        pass

@BlockRegistry.register
class NoteBlock(BaseLogicBlock):
    def __init__(self, type_id="doc.note", default_name="Note", category="Dokumentacja", description="Multiline note"):
        super().__init__(type_id, default_name, category, description)
        self.width = 200
        self.height = 80
        self.properties["Text"] = "Multiline\\nnote here"

        self.inputs = []
        self.outputs = []

    def evaluate(self):
        pass

@BlockRegistry.register
class SectionTitleBlock(BaseLogicBlock):
    def __init__(self, type_id="doc.section", default_name="Section Title", category="Dokumentacja", description="Large section title"):
        super().__init__(type_id, default_name, category, description)
        self.width = 300
        self.height = 50
        self.properties["Text"] = "SECTION TITLE"

        self.inputs = []
        self.outputs = []

    def evaluate(self):
        pass
