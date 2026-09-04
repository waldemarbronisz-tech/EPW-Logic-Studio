"""Signal Watch panel (feat/signal-watch) — pins arbitrary signals (physical
DI/DO, analog AI/AO, internal bits/registers, system signals) for continuous
monitoring during simulation, independent of whatever is currently selected
on the canvas or in the library. Built on core/watch.py, the same
core-logic/Qt-panel split as core/crossref.py vs. ui/panels/signals.py.

The trend column is a small, procedurally-drawn (QPainter) strip chart —
zero charting-library dependency, the same philosophy already used for
ui/canvas/shapes.py's block shapes and ui/icons.py's library icons.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QTableWidget,
    QTableWidgetItem, QAbstractItemView, QHeaderView, QDialog,
)
from PySide6.QtGui import QPainter, QPen, QColor, QKeySequence
from PySide6.QtCore import Qt, Signal, QSettings, QPointF

from logic_studio.ui.canvas import style as canvas_style
from logic_studio.core import watch
from logic_studio.core.crossref import (
    KIND_PHYSICAL_DI, KIND_PHYSICAL_DO, KIND_ANALOG_IN, KIND_ANALOG_OUT,
    KIND_INTERNAL_BIT, KIND_INTERNAL_REG, KIND_SYSTEM,
)

KIND_ROLE = Qt.UserRole
SIGNAL_ID_ROLE = Qt.UserRole + 1

# Short, table-friendly labels for each kind — mirrors the letter-prefix
# convention core/short_id.py already uses for blocks (g12, i3, ...), applied
# here to signal namespaces instead of block categories.
_KIND_LABELS = {
    KIND_PHYSICAL_DI: "DI",
    KIND_PHYSICAL_DO: "DO",
    KIND_ANALOG_IN: "AI",
    KIND_ANALOG_OUT: "AO",
    KIND_INTERNAL_BIT: "M",
    KIND_INTERNAL_REG: "MW",
    KIND_SYSTEM: "SYS",
}

_COL_KIND, _COL_ID, _COL_DESC, _COL_VALUE, _COL_TREND = range(5)


class _Sparkline(QWidget):
    """Fixed-size scrolling strip chart of one watched signal's recent
    samples. Boolean signals draw a 0/1 step trace; analog signals scale to
    the min/max actually SEEN so far (not a declared range — a watch can
    point at any signal, most of which have no declared range at all)."""

    # feat/signal-watch: sized for the bottom output_panel strip (canvas-
    # width, shared with Compiler/Warnings/Errors/Runtime), not the 300px
    # left sidebar this panel originally lived in — see main_window.py's
    # WatchPanel wiring comment.
    WIDTH = 240
    HEIGHT = 32
    MAX_SAMPLES = 200

    def __init__(self, is_boolean: bool, parent=None):
        super().__init__(parent)
        self.setFixedSize(self.WIDTH, self.HEIGHT)
        self.is_boolean = is_boolean
        self._samples = []  # newest last; entries may be None (unresolved)

    def add_sample(self, value):
        self._samples.append(value)
        if len(self._samples) > self.MAX_SAMPLES:
            self._samples.pop(0)
        self.update()

    def clear_samples(self):
        self._samples = []
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        painter.fillRect(self.rect(), canvas_style.COLOR_BACKGROUND)
        painter.setPen(QPen(canvas_style.COLOR_GRID_MINOR, 1))
        painter.drawRect(0, 0, self.WIDTH - 1, self.HEIGHT - 1)

        n = len(self._samples)
        if n < 2:
            return

        step = (self.WIDTH - 4) / max(1, self.MAX_SAMPLES - 1)
        start_x = self.WIDTH - 2 - (n - 1) * step
        top, bottom = 3, self.HEIGHT - 3

        if self.is_boolean:
            painter.setPen(QPen(canvas_style.COLOR_LOGIC_HIGH, 1.5))
            points = []
            for i, v in enumerate(self._samples):
                if v is None:
                    continue
                x = start_x + i * step
                y = top if v else bottom
                points.append(QPointF(x, y))
            for a, b in zip(points, points[1:]):
                painter.drawLine(a, b)
            return

        numeric = [v for v in self._samples if isinstance(v, (int, float))]
        if len(numeric) < 2:
            return
        lo, hi = min(numeric), max(numeric)
        span = (hi - lo) or 1.0
        painter.setPen(QPen(canvas_style.COLOR_ANALOG_VALUE, 1.5))
        points = []
        for i, v in enumerate(self._samples):
            if not isinstance(v, (int, float)):
                continue
            x = start_x + i * step
            y = bottom - ((v - lo) / span) * (bottom - top)
            points.append(QPointF(x, y))
        for a, b in zip(points, points[1:]):
            painter.drawLine(a, b)


class WatchPanel(QWidget):
    """Table of pinned signals: kind, address/name, description, live
    value, trend. "Dodaj..." reuses SignalPickerDialog (the same picker
    every "Bit"/"Sygnał"/"Address" property already uses) so adding a watch
    never means a second, independently-maintained way to browse signals."""

    # Emitted after a watch is added/removed (project.settings mutated) —
    # MainWindow connects this to set_dirty(), the same pattern SimulationPanel's
    # step_requested uses for "this panel changed something MainWindow owns."
    changed = Signal()

    def __init__(self, project=None, parent=None, settings=None):
        super().__init__(parent)
        self.settings = settings if settings is not None else QSettings("BroniszLabs", "EPW Logic Studio")
        self.project = project

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        toolbar = QHBoxLayout()
        self.add_btn = QPushButton("Dodaj...")
        self.add_btn.clicked.connect(self._on_add_clicked)
        self.remove_btn = QPushButton("Usuń")
        self.remove_btn.setEnabled(False)
        self.remove_btn.clicked.connect(self._on_remove_clicked)
        toolbar.addWidget(self.add_btn)
        toolbar.addWidget(self.remove_btn)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Typ", "Sygnał", "Opis", "Wartość", "Trend"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        # feat/signal-watch: this panel lives in the bottom output_panel
        # strip (canvas width), not a 300px sidebar — column widths sized
        # accordingly: Typ/Wartość narrow-fixed, Sygnał a sensible fixed
        # default (still user-resizable), Opis takes whatever's left, Trend
        # fixed to the sparkline's own size plus a little breathing room.
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(_COL_KIND, QHeaderView.Fixed)
        header.setSectionResizeMode(_COL_ID, QHeaderView.Interactive)
        header.setSectionResizeMode(_COL_DESC, QHeaderView.Stretch)
        header.setSectionResizeMode(_COL_VALUE, QHeaderView.Fixed)
        header.setSectionResizeMode(_COL_TREND, QHeaderView.Fixed)
        self.table.setColumnWidth(_COL_KIND, 48)
        self.table.setColumnWidth(_COL_ID, 160)
        self.table.setColumnWidth(_COL_VALUE, 90)
        self.table.setColumnWidth(_COL_TREND, _Sparkline.WIDTH + 12)
        self.table.verticalHeader().setDefaultSectionSize(_Sparkline.HEIGHT + 8)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self.table)

        self.empty_label = QLabel('Brak obserwowanych sygnałów — kliknij "Dodaj...".')
        self.empty_label.setStyleSheet(_rgb_style("color", canvas_style.COLOR_COMMENT_TEXT))
        layout.addWidget(self.empty_label)

        self.set_project(project)

    # ---- project wiring -----------------------------------------------------

    def set_project(self, project):
        """Rebuild every row from project.settings["watched_signals"] — call
        on load/new/undo/redo, exactly like every other project-derived
        panel's set_project()."""
        self.project = project
        self.table.setRowCount(0)
        watches = watch.get_watches(project) if project else []
        for entry in watches:
            self._append_row(entry["kind"], entry["signal_id"])
        self._update_empty_state()
        self._on_selection_changed()

    def refresh_values(self, io_provider, now_ms: int = 0):
        """Pulls one fresh sample for every row from `io_provider` and
        appends it to that row's sparkline — called once per scan
        (MainWindow._run_scan(), the same choke point SimulationPanel's
        DI/DO/AI/AO sync already goes through). A no-op with zero rows, so
        it's always safe to call regardless of whether anything is
        watched."""
        if self.project is None:
            return
        for row in range(self.table.rowCount()):
            kind = self.table.item(row, _COL_KIND).data(KIND_ROLE)
            signal_id = self.table.item(row, _COL_ID).data(SIGNAL_ID_ROLE)
            value = watch.read_value(self.project, io_provider, kind, signal_id, now_ms)
            self._set_value_cell(row, value)
            sparkline = self.table.cellWidget(row, _COL_TREND)
            if sparkline is not None:
                sparkline.add_sample(value)

    # ---- row construction -----------------------------------------------------

    def _append_row(self, kind: str, signal_id: str):
        row = self.table.rowCount()
        self.table.insertRow(row)

        kind_item = QTableWidgetItem(_KIND_LABELS.get(kind, kind))
        kind_item.setData(KIND_ROLE, kind)
        self.table.setItem(row, _COL_KIND, kind_item)

        id_item = QTableWidgetItem(signal_id)
        id_item.setData(SIGNAL_ID_ROLE, signal_id)
        self.table.setItem(row, _COL_ID, id_item)

        desc = watch.describe_watch(self.project, kind, signal_id) if self.project else ""
        self.table.setItem(row, _COL_DESC, QTableWidgetItem(desc))

        self.table.setItem(row, _COL_VALUE, QTableWidgetItem("-"))
        self.table.item(row, _COL_VALUE).setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

        is_boolean = watch.is_boolean_kind(self.project, kind, signal_id) if self.project else True
        self.table.setCellWidget(row, _COL_TREND, _Sparkline(is_boolean))

    def _set_value_cell(self, row: int, value):
        item = self.table.item(row, _COL_VALUE)
        if value is None:
            item.setText("-")
        elif isinstance(value, bool):
            item.setText("1" if value else "0")
        elif isinstance(value, float):
            item.setText(f"{value:.2f}")
        else:
            item.setText(str(value))

    def _update_empty_state(self):
        empty = self.table.rowCount() == 0
        self.table.setVisible(not empty)
        self.empty_label.setVisible(empty)

    # ---- add / remove ---------------------------------------------------------

    def _on_add_clicked(self):
        if self.project is None:
            return
        from logic_studio.ui.signal_picker import SignalPickerDialog
        from logic_studio.core.crossref import classify_signal_id

        dialog = SignalPickerDialog(self.project, value_type=None, parent=self)
        if dialog.exec() != QDialog.Accepted:
            return
        signal_id = dialog.selected_signal_id()
        coarse_kind = dialog.selected_kind()
        if not signal_id or not coarse_kind:
            return

        kind = classify_signal_id(self.project, coarse_kind, signal_id)
        if watch.is_watched(self.project, kind, signal_id):
            return  # already watched — nothing changed, nothing to push
        self.project.push_state()
        watch.add_watch(self.project, kind, signal_id)
        self._append_row(kind, signal_id)
        self._update_empty_state()
        self.changed.emit()

    def _on_remove_clicked(self):
        """One undo entry for the whole selection, regardless of row
        count — the same pattern as scene.py's delete_selected_items()."""
        rows = sorted({idx.row() for idx in self.table.selectedIndexes()}, reverse=True)
        if not rows or self.project is None:
            return
        self.project.push_state()
        removed_any = False
        for row in rows:
            kind = self.table.item(row, _COL_KIND).data(KIND_ROLE)
            signal_id = self.table.item(row, _COL_ID).data(SIGNAL_ID_ROLE)
            if watch.remove_watch(self.project, kind, signal_id):
                removed_any = True
            self.table.removeRow(row)
        self._update_empty_state()
        if removed_any:
            self.changed.emit()

    def _on_selection_changed(self):
        self.remove_btn.setEnabled(bool(self.table.selectedIndexes()))

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.Delete) and self.remove_btn.isEnabled():
            self._on_remove_clicked()
            event.accept()
            return
        super().keyPressEvent(event)


def _rgb_style(prop, qcolor):
    return f"{prop}: rgb({qcolor.red()},{qcolor.green()},{qcolor.blue()});"
