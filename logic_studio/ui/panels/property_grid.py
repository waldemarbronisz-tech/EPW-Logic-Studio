from PySide6.QtWidgets import QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView
from PySide6.QtCore import Qt

class PropertyGridPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Property", "Value"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)

        layout.addWidget(self.table)

        # Initialize with empty selection message or defaults
        self._set_empty_state()

    def _set_empty_state(self):
        self.table.setRowCount(1)
        item = QTableWidgetItem("No object selected")
        item.setFlags(Qt.ItemIsEnabled)
        self.table.setItem(0, 0, item)
        self.table.setItem(0, 1, QTableWidgetItem(""))

    def load_block_properties(self, block):
        """Loads properties from a BaseLogicBlock instance."""
        self.table.setRowCount(0)

        # Common properties defined in SRS
        props = {
            "Name": block.display_name,
            "Description": block.description,
            "UUID": block.uuid,
            "Category": block.category,
            "Priority": str(block.execution_priority),
            "Enabled": str(block.enabled),
            "Visible": str(block.visibility),
            "Execution State": block.execution_state
        }

        # Add dynamic properties
        props.update(block.properties)

        self.table.setRowCount(len(props))
        for row, (key, value) in enumerate(props.items()):

            key_item = QTableWidgetItem(key)
            key_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable) # Read-only key

            val_item = QTableWidgetItem(str(value))
            # Depending on property, might make it editable here in future

            self.table.setItem(row, 0, key_item)
            self.table.setItem(row, 1, val_item)
