class Validator:
    def __init__(self, project):
        self.project = project

    def run(self, errors: list, warnings: list):
        blocks = self.project.blocks

        if not blocks:
            warnings.append("Project contains no logic blocks.")
            return

        for block in blocks:
            # 1. Ask block to self-validate
            block_errors = block.validate()
            for err in block_errors:
                errors.append(f"[{block.display_name}] {err}")

            # 2. Pin Level Validation
            for pin in block.inputs:
                if not pin.connections:
                    warnings.append(f"[{block.display_name}] Input '{pin.name}' is unconnected.")

            # 3. Explicit IO Address Validation
            from logic_studio.core.device_model import DeviceModel

            if block.__class__.__name__ == "DigitalInputBlock":
                addr = block.properties.get("Address", "")
                if addr not in DeviceModel.get_ela_addresses():
                    errors.append(f"[{block.display_name}] Invalid DI Address: '{addr}'. Must be valid DI01 to DI32.")
            elif block.__class__.__name__ == "DigitalOutputBlock":
                addr = block.properties.get("Address", "")
                if addr not in DeviceModel.get_ada_addresses():
                    errors.append(f"[{block.display_name}] Invalid DO Address: '{addr}'. Must be valid DO01 to DO32.")

        # 4. Duplicate Output Detection
        output_addresses = {}
        for block in blocks:
            if block.__class__.__name__ == "DigitalOutputBlock":
                addr = block.properties.get("Address", "")
                if addr in output_addresses:
                    errors.append(f"Multiple outputs assigned to address: {addr} ({output_addresses[addr]} and {block.display_name})")
                else:
                    output_addresses[addr] = block.display_name
