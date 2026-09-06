"""feat/macro-blocks — the library tree's "Makrobloki" section
(ui/panels/library.py). See test_library_panel.py for the rest of the
library panel's behavior, unrelated to macros."""
import pytest
from PySide6.QtWidgets import QApplication

from logic_studio.blocks import register_builtin_blocks
from logic_studio.core.project import Project
from logic_studio.core.macros import set_definition

register_builtin_blocks()


def _app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _close(window):
    window.is_dirty = False
    window.close()


def _definition(name="MojMakro", n_in=1, n_out=1):
    return {
        "name": name,
        "blocks": [],
        "input_pins": [{"block_uuid": "b", "pin_name": f"In{i+1}", "data_type": "Boolean", "label": f"In{i+1}"} for i in range(n_in)],
        "output_pins": [{"block_uuid": "b", "pin_name": f"Out{i+1}", "data_type": "Boolean", "label": f"Out{i+1}"} for i in range(n_out)],
    }


def _macro_root(panel):
    from logic_studio.ui.panels.library import MACRO_LABEL
    for i in range(panel.tree.topLevelItemCount()):
        item = panel.tree.topLevelItem(i)
        if item.text(0) == MACRO_LABEL:
            return item
    return None


# ---- set_project() / _rebuild_macro_section() ------------------------------

def test_macro_root_hidden_when_no_project(qsettings):
    _app()
    from logic_studio.ui.panels.library import LibraryPanel
    panel = LibraryPanel(settings=qsettings)
    root = _macro_root(panel)
    assert root is not None
    assert root.isHidden()

def test_macro_root_hidden_when_project_has_no_definitions(qsettings):
    _app()
    from logic_studio.ui.panels.library import LibraryPanel
    panel = LibraryPanel(settings=qsettings)
    panel.set_project(Project())
    assert _macro_root(panel).isHidden()

def test_set_project_lists_existing_definitions(qsettings):
    _app()
    from logic_studio.ui.panels.library import LibraryPanel, TYPE_ID_ROLE
    p = Project()
    set_definition(p, "abc123", _definition("MojMakro"))

    panel = LibraryPanel(settings=qsettings)
    panel.set_project(p)

    root = _macro_root(panel)
    assert not root.isHidden()
    assert root.childCount() == 1
    child = root.child(0)
    assert child.text(0) == "MojMakro"
    assert child.data(0, TYPE_ID_ROLE) == "macro.abc123"

def test_set_project_swap_replaces_the_list(qsettings):
    _app()
    from logic_studio.ui.panels.library import LibraryPanel
    p1 = Project()
    set_definition(p1, "a", _definition("A"))
    p2 = Project()
    set_definition(p2, "b", _definition("B"))
    set_definition(p2, "c", _definition("C"))

    panel = LibraryPanel(settings=qsettings)
    panel.set_project(p1)
    assert _macro_root(panel).childCount() == 1

    panel.set_project(p2)
    root = _macro_root(panel)
    assert root.childCount() == 2
    names = {root.child(i).text(0) for i in range(root.childCount())}
    assert names == {"B", "C"}

def test_definitions_are_sorted_by_name(qsettings):
    _app()
    from logic_studio.ui.panels.library import LibraryPanel
    p = Project()
    set_definition(p, "z", _definition("Zebra"))
    set_definition(p, "a", _definition("Alpha"))

    panel = LibraryPanel(settings=qsettings)
    panel.set_project(p)
    root = _macro_root(panel)
    names = [root.child(i).text(0) for i in range(root.childCount())]
    assert names == ["Alpha", "Zebra"]


# ---- _display_name() / _description() / tooltip ----------------------------

def test_display_name_and_tooltip_reflect_the_real_definition(qsettings):
    _app()
    from logic_studio.ui.panels.library import LibraryPanel
    p = Project()
    set_definition(p, "abc", _definition("Blokada", n_in=2, n_out=1))

    panel = LibraryPanel(settings=qsettings)
    panel.set_project(p)
    child = _macro_root(panel).child(0)

    assert child.text(0) == "Blokada"
    assert "2 wej." in child.toolTip(0)
    assert "1 wyj." in child.toolTip(0)

def test_display_name_falls_back_to_def_id_for_dangling_reference(qsettings):
    """A macro instance placed via a stale type_id whose definition no
    longer exists — must show SOMETHING rather than crash."""
    _app()
    from logic_studio.ui.panels.library import LibraryPanel
    panel = LibraryPanel(settings=qsettings)
    panel.set_project(Project())
    assert panel._display_name("macro.doesnotexist") == "macro.doesnotexist"
    assert panel._description("macro.doesnotexist") == ""


# ---- search -----------------------------------------------------------------

def test_search_matches_macro_by_its_own_name(qsettings):
    _app()
    from logic_studio.ui.panels.library import LibraryPanel
    p = Project()
    set_definition(p, "abc", _definition("Blokada"))

    panel = LibraryPanel(settings=qsettings)
    panel.set_project(p)
    panel.search_box.setText("blokada")

    root = _macro_root(panel)
    assert not root.isHidden()
    assert not root.child(0).isHidden()

def test_search_hides_macro_root_when_nothing_matches(qsettings):
    _app()
    from logic_studio.ui.panels.library import LibraryPanel
    p = Project()
    set_definition(p, "abc", _definition("Blokada"))

    panel = LibraryPanel(settings=qsettings)
    panel.set_project(p)
    panel.search_box.setText("zzz_no_such_macro_zzz")

    assert _macro_root(panel).isHidden()


# ---- end-to-end via MainWindow / create_macro_from_selection() ------------

def test_creating_a_macro_refreshes_the_library_tree(qsettings):
    _app()
    from logic_studio.ui.main_window import MainWindow
    from logic_studio.ui.canvas.block_item import BlockItem

    window = MainWindow(settings=qsettings)
    window.scene.clear()
    window.scene.add_block_from_library("logic.and", 0, 0)
    for item in window.scene.items():
        if isinstance(item, BlockItem):
            item.setSelected(True)

    assert window.scene.create_macro_from_selection("Nowy") is True

    root = _macro_root(window.library_panel)
    assert not root.isHidden()
    assert root.childCount() == 1
    assert root.child(0).text(0) == "Nowy"
    _close(window)

def test_undo_after_macro_creation_removes_it_from_the_library_tree(qsettings):
    _app()
    from logic_studio.ui.main_window import MainWindow
    from logic_studio.ui.canvas.block_item import BlockItem

    window = MainWindow(settings=qsettings)
    window.scene.clear()
    window.scene.add_block_from_library("logic.and", 0, 0)
    for item in window.scene.items():
        if isinstance(item, BlockItem):
            item.setSelected(True)
    window.scene.create_macro_from_selection("Nowy")

    window._undo()

    root = _macro_root(window.library_panel)
    assert root.isHidden()
    _close(window)

def test_loading_a_new_project_clears_the_macro_section(qsettings):
    _app()
    from logic_studio.ui.main_window import MainWindow
    from logic_studio.ui.canvas.block_item import BlockItem

    window = MainWindow(settings=qsettings)
    window.scene.clear()
    window.scene.add_block_from_library("logic.and", 0, 0)
    for item in window.scene.items():
        if isinstance(item, BlockItem):
            item.setSelected(True)
    window.scene.create_macro_from_selection("Nowy")
    assert not _macro_root(window.library_panel).isHidden()

    window.is_dirty = False  # skip the unsaved-changes modal prompt
    window._new_project()

    assert _macro_root(window.library_panel).isHidden()
    _close(window)
