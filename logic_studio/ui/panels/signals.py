"""feat/signal-crossref §2 — the "Sygnały" side panel: a read-only,
sortable/filterable cross-reference table backed by core/crossref.py.
Never modifies the project, never touches the compiler/engine.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QAbstractItemView, QHeaderView, QMenu,
    QGraphicsRectItem
)
from PySide6.QtCore import Qt, QSettings, QTimer, Signal
from PySide6.QtGui import QFont, QColor, QBrush, QPen, QPixmap, QPainter, QIcon

from logic_studio.core.crossref import (
    build_crossref, find_issues,
    KIND_PHYSICAL_DI, KIND_PHYSICAL_DO, KIND_ANALOG_IN, KIND_ANALOG_OUT,
    KIND_INTERNAL_BIT, KIND_INTERNAL_REG, KIND_SYSTEM, KIND_UNASSIGNED,
)

SIGNAL_ID_ROLE = Qt.UserRole

# §2.2's column order: Stan | Sygnał | Typ | Etykieta | Zapisuje | Czyta
COL_STATE, COL_SIGNAL, COL_TYPE, COL_LABEL, COL_WRITES, COL_READS = range(6)
COLUMN_HEADERS = ["Stan", "Sygnał", "Typ", "Etykieta", "Zapisuje", "Czyta"]

_KIND_SHORT = {
    KIND_PHYSICAL_DI: "DI", KIND_PHYSICAL_DO: "DO",
    KIND_ANALOG_IN: "AI", KIND_ANALOG_OUT: "AO",
    KIND_INTERNAL_BIT: "BIT", KIND_INTERNAL_REG: "REG",
    KIND_SYSTEM: "SYS",
}

# §2.3: filter-group label -> the kinds it shows. "Wszystkie" (None) shows
# every kind except the internal KIND_UNASSIGNED bookkeeping entry, which
# never gets a row of its own (see _rebuild()) — it only ever feeds §1.4's
# "no address assigned" issue text attached to the OFFENDING BLOCK's own
# real signal rows, not a synthetic row of its own.
_FILTER_GROUPS = [
    ("Wszystkie", None),
    ("Fizyczne", (KIND_PHYSICAL_DI, KIND_PHYSICAL_DO)),
    ("Analogowe", (KIND_ANALOG_IN, KIND_ANALOG_OUT)),
    ("Wewnętrzne", (KIND_INTERNAL_BIT, KIND_INTERNAL_REG)),
    ("Systemowe", (KIND_SYSTEM,)),
]

_SEVERITY_RANK = {"error": 0, "warning": 1, "info": 2, None: 3}
# §2.2's Stan column literally names 3 states — "czerwona przy błędzie,
# pomarańczowa przy ostrzeżeniu, pusta gdy w porządku" — an "info" issue
# (§1.4's "read by many blocks", not itself a problem) deliberately gets
# no color/icon here, same as a clean row; §2.3's "tylko problemy" toggle
# is explicit too ("wiersze ze statusem błędu albo ostrzeżenia") about
# excluding it. It still gets a tooltip on its row (see _fill_row) since
# that costs nothing and the fact is still worth surfacing on hover.
_ICON_SEVERITIES = ("error", "warning")
_SEVERITY_COLOR = {"error": QColor(220, 0, 0), "warning": QColor(200, 120, 0)}
_SEVERITY_LABEL_PL = {"error": "Błąd", "warning": "Ostrzeżenie", "info": "Informacja", None: ""}

REFRESH_DEBOUNCE_MS = 200  # §2.4


def _status_icon(color: QColor) -> QIcon:
    pix = QPixmap(12, 12)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setPen(Qt.NoPen)
    painter.setBrush(color)
    painter.drawEllipse(1, 1, 10, 10)
    painter.end()
    return QIcon(pix)


class _SortableItem(QTableWidgetItem):
    """QTableWidget's default sort compares Qt.DisplayRole text — wrong for
    "Stan" (severity, not alphabetical) and "Czyta" (reader COUNT, not the
    lexical order of "10" vs "2"). `sort_key` carries the real comparison
    value; falls back to the same behavior as a plain item otherwise."""

    def __init__(self, text: str, sort_key=None):
        super().__init__(text)
        self.sort_key = text if sort_key is None else sort_key

    def __lt__(self, other):
        if isinstance(other, _SortableItem):
            return self.sort_key < other.sort_key
        return super().__lt__(other)


class SignalsPanel(QWidget):
    def __init__(self, parent=None, settings=None):
        super().__init__(parent)
        # Injectable — same pattern as every other panel in this app, so
        # tests/verification scripts never touch the real user registry.
        self.settings = settings if settings is not None else QSettings("BroniszLabs", "EPW Logic Studio")

        self.project = None
        self._crossref = {}
        self._issues_by_signal = {}  # signal_id -> Issue (at most one, see crossref.py)

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.timeout.connect(self._rebuild)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        # ---- Search + kind filter (§2.3) ----
        # Widgets are all CONSTRUCTED first, initial state set, and only
        # THEN wired up with signal connections and self.table built —
        # setChecked() on a filter button/toggle emits its signal
        # immediately when the value actually changes, and the handlers
        # (_on_kind_filter_changed/_on_only_issues_toggled) reach into
        # self.table via _apply_filters(); building it before any of that
        # can fire avoids a chicken-and-egg AttributeError.
        search_row = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Szukaj sygnału, etykiety lub identyfikatora bloku...")
        search_row.addWidget(self.search_edit)
        layout.addLayout(search_row)

        filter_row = QHBoxLayout()
        self.filter_buttons = {}
        for label, kinds in _FILTER_GROUPS:
            btn = QPushButton(label)
            btn.setCheckable(True)
            filter_row.addWidget(btn)
            self.filter_buttons[label] = btn
        self.only_issues_check = QPushButton("Tylko problemy")
        self.only_issues_check.setCheckable(True)
        filter_row.addWidget(self.only_issues_check)
        filter_row.addStretch()
        layout.addLayout(filter_row)

        # ---- Table ----
        self.table = QTableWidget(0, len(COLUMN_HEADERS))
        self.table.setHorizontalHeaderLabels(COLUMN_HEADERS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)  # §2: read-only
        self.table.setSortingEnabled(True)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        layout.addWidget(self.table)

        self.empty_label = QLabel("Brak sygnałów w projekcie — dodaj blok wejścia lub wyjścia i przypisz adres")
        self.empty_label.setWordWrap(True)
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setVisible(False)
        layout.addWidget(self.empty_label)

        # ---- Initial filter state, THEN wire signals ----
        self._active_kind_filter = self._read_setting("kind_filter", "Wszystkie")
        if self._active_kind_filter not in self.filter_buttons:
            self._active_kind_filter = "Wszystkie"
        self.filter_buttons[self._active_kind_filter].setChecked(True)
        self.only_issues_check.setChecked(self._read_bool_setting("only_issues", False))

        self.search_edit.textChanged.connect(self._on_search_changed)
        for label, btn in self.filter_buttons.items():
            btn.clicked.connect(lambda checked, l=label: self._on_kind_filter_changed(l))
        self.only_issues_check.toggled.connect(self._on_only_issues_toggled)

        # §3.1/§3.2: navigation.
        self.table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        self.table.customContextMenuRequested.connect(self._on_table_context_menu)

        self._rebuild()

    # ---- QSettings (§2.3) --------------------------------------------------

    def _setting_key(self, name):
        return f"signals_panel/{name}"

    def _read_setting(self, name, default):
        return self.settings.value(self._setting_key(name), default)

    def _read_bool_setting(self, name, default):
        val = self._read_setting(name, default)
        if isinstance(val, str):
            return val.lower() in ("true", "1")
        return bool(val)

    # ---- Project wiring / debounced refresh (§2.4) -------------------------

    def set_project(self, project):
        """Full, immediate rebuild — call when the project ITSELF changes
        (new/open/undo/redo), unlike request_refresh() which is for an
        in-place edit to the same project."""
        self.project = project
        self._refresh_timer.stop()
        self._rebuild()

    def request_refresh(self):
        """§2.4: debounced — a burst of edits (e.g. several properties
        changed in a row, or a large paste) collapses into a single
        rebuild 200ms after the last one, instead of recomputing the whole
        index after every single change. Restarting an already-running
        timer is exactly QTimer.start()'s documented behavior."""
        self._refresh_timer.start(REFRESH_DEBOUNCE_MS)

    def _rebuild(self):
        self._crossref = build_crossref(self.project) if self.project is not None else {}
        issues = find_issues(self._crossref)
        # At most one issue per signal_id by construction (crossref.py's
        # rules are mutually exclusive — see its own module docstring) —
        # a dict is still used defensively rather than assuming that never
        # changes, keeping the worse severity if it ever did.
        self._issues_by_signal = {}
        for issue in issues:
            existing = self._issues_by_signal.get(issue.signal_id)
            if existing is None or _SEVERITY_RANK[issue.severity] < _SEVERITY_RANK[existing.severity]:
                self._issues_by_signal[issue.signal_id] = issue

        self._populate_table()
        self._apply_filters()

    def _populate_table(self):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)

        rows = [(sid, usage) for sid, usage in self._crossref.items() if usage.kind != KIND_UNASSIGNED]
        self.table.setRowCount(len(rows))

        for row, (signal_id, usage) in enumerate(rows):
            self._fill_row(row, signal_id, usage)

        self.table.setSortingEnabled(True)
        has_signals = len(rows) > 0
        self.table.setVisible(has_signals)
        self.empty_label.setVisible(not has_signals)

    def _fill_row(self, row, signal_id, usage):
        issue = self._issues_by_signal.get(signal_id)
        severity = issue.severity if issue else None
        has_icon = severity in _ICON_SEVERITIES

        state_item = _SortableItem("", sort_key=_SEVERITY_RANK[severity])
        if has_icon:
            state_item.setIcon(_status_icon(_SEVERITY_COLOR[severity]))
        if issue:
            state_item.setToolTip(issue.text)  # info issues still get a tooltip, just no icon/color
        state_item.setData(SIGNAL_ID_ROLE, signal_id)
        self.table.setItem(row, COL_STATE, state_item)

        signal_item = _SortableItem(signal_id)
        signal_item.setFont(QFont("Consolas", 9))
        signal_item.setData(SIGNAL_ID_ROLE, signal_id)
        if has_icon:
            signal_item.setForeground(QBrush(_SEVERITY_COLOR[severity]))
        self.table.setItem(row, COL_SIGNAL, signal_item)

        type_text = f"{_KIND_SHORT.get(usage.kind, usage.kind)} · {usage.data_type}"
        self.table.setItem(row, COL_TYPE, _SortableItem(type_text))

        self.table.setItem(row, COL_LABEL, _SortableItem(usage.label))

        writes_text, writes_tooltip = self._writers_text(usage)
        writes_item = _SortableItem(writes_text)
        writes_item.setToolTip(writes_tooltip)
        self.table.setItem(row, COL_WRITES, writes_item)

        reads_text, reads_tooltip = self._readers_text(usage)
        reads_item = _SortableItem(reads_text, sort_key=len(usage.readers))
        reads_item.setToolTip(reads_tooltip)
        self.table.setItem(row, COL_READS, reads_item)

    @staticmethod
    def _writers_text(usage):
        # §2.2: physical/system INPUTS are written by the field device, not
        # by any project block — no block ever has an input pin wired to a
        # DI/AI/system-signal address, so `writers` is structurally always
        # empty for these kinds; shown as "urządzenie" rather than "—" to
        # say why, not just that nothing's there.
        if usage.kind in (KIND_PHYSICAL_DI, KIND_ANALOG_IN, KIND_SYSTEM):
            return "urządzenie", "Sygnał pochodzi z urządzenia fizycznego, nie z bloku w projekcie."
        if not usage.writers:
            return "—", ""
        short_ids = [w[1] for w in usage.writers]
        text = ", ".join(short_ids)
        return text, text

    @staticmethod
    def _readers_text(usage):
        if not usage.readers:
            return "—", ""
        short_ids = [r[1] for r in usage.readers]
        text = f"{len(short_ids)}: " + ", ".join(short_ids)
        return text, ", ".join(short_ids)

    # ---- Filtering (§2.3) --------------------------------------------------

    def _on_search_changed(self, _text):
        self._apply_filters()

    def _on_kind_filter_changed(self, label):
        self._active_kind_filter = label
        for l, btn in self.filter_buttons.items():
            btn.setChecked(l == label)
        self.settings.setValue(self._setting_key("kind_filter"), label)
        self._apply_filters()

    def _on_only_issues_toggled(self, checked):
        self.settings.setValue(self._setting_key("only_issues"), checked)
        self._apply_filters()

    def _apply_filters(self):
        text = self.search_edit.text().strip().lower()
        kinds = dict(_FILTER_GROUPS)[self._active_kind_filter]
        only_issues = self.only_issues_check.isChecked()

        for row in range(self.table.rowCount()):
            signal_id = self.table.item(row, COL_SIGNAL).data(SIGNAL_ID_ROLE)
            usage = self._crossref.get(signal_id)
            if usage is None:
                continue

            visible = True
            if kinds is not None and usage.kind not in kinds:
                visible = False
            # §2.3: "wiersze ze statusem błędu albo ostrzeżenia" —
            # explicitly error/warning only, not "info" (matches the Stan
            # column's own icon rule above).
            issue = self._issues_by_signal.get(signal_id)
            if visible and only_issues and (issue is None or issue.severity not in _ICON_SEVERITIES):
                visible = False
            if visible and text:
                haystack = signal_id.lower() + " " + usage.label.lower() + " " + " ".join(
                    s for (_u, s, _p) in usage.readers + usage.writers
                ).lower()
                if text not in haystack:
                    visible = False

            self.table.setRowHidden(row, not visible)

    # ---- Navigation (§3) -----------------------------------------------------

    def _on_cell_double_clicked(self, row, _column):
        """§3.1: jumps to the WRITER of this signal, or its first reader
        when there's no writer (either it's a physical/analog input or
        system signal, whose writer is structurally always "urządzenie" —
        never a project block — or an internal signal that's read but
        never written, which §1.4 already flags as its own warning)."""
        signal_id = self.table.item(row, COL_SIGNAL).data(SIGNAL_ID_ROLE)
        usage = self._crossref.get(signal_id)
        if usage is None:
            return
        target = usage.writers[0] if usage.writers else (usage.readers[0] if usage.readers else None)
        if target is None:
            return
        block_uuid, _short_id, _pin = target
        self._jump_to_block(block_uuid)

    def _on_table_context_menu(self, pos):
        """§3.2: right-click on a row with at least one reader opens a menu
        listing every one of them — choosing one jumps to it. A row with
        no readers (a DO/AO/write-only internal signal, or a physical
        input read by nothing) offers nothing to jump to, so no menu is
        shown at all."""
        item = self.table.itemAt(pos)
        if item is None:
            return
        row = item.row()
        signal_id = self.table.item(row, COL_SIGNAL).data(SIGNAL_ID_ROLE)
        menu = self._build_reader_menu(signal_id)
        if menu is None:
            return
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _build_reader_menu(self, signal_id):
        """Split out from _on_table_context_menu() so it's testable without
        ever calling QMenu.exec() (a modal call — invoking it in an
        automated/headless test would block forever waiting for a click
        that never comes)."""
        usage = self._crossref.get(signal_id)
        if usage is None or not usage.readers:
            return None
        menu = QMenu(self)
        for (block_uuid, short_id, _pin) in usage.readers:
            action = menu.addAction(self._block_menu_label(block_uuid, short_id))
            action.triggered.connect(lambda checked=False, u=block_uuid: self._jump_to_block(u))
        return menu

    def _block_menu_label(self, block_uuid, short_id):
        block = next((b for b in (self.project.blocks if self.project else []) if b.uuid == block_uuid), None)
        if block is None:
            return short_id
        extra = block.properties.get("Tag", "") or block.properties.get("Comment", "")
        return f"{short_id} — {extra}" if extra else short_id

    def _jump_to_block(self, block_uuid):
        window = self.window()
        scene = getattr(window, "scene", None)
        view = getattr(window, "view", None)
        if scene is None or view is None:
            return
        item = self._find_block_item(scene, block_uuid)
        if item is None:
            return
        scene.clearSelection()
        item.setSelected(True)
        view.centerOn(item)
        self._pulse_highlight(scene, item)

    @staticmethod
    def _find_block_item(scene, block_uuid):
        from logic_studio.ui.canvas.block_item import BlockItem
        for it in scene.items():
            if isinstance(it, BlockItem) and it.logic_block.uuid == block_uuid:
                return it
        return None

    @staticmethod
    def _pulse_highlight(scene, item, cycles: int = 8, interval_ms: int = 125):
        """§3.1: "podświetla pulsowaniem przez około sekundę" — a temporary
        overlay rectangle flashed on/off `cycles` times (~1s total at the
        default interval), added directly to the scene and removed at the
        end. Deliberately does NOT touch BlockItem/block_item.py at all —
        this PR's scope keeps that file untouched outside its one new
        context-menu action (§4)."""
        rect = item.sceneBoundingRect().adjusted(-4, -4, 4, 4)
        overlay = QGraphicsRectItem(rect)
        overlay.setPen(QPen(QColor(255, 180, 0), 3))
        overlay.setBrush(Qt.NoBrush)
        overlay.setZValue(1000)
        scene.addItem(overlay)

        timer = QTimer()
        state = {"ticks": 0}

        def _toggle():
            try:
                state["ticks"] += 1
                overlay.setVisible(not overlay.isVisible())
                if state["ticks"] >= cycles:
                    timer.stop()
                    scene.removeItem(overlay)
            except RuntimeError:
                # The overlay (or its scene) was already destroyed out from
                # under this pulse — e.g. the project/window was closed
                # before the ~1s animation finished. Nothing left to clean
                # up; just stop ticking.
                timer.stop()

        timer.timeout.connect(_toggle)
        # Kept alive on the overlay item itself — nothing else holds a
        # reference to `timer`, and the overlay stays alive (owned by the
        # scene) for exactly as long as the timer needs to keep firing.
        overlay._pulse_timer = timer
        timer.start(interval_ms)

    def highlight_blocks(self, block_items):
        """§3.3: highlights (background color) — never scrolls to — every
        row for a signal one of `block_items` reads or writes. Called from
        main_window.py on scene.selectionChanged, not connected here
        directly (this panel has no reference to the scene on its own)."""
        from logic_studio.ui.canvas.block_item import BlockItem
        short_ids = {item.logic_block.short_id for item in block_items if isinstance(item, BlockItem)}
        highlight = QBrush(QColor(200, 220, 255))
        clear = QBrush()

        for row in range(self.table.rowCount()):
            signal_id = self.table.item(row, COL_SIGNAL).data(SIGNAL_ID_ROLE)
            usage = self._crossref.get(signal_id)
            matches = bool(usage) and bool(short_ids) and any(
                s in short_ids for (_u, s, _p) in usage.readers + usage.writers
            )
            brush = highlight if matches else clear
            for col in range(self.table.columnCount()):
                self.table.item(row, col).setBackground(brush)

    # ---- §4: entry point from the block context menu -----------------------

    def focus_signal(self, signal_id: str):
        """Called from the canvas block context menu's "Pokaż użycia
        sygnału" (block_item.py) — resets the kind/only-issues filters
        (whatever the target signal's kind or issue state, it must end up
        VISIBLE — a stale "Fizyczne"/"Tylko problemy" filter from earlier
        browsing could otherwise hide the very row this is supposed to
        reveal), sets the search filter to this signal's id, and selects
        + scrolls to its row, if found."""
        self._on_kind_filter_changed("Wszystkie")
        self.only_issues_check.setChecked(False)
        self.search_edit.setText(signal_id)
        for row in range(self.table.rowCount()):
            if self.table.item(row, COL_SIGNAL).data(SIGNAL_ID_ROLE) == signal_id:
                self.table.selectRow(row)
                self.table.scrollToItem(self.table.item(row, COL_SIGNAL))
                break
