from PySide6.QtWidgets import QWidget, QVBoxLayout, QLineEdit, QTreeWidget, QTreeWidgetItem
from PySide6.QtGui import QDrag
from PySide6.QtCore import Qt, QMimeData, QSettings, QPoint, Signal

from logic_studio.ui.icons import block_icon

# feat/editor-modes-and-geometry §3: these six categories used to appear in
# the tree, grayed out and unexpandable, labeled "(w przygotowaniu)" —
# structure with no registered blocks behind it at all. Removed entirely
# (both here and from the tree — see _populate_tree()'s standard_categories
# below, which no longer includes them): declaring a feature that doesn't
# exist is the same class of problem as a UI element showing a fabricated
# value.
#
# 2026-09: confirmed with the product owner these are NOT coming back as
# dedicated block types — safety/interlock logic is meant to be composed
# from the existing block library (gates, comparators, timers, ...) wired
# through internal bits (project.settings["internal_bits"], ARCHITECTURE.md
# §10), not built as new block categories. Don't propose re-adding these as
# empty scaffolding, and don't propose implementing new block TYPES under
# these names — if this comes up again, the actual ask is internal-bit-based
# composition support, not a library category:
#   "Zabezpieczenia Analogowe", "Zabezpieczenia Dwustanowe",
#   "Zabezpieczenia Technologiczne", "Łączniki", "Banki Nastaw",
#   "Zabezpieczenia silnikowe"

RECENT_LABEL = "Ostatnio używane"
RECENT_MAX = 10

DRAG_THRESHOLD_PX = 4

TYPE_ID_ROLE = Qt.UserRole


class LibraryTree(QTreeWidget):
    """QTreeWidget that drives drag-and-drop manually (mime data = plain
    type_id text, matching what LogicView.dropEvent already expects) with an
    explicit distance threshold, so a plain click/double-click doesn't also
    fire a drag (§4.3)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(False)  # driven manually below, not Qt's default item-drag
        self._press_pos = None
        self._press_type_id = None

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            item = self.itemAt(event.pos())
            type_id = item.data(0, TYPE_ID_ROLE) if item else None
            if type_id:
                self._press_pos = event.pos()
                self._press_type_id = type_id
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._press_type_id and (event.buttons() & Qt.LeftButton) and self._press_pos is not None:
            if (event.pos() - self._press_pos).manhattanLength() > DRAG_THRESHOLD_PX:
                type_id = self._press_type_id
                self._press_type_id = None
                self._press_pos = None
                drag = QDrag(self)
                mime = QMimeData()
                mime.setText(type_id)
                drag.setMimeData(mime)
                drag.setPixmap(block_icon(type_id, size=24).pixmap(24, 24))
                drag.exec(Qt.CopyAction)
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._press_pos = None
        self._press_type_id = None
        super().mouseReleaseEvent(event)


class LibraryPanel(QWidget):
    # Emitted when the current tree item changes to a real block (not a
    # category header) — MainWindow connects this to the element preview
    # panel (§6).
    selection_changed = Signal(str)

    def __init__(self, parent=None, settings=None):
        super().__init__(parent)
        # Injectable so tests don't write expand-state/recently-used into the
        # real user registry (QSettings("BroniszLabs", "EPW Logic Studio") is
        # NativeFormat on Windows == the actual HKCU registry).
        self.settings = settings if settings is not None else QSettings("BroniszLabs", "EPW Logic Studio")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Szukaj...")
        self.search_box.textChanged.connect(self._filter_tree)
        layout.addWidget(self.search_box)

        self.tree = LibraryTree()
        self.tree.setHeaderHidden(True)
        self.tree.setDragEnabled(False)
        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.tree.itemExpanded.connect(self._on_item_expanded_changed)
        self.tree.itemCollapsed.connect(self._on_item_expanded_changed)
        self.tree.currentItemChanged.connect(self._on_current_item_changed)
        layout.addWidget(self.tree)

        self._recent_root = None
        self._category_roots = {}

        self._populate_tree()

    # ---- Tree construction ----------------------------------------------

    def _populate_tree(self):
        from logic_studio.blocks.registry import BlockRegistry

        self.tree.clear()
        self._category_roots = {}

        self._recent_root = QTreeWidgetItem(self.tree, [RECENT_LABEL])
        self._recent_root.setExpanded(self._is_expanded(RECENT_LABEL, default=True))
        self._rebuild_recent_section()

        standard_categories = [
            "Bramki logiczne", "Detekcja zboczy", "Wejścia / Wyjścia", "Elementy Analogowe", "Timery",
            "Przerzutniki", "Przyciski", "LED", "Liczniki", "Telemechanika", "Inne",
            # Documentation blocks aren't executable logic — kept last, after
            # every functional category (§9.8).
            "Dokumentacja",
        ]

        # "Dokumentacja" (Text/Note/Section) is excluded from compilation
        # (GraphBuilder/Compiler) because those blocks don't execute — but
        # they ARE placeable canvas annotations, so the library still lists
        # them like any other block type.
        registered_categories = set(BlockRegistry.get_categories())
        all_cats = list(dict.fromkeys(standard_categories).keys() | registered_categories)

        def sort_key(cat):
            try:
                return (0, standard_categories.index(cat))
            except ValueError:
                return (1, cat)
        all_cats.sort(key=sort_key)

        for cat in all_cats:
            type_ids = BlockRegistry.get_blocks_in_category(cat)
            if not type_ids:
                continue

            root = QTreeWidgetItem(self.tree, [cat])
            root.setExpanded(self._is_expanded(cat, default=True))
            self._category_roots[cat] = root

            for type_id in sorted(type_ids, key=lambda t: self._display_name(t)):
                self._add_block_item(root, type_id)

    def _add_block_item(self, parent, type_id):
        item = QTreeWidgetItem(parent, [self._display_name(type_id)])
        item.setData(0, TYPE_ID_ROLE, type_id)
        item.setIcon(0, block_icon(type_id))
        item.setToolTip(0, self._description(type_id))
        return item

    @staticmethod
    def _display_name(type_id):
        from logic_studio.blocks.registry import BlockRegistry
        block_class = BlockRegistry.get_block_class(type_id)
        if not block_class:
            return type_id
        return block_class().display_name

    @staticmethod
    def _description(type_id):
        from logic_studio.blocks.registry import BlockRegistry
        block_class = BlockRegistry.get_block_class(type_id)
        if not block_class:
            return ""
        return block_class().description

    # ---- Expand-state persistence (§4.1) ---------------------------------

    def _is_expanded(self, category, default):
        val = self.settings.value(f"library/expanded/{category}", default)
        if isinstance(val, str):
            return val.lower() in ("true", "1")
        return bool(val)

    def _on_item_expanded_changed(self, item):
        cat = item.text(0)
        self.settings.setValue(f"library/expanded/{cat}", item.isExpanded())

    # ---- Recently used (§4.7) --------------------------------------------

    def _recent_list(self):
        val = self.settings.value("library/recent", [])
        if val is None:
            return []
        if isinstance(val, str):
            return [val] if val else []
        return list(val)

    def record_recently_used(self, type_id):
        """Call whenever a block is actually placed on the canvas — from
        either a library drag/double-click or a plain canvas paste/duplicate
        path that goes through LogicScene.add_block_from_library()."""
        from logic_studio.blocks.registry import BlockRegistry
        if not BlockRegistry.get_block_class(type_id):
            return

        recent = [t for t in self._recent_list() if t != type_id]
        recent.insert(0, type_id)
        recent = recent[:RECENT_MAX]
        self.settings.setValue("library/recent", recent)
        self._rebuild_recent_section()

    def _rebuild_recent_section(self):
        if self._recent_root is None:
            return
        self._recent_root.takeChildren()
        for type_id in self._recent_list():
            self._add_block_item(self._recent_root, type_id)
        self._recent_root.setHidden(self._recent_root.childCount() == 0)

    def _on_current_item_changed(self, current, previous):
        type_id = current.data(0, TYPE_ID_ROLE) if current else None
        if type_id:
            self.selection_changed.emit(type_id)

    # ---- Insertion (§4.4) -------------------------------------------------

    def _on_item_double_clicked(self, item, column):
        type_id = item.data(0, TYPE_ID_ROLE)
        if not type_id:
            return
        window = self.window()
        view = getattr(window, 'view', None)
        if view is None:
            return

        scene_pos = view.mapToScene(view.viewport().rect().center())
        if getattr(view.scene(), 'snap_enabled', True):
            grid = view.scene().grid_size
            x = round(scene_pos.x() / grid) * grid
            y = round(scene_pos.y() / grid) * grid
        else:
            x, y = scene_pos.x(), scene_pos.y()

        view.scene().add_block_from_library(type_id, x, y)

    # ---- Search (§4.5) -----------------------------------------------------

    def _filter_tree(self, text):
        text = text.strip().lower()

        for cat, root in self._category_roots.items():
            visible_children = 0
            for i in range(root.childCount()):
                child = root.child(i)
                match = not text or self._matches(child.data(0, TYPE_ID_ROLE), text)
                child.setHidden(not match)
                if match:
                    visible_children += 1
            root.setHidden(visible_children == 0)
            if text and visible_children:
                root.setExpanded(True)

        if self._recent_root:
            visible_children = 0
            for i in range(self._recent_root.childCount()):
                child = self._recent_root.child(i)
                match = not text or self._matches(child.data(0, TYPE_ID_ROLE), text)
                child.setHidden(not match)
                if match:
                    visible_children += 1
            self._recent_root.setHidden(visible_children == 0)

    @staticmethod
    def _matches(type_id, text):
        if not type_id:
            return False
        from logic_studio.blocks.registry import BlockRegistry
        block_class = BlockRegistry.get_block_class(type_id)
        if not block_class:
            return text in type_id.lower()
        dummy = block_class()
        haystacks = [dummy.display_name, type_id, dummy.description] + list(getattr(dummy, 'aliases', []))
        return any(text in h.lower() for h in haystacks if h)
