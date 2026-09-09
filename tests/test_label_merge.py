"""fix/wire-labels-and-project-integrity §A1/§A2 — compiler/label_merge.py.

The whole point of a Wire's label (feat/wire-labels) was to move a
signal to another part of the schematic without a physical wire all
the way across it. Before this module, the label was pure inert text —
this is what finally makes it do something, and the tests that prove
it does EXACTLY the same thing a direct wire would, no more, no less.
"""
import pytest

from logic_studio.blocks import register_builtin_blocks
from logic_studio.blocks.registry import BlockRegistry
from logic_studio.core.project import Project
from logic_studio.core.wire import Wire
from logic_studio.compiler.core import Compiler
from logic_studio.compiler.label_merge import (
    group_labeled_pins, merge_and_validate_labels, describe_label_groups,
)

register_builtin_blocks()


def _di(address="ELA01.DI01"):
    b = BlockRegistry.create_block("input.di")
    b.properties["Address"] = address
    return b


def _do(address="ADA01.DO01"):
    b = BlockRegistry.create_block("output.do")
    b.properties["Address"] = address
    return b


def _free_end_wire(pin, label, is_source: bool):
    w = Wire()
    if is_source:
        w.source_pin = pin.uuid
        w.free_end_dest = {"x": 0.0, "y": 0.0}
    else:
        w.dest_pin = pin.uuid
        w.free_end_source = {"x": 0.0, "y": 0.0}
    w.label = label
    return w


# ---- §A1: the acceptance test — identical execution_order & simulation ----

def _labeled_project():
    p = Project()
    di = _di()
    do = _do()
    p.add_block(di)
    p.add_block(do)
    p.add_wire(_free_end_wire(di.outputs[0], "Cmd", is_source=True))
    p.add_wire(_free_end_wire(do.inputs[0], "Cmd", is_source=False))
    return p, di, do


def _directly_wired_project():
    p = Project()
    di = _di()
    do = _do()
    p.add_block(di)
    p.add_block(do)
    di.outputs[0].connect(do.inputs[0])
    return p, di, do


def test_label_and_direct_wire_compile_to_the_same_execution_order():
    """§A1's own acceptance test. Blocks are added in the SAME order to
    both projects so uuids aren't a source of accidental difference —
    what's actually being proven is that label_merge.py produces the
    same Pin.connections-shaped graph GraphBuilder already knows how to
    sort, not a parallel notion of "connected" it has to special-case."""
    labeled_p, labeled_di, labeled_do = _labeled_project()
    direct_p, direct_di, direct_do = _directly_wired_project()

    labeled_res = Compiler(labeled_p).compile()
    direct_res = Compiler(direct_p).compile()
    assert labeled_res is not None
    assert direct_res is not None

    # uuids differ between the two separately-built projects -- compare
    # by POSITION (di first, do second) rather than raw uuid equality.
    labeled_order_types = [
        "input.di" if u == labeled_di.uuid else "output.do"
        for u in labeled_res["execution_order"]
    ]
    direct_order_types = [
        "input.di" if u == direct_di.uuid else "output.do"
        for u in direct_res["execution_order"]
    ]
    assert labeled_order_types == direct_order_types == ["input.di", "output.do"]

def test_source_declared_after_receiver_still_sorts_before_it():
    """User-requested addition: the main acceptance test's own two
    blocks (input.di has zero dependencies, output.do has exactly one)
    could pass even by ACCIDENT regardless of whether label-merging
    correctly wires anything at all -- Kahn's algorithm would put the
    zero-in-degree block first either way. This test forces the real
    question: the RECEIVER block is added to the project BEFORE its
    source, so a topological sort that (bug) relied on insertion order
    instead of the actual Pin.connections graph would get this wrong."""
    p = Project()
    receiver = BlockRegistry.create_block("logic.buffer")  # added FIRST
    p.add_block(receiver)
    source = _di()  # added SECOND -- but must still execute FIRST
    p.add_block(source)
    p.add_wire(_free_end_wire(receiver.inputs[0], "Later", is_source=False))
    p.add_wire(_free_end_wire(source.outputs[0], "Later", is_source=True))

    c = Compiler(p)
    res = c.compile()
    assert res is not None, c.errors
    order = res["execution_order"]
    assert order.index(source.uuid) < order.index(receiver.uuid)

def test_one_source_three_receivers_matches_direct_fanout_wiring():
    """User-requested addition, and per their own note the more
    important of the two: "jeden sygnał na pięć stron schematu" is the
    single most common real use of a label. One source, three
    receivers, MUST produce the same execution_order as the identical
    topology wired with three direct fan-out connections from the same
    output (Pin.connect() already allows one output driving several
    inputs -- only an INPUT is single-driver)."""
    def _labeled_fanout():
        p = Project()
        source = _di()
        r1 = BlockRegistry.create_block("logic.buffer")
        r2 = BlockRegistry.create_block("logic.buffer")
        r3 = BlockRegistry.create_block("logic.buffer")
        for b in (source, r1, r2, r3):
            p.add_block(b)
        p.add_wire(_free_end_wire(source.outputs[0], "Fanout", is_source=True))
        p.add_wire(_free_end_wire(r1.inputs[0], "Fanout", is_source=False))
        p.add_wire(_free_end_wire(r2.inputs[0], "Fanout", is_source=False))
        p.add_wire(_free_end_wire(r3.inputs[0], "Fanout", is_source=False))
        return p, source, [r1, r2, r3]

    def _direct_fanout():
        p = Project()
        source = _di()
        r1 = BlockRegistry.create_block("logic.buffer")
        r2 = BlockRegistry.create_block("logic.buffer")
        r3 = BlockRegistry.create_block("logic.buffer")
        for b in (source, r1, r2, r3):
            p.add_block(b)
        source.outputs[0].connect(r1.inputs[0])
        source.outputs[0].connect(r2.inputs[0])
        source.outputs[0].connect(r3.inputs[0])
        return p, source, [r1, r2, r3]

    labeled_p, labeled_source, labeled_receivers = _labeled_fanout()
    direct_p, direct_source, direct_receivers = _direct_fanout()

    labeled_res = Compiler(labeled_p).compile()
    direct_res = Compiler(direct_p).compile()
    assert labeled_res is not None, Compiler(labeled_p).errors
    assert direct_res is not None

    def _shape(execution_order, source, receivers):
        """Position-independent shape: (is-source-first, set of
        positions after it) -- uuids differ between the two separately-
        built projects, only relative order is comparable."""
        source_index = execution_order.index(source.uuid)
        receiver_indices = {execution_order.index(r.uuid) for r in receivers}
        return source_index, sorted(receiver_indices)

    labeled_shape = _shape(labeled_res["execution_order"], labeled_source, labeled_receivers)
    direct_shape = _shape(direct_res["execution_order"], direct_source, direct_receivers)

    assert labeled_shape == direct_shape
    # And explicitly: the source runs before EVERY receiver, in both.
    assert all(i > labeled_shape[0] for i in labeled_shape[1])
    assert all(i > direct_shape[0] for i in direct_shape[1])

def test_label_and_direct_wire_produce_identical_simulation_results():
    from logic_studio.engine.execution import ExecutionEngine
    from logic_studio.engine.io_provider import SimulationIOProvider
    from logic_studio.engine.time_provider import SimulationTimeProvider

    labeled_p, _, _ = _labeled_project()
    direct_p, _, _ = _directly_wired_project()

    for project, expected in ((labeled_p, True), (direct_p, True)):
        res = Compiler(project).compile()
        assert res is not None, res
        io = SimulationIOProvider()
        engine = ExecutionEngine(res["program"], io, SimulationTimeProvider())
        engine.start()
        io.set_digital_input("ELA01.DI01", True)
        engine.step()
        assert io.output_image["digital"].get("ADA01.DO01") is expected

def test_live_project_pins_are_never_mutated_by_compiling_a_label():
    """label_merge.py runs against compile_view's already-CLONED pins
    (compiler/core.py's _ExpandedProjectView, via macros.expand_project()'s
    clone(preserve_uuid=True) of every top-level block, macro or not) --
    compiling must never leave the live Pin.connections looking like a
    real wire was drawn just because a label happened to merge two ends."""
    p, di, do = _labeled_project()
    Compiler(p).compile()
    assert di.outputs[0].connections == []
    assert do.inputs[0].connections == []


# ---- §A1.1/§A1.2: grouping ------------------------------------------------

def test_grouping_is_case_insensitive():
    p, di, do = _labeled_project()
    p.wires[1].label = "cmd"  # was "Cmd" -- same node, different case
    res = Compiler(p).compile()
    assert res is not None, res.errors if res is None else None
    assert res["execution_order"] is not None

def test_a_fully_connected_wire_with_a_unique_label_changes_nothing():
    """§A1.2: a label on a wire whose BOTH ends are already real pins is
    purely documentary on its own -- merging it with nothing produces no
    new edge, no error, no warning."""
    p = Project()
    src = _di()
    a = BlockRegistry.create_block("logic.not")
    b = BlockRegistry.create_block("logic.buffer")
    p.add_block(src)
    p.add_block(a)
    p.add_block(b)
    src.outputs[0].connect(a.inputs[0])
    a.outputs[0].connect(b.inputs[0])
    w = Wire()
    w.source_pin = a.outputs[0].uuid
    w.dest_pin = b.inputs[0].uuid
    w.label = "JustADocNote"
    p.add_wire(w)

    c = Compiler(p)
    res = c.compile()
    assert res is not None, c.errors
    assert c.errors == []
    assert c.warnings == []

def test_a_fully_connected_wires_pins_join_a_free_end_sharing_its_label():
    """§A1.2's own explicit case: the fully-connected wire's label is
    "just documentary" ONLY when nothing else shares it -- the moment a
    free end elsewhere uses the same name, every pin from every wire in
    the group is one node, uniformly, "bez wyjątków zależnych od
    geometrii". mid_b has NO physical wire to src at all -- it only
    receives anything because it shares "Shared" with the
    already-wired mid_a link."""
    from logic_studio.engine.execution import ExecutionEngine
    from logic_studio.engine.io_provider import SimulationIOProvider
    from logic_studio.engine.time_provider import SimulationTimeProvider

    p = Project()
    src = _di()
    mid_a = BlockRegistry.create_block("logic.buffer")
    mid_b = BlockRegistry.create_block("logic.buffer")
    do_b = _do("ADA01.DO01")
    p.add_block(src)
    p.add_block(mid_a)
    p.add_block(mid_b)
    p.add_block(do_b)
    src.outputs[0].connect(mid_a.inputs[0])
    mid_b.outputs[0].connect(do_b.inputs[0])

    fully_connected = Wire()
    fully_connected.source_pin = src.outputs[0].uuid
    fully_connected.dest_pin = mid_a.inputs[0].uuid
    fully_connected.label = "Shared"
    p.add_wire(fully_connected)

    free_end = Wire()
    free_end.dest_pin = mid_b.inputs[0].uuid
    free_end.free_end_source = {"x": 0.0, "y": 0.0}
    free_end.label = "Shared"
    p.add_wire(free_end)

    c = Compiler(p)
    res = c.compile()
    assert res is not None, c.errors
    assert c.errors == []
    assert c.warnings == []

    io = SimulationIOProvider()
    engine = ExecutionEngine(res["program"], io, SimulationTimeProvider())
    engine.start()
    io.set_digital_input("ELA01.DI01", True)
    engine.step()
    # do_b is fed only via mid_b, which is fed only via the "Shared" label
    # -- if the merge didn't reach it, this stays False/None forever.
    assert io.output_image["digital"].get("ADA01.DO01") is True


# ---- §A2: validation -------------------------------------------------------

def test_label_with_no_source_is_an_error():
    p = Project()
    do = _do()
    p.add_block(do)
    p.add_wire(_free_end_wire(do.inputs[0], "Orphan", is_source=False))

    c = Compiler(p)
    res = c.compile()
    assert res is None
    assert any("Orphan" in e and "nie ma źródła" in e for e in c.errors), c.errors

def test_label_with_two_sources_is_an_error_naming_both_blocks():
    p = Project()
    di1 = _di("ELA01.DI01")
    di2 = _di("ELA01.DI02")
    p.add_block(di1)
    p.add_block(di2)
    p.add_wire(_free_end_wire(di1.outputs[0], "TwoSources", is_source=True))
    p.add_wire(_free_end_wire(di2.outputs[0], "TwoSources", is_source=True))

    c = Compiler(p)
    res = c.compile()
    assert res is None
    matches = [e for e in c.errors if "TwoSources" in e and "więcej niż jedno źródło" in e]
    assert len(matches) == 1
    assert di1.short_id in matches[0]
    assert di2.short_id in matches[0]

def test_label_with_source_but_no_receiver_is_a_warning_not_an_error():
    p = Project()
    di = _di()
    p.add_block(di)
    p.add_wire(_free_end_wire(di.outputs[0], "Unheard", is_source=True))

    c = Compiler(p)
    res = c.compile()
    assert res is not None, c.errors
    assert any("Unheard" in w and "nigdzie nie jest odbierany" in w for w in c.warnings), c.warnings

def test_incompatible_types_across_a_label_is_an_error_naming_the_label():
    """A REAL (non-Any) typed output feeding a REAL-typed input of a
    different type through a label -- exactly the same rejection
    Pin.connect() already gives a direct wire, surfaced with the label
    named so the mismatch is locatable (§A1.3)."""
    p = Project()
    ai = BlockRegistry.create_block("input.ai")
    ai.properties["Address"] = "AI.CONTRACT"
    cmp_block = BlockRegistry.create_block("logic.not")  # BOOL input
    p.settings["analog_points"] = [
        {"address": "AI.CONTRACT", "name": "X", "unit": "u", "min": 0.0, "max": 10.0, "direction": "input"},
    ]
    p.add_block(ai)
    p.add_block(cmp_block)
    p.add_wire(_free_end_wire(ai.outputs[0], "TypeMismatch", is_source=True))  # REAL output
    p.add_wire(_free_end_wire(cmp_block.inputs[0], "TypeMismatch", is_source=False))  # BOOL input

    c = Compiler(p)
    res = c.compile()
    assert res is None
    assert any("TypeMismatch" in e for e in c.errors), c.errors

def test_multiple_receivers_on_one_label_is_legal():
    p = Project()
    di = _di()
    do1 = _do("ADA01.DO01")
    do2 = _do("ADA01.DO02")
    p.add_block(di)
    p.add_block(do1)
    p.add_block(do2)
    p.add_wire(_free_end_wire(di.outputs[0], "Fanout", is_source=True))
    p.add_wire(_free_end_wire(do1.inputs[0], "Fanout", is_source=False))
    p.add_wire(_free_end_wire(do2.inputs[0], "Fanout", is_source=False))

    c = Compiler(p)
    res = c.compile()
    assert res is not None, c.errors
    assert c.errors == []


# ---- group_labeled_pins() in isolation -------------------------------------

# ---- describe_label_groups() (UI-facing, read-only) -----------------------

def test_describe_label_groups_never_mutates_pin_connections():
    p, di, do = _labeled_project()
    describe_label_groups(p.wires, p.blocks)
    assert di.outputs[0].connections == []
    assert do.inputs[0].connections == []

def test_describe_label_groups_reports_source_position_and_receiver_count():
    p = Project()
    di = _di()
    di.set_position(300.0, 500.0)
    do1 = _do("ADA01.DO01")
    do2 = _do("ADA01.DO02")
    p.add_block(di)
    p.add_block(do1)
    p.add_block(do2)
    p.add_wire(_free_end_wire(di.outputs[0], "Fanout", is_source=True))
    p.add_wire(_free_end_wire(do1.inputs[0], "Fanout", is_source=False))
    p.add_wire(_free_end_wire(do2.inputs[0], "Fanout", is_source=False))

    summary = describe_label_groups(p.wires, p.blocks)["fanout"]
    assert summary["source_pos"] == (300.0, 500.0)
    assert summary["receiver_count"] == 2
    assert summary["has_error"] is False

def test_describe_label_groups_flags_no_source_as_an_error():
    p, di, do = _labeled_project()
    p.remove_wire(p.wires[0])  # only the receiver-side wire is left -- no source

    summary = describe_label_groups(p.wires, p.blocks)["cmd"]
    assert summary["source_pos"] is None
    assert summary["has_error"] is True

def test_describe_label_groups_flags_multiple_sources_as_an_error():
    p = Project()
    di1 = _di("ELA01.DI01")
    di2 = _di("ELA01.DI02")
    p.add_block(di1)
    p.add_block(di2)
    p.add_wire(_free_end_wire(di1.outputs[0], "TwoSources", is_source=True))
    p.add_wire(_free_end_wire(di2.outputs[0], "TwoSources", is_source=True))

    summary = describe_label_groups(p.wires, p.blocks)["twosources"]
    assert summary["source_pos"] is None
    assert summary["has_error"] is True


def test_group_labeled_pins_ignores_empty_and_whitespace_only_labels():
    p, di, do = _labeled_project()
    blank = Wire()
    blank.source_pin = di.outputs[0].uuid
    blank.free_end_dest = {"x": 1.0, "y": 1.0}
    blank.label = "   "
    groups = group_labeled_pins(p.wires + [blank], p.blocks)
    assert "   ".strip().lower() not in groups
    assert "cmd" in groups
