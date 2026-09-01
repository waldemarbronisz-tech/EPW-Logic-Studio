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
    m.scene.add_block_from_library('input.di', 0, 0)
    m.scene.add_block_from_library('logic.not', 100, 0)
    m.scene.add_block_from_library('output.do', 200, 0)

    # Get blocks
    di = m.project.blocks[0]
    no = m.project.blocks[1]
    do = m.project.blocks[2]

    # 3. Configure
    di.update_property("Address", "ELA01.DI01")
    do.update_property("Address", "ADA01.DO01")
    no.update_property("Name", "NEGATE_TEST")

    # 4. Connect
    di.outputs[0].connect(no.inputs[0])
    no.outputs[0].connect(do.inputs[0])

    # 5. Compile
    m.compile_project()
    assert len(m.engine.program.execution_order) == 3

    # 6. Simulate step 1
    # Mocking ELA1 input to False
    m.io_provider.set_digital_input("ELA01.DI01", False)
    m.engine.step() # Manual tick evaluates and propagates

    # Assert
    assert m.engine.get_block_state(do.uuid).simulation_state.get("sim_value") == True # NOT False -> True

    # 7. Simulate step 2
    m.io_provider.set_digital_input("ELA01.DI01", True)
    m.engine.step()

    # Assert
    assert m.engine.get_block_state(do.uuid).simulation_state.get("sim_value") == False # NOT True -> False

    # Clean up
    # Force bypass prompt so test doesn't hang waiting for user to click Discard
    m.is_dirty = False
    m.close()

def test_headless_fat():
    from logic_studio.core.project import Project
    from logic_studio.compiler.core import Compiler
    from logic_studio.engine.execution import ExecutionEngine
    from logic_studio.engine.io_provider import SimulationIOProvider
    from logic_studio.engine.time_provider import SimulationTimeProvider
    from logic_studio.blocks.io_blocks import DigitalInputBlock, DigitalOutputBlock
    from logic_studio.blocks.logic_gates import NotGate
    from logic_studio.blocks.timers import TON
    from logic_studio.blocks.memory import SR
    from logic_studio.blocks import register_builtin_blocks

    register_builtin_blocks()

    project = Project()

    # Create Program:
    # ELA01.DI01 -> NOT -> TON (200ms) -> SR -> ADA01.DO01

    di = DigitalInputBlock()
    di.properties["Address"] = "ELA01.DI01"

    no = NotGate()

    ton = TON()
    ton.properties["Preset (ms)"] = 200

    sr = SR()

    do = DigitalOutputBlock()
    do.properties["Address"] = "ADA01.DO01"

    # Connect
    di.outputs[0].connect(no.inputs[0])
    no.outputs[0].connect(ton.inputs[0])
    ton.outputs[0].connect(sr.inputs[0])
    sr.outputs[0].connect(do.inputs[0])

    project.add_block(di)
    project.add_block(no)
    project.add_block(ton)
    project.add_block(sr)
    project.add_block(do)

    # Compile
    compiler = Compiler(project)
    res = compiler.compile()
    assert res is not None, f"Compile failed: {compiler.errors}"

    # Setup headless execution
    io = SimulationIOProvider()
    time = SimulationTimeProvider()
    engine = ExecutionEngine(res.get("program"), io, time)
    engine.start()

    # Step 1: ELA is FALSE
    # NOT evaluates to TRUE
    # TON begins timing (but needs 200ms)
    io.set_digital_input("ELA01.DI01", False)
    engine.step()

    assert io.output_image["digital"].get("ADA01.DO01") in [False, None]

    # Step 2: Advance time 200ms. ELA still FALSE.
    # TON should complete and output TRUE.
    # SR should SET and output TRUE.
    # ADA should output TRUE.
    time.advance(200)
    engine.step()

    assert io.output_image["digital"].get("ADA01.DO01") is True

    # Step 3: Change ELA to TRUE.
    # NOT becomes FALSE.
    # TON resets to FALSE.
    # SR should retain its state (SET dominant, but since S is false and R is false, it holds).
    # ADA should remain TRUE.
    io.set_digital_input("ELA01.DI01", True)
    engine.step()

    assert io.output_image["digital"].get("ADA01.DO01") is True

def test_stop_drives_outputs_to_safe_state():
    """AUDIT_REPORT.md §0.1: stop() must NOT latch outputs at their last
    value — every output ever written this session goes to its safe state
    (digital False) in the IOProvider itself, not just in block memory."""
    from logic_studio.core.project import Project
    from logic_studio.compiler.core import Compiler
    from logic_studio.engine.execution import ExecutionEngine
    from logic_studio.engine.io_provider import SimulationIOProvider
    from logic_studio.engine.time_provider import SimulationTimeProvider
    from logic_studio.blocks.io_blocks import DigitalInputBlock, DigitalOutputBlock
    from logic_studio.blocks import register_builtin_blocks

    register_builtin_blocks()
    project = Project()

    di = DigitalInputBlock()
    di.properties["Address"] = "ELA01.DI01"
    do = DigitalOutputBlock()
    do.properties["Address"] = "ADA01.DO01"
    di.outputs[0].connect(do.inputs[0])

    project.add_block(di)
    project.add_block(do)

    compiler = Compiler(project)
    res = compiler.compile()
    assert res is not None

    io = SimulationIOProvider()
    engine = ExecutionEngine(res.get("program"), io, SimulationTimeProvider())
    engine.start()

    io.set_digital_input("ELA01.DI01", True)
    engine.step()
    assert io.output_image["digital"].get("ADA01.DO01") is True

    engine.stop()
    assert io.output_image["digital"].get("ADA01.DO01") is False

def test_fault_transition_drives_outputs_to_safe_state():
    """AUDIT_REPORT.md §0.1: a transition to FAULT (start() with no valid
    compiled program) must fail-safe outputs the same way stop() does."""
    from logic_studio.core.project import Project
    from logic_studio.compiler.core import Compiler
    from logic_studio.engine.execution import ExecutionEngine, ExecutionState
    from logic_studio.engine.io_provider import SimulationIOProvider
    from logic_studio.engine.time_provider import SimulationTimeProvider
    from logic_studio.blocks.io_blocks import DigitalInputBlock, DigitalOutputBlock
    from logic_studio.blocks import register_builtin_blocks

    register_builtin_blocks()
    project = Project()

    di = DigitalInputBlock()
    di.properties["Address"] = "ELA01.DI01"
    do = DigitalOutputBlock()
    do.properties["Address"] = "ADA01.DO01"
    di.outputs[0].connect(do.inputs[0])
    project.add_block(di)
    project.add_block(do)

    compiler = Compiler(project)
    res = compiler.compile()

    io = SimulationIOProvider()
    engine = ExecutionEngine(res.get("program"), io, SimulationTimeProvider())
    engine.start()
    io.set_digital_input("ELA01.DI01", True)
    engine.step()
    assert io.output_image["digital"].get("ADA01.DO01") is True

    # Force an invalid program, then attempt to (re)start -> FAULT.
    engine.program = None
    engine.start()
    assert engine.state == ExecutionState.FAULT
    assert io.output_image["digital"].get("ADA01.DO01") is False

def test_pause_does_not_touch_outputs():
    """AUDIT_REPORT.md §0.1: pause() freezes the scan, it must not fail-safe
    outputs the way stop()/FAULT do."""
    from logic_studio.core.project import Project
    from logic_studio.compiler.core import Compiler
    from logic_studio.engine.execution import ExecutionEngine
    from logic_studio.engine.io_provider import SimulationIOProvider
    from logic_studio.engine.time_provider import SimulationTimeProvider
    from logic_studio.blocks.io_blocks import DigitalInputBlock, DigitalOutputBlock
    from logic_studio.blocks import register_builtin_blocks

    register_builtin_blocks()
    project = Project()

    di = DigitalInputBlock()
    di.properties["Address"] = "ELA01.DI01"
    do = DigitalOutputBlock()
    do.properties["Address"] = "ADA01.DO01"
    di.outputs[0].connect(do.inputs[0])
    project.add_block(di)
    project.add_block(do)

    compiler = Compiler(project)
    res = compiler.compile()

    io = SimulationIOProvider()
    engine = ExecutionEngine(res.get("program"), io, SimulationTimeProvider())
    engine.start()
    io.set_digital_input("ELA01.DI01", True)
    engine.step()
    assert io.output_image["digital"].get("ADA01.DO01") is True

    engine.pause()
    assert io.output_image["digital"].get("ADA01.DO01") is True

def test_same_scan_input_fat():
    from logic_studio.core.project import Project
    from logic_studio.compiler.core import Compiler
    from logic_studio.engine.execution import ExecutionEngine
    from logic_studio.engine.io_provider import SimulationIOProvider
    from logic_studio.engine.time_provider import SimulationTimeProvider
    from logic_studio.blocks.io_blocks import DigitalInputBlock, DigitalOutputBlock
    from logic_studio.blocks.logic_gates import NotGate
    from logic_studio.blocks import register_builtin_blocks

    register_builtin_blocks()
    project = Project()

    # ELA01.DI01 -> NOT -> ADA01.DO01
    di = DigitalInputBlock()
    di.properties["Address"] = "ELA01.DI01"

    no = NotGate()

    do = DigitalOutputBlock()
    do.properties["Address"] = "ADA01.DO01"

    di.outputs[0].connect(no.inputs[0])
    no.outputs[0].connect(do.inputs[0])

    project.add_block(di)
    project.add_block(no)
    project.add_block(do)

    compiler = Compiler(project)
    res = compiler.compile()

    io = SimulationIOProvider()
    engine = ExecutionEngine(res.get("program"), io, SimulationTimeProvider())
    engine.start()

    # Set FALSE, execute ONE scan
    io.set_digital_input("ELA01.DI01", False)
    engine.step()

    # DO01 must be TRUE IMMEDIATELY after that scan
    assert io.output_image["digital"].get("ADA01.DO01") is True

    # Set TRUE, execute ONE scan
    io.set_digital_input("ELA01.DI01", True)
    engine.step()

    # DO01 must be FALSE IMMEDIATELY after that scan
    assert io.output_image["digital"].get("ADA01.DO01") is False

def test_stop_restart_fat():
    from logic_studio.core.project import Project
    from logic_studio.compiler.core import Compiler
    from logic_studio.engine.execution import ExecutionEngine
    from logic_studio.engine.io_provider import SimulationIOProvider
    from logic_studio.engine.time_provider import SimulationTimeProvider
    from logic_studio.blocks.io_blocks import DigitalInputBlock, DigitalOutputBlock
    from logic_studio.blocks.timers import TON
    from logic_studio.blocks.memory import SR
    from logic_studio.blocks import register_builtin_blocks

    register_builtin_blocks()
    project = Project()

    di = DigitalInputBlock()
    di.properties["Address"] = "ELA01.DI01"

    ton = TON()
    ton.properties["Preset (ms)"] = 200

    sr = SR()

    do = DigitalOutputBlock()
    do.properties["Address"] = "ADA01.DO01"

    di.outputs[0].connect(ton.inputs[0])
    ton.outputs[0].connect(sr.inputs[0])
    sr.outputs[0].connect(do.inputs[0])

    project.add_block(di)
    project.add_block(ton)
    project.add_block(sr)
    project.add_block(do)

    compiler = Compiler(project)
    res = compiler.compile()

    io = SimulationIOProvider()
    time = SimulationTimeProvider()
    engine = ExecutionEngine(res.get("program"), io, time)
    engine.start()

    io.set_digital_input("ELA01.DI01", True)
    engine.step()

    # Advance 200 to trigger TON and set SR
    time.advance(200)
    engine.step()
    assert io.output_image["digital"].get("ADA01.DO01") is True

    # STOP engine
    engine.stop()
    assert engine.state == "STOPPED"

    # Engine is stopped, outputs/pins should be wiped from runtime values
    # Actually IO Provider retains last written state until explicitly overwritten,
    # but block internal memory must be clean.
    assert sr.simulation_state.get("memory", False) is False
    assert ton.running is False
    assert ton.outputs[1].value is None

    # Restart
    engine.start()

    # Re-evaluate
    io.set_digital_input("ELA01.DI01", True)
    engine.step()

    # Because TON just started again, SR is not yet set, ADA01 should now be overwritten to False
    assert io.output_image["digital"].get("ADA01.DO01") is False
