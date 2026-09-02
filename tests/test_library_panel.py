"""Tests for the library tree, procedural icons, and element preview panel
(feat/block-rendering-library §4-6)."""
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from logic_studio.blocks import register_builtin_blocks
from logic_studio.blocks.registry import BlockRegistry


def _app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


register_builtin_blocks()


def test_library_tree_lists_every_registered_block(qsettings):
    """Regression: an earlier draft of the tree excluded "Dokumentacja" the
    same way the compiler does, silently dropping Text/Note/Section from the
    library even though they're placeable canvas annotations."""
    _app()
    from logic_studio.ui.panels.library import LibraryPanel

    panel = LibraryPanel(settings=qsettings)
    total = 0
    for i in range(panel.tree.topLevelItemCount()):
        item = panel.tree.topLevelItem(i)
        if item.text(0) != "Ostatnio używane":
            total += item.childCount()

    expected = sum(len(BlockRegistry.get_blocks_in_category(c)) for c in BlockRegistry.get_categories())
    assert total == expected

_REMOVED_PLACEHOLDER_CATEGORIES = [
    "Zabezpieczenia Analogowe", "Zabezpieczenia Dwustanowe",
    "Zabezpieczenia Technologiczne", "Łączniki", "Banki Nastaw",
    "Zabezpieczenia silnikowe",
]

def test_empty_placeholder_categories_are_not_shown_at_all(qsettings):
    """feat/editor-modes-and-geometry §3: these six categories used to
    appear grayed out, labeled "(w przygotowaniu)" — a UI element declaring
    a feature that doesn't exist yet, the same class of problem as
    displaying a fabricated value. They're gone from the tree entirely now
    (the roadmap lives in REPORT.md instead) and return only once real
    blocks are registered under them."""
    _app()
    from logic_studio.ui.panels.library import LibraryPanel

    panel = LibraryPanel(settings=qsettings)
    top_level_labels = [panel.tree.topLevelItem(i).text(0) for i in range(panel.tree.topLevelItemCount())]

    for cat in _REMOVED_PLACEHOLDER_CATEGORIES:
        assert cat not in top_level_labels
        assert f"{cat} (w przygotowaniu)" not in top_level_labels

def test_search_matches_by_alias(qsettings):
    _app()
    from logic_studio.ui.panels.library import LibraryPanel, TYPE_ID_ROLE

    panel = LibraryPanel(settings=qsettings)
    panel.search_box.setText("opóźnienie")

    visible = []
    for i in range(panel.tree.topLevelItemCount()):
        root = panel.tree.topLevelItem(i)
        for j in range(root.childCount()):
            child = root.child(j)
            if not child.isHidden():
                visible.append(child.data(0, TYPE_ID_ROLE))

    assert "timer.ton" in visible
    assert "timer.tof" in visible
    assert "logic.and" not in visible  # unrelated block filtered out

def test_search_hides_empty_categories(qsettings):
    _app()
    from logic_studio.ui.panels.library import LibraryPanel

    panel = LibraryPanel(settings=qsettings)
    panel.search_box.setText("zzz_no_such_block_zzz")

    for cat, root in panel._category_roots.items():
        assert root.isHidden(), f"{cat} should be hidden when nothing in it matches"

def test_double_click_inserts_block_at_view_center(qsettings):
    _app()
    from logic_studio.ui.main_window import MainWindow

    m = MainWindow(settings=qsettings)
    m.scene.clear()

    lib = m.library_panel
    and_item = None
    for i in range(lib.tree.topLevelItemCount()):
        root = lib.tree.topLevelItem(i)
        for j in range(root.childCount()):
            child = root.child(j)
            if child.data(0, Qt.UserRole) == "logic.and":
                and_item = child

    assert and_item is not None
    lib._on_item_double_clicked(and_item, 0)

    assert len(m.project.blocks) == 1
    assert m.project.blocks[0].type_id == "logic.and"

    m.is_dirty = False
    m.close()

def test_recently_used_updates_on_insertion(qsettings):
    _app()
    from logic_studio.ui.main_window import MainWindow

    m = MainWindow(settings=qsettings)
    m.scene.clear()
    m.scene.add_block_from_library("logic.and", 0, 0)

    assert m.library_panel._recent_root.childCount() == 1
    assert m.library_panel._recent_root.child(0).data(0, Qt.UserRole) == "logic.and"
    assert m.library_panel._recent_list() == ["logic.and"]

    m.scene.add_block_from_library("logic.or", 100, 0)
    assert m.library_panel._recent_list() == ["logic.or", "logic.and"]

    m.is_dirty = False
    m.close()

def test_expand_state_persisted_across_instances(qsettings):
    _app()
    from logic_studio.ui.panels.library import LibraryPanel

    panel1 = LibraryPanel(settings=qsettings)
    root = panel1._category_roots["Timery"]
    root.setExpanded(False)  # triggers itemCollapsed -> persisted

    panel2 = LibraryPanel(settings=qsettings)
    assert panel2._category_roots["Timery"].isExpanded() is False

def test_drag_threshold_is_four_pixels():
    from logic_studio.ui.panels.library import DRAG_THRESHOLD_PX
    assert DRAG_THRESHOLD_PX == 4


def test_block_icon_is_cached():
    from logic_studio.ui import icons
    icon1 = icons.block_icon("logic.and")
    icon2 = icons.block_icon("logic.and")
    assert icon1 is icon2  # same cached QIcon instance

def test_block_icon_unknown_type_returns_null_icon():
    from logic_studio.ui import icons
    icon = icons.block_icon("no.such.block")
    assert icon.isNull()

def test_all_action_icons_render_without_crashing():
    _app()
    from logic_studio.ui import icons
    for name in ["new", "open", "save", "undo", "redo", "compile", "start",
                 "pause", "stop", "zoom_in", "zoom_out", "grid", "snap"]:
        icon = icons.action_icon(name)
        assert not icon.isNull()


def test_preview_panel_shows_library_selection():
    _app()
    from logic_studio.ui.panels.element_preview import ElementPreviewPanel
    from PySide6.QtCore import QSettings
    import tempfile, os

    settings = QSettings(os.path.join(tempfile.gettempdir(), "preview_test.ini"), QSettings.IniFormat)
    panel = ElementPreviewPanel(settings=settings)

    panel.show_type_id("logic.and3", source="library")
    assert panel.name_label.text() == "AND-3"
    assert panel.type_id_label.text() == "logic.and3"
    assert panel.pins_table.rowCount() == 4  # In1, In2, In3, Out

def test_preview_panel_canvas_selection_wins_over_library():
    _app()
    from logic_studio.ui.panels.element_preview import ElementPreviewPanel
    from logic_studio.blocks.logic_gates import OrGate
    from PySide6.QtCore import QSettings
    import tempfile, os

    settings = QSettings(os.path.join(tempfile.gettempdir(), "preview_test2.ini"), QSettings.IniFormat)
    panel = ElementPreviewPanel(settings=settings)

    block = OrGate()
    panel.show_block_instance(block)
    assert panel.type_id_label.text() == "logic.or"

    # A library click while a canvas block is selected must NOT override it (§6).
    panel.show_type_id("logic.and", source="library")
    assert panel.type_id_label.text() == "logic.or"

    panel.clear_canvas_selection()
    assert panel.name_label.text() == "Brak zaznaczenia"

def test_preview_panel_highlights_safety_relevant_pins():
    _app()
    from logic_studio.ui.panels.element_preview import ElementPreviewPanel
    from logic_studio.blocks.logic_gates import AndGate
    from PySide6.QtCore import QSettings
    import tempfile, os

    settings = QSettings(os.path.join(tempfile.gettempdir(), "preview_test3.ini"), QSettings.IniFormat)
    panel = ElementPreviewPanel(settings=settings)

    block = AndGate()
    block.outputs[0].safety_relevant = True
    panel.show_block_instance(block)

    out_row = len(block.inputs)  # outputs listed after inputs
    assert panel.pins_table.item(out_row, 3).text() == "istotne dla bezpieczeństwa"

def test_doc_block_icon_renders():
    _app()
    from logic_studio.ui import icons
    for tid in ("doc.text", "doc.note", "doc.section"):
        icon = icons.block_icon(tid)
        assert not icon.isNull()

def test_dokumentacja_category_is_last_in_library_tree(qsettings):
    """§9.8: Dokumentacja is a real, visible category (not hidden — it holds
    placeable canvas annotations), positioned after every functional
    category."""
    _app()
    from logic_studio.ui.panels.library import LibraryPanel

    panel = LibraryPanel(settings=qsettings)
    names = [panel.tree.topLevelItem(i).text(0) for i in range(panel.tree.topLevelItemCount())]
    assert "Dokumentacja" in names

    functional = [n for n in names if n != "Ostatnio używane" and "w przygotowaniu" not in n and n != "Dokumentacja"]
    assert names.index("Dokumentacja") > max(names.index(n) for n in functional)

def test_doc_search_alias_finds_all_three_doc_blocks(qsettings):
    _app()
    from logic_studio.ui.panels.library import LibraryPanel, TYPE_ID_ROLE

    panel = LibraryPanel(settings=qsettings)
    panel.search_box.setText("komentarz")

    visible = set()
    for i in range(panel.tree.topLevelItemCount()):
        root = panel.tree.topLevelItem(i)
        for j in range(root.childCount()):
            child = root.child(j)
            if not child.isHidden():
                visible.add(child.data(0, TYPE_ID_ROLE))

    assert {"doc.text", "doc.note", "doc.section"} <= visible

def test_pin_defaults_to_not_safety_relevant():
    from logic_studio.blocks.pin import Pin
    p = Pin("X", Pin.DIR_OUTPUT, Pin.TYPE_BOOLEAN)
    assert p.safety_relevant is False
