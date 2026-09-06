"""feat/project-diff — core/project_diff.py's compare_projects() and its
helpers, in complete isolation from Project/Qt (plain dicts only, exactly
the shape Project.serialize() produces) — same convention as
test_state_diff.py for core/state_diff.py, a deliberately SEPARATE module
(see project_diff.py's own docstring for why: readability, not undo/redo
storage efficiency)."""
from logic_studio.core.project_diff import (
    compare_projects, has_changes, summarize, block_label,
)


def _state(blocks, settings=None):
    return {
        "format": "EPW_LOGIC",
        "schema_version": 8,
        "settings": settings or {"name": "P"},
        "blocks": blocks,
    }


def _block(uuid, **extra):
    d = {
        "uuid": uuid, "short_id": f"g{uuid}", "type_id": "logic.and",
        "display_name": "AND", "enabled": True, "color": "#00557f",
        "execution_priority": 1,
        "position": {"x": 0.0, "y": 0.0}, "size": {"width": 60.0, "height": 60.0},
        "properties": {"Address": "", "Tag": "", "Comment": ""},
        "inputs": [], "outputs": [],
    }
    d.update(extra)
    return d


def _pin(uuid, name="P", connections=None):
    return {"uuid": uuid, "name": name, "direction": "input", "data_type": "BOOL", "connections": connections or []}


# ---- no differences ---------------------------------------------------

def test_identical_projects_have_no_differences():
    state = _state([_block("a"), _block("b")])
    comparison = compare_projects(state, state)
    assert comparison["blocks_added"] == []
    assert comparison["blocks_removed"] == []
    assert comparison["blocks_changed"] == []
    assert comparison["settings_changes"] == []
    assert has_changes(comparison) is False
    assert summarize(comparison) == "Brak różnic"


# ---- added / removed --------------------------------------------------

def test_block_added():
    base = _state([_block("a")])
    target = _state([_block("a"), _block("b")])
    comparison = compare_projects(base, target)
    assert [b["uuid"] for b in comparison["blocks_added"]] == ["b"]
    assert comparison["blocks_removed"] == []
    assert has_changes(comparison) is True

def test_block_removed():
    base = _state([_block("a"), _block("b")])
    target = _state([_block("a")])
    comparison = compare_projects(base, target)
    assert comparison["blocks_added"] == []
    assert [b["uuid"] for b in comparison["blocks_removed"]] == ["b"]

def test_added_and_removed_do_not_scramble_a_middle_insertion():
    """Blocks matched by uuid, never list position — inserting a block in
    the MIDDLE of the list must not make everything after it look changed."""
    base = _state([_block("a"), _block("c")])
    target = _state([_block("a"), _block("b"), _block("c")])
    comparison = compare_projects(base, target)
    assert [b["uuid"] for b in comparison["blocks_added"]] == ["b"]
    assert comparison["blocks_changed"] == []


# ---- changed: scalar fields ---------------------------------------------

def test_display_name_change():
    base = _state([_block("a", display_name="AND")])
    target = _state([_block("a", display_name="MyGate")])
    comparison = compare_projects(base, target)
    assert len(comparison["blocks_changed"]) == 1
    change = comparison["blocks_changed"][0]
    assert change["uuid"] == "a"
    assert {"field": "display_name", "old": "AND", "new": "MyGate"} in change["field_changes"]

def test_enabled_change():
    base = _state([_block("a", enabled=True)])
    target = _state([_block("a", enabled=False)])
    comparison = compare_projects(base, target)
    assert {"field": "enabled", "old": True, "new": False} in comparison["blocks_changed"][0]["field_changes"]

def test_color_and_execution_priority_changes():
    base = _state([_block("a", color="#111111", execution_priority=1)])
    target = _state([_block("a", color="#222222", execution_priority=5)])
    change = compare_projects(base, target)["blocks_changed"][0]
    assert {"field": "color", "old": "#111111", "new": "#222222"} in change["field_changes"]
    assert {"field": "execution_priority", "old": 1, "new": 5} in change["field_changes"]


# ---- changed: properties -------------------------------------------------

def test_property_change():
    base = _state([_block("a", properties={"Address": "ELA01.DI01", "Tag": "", "Comment": ""})])
    target = _state([_block("a", properties={"Address": "ELA01.DI02", "Tag": "", "Comment": ""})])
    change = compare_projects(base, target)["blocks_changed"][0]
    assert {"field": "properties.Address", "old": "ELA01.DI01", "new": "ELA01.DI02"} in change["field_changes"]

def test_property_added_and_removed_keys():
    base = _state([_block("a", properties={"Address": ""})])
    target = _state([_block("a", properties={"Address": "", "Extra": "X"})])
    change = compare_projects(base, target)["blocks_changed"][0]
    assert {"field": "properties.Extra", "old": None, "new": "X"} in change["field_changes"]


# ---- changed: moved (position) reported separately -----------------------

def test_position_change_is_reported_as_moved_not_a_field_change():
    base = _state([_block("a", position={"x": 0.0, "y": 0.0})])
    target = _state([_block("a", position={"x": 100.0, "y": 50.0})])
    change = compare_projects(base, target)["blocks_changed"][0]
    assert change["moved"] is True
    assert all(fc["field"] != "position" for fc in change["field_changes"])

def test_unchanged_position_is_not_moved():
    base = _state([_block("a", display_name="X", position={"x": 0.0, "y": 0.0})])
    target = _state([_block("a", display_name="Y", position={"x": 0.0, "y": 0.0})])
    change = compare_projects(base, target)["blocks_changed"][0]
    assert change["moved"] is False


# ---- changed: connections -------------------------------------------------

def test_connection_added():
    base = _block("a", inputs=[_pin("p1", connections=[])])
    target = _block("a", inputs=[_pin("p1", connections=["other-pin"])])
    change = compare_projects(_state([base]), _state([target]))["blocks_changed"][0]
    assert change["connection_changes"] == [
        {"pin_uuid": "p1", "pin_name": "P", "added": ["other-pin"], "removed": []}
    ]

def test_connection_removed():
    base = _block("a", inputs=[_pin("p1", connections=["other-pin"])])
    target = _block("a", inputs=[_pin("p1", connections=[])])
    change = compare_projects(_state([base]), _state([target]))["blocks_changed"][0]
    assert change["connection_changes"] == [
        {"pin_uuid": "p1", "pin_name": "P", "added": [], "removed": ["other-pin"]}
    ]

def test_unrelated_pins_are_not_reported():
    base = _block("a", inputs=[_pin("p1", connections=["x"])])
    target = _block("a", inputs=[_pin("p1", connections=["x"])])
    comparison = compare_projects(_state([base]), _state([target]))
    assert comparison["blocks_changed"] == []  # identical, no spurious entry


# ---- unchanged blocks never appear -----------------------------------

def test_a_completely_identical_block_is_never_listed_as_changed():
    base = _state([_block("a"), _block("b", display_name="X")])
    target = _state([_block("a"), _block("b", display_name="Y")])
    comparison = compare_projects(base, target)
    assert [c["uuid"] for c in comparison["blocks_changed"]] == ["b"]


# ---- settings --------------------------------------------------------

def test_settings_key_added():
    base = _state([], settings={"name": "P"})
    target = _state([], settings={"name": "P", "cycle_time_ms": 100})
    comparison = compare_projects(base, target)
    assert {"key": "cycle_time_ms", "old": None, "new": 100} in comparison["settings_changes"]

def test_settings_key_removed():
    base = _state([], settings={"name": "P", "cycle_time_ms": 100})
    target = _state([], settings={"name": "P"})
    comparison = compare_projects(base, target)
    assert {"key": "cycle_time_ms", "old": 100, "new": None} in comparison["settings_changes"]

def test_settings_key_changed():
    base = _state([], settings={"name": "Old"})
    target = _state([], settings={"name": "New"})
    comparison = compare_projects(base, target)
    assert {"key": "name", "old": "Old", "new": "New"} in comparison["settings_changes"]

def test_settings_diff_is_whole_key_not_deep():
    base = _state([], settings={"analog_points": [{"address": "AI01", "min": 0}]})
    target = _state([], settings={"analog_points": [{"address": "AI01", "min": 0}, {"address": "AI02", "min": 0}]})
    comparison = compare_projects(base, target)
    assert len(comparison["settings_changes"]) == 1
    assert comparison["settings_changes"][0]["key"] == "analog_points"


# ---- summarize() / has_changes() ------------------------------------------

def test_summarize_combines_every_category():
    base = _state([_block("a"), _block("b")], settings={"name": "Old"})
    target = _state([_block("a", display_name="Changed"), _block("c")], settings={"name": "New"})
    comparison = compare_projects(base, target)
    text = summarize(comparison)
    assert "+1" in text
    assert "-1" in text
    assert "1 zmienione" in text
    assert "zmian ustawień" in text


# ---- block_label() ------------------------------------------------------

def test_block_label_with_tag():
    assert block_label(_block("a", short_id="g7", properties={"Tag": "Q1"})) == "g7 — Q1"

def test_block_label_with_comment_when_no_tag():
    assert block_label(_block("a", short_id="g7", properties={"Tag": "", "Comment": "opis"})) == "g7 — opis"

def test_block_label_falls_back_to_short_id_alone():
    assert block_label(_block("a", short_id="g7", properties={})) == "g7"

def test_block_label_falls_back_to_display_name_without_short_id():
    d = _block("a", properties={})
    del d["short_id"]
    assert block_label(d) == "AND"
