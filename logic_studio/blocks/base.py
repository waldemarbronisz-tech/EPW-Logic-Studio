import uuid

class BaseLogicBlock:
    def __init__(self, type_id: str, default_name: str, category: str, description: str = ""):
        self.uuid: str = str(uuid.uuid4())
        self.type_id: str = type_id
        self.display_name: str = default_name # instance_name
        self.category: str = category
        self.description: str = description

        # Position on canvas
        self.x: float = 0.0
        self.y: float = 0.0

        # Size
        self.width: float = 120.0
        self.height: float = 80.0

        # I/O Pins
        self.inputs: list = []  # List of Pin objects
        self.outputs: list = [] # List of Pin objects

        # Basic properties
        self.execution_state: str = "Idle"
        self.execution_priority: int = 1
        self.color: str = "#C0C0C0"  # Classic Win98 grey
        self.visibility: bool = True
        self.enabled: bool = True

        # Read-only UI display state. Blocks may WRITE their current value here for
        # panels to show, but must never READ it back as their own logic state —
        # own state belongs in plain instance fields (e.g. self._count, self._memory)
        # so it survives ExecutionEngine.start()/stop() clearing this dict.
        self.simulation_state: dict = {}

        # True for blocks with no logic inputs (DI, constants, system signals, ...):
        # the ExecutionEngine evaluates these before the rest of the graph, once per
        # scan, so their output is available to every downstream block in that scan.
        self.is_source: bool = False

        # Search metadata only — never serialized, never edited by the user.
        # Polish synonyms so the library search (ui/panels/library.py) finds a
        # block by what an engineer actually types, not just its type_id/name.
        self.aliases: list = []

        # feat/editor-modes-and-geometry §2.4: whether this block permits
        # disabling one of its own inputs (Pin.disabled) at all — False for
        # everything except multi-input logic gates (LogicGateBase sets
        # this to True for 2+ input gates specifically; see its __init__).
        # Disabling an input on a block that doesn't allow it is a compile
        # ERROR (compiler/validator.py), not silently accepted.
        self.allows_disabled_inputs: bool = False

        # Extensible properties mapped by string key. Every block gets "Tag"
        # (its schematic designation, e.g. "C1", "Q_I>1") and "Comment" (a
        # short description of what it does) — the first two fields an
        # engineer fills in after placing a block (see feat/block-rendering-
        # library §3.1). Some IO blocks (Virtual IN/OUT, system signals) also
        # use "Tag" for their own HMI/network identifier — that predates this
        # field and is left as-is; for every other block "Tag" starts empty.
        self.properties: dict = {
            "Address": "",
            "Tag": "",
            "Comment": ""
        }

    def update_property(self, key: str, value: str):
        """Update property, casting to correct type if necessary."""
        if key in self.properties:
            # Simple type inference for Phase 4/5
            if isinstance(self.properties[key], bool):
                self.properties[key] = value.lower() in ["true", "1", "t", "yes", "y"]
            elif isinstance(self.properties[key], int) and not isinstance(self.properties[key], bool):
                try:
                    self.properties[key] = int(value)
                except ValueError:
                    pass
            elif isinstance(self.properties[key], float):
                try:
                    self.properties[key] = float(value)
                except ValueError:
                    pass
            else:
                self.properties[key] = value

        elif key == "Name":
            self.display_name = value
        elif key == "Description":
            self.description = value

    def serialize(self) -> dict:
        """Serialize block to a dictionary for JSON."""
        return {
            "uuid": self.uuid,
            "type_id": self.type_id,
            "display_name": self.display_name, # instance_name
            "category": self.category,
            "description": self.description,
            "position": {"x": self.x, "y": self.y},
            "size": {"width": self.width, "height": self.height},
            "inputs": [pin.serialize() for pin in self.inputs],
            "outputs": [pin.serialize() for pin in self.outputs],
            "execution_state": self.execution_state,
            "execution_priority": self.execution_priority,
            "color": self.color,
            "visibility": self.visibility,
            "enabled": self.enabled,
            "properties": self.properties
        }

    @classmethod
    def deserialize(cls, data: dict):
        """Reconstruct block from JSON dict. Overridden by subclasses."""
        # type_id must match the class definition. display_name handles instance_name loading.
        block = cls() # Subclasses handle their own static type_id, category, description
        if "display_name" in data:
            block.display_name = data["display_name"]

        block.uuid = data.get("uuid", block.uuid)
        pos = data.get("position", {"x": 0.0, "y": 0.0})
        block.set_position(pos["x"], pos["y"])
        size = data.get("size", {"width": 120.0, "height": 80.0})
        block.width = size["width"]
        block.height = size["height"]
        block.execution_priority = data.get("execution_priority", 1)
        block.color = data.get("color", "#E0E0E0")
        block.properties = data.get("properties", {}).copy() # Ensure copy
        # Pin deserialization is handled by the project loader
        return block

    def clone(self, preserve_uuid=False):
        """Creates a copy of the block."""
        new_block = self.__class__()
        if preserve_uuid:
            new_block.uuid = self.uuid
        new_block.display_name = self.display_name
        new_block.width = self.width
        new_block.height = self.height
        new_block.color = self.color
        new_block.properties = self.properties.copy()
        new_block.type_id = self.type_id # MUST PRESERVE TYPE ID explicitly

        from logic_studio.blocks.pin import Pin

        # Pins are cloned into fresh objects (never shared) to avoid mutable-state
        # aliasing between the original and the copy. When preserve_uuid is set
        # (isolating a CompiledProgram from the UI project), pin UUIDs and their
        # `connections` lists — which reference OTHER pins' UUIDs — are copied
        # verbatim, because GraphBuilder's execution_order is keyed by those UUIDs.
        # disabled/negated (feat/editor-modes-and-geometry §2/§8) are
        # configuration of the PIN ITSELF, not tied to a specific wire —
        # copied unconditionally, unlike uuid/connections which only make
        # sense to preserve for the isolated-CompiledProgram case.
        new_block.inputs = []
        for p in self.inputs:
            new_p = Pin(p.name, p.direction, p.data_type)
            new_p.disabled = p.disabled
            if preserve_uuid:
                new_p.uuid = p.uuid
                new_p.connections = list(p.connections)
            new_block.inputs.append(new_p)

        new_block.outputs = []
        for p in self.outputs:
            new_p = Pin(p.name, p.direction, p.data_type)
            if preserve_uuid:
                new_p.uuid = p.uuid
                new_p.connections = list(p.connections)
            new_block.outputs.append(new_p)

        new_block.simulation_state = self.simulation_state.copy()

        return new_block

    def evaluate(self, engine=None):
        """Execute block logic. Overridden by subclasses."""
        pass

    def _active_inputs(self) -> list:
        """Input pins participating in evaluate() — every input EXCEPT one
        explicitly disabled (feat/editor-modes-and-geometry §2). A disabled
        input is excluded from the block's own logic entirely, not fed an
        implicit default value; blocks that allow disabling (multi-input
        logic gates, see LogicGateBase) should loop over this instead of
        self.inputs directly."""
        return [p for p in self.inputs if not p.disabled]

    def reset_runtime_state(self):
        """Reset block to cold deterministic state. Overridden by subclasses."""
        pass

    def validate(self) -> list:
        """Validate block configuration. Returns list of errors."""
        errors = []
        if not self.enabled:
            return errors

        for pin in self.inputs:
            # Depending on strictness, check if connected
            pass

        return errors

    def set_position(self, x: float, y: float):
        self.x = x
        self.y = y
