"""feat/signal-crossref §3 — navigation from the Sygnały panel to the
canvas, and back (canvas selection highlighting rows).
"""
import time

import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest

from logic_studio.blocks import register_builtin_blocks

register_builtin_blocks()


def _app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _row_of(panel, signal_id):
    """The leaf QTreeWidgetItem for `signal_id`, or None."""
    for leaf in panel._iter_leaves():
        if panel._signal_id_of(leaf) == signal_id:
            return leaf
    return None


def _make_window(qsettings):
    from logic_studio.ui.main_window import MainWindow
    window = MainWindow(settings=qsettings)
    window.scene.clear()
    return window


def _close(window):
    window.is_dirty = False  # avoid the real Unsaved-Changes modal on close()
    window.close()


# ---- §3.1 double-click ----------------------------------------------------

def test_double_click_jumps_to_writer_and_selects_it(qsettings):
    _app()
    window = _make_window(qsettings)
    do_item = window.scene.add_block_from_library("output.do", 0, 0)
    # add_block_from_library doesn't return the item in the current API —
    # find it back via the project's own block list instead.
    do_block = window.project.blocks[0]
    do_block.properties["Address"] = "ADA01.DO01"
    window.signals_panel.set_project(window.project)

    row = _row_of(window.signals_panel, "ADA01.DO01")
    assert row is not None
    window.signals_panel._on_item_double_clicked(row, 0)

    from logic_studio.ui.canvas.block_item import BlockItem
    selected = [i for i in window.scene.selectedItems() if isinstance(i, BlockItem)]
    assert len(selected) == 1
    assert selected[0].logic_block.uuid == do_block.uuid
    _close(window)

def test_double_click_with_no_writer_jumps_to_first_reader(qsettings):
    """A physical DI's "writer" is structurally always the device — double-
    click must fall through to the reader (the DI block itself)."""
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("input.di", 0, 0)
    di_block = window.project.blocks[0]
    di_block.properties["Address"] = "ELA01.DI01"
    window.signals_panel.set_project(window.project)

    row = _row_of(window.signals_panel, "ELA01.DI01")
    window.signals_panel._on_item_double_clicked(row, 0)

    from logic_studio.ui.canvas.block_item import BlockItem
    selected = [i for i in window.scene.selectedItems() if isinstance(i, BlockItem)]
    assert len(selected) == 1
    assert selected[0].logic_block.uuid == di_block.uuid
    _close(window)

def test_double_click_centers_the_view_on_the_block(qsettings):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("output.do", 500, 500)
    window.project.blocks[0].properties["Address"] = "ADA01.DO01"
    window.signals_panel.set_project(window.project)

    row = _row_of(window.signals_panel, "ADA01.DO01")
    window.signals_panel._on_item_double_clicked(row, 0)

    center = window.view.mapToScene(window.view.viewport().rect().center())
    # Roughly centered on the block (500,500 placement + block size) — a
    # loose bound is enough to prove centerOn() actually ran, without
    # coupling the test to exact block dimensions.
    assert abs(center.x() - 500) < 200
    assert abs(center.y() - 500) < 200
    _close(window)


# ---- §3.2 right-click reader menu -----------------------------------------

def test_reader_menu_is_none_when_no_readers(qsettings):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("output.do", 0, 0)
    window.project.blocks[0].properties["Address"] = "ADA01.DO01"
    window.signals_panel.set_project(window.project)

    menu = window.signals_panel._build_reader_menu("ADA01.DO01")
    assert menu is None
    _close(window)

def test_reader_menu_lists_every_reader(qsettings):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("input.di", 0, 0)
    window.scene.add_block_from_library("input.di", 100, 0)
    for b in window.project.blocks:
        b.properties["Address"] = "ELA01.DI01"
    window.signals_panel.set_project(window.project)

    menu = window.signals_panel._build_reader_menu("ELA01.DI01")
    assert menu is not None
    assert len(menu.actions()) == 2
    texts = [a.text() for a in menu.actions()]
    for block in window.project.blocks:
        assert any(block.short_id in t for t in texts)
    _close(window)

def test_reader_menu_label_includes_tag_when_set(qsettings):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("input.di", 0, 0)
    block = window.project.blocks[0]
    block.properties["Address"] = "ELA01.DI01"
    block.properties["Tag"] = "Wyłącznik główny"
    window.signals_panel.set_project(window.project)

    menu = window.signals_panel._build_reader_menu("ELA01.DI01")
    assert f"{block.short_id} — Wyłącznik główny" == menu.actions()[0].text()
    _close(window)

def test_choosing_a_reader_menu_action_jumps_to_that_block(qsettings):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("input.di", 0, 0)
    window.scene.add_block_from_library("input.di", 300, 0)
    for b in window.project.blocks:
        b.properties["Address"] = "ELA01.DI01"
    window.signals_panel.set_project(window.project)

    menu = window.signals_panel._build_reader_menu("ELA01.DI01")
    target_block = window.project.blocks[1]
    target_action = next(a for a in menu.actions() if target_block.short_id in a.text())
    target_action.trigger()

    from logic_studio.ui.canvas.block_item import BlockItem
    selected = [i for i in window.scene.selectedItems() if isinstance(i, BlockItem)]
    assert len(selected) == 1
    assert selected[0].logic_block.uuid == target_block.uuid
    _close(window)


# ---- §3.3 canvas selection highlights rows --------------------------------

def test_selecting_a_block_highlights_its_signal_row(qsettings):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("output.do", 0, 0)
    window.scene.add_block_from_library("output.do", 200, 0)
    window.project.blocks[0].properties["Address"] = "ADA01.DO01"
    window.project.blocks[1].properties["Address"] = "ADA01.DO02"
    window.signals_panel.set_project(window.project)

    from logic_studio.ui.canvas.block_item import BlockItem
    items = [i for i in window.scene.items() if isinstance(i, BlockItem)]
    target = next(i for i in items if i.logic_block.properties["Address"] == "ADA01.DO01")
    target.setSelected(True)  # triggers scene.selectionChanged -> highlight_blocks wiring

    leaf_hit = _row_of(window.signals_panel, "ADA01.DO01")
    leaf_miss = _row_of(window.signals_panel, "ADA01.DO02")
    from PySide6.QtGui import QColor
    assert leaf_hit.background(0).color() == QColor(200, 220, 255)
    assert leaf_miss.background(0).color() != QColor(200, 220, 255)
    _close(window)

def test_highlight_is_never_a_scroll():
    """highlight_blocks() must only ever touch cell backgrounds — no
    scrollTo/centerOn/selectRow call anywhere in it (that's §3.1's job,
    not §3.3's)."""
    import inspect
    from logic_studio.ui.panels.signals import SignalsPanel
    source = inspect.getsource(SignalsPanel.highlight_blocks)
    assert "scrollTo" not in source
    assert "centerOn" not in source
    assert "selectRow" not in source


# ---- pulse highlight --------------------------------------------------------

def test_pulse_highlight_overlay_is_added_then_removed(qsettings):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("output.do", 0, 0)
    window.project.blocks[0].properties["Address"] = "ADA01.DO01"
    window.signals_panel.set_project(window.project)

    from logic_studio.ui.canvas.block_item import BlockItem
    item = next(i for i in window.scene.items() if isinstance(i, BlockItem))

    from PySide6.QtWidgets import QGraphicsRectItem
    before = len([i for i in window.scene.items() if isinstance(i, QGraphicsRectItem)])
    window.signals_panel._pulse_highlight(window.scene, item, cycles=2, interval_ms=20)
    during = len([i for i in window.scene.items() if isinstance(i, QGraphicsRectItem)])
    assert during == before + 1

    # CI flake fix (feat/clipboard-and-align, diagnosed from a real CI
    # failure — the SAME commit passed on `pull_request` and failed on
    # `push` 39 minutes later): a single fixed QTest.qWait(150) then one
    # check is exactly the shape of test that goes flaky under runner
    # contention — the ~40ms animation (cycles=2 * interval_ms=20) is
    # normally done well within 150ms, but a stalled/throttled CI runner
    # can occasionally miss even a 3.75x margin. Poll instead, with a much
    # larger ceiling than the animation could plausibly need, breaking out
    # the moment the overlay is actually gone rather than waiting a fixed
    # span and checking exactly once.
    deadline = time.monotonic() + 2.0
    after = during
    while time.monotonic() < deadline:
        QTest.qWait(20)
        after = len([i for i in window.scene.items() if isinstance(i, QGraphicsRectItem)])
        if after == before:
            break
    assert after == before
    _close(window)
