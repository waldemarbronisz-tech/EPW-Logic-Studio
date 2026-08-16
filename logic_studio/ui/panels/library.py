from PySide6.QtWidgets import QWidget, QVBoxLayout, QLineEdit, QScrollArea, QGroupBox, QGridLayout, QPushButton
from PySide6.QtGui import QDrag
from PySide6.QtCore import Qt, QMimeData

class BlockDragButton(QPushButton):
    def __init__(self, display_name, type_id, parent=None):
        super().__init__(display_name, parent)
        self.display_name = display_name
        self.type_id = type_id
        # Make it look like a classic block icon button
        self.setFixedSize(60, 40)
        self.setStyleSheet("""
            QPushButton {
                background: #C0C0C0;
                border-left: 1px solid #FFFFFF;
                border-top: 1px solid #FFFFFF;
                border-right: 1px solid #808080;
                border-bottom: 1px solid #808080;
                font-weight: bold;
                font-size: 8pt;
            }
            QPushButton:hover {
                background: #D0D0D0;
            }
        """)

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton:
            drag = QDrag(self)
            mime = QMimeData()
            mime.setText(self.type_id)
            drag.setMimeData(mime)
            drag.exec(Qt.CopyAction)
        super().mouseMoveEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            # Emulate dropping the block in the center of the canvas view
            window = self.window()
            if hasattr(window, 'view'):
                view = window.view
                scene_pos = view.mapToScene(view.viewport().rect().center())

                # Snap to grid
                grid = view.scene().grid_size
                x = round(scene_pos.x() / grid) * grid
                y = round(scene_pos.y() / grid) * grid

                view.scene().add_block_from_library(self.type_id, x, y)
        super().mouseDoubleClickEvent(event)

class LibraryPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Search Box
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search...")
        self.search_box.textChanged.connect(self._filter_library)
        layout.addWidget(self.search_box)

        # Scroll Area for Toolbox
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(2, 2, 2, 2)
        self.content_layout.setSpacing(4)

        self.scroll.setWidget(self.content_widget)
        layout.addWidget(self.scroll)

        self.category_groups = []
        self.block_buttons = []

        self._populate_categories()

    def _populate_categories(self):
        from logic_studio.blocks.registry import BlockRegistry

        standard_categories = [
            "Inputs", "Outputs", "Logic Gates", "Memory", "Timers",
            "Counters", "Mathematics", "Comparators", "Communication", "System"
        ]

        all_cats = list(set(standard_categories + BlockRegistry.get_categories()))

        # Sort based on standard order then alpha
        def sort_key(cat):
            try:
                return standard_categories.index(cat)
            except ValueError:
                return 999
        all_cats.sort(key=lambda x: (sort_key(x), x))

        for cat in all_cats:
            group = QGroupBox(cat)
            group_layout = QGridLayout(group)
            group_layout.setSpacing(2)
            group_layout.setContentsMargins(2, 12, 2, 2)

            blocks = BlockRegistry.get_blocks_in_category(cat)
            if not blocks:
                group.hide()

            col = 0
            row = 0
            for type_id in blocks:
                b_class = BlockRegistry.get_block_class(type_id)
                if not b_class:
                    continue
                # Instantiate a dummy to get the friendly display name
                dummy = b_class()
                btn = BlockDragButton(dummy.display_name, type_id)
                group_layout.addWidget(btn, row, col)
                self.block_buttons.append((btn, group))

                col += 1
                if col > 3: # 4 items per row
                    col = 0
                    row += 1

            self.content_layout.addWidget(group)
            self.category_groups.append(group)

        self.content_layout.addStretch()

    def _filter_library(self, text):
        text = text.lower()

        # Hide/show logic
        for btn, group in self.block_buttons:
            if text in btn.display_name.lower():
                btn.show()
            else:
                btn.hide()

        for group in self.category_groups:
            # Check if group has any visible children
            visible_children = sum(1 for btn, g in self.block_buttons if g == group and not btn.isHidden())
            if visible_children > 0:
                group.show()
            else:
                group.hide()
