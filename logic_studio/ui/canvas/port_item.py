from PySide6.QtWidgets import QGraphicsItem, QStyleOptionGraphicsItem
from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QFont
from PySide6.QtCore import Qt, QRectF

from logic_studio.ui.canvas import style

class PortItem(QGraphicsItem):
    def __init__(self, pin, parent=None):
        super().__init__(parent)
        self.pin = pin
        self.radius = style.PORT_RADIUS
        self.setFlag(QGraphicsItem.ItemIsSelectable, False)

        self.color = style.COLOR_LOGIC_LOW  # Default OFF/black

    def update_live_state(self):
        """Called by engine/scene to refresh UI."""
        self.update()

    def boundingRect(self):
        # Slightly larger for easier clicking
        margin = style.PORT_CLICK_MARGIN
        return QRectF(-self.radius - margin, -self.radius - margin,
                      self.radius*2 + margin*2, self.radius*2 + margin*2)

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget=None):
        painter.setPen(QPen(style.COLOR_OUTLINE, 1))

        # Live fill
        fill_color = self.color
        if isinstance(self.pin.value, bool) and self.pin.value:
            fill_color = style.COLOR_LOGIC_HIGH

        # Draw square pin like in the reference image
        rect_pin = QRectF(-self.radius, -self.radius, self.radius*2, self.radius*2)
        painter.setBrush(QBrush(fill_color))
        painter.drawRect(rect_pin)

        # Draw label if needed — suppressed for gates (label under the body
        # says enough) and for IO blocks (their single pin's generic name
        # would repeat, and for output-direction IO blocks collide with, the
        # Address/display-name text already drawn on the block's own face).
        parent_block = self.parentItem()
        from logic_studio.ui.canvas.block_item import NO_PIN_LABEL_SHAPES
        if parent_block and getattr(parent_block, 'shape_style', '') in NO_PIN_LABEL_SHAPES:
             return

        painter.setPen(QPen(style.COLOR_OUTLINE))
        font = QFont(style.FONT_FAMILY, style.FONT_SIZE_PIN_LABEL)
        painter.setFont(font)

        from logic_studio.blocks.pin import Pin
        if self.pin.direction == Pin.DIR_INPUT:
            painter.drawText(QRectF(self.radius + 2, -10, 50, 20), Qt.AlignLeft | Qt.AlignVCenter, self.pin.name)
        else:
            painter.drawText(QRectF(-50 - self.radius - 2, -10, 50, 20), Qt.AlignRight | Qt.AlignVCenter, self.pin.name)
