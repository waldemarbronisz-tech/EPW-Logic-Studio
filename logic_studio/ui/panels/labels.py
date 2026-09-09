"""fix/wire-labels-and-project-integrity §A5 — the Labels panel: every
network node compiler/label_merge.py knows how to resolve, in one
table, instead of hunting free-end stubs across the whole schematic.
Same core-logic/Qt-panel split as core/watch.py vs. ui/panels/watch.py:
all the actual grouping/validation logic already lives in
compiler/label_merge.py — this panel only ever displays it and reacts
to a double-click/rename.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem, QAbstractItemView,
    QHeaderView, QLabel,
)
from PySide6.QtGui import QColor
from PySide6.QtCore import Qt, QSettings, Signal

from logic_studio.ui.canvas import style as canvas_style

_COL_LABEL, _COL_TYPE, _COL_SOURCE, _COL_RECEIVERS, _COL_STATE = range(5)
_LABEL_KEY_ROLE = Qt.UserRole


def _rgb_style(prop, qcolor):
    return f"{prop}: rgb({qcolor.red()},{qcolor.green()},{qcolor.blue()});"


class LabelsPanel(QWidget):
    """§A5: Etykieta | Typ | Źródło | Odbiorników | Stan — one row per
    network node compiler/label_merge.py's own grouping produces.
    Double-click the "Etykieta" cell to rename the whole node (every
    wire sharing the old label, via the SAME LabelNameDialog every
    other label-editing action already uses); double-click anywhere
    else in the row jumps to the resolved source, same as SignalsPanel's
    own "Pokaż użycia sygnału"."""

    changed = Signal()

    def __init__(self, project=None, parent=None, settings=None):
        super().__init__(parent)
        self.settings = settings if settings is not None else QSettings("BroniszLabs", "EPW Logic Studio")
        self.project = project

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Etykieta", "Typ", "Źródło", "Odbiorników", "Stan"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        header = self.table.horizontalHeader()
        for col in range(5):
            header.setSectionResizeMode(col, QHeaderView.Interactive)
        header.setStretchLastSection(False)
        self.table.setColumnWidth(_COL_LABEL, 140)
        self.table.setColumnWidth(_COL_TYPE, 70)
        self.table.setColumnWidth(_COL_SOURCE, 90)
        self.table.setColumnWidth(_COL_RECEIVERS, 80)
        self.table.setColumnWidth(_COL_STATE, 70)
        self.table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        layout.addWidget(self.table)

        self.empty_label = QLabel(
            'Brak etykiet w projekcie — nadaj etykietę przewodowi lub "Dodaj odnośnik...".'
        )
        self.empty_label.setWordWrap(True)
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setStyleSheet(_rgb_style("color", canvas_style.COLOR_COMMENT_TEXT))
        layout.addWidget(self.empty_label)

        self.set_project(project)

    # ---- project wiring ---------------------------------------------------

    def set_project(self, project):
        self.project = project
        self._rebuild()

    def request_refresh(self):
        """Same call shape as SignalsPanel.request_refresh() (main_window.py's
        set_dirty() calls both) — no debounce timer of its own: this
        table is at most one row per label, orders of magnitude smaller
        than the cross-reference index SignalsPanel debounces for, so a
        synchronous rebuild costs nothing worth guarding against."""
        self._rebuild()

    # ---- rebuild -------------------------------------------------------------

    def _rebuild(self):
        self.table.setRowCount(0)
        if self.project is None:
            self._update_empty_state()
            return

        from logic_studio.compiler.label_merge import group_labeled_pins, describe_label_groups
        groups = group_labeled_pins(self.project.wires, self.project.blocks)
        summary = describe_label_groups(self.project.wires, self.project.blocks)

        pin_to_block = {}
        for block in self.project.blocks:
            for pin in block.inputs + block.outputs:
                pin_to_block[pin.uuid] = block

        for key in sorted(groups):
            group = groups[key]
            info = summary[key]
            self._append_row(key, group, info, pin_to_block)

        self._update_empty_state()

    def _append_row(self, key, group, info, pin_to_block):
        from logic_studio.blocks.pin import Pin

        row = self.table.rowCount()
        self.table.insertRow(row)

        outputs = [p for p in group["pins"] if p.direction == Pin.DIR_OUTPUT]
        source_pin = outputs[0] if len(outputs) == 1 else None
        source_block = pin_to_block.get(source_pin.uuid) if source_pin is not None else None

        label_item = QTableWidgetItem(group["label"])
        label_item.setData(_LABEL_KEY_ROLE, key)
        self.table.setItem(row, _COL_LABEL, label_item)

        type_text = source_pin.data_type if source_pin is not None else "?"
        self.table.setItem(row, _COL_TYPE, QTableWidgetItem(type_text))

        source_text = (source_block.short_id or source_block.display_name) if source_block is not None else "-"
        source_item = QTableWidgetItem(source_text)
        source_item.setData(_LABEL_KEY_ROLE, source_block.uuid if source_block is not None else None)
        self.table.setItem(row, _COL_SOURCE, source_item)

        self.table.setItem(row, _COL_RECEIVERS, QTableWidgetItem(str(info["receiver_count"])))

        state_item = QTableWidgetItem("Błąd" if info["has_error"] else "OK")
        if info["has_error"]:
            for col in range(5):
                item = self.table.item(row, col) or state_item
                item.setForeground(QColor(canvas_style.COLOR_ERROR))
        self.table.setItem(row, _COL_STATE, state_item)

    def _update_empty_state(self):
        empty = self.table.rowCount() == 0
        self.table.setVisible(not empty)
        self.empty_label.setVisible(empty)

    # ---- interaction -----------------------------------------------------

    def _on_cell_double_clicked(self, row, column):
        if self.project is None:
            return
        key = self.table.item(row, _COL_LABEL).data(_LABEL_KEY_ROLE)
        if column == _COL_LABEL:
            self._rename_label(key)
        else:
            self._jump_to_source(row)

    def _jump_to_source(self, row):
        source_block_uuid = self.table.item(row, _COL_SOURCE).data(_LABEL_KEY_ROLE)
        if not source_block_uuid:
            return
        from logic_studio.ui.canvas.navigation import jump_to_block
        window = self.window()
        scene = getattr(window, "scene", None)
        view = getattr(window, "view", None)
        jump_to_block(scene, view, source_block_uuid)

    def _rename_label(self, key):
        """Renames EVERY wire currently sharing `key` (case-insensitive
        grouping key, compiler/label_merge.py's own) to a new name,
        picked via the SAME LabelNameDialog every other label-editing
        action already uses (§A3.3's completer/validation/similarity
        warning included, free)."""
        from logic_studio.ui.label_dialog import prompt_for_label

        matching_wires = [w for w in self.project.wires if (w.label or "").strip().lower() == key]
        if not matching_wires:
            return
        window = self.window()
        text, similar = prompt_for_label(window, self.project, initial=matching_wires[0].label, title="Zmień nazwę etykiety")
        if text is None or text == matching_wires[0].label:
            return

        self.project.push_state()
        for wire in matching_wires:
            wire.label = text
        if hasattr(window, "set_dirty"):
            window.set_dirty()
        if similar and hasattr(window, "statusBar"):
            window.statusBar().showMessage(f"Podobna etykieta w projekcie: {similar}", 5000)

        self._rebuild()
        self.changed.emit()
        if hasattr(window, "scene") and hasattr(window, "_reconstruct_scene"):
            window.scene.clear()
            window._reconstruct_scene()
