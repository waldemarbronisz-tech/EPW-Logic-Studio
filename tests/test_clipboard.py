"""feat/clipboard-and-align §1 — in-app clipboard: copy/cut/paste, with
connections preserved between copied blocks and dropped when they leave
the selection.
"""
import pytest
from PySide6.QtWidgets import QApplication

from logic_studio.blocks import register_builtin_blocks
from logic_studio.core.project import Project

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


def _block_items(window):
    from logic_studio.ui.canvas.block_item import BlockItem
    return [i for i in window.scene.items() if isinstance(i, BlockItem)]


# ---- §1.7 required tests --------------------------------------------------

def test_copy_paste_two_connected_blocks(qsettings):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("logic.and", 0, 0)
    window.scene.add_block_from_library("logic.not", 200, 0)
    and_block, not_block = window.project.blocks
    assert and_block.outputs[0].connect(not_block.inputs[0])

    for item in _block_items(window):
        item.setSelected(True)

    assert window.scene.copy_selected_items() is True
    window.scene.paste_clipboard()

    assert len(window.project.blocks) == 4
    uuids = [b.uuid for b in window.project.blocks]
    assert len(set(uuids)) == 4
    short_ids = [b.short_id for b in window.project.blocks]
    assert len(set(short_ids)) == 4

    # The pasted pair (the two most recently added blocks) must have their
    # OWN internal connection, pointing at each other's NEW pins — not the
    # originals'.
    pasted = window.project.blocks[2:]
    pasted_and = next(b for b in pasted if b.type_id == "logic.and")
    pasted_not = next(b for b in pasted if b.type_id == "logic.not")
    assert pasted_not.inputs[0].uuid in pasted_and.outputs[0].connections
    assert pasted_and.outputs[0].uuid in pasted_not.inputs[0].connections
    assert and_block.outputs[0].uuid not in pasted_not.inputs[0].connections
    assert not_block.inputs[0].uuid not in pasted_and.outputs[0].connections
    _close(window)

def test_copy_drops_connection_leaving_the_selection(qsettings):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("logic.and", 0, 0)
    window.scene.add_block_from_library("logic.not", 200, 0)
    and_block, not_block = window.project.blocks
    assert and_block.outputs[0].connect(not_block.inputs[0])

    # Select only the AND — its output connects to something OUTSIDE the selection.
    and_item = next(i for i in _block_items(window) if i.logic_block is and_block)
    and_item.setSelected(True)

    window.scene.copy_selected_items()
    window.scene.paste_clipboard()

    pasted_and = window.project.blocks[-1]
    assert pasted_and.type_id == "logic.and"
    assert pasted_and.outputs[0].connections == []
    _close(window)

def test_cut_then_undo_restores_blocks_and_connections(qsettings):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("logic.and", 0, 0)
    window.scene.add_block_from_library("logic.not", 200, 0)
    and_block, not_block = window.project.blocks
    assert and_block.outputs[0].connect(not_block.inputs[0])
    and_uuid, not_uuid = and_block.uuid, not_block.uuid

    for item in _block_items(window):
        item.setSelected(True)
    window.scene.cut_selected_items()

    assert len(window.project.blocks) == 0

    window._undo()

    assert len(window.project.blocks) == 2
    restored_uuids = {b.uuid for b in window.project.blocks}
    assert restored_uuids == {and_uuid, not_uuid}
    restored_and = next(b for b in window.project.blocks if b.uuid == and_uuid)
    restored_not = next(b for b in window.project.blocks if b.uuid == not_uuid)
    assert restored_not.inputs[0].uuid in restored_and.outputs[0].connections
    _close(window)

def test_pasting_three_times_does_not_stack_copies(qsettings):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("logic.and", 0, 0)
    _block_items(window)[0].setSelected(True)
    window.scene.copy_selected_items()

    window.scene.paste_clipboard()
    window.scene.paste_clipboard()
    window.scene.paste_clipboard()

    positions = [(b.x, b.y) for b in window.project.blocks[1:]]  # exclude the original
    assert len(positions) == 3
    assert len(set(positions)) == 3  # no two pasted copies share a position
    _close(window)


# ---- §1.5 action state -----------------------------------------------------

def test_cut_copy_disabled_with_no_selection(qsettings):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("logic.and", 0, 0)
    window.scene.clearSelection()
    assert window.act_cut.isEnabled() is False
    assert window.act_copy.isEnabled() is False
    _close(window)

def test_cut_copy_enabled_when_something_selected(qsettings):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("logic.and", 0, 0)
    _block_items(window)[0].setSelected(True)
    assert window.act_cut.isEnabled() is True
    assert window.act_copy.isEnabled() is True
    _close(window)

def test_paste_disabled_until_something_copied(qsettings):
    _app()
    window = _make_window(qsettings)
    assert window.act_paste.isEnabled() is False

    window.scene.add_block_from_library("logic.and", 0, 0)
    _block_items(window)[0].setSelected(True)
    window.scene.copy_selected_items()
    assert window.act_paste.isEnabled() is True
    _close(window)


# ---- §1.4 duplicate output-address warning ---------------------------------

def test_pasting_a_do_block_with_a_used_address_warns_and_keeps_the_address(qsettings):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("output.do", 0, 0)
    window.project.blocks[0].properties["Address"] = "ADA01.DO01"
    _block_items(window)[0].setSelected(True)

    window.scene.copy_selected_items()
    window.scene.paste_clipboard()

    pasted = window.project.blocks[-1]
    assert pasted.properties["Address"] == "ADA01.DO01"  # never silently cleared
    assert "powielonymi adresami" in window.statusBar().currentMessage()
    _close(window)

def test_pasting_a_do_block_with_a_free_address_does_not_warn(qsettings):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("output.do", 0, 0)
    window.project.blocks[0].properties["Address"] = ""  # deliberately unassigned
    _block_items(window)[0].setSelected(True)

    window.scene.copy_selected_items()
    window.scene.paste_clipboard()

    assert "powielonymi" not in window.statusBar().currentMessage()
    _close(window)


# ---- §1.6 Ctrl+D now preserves connections ---------------------------------

def test_duplicate_preserves_connections(qsettings):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("logic.and", 0, 0)
    window.scene.add_block_from_library("logic.not", 200, 0)
    and_block, not_block = window.project.blocks
    assert and_block.outputs[0].connect(not_block.inputs[0])

    for item in _block_items(window):
        item.setSelected(True)
    window.scene.duplicate_selected_items()

    assert len(window.project.blocks) == 4
    pasted = window.project.blocks[2:]
    pasted_and = next(b for b in pasted if b.type_id == "logic.and")
    pasted_not = next(b for b in pasted if b.type_id == "logic.not")
    assert pasted_not.inputs[0].uuid in pasted_and.outputs[0].connections
    _close(window)

def test_duplicate_selects_the_new_copies(qsettings):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("logic.and", 0, 0)
    original = window.project.blocks[0]
    _block_items(window)[0].setSelected(True)
    window.scene.duplicate_selected_items()

    from logic_studio.ui.canvas.block_item import BlockItem
    selected = [i for i in window.scene.selectedItems() if isinstance(i, BlockItem)]
    assert len(selected) == 1
    assert selected[0].logic_block.uuid != original.uuid
    _close(window)


# ---- properties copied unchanged ------------------------------------------

def test_paste_copies_properties_unchanged(qsettings):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("input.di", 0, 0)
    block = window.project.blocks[0]
    block.properties["Address"] = "ELA01.DI05"
    block.properties["Tag"] = "Q1"
    block.properties["Comment"] = "Wyłącznik główny"
    _block_items(window)[0].setSelected(True)

    window.scene.copy_selected_items()
    window.scene.paste_clipboard()

    pasted = window.project.blocks[-1]
    assert pasted.properties["Address"] == "ELA01.DI05"
    assert pasted.properties["Tag"] == "Q1"
    assert pasted.properties["Comment"] == "Wyłącznik główny"
    _close(window)


# ---- copy/paste is one undo entry ------------------------------------------

def test_paste_is_exactly_one_undo_entry(qsettings):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("logic.and", 0, 0)
    window.scene.add_block_from_library("logic.not", 200, 0)
    for item in _block_items(window):
        item.setSelected(True)
    window.scene.copy_selected_items()

    before = len(window.project.undo_stack)
    window.scene.paste_clipboard()
    assert len(window.project.undo_stack) == before + 1
    _close(window)

def test_cut_is_exactly_one_undo_entry(qsettings):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("logic.and", 0, 0)
    window.scene.add_block_from_library("logic.not", 200, 0)
    for item in _block_items(window):
        item.setSelected(True)

    before = len(window.project.undo_stack)
    window.scene.cut_selected_items()
    assert len(window.project.undo_stack) == before + 1
    _close(window)
