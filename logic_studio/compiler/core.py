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
        return exporter.export()
