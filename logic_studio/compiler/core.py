import logging

class Compiler:
    """Orchestrates the process of converting Logic Studio project to Runtime JSON."""

    def __init__(self, project):
        self.project = project
        self.errors = []
        self.warnings = []

    def compile(self) -> dict:
        """Executes the compilation pipeline."""
        self.errors.clear()
        self.warnings.clear()
        self.last_execution_order = []
        self.status = "UNCOMPILED"

        # 1. Validation Stage
        from logic_studio.compiler.validator import Validator
        validator = Validator(self.project)
        validator.run(self.errors, self.warnings)

        if self.errors:
            self.status = "COMPILE_FAILED"
            return None # Abort on validation errors

        # 2. Dependency Graph and Execution Order (Topological Sort)
        from logic_studio.compiler.graph import GraphBuilder
        graph = GraphBuilder(self.project)
        execution_order = graph.build_and_sort(self.errors)

        if self.errors:
            self.status = "COMPILE_FAILED"
            return None

        # 3. Export Intermediate JSON
        self.last_execution_order = execution_order
        self.status = "COMPILED_VALID"
        from logic_studio.compiler.exporter import Exporter
        exporter = Exporter(self.project, execution_order)
        compiled_data = exporter.export()
        self.warnings.extend(exporter.warnings)

        # 4. Generate isolated CompiledProgram for the ExecutionEngine
        from logic_studio.engine.program import CompiledProgram
        # We need true isolated blocks. deserialize creates fresh instances
        project_json = self.project.serialize()
        from logic_studio.core.project import Project
        isolated_project = Project.deserialize(project_json)

        # Resolve each AI block's analog point range once, here, since the
        # ExecutionEngine/CompiledProgram deliberately never holds a live
        # Project reference (see AUDIT_REPORT.md §2.1). Validator has already
        # confirmed the address exists with direction="input".
        from logic_studio.core.device_model import DeviceModel
        for block in isolated_project.blocks:
            if block.type_id == "input.ai" and hasattr(block, 'set_range'):
                point = DeviceModel.get_analog_point(self.project, block.properties.get("Address", ""))
                if point:
                    block.set_range(point.get("min"), point.get("max"))

        # In serialize/deserialize, UUIDs are fully preserved, so execution_order matches
        program = CompiledProgram(
            blocks=isolated_project.blocks,
            execution_order=execution_order,
            cycle_time_ms=self.project.settings.get("cycle_time_ms", 100)
        )

        compiled_data["program"] = program

        return compiled_data
