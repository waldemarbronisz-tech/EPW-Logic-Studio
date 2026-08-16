import pytest
from PySide6.QtWidgets import QApplication
from logic_studio.ui.main_window import MainWindow
from logic_studio.blocks import register_builtin_blocks

import os

def test_e2e_simulation_loop():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    register_builtin_blocks()
    m = MainWindow()

    # 1. Start clean
    m.scene.clear()

    # 2. Add blocks
    m.scene.add_block_from_library('DI', 0, 0)
    m.scene.add_block_from_library('NOT', 100, 0)
    m.scene.add_block_from_library('DO', 200, 0)

    # Get blocks
    di = m.project.blocks[0]
    no = m.project.blocks[1]
    do = m.project.blocks[2]

    # 3. Configure
    di.update_property("Address", "ELA1")
    do.update_property("Address", "ADA1")
    no.update_property("Name", "NEGATE_TEST")

    # 4. Connect
    di.outputs[0].connect(no.inputs[0])
    no.outputs[0].connect(do.inputs[0])

    # 5. Compile
    m.compile_project()
    assert len(m.engine.execution_order) == 3

    # 6. Simulate step 1
    # Mocking ELA1 input to False
    m.simulation_panel.ela_boxes[0].setChecked(False)
    m._update_simulation_panel() # Push UI state to ELA block memory
    m.engine._tick() # Manual tick evaluates and propagates

    # Assert
    assert do.simulation_state.get("sim_value") == True # NOT False -> True

    # 7. Simulate step 2
    m.simulation_panel.ela_boxes[0].setChecked(True)
    m._update_simulation_panel() # Push UI state to ELA block memory
    m.engine._tick()

    # Assert
    assert do.simulation_state.get("sim_value") == False # NOT True -> False

    # Clean up
    # Force bypass prompt so test doesn't hang waiting for user to click Discard
    m.is_dirty = False
    m.close()
