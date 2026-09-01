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

            if block.type_id == "input.di":
                addr = block.properties.get("Address", "")
                if addr not in DeviceModel.get_ela_addresses():
                    errors.append(f"[{block.display_name}] Invalid DI Address: '{addr}'. Must be valid DI01 to DI32.")
            elif block.type_id == "output.do":
                addr = block.properties.get("Address", "")
                if addr not in DeviceModel.get_ada_addresses():
                    errors.append(f"[{block.display_name}] Invalid DO Address: '{addr}'. Must be valid DO01 to DO32.")
            elif block.type_id == "input.ai":
                # Analog points are project-defined, not fixed hardware channels
                # (AUDIT_REPORT.md §1) — the address must name a point with
                # direction="input" in project.settings["analog_points"].
                addr = block.properties.get("Address", "")
                if addr not in DeviceModel.get_analog_input_addresses(self.project):
                    errors.append(f"[{block.display_name}] Invalid AI Address: '{addr}'. Must match an analog point with direction=input.")
            elif block.type_id == "output.ao":
                addr = block.properties.get("Address", "")
                if addr not in DeviceModel.get_analog_output_addresses(self.project):
                    errors.append(f"[{block.display_name}] Invalid AO Address: '{addr}'. Must match an analog point with direction=output.")

        # 4. Duplicate Output Detection
        output_addresses = {}
        analog_output_addresses = {}
        analog_input_addresses = {}
        for block in blocks:
            if block.type_id == "output.do":
                addr = block.properties.get("Address", "")
                if addr in output_addresses:
                    errors.append(f"Multiple outputs assigned to address: {addr} ({output_addresses[addr]} and {block.display_name})")
                else:
                    output_addresses[addr] = block.display_name
            elif block.type_id == "output.ao":
                addr = block.properties.get("Address", "")
                if addr in analog_output_addresses:
                    errors.append(f"Multiple analog outputs assigned to address: {addr} ({analog_output_addresses[addr]} and {block.display_name})")
                else:
                    analog_output_addresses[addr] = block.display_name
            elif block.type_id == "input.ai":
                # Several blocks reading the same analog measurement is legal
                # (e.g. one for logic, one for a display) — warn, don't fail.
                addr = block.properties.get("Address", "")
                if addr in analog_input_addresses:
                    warnings.append(f"Multiple AI blocks read address: {addr} ({analog_input_addresses[addr]} and {block.display_name})")
                else:
                    analog_input_addresses[addr] = block.display_name
