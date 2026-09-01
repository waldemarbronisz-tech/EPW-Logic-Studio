import pytest
from PySide6.QtWidgets import QApplication
from logic_studio.ui.main_window import MainWindow
from logic_studio.blocks import register_builtin_blocks

import os
import json

def test_file_operations_and_export(qsettings):
    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    register_builtin_blocks()
    m = MainWindow(settings=qsettings)

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
    assert len(m.engine.program.execution_order) == 3

    from logic_studio.compiler.exporter import Exporter
    exporter = Exporter(m.project, m.engine.program.execution_order)
    runtime_data = exporter.export()

    assert "format" in runtime_data
    assert len(runtime_data["blocks"]) == 3

    # Save as temp file to verify
    m.project.save_to_file("temp_test.epwlogic")
    assert os.path.exists("temp_test.epwlogic")
    os.remove("temp_test.epwlogic")

def test_final_acceptance_project(qsettings):
    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    register_builtin_blocks()
    m = MainWindow(settings=qsettings)

    test_proj = os.path.abspath("examples/EPW_LOGIC_FINAL_UI_TEST.epwlogic")
    assert os.path.exists(test_proj)

    m.stop_simulation()
    m.scene.clear()
    from logic_studio.core.project import Project
    m.project = Project.load_from_file(test_proj)
    m.engine.project = m.project
    m.current_file = test_proj
    m._reconstruct_scene()

    # 2 docs + 2 DI + 1 AND + 1 DO = 6 blocks
    assert len(m.project.blocks) == 6

    m.compile_project()
    # Exclude docs from execution order
    assert len(m.engine.program.execution_order) == 4

    # Check if simulation handles execution order properly
    m.start_simulation()
    m.engine.step()
    m.stop_simulation()

def test_headless_engine_no_qt():
    import sys
    import subprocess

    # Run a python process that imports ExecutionEngine and blocks,
    # and asserts that 'PySide6' is not in sys.modules.
    script = """
import sys
from logic_studio.engine.execution import ExecutionEngine
from logic_studio.compiler.core import Compiler
from logic_studio.core.project import Project
from logic_studio.blocks.logic_gates import AndGate

assert 'PySide6' not in sys.modules, "PySide6 was imported!"
assert 'logic_studio.ui' not in sys.modules, "UI package was imported!"
"""

    with open('test_headless_import.py', 'w') as f:
        f.write(script)

    res = subprocess.run([sys.executable, 'test_headless_import.py'], capture_output=True, text=True)
    assert res.returncode == 0, f"Headless import test failed: {res.stderr}"

    os.remove('test_headless_import.py')
