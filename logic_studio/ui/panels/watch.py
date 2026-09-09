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
import weakref

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QTableWidget,
    QTableWidgetItem, QAbstractItemView, QHeaderView, QDialog, QCheckBox,
    QDoubleSpinBox, QComboBox, QScrollBar,
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

# feat/signal-watch (§ user feedback: "edit scale, time(s), etc."):
# selectable time windows for _TrendDialog's chart — (label, milliseconds).
# Chosen against engine time (TimeProvider), never a wall clock, exactly
# like every other time-derived value in this codebase.
_TIME_WINDOWS_MS = [
    ("10 s", 10_000),
    ("30 s", 30_000),
    ("1 min", 60_000),
    ("2 min", 120_000),
    ("5 min", 300_000),
    ("15 min", 900_000),
    ("30 min", 1_800_000),
    ("1 h", 3_600_000),
    ("4 h", 14_400_000),
]
_DEFAULT_WINDOW_INDEX = 2  # "1 min"

# History retention cap — core/watch.py's MAX_HISTORY_MS (project-persisted
# storage) matches this list's own longest window by construction (both are
# 4 h; see core/watch.py's own docstring) so switching to the widest window
# always has data to show for as long as anything has been recorded.
_MAX_HISTORY_MS = watch.MAX_HISTORY_MS


def _format_ago(window_ms: int) -> str:
    seconds = window_ms / 1000.0
    if seconds < 60:
        return f"-{seconds:.0f} s"
    return f"-{seconds / 60.0:.1f} min"


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


class _TrendChart(QWidget):
    """Time-axis-aware trend chart for _TrendDialog's popup — samples are
    `(t_ms, value)` pairs (t_ms from the engine's own TimeProvider, never a
    wall clock) and the chart shows a SELECTABLE TIME WINDOW, not just
    "last N samples" — the inline table _Sparkline's simpler model. Kept
    as a separate class rather than extending _Sparkline: the popup exists
    specifically to expose controls (time range, axis labels, rescaling,
    scrollback) the tiny inline strip has no room for, and no room to need.

    `anchor_ms` is the engine-time instant the window's RIGHT edge is
    pinned to: `None` means "live" — the window always ends at the newest
    sample, sliding forward as new ones arrive (§_TrendDialog's scrollbar:
    dragging it away from the live end sets a fixed anchor_ms, pausing the
    view at that point in history even as new samples keep arriving in the
    background; "Na żywo" clears it)."""

    MARGIN_LEFT = 46
    MARGIN_BOTTOM = 16
    MARGIN_TOP = 6
    MARGIN_RIGHT = 6

    def __init__(self, is_boolean: bool, parent=None):
        super().__init__(parent)
        self.is_boolean = is_boolean
        self.manual_range = None  # None -> auto-scale to the visible window; else (lo, hi)
        self.window_ms = _TIME_WINDOWS_MS[_DEFAULT_WINDOW_INDEX][1]
        self.anchor_ms = None  # None -> live (track the newest sample); else a fixed right-edge instant
        self.setMinimumSize(200, 100)
        self._samples = []  # [(t_ms, value), ...], oldest first, entries may have value=None

    def sizeHint(self):
        return QSize(600, 240)

    def set_window_ms(self, window_ms: int):
        self.window_ms = window_ms
        self.update()

    def add_sample(self, t_ms: int, value):
        self._samples.append((t_ms, value))
        self._prune(t_ms)
        self.update()

    def set_samples(self, samples):
        """Replace the whole buffer at once — _TrendDialog seeds the chart
        from WatchPanel's own timestamped history when opened, instead of
        starting from an empty trace."""
        self._samples = list(samples)
        if self._samples:
            self._prune(self._samples[-1][0])
        self.update()

    def clear_samples(self):
        self._samples = []
        self.update()

    def _prune(self, now_ms):
        cutoff = now_ms - _MAX_HISTORY_MS
        while self._samples and self._samples[0][0] < cutoff:
            self._samples.pop(0)

    def _visible_samples(self, start_ms, end_ms):
        return [(t, v) for t, v in self._samples if start_ms <= t <= end_ms]

    def paintEvent(self, event):
        w, h = self.width(), self.height()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        painter.fillRect(self.rect(), canvas_style.COLOR_BACKGROUND)

        left, right = self.MARGIN_LEFT, w - self.MARGIN_RIGHT
        top, bottom = self.MARGIN_TOP, h - self.MARGIN_BOTTOM
        painter.setPen(QPen(canvas_style.COLOR_GRID_MINOR, 1))
        painter.drawRect(left, top, max(1, right - left - 1), max(1, bottom - top - 1))

        if not self._samples:
            painter.setPen(QPen(canvas_style.COLOR_COMMENT_TEXT, 1))
            painter.drawText(left, h - 3, _format_ago(self.window_ms))
            painter.drawText(right - 28, h - 3, "teraz")
            painter.drawText(self.rect(), Qt.AlignCenter, "Brak danych")
            return

        newest_t = self._samples[-1][0]
        end_t = self.anchor_ms if self.anchor_ms is not None else newest_t
        start_t = end_t - self.window_ms

        painter.setPen(QPen(canvas_style.COLOR_COMMENT_TEXT, 1))
        painter.drawText(left, h - 3, _format_ago(self.window_ms))
        # "teraz" only when truly at the live edge — a paused/scrolled-back
        # view instead shows how far behind the true latest sample this
        # window's right edge is, so scrolling back is legible at a glance.
        lag_ms = newest_t - end_t
        right_label = "teraz" if lag_ms < 500 else _format_ago(lag_ms)
        painter.drawText(right - 40, h - 3, right_label)

        visible = self._visible_samples(start_t, end_t)
        if len(visible) < 2:
            return

        def x_of(t):
            return left + ((t - start_t) / self.window_ms) * (right - left)

        if self.is_boolean:
            painter.setPen(QPen(canvas_style.COLOR_TAG_TEXT, 1))
            painter.drawText(2, top + 9, "1")
            painter.drawText(2, bottom, "0")
            painter.setPen(QPen(canvas_style.COLOR_LOGIC_HIGH, 1.5))
            points = []
            for t, v in visible:
                if v is None:
                    continue
                points.append(QPointF(x_of(t), top + 3 if v else bottom - 3))
            for a, b in zip(points, points[1:]):
                painter.drawLine(a, b)
            return

        numeric = [(t, v) for t, v in visible if isinstance(v, (int, float))]
        if len(numeric) < 2:
            return
        if self.manual_range is not None:
            lo, hi = self.manual_range
        else:
            values = [v for _, v in numeric]
            lo, hi = min(values), max(values)
        span = (hi - lo) or 1.0

        painter.setPen(QPen(canvas_style.COLOR_TAG_TEXT, 1))
        painter.drawText(2, top + 9, f"{hi:.2f}")
        painter.drawText(2, bottom, f"{lo:.2f}")

        painter.setPen(QPen(canvas_style.COLOR_ANALOG_VALUE, 1.5))
        points = []
        for t, v in numeric:
            y = bottom - ((v - lo) / span) * (bottom - top)
            y = max(top, min(bottom, y))  # clip — a manual range narrower than the data must not draw outside the frame
            points.append(QPointF(x_of(t), y))
        for a, b in zip(points, points[1:]):
            painter.drawLine(a, b)


class _TrendDialog(QDialog):
    """Enlarged trend popup for one watched signal, opened by double-
    clicking its Trend cell. Non-modal (show(), not exec()) — the engineer
    keeps working the rest of the app, including running the simulation,
    while it's open; WatchPanel.refresh_values() pushes it live samples
    exactly like the inline sparkline for as long as it stays open.

    The scrollbar (§ user feedback: "and scrolling back") lets the
    engineer pause the view at any point in the RECORDED history (persisted
    by core/watch.py — not just what's arrived since this popup opened) and
    scroll through it; "Na żywo" snaps back to following the newest
    sample. Scrolling never stops new samples from being recorded — it
    only changes what the chart currently shows."""

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
        self.resize(640, 360)
        self._live = True

        layout = QVBoxLayout(self)
        title = f"[{_KIND_LABELS.get(kind, kind)}] {signal_id}"
        if description:
            title += f" — {description}"
        header = QLabel(title)
        header.setStyleSheet("font-weight: bold;")
        layout.addWidget(header)

        self.chart = _TrendChart(is_boolean)
        self.chart.set_samples(initial_samples)
        layout.addWidget(self.chart, 1)

        scroll_row = QHBoxLayout()
        self.scrollbar = QScrollBar(Qt.Horizontal)
        self.scrollbar.valueChanged.connect(self._on_scrollbar_value_changed)
        scroll_row.addWidget(self.scrollbar, 1)
        self.live_btn = QPushButton("⏵ Na żywo")
        self.live_btn.setCheckable(True)
        self.live_btn.setChecked(True)
        self.live_btn.toggled.connect(self._on_live_toggled)
        scroll_row.addWidget(self.live_btn)
        layout.addLayout(scroll_row)
        self._update_scrollbar_range()

        bottom_row = QHBoxLayout()
        bottom_row.addWidget(QLabel("Zakres czasu"))
        self.window_combo = QComboBox()
        for label, ms in _TIME_WINDOWS_MS:
            self.window_combo.addItem(label, ms)
        self.window_combo.setCurrentIndex(_DEFAULT_WINDOW_INDEX)
        self.window_combo.currentIndexChanged.connect(self._on_window_changed)
        bottom_row.addWidget(self.window_combo)

        if not is_boolean:
            bottom_row.addSpacing(16)
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
        clear_btn.clicked.connect(self._on_clear_clicked)
        bottom_row.addWidget(clear_btn)
        layout.addLayout(bottom_row)

    def add_sample(self, t_ms: int, value):
        self.chart.add_sample(t_ms, value)
        self._update_scrollbar_range()  # re-pins to the live edge itself, when live
        if self._live:
            self.chart.anchor_ms = None
            self.chart.update()

    def _update_scrollbar_range(self):
        """Range spans the full RECORDED history (oldest sample .. newest),
        in absolute engine-time milliseconds — the scrollbar's value IS the
        chart's anchor_ms directly, no separate unit conversion. Called
        after every new sample (the range keeps growing) and after a window
        change (the page step, i.e. how far one click of the trough jumps,
        tracks the currently selected window width)."""
        samples = self.chart._samples
        if not samples:
            return
        oldest_t, newest_t = samples[0][0], samples[-1][0]
        # `self.scrollbar.value()` (read BEFORE touching the range below) is
        # only actually used in the paused branch — reaching this method
        # while paused means the scrollbar was already initialized with a
        # real range by an earlier live call, so it's always meaningful there.
        current = newest_t if self._live else self.scrollbar.value()
        self.scrollbar.blockSignals(True)
        self.scrollbar.setRange(oldest_t, newest_t)
        self.scrollbar.setPageStep(max(1, self.chart.window_ms))
        self.scrollbar.setSingleStep(max(1, self.chart.window_ms // 10))
        self.scrollbar.setValue(current)
        self.scrollbar.blockSignals(False)

    def _on_window_changed(self, index: int):
        self.chart.set_window_ms(self.window_combo.itemData(index))
        self._update_scrollbar_range()

    def _on_scrollbar_value_changed(self, value: int):
        """Every programmatic setValue() call elsewhere in this class wraps
        itself in blockSignals(True/False) (add_sample()'s live-tracking,
        _update_scrollbar_range()'s clamped restore, _on_live_toggled()'s
        snap-to-live) — so a valueChanged that actually reaches here is BY
        DEFINITION user-initiated (drag, trough click, arrow key, Home/
        End...), and any of those pauses live tracking, even a drag that
        happens to land back on the maximum (the "Na żywo" button is the
        explicit, unambiguous way back to live)."""
        if self._live:
            self._live = False
            self.live_btn.blockSignals(True)
            self.live_btn.setChecked(False)
            self.live_btn.blockSignals(False)
        self.chart.anchor_ms = value
        self.chart.update()

    def _on_live_toggled(self, checked: bool):
        self._live = checked
        if checked:
            # blockSignals: _on_scrollbar_value_changed treats any
            # unblocked valueChanged as a user drag that should turn live
            # back OFF — this setValue() is the opposite, a programmatic
            # snap-to-live, so it must not re-trigger that logic. anchor_ms
            # is set directly rather than relying on the signal anyway:
            # if the scrollbar already sits at its maximum, Qt never emits
            # valueChanged for a no-op set, and anchor_ms would otherwise
            # stay stuck at its old (paused) value.
            self.chart.anchor_ms = None
            self.scrollbar.blockSignals(True)
            self.scrollbar.setValue(self.scrollbar.maximum())
            self.scrollbar.blockSignals(False)
        else:
            self.chart.anchor_ms = self.scrollbar.value()
        self.chart.update()

    def _on_clear_clicked(self):
        self.chart.clear_samples()
        self.chart.anchor_ms = None
        # Reset the scrollbar's range BEFORE (possibly) checking live_btn:
        # if it was unchecked (paused), setChecked(True) fires
        # _on_live_toggled(), which snaps to scrollbar.maximum() — that
        # must already reflect the just-cleared, empty range, not the
        # stale one from before clearing.
        self.scrollbar.blockSignals(True)
        self.scrollbar.setRange(0, 0)
        self.scrollbar.blockSignals(False)
        self.live_btn.setChecked(True)
        self._live = True

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
        # Recorded history itself lives in project.settings["watch_history"]
        # (core/watch.py's append_history_sample()/get_history()/etc.) —
        # persisted as part of the project file itself (§ user feedback:
        # "let the program save these runs"), not a panel-local dict. Only
        # bookkeeping that doesn't belong in the project stays here.
        self._last_now_ms = None

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
        self._last_now_ms = None
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

        # A restarted engine (start() after stop()) resets its TimeProvider
        # to 0 — every existing timestamped sample would then read as "in
        # the future" relative to the new clock, breaking every open
        # trend's time window. Detected by the clock going backwards; the
        # only sane response is to start every recorded history over, not
        # try to reconcile two incomparable clocks.
        if self._last_now_ms is not None and now_ms < self._last_now_ms:
            watch.clear_all_history(self.project)
        self._last_now_ms = now_ms

        for row in range(self.table.rowCount()):
            kind = self.table.item(row, _COL_KIND).data(KIND_ROLE)
            signal_id = self.table.item(row, _COL_ID).data(SIGNAL_ID_ROLE)
            value = watch.read_value(self.project, io_provider, kind, signal_id, now_ms)
            self._set_value_cell(row, value)
            sparkline = self.table.cellWidget(row, _COL_TREND)
            if sparkline is not None:
                sparkline.add_sample(value)

            # Persisted straight into project.settings["watch_history"] —
            # rides along with the project's own save/load, no separate
            # file or save trigger needed (§ user feedback).
            watch.append_history_sample(self.project, kind, signal_id, now_ms, value)

            dialog = self._trend_dialogs.get((kind, signal_id))
            if dialog is not None:
                try:
                    dialog.add_sample(now_ms, value)
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
        # The FULL recorded (persisted) history, not just what's arrived
        # since this popup opened — the inline sparkline's own buffer
        # carries no timestamps either way, only arrival order.
        initial_samples = watch.get_history(self.project, kind, signal_id)

        dialog = _TrendDialog(kind, signal_id, description, is_boolean, initial_samples, parent=self)
        # fix/trend-dialog-lifetime: NOT `lambda _result, k=key: self._trend_dialogs.pop(k, None)`.
        # A plain closure over `self` is kept alive by `dialog`'s own C++-side
        # connection object for as long as `dialog`'s C++ object exists —
        # which, because of WA_DeleteOnClose, is until its DEFERRED
        # deleteLater() actually runs during a later processEvents() call,
        # not the moment close() returns. If nothing else is holding this
        # WatchPanel alive at that moment (its own last reference was
        # whoever called _on_cell_double_clicked()'s own scope, since gone),
        # that closure is the panel's LAST reference — so the panel gets
        # destroyed reentrantly, in the middle of Qt still processing the
        # dialog's own deferred-deletion event. That reentrant teardown is
        # what crashed tests/test_watch_panel.py deterministically (see
        # AUDIT_REPORT.md §44 for the full diagnosis and how it was
        # isolated). A weakref breaks the chain: the connection's callable
        # no longer extends the panel's lifetime, so the panel's own
        # destruction is never entangled with this dialog's deferred
        # deletion timing — same principle as ui/qt_lifetime.py's
        # create_owned_timer() guarding a callback against its owner's
        # lifetime, applied here to a QDialog's own signal connection
        # instead of a QTimer's tick.
        panel_ref = weakref.ref(self)

        def _forget_trend_dialog(_result, k=key, ref=panel_ref):
            panel = ref()
            if panel is not None:
                panel._trend_dialogs.pop(k, None)

        dialog.finished.connect(_forget_trend_dialog)
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
            watch.clear_history(self.project, kind, signal_id)
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
