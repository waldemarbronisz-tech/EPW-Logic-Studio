from logic_studio.core.project import Project
from logic_studio.compiler.core import Compiler
from logic_studio.engine.execution import ExecutionEngine
from logic_studio.engine.io_provider import SimulationIOProvider
from logic_studio.engine.time_provider import SimulationTimeProvider
from logic_studio.blocks.io_blocks import DigitalInputBlock, DigitalOutputBlock
from logic_studio.blocks.logic_gates import NotGate

def test_isolation():
    project = Project()
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

    # Run once
    io.set_digital_input("ELA01.DI01", False)
    engine.step()

    assert engine.get_block_state(do.uuid).simulation_state.get("sim_value") is True

    # Mutate UI project
    no.properties["Name"] = "MUTATED"
    di.properties["Address"] = "ELA02.DI02"

    # Verify runtime is unaffected
    io.set_digital_input("ELA01.DI01", True)
    # DI block uses Address property to lookup IO, so it checks ELA01.DI01.

    engine.step()

    # ELA01.DI01 -> True -> NOT -> False -> DO -> False
    assert engine.get_block_state(do.uuid).simulation_state.get("sim_value") is False
    assert engine.io.read_digital_output("ADA01.DO01") == False
    assert io.output_image["digital"].get("ADA01.DO01") == False
    assert engine.get_block_state(no.uuid).properties.get("Name") != "MUTATED"

    # Recompile
    res2 = compiler.compile()
    if res2:
        engine.load_program(res2["program"])

    # Verify new runtime HAS mutations
    if res2:
        assert engine.get_block_state(no.uuid).properties.get("Name") == "MUTATED"

    print("test_isolation passed")

if __name__ == "__main__":
    test_isolation()
