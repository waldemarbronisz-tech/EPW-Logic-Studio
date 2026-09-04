"""feat/signal-crossref §2 — the "Sygnały" side panel: a read-only,
sortable/filterable cross-reference tree backed by core/crossref.py.
Never modifies the project, never touches the compiler/engine.

feat/signals-panel-tree: rebuilt from a flat QTableWidget onto a
QTreeWidget grouped by category (Fizyczne/Analogowe/Wewnętrzne/Systemowe)
— each category is a collapsible top-level node, signals are its
children. Categorization is now purely STRUCTURAL (collapse the
categories you don't care about) rather than a separate filter control —
several categories can be visible at once, which the earlier single-
select "Wszystkie/Fizyczne/.../Systemowe" buttons never allowed, and a
tree's indentation doesn't impose the wide fixed minimum width a row of
category buttons did. Search and "Problemy" stay real cross-cutting
filters (a signal can be in any category), auto-expanding a category
whose children match while a search is active.
"""
import csv
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QLabel,
    QTreeWidget, QTreeWidgetItem, QAbstractItemView, QHeaderView, QMenu,
    QFileDialog
)
from PySide6.QtCore import Qt, QSettings, QTimer, Signal
from PySide6.QtGui import QFont, QColor, QBrush, QPixmap, QPainter, QIcon

from logic_studio.core.crossref import (
    build_crossref, find_issues,
    KIND_PHYSICAL_DI, KIND_PHYSICAL_DO, KIND_ANALOG_IN, KIND_ANALOG_OUT,
    KIND_INTERNAL_BIT, KIND_INTERNAL_REG, KIND_SYSTEM, KIND_UNASSIGNED,
)

SIGNAL_ID_ROLE = Qt.UserRole
CATEGORY_LABEL_ROLE = Qt.UserRole + 1

# §2.2's column order: Stan | Sygnał | Typ | Etykieta | Zapisuje | Czyta
COL_STATE, COL_SIGNAL, COL_TYPE, COL_LABEL, COL_WRITES, COL_READS = range(6)
COLUMN_HEADERS = ["Stan", "Sygnał", "Typ", "Etykieta", "Zapisuje", "Czyta"]

_KIND_SHORT = {
    KIND_PHYSICAL_DI: "DI", KIND_PHYSICAL_DO: "DO",
    KIND_ANALOG_IN: "AI", KIND_ANALOG_OUT: "AO",
    KIND_INTERNAL_BIT: "BIT", KIND_INTERNAL_REG: "REG",
    KIND_SYSTEM: "SYS",
}

# feat/signals-panel-tree: category label -> the kinds grouped under it —
# every real KIND_* a row can ever have falls into exactly one of these
# four (KIND_UNASSIGNED never gets a row of its own, see _populate_tree()).
# The four top-level tree nodes are built from this list, in this order,
# and stay in this order regardless of any column sort (§ sorting below).
_SIGNAL_CATEGORIES = [
    ("Fizyczne", (KIND_PHYSICAL_DI, KIND_PHYSICAL_DO)),
    ("Analogowe", (KIND_ANALOG_IN, KIND_ANALOG_OUT)),
    ("Wewnętrzne", (KIND_INTERNAL_BIT, KIND_INTERNAL_REG)),
    ("Systemowe", (KIND_SYSTEM,)),
]
_CATEGORY_FOR_KIND = {kind: label for label, kinds in _SIGNAL_CATEGORIES for kind in kinds}

_SEVERITY_RANK = {"error": 0, "warning": 1, "info": 2, None: 3}
# §2.2's Stan column literally names 3 states — "czerwona przy błędzie,
# pomarańczowa przy ostrzeżeniu, pusta gdy w porządku" — an "info" issue
# (§1.4's "read by many blocks", not itself a problem) deliberately gets
# no color/icon here, same as a clean row; §2.3's "tylko problemy" toggle
# is explicit too ("wiersze ze statusem błędu albo ostrzeżenia") about
# excluding it. It still gets a tooltip on its row (see _fill_leaf) since
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


class _SortableTreeItem(QTreeWidgetItem):
    """QTreeWidget's default sort compares each column's Qt.DisplayRole
    text — wrong for "Stan" (severity, not alphabetical) and "Czyta"
    (reader COUNT, not the lexical order of "10" vs "2"). `sort_keys` is a
    {column: real_comparison_value} override map; columns not listed fall
    back to their own displayed text, matching plain-item behavior.

    A category (top-level) node's sort_keys always map every real column
    to that category's fixed registration-order index — so no matter
    which column the user sorts children by, the four category nodes
    themselves never reorder; only their children do."""

    def __init__(self, texts, sort_keys=None):
        super().__init__(texts)
        self._sort_keys = sort_keys or {}

    def __lt__(self, other):
        tree = self.treeWidget()
        column = tree.sortColumn() if tree is not None else 0
        mine = self._sort_keys.get(column, self.text(column))
        theirs = (
            other._sort_keys.get(column, other.text(column))
            if isinstance(other, _SortableTreeItem) else other.text(column)
        )
        try:
            return mine < theirs
        except TypeError:
            return str(mine) < str(theirs)


class SignalsPanel(QWidget):
    def __init__(self, parent=None, settings=None):
        super().__init__(parent)
        # Injectable — same pattern as every other panel in this app, so
        # tests/verification scripts never touch the real user registry.
        self.settings = settings if settings is not None else QSettings("BroniszLabs", "EPW Logic Studio")

        self.project = None
        self._crossref = {}
        self._issues_by_signal = {}  # signal_id -> Issue (at most one, see crossref.py)
        self._category_items = {}  # label -> top-level _SortableTreeItem

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.timeout.connect(self._rebuild)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        # ---- Search + "Problemy" (§2.3) ----
        # feat/signals-panel-tree: no separate category-filter control any
        # more — categorization is the tree's own structure now (collapse
        # what you don't want to see), so this row only ever needs the two
        # cross-cutting filters that genuinely can't be structural (a
        # signal's category is fixed, but whether it matches a search term
        # or has an issue isn't tied to category at all).
        search_row = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Szukaj sygnału, etykiety lub identyfikatora bloku...")
        search_row.addWidget(self.search_edit)
        layout.addLayout(search_row)

        filter_row = QHBoxLayout()
        self.only_issues_check = QPushButton("Problemy")
        self.only_issues_check.setToolTip("Pokaż tylko sygnały z błędem lub ostrzeżeniem.")
        self.only_issues_check.setCheckable(True)
        filter_row.addWidget(self.only_issues_check)
        filter_row.addStretch()
        layout.addLayout(filter_row)

        # ---- Tree ----
        self.tree = QTreeWidget()
        self.tree.setColumnCount(len(COLUMN_HEADERS))
        self.tree.setHeaderLabels(COLUMN_HEADERS)
        self.tree.header().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tree.header().setStretchLastSection(True)
        self.tree.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tree.setEditTriggers(QAbstractItemView.NoEditTriggers)  # §2: read-only
        # Sorting is driven manually (see _on_sort_indicator_changed) — only
        # a category's OWN children are ever resorted, never the four
        # category nodes themselves, regardless of which column/direction
        # the user clicks. setSortingEnabled(True) would resort everything
        # recursively on every click, including the category order.
        self.tree.header().setSortIndicatorShown(True)
        self.tree.header().sortIndicatorChanged.connect(self._on_sort_indicator_changed)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        layout.addWidget(self.tree)

        self.empty_label = QLabel("Brak sygnałów w projekcie — dodaj blok wejścia lub wyjścia i przypisz adres")
        self.empty_label.setWordWrap(True)
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setVisible(False)
        layout.addWidget(self.empty_label)

        # ---- Initial filter state, THEN wire signals ----
        self.only_issues_check.setChecked(self._read_bool_setting("only_issues", False))

        self.search_edit.textChanged.connect(self._on_search_changed)
        self.only_issues_check.toggled.connect(self._on_only_issues_toggled)

        # §3.1/§3.2: navigation.
        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.tree.customContextMenuRequested.connect(self._on_tree_context_menu)
        # feat/signals-panel-tree §4.1-style expand persistence (mirrors
        # library.py's LibraryPanel — see its own "Expand-state
        # persistence" section): only a REAL user click should be
        # remembered — _apply_filters()'s own temporary force-expand/
        # collapse during an active search blocks these signals first so
        # it never overwrites the user's actual preference.
        self.tree.itemExpanded.connect(self._on_item_expanded_changed)
        self.tree.itemCollapsed.connect(self._on_item_expanded_changed)

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

    def _is_category_expanded(self, label, default=True):
        return self._read_bool_setting(f"expanded/{label}", default)

    def _on_item_expanded_changed(self, item):
        if item.parent() is not None:
            return  # only category (top-level) nodes persist expand state
        label = item.data(0, CATEGORY_LABEL_ROLE)
        self.settings.setValue(self._setting_key(f"expanded/{label}"), item.isExpanded())

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

        self._populate_tree()
        self._apply_filters()

    def _populate_tree(self):
        self.tree.blockSignals(True)
        try:
            self.tree.clear()
            self._category_items = {}

            rows = [(sid, usage) for sid, usage in self._crossref.items() if usage.kind != KIND_UNASSIGNED]
            by_category = {label: [] for label, _kinds in _SIGNAL_CATEGORIES}
            for signal_id, usage in rows:
                label = _CATEGORY_FOR_KIND.get(usage.kind)
                if label is not None:
                    by_category[label].append((signal_id, usage))

            for index, (label, _kinds) in enumerate(_SIGNAL_CATEGORIES):
                members = by_category[label]
                category_item = _SortableTreeItem(
                    [f"{label} ({len(members)})"] + [""] * (len(COLUMN_HEADERS) - 1),
                    sort_keys={col: index for col in range(len(COLUMN_HEADERS))},
                )
                category_item.setData(0, CATEGORY_LABEL_ROLE, label)
                category_item.setFirstColumnSpanned(True)
                font = category_item.font(0)
                font.setBold(True)
                category_item.setFont(0, font)
                self.tree.addTopLevelItem(category_item)
                self._category_items[label] = category_item

                for signal_id, usage in members:
                    self._fill_leaf(category_item, signal_id, usage)

                category_item.setExpanded(self._is_category_expanded(label))

            has_signals = len(rows) > 0
            self.tree.setVisible(has_signals)
            self.empty_label.setVisible(not has_signals)
        finally:
            self.tree.blockSignals(False)

    def _fill_leaf(self, category_item, signal_id, usage):
        issue = self._issues_by_signal.get(signal_id)
        severity = issue.severity if issue else None
        has_icon = severity in _ICON_SEVERITIES

        type_text = f"{_KIND_SHORT.get(usage.kind, usage.kind)} · {usage.data_type}"
        writes_text, writes_tooltip = self._writers_text(usage)
        reads_text, reads_tooltip = self._readers_text(usage)

        texts = [""] * len(COLUMN_HEADERS)
        texts[COL_SIGNAL] = signal_id
        texts[COL_TYPE] = type_text
        texts[COL_LABEL] = usage.label
        texts[COL_WRITES] = writes_text
        texts[COL_READS] = reads_text

        item = _SortableTreeItem(texts, sort_keys={
            COL_STATE: _SEVERITY_RANK[severity],
            COL_READS: len(usage.readers),
        })
        item.setData(0, SIGNAL_ID_ROLE, signal_id)

        if has_icon:
            item.setIcon(COL_STATE, _status_icon(_SEVERITY_COLOR[severity]))
        if issue:
            item.setToolTip(COL_STATE, issue.text)  # info issues still get a tooltip, just no icon/color

        item.setFont(COL_SIGNAL, QFont("Consolas", 9))
        if has_icon:
            item.setForeground(COL_SIGNAL, QBrush(_SEVERITY_COLOR[severity]))

        item.setToolTip(COL_WRITES, writes_tooltip)
        item.setToolTip(COL_READS, reads_tooltip)

        category_item.addChild(item)
        return item

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

    # ---- Iteration helpers ---------------------------------------------------

    def _iter_leaves(self):
        """Every signal (leaf) item across every category, in tree order."""
        for category_item in self._category_items.values():
            for i in range(category_item.childCount()):
                yield category_item.child(i)

    @staticmethod
    def _signal_id_of(item):
        return item.data(0, SIGNAL_ID_ROLE)

    # ---- Sorting (children only — see the QTreeWidget setup above) --------

    def _on_sort_indicator_changed(self, column, order):
        for category_item in self._category_items.values():
            category_item.sortChildren(column, order)

    # ---- Filtering (§2.3) --------------------------------------------------

    def _on_search_changed(self, _text):
        self._apply_filters()

    def _on_only_issues_toggled(self, checked):
        self.settings.setValue(self._setting_key("only_issues"), checked)
        self._apply_filters()

    def _apply_filters(self):
        text = self.search_edit.text().strip().lower()
        only_issues = self.only_issues_check.isChecked()
        filter_active = bool(text) or only_issues

        # Programmatic expand/collapse below must NOT be mistaken for a
        # real user click by _on_item_expanded_changed (which would
        # persist it as if it were the user's own preference).
        self.tree.blockSignals(True)
        try:
            for label, category_item in self._category_items.items():
                any_visible = False
                for i in range(category_item.childCount()):
                    leaf = category_item.child(i)
                    signal_id = self._signal_id_of(leaf)
                    usage = self._crossref.get(signal_id)
                    visible = usage is not None and self._leaf_matches(leaf, signal_id, usage, text, only_issues)
                    leaf.setHidden(not visible)
                    any_visible = any_visible or visible

                # Structural presence: a category with genuinely nothing in
                # it (before any filter) still shows, so its "(0)" count is
                # informative. Only hide it once a filter is ACTIVE and it
                # has no match at all — decluttering an active search,
                # never hiding an honestly-empty category on its own.
                category_item.setHidden(filter_active and not any_visible)
                if filter_active:
                    category_item.setExpanded(any_visible)
                else:
                    category_item.setExpanded(self._is_category_expanded(label))
        finally:
            self.tree.blockSignals(False)

    def _leaf_matches(self, leaf, signal_id, usage, text, only_issues) -> bool:
        # §2.3: "wiersze ze statusem błędu albo ostrzeżenia" — explicitly
        # error/warning only, not "info" (matches the Stan column's own
        # icon rule above).
        issue = self._issues_by_signal.get(signal_id)
        if only_issues and (issue is None or issue.severity not in _ICON_SEVERITIES):
            return False
        if text:
            haystack = signal_id.lower() + " " + usage.label.lower() + " " + " ".join(
                s for (_u, s, _p) in usage.readers + usage.writers
            ).lower()
            if text not in haystack:
                return False
        return True

    # ---- Navigation (§3) -----------------------------------------------------

    def _on_item_double_clicked(self, item, _column):
        """§3.1: jumps to the WRITER of this signal, or its first reader
        when there's no writer (either it's a physical/analog input or
        system signal, whose writer is structurally always "urządzenie" —
        never a project block — or an internal signal that's read but
        never written, which §1.4 already flags as its own warning)."""
        signal_id = self._signal_id_of(item)
        if signal_id is None:
            return  # a category header, not a signal row
        usage = self._crossref.get(signal_id)
        if usage is None:
            return
        target = usage.writers[0] if usage.writers else (usage.readers[0] if usage.readers else None)
        if target is None:
            return
        block_uuid, _short_id, _pin = target
        self._jump_to_block(block_uuid)

    def _on_tree_context_menu(self, pos):
        """§3.2: right-click on a row with at least one reader opens a menu
        listing every one of them — choosing one jumps to it. A row with
        no readers (a DO/AO/write-only internal signal, or a physical
        input read by nothing), or a category header, offers nothing to
        jump to, so no menu is shown at all."""
        item = self.tree.itemAt(pos)
        if item is None:
            return
        signal_id = self._signal_id_of(item)
        if signal_id is None:
            return
        menu = self._build_reader_menu(signal_id)
        if menu is None:
            return
        menu.exec(self.tree.viewport().mapToGlobal(pos))

    def _build_reader_menu(self, signal_id):
        """Split out from _on_tree_context_menu() so it's testable without
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
        # feat/duplicate-address-hyperlink: this used to be implemented
        # here directly — moved to ui/canvas/navigation.py so BlockItem's
        # own context menu (jumping directly between blocks that share a
        # signal reference) can call the exact same "select + center +
        # pulse" behavior instead of duplicating it.
        from logic_studio.ui.canvas.navigation import jump_to_block
        window = self.window()
        scene = getattr(window, "scene", None)
        view = getattr(window, "view", None)
        jump_to_block(scene, view, block_uuid)

    def highlight_blocks(self, block_items):
        """§3.3: highlights (background color) — never scrolls to — every
        row for a signal one of `block_items` reads or writes. Called from
        main_window.py on scene.selectionChanged, not connected here
        directly (this panel has no reference to the scene on its own)."""
        from logic_studio.ui.canvas.block_item import BlockItem
        short_ids = {item.logic_block.short_id for item in block_items if isinstance(item, BlockItem)}
        highlight = QBrush(QColor(200, 220, 255))
        clear = QBrush()

        for leaf in self._iter_leaves():
            signal_id = self._signal_id_of(leaf)
            usage = self._crossref.get(signal_id)
            matches = bool(usage) and bool(short_ids) and any(
                s in short_ids for (_u, s, _p) in usage.readers + usage.writers
            )
            brush = highlight if matches else clear
            for col in range(len(COLUMN_HEADERS)):
                leaf.setBackground(col, brush)

    # ---- §4: entry point from the block context menu -----------------------

    # ---- §5: CSV export -------------------------------------------------------

    def _is_filter_applied(self) -> bool:
        return bool(self.search_edit.text().strip()) or self.only_issues_check.isChecked()

    def export_csv(self, path: str):
        """§5.1/§5.2: writes exactly the rows CURRENTLY VISIBLE in the
        tree (i.e. after search/"Problemy", exactly like the old table's
        filters — collapsing a category is a display convenience and does
        NOT affect what's exported, only setHidden()/leaf visibility
        does), in the tree's own column order plus a trailing "Problemy"
        column — reads straight off the rendered cell text rather than
        re-deriving anything from core/crossref.py, so the export can
        never disagree with what's actually on screen. UTF-8 with a BOM
        ("utf-8-sig") and a ";" delimiter, so the file opens correctly in
        Excel with Polish characters with no manual import-wizard step.
        First line is a "#" comment (project name, ISO date, whether a
        filter was applied) — not a csv.writer row, so spreadsheet tools
        that treat a leading "#" as a comment skip it automatically."""
        project_name = self.project.settings.get("name", "") if self.project else ""
        timestamp = datetime.now().isoformat(timespec="seconds")
        filter_applied = "tak" if self._is_filter_applied() else "nie"

        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            f.write(f"# Projekt: {project_name} | Data: {timestamp} | Filtr zastosowany: {filter_applied}\n")
            writer = csv.writer(f, delimiter=";")
            writer.writerow(list(COLUMN_HEADERS) + ["Problemy"])

            for leaf in self._iter_leaves():
                if leaf.isHidden():
                    continue
                signal_id = self._signal_id_of(leaf)
                issue = self._issues_by_signal.get(signal_id)
                state_text = _SEVERITY_LABEL_PL[issue.severity] if issue else ""
                writer.writerow([
                    state_text,
                    leaf.text(COL_SIGNAL),
                    leaf.text(COL_TYPE),
                    leaf.text(COL_LABEL),
                    leaf.text(COL_WRITES),
                    leaf.text(COL_READS),
                    issue.text if issue else "",
                ])

    def prompt_export_csv(self):
        """§5.1: "Project -> Eksportuj listę sygnałów..." — wired from
        main_window.py."""
        path, _ = QFileDialog.getSaveFileName(self, "Eksportuj listę sygnałów", "sygnaly.csv", "CSV (*.csv)")
        if not path:
            return
        self.export_csv(path)

    def focus_signal(self, signal_id: str):
        """Called from the canvas block context menu's "Pokaż użycia
        sygnału" (block_item.py) — resets the "Problemy" filter (whatever
        the target signal's issue state, it must end up VISIBLE — a stale
        "Tylko problemy" from earlier browsing could otherwise hide the
        very row this is supposed to reveal), sets the search filter to
        this signal's id (which also auto-expands its category, see
        _apply_filters()), and selects + scrolls to its row, if found."""
        self.only_issues_check.setChecked(False)
        self.search_edit.setText(signal_id)
        for leaf in self._iter_leaves():
            if self._signal_id_of(leaf) == signal_id:
                self.tree.setCurrentItem(leaf)
                self.tree.scrollToItem(leaf)
                break
