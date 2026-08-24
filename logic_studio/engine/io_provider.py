class IOProvider:
    """Abstract interface for hardware IO interactions."""
    def read_digital(self, address: str) -> bool:
        raise NotImplementedError()

    def write_digital(self, address: str, value: bool):
        raise NotImplementedError()

    def read_analog(self, address: str) -> float:
        raise NotImplementedError()

    def write_analog(self, address: str, value: float):
        raise NotImplementedError()

class SimulationIOProvider(IOProvider):
    """Memory-backed IO for headless testing and Logic Studio GUI simulation."""
    def __init__(self):
        self.digital_inputs = {}
        self.digital_outputs = {}
        self.analog_inputs = {}
        self.analog_outputs = {}

    def read_digital(self, address: str) -> bool:
        return self.digital_inputs.get(address, False)

    def write_digital(self, address: str, value: bool):
        self.digital_outputs[address] = value

    def read_analog(self, address: str) -> float:
        return self.analog_inputs.get(address, 0.0)

    def write_analog(self, address: str, value: float):
        self.analog_outputs[address] = value

    def set_digital_input(self, address: str, value: bool):
        self.digital_inputs[address] = value

    def set_analog_input(self, address: str, value: float):
        self.analog_inputs[address] = value
