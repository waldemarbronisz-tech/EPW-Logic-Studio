"""feat/help-system §7.6 (context) and general UI-level smoke coverage
for ui/help_window.py + its MainWindow wiring — everything core/
help_content.py/block_catalog.py/shortcuts.py itself already covers
headlessly lives in test_help_content.py/test_block_catalog.py instead;
this file is specifically the Qt layer on top.
"""
from PySide6.QtWidgets import QApplication

from logic_studio.blocks import register_builtin_blocks
from logic_studio.ui.help_window import HelpWindow

register_builtin_blocks()


def _app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _make_window(qsettings):
    _app()
    from logic_studio.ui.main_window import MainWindow
    window = MainWindow(settings=qsettings)
    window.scene.clear()
    return window


def _close(window):
    window.is_dirty = False
    window.close()


# ---- HelpWindow on its own -------------------------------------------------

def test_help_window_opens_on_welcome_by_default(qsettings):
    _app()
    win = HelpWindow(settings=qsettings)
    assert "Witamy" in win.windowTitle()
    win.close()

def test_help_window_navigation_updates_title_and_history(qsettings):
    _app()
    win = HelpWindow(settings=qsettings)
    win.navigate_to("block:logic.and")
    assert "AND" in win.windowTitle()
    win.navigate_to("concept_labels")
    win._go_back()
    assert "AND" in win.windowTitle()
    win._go_forward()
    assert "Etykiety" in win.windowTitle()
    win.close()

def test_back_forward_buttons_reflect_history_position(qsettings):
    _app()
    win = HelpWindow(settings=qsettings)
    assert not win.btn_back.isEnabled()
    assert not win.btn_forward.isEnabled()
    win.navigate_to("concept_labels")
    assert win.btn_back.isEnabled()
    assert not win.btn_forward.isEnabled()
    win._go_back()
    assert not win.btn_back.isEnabled()
    assert win.btn_forward.isEnabled()
    win.close()

def test_hide_toggle_hides_and_restores_the_tree(qsettings):
    _app()
    win = HelpWindow(settings=qsettings)
    win.show()  # isVisible() is always False for an unshown top-level widget
    assert win.tabs.isVisible()
    win._toggle_left_panel()
    assert not win.tabs.isVisible()
    win._toggle_left_panel()
    assert win.tabs.isVisible()
    win.close()

def test_contents_tree_has_a_block_catalog_chapter_with_categories(qsettings):
    _app()
    win = HelpWindow(settings=qsettings)
    top_titles = [win.tree.topLevelItem(i).text(0) for i in range(win.tree.topLevelItemCount())]
    assert "Katalog bloków" in top_titles
    catalog_item = win.tree.topLevelItem(top_titles.index("Katalog bloków"))
    assert catalog_item.childCount() > 0
    # a category node's own children are individual block types
    first_category = catalog_item.child(0)
    assert first_category.childCount() > 0
    win.close()

def test_block_topic_embeds_a_graphical_icon(qsettings):
    """§2.1: "podgląd graficzny renderowany tym samym kodem co kanwa" --
    regression test for a real, silent rendering bug found while taking
    a manual screenshot: Qt's Markdown-to-HTML converter drops an image
    link whose alt text is empty (`![](data:...)`) with no error at all
    -- confirmed directly, including for a plain http(s) URL, not just
    a data: one. A non-block topic must NOT get an image spliced in."""
    _app()
    win = HelpWindow(settings=qsettings)
    win.navigate_to("block:logic.and")
    assert "<img" in win.viewer.toHtml()
    win.navigate_to("concept_labels")
    assert "<img" not in win.viewer.toHtml()
    win.close()

def test_geometry_is_restored_from_settings(qsettings):
    """Exact pixel dimensions aren't guaranteed to round-trip through
    saveGeometry()/restoreGeometry() on every windowing platform (the
    offscreen QPA plugin included, with no real window manager involved)
    -- what's actually being tested is that SOME persisted geometry (not
    just the plain 780x540 default) got applied at all."""
    _app()
    win1 = HelpWindow(settings=qsettings)
    win1.resize(900, 650)
    win1.close()  # persists geometry via closeEvent
    assert qsettings.value("help_window/geometry") is not None

    win2 = HelpWindow(settings=qsettings)
    assert (win2.width(), win2.height()) != (780, 540)
    win2.close()

def test_garbage_geometry_falls_back_to_a_sane_default(qsettings):
    qsettings.setValue("help_window/geometry", b"not a real geometry blob")
    _app()
    win = HelpWindow(settings=qsettings)
    assert win.width() >= 200
    assert win.height() >= 150
    win.close()


# ---- MainWindow wiring (§5/§6) ---------------------------------------------

def test_f1_with_no_selection_opens_welcome(qsettings):
    window = _make_window(qsettings)
    window._show_help()
    assert "Witamy" in window._help_window.windowTitle()
    _close(window)

def test_f1_with_one_block_selected_opens_that_blocks_catalog_page(qsettings):
    window = _make_window(qsettings)
    window.scene.add_block_from_library("logic.and", 0, 0)
    from logic_studio.ui.canvas.block_item import BlockItem
    item = next(i for i in window.scene.items() if isinstance(i, BlockItem))
    item.setSelected(True)

    window._show_help()

    assert "AND" in window._help_window.windowTitle()
    _close(window)

def test_f1_while_editing_a_macro_opens_the_macro_concept_topic(qsettings):
    window = _make_window(qsettings)
    window.current_macro_def_id = "some-macro-def-id"
    assert window._context_help_topic() == "concept_macros"
    _close(window)

def test_f1_while_simulation_running_opens_the_simulation_guide(qsettings):
    window = _make_window(qsettings)
    from logic_studio.engine.execution import ExecutionState
    window.engine.state = ExecutionState.RUNNING
    assert window._context_help_topic() == "guide_simulation"
    _close(window)

def test_help_window_is_reused_across_repeated_f1_presses(qsettings):
    window = _make_window(qsettings)
    window._show_help()
    first = window._help_window
    window._show_help()
    assert window._help_window is first
    _close(window)

def test_more_info_button_in_element_preview_opens_help_on_that_block(qsettings):
    window = _make_window(qsettings)
    window.element_preview.show_type_id("logic.or")
    window.element_preview.more_info_btn.click()
    assert "OR" in window._help_window.windowTitle()
    _close(window)

def test_export_block_catalog_menu_action_exists_and_is_wired(qsettings):
    window = _make_window(qsettings)
    assert window.act_export_block_catalog.text() == "Eksportuj katalog bloków..."
    assert window.act_export_block_catalog.receivers("2triggered()") > 0
    _close(window)

def test_help_menu_actions_all_have_a_connected_handler(qsettings):
    """§6: 'Usuń wszystko, co nie ma podpiętego działania' -- verified
    structurally: every action this menu holds must have at least one
    receiver connected to its triggered signal."""
    window = _make_window(qsettings)
    for action in (window.act_help, window.act_help_catalog, window.act_help_shortcuts,
                   window.act_export_block_catalog, window.act_about):
        assert action.receivers("2triggered()") > 0, f"{action.text()!r} has no connected handler"
    _close(window)
