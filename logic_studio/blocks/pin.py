import uuid

class Pin:
    DIR_INPUT = 0
    DIR_OUTPUT = 1

    TYPE_DIGITAL = "Digital"
    TYPE_ANALOG = "Analog"
    TYPE_INTEGER = "Integer"
    TYPE_FLOAT = "Float"
    TYPE_BOOLEAN = "Boolean"
    TYPE_STRING = "String"
    TYPE_ANY = "Any"

    def __init__(self, name: str, direction: int, data_type: str = TYPE_ANY):
        self.uuid: str = str(uuid.uuid4())
        self.name: str = name
        self.direction: int = direction
        self.data_type: str = data_type

        # Connections hold UUIDs of the connected pins
        self.connections: list[str] = []

        self.value = None # For simulation/runtime

        # UI-only metadata: highlighted in the element preview panel (§6) as
        # "istotne dla bezpieczeństwa". Not set by any block today — ready
        # for use once the Zabezpieczenia * block categories exist.
        self.safety_relevant: bool = False

        # feat/editor-modes-and-geometry §2: an explicitly disabled input is
        # EXCLUDED from the block's own evaluate() entirely — not fed a
        # default value (True for AND, False for OR, ...), which would be
        # an implicit, easy-to-misread rule that differs per block type.
        # Exclusion is unambiguous regardless of what kind of block it is.
        # Only meaningful for an INPUT pin with no connection (§2.2 — you
        # must remove a wire before disabling the port it lands on) and
        # only on block types that opt in (BaseLogicBlock.
        # allows_disabled_inputs, §2.4) — multi-input logic gates only.
        self.disabled: bool = False

    def connect(self, other_pin: 'Pin') -> bool:
        """Connect this pin to another pin if types/directions match."""
        if self.direction == other_pin.direction:
            return False # Cannot connect Input-Input or Output-Output

        # Identify which is input and which is output
        input_pin = self if self.direction == self.DIR_INPUT else other_pin
        output_pin = self if self.direction == self.DIR_OUTPUT else other_pin

        # Enforce single driver: An input pin can only have ONE source
        if len(input_pin.connections) > 0 and output_pin.uuid not in input_pin.connections:
            return False

        # Strict type checking: prevent connecting BOOL to REAL/INT directly
        # Allow connecting ANY to anything, but specific types must match.
        if self.data_type != self.TYPE_ANY and other_pin.data_type != self.TYPE_ANY:
            if self.data_type != other_pin.data_type:
                return False

        if other_pin.uuid not in self.connections:
            self.connections.append(other_pin.uuid)
            other_pin.connections.append(self.uuid)
        return True

    def disconnect(self, other_pin: 'Pin'):
        if other_pin.uuid in self.connections:
            self.connections.remove(other_pin.uuid)
        if self.uuid in other_pin.connections:
            other_pin.connections.remove(self.uuid)

    def serialize(self) -> dict:
        # Convert internal UI types to CANONICAL RUNTIME TYPES
        type_mapping = {
            self.TYPE_BOOLEAN: "BOOL",
            self.TYPE_FLOAT: "REAL",
            self.TYPE_INTEGER: "DINT",
            self.TYPE_STRING: "STRING"
        }
        canonical_type = type_mapping.get(self.data_type, "ANY")
        return {
            "uuid": self.uuid,
            "name": self.name,
            "direction": "input" if self.direction == self.DIR_INPUT else "output",
            "data_type": canonical_type,
            "connections": self.connections,
            "disabled": self.disabled,
        }

    @classmethod
    def deserialize(cls, data: dict):
        direction = cls.DIR_INPUT if data.get("direction") == "input" else cls.DIR_OUTPUT

        # Convert CANONICAL RUNTIME TYPES back to internal UI types
        type_str = data.get("data_type", "ANY")
        reverse_mapping = {
            "BOOL": cls.TYPE_BOOLEAN,
            "REAL": cls.TYPE_FLOAT,
            "DINT": cls.TYPE_INTEGER,
            "INT": cls.TYPE_INTEGER,
            "STRING": cls.TYPE_STRING,
            "TIME": cls.TYPE_INTEGER # We treat time as ms int internally for now
        }
        internal_type = reverse_mapping.get(type_str, type_str) # fallback to original if unknown

        pin = cls(data.get("name", ""), direction, internal_type)
        pin.uuid = data.get("uuid", pin.uuid)
        pin.connections = data.get("connections", [])
        pin.disabled = bool(data.get("disabled", False))  # back-compat: absent = False
        return pin
