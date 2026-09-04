"""Signal Watch panel (feat/signal-watch) — pins arbitrary signals (physical
DI/DO, analog AI/AO, internal bits/registers, system signals) for continuous
monitoring during simulation, independent of whatever is currently selected
on the canvas or in the library. Built on core/watch.py, the same
core-logic/Qt-panel split as core/crossref.py vs. ui/panels/signals.py.

The trend column is a small, procedurally-drawn (QPainter) strip chart —
zero charting-library dependency, the same philosophy already used for
ui/canvas/shapes.py's block shapes and ui/icons.py's library icons.
Double-clicking a Trend cell opens an enlarged, live-updating, rescalable
copy of the same widget in a non-modal popup (§ user feedback after the
first version shipped: the inline strip is necessarily too small to read
closely at table-row height).
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QTableWidget,
    QTableWidgetItem, QAbstractItemView, QHeaderView, QDialog, QCheckBox,
    QDoubleSpinBox,
)
from PySide6.QtGui import QPainter, QPen, QKeySequence
from PySide6.QtCore import Qt, Signal, QSettings, QPointF, QSize

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
    """Scrolling strip chart of one watched signal's recent samples.
    Boolean signals draw a 0/1 step trace; analog signals scale to the
    min/max actually SEEN so far (a watch can point at any signal, most of
    which have no declared range at all) unless `manual_range` overrides
    it — set by _TrendDialog's rescale controls.

    Sized by the table CELL (or the popup dialog's layout) it's placed in,
    not a fixed pixel size — paintEvent reads self.width()/self.height()
    fresh every time, so dragging a column border (or resizing the popup)
    actually resizes the chart itself, not just blank padding around a
    fixed-size widget. `sizeHint()` only supplies the STARTING size."""

    DEFAULT_WIDTH = 260
    DEFAULT_HEIGHT = 32
    DEFAULT_MAX_SAMPLES = 200

    def __init__(self, is_boolean: bool, max_samples: int = None, parent=None):
        super().__init__(parent)
        self.is_boolean = is_boolean
        self.max_samples = max_samples or self.DEFAULT_MAX_SAMPLES
        self.manual_range = None  # None -> auto-scale; else (lo, hi) override
        self.setMinimumSize(60, 18)
        self._samples = []  # newest last; entries may be None (unresolved)

    def sizeHint(self):
        return QSize(self.DEFAULT_WIDTH, self.DEFAULT_HEIGHT)

    def add_sample(self, value):
        self._samples.append(value)
        if len(self._samples) > self.max_samples:
            self._samples.pop(0)
        self.update()

    def set_samples(self, samples):
        """Replace the whole buffer at once — _TrendDialog seeds its bigger
        chart from the inline widget's current history when opened, instead
        of starting from an empty trace."""
        self._samples = list(samples)[-self.max_samples:]
        self.update()

    def clear_samples(self):
        self._samples = []
        self.update()

    def paintEvent(self, event):
        w, h = self.width(), self.height()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        painter.fillRect(self.rect(), canvas_style.COLOR_BACKGROUND)
        painter.setPen(QPen(canvas_style.COLOR_GRID_MINOR, 1))
        painter.drawRect(0, 0, w - 1, h - 1)

        n = len(self._samples)
        if n < 2:
            return

        step = (w - 4) / max(1, self.max_samples - 1)
        start_x = w - 2 - (n - 1) * step
        top, bottom = 3, h - 3

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
        if self.manual_range is not None:
            lo, hi = self.manual_range
        else:
            lo, hi = min(numeric), max(numeric)
        span = (hi - lo) or 1.0
        painter.setPen(QPen(canvas_style.COLOR_ANALOG_VALUE, 1.5))
        points = []
        for i, v in enumerate(self._samples):
            if not isinstance(v, (int, float)):
                continue
            x = start_x + i * step
            y = bottom - ((v - lo) / span) * (bottom - top)
            y = max(top, min(bottom, y))  # clip — a manual range narrower than the data must not draw outside the frame
            points.append(QPointF(x, y))
        for a, b in zip(points, points[1:]):
            painter.drawLine(a, b)


class _TrendDialog(QDialog):
    """Enlarged trend popup for one watched signal, opened by double-
    clicking its Trend cell. Non-modal (show(), not exec()) — the engineer
    keeps working the rest of the app, including running the simulation,
    while it's open; WatchPanel.refresh_values() pushes it live samples
    exactly like the inline sparkline for as long as it stays open."""

    def __init__(self, kind: str, signal_id: str, description: str,
                 is_boolean: bool, initial_samples: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Trend — {signal_id}")
        self.setModal(False)
        # A transient popup must actually be destroyed on close(), not just
        # hidden — an orphaned, never-deleted top-level QDialog left behind
        # by every open-without-explicit-teardown call site (tests included)
        # accumulates for the life of the process.
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.resize(640, 320)

        layout = QVBoxLayout(self)
        title = f"[{_KIND_LABELS.get(kind, kind)}] {signal_id}"
        if description:
            title += f" — {description}"
        header = QLabel(title)
        header.setStyleSheet("font-weight: bold;")
        layout.addWidget(header)

        self.chart = _Sparkline(is_boolean, max_samples=600)
        self.chart.set_samples(initial_samples)
        layout.addWidget(self.chart, 1)

        bottom_row = QHBoxLayout()
        if not is_boolean:
            self.auto_check = QCheckBox("Skala automatyczna")
            self.auto_check.setChecked(True)
            self.auto_check.toggled.connect(self._on_auto_toggled)
            self.min_spin = QDoubleSpinBox()
            self.min_spin.setRange(-1e9, 1e9)
            self.min_spin.setEnabled(False)
            self.max_spin = QDoubleSpinBox()
            self.max_spin.setRange(-1e9, 1e9)
            self.max_spin.setValue(1.0)
            self.max_spin.setEnabled(False)
            self.min_spin.valueChanged.connect(self._on_manual_range_changed)
            self.max_spin.valueChanged.connect(self._on_manual_range_changed)
            bottom_row.addWidget(self.auto_check)
            bottom_row.addWidget(QLabel("Min"))
            bottom_row.addWidget(self.min_spin)
            bottom_row.addWidget(QLabel("Maks"))
            bottom_row.addWidget(self.max_spin)
        bottom_row.addStretch()
        clear_btn = QPushButton("Wyczyść bufor")
        clear_btn.clicked.connect(self.chart.clear_samples)
        bottom_row.addWidget(clear_btn)
        layout.addLayout(bottom_row)

    def add_sample(self, value):
        self.chart.add_sample(value)

    def _on_auto_toggled(self, checked):
        self.min_spin.setEnabled(not checked)
        self.max_spin.setEnabled(not checked)
        self.chart.manual_range = None if checked else (self.min_spin.value(), self.max_spin.value())
        self.chart.update()

    def _on_manual_range_changed(self):
        if not self.auto_check.isChecked():
            self.chart.manual_range = (self.min_spin.value(), self.max_spin.value())
            self.chart.update()


class WatchPanel(QWidget):
    """Table of pinned signals: kind, address/name, description, live
    value, trend. "Dodaj..." reuses SignalPickerDialog (the same picker
    every "Bit"/"Sygnał"/"Address" property already uses) so adding a watch
    never means a second, independently-maintained way to browse signals.
    Every column is individually resizable by the engineer (§ user
    feedback) — none is forced to Stretch."""

    # Emitted after a watch is added/removed (project.settings mutated) —
    # MainWindow connects this to set_dirty(), the same pattern SimulationPanel's
    # step_requested uses for "this panel changed something MainWindow owns."
    changed = Signal()

    def __init__(self, project=None, parent=None, settings=None):
        super().__init__(parent)
        self.settings = settings if settings is not None else QSettings("BroniszLabs", "EPW Logic Studio")
        self.project = project
        self._trend_dialogs = {}  # (kind, signal_id) -> open _TrendDialog

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
        # feat/signal-watch (§ user feedback): every column is Interactive
        # (draggable), none Stretch — the first version force-stretched
        # Opis to fill the panel, which just made an often-empty column
        # huge while Trend stayed pinned to a small fixed width the user
        # had no way to enlarge. Widths below are only STARTING points.
        header = self.table.horizontalHeader()
        for col in (_COL_KIND, _COL_ID, _COL_DESC, _COL_VALUE, _COL_TREND):
            header.setSectionResizeMode(col, QHeaderView.Interactive)
        header.setStretchLastSection(False)
        self.table.setColumnWidth(_COL_KIND, 48)
        self.table.setColumnWidth(_COL_ID, 160)
        self.table.setColumnWidth(_COL_DESC, 260)
        self.table.setColumnWidth(_COL_VALUE, 90)
        self.table.setColumnWidth(_COL_TREND, _Sparkline.DEFAULT_WIDTH + 12)
        self.table.verticalHeader().setDefaultSectionSize(_Sparkline.DEFAULT_HEIGHT + 8)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        self.table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        layout.addWidget(self.table)

        self.empty_label = QLabel('Brak obserwowanych sygnałów — kliknij "Dodaj...".')
        self.empty_label.setStyleSheet(_rgb_style("color", canvas_style.COLOR_COMMENT_TEXT))
        layout.addWidget(self.empty_label)

        self.set_project(project)

    # ---- project wiring -----------------------------------------------------

    def set_project(self, project):
        """Rebuild every row from project.settings["watched_signals"] — call
        on load/new/undo/redo, exactly like every other project-derived
        panel's set_project(). Closes any open trend popups first: they
        refer to a specific (project, kind, signal_id) that a whole-project
        swap may have invalidated entirely."""
        self._close_all_trend_dialogs()
        self.project = project
        self.table.setRowCount(0)
        watches = watch.get_watches(project) if project else []
        for entry in watches:
            self._append_row(entry["kind"], entry["signal_id"])
        self._update_empty_state()
        self._on_selection_changed()

    def refresh_values(self, io_provider, now_ms: int = 0):
        """Pulls one fresh sample for every row from `io_provider` and
        appends it to that row's sparkline (and its trend popup, if one is
        open) — called once per scan (MainWindow._run_scan(), the same
        choke point SimulationPanel's DI/DO/AI/AO sync already goes
        through). A no-op with zero rows, so it's always safe to call
        regardless of whether anything is watched."""
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
            dialog = self._trend_dialogs.get((kind, signal_id))
            if dialog is not None:
                try:
                    dialog.add_sample(value)
                except RuntimeError:
                    # Defensive, mirrors ui/canvas/navigation.py's
                    # pulse_highlight(): the popup's C++ object was
                    # destroyed out from under this dict entry (should be
                    # unreachable — close()'s finished signal removes the
                    # entry synchronously before deleteLater() runs — but
                    # a stray access to a torn-down window is exactly the
                    # class of crash worth guarding against here).
                    self._trend_dialogs.pop((kind, signal_id), None)

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

    # ---- trend popup (§ user feedback) -----------------------------------------

    def _on_cell_double_clicked(self, row: int, column: int):
        if column != _COL_TREND:
            return
        kind = self.table.item(row, _COL_KIND).data(KIND_ROLE)
        signal_id = self.table.item(row, _COL_ID).data(SIGNAL_ID_ROLE)
        key = (kind, signal_id)

        existing = self._trend_dialogs.get(key)
        if existing is not None:
            try:
                existing.raise_()
                existing.activateWindow()
                return
            except RuntimeError:
                self._trend_dialogs.pop(key, None)  # fall through, open a fresh one

        description = self.table.item(row, _COL_DESC).text()
        sparkline = self.table.cellWidget(row, _COL_TREND)
        is_boolean = sparkline.is_boolean if sparkline is not None else True
        initial_samples = sparkline._samples if sparkline is not None else []

        dialog = _TrendDialog(kind, signal_id, description, is_boolean, initial_samples, parent=self)
        dialog.finished.connect(lambda _result, k=key: self._trend_dialogs.pop(k, None))
        self._trend_dialogs[key] = dialog
        dialog.show()

    def _close_all_trend_dialogs(self):
        for dialog in list(self._trend_dialogs.values()):
            try:
                dialog.close()
            except RuntimeError:
                pass
        self._trend_dialogs.clear()

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
            dialog = self._trend_dialogs.pop((kind, signal_id), None)
            if dialog is not None:
                try:
                    dialog.close()
                except RuntimeError:
                    pass
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
