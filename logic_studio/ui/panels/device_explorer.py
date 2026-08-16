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
        from logic_studio.core.device_model import DeviceModel

        # Root node
        root = QTreeWidgetItem(self.tree, ["EPW Controller"])
        root.setExpanded(True)

        # ELA-01 Module
        ela_module = QTreeWidgetItem(root, ["ELA-01 [ONLINE]"])
        ela_module.setExpanded(True)
        di_group = QTreeWidgetItem(ela_module, ["Digital Inputs (Input Module / Acquisition)"])
        for addr in DeviceModel.get_ela_addresses():
            QTreeWidgetItem(di_group, [addr])

        ai_group = QTreeWidgetItem(ela_module, ["Analog Inputs"])
        QTreeWidgetItem(ai_group, ["AI01"])
        QTreeWidgetItem(ai_group, ["AI02"])

        # ADA-01 Module
        ada_module = QTreeWidgetItem(root, ["ADA-01 [ONLINE]"])
        ada_module.setExpanded(True)
        do_group = QTreeWidgetItem(ada_module, ["Digital Outputs (Output Module / Actuator)"])
        for addr in DeviceModel.get_ada_addresses():
            QTreeWidgetItem(do_group, [addr])

        # EPM-01 Module
        epm_module = QTreeWidgetItem(root, ["EPM-01"])
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
