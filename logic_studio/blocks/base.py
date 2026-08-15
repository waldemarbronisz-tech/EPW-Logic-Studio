import uuid

class BaseLogicBlock:
    def __init__(self, name: str, category: str, description: str = ""):
        self.uuid: str = str(uuid.uuid4())
        self.display_name: str = name
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
        self.simulation_state: dict = {}

        # Extensible properties mapped by string key
        self.properties: dict = {
            "Address": "",
            "Comment": ""
        }

    def update_property(self, key: str, value: str):
        """Update property, casting to correct type if necessary."""
        if key in self.properties:
            # Simple type inference for Phase 4
            if isinstance(self.properties[key], int):
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
            "display_name": self.display_name,
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
            "simulation_state": self.simulation_state,
            "properties": self.properties
        }

    @classmethod
    def deserialize(cls, data: dict):
        """Reconstruct block from JSON dict. Overridden by subclasses."""
        block = cls(data.get("display_name", ""), data.get("category", ""), data.get("description", ""))
        block.uuid = data.get("uuid", block.uuid)
        pos = data.get("position", {"x": 0.0, "y": 0.0})
        block.set_position(pos["x"], pos["y"])
        size = data.get("size", {"width": 120.0, "height": 80.0})
        block.width = size["width"]
        block.height = size["height"]
        block.execution_priority = data.get("execution_priority", 1)
        block.color = data.get("color", "#E0E0E0")
        block.properties = data.get("properties", {})
        # Pin deserialization is handled by the project loader
        return block

    def clone(self):
        """Creates a deep copy of the block with a new UUID."""
        new_block = self.__class__(self.display_name, self.category, self.description)
        new_block.width = self.width
        new_block.height = self.height
        new_block.color = self.color
        new_block.properties = self.properties.copy()

        # Adjust dynamic inputs/outputs lengths if needed
        # (This helps blocks with dynamic port counts)
        while len(new_block.inputs) < len(self.inputs):
            from logic_studio.blocks.pin import Pin
            p = self.inputs[len(new_block.inputs)]
            new_block.inputs.append(Pin(p.name, p.direction, p.data_type))

        # We don't clone UUID, position, or connections.
        return new_block

    def evaluate(self):
        """Execute block logic. Overridden by subclasses."""
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
