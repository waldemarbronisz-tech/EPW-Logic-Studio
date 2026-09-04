"""feat/undo-diff-storage — Project's undo/redo history, now stored as a
"top is always full, everything below it is a diff relative to its
neighbor above" chain (core/state_diff.py) instead of 50 independent full
JSON snapshots (AUDIT_REPORT.md §9.1/§25). The external contract
(push_state()/undo()/redo(), undo_stack/redo_stack as plain lists whose
len() is the entry count) is unchanged and covered elsewhere
(tests/test_undo_stack.py, UI-level); this file covers the STORAGE
change itself: multi-step correctness, the 50-entry cap, and the
in-place-mutation aliasing bug this redesign's own deep-copy fixes along
the way (BaseLogicBlock.serialize()'s "properties" and Project.settings'
nested values are returned BY REFERENCE, not copied -- undiagnosed before
this branch since nothing previously depended on a pushed snapshot
staying independent of later live edits).
"""
import pytest

from logic_studio.blocks import register_builtin_blocks
from logic_studio.blocks.registry import BlockRegistry
from logic_studio.core.project import Project, _HistoryEntry
from logic_studio.core.device_model import DeviceModel

register_builtin_blocks()


def _di():
    return BlockRegistry.create_block("input.di")


# ---- multi-step correctness --------------------------------------------

def test_three_edits_undo_all_the_way_back_in_order():
    p = Project()
    b = _di()
    b.properties["Address"] = "ELA01.DI01"
    p.add_block(b)

    p.push_state()          # snapshot: x=0
    b.x = 10.0
    p.push_state()          # snapshot: x=10
    b.x = 20.0
    p.push_state()          # snapshot: x=20
    b.x = 30.0               # live state now: x=30, not yet pushed

    assert len(p.undo_stack) == 3

    state = p.undo()
    assert state["blocks"][0]["position"]["x"] == 20.0
    p2 = Project.deserialize(state)
    assert p2.blocks[0].x == 20.0

    state = p.undo()
    assert state["blocks"][0]["position"]["x"] == 10.0

    state = p.undo()
    assert state["blocks"][0]["position"]["x"] == 0.0

    assert len(p.undo_stack) == 0
    assert p.undo() is None

def _apply(p, state):
    """Mirrors MainWindow._apply_state(): Project itself never self-
    applies the dict undo()/redo() hands back -- the caller (here, the
    test) swaps it in, exactly like the UI does, carrying the stacks
    forward onto the replacement instance."""
    undo_s, redo_s = p.undo_stack, p.redo_stack
    p = Project.deserialize(state)
    p.undo_stack, p.redo_stack = undo_s, redo_s
    return p

def test_redo_replays_forward_through_the_same_diff_chain():
    p = Project()
    b = _di()
    p.add_block(b)

    p.push_state()
    b.x = 10.0
    p.push_state()
    b.x = 20.0

    p = _apply(p, p.undo())  # -> x=10
    p = _apply(p, p.undo())  # -> x=0
    assert p.blocks[0].x == 0.0
    assert len(p.redo_stack) == 2

    p = _apply(p, p.redo())  # -> x=10
    assert p.blocks[0].x == 10.0
    p = _apply(p, p.redo())  # -> x=20
    assert p.blocks[0].x == 20.0
    assert len(p.redo_stack) == 0

def test_new_push_after_undo_clears_redo_stack():
    p = Project()
    b = _di()
    p.add_block(b)
    p.push_state()
    b.x = 10.0
    p.undo()
    assert len(p.redo_stack) == 1
    p.push_state()
    assert len(p.redo_stack) == 0


# ---- the 50-entry cap, still respected under diff storage ----------------

def test_cap_at_fifty_and_undo_still_walks_back_correctly_after_eviction():
    p = Project()
    b = _di()
    p.add_block(b)

    for i in range(60):
        b.x = float(i)
        p.push_state()

    assert len(p.undo_stack) == 50
    # oldest 10 pushes (x=0..9) were evicted -- the retained bottom entry
    # is the one pushed with b.x == 10.0
    state = p.undo_stack[0].full if p.undo_stack[0].full is not None else None
    # bottom entry may be stored as a diff (only the top is guaranteed
    # full) -- walk undo() 50 times and check the FINAL restored value
    # instead of poking at internal representation directly.
    last_state = None
    for _ in range(50):
        last_state = p.undo()
    assert last_state["blocks"][0]["position"]["x"] == 10.0
    assert p.undo() is None  # exactly 50, no more


# ---- the aliasing bug this redesign's deep-copy fixes ---------------------

def test_undo_after_a_later_in_place_property_mutation_is_not_corrupted():
    """BaseLogicBlock.serialize()'s "properties" key is the SAME dict
    object as the live block's own self.properties (not copied) -- a
    pushed snapshot must not silently pick up a LATER in-place edit to
    that dict through the shared reference."""
    p = Project()
    b = _di()
    b.properties["Address"] = "ELA01.DI01"
    p.add_block(b)

    p.push_state()  # snapshot: Address = ELA01.DI01
    b.properties["Address"] = "ELA01.DI02"  # in-place mutation, like the property grid does

    state = p.undo()
    assert state["blocks"][0]["properties"]["Address"] == "ELA01.DI01"

def test_undo_after_a_later_in_place_settings_mutation_is_not_corrupted():
    """Same hazard via Project.settings -- DeviceModel.set_io_label()
    mutates the io_labels dict in place through settings.setdefault()."""
    p = Project()
    p.push_state()  # snapshot: no io_labels entries
    DeviceModel.set_io_label(p, "ELA01.DI01", "Wyłącznik Q1")

    state = p.undo()
    assert state["settings"].get("io_labels", {}) == {}

def test_two_pushed_snapshots_do_not_alias_each_others_blocks_dict():
    p = Project()
    b = _di()
    b.properties["Address"] = "ELA01.DI01"
    p.add_block(b)

    p.push_state()  # snapshot A
    b.properties["Address"] = "ELA01.DI02"
    p.push_state()  # snapshot B
    b.properties["Address"] = "ELA01.DI03"  # live, unpushed

    state_b = p.undo()
    assert state_b["blocks"][0]["properties"]["Address"] == "ELA01.DI02"
    state_a = p.undo()
    assert state_a["blocks"][0]["properties"]["Address"] == "ELA01.DI01"
    # mutating the dict returned by the later undo() must not retroactively
    # change the earlier one's already-returned dict
    state_b["blocks"][0]["properties"]["Address"] = "TAMPERED"
    assert state_a["blocks"][0]["properties"]["Address"] == "ELA01.DI01"


# ---- storage shape: a single-block edit only stores that one block -------

def test_pushing_a_change_to_one_block_only_diffs_that_block_regardless_of_project_size():
    p = Project()
    blocks = []
    for i in range(20):
        blk = _di()
        blk.properties["Address"] = f"ELA01.DI{i+1:02d}"
        p.add_block(blk)
        blocks.append(blk)

    p.push_state()          # entry 0: full (first push)
    blocks[5].x = 999.0
    p.push_state()          # entry 1: full (new top); entry 0 becomes a diff

    entry_0 = p.undo_stack[0]
    assert entry_0.full is None and entry_0.diff is not None
    # only the ONE block that changed between these two states is present
    # in the diff's "set" -- not all 20.
    assert list(entry_0.diff["blocks"]["set"].keys()) == [blocks[5].uuid]
    assert entry_0.diff["blocks"]["remove"] == []

def test_history_entry_is_the_internal_storage_type():
    p = Project()
    p.add_block(_di())
    p.push_state()
    assert isinstance(p.undo_stack[0], _HistoryEntry)
