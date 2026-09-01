from PySide6.QtWidgets import QWidget, QVBoxLayout, QTreeWidget, QTreeWidgetItem
from PySide6.QtCore import Qt

class DeviceExplorerPanel(QWidget):
    """Lists the IO addresses this build actually knows about: the fixed
    DI/DO channels from DeviceModel, and the project's dynamic analog points
    (AUDIT_REPORT.md §7) — rebuilt via set_project() whenever the project (or
    its analog_points setting) changes. No EPM branch: that comes back once
    EPM measurement blocks exist to back it.
    """
    def __init__(self, project=None, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Urządzenia"])
        self.tree.setDragEnabled(True)
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
            QTreeWidgetItem(di_group, [addr])

        # ADA-01 Module
        ada_module = QTreeWidgetItem(root, ["ADA-01"])
        ada_module.setExpanded(True)
        do_group = QTreeWidgetItem(ada_module, ["Digital Outputs (Output Module / Actuator)"])
        for addr in DeviceModel.get_ada_addresses():
            QTreeWidgetItem(do_group, [addr])

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
                QTreeWidgetItem(analog_branch, [label])
