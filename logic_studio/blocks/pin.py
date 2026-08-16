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

    def connect(self, other_pin: 'Pin') -> bool:
        """Connect this pin to another pin if types/directions match."""
        if self.direction == other_pin.direction:
            return False # Cannot connect Input-Input or Output-Output

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
        return {
            "uuid": self.uuid,
            "name": self.name,
            "direction": "input" if self.direction == self.DIR_INPUT else "output",
            "data_type": self.data_type,
            "connections": self.connections
        }

    @classmethod
    def deserialize(cls, data: dict):
        direction = cls.DIR_INPUT if data.get("direction") == "input" else cls.DIR_OUTPUT
        pin = cls(data.get("name", ""), direction, data.get("data_type", cls.TYPE_ANY))
        pin.uuid = data.get("uuid", pin.uuid)
        pin.connections = data.get("connections", [])
        return pin
