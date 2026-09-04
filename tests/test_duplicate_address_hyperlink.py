"""feat/duplicate-address-hyperlink — a block's own context menu can jump
directly to another block referencing the exact same signal (a duplicate
DI address, most commonly), rather than requiring a detour through the
Sygnały panel. Deliberately NOT a Validator error — see
AUDIT_REPORT.md §10 / MEMORY.md for why.
"""
import pytest
from PySide6.QtWidgets import QApplication, QMenu

from logic_studio.blocks import register_builtin_blocks
from logic_studio.ui.canvas.block_item import BlockItem

register_builtin_blocks()


def _app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _make_window(qsettings):
    from logic_studio.ui.main_window import MainWindow
    window = MainWindow(settings=qsettings)
    window.scene.clear()
    return window


def _close(window):
    window.is_dirty = False
    window.close()


def _item_for(window, block):
    return next(i for i in window.scene.items() if isinstance(i, BlockItem) and i.logic_block is block)


# ---- _duplicate_reference_blocks() ----------------------------------------

def test_two_blocks_with_the_same_address_reference_each_other(qsettings):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("input.di", 0, 0)
    window.scene.add_block_from_library("input.di", 200, 0)
    di1, di2 = window.project.blocks
    di1.properties["Address"] = "ELA01.DI01"
    di2.properties["Address"] = "ELA01.DI01"

    item1 = _item_for(window, di1)
    others = item1._duplicate_reference_blocks()

    assert [short_id for _u, short_id in others] == [di2.short_id]
    _close(window)

def test_a_unique_address_has_no_duplicates(qsettings):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("input.di", 0, 0)
    window.scene.add_block_from_library("input.di", 200, 0)
    di1, di2 = window.project.blocks
    di1.properties["Address"] = "ELA01.DI01"
    di2.properties["Address"] = "ELA01.DI02"

    item1 = _item_for(window, di1)
    assert item1._duplicate_reference_blocks() == []
    _close(window)

def test_a_block_with_no_signal_reference_has_no_duplicates(qsettings):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("logic.and", 0, 0)
    item = _item_for(window, window.project.blocks[0])
    assert item._duplicate_reference_blocks() == []
    _close(window)

def test_three_blocks_sharing_an_address_each_see_the_other_two(qsettings):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("input.di", 0, 0)
    window.scene.add_block_from_library("input.di", 200, 0)
    window.scene.add_block_from_library("input.di", 400, 0)
    for b in window.project.blocks:
        b.properties["Address"] = "ELA01.DI01"
    di1, di2, di3 = window.project.blocks

    item1 = _item_for(window, di1)
    others = {short_id for _u, short_id in item1._duplicate_reference_blocks()}
    assert others == {di2.short_id, di3.short_id}
    _close(window)

def test_works_for_bit_based_blocks_too_not_just_address(qsettings):
    """The feature isn't DI-specific — it reuses core/crossref.py's own
    signal resolution, which covers Address/Bit/Sygnał uniformly."""
    _app()
    window = _make_window(qsettings)
    window.project.settings["internal_bits"] = [{"name": "X", "type": "BOOL", "retentive": False}]
    window.scene.add_block_from_library("virtual.input", 0, 0)
    window.scene.add_block_from_library("virtual.input", 200, 0)
    vi1, vi2 = window.project.blocks
    vi1.properties["Bit"] = "X"
    vi2.properties["Bit"] = "X"

    item1 = _item_for(window, vi1)
    others = item1._duplicate_reference_blocks()
    assert [short_id for _u, short_id in others] == [vi2.short_id]
    _close(window)


# ---- populate_duplicate_reference_menu() ----------------------------------

def test_submenu_disabled_when_nothing_shares_the_address(qsettings):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("input.di", 0, 0)
    window.project.blocks[0].properties["Address"] = "ELA01.DI01"
    item = _item_for(window, window.project.blocks[0])

    menu = QMenu()
    submenu = item.populate_duplicate_reference_menu(menu)
    assert submenu.menuAction().isEnabled() is False
    assert submenu.actions() == []
    _close(window)

def test_submenu_enabled_and_lists_the_duplicate_by_short_id(qsettings):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("input.di", 0, 0)
    window.scene.add_block_from_library("input.di", 200, 0)
    di1, di2 = window.project.blocks
    di1.properties["Address"] = "ELA01.DI01"
    di2.properties["Address"] = "ELA01.DI01"
    item1 = _item_for(window, di1)

    menu = QMenu()
    submenu = item1.populate_duplicate_reference_menu(menu)
    assert submenu.menuAction().isEnabled() is True
    assert [a.text() for a in submenu.actions()] == [di2.short_id]
    _close(window)

def test_submenu_label_includes_tag_when_set(qsettings):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("input.di", 0, 0)
    window.scene.add_block_from_library("input.di", 200, 0)
    di1, di2 = window.project.blocks
    di1.properties["Address"] = "ELA01.DI01"
    di2.properties["Address"] = "ELA01.DI01"
    di2.properties["Tag"] = "Wyłącznik pomocniczy"
    item1 = _item_for(window, di1)

    menu = QMenu()
    submenu = item1.populate_duplicate_reference_menu(menu)
    assert submenu.actions()[0].text() == f"{di2.short_id} — Wyłącznik pomocniczy"
    _close(window)

def test_choosing_a_duplicate_action_jumps_to_and_selects_that_block(qsettings):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("input.di", 0, 0)
    window.scene.add_block_from_library("input.di", 300, 0)
    di1, di2 = window.project.blocks
    di1.properties["Address"] = "ELA01.DI01"
    di2.properties["Address"] = "ELA01.DI01"
    item1 = _item_for(window, di1)

    menu = QMenu()
    submenu = item1.populate_duplicate_reference_menu(menu)
    submenu.actions()[0].trigger()

    selected = [i for i in window.scene.selectedItems() if isinstance(i, BlockItem)]
    assert len(selected) == 1
    assert selected[0].logic_block.uuid == di2.uuid
    _close(window)

def test_submenu_is_always_present_in_the_real_context_menu_builder(qsettings):
    """contextMenuEvent() itself calls QMenu.exec() (modal — would hang
    forever in a headless test), so this exercises the exact same
    population path it uses instead of the real event handler."""
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("logic.and", 0, 0)
    item = _item_for(window, window.project.blocks[0])

    menu = QMenu()
    submenu = item.populate_duplicate_reference_menu(menu)
    assert submenu.title() == "Inne bloki tego samego sygnału"
    assert submenu.menuAction().isEnabled() is False  # a gate has no signal reference at all
    _close(window)
