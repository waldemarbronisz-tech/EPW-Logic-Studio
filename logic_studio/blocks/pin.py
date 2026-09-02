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

    _TYPE_TO_CANONICAL = {
        TYPE_BOOLEAN: "BOOL",
        TYPE_FLOAT: "REAL",
        TYPE_INTEGER: "DINT",
        TYPE_STRING: "STRING",
    }
    _CANONICAL_TO_TYPE = {
        "BOOL": TYPE_BOOLEAN,
        "REAL": TYPE_FLOAT,
        "DINT": TYPE_INTEGER,
        "INT": TYPE_INTEGER,
        "STRING": TYPE_STRING,
        "TIME": TYPE_INTEGER,  # We treat time as ms int internally for now
    }

    # feat/clipboard-and-align §4.2: the value a DISABLED block's output pin
    # is forced to every scan (ExecutionEngine.step()) — defined and type-
    # appropriate, never None, so anything still reading it (a connection
    # left over from before the block was disabled) sees a sane value
    # instead of crashing or propagating an undefined state downstream.
    # False/0.0 for the two types §4.2 names explicitly (BOOL/REAL); the
    # remaining pin types get the same "falsy, defined" treatment for
    # consistency, and anything unrecognized falls back to False.
    _SAFE_DISABLED_DEFAULTS = {
        TYPE_BOOLEAN: False,
        TYPE_DIGITAL: False,
        TYPE_FLOAT: 0.0,
        TYPE_ANALOG: 0.0,
        TYPE_INTEGER: 0,
        TYPE_STRING: "",
    }

    def safe_default_value(self):
        """The value this pin should present while its owning block is
        disabled — see _SAFE_DISABLED_DEFAULTS above."""
        return self._SAFE_DISABLED_DEFAULTS.get(self.data_type, False)

    # feat/wire-modes-and-labels §0.1 — STRUCTURAL FIX for a bug that has now
    # bitten twice: serialize() gained a new field (first `connections`,
    # aliased instead of copied; then `disabled`, dropped entirely) and the
    # separately hand-written deserialize()/project-loader side didn't know
    # about it. The failure is silent — the file round-trips through
    # save/load looking fine, the field just quietly resets to its default.
    #
    # SERIALIZED_FIELDS is now the single source of truth: every field that
    # crosses save/load is named here exactly once, and serialize()/
    # deserialize() both walk this same list instead of each maintaining
    # their own hand-written enumeration that can drift out of sync with
    # the other. Adding a new persisted field means adding its name here —
    # nothing else to remember on the read side. `value` is deliberately
    # NOT listed: it's runtime/simulation-only (see __init__), never meant
    # to survive a save. test_pin_serialization.py's field-audit test
    # enforces that every other plain Pin attribute IS listed here, so an
    # attribute added without being added to this tuple fails loudly
    # instead of silently losing its persistence.
    SERIALIZED_FIELDS = (
        "uuid", "name", "direction", "data_type",
        "connections", "disabled", "safety_relevant",
    )

    # Attributes intentionally excluded from SERIALIZED_FIELDS — runtime-only
    # state that must never be written to / read back from a save file.
    # Kept explicit (rather than "everything not in SERIALIZED_FIELDS") so
    # the field-audit test can tell "deliberately transient" apart from
    # "someone forgot to list it".
    _TRANSIENT_FIELDS = ("value",)

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

    # ---- Per-field encode/decode (§0.1) ------------------------------------
    # Most SERIALIZED_FIELDS round-trip verbatim (a list field is still
    # copied, never aliased, even by the "identity" codec below). `direction`
    # and `data_type` are the two exceptions: the file format stores them as
    # CANONICAL RUNTIME TYPES/direction strings, not the raw internal
    # enum/UI-type value, so they need a real translation each way.

    @classmethod
    def _encode_direction(cls, value):
        return "input" if value == cls.DIR_INPUT else "output"

    @classmethod
    def _decode_direction(cls, value):
        return cls.DIR_INPUT if value == "input" else cls.DIR_OUTPUT

    @classmethod
    def _encode_data_type(cls, value):
        return cls._TYPE_TO_CANONICAL.get(value, "ANY")

    @classmethod
    def _decode_data_type(cls, value):
        return cls._CANONICAL_TO_TYPE.get(value, value)  # fallback to original if unknown

    @staticmethod
    def _identity_encode(value):
        return list(value) if isinstance(value, list) else value

    _identity_decode = _identity_encode

    # name/direction/data_type are constructor arguments (Pin has no no-arg
    # constructor) — a pin's own identity, fixed by whichever block
    # constructed it. Never blind-restored onto an already-constructed pin
    # (restore_fields, below); deserialize() applies them once, up front,
    # by constructing a fresh Pin with them instead.
    _IDENTITY_FIELDS = ("name", "direction", "data_type")

    @classmethod
    def _codec_for(cls, field):
        return {
            "direction": (cls._encode_direction, cls._decode_direction),
            "data_type": (cls._encode_data_type, cls._decode_data_type),
        }.get(field, (cls._identity_encode, cls._identity_decode))

    def serialize(self) -> dict:
        data = {}
        for field in self.SERIALIZED_FIELDS:
            encode, _ = self._codec_for(field)
            data[field] = encode(getattr(self, field))
        return data

    @classmethod
    def restore_fields(cls, pin: 'Pin', data: dict):
        """Applies every SERIALIZED_FIELDS value present in `data` onto an
        ALREADY-CONSTRUCTED pin — uuid/connections/disabled/... — never
        name/direction/data_type (_IDENTITY_FIELDS), which stay whatever the
        pin already has. Used by deserialize() itself (right after building
        a fresh Pin) and by Project.deserialize() (§0.1 — the project loader
        restores a block's own already-constructed pins from the saved
        per-pin dicts; hand-enumerating which fields to copy there is
        exactly the bug this refactor fixes, so it shares this one
        implementation instead of keeping its own list)."""
        for field in cls.SERIALIZED_FIELDS:
            if field in cls._IDENTITY_FIELDS:
                continue
            if field not in data:
                continue  # back-compat: absent -> whatever the pin already has
            _, decode = cls._codec_for(field)
            setattr(pin, field, decode(data[field]))

    @classmethod
    def deserialize(cls, data: dict):
        _, decode_direction = cls._codec_for("direction")
        _, decode_data_type = cls._codec_for("data_type")
        direction = decode_direction(data["direction"]) if "direction" in data else cls.DIR_INPUT
        data_type = decode_data_type(data["data_type"]) if "data_type" in data else cls.TYPE_ANY
        name = data.get("name", "")

        pin = cls(name, direction, data_type)
        cls.restore_fields(pin, data)
        return pin
