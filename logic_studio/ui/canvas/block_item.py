from PySide6.QtWidgets import QGraphicsItem, QGraphicsRectItem, QGraphicsTextItem, QStyleOptionGraphicsItem
from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QFont, QCursor
from PySide6.QtWidgets import QMenu
from PySide6.QtCore import Qt, QRectF

class BlockItem(QGraphicsItem):
    def __init__(self, logic_block, parent=None):
        super().__init__(parent)
        self.logic_block = logic_block

        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)

        # Industrial look colors
        self.bg_color = QColor(220, 220, 220)
        self.header_color = QColor(100, 100, 100)
        if logic_block.color.startswith("#"):
            self.header_color = QColor(logic_block.color)

        self.border_color = QColor(50, 50, 50)
        self.selected_color = QColor(0, 120, 215) # Standard selection blue

        self.width = logic_block.width
        self.height = logic_block.height

        self.setPos(logic_block.x, logic_block.y)

        # Instantiate Port graphics
        self._create_ports()

    def _create_ports(self):
        from logic_studio.ui.canvas.port_item import PortItem

        # Position inputs on the left edge
        y_offset = 30
        for pin in self.logic_block.inputs:
            port = PortItem(pin, parent=self)
            port.setPos(0, y_offset)
            y_offset += 20

        # Position outputs on the right edge
        y_offset = 30
        for pin in self.logic_block.outputs:
            port = PortItem(pin, parent=self)
            port.setPos(self.width, y_offset)
            y_offset += 20

    def boundingRect(self):
        # Allow extra space for selection border and ports
        margin = 10
        return QRectF(-margin, -margin, self.width + margin*2, self.height + margin*2)

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget=None):
        rect = QRectF(0, 0, self.width, self.height)
        header_rect = QRectF(0, 0, self.width, 20)

        # Industrial Win98 Raised Border
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(self.bg_color))
        painter.drawRect(rect)

        # Light top-left border
        painter.setPen(QPen(QColor(255, 255, 255), 2))
        painter.drawLine(rect.topLeft(), rect.topRight())
        painter.drawLine(rect.topLeft(), rect.bottomLeft())

        # Dark bottom-right border
        painter.setPen(QPen(QColor(128, 128, 128), 2))
        painter.drawLine(rect.bottomLeft(), rect.bottomRight())
        painter.drawLine(rect.topRight(), rect.bottomRight())

        # Draw Header Bar (Classic Blue)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(self.header_color))
        header_rect.adjust(2, 2, -2, 0)
        painter.drawRect(header_rect)

        # Draw Title
        painter.setPen(QPen(Qt.white))
        font = QFont("MS Sans Serif", 8, QFont.Bold)
        painter.setFont(font)
        painter.drawText(header_rect.adjusted(4, 0, 0, 0), Qt.AlignLeft | Qt.AlignVCenter, self.logic_block.display_name)

        # Draw Address/State (If applicable)
        addr = self.logic_block.properties.get("Address", "")
        if addr:
            painter.setPen(QPen(Qt.black))
            font = QFont("MS Sans Serif", 7)
            painter.setFont(font)
            painter.drawText(rect.adjusted(4, 25, -4, -4), Qt.AlignTop | Qt.AlignRight, addr)

        # Draw Selection Border
        if self.isSelected():
            pen = QPen(self.selected_color, 1, Qt.DotLine)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(rect.adjusted(2, 2, -2, -2))

    def contextMenuEvent(self, event):
        menu = QMenu()
        menu.setStyleSheet("""
            QMenu { background-color: #C0C0C0; border: 2px solid #FFFFFF; border-bottom-color: #808080; border-right-color: #808080; }
            QMenu::item { padding: 4px 20px; color: black; }
            QMenu::item:selected { background-color: #000080; color: white; }
        """)

        prop_action = menu.addAction("Properties")
        menu.addSeparator()
        dup_action = menu.addAction("Duplicate")
        del_action = menu.addAction("Delete")

        action = menu.exec(QCursor.pos())
        if action == del_action:
            if self.scene():
                self.scene().delete_selected_items()
        elif action == dup_action:
            if self.scene():
                self.scene().duplicate_selected_items()
        elif action == prop_action:
            # Tell scene to focus this
            self.setSelected(True)
            # Future: emit signal to specifically pop a property dialog if desired,
            # or rely on PropertyGrid tracking selection.
            pass

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionHasChanged:
            self.logic_block.set_position(self.pos().x(), self.pos().y())
            # Update connected wires
            if self.scene():
                from logic_studio.ui.canvas.wire_item import WireItem
                for item in self.scene().items():
                    if isinstance(item, WireItem):
                        if (item.source_port and item.source_port.parentItem() == self) or \
                           (item.dest_port and item.dest_port.parentItem() == self):
                            item.update_path()
        return super().itemChange(change, value)
