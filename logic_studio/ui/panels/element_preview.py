from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
    QHeaderView, QToolButton
)
from PySide6.QtGui import QColor, QBrush
from PySide6.QtCore import Qt, QSettings

from logic_studio.ui.icons import block_icon

SAFETY_HIGHLIGHT = QColor(255, 235, 205)


class ElementPreviewPanel(QWidget):
    """"Element:" preview panel (eTango Studio-style, §6) at the bottom of
    the Library panel. Shows whatever is selected in the library tree OR on
    the canvas — canvas selection takes priority, matching how an engineer
    actually works (inspect what's already placed over what's in the
    catalog). Eliminates the old "drop it on the canvas and click it just to
    see its pins" cycle."""

    def __init__(self, parent=None, settings=None):
        super().__init__(parent)
        self.settings = settings if settings is not None else QSettings("BroniszLabs", "EPW Logic Studio")
        self._current_source = None  # "canvas" | "library" | None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        header_row = QHBoxLayout()
        self.toggle_btn = QToolButton()
        self.toggle_btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.toggle_btn.setCheckable(True)
        self.toggle_btn.setChecked(self._is_expanded())
        self.toggle_btn.toggled.connect(self._on_toggle)
        header_row.addWidget(self.toggle_btn)
        header_row.addStretch()
        layout.addLayout(header_row)

        self.content = QWidget()
        content_layout = QVBoxLayout(self.content)
        content_layout.setContentsMargins(0, 0, 0, 0)

        top_row = QHBoxLayout()
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(80, 80)
        self.icon_label.setAlignment(Qt.AlignCenter)
        top_row.addWidget(self.icon_label)

        text_col = QVBoxLayout()
        self.name_label = QLabel()
        self.name_label.setStyleSheet("font-weight: bold;")
        self.type_id_label = QLabel()
        self.description_label = QLabel()
        self.description_label.setWordWrap(True)
        text_col.addWidget(self.name_label)
        text_col.addWidget(self.type_id_label)
        text_col.addWidget(self.description_label)
        text_col.addStretch()
        top_row.addLayout(text_col, 1)
        content_layout.addLayout(top_row)

        self.pins_table = QTableWidget(0, 4)
        self.pins_table.setHorizontalHeaderLabels(["Pin", "Kierunek", "Typ", "Opis"])
        self.pins_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.pins_table.verticalHeader().setVisible(False)
        self.pins_table.setEditTriggers(QTableWidget.NoEditTriggers)
        content_layout.addWidget(self.pins_table)

        self.props_table = QTableWidget(0, 2)
        self.props_table.setHorizontalHeaderLabels(["Właściwość", "Wartość domyślna"])
        self.props_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.props_table.verticalHeader().setVisible(False)
        self.props_table.setEditTriggers(QTableWidget.NoEditTriggers)
        content_layout.addWidget(self.props_table)

        layout.addWidget(self.content)

        self._set_empty_state()
        self._update_toggle_text()
        self.content.setVisible(self.toggle_btn.isChecked())

    # ---- Collapse state (§6) ----------------------------------------------

    def _is_expanded(self):
        val = self.settings.value("preview/expanded", True)
        if isinstance(val, str):
            return val.lower() in ("true", "1")
        return bool(val)

    def _on_toggle(self, checked):
        self.content.setVisible(checked)
        self._update_toggle_text()
        self.settings.setValue("preview/expanded", checked)

    def _update_toggle_text(self):
        self.toggle_btn.setText(("▾ " if self.toggle_btn.isChecked() else "▸ ") + "Element")

    # ---- Content ------------------------------------------------------------

    def _set_empty_state(self):
        self.icon_label.clear()
        self.name_label.setText("Brak zaznaczenia")
        self.type_id_label.setText("")
        self.description_label.setText("")
        self.pins_table.setRowCount(0)
        self.props_table.setRowCount(0)

    def show_type_id(self, type_id, source="library"):
        """Show a block TYPE by id — used for a library tree selection. No
        live instance exists yet, so a throwaway one is built purely to read
        its pin/property metadata (same approach icons.py uses)."""
        if source == "library" and self._current_source == "canvas":
            return  # canvas selection wins (§6)

        from logic_studio.blocks.registry import BlockRegistry
        block_class = BlockRegistry.get_block_class(type_id)
        if not block_class:
            self._set_empty_state()
            return
        self._current_source = source
        self._render(block_class(), type_id)

    def show_block_instance(self, block):
        """Show a live block instance selected on the canvas."""
        self._current_source = "canvas"
        self._render(block, block.type_id)

    def clear_canvas_selection(self):
        """Canvas selection cleared — falls back to nothing shown (a library
        selection does not automatically reassert itself)."""
        if self._current_source == "canvas":
            self._current_source = None
            self._set_empty_state()

    def _render(self, block, type_id):
        self.icon_label.setPixmap(block_icon(type_id, size=80).pixmap(80, 80))
        self.name_label.setText(block.display_name)
        self.type_id_label.setText(type_id)
        self.description_label.setText(block.description)

        self.pins_table.setRowCount(len(block.inputs) + len(block.outputs))
        row = 0
        for pin in block.inputs:
            self._fill_pin_row(row, pin, "Wejście")
            row += 1
        for pin in block.outputs:
            self._fill_pin_row(row, pin, "Wyjście")
            row += 1

        self.props_table.setRowCount(len(block.properties))
        for i, (key, value) in enumerate(block.properties.items()):
            self.props_table.setItem(i, 0, QTableWidgetItem(key))
            self.props_table.setItem(i, 1, QTableWidgetItem(str(value)))

    def _fill_pin_row(self, row, pin, direction_label):
        safety = bool(getattr(pin, 'safety_relevant', False))
        note = "istotne dla bezpieczeństwa" if safety else ""

        cells = [pin.name, direction_label, pin.data_type, note]
        for col, text in enumerate(cells):
            item = QTableWidgetItem(text)
            if safety:
                item.setBackground(QBrush(SAFETY_HIGHLIGHT))
                font = item.font()
                font.setBold(True)
                item.setFont(font)
            self.pins_table.setItem(row, col, item)
