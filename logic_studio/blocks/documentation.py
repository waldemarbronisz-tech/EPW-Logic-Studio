from logic_studio.blocks.base import BaseLogicBlock
from logic_studio.blocks.registry import BlockRegistry

# Shared search aliases for every documentation block type (§9.6).
DOC_ALIASES = ["opis", "komentarz", "tekst", "tytuł"]

# feat/wire-detour-and-text-size §B1: the "Rozmiar tekstu" property key —
# " (pkt)" suffix so ui/panels/property_grid.py's own unit-suffix
# convention (_split_unit()) shows it as a "pkt"-suffixed spinbox
# automatically, the same way every other unit-bearing property already
# does, no per-property UI code needed here. Range (§B1: 6-48) is
# enforced in property_grid.py's own editor construction, not here —
# this module has no UI dependency and shouldn't gain one just for a
# min/max pair.
TEXT_SIZE_KEY = "Rozmiar tekstu (pkt)"
_TEXT_SIZE_DESCRIPTION = "Rozmiar czcionki tekstu na schemacie, w punktach (6-48)."

@BlockRegistry.register
class TextBlock(BaseLogicBlock):
    PROPERTY_DESCRIPTIONS = {
        "Text": "Dowolny tekst wyświetlany na schemacie.",
        TEXT_SIZE_KEY: _TEXT_SIZE_DESCRIPTION,
    }

    def __init__(self, type_id="doc.text", default_name="Text", category="Dokumentacja", description="Dowolny tekst na schemacie, bez wpływu na logikę."):
        super().__init__(type_id, default_name, category, description)
        self.aliases = list(DOC_ALIASES)
        self.width = 150
        self.height = 40
        self.properties["Text"] = "Enter text here"
        # feat/wire-detour-and-text-size §B1: 9 matches the font size this
        # block type has always painted at -- ui/canvas/style.py's own
        # FONT_SIZE_DOC_TEXT, read directly from that module's current
        # value rather than guessed. NOT imported from there: this module
        # (like every logic_studio/blocks/*.py file) must stay importable,
        # and its blocks constructible, with zero PySide6/logic_studio.ui
        # dependency -- a headless engine/compiler process reconstructs
        # every block type on project load, doc blocks included, and must
        # never pull in Qt just to do that (tests/test_acceptance.py::
        # test_headless_engine_no_qt).
        self.properties[TEXT_SIZE_KEY] = 9

        # Doc blocks don't execute logic and have no pins
        self.inputs = []
        self.outputs = []

    def evaluate(self, engine=None):
        pass

@BlockRegistry.register
class NoteBlock(BaseLogicBlock):
    PROPERTY_DESCRIPTIONS = {
        "Text": "Wielowierszowa notatka wyświetlana na schemacie.",
        TEXT_SIZE_KEY: _TEXT_SIZE_DESCRIPTION,
    }

    def __init__(self, type_id="doc.note", default_name="Note", category="Dokumentacja", description="Wielowierszowa notatka na schemacie, bez wpływu na logikę."):
        super().__init__(type_id, default_name, category, description)
        self.aliases = list(DOC_ALIASES)
        self.width = 200
        self.height = 80
        # Was "Multiline\\nnote here" (a literal backslash-n, not a newline)
        # before this PR — fixed (§6.7).
        self.properties["Text"] = "Multiline\nnote here"
        # §B1: matches ui/canvas/style.py's own FONT_SIZE_DOC_NOTE — see
        # TextBlock's own comment above for why this isn't imported.
        self.properties[TEXT_SIZE_KEY] = 8

        self.inputs = []
        self.outputs = []

    def evaluate(self, engine=None):
        pass

@BlockRegistry.register
class SectionTitleBlock(BaseLogicBlock):
    PROPERTY_DESCRIPTIONS = {
        "Text": "Treść nagłówka sekcji.",
        TEXT_SIZE_KEY: _TEXT_SIZE_DESCRIPTION,
    }

    def __init__(self, type_id="doc.section", default_name="Section Title", category="Dokumentacja", description="Duży nagłówek sekcji schematu, bez wpływu na logikę."):
        super().__init__(type_id, default_name, category, description)
        self.aliases = list(DOC_ALIASES)
        self.width = 300
        self.height = 50
        self.properties["Text"] = "SECTION TITLE"
        # §B1: matches ui/canvas/style.py's own FONT_SIZE_DOC_SECTION —
        # see TextBlock's own comment above for why this isn't imported.
        self.properties[TEXT_SIZE_KEY] = 14

        self.inputs = []
        self.outputs = []

    def evaluate(self, engine=None):
        pass
