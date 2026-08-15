from PySide6.QtWidgets import QGraphicsItem, QStyleOptionGraphicsItem
from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QFont
from PySide6.QtCore import Qt, QRectF

class PortItem(QGraphicsItem):
    def __init__(self, pin, parent=None):
        super().__init__(parent)
        self.pin = pin
        self.radius = 4
        self.setFlag(QGraphicsItem.ItemIsSelectable, False)

        # Color based on data type (can be expanded later)
        self.color = QColor(100, 100, 100) # Default grey
        if pin.data_type == pin.TYPE_BOOLEAN:
            self.color = QColor(0, 150, 0)
        elif pin.data_type in [pin.TYPE_INTEGER, pin.TYPE_FLOAT]:
            self.color = QColor(0, 0, 200)

    def boundingRect(self):
        # Slightly larger for easier clicking
        margin = 4
        return QRectF(-self.radius - margin, -self.radius - margin,
                      self.radius*2 + margin*2, self.radius*2 + margin*2)

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget=None):
        rect = QRectF(-self.radius, -self.radius, self.radius*2, self.radius*2)

        painter.setPen(QPen(Qt.black, 1))
        painter.setBrush(QBrush(self.color))
        painter.drawEllipse(rect)

        # Draw label
        painter.setPen(QPen(Qt.black))
        font = QFont("Arial", 7)
        painter.setFont(font)

        from logic_studio.blocks.pin import Pin
        if self.pin.direction == Pin.DIR_INPUT:
            # Text to the right
            painter.drawText(QRectF(self.radius + 2, -10, 50, 20), Qt.AlignLeft | Qt.AlignVCenter, self.pin.name)
        else:
            # Text to the left
            painter.drawText(QRectF(-50 - self.radius - 2, -10, 50, 20), Qt.AlignRight | Qt.AlignVCenter, self.pin.name)
