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
        from logic_studio.blocks.registry import BlockRegistry

        # We ensure standard categories are created even if empty yet
        standard_categories = [
            "Logic Gates", "Timers", "Memory", "Inputs", "Outputs",
            "Mathematics", "Comparators", "Electrical Protection",
            "Environmental Protection", "Automation", "Switching",
            "Counters", "Communication", "System", "Simulation"
        ]

        all_cats = list(set(standard_categories + BlockRegistry.get_categories()))
        all_cats.sort()

        for cat in all_cats:
            item = QTreeWidgetItem(self.tree)
            item.setText(0, cat)
            item.setFlags(item.flags() & ~Qt.ItemIsDragEnabled) # Category can't be dragged

            blocks = BlockRegistry.get_blocks_in_category(cat)
            for block_name in blocks:
                child = QTreeWidgetItem(item)
                child.setText(0, block_name)

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
