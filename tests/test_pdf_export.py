"""feat/pdf-export — ui/pdf_export.py. `signal_list_rows()` is pure,
Qt-free logic tested in isolation; export_schematic_to_pdf() and the
page-layout helpers are genuinely Qt-dependent (QPainter/QPdfWriter/
QGraphicsScene) and tested end-to-end against real objects, matching
this module's own docstring on why it can't be split the Qt-free-core
way most of this app's other features are."""
import pytest
from PySide6.QtWidgets import QApplication, QFileDialog
from PySide6.QtGui import QPainter

from logic_studio.blocks import register_builtin_blocks
from logic_studio.core.crossref import build_crossref
from logic_studio.ui.pdf_export import (
    signal_list_rows, export_schematic_to_pdf, _draw_signal_list_pages,
)

register_builtin_blocks()


def _app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _close(window):
    window.is_dirty = False
    window.close()


def _make_window(qsettings):
    from logic_studio.ui.main_window import MainWindow
    window = MainWindow(settings=qsettings)
    window.scene.clear()
    return window


class _FakeWriter:
    """A plain Python double for QPdfWriter — used only to test
    _draw_signal_list_pages()'s OWN pagination logic in isolation,
    without needing a real file or a real (much taller) A4 page to force
    an overflow. Paired with a genuine, if never begin()'d-on-a-device,
    QPainter — Qt tolerates drawText() calls on an inactive painter as a
    silent no-op, confirmed empirically before relying on it here."""
    def __init__(self, width=2000, height=600):
        self._width = width
        self._height = height
        self.new_page_count = 0

    def width(self):
        return self._width

    def height(self):
        return self._height

    def newPage(self):
        self.new_page_count += 1


# ---- signal_list_rows() (pure logic) --------------------------------

def test_signal_list_rows_empty_crossref():
    assert signal_list_rows({}) == []

def test_signal_list_rows_reflects_a_real_project(qsettings):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("input.di", 0, 0)
    di = window.project.blocks[0]
    di.properties["Address"] = "ELA01.DI01"

    rows = signal_list_rows(build_crossref(window.project))

    assert len(rows) == 1
    signal_id, kind, data_type, label, writers, readers = rows[0]
    assert signal_id == "ELA01.DI01"
    assert kind == "DI"
    assert readers == di.short_id
    _close(window)

def test_signal_list_rows_sorted_by_signal_id(qsettings):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("input.di", 0, 0)
    window.scene.add_block_from_library("input.di", 200, 0)
    di1, di2 = window.project.blocks
    di1.properties["Address"] = "ELA01.DI05"
    di2.properties["Address"] = "ELA01.DI02"

    rows = signal_list_rows(build_crossref(window.project))
    ids = [r[0] for r in rows]
    assert ids == sorted(ids)
    _close(window)


# ---- _draw_signal_list_pages() pagination (isolated from file I/O) ------

def test_pagination_triggers_new_page_when_content_overflows():
    _app()
    painter = QPainter()
    writer = _FakeWriter(height=600)
    rows = [(f"SIG{i}", "DI", "BOOL", "", "", "") for i in range(50)]

    _draw_signal_list_pages(painter, writer, rows)

    assert writer.new_page_count > 0

def test_no_pagination_for_a_short_list():
    _app()
    painter = QPainter()
    writer = _FakeWriter(height=2000)
    rows = [("SIG1", "DI", "BOOL", "", "", "")]

    _draw_signal_list_pages(painter, writer, rows)

    assert writer.new_page_count == 0


# ---- export_schematic_to_pdf() end-to-end -------------------------------

def test_export_creates_a_non_empty_pdf_file(qsettings, tmp_path):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("input.di", 0, 0)
    window.scene.add_block_from_library("output.do", 200, 0)
    path = str(tmp_path / "out.pdf")

    export_schematic_to_pdf(window.scene, window.project, path)

    assert (tmp_path / "out.pdf").exists()
    assert (tmp_path / "out.pdf").stat().st_size > 0
    _close(window)

def test_export_works_for_an_empty_project(qsettings, tmp_path):
    """No blocks placed at all — must still produce a valid (title-block-
    only) file instead of crashing on an empty itemsBoundingRect()."""
    _app()
    window = _make_window(qsettings)
    path = str(tmp_path / "empty.pdf")

    export_schematic_to_pdf(window.scene, window.project, path)

    assert (tmp_path / "empty.pdf").exists()
    assert (tmp_path / "empty.pdf").stat().st_size > 0
    _close(window)

def test_export_clears_the_selection_before_rendering(qsettings, tmp_path):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("logic.and", 0, 0)
    from logic_studio.ui.canvas.block_item import BlockItem
    item = next(i for i in window.scene.items() if isinstance(i, BlockItem))
    item.setSelected(True)
    path = str(tmp_path / "out.pdf")

    export_schematic_to_pdf(window.scene, window.project, path)

    assert not item.isSelected()
    _close(window)

def test_export_without_signal_list_skips_crossref(qsettings, tmp_path, monkeypatch):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("input.di", 0, 0)
    path = str(tmp_path / "out.pdf")

    called = []
    monkeypatch.setattr("logic_studio.core.crossref.build_crossref", lambda p: called.append(True) or {})

    export_schematic_to_pdf(window.scene, window.project, path, include_signal_list=False)

    assert called == []
    _close(window)

def test_export_with_signal_list_produces_a_larger_file(qsettings, tmp_path):
    """Not a precise content check (no PDF parser in requirements.txt),
    but a reasonable sanity signal that the extra page(s) actually got
    written: strictly more bytes than the same schematic without one."""
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("input.di", 0, 0)
    di = window.project.blocks[0]
    di.properties["Address"] = "ELA01.DI01"

    path_without = str(tmp_path / "without.pdf")
    export_schematic_to_pdf(window.scene, window.project, path_without, include_signal_list=False)

    path_with = str(tmp_path / "with.pdf")
    export_schematic_to_pdf(window.scene, window.project, path_with, include_signal_list=True)

    assert (tmp_path / "with.pdf").stat().st_size > (tmp_path / "without.pdf").stat().st_size
    _close(window)


# ---- MainWindow._export_pdf() wiring ------------------------------------

def test_export_pdf_action_creates_the_chosen_file(qsettings, tmp_path, monkeypatch):
    _app()
    window = _make_window(qsettings)
    window.scene.add_block_from_library("input.di", 0, 0)
    path = str(tmp_path / "chosen.pdf")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (path, "")))

    window._export_pdf()

    assert (tmp_path / "chosen.pdf").exists()
    _close(window)

def test_export_pdf_action_appends_extension_if_missing(qsettings, tmp_path, monkeypatch):
    _app()
    window = _make_window(qsettings)
    path_no_ext = str(tmp_path / "chosen")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (path_no_ext, "")))

    window._export_pdf()

    assert (tmp_path / "chosen.pdf").exists()
    _close(window)

def test_export_pdf_action_is_a_noop_when_dialog_is_cancelled(qsettings, monkeypatch):
    _app()
    window = _make_window(qsettings)
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: ("", "")))

    window._export_pdf()  # must not raise

    _close(window)

def test_export_pdf_action_normalizes_out_of_a_macro_edit_view_first(qsettings, tmp_path, monkeypatch):
    """Same reasoning as compile_project()/_save_project(): the export
    must always document the TRUE top-level project, never whatever a
    macro's own breadcrumb edit view happens to be showing."""
    _app()
    window = _make_window(qsettings)
    exited = []
    monkeypatch.setattr(window, "_exit_all_macro_levels", lambda: exited.append(True))
    path = str(tmp_path / "out.pdf")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (path, "")))

    window._export_pdf()

    assert exited == [True]
    _close(window)

def test_export_pdf_action_reports_errors_via_a_message_box(qsettings, tmp_path, monkeypatch):
    _app()
    window = _make_window(qsettings)
    path = str(tmp_path / "out.pdf")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (path, "")))
    monkeypatch.setattr(
        "logic_studio.ui.pdf_export.export_schematic_to_pdf",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    from PySide6.QtWidgets import QMessageBox
    boxes = []
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: boxes.append(a) or QMessageBox.Ok))

    window._export_pdf()  # must not raise

    assert len(boxes) == 1
    _close(window)
