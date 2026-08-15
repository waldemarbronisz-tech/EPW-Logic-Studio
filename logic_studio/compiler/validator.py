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

            # Future: Advanced Type validation can occur here (if generic Pin checking isn't strict enough)
