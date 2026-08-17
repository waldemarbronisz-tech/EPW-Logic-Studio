import pytest
import os
from PySide6.QtWidgets import QApplication
from logic_studio.ui.main_window import MainWindow
from logic_studio.blocks import register_builtin_blocks

def test_priority_a_audit():
    # 9. REGISTRY / 1. LIBRARY
    # Verify clean startup registration
    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    register_builtin_blocks()
    m = MainWindow()

    # Verify Library categories
    from logic_studio.blocks.registry import BlockRegistry
    cats = BlockRegistry.get_categories()
    assert "Wejścia / Wyjścia" in cats
    assert "Inne" in cats
    assert "Liczniki" in cats
    # assert "Edges" in cats
    assert "Elementy Analogowe" in cats
    assert "Timery" in cats
    assert "Elementy Analogowe" in cats
    assert "Elementy Analogowe" in cats

    # 2. PLACEMENT
    m.scene.clear()

    # Network A
    m.scene.add_block_from_library("virtual.input", 0, 0)
    m.scene.add_block_from_library("edge.rtrig", 100, 0)
    m.scene.add_block_from_library("system.signal", 0, 100)
    m.scene.add_block_from_library("logic.and", 200, 0)
    m.scene.add_block_from_library("virtual.output", 300, 0)

    # Network B
    m.scene.add_block_from_library("const.real", 0, 200)
    m.scene.add_block_from_library("analog.scale", 100, 200)
    m.scene.add_block_from_library("analog.mov_avg", 200, 200)
    m.scene.add_block_from_library("analog.hysteresis", 300, 200)
    m.scene.add_block_from_library("timer.ton", 400, 200)
    m.scene.add_block_from_library("virtual.output", 500, 200)

    # Map blocks
    def get_block(index):
        return m.project.blocks[index]

    vi_a = get_block(0)
    rtrig = get_block(1)
    sys_sig = get_block(2)
    and_gate = get_block(3)
    vo_a = get_block(4)

    analog_src = get_block(5)
    scale = get_block(6)
    mov_avg = get_block(7)
    hyst = get_block(8)
    ton = get_block(9)
    vo_b = get_block(10)

    # 3. PROPERTIES
    vi_a.update_property("Tag", "VI.PULSE_REQUEST")
    assert vi_a.properties["Tag"] == "VI.PULSE_REQUEST"

    sys_sig.update_property("Tag", "SYSTEM.CORE_ONLINE")

    analog_src.update_property("Value", "5.0")
    assert float(analog_src.properties["Value"]) == 5.0

    scale.update_property("In Min", "0.0")
    scale.update_property("In Max", "10.0")
    scale.update_property("Out Min", "0.0")
    scale.update_property("Out Max", "100.0")

    hyst.update_property("High Threshold", "40.0")
    hyst.update_property("Low Threshold", "10.0")

    ton.update_property("Preset (ms)", "200") # 2 ticks

    # 4. CONNECTIONS
    # Network A
    assert vi_a.outputs[0].connect(rtrig.inputs[0]) is True
    assert rtrig.outputs[0].connect(and_gate.inputs[0]) is True
    assert sys_sig.outputs[0].connect(and_gate.inputs[1]) is True
    assert and_gate.outputs[0].connect(vo_a.inputs[0]) is True

    # Network B
    assert analog_src.outputs[0].connect(scale.inputs[0]) is True
    assert scale.outputs[0].connect(mov_avg.inputs[0]) is True
    assert mov_avg.outputs[0].connect(hyst.inputs[0]) is True
    assert hyst.outputs[0].connect(ton.inputs[0]) is True
    assert ton.outputs[0].connect(vo_b.inputs[0]) is True

    # 5. TYPE VALIDATION
    # Analog output to boolean input should fail
    assert scale.outputs[0].connect(vo_b.inputs[0]) is False

    # 6. SIMULATION
    m.compile_project()
    assert len(m.engine.execution_order) == 11

    # Tick 1: Pulse input high
    vi_a.properties["Force Value"] = True
    m.engine._tick()

    # Network A Checks
    assert sys_sig.outputs[0].value is True
    assert rtrig.outputs[0].value is True
    assert and_gate.outputs[0].value is True
    assert vo_a.simulation_state["sim_value"] is True

    # Network B Checks
    assert analog_src.outputs[0].value == 5.0
    assert scale.outputs[0].value == 50.0
    assert mov_avg.outputs[0].value == 50.0 # window fills
    assert hyst.outputs[0].value is True # 50 >= 40 High Threshold
    assert ton.outputs[0].value is False # Needs 200ms

    # Tick 2: Pulse goes low
    vi_a.properties["Force Value"] = False
    import time
    time.sleep(0.1) # Simulate real engine sleep delay for TON
    m.engine._tick()

    assert rtrig.outputs[0].value is False
    assert vo_a.simulation_state["sim_value"] is False
    assert ton.outputs[0].value is False # Only 100ms passed

    # Tick 3:
    time.sleep(0.1)
    m.engine._tick()

    assert ton.outputs[0].value is True # 200ms passed, Output goes high
    assert vo_b.simulation_state["sim_value"] is True

    # 10. EXAMPLE PROJECT / 7. SAVE OPEN
    save_path = "examples/EPW_LOGIC_PRIORITY_A_TEST.epwlogic"
    m.project.save_to_file(save_path)
    assert os.path.exists(save_path)

    # Reopen
    m._open_project_headless(save_path)
    assert len(m.project.blocks) == 11

    # Find scale
    loaded_scale = None
    for b in m.project.blocks:
        if b.type_id == "analog.scale":
            loaded_scale = b
            break

    assert loaded_scale is not None
    assert len(loaded_scale.inputs[0].connections) == 1 # still wired

    # 8. RUNTIME EXPORT
    from logic_studio.compiler.exporter import Exporter
    runtime_data = Exporter(m.project, m.engine.execution_order).export()

    assert "version" in runtime_data
    assert len(runtime_data["blocks"]) == 11
    # Check that scale block is in the runtime data
    assert loaded_scale.uuid in runtime_data["blocks"]

    m.is_dirty = False
    m.close()
