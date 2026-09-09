"""feat/wire-detour-and-text-size §B — "Rozmiar tekstu" property on the
three documentation block types (doc.text/doc.note/doc.section).
"""
import pytest
from PySide6.QtCore import Qt, QPoint, QPointF, QRectF
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication, QSpinBox

from logic_studio.blocks import register_builtin_blocks
from logic_studio.blocks.registry import BlockRegistry
from logic_studio.core.project import Project
from logic_studio.ui.canvas import style
from logic_studio.ui.canvas.block_item import BlockItem
from logic_studio.ui.canvas.scene import LogicScene
from logic_studio.ui.canvas.view import LogicView
from logic_studio.ui.panels.property_grid import PropertyGridPanel

register_builtin_blocks()

_DOC_TYPE_IDS = ("doc.text", "doc.note", "doc.section")
_KEY = "Rozmiar tekstu (pkt)"


def _app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


# ---- §B1: property exists, with the pre-existing look's own default ------

@pytest.mark.parametrize("type_id, expected_default", [
    ("doc.text", style.FONT_SIZE_DOC_TEXT),
    ("doc.note", style.FONT_SIZE_DOC_NOTE),
    ("doc.section", style.FONT_SIZE_DOC_SECTION),
])
def test_default_text_size_matches_the_pre_existing_font_size(type_id, expected_default):
    """§B1: "odczytaj [wartości domyślne] z bieżącego kodu, nie zgaduj" —
    documentation.py can't import ui/canvas/style.py directly (it must
    stay Qt-free for headless engine use, see its own comment), so its
    default is a hardcoded literal that must be kept in sync with
    style.py's own constant BY HAND. This is exactly the guard against
    that drifting apart silently."""
    block = BlockRegistry.create_block(type_id)
    assert block.properties[_KEY] == expected_default

@pytest.mark.parametrize("type_id", _DOC_TYPE_IDS)
def test_documentation_module_never_imports_qt(type_id):
    """The defaults above are hardcoded specifically so constructing a doc
    block never pulls in PySide6 — verified directly (AST, not a plain
    'PySide6' not in sys.modules' check, which this test process already
    fails trivially by having imported plenty of Qt elsewhere), mirroring
    test_acceptance.py::test_headless_engine_no_qt's own reasoning for
    this specific new property."""
    import ast
    import inspect
    import logic_studio.blocks.documentation as doc_module
    source = inspect.getsource(doc_module)
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            module = getattr(node, "module", None) or ""
            names = [n.name for n in node.names]
            assert "PySide6" not in module and "logic_studio.ui" not in module, (
                f"documentation.py imports {module or names} -- breaks headless engine use"
            )


# ---- §B1: range enforced by the editor, not just validation after -------

@pytest.mark.parametrize("type_id", _DOC_TYPE_IDS)
def test_text_size_editor_enforces_6_to_48(qsettings, type_id):
    _app()
    p = Project()
    block = BlockRegistry.create_block(type_id)
    p.add_block(block)
    panel = PropertyGridPanel(settings=qsettings)
    panel.load_block_properties(block, p)

    field = panel.field_widget("Rozmiar tekstu")
    assert isinstance(field, QSpinBox)
    assert field.minimum() == 6
    assert field.maximum() == 48
    assert field.suffix() == " pkt"


# ---- §B2: SERIALIZED_FIELDS mechanism, no manual per-path code -----------

@pytest.mark.parametrize("type_id", _DOC_TYPE_IDS)
def test_text_size_round_trips_through_serialize_deserialize(type_id):
    block = BlockRegistry.create_block(type_id)
    block.properties[_KEY] = 24
    data = block.serialize()
    restored = block.__class__.deserialize(data)
    assert restored.properties[_KEY] == 24

@pytest.mark.parametrize("type_id", _DOC_TYPE_IDS)
def test_text_size_round_trips_through_clone(type_id):
    block = BlockRegistry.create_block(type_id)
    block.properties[_KEY] = 30
    cloned = block.clone()
    assert cloned.properties[_KEY] == 30

@pytest.mark.parametrize("type_id, expected_default", [
    ("doc.text", style.FONT_SIZE_DOC_TEXT),
    ("doc.note", style.FONT_SIZE_DOC_NOTE),
    ("doc.section", style.FONT_SIZE_DOC_SECTION),
])
def test_missing_text_size_in_an_old_file_defaults_without_migration(type_id, expected_default):
    """§B2: "brak właściwości w starym pliku oznacza wartość domyślną, bez
    migracji schematu" — a save file from before this property existed
    has no "Rozmiar tekstu (pkt)" key in its "properties" dict AT ALL,
    not an empty/null one. Deserializing it must still come back with
    the correct per-type default, with zero schema_version bump."""
    block = BlockRegistry.create_block(type_id)
    data = block.serialize()
    del data["properties"][_KEY]  # simulate a pre-this-feature save file
    assert _KEY not in data["properties"]

    restored = block.__class__.deserialize(data)
    assert restored.properties[_KEY] == expected_default

def test_deserialize_merges_missing_properties_onto_fresh_defaults_generically():
    """The mechanism behind the test above, checked directly and
    type-agnostically: BaseLogicBlock.deserialize() must MERGE a saved
    "properties" dict onto a freshly-constructed instance's own defaults
    (update()), never REPLACE it outright — a plain replace would drop
    any key the file predates instead of defaulting it, for every block
    type, not just documentation ones."""
    block = BlockRegistry.create_block("doc.text")
    data = block.serialize()
    data["properties"] = {"Text": "only this key, nothing else"}
    restored = block.__class__.deserialize(data)
    assert restored.properties["Text"] == "only this key, nothing else"
    assert restored.properties[_KEY] == style.FONT_SIZE_DOC_TEXT
    assert restored.properties["Tag"] == ""  # every other base default still present too


# ---- §B3: geometry follows the text/font, never clips ---------------------

@pytest.mark.parametrize("type_id", _DOC_TYPE_IDS)
@pytest.mark.parametrize("size", [6, 12, 24, 48])
def test_text_fits_within_the_block_at_every_size(type_id, size):
    """§B3: "Tekst nie może wychodzić poza obrys" — checked geometrically
    (QFontMetricsF against the block's own final width/height), the way
    this codebase's own existing rendering tests check fit (e.g.
    test_block_display.py's IO-text-bounding-rect test) — extended here
    to doc blocks, which none of the existing ones cover."""
    from PySide6.QtGui import QFontMetricsF
    _app()
    block = BlockRegistry.create_block(type_id)
    block.properties[_KEY] = size
    block.properties["Text"] = "Sample documentation text for sizing"
    item = BlockItem(block)

    font = item.doc_text_font()
    fm = QFontMetricsF(font)
    if type_id == "doc.note":
        inner_width = max(item.width - 12, 1)
        wrapped = fm.boundingRect(QRectF(0, 0, inner_width, 1_000_000.0), Qt.TextWordWrap, block.properties["Text"])
        assert wrapped.height() + 12 <= item.height + 0.5  # +0.5: float rounding at the grid boundary
    else:
        assert fm.horizontalAdvance(block.properties["Text"]) + 20 <= item.width + 0.5
        assert fm.height() + 10 <= item.height + 0.5

@pytest.mark.parametrize("type_id", ("doc.text", "doc.section"))
def test_changing_text_size_changes_block_dimensions(type_id):
    """§B5: "zmiana rozmiaru zmienia wysokość i szerokość bloku"."""
    _app()
    block = BlockRegistry.create_block(type_id)
    block.properties["Text"] = "A reasonably long sample line of text"
    small_item = BlockItem(block)
    small_size = (small_item.width, small_item.height)

    block.properties[_KEY] = 40
    small_item._determine_shape_style()
    assert (small_item.width, small_item.height) != small_size
    assert small_item.width >= small_size[0]
    assert small_item.height >= small_size[1]

def test_changing_doc_note_text_size_grows_height_not_width():
    """doc.note specifically: width is the user's own manual choice and
    must never be silently grown; height grows only if the new font no
    longer fits the wrapped text at the CURRENT width."""
    _app()
    block = BlockRegistry.create_block("doc.note")
    block.properties["Text"] = "A note with enough words to wrap across more than one line at a small font size."
    block.properties[_KEY] = 8  # small -- the note's initial default width comfortably fits it
    item = BlockItem(block)
    item.logic_block.width = item.width  # lock in the "manual" width
    original_width, original_height = item.width, item.height

    block.properties[_KEY] = 36  # much bigger -- same wrapped text no longer fits at this height
    item._determine_shape_style()
    assert item.width == original_width
    assert item.height > original_height

def test_doc_note_manual_size_already_big_enough_is_left_alone():
    """§B3: a manual resize must never be silently undone -- only grown
    when it's genuinely too small for the new font."""
    _app()
    block = BlockRegistry.create_block("doc.note")
    block.properties["Text"] = "short"
    item = BlockItem(block)
    item.logic_block.width = 400
    item.logic_block.height = 300
    item._determine_shape_style()
    assert item.width == 400
    assert item.height == 300

    block.properties[_KEY] = 10  # still tiny relative to a 400x300 box
    item._determine_shape_style()
    assert item.width == 400
    assert item.height == 300


# ---- §B1/§B3: property-panel-driven edits also refresh the canvas item ---

def test_editing_text_size_via_the_property_panel_refits_the_canvas_item(qsettings):
    _app()
    p = Project()
    block = BlockRegistry.create_block("doc.text")
    block.properties["Text"] = "A reasonably long sample line of text"
    p.add_block(block)
    scene = LogicScene()
    scene.set_project(p) if hasattr(scene, "set_project") else None
    item = BlockItem(block)
    scene.addItem(item)
    original_width = item.width

    panel = PropertyGridPanel(settings=qsettings)
    panel.window = lambda: type("W", (), {"project": p, "scene": scene, "set_dirty": lambda self: None})()
    panel.load_block_properties(block, p)
    panel._commit_property(_KEY, 40)

    assert block.properties[_KEY] == 40
    assert item.width != original_width


# ---- §B4: Ctrl+scroll ------------------------------------------------------

def _wheel_event(pos, delta_y, ctrl):
    modifiers = Qt.ControlModifier if ctrl else Qt.NoModifier
    return QWheelEvent(
        QPointF(pos), QPointF(pos), QPoint(0, 0), QPoint(0, delta_y),
        Qt.NoButton, modifiers, Qt.NoScrollPhase, False,
    )


def test_ctrl_scroll_over_a_selected_doc_block_changes_its_text_size():
    _app()
    scene = LogicScene()
    scene.add_block_from_library("doc.text", 0, 0)
    item = next(i for i in scene.items() if isinstance(i, BlockItem))
    item.setSelected(True)
    view = LogicView(scene)
    view.resize(400, 400)

    original = item.logic_block.properties[_KEY]
    center = view.mapFromScene(item.sceneBoundingRect().center())
    view.wheelEvent(_wheel_event(center, 120, ctrl=True))
    assert item.logic_block.properties[_KEY] == original + 1

def test_ctrl_scroll_over_empty_canvas_still_zooms():
    """§B4: verifying the OTHER half — Ctrl+scroll away from any selected
    doc block must fall through to the pre-existing zoom behavior
    unchanged, not silently do nothing."""
    _app()
    scene = LogicScene()
    view = LogicView(scene)
    view.resize(400, 400)
    zoom_before = view.current_zoom()

    view.wheelEvent(_wheel_event(QPointF(200, 200), 120, ctrl=True))
    assert view.current_zoom() != zoom_before

def test_plain_scroll_over_a_selected_doc_block_still_zooms_not_resizes():
    """Only Ctrl+scroll is intercepted — a plain scroll over a selected
    doc block must zoom exactly as it always has."""
    _app()
    scene = LogicScene()
    scene.add_block_from_library("doc.text", 0, 0)
    item = next(i for i in scene.items() if isinstance(i, BlockItem))
    item.setSelected(True)
    view = LogicView(scene)
    view.resize(400, 400)

    original_size = item.logic_block.properties[_KEY]
    zoom_before = view.current_zoom()
    center = view.mapFromScene(item.sceneBoundingRect().center())
    view.wheelEvent(_wheel_event(center, 120, ctrl=False))

    assert item.logic_block.properties[_KEY] == original_size
    assert view.current_zoom() != zoom_before

def test_ctrl_scroll_over_an_unselected_doc_block_falls_through_to_zoom():
    _app()
    scene = LogicScene()
    scene.add_block_from_library("doc.text", 0, 0)
    item = next(i for i in scene.items() if isinstance(i, BlockItem))
    # deliberately NOT selected
    view = LogicView(scene)
    view.resize(400, 400)

    original_size = item.logic_block.properties[_KEY]
    zoom_before = view.current_zoom()
    center = view.mapFromScene(item.sceneBoundingRect().center())
    view.wheelEvent(_wheel_event(center, 120, ctrl=True))

    assert item.logic_block.properties[_KEY] == original_size
    assert view.current_zoom() != zoom_before

def test_ctrl_scroll_clamps_at_the_declared_range():
    _app()
    scene = LogicScene()
    scene.add_block_from_library("doc.text", 0, 0)
    item = next(i for i in scene.items() if isinstance(i, BlockItem))
    item.setSelected(True)
    item.logic_block.properties[_KEY] = 48
    view = LogicView(scene)
    view.resize(400, 400)
    center = view.mapFromScene(item.sceneBoundingRect().center())

    view.wheelEvent(_wheel_event(center, 120, ctrl=True))  # scroll up past 48
    assert item.logic_block.properties[_KEY] == 48

    item.logic_block.properties[_KEY] = 6
    view.wheelEvent(_wheel_event(center, -120, ctrl=True))  # scroll down past 6
    assert item.logic_block.properties[_KEY] == 6
