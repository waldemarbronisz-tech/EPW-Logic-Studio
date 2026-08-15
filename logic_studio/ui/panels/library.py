from PySide6.QtWidgets import QWidget, QVBoxLayout, QTreeWidget, QTreeWidgetItem, QLineEdit, QLabel
from PySide6.QtCore import Qt

class LibraryPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Search Box
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search components...")
        self.search_box.textChanged.connect(self._filter_library)
        layout.addWidget(self.search_box)

        # Library Tree
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setDragEnabled(True)
        layout.addWidget(self.tree)

        self._populate_categories()

    def _populate_categories(self):
        categories = [
            "Logic Gates", "Timers", "Memory", "Inputs", "Outputs",
            "Mathematics", "Comparators", "Electrical Protection",
            "Environmental Protection", "Automation", "Switching",
            "Counters", "Communication", "System", "Simulation"
        ]

        for cat in categories:
            item = QTreeWidgetItem(self.tree)
            item.setText(0, cat)
            # Add some placeholder items inside
            child = QTreeWidgetItem(item)
            child.setText(0, f"Basic {cat} Component")

            # For logic gates, add standard ones
            if cat == "Logic Gates":
                QTreeWidgetItem(item, ["AND Gate"])
                QTreeWidgetItem(item, ["OR Gate"])
                QTreeWidgetItem(item, ["NOT Gate"])

    def _filter_library(self, text):
        text = text.lower()

        # Hide all first
        for item in self.tree.findItems("*", Qt.MatchWildcard | Qt.MatchRecursive):
            item.setHidden(True)

        # Show matching items and their parents
        for item in self.tree.findItems(f"*{text}*", Qt.MatchWildcard | Qt.MatchRecursive):
            item.setHidden(False)
            parent = item.parent()
            while parent:
                parent.setHidden(False)
                parent.setExpanded(bool(text)) # expand if searching
                parent = parent.parent()
