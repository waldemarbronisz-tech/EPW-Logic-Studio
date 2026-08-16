import pytest
from PySide6.QtWidgets import QApplication
from logic_studio.ui.main_window import MainWindow
from logic_studio.blocks import register_builtin_blocks

import os
import json

def test_file_operations_and_export():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    register_builtin_blocks()
    m = MainWindow()

    # Simulate loading the examples project
    test_proj = os.path.abspath("examples/ENTRY_GATE_MINIMAL.epwlogic")
    assert os.path.exists(test_proj)

    # We bypass QFileDialog for automation
    m.stop_simulation()
    m.scene.clear()
    from logic_studio.core.project import Project
    m.project = Project.load_from_file(test_proj)
    m.engine.project = m.project
    m.current_file = test_proj
    m._reconstruct_scene()

    assert len(m.project.blocks) == 3
    assert len(m.scene.items()) > 0

    # Validate compile and runtime export bypass
    m.compile_project()
    assert len(m.engine.execution_order) == 3

    from logic_studio.compiler.exporter import Exporter
    exporter = Exporter(m.project, m.engine.execution_order)
    runtime_data = exporter.export()

    assert "version" in runtime_data
    assert len(runtime_data["blocks"]) == 3

    # Save as temp file to verify
    m.project.save_to_file("temp_test.epwlogic")
    assert os.path.exists("temp_test.epwlogic")
    os.remove("temp_test.epwlogic")
