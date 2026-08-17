from PySide6.QtWidgets import QGraphicsItem, QStyleOptionGraphicsItem
from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QFont
from PySide6.QtCore import Qt, QRectF

class PortItem(QGraphicsItem):
    def __init__(self, pin, parent=None):
        super().__init__(parent)
        self.pin = pin
        self.radius = 3 # Smaller industrial pin size
        self.setFlag(QGraphicsItem.ItemIsSelectable, False)

        self.color = QColor(0, 0, 0) # Default OFF/Black

    def update_live_state(self):
        """Called by engine/scene to refresh UI."""
        self.update()

    def boundingRect(self):
        # Slightly larger for easier clicking
        margin = 4
        return QRectF(-self.radius - margin, -self.radius - margin,
                      self.radius*2 + margin*2, self.radius*2 + margin*2)

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget=None):
        rect = QRectF(-self.radius, -self.radius, self.radius*2, self.radius*2)

        painter.setPen(QPen(Qt.black, 1))

        # Live fill
        fill_color = self.color
        if isinstance(self.pin.value, bool) and self.pin.value:
            fill_color = QColor(0, 255, 0) # Bright green when high

        # Draw square pin like in the reference image
        rect_pin = QRectF(-self.radius, -self.radius, self.radius*2, self.radius*2)
        painter.setBrush(QBrush(fill_color))
        painter.drawRect(rect_pin)

        # Draw label if needed (disabled for gates to match reference)
        parent_block = self.parentItem()
        if parent_block and getattr(parent_block, 'shape_style', '') in ["AND", "OR", "NOT", "XOR", "NAND", "NOR", "XNOR"]:
             return # Standard gates don't have pin labels in reference

        painter.setPen(QPen(Qt.black))
        font = QFont("Arial", 6)
        painter.setFont(font)

        from logic_studio.blocks.pin import Pin
        if self.pin.direction == Pin.DIR_INPUT:
            painter.drawText(QRectF(self.radius + 2, -10, 50, 20), Qt.AlignLeft | Qt.AlignVCenter, self.pin.name)
        else:
            painter.drawText(QRectF(-50 - self.radius - 2, -10, 50, 20), Qt.AlignRight | Qt.AlignVCenter, self.pin.name)
