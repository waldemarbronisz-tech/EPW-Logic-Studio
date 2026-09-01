from PySide6.QtWidgets import QWidget, QVBoxLayout, QTreeWidget, QTreeWidgetItem
from PySide6.QtGui import QDrag
from PySide6.QtCore import Qt, QMimeData

from logic_studio.ui.icons import block_icon

TYPE_ID_ROLE = Qt.UserRole
ADDRESS_ROLE = Qt.UserRole + 1

DRAG_THRESHOLD_PX = 4


class DeviceTree(QTreeWidget):
    """Drag-and-drop for a device address leaf, straight onto the canvas —
    same manual, distance-thresholded drag as LibraryTree
    (ui/panels/library.py), kept as its own small class rather than shared
    because this one also carries an address alongside the type_id in the
    drag payload (see mouseMoveEvent): dropping ELA01.DI06 here creates an
    already-configured input.di block instead of a blank one that still
    needs its Address set by hand in the property grid.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(False)  # driven manually below, like LibraryTree
        self._press_pos = None
        self._press_item = None

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            item = self.itemAt(event.pos())
            if item and item.data(0, TYPE_ID_ROLE):
                self._press_pos = event.pos()
                self._press_item = item
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._press_item and (event.buttons() & Qt.LeftButton) and self._press_pos is not None:
            if (event.pos() - self._press_pos).manhattanLength() > DRAG_THRESHOLD_PX:
                item = self._press_item
                self._press_item = None
                self._press_pos = None

                type_id = item.data(0, TYPE_ID_ROLE)
                address = item.data(0, ADDRESS_ROLE) or ""

                drag = QDrag(self)
                mime = QMimeData()
                # "type_id|address" — LogicView.dropEvent() splits this back
                # apart; plain type_id (no "|") still works for anything
                # that drags from here without an address one day.
                mime.setText(f"{type_id}|{address}" if address else type_id)
                drag.setMimeData(mime)
                drag.setPixmap(block_icon(type_id, size=24).pixmap(24, 24))
                drag.exec(Qt.CopyAction)
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._press_pos = None
        self._press_item = None
        super().mouseReleaseEvent(event)


class DeviceExplorerPanel(QWidget):
    """Lists the IO addresses this build actually knows about: the fixed
    DI/DO channels from DeviceModel, and the project's dynamic analog points
    (AUDIT_REPORT.md §7) — rebuilt via set_project() whenever the project (or
    its analog_points setting) changes. No EPM branch: that comes back once
    EPM measurement blocks exist to back it.

    Every address leaf is draggable straight onto the canvas as an
    already-configured DI/DO/AI/AO block (feat/block-rendering-library,
    follow-up request).
    """
    def __init__(self, project=None, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.tree = DeviceTree()
        self.tree.setHeaderLabels(["Urządzenia"])
        layout.addWidget(self.tree)

        self.project = project
        self._build_tree()

    def set_project(self, project):
        """Rebind to a (possibly new) project and rebuild the Analog branch.
        Call whenever the project is swapped (new/open/undo/redo) or its
        analog_points setting changes (Project Settings dialog)."""
        self.project = project
        self._build_tree()

    def _build_tree(self):
        from logic_studio.core.device_model import DeviceModel

        self.tree.clear()

        # Root node
        root = QTreeWidgetItem(self.tree, ["EPW Controller"])
        root.setExpanded(True)

        # ELA-01 Module
        ela_module = QTreeWidgetItem(root, ["ELA-01"])
        ela_module.setExpanded(True)
        di_group = QTreeWidgetItem(ela_module, ["Digital Inputs (Input Module / Acquisition)"])
        for addr in DeviceModel.get_ela_addresses():
            self._add_leaf(di_group, addr, "input.di", addr)

        # ADA-01 Module
        ada_module = QTreeWidgetItem(root, ["ADA-01"])
        ada_module.setExpanded(True)
        do_group = QTreeWidgetItem(ada_module, ["Digital Outputs (Output Module / Actuator)"])
        for addr in DeviceModel.get_ada_addresses():
            self._add_leaf(do_group, addr, "output.do", addr)

        # Analog points — fully project-defined, empty tree when the project
        # has none. No example/placeholder entries.
        analog_branch = QTreeWidgetItem(root, ["Analog"])
        analog_branch.setExpanded(True)
        if self.project is not None:
            for point in DeviceModel.get_analog_points(self.project):
                addr = point.get("address", "")
                unit = point.get("unit", "")
                direction = point.get("direction", "")
                label = f"{addr} ({direction}{', ' + unit if unit else ''})"
                type_id = "input.ai" if direction == "input" else "output.ao"
                self._add_leaf(analog_branch, label, type_id, addr)

    def _add_leaf(self, parent, label, type_id, address):
        item = QTreeWidgetItem(parent, [label])
        item.setData(0, TYPE_ID_ROLE, type_id)
        item.setData(0, ADDRESS_ROLE, address)
        item.setIcon(0, block_icon(type_id))
        return item
