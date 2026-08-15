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

        # Draw Drop Shadow
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(0, 0, 0, 50))
        painter.drawRect(rect.translated(3, 3))

        # Draw Background
        painter.setPen(QPen(self.border_color, 1))
        painter.setBrush(QBrush(self.bg_color))
        painter.drawRect(rect)

        # Draw Header
        painter.setBrush(QBrush(self.header_color))
        painter.drawRect(header_rect)

        # Draw Selection Border
        if self.isSelected():
            pen = QPen(self.selected_color, 2, Qt.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(rect.adjusted(-2, -2, 2, 2))

        # Draw Text
        painter.setPen(QPen(Qt.white))
        font = QFont("Arial", 9, QFont.Bold)
        painter.setFont(font)
        painter.drawText(header_rect, Qt.AlignCenter, self.logic_block.display_name)

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
        return super().itemChange(change, value)
