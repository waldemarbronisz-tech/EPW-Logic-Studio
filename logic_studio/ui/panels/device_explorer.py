from PySide6.QtWidgets import QWidget, QVBoxLayout, QTreeWidget, QTreeWidgetItem
from PySide6.QtCore import Qt

class DeviceExplorerPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Project Explorer"])
        self.tree.setDragEnabled(True)
        layout.addWidget(self.tree)

        self._build_tree()

    def _build_tree(self):
        # Root node
        root = QTreeWidgetItem(self.tree, ["EPW Controller"])
        root.setExpanded(True)

        # ELA-01 Module
        ela_module = QTreeWidgetItem(root, ["ELA-01 (Digital I/O)"])
        QTreeWidgetItem(ela_module, ["DI1"])
        QTreeWidgetItem(ela_module, ["DI2"])

        # ADA-01 Module
        ada_module = QTreeWidgetItem(root, ["ADA-01 (Analog/Digital)"])
        QTreeWidgetItem(ada_module, ["DO1"])
        QTreeWidgetItem(ada_module, ["DO2"])

        # EPM-01 Module
        epm_module = QTreeWidgetItem(root, ["EPM-01 (Power Metering)"])
        QTreeWidgetItem(epm_module, ["UL1"])
        QTreeWidgetItem(epm_module, ["UL2"])
        QTreeWidgetItem(epm_module, ["UL3"])
        QTreeWidgetItem(epm_module, ["I1"])
        QTreeWidgetItem(epm_module, ["I2"])
        QTreeWidgetItem(epm_module, ["I3"])
        QTreeWidgetItem(epm_module, ["IN"])
        QTreeWidgetItem(epm_module, ["Power"])
        QTreeWidgetItem(epm_module, ["Frequency"])
        QTreeWidgetItem(epm_module, ["THD"])
        QTreeWidgetItem(epm_module, ["Temperature"])
