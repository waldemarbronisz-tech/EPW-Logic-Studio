class IOProvider:
    """Abstract interface for hardware IO interactions."""
    def read_digital_input(self, address: str) -> bool:
        raise NotImplementedError()

    def write_digital_output(self, address: str, value: bool):
        raise NotImplementedError()

    def read_digital_output(self, address: str) -> bool:
        raise NotImplementedError()

    def read_analog_input(self, address: str) -> float:
        raise NotImplementedError()

    def write_analog_output(self, address: str, value: float):
        raise NotImplementedError()

class SimulationIOProvider(IOProvider):
    """Memory-backed IO for headless testing and Logic Studio GUI simulation."""
    def __init__(self):
        self.input_image = {
            "digital": {},
            "analog": {}
        }
        self.output_image = {
            "digital": {},
            "analog": {}
        }

    def read_digital_input(self, address: str) -> bool:
        return self.input_image["digital"].get(address, False)

    def write_digital_output(self, address: str, value: bool):
        self.output_image["digital"][address] = value

    def read_digital_output(self, address: str) -> bool:
        return self.output_image["digital"].get(address, False)

    def read_analog_input(self, address: str) -> float:
        return self.input_image["analog"].get(address, 0.0)

    def write_analog_output(self, address: str, value: float):
        self.output_image["analog"][address] = value

    def set_digital_input(self, address: str, value: bool):
        self.input_image["digital"][address] = value

    def set_analog_input(self, address: str, value: float):
        self.input_image["analog"][address] = value
