from PySide6.QtWidgets import QWidget, QVBoxLayout, QTreeWidget, QTreeWidgetItem
from PySide6.QtCore import Qt

class DeviceExplorerPanel(QWidget):
    """Lists the IO addresses this build actually knows about (DeviceModel).

    Analog inputs and the EPM power-meter channels are NOT listed here: there
    are no `input.ai` / EPM measurement blocks yet, so showing them would be a
    static mock with nothing behind it (AUDIT_REPORT.md §2.5). They belong
    back in this tree once those blocks exist. Likewise, no "[ONLINE]" status
    is shown — this build has no device-liveness detection to report.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Urządzenia"])
        self.tree.setDragEnabled(True)
        layout.addWidget(self.tree)

        self._build_tree()

    def _build_tree(self):
        from logic_studio.core.device_model import DeviceModel

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
