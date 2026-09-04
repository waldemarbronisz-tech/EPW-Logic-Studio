"""feat/undo-diff-storage — core/state_diff.py's diff/patch pair in
complete isolation from Project/Qt (plain dicts only, exactly the shape
Project.serialize() produces).
"""
from logic_studio.core.state_diff import diff_project_state, apply_project_diff


def _state(blocks, settings=None):
    return {
        "format": "EPW_LOGIC",
        "schema_version": 5,
        "settings": settings or {"name": "P", "ela_devices": ["ELA01"]},
        "blocks": blocks,
    }


def _block(uuid, **extra):
    d = {"uuid": uuid, "type_id": "logic.and", "x": 0.0, "y": 0.0}
    d.update(extra)
    return d


# ---- round-trip: apply_project_diff(base, diff_project_state(base, target)) == target ----

def test_round_trip_identical_states():
    base = _state([_block("a"), _block("b")])
    target = _state([_block("a"), _block("b")])
    diff = diff_project_state(base, target)
    assert apply_project_diff(base, diff) == target
    assert diff["blocks"]["set"] == {}
    assert diff["blocks"]["remove"] == []

def test_round_trip_one_block_changed():
    base = _state([_block("a", x=0.0), _block("b", x=100.0)])
    target = _state([_block("a", x=50.0), _block("b", x=100.0)])
    diff = diff_project_state(base, target)
    assert apply_project_diff(base, diff) == target
    # only the changed block appears in "set" -- "b" is untouched
    assert list(diff["blocks"]["set"].keys()) == ["a"]

def test_round_trip_block_added():
    base = _state([_block("a")])
    target = _state([_block("a"), _block("b")])
    diff = diff_project_state(base, target)
    assert apply_project_diff(base, diff) == target
    assert diff["blocks"]["set"] == {"b": _block("b")}
    assert diff["blocks"]["remove"] == []

def test_round_trip_block_removed():
    base = _state([_block("a"), _block("b")])
    target = _state([_block("a")])
    diff = diff_project_state(base, target)
    assert apply_project_diff(base, diff) == target
    assert diff["blocks"]["remove"] == ["b"]

def test_round_trip_block_reordered_without_content_change():
    """List order is preserved via an explicit uuid list -- reordering
    with no content change still round-trips exactly, not just
    "same set of blocks in some order"."""
    base = _state([_block("a"), _block("b")])
    target = _state([_block("b"), _block("a")])
    diff = diff_project_state(base, target)
    result = apply_project_diff(base, diff)
    assert result == target
    assert [b["uuid"] for b in result["blocks"]] == ["b", "a"]

def test_round_trip_settings_changed():
    base = _state([], settings={"name": "Old", "ela_devices": ["ELA01"]})
    target = _state([], settings={"name": "New", "ela_devices": ["ELA01", "ELA02"]})
    diff = diff_project_state(base, target)
    assert apply_project_diff(base, diff) == target
    assert diff["settings"]["set"] == {"ela_devices": ["ELA01", "ELA02"], "name": "New"}

def test_round_trip_settings_key_added_and_removed():
    base = _state([], settings={"name": "P"})
    target = _state([], settings={"name": "P", "io_labels": {"ELA01.DI01": "Q1"}})
    diff = diff_project_state(base, target)
    assert apply_project_diff(base, diff) == target
    assert diff["settings"]["set"] == {"io_labels": {"ELA01.DI01": "Q1"}}

    # and the reverse direction: a key present in base, absent in target
    diff_back = diff_project_state(target, base)
    assert apply_project_diff(target, diff_back) == base
    assert diff_back["settings"]["unset"] == ["io_labels"]

def test_diff_is_empty_shaped_for_two_identical_states():
    base = _state([_block("a")])
    diff = diff_project_state(base, base)
    assert diff["blocks"]["set"] == {}
    assert diff["blocks"]["remove"] == []
    assert diff["settings"]["set"] == {}
    assert diff["settings"]["unset"] == []

def test_diff_does_not_mutate_either_input():
    base = _state([_block("a", x=0.0)])
    target = _state([_block("a", x=50.0), _block("b")])
    base_copy, target_copy = dict(base), dict(target)
    diff_project_state(base, target)
    assert base == base_copy
    assert target == target_copy

def test_apply_does_not_mutate_base():
    base = _state([_block("a", x=0.0)])
    target = _state([_block("a", x=50.0)])
    diff = diff_project_state(base, target)
    base_copy = {
        "format": base["format"], "schema_version": base["schema_version"],
        "settings": dict(base["settings"]), "blocks": [dict(b) for b in base["blocks"]],
    }
    apply_project_diff(base, diff)
    assert base == base_copy

def test_format_and_schema_version_carried_through():
    base = _state([])
    target = _state([_block("a")])
    diff = diff_project_state(base, target)
    result = apply_project_diff(base, diff)
    assert result["format"] == "EPW_LOGIC"
    assert result["schema_version"] == 5
