from logic_studio.blocks.base import BaseLogicBlock
from logic_studio.blocks.registry import BlockRegistry

# Shared search aliases for every documentation block type (§9.6).
DOC_ALIASES = ["opis", "komentarz", "tekst", "tytuł"]

@BlockRegistry.register
class TextBlock(BaseLogicBlock):
    PROPERTY_DESCRIPTIONS = {"Text": "Dowolny tekst wyświetlany na schemacie."}

    def __init__(self, type_id="doc.text", default_name="Text", category="Dokumentacja", description="Dowolny tekst na schemacie, bez wpływu na logikę."):
        super().__init__(type_id, default_name, category, description)
        self.aliases = list(DOC_ALIASES)
        self.width = 150
        self.height = 40
        self.properties["Text"] = "Enter text here"

        # Doc blocks don't execute logic and have no pins
        self.inputs = []
        self.outputs = []

    def evaluate(self, engine=None):
        pass

@BlockRegistry.register
class NoteBlock(BaseLogicBlock):
    PROPERTY_DESCRIPTIONS = {"Text": "Wielowierszowa notatka wyświetlana na schemacie."}

    def __init__(self, type_id="doc.note", default_name="Note", category="Dokumentacja", description="Wielowierszowa notatka na schemacie, bez wpływu na logikę."):
        super().__init__(type_id, default_name, category, description)
        self.aliases = list(DOC_ALIASES)
        self.width = 200
        self.height = 80
        # Was "Multiline\\nnote here" (a literal backslash-n, not a newline)
        # before this PR — fixed (§6.7).
        self.properties["Text"] = "Multiline\nnote here"

        self.inputs = []
        self.outputs = []

    def evaluate(self, engine=None):
        pass

@BlockRegistry.register
class SectionTitleBlock(BaseLogicBlock):
    PROPERTY_DESCRIPTIONS = {"Text": "Treść nagłówka sekcji."}

    def __init__(self, type_id="doc.section", default_name="Section Title", category="Dokumentacja", description="Duży nagłówek sekcji schematu, bez wpływu na logikę."):
        super().__init__(type_id, default_name, category, description)
        self.aliases = list(DOC_ALIASES)
        self.width = 300
        self.height = 50
        self.properties["Text"] = "SECTION TITLE"

        self.inputs = []
        self.outputs = []

    def evaluate(self, engine=None):
        pass
