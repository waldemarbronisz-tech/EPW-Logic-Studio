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

        # I/O Pins will be stored here. In future phase: Pin objects
        self.inputs: dict = {}
        self.outputs: dict = {}

        # Basic properties
        self.execution_state: str = "Idle"
        self.execution_priority: int = 1
        self.color: str = "#E0E0E0"  # Default industrial grey
        self.visibility: bool = True
        self.enabled: bool = True
        self.simulation_state: dict = {}

        # Extensible properties mapped by string key
        self.properties: dict = {}

    def serialize(self) -> dict:
        """Serialize block to a dictionary for JSON."""
        return {
            "uuid": self.uuid,
            "display_name": self.display_name,
            "category": self.category,
            "description": self.description,
            "position": {"x": self.x, "y": self.y},
            "inputs": self.inputs, # Expand when Pin class exists
            "outputs": self.outputs,
            "execution_state": self.execution_state,
            "execution_priority": self.execution_priority,
            "color": self.color,
            "visibility": self.visibility,
            "enabled": self.enabled,
            "simulation_state": self.simulation_state,
            "properties": self.properties
        }

    def set_position(self, x: float, y: float):
        self.x = x
        self.y = y
