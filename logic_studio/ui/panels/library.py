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

# feat/macro-blocks: the library's ONE per-project category (every other
# root here is a fixed, class-registered BlockRegistry category, known at
# import time) — see LibraryPanel.set_project()/_rebuild_macro_section().
MACRO_LABEL = "Makrobloki"

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
        self._macro_root = None
        self._category_roots = {}
        # feat/macro-blocks: unlike every other category (a fixed
        # BlockRegistry class list, known at import time), "Makrobloki" is
        # per-PROJECT data — nothing to show until set_project() hands one
        # over (MainWindow does so right after construction, in
        # _refresh_project_dependent_panels()).
        self._project = None

        self._populate_tree()

    # ---- Tree construction ----------------------------------------------

    def set_project(self, project):
        """feat/macro-blocks: called by MainWindow whenever the project is
        swapped (load/new/undo/redo — the SAME choke point every other
        project-dependent panel already goes through,
        _refresh_project_dependent_panels()) and right after
        LogicScene.create_macro_from_selection() adds a new definition —
        rebuilds the "Makrobloki" section from THIS project's own
        macro_definitions."""
        self._project = project
        self._rebuild_macro_section()

    def _populate_tree(self):
        from logic_studio.blocks.registry import BlockRegistry

        self.tree.clear()
        self._category_roots = {}

        self._recent_root = QTreeWidgetItem(self.tree, [RECENT_LABEL])
        self._recent_root.setExpanded(self._is_expanded(RECENT_LABEL, default=True))
        self._rebuild_recent_section()

        # feat/macro-blocks: right after "Ostatnio używane" — a stable,
        # predictable spot, since (unlike every category below) it isn't
        # sorted alongside the rest by `sort_key()` at all.
        self._macro_root = QTreeWidgetItem(self.tree, [MACRO_LABEL])
        self._macro_root.setExpanded(self._is_expanded(MACRO_LABEL, default=True))
        self._rebuild_macro_section()

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

    def _display_name(self, type_id):
        # feat/macro-blocks: BlockRegistry.get_block_class("macro.<def_id>")
        # returns MacroInstanceBlock — a real class, but `block_class()`
        # (no args) gives a bare, UNCONFIGURED instance whose display_name
        # is the generic "Makroblok", not this SPECIFIC macro's own name.
        # Consult the project's actual definition instead, same as
        # _rebuild_macro_section() already must.
        macro_name = self._macro_definition_name(type_id)
        if macro_name is not None:
            return macro_name
        from logic_studio.blocks.registry import BlockRegistry
        block_class = BlockRegistry.get_block_class(type_id)
        if not block_class:
            return type_id
        return block_class().display_name

    def _description(self, type_id):
        from logic_studio.core.macros import macro_def_id, get_definition
        def_id = macro_def_id(type_id)
        if def_id is not None:
            definition = get_definition(self._project, def_id) if self._project is not None else None
            if definition is None:
                return ""
            n_in = len(definition.get("input_pins", []))
            n_out = len(definition.get("output_pins", []))
            return f"Makroblok użytkownika ({n_in} wej. / {n_out} wyj.)"
        from logic_studio.blocks.registry import BlockRegistry
        block_class = BlockRegistry.get_block_class(type_id)
        if not block_class:
            return ""
        return block_class().description

    def _macro_definition_name(self, type_id):
        """The actual macro definition's own "name" for `type_id`
        ("macro.<def_id>"), or None if `type_id` isn't a macro instance at
        all (as opposed to "" — a real, if empty, name — or the def_id
        fallback for a dangling reference, both valid display strings)."""
        from logic_studio.core.macros import macro_def_id, get_definition
        def_id = macro_def_id(type_id)
        if def_id is None:
            return None
        definition = get_definition(self._project, def_id) if self._project is not None else None
        return definition.get("name", type_id) if definition is not None else type_id

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

    # ---- Makrobloki (feat/macro-blocks) ------------------------------------

    def _rebuild_macro_section(self):
        """Rebuilds the "Makrobloki" root from `self._project`'s own
        `macro_definitions` — called by set_project() (project swapped) and
        by MainWindow right after LogicScene.create_macro_from_selection()
        adds a new one. Unlike every other category here, this one has no
        BlockRegistry entries behind it at all — each child's own type_id
        ("macro.<def_id>") is resolved through core/macros.py instead."""
        if self._macro_root is None:
            return
        self._macro_root.takeChildren()
        if self._project is not None:
            from logic_studio.core.macros import get_definitions, MACRO_TYPE_PREFIX
            definitions = get_definitions(self._project)
            for def_id, definition in sorted(definitions.items(), key=lambda kv: kv[1].get("name", "")):
                self._add_block_item(self._macro_root, f"{MACRO_TYPE_PREFIX}{def_id}")
        self._macro_root.setHidden(self._macro_root.childCount() == 0)

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

        # feat/macro-blocks: unified across every root (category, recent,
        # macro) — previously category roots and _recent_root each ran
        # their own near-identical copy of this loop; _macro_root needs
        # the exact same treatment, so this pulls it out once instead of
        # adding a third copy.
        roots = list(self._category_roots.values())
        if self._recent_root is not None:
            roots.append(self._recent_root)
        if self._macro_root is not None:
            roots.append(self._macro_root)

        for root in roots:
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

    def _matches(self, type_id, text):
        if not type_id:
            return False
        macro_name = self._macro_definition_name(type_id)
        if macro_name is not None:
            # feat/macro-blocks: a macro instance's own definition name —
            # BlockRegistry.get_block_class() would resolve the type_id to
            # MacroInstanceBlock too, but `dummy = block_class()` (no
            # args, the branch below) only ever gives the generic
            # "Makroblok" name/description, never THIS macro's own.
            return text in type_id.lower() or text in macro_name.lower()
        from logic_studio.blocks.registry import BlockRegistry
        block_class = BlockRegistry.get_block_class(type_id)
        if not block_class:
            return text in type_id.lower()
        dummy = block_class()
        haystacks = [dummy.display_name, type_id, dummy.description] + list(getattr(dummy, 'aliases', []))
        return any(text in h.lower() for h in haystacks if h)
