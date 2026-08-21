import pytest
import os
import json
from PySide6.QtWidgets import QApplication
from logic_studio.ui.main_window import MainWindow
from logic_studio.blocks import register_builtin_blocks

def test_universal_library_integration():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    register_builtin_blocks()
    m = MainWindow()

    # 1. Instantiate blocks
    m.scene.add_block_from_library('virtual.input', 0, 0)
    m.scene.add_block_from_library('edge.rtrig', 150, 0)
    m.scene.add_block_from_library('const.real', 0, 150)
    m.scene.add_block_from_library('analog.scale', 150, 150)
    m.scene.add_block_from_library('analog.limit', 300, 150)

    # Find blocks safely
    def find_block(type_id):
        for b in m.project.blocks:
            if b.type_id == type_id:
                return b
        return None

    vi = find_block('virtual.input')
    rtrig = find_block('edge.rtrig')
    const_real = find_block('const.real')
    scale = find_block('analog.scale')
    limit = find_block('analog.limit')

    assert vi is not None
    assert rtrig is not None
    assert const_real is not None
    assert scale is not None
    assert limit is not None

    # 2. Configure Properties
    const_real.update_property("Value", "50.0")
    scale.update_property("Out Max", "1000.0")
    limit.update_property("Max", "800.0")

    # 3. Connection and Typing tests
    assert vi.outputs[0].connect(rtrig.inputs[0]) is True # Bool to Bool
    assert const_real.outputs[0].connect(scale.inputs[0]) is True # Float to Float
    assert scale.outputs[0].connect(limit.inputs[0]) is True # Float to Float

    # Invalid typing check
    assert const_real.outputs[0].connect(rtrig.inputs[0]) is False # Float to Bool should fail

    # 4. Compilation
    m.compile_project()
    assert len(m.engine.execution_order) == 5

    # 5. Simulation Execution
    # First tick
    vi.properties["Force Value"] = True # simulate active edge
    m.engine._tick()

    # Verify R_TRIG pulse is high on first scan
    assert rtrig.outputs[0].value is True

    # Verify Analog flow: Constant (50.0) -> Scale (100 in, 1000 out => 500.0) -> Limit (Max 800 => 500.0)
    assert scale.outputs[0].value == 500.0
    assert limit.outputs[0].value == 500.0

    # Second tick
    m.engine._tick()

    # Verify R_TRIG pulse goes low on second scan
    assert rtrig.outputs[0].value is False

    # 6. Save and Load
    export_path = "examples/EPW_LOGIC_BLOCKS_INTEGRATION_TEST.epwlogic"
    m.project.save_to_file(export_path)
    assert os.path.exists(export_path)

    # Load back
    m._open_project_headless(export_path)
    assert len(m.project.blocks) == 5

    # Verify states persisted
    const_real_loaded = None
    for b in m.project.blocks:
        if b.type_id == 'const.real':
            const_real_loaded = b
            break

    assert float(const_real_loaded.properties["Value"]) == 50.0

    # 7. Test Runtime Export explicitly for analog networks
    from logic_studio.compiler.exporter import Exporter
    runtime_data = Exporter(m.project, m.engine.execution_order).export()

    assert "format" in runtime_data
    assert len(runtime_data["blocks"]) == 5

    # Verify boolean parsing fix via BaseLogicBlock property engine
    vi.update_property("Force Value", "true")
    assert vi.properties["Force Value"] is True

    vi.update_property("Force Value", "0")
    assert vi.properties["Force Value"] is False

    # Ensure application doesn't block shutdown UI flows
    m.is_dirty = False
    m.close()
