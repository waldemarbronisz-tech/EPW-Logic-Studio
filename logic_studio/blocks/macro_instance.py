"""MacroInstanceBlock (feat/macro-blocks) — a placed instance of a user-
defined macro. See core/macros.py's module docstring for why this can't be
a normal BlockRegistry entry: its pin layout is project data (however many
inputs/outputs its own definition declares), not something a single fixed
Python class constructor could represent. Never registered via
@BlockRegistry.register — core/project.py's deserialize() and
ui/canvas/scene.py resolve this class directly via the "macro." type_id
prefix (core/macros.py::macro_def_id()) instead.
"""
from logic_studio.blocks.base import BaseLogicBlock
from logic_studio.blocks.pin import Pin

CATEGORY = "Makrobloki"


class MacroInstanceBlock(BaseLogicBlock):
    # feat/macro-blocks: `def_id` is NOT listed here — it's fully encoded
    # in `type_id` ("macro.<def_id>", restored via the deserialize()
    # override below, itself the "one deliberate, narrow exception" to
    # BaseLogicBlock.deserialize()'s own rule that type_id is never
    # restored from a file — see that override's docstring) rather than
    # duplicated as a second, independently-serialized field that could
    # drift from it.
    _TRANSIENT_FIELDS = BaseLogicBlock._TRANSIENT_FIELDS + ("def_id",)

    def __init__(self, def_id: str = "", default_name: str = "Makroblok"):
        type_id = f"macro.{def_id}" if def_id else "macro."
        super().__init__(type_id, default_name, CATEGORY, "Blok użytkownika (makroblok)")
        self.def_id = def_id
        self.color = "#6A4FB3"  # distinct from every built-in category, matches system.signal's precedent of a category-specific color
        self.width = 140.0
        self.height = 100.0

    def configure(self, definition: dict):
        """Builds this instance's ACTUAL pins from a macro definition dict
        (core/macros.py's shape) — called once, right after construction,
        by whichever code path just created a genuinely new instance
        ("Utwórz makroblok" / placing an existing one from the library),
        or is deserializing an old one (see deserialize() below — that
        path builds untyped placeholder pins instead, sized only from the
        instance's OWN saved data, deliberately never consulting the live
        definition; see its own docstring for why)."""
        self.display_name = definition.get("name", self.display_name)
        self.inputs = [
            Pin(p.get("label", p.get("pin_name", "")), Pin.DIR_INPUT, p.get("data_type", Pin.TYPE_BOOLEAN))
            for p in definition.get("input_pins", [])
        ]
        self.outputs = [
            Pin(p.get("label", p.get("pin_name", "")), Pin.DIR_OUTPUT, p.get("data_type", Pin.TYPE_BOOLEAN))
            for p in definition.get("output_pins", [])
        ]

    @classmethod
    def deserialize(cls, data: dict):
        """Overrides BaseLogicBlock.deserialize(): builds this instance's
        pins directly from its OWN saved "inputs"/"outputs" lists (every
        block, macro instances included, already serializes its full pin
        list like any other) via Pin.deserialize() — which decodes
        name/data_type from that same data in one shot — rather than
        consulting project.settings["macro_definitions"] at all. The
        generic per-block loop in Project.deserialize() doesn't thread a
        `project` through this classmethod (and structurally can't:
        BaseLogicBlock.deserialize() is shared by every registered block
        type, none of which need one) — and doesn't need to: a saved
        instance's own pins are already a complete, correct record of what
        it looked like at save time. A resync against a definition that
        changed shape SINCE this instance was last saved is deliberately
        not this method's job; see ARCHITECTURE.md's macro-blocks
        section."""
        block = super().deserialize(data)
        # BaseLogicBlock.deserialize() deliberately never restores type_id
        # from `data` (see its own docstring — correct for every block
        # whose type_id is fixed by its class). Wrong for this one, whose
        # type_id ENCODES which definition it's an instance of — the one
        # deliberate, narrow exception to that rule.
        type_id = data.get("type_id", block.type_id)
        block.type_id = type_id
        block.def_id = type_id[len("macro."):] if type_id.startswith("macro.") else ""

        block.inputs = [Pin.deserialize(p) for p in data.get("inputs", [])]
        block.outputs = [Pin.deserialize(p) for p in data.get("outputs", [])]
        return block

    def clone(self, preserve_uuid=False):
        new_block = super().clone(preserve_uuid=preserve_uuid)
        new_block.def_id = self.def_id
        return new_block
