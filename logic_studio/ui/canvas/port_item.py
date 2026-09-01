from PySide6.QtWidgets import QGraphicsItem, QStyleOptionGraphicsItem
from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QFont, QFontMetricsF
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

        # Draw label if needed — suppressed for gates always, and for IO
        # blocks only when they have exactly one pin (see
        # block_item.pin_labels_suppressed() for why it's conditional there).
        parent_block = self.parentItem()
        from logic_studio.ui.canvas.block_item import pin_labels_suppressed
        if parent_block and pin_labels_suppressed(parent_block):
             return

        painter.setPen(QPen(style.COLOR_OUTLINE))
        font = QFont(style.FONT_FAMILY, style.FONT_SIZE_PIN_LABEL)
        painter.setFont(font)
        fm = QFontMetricsF(font)

        # §0.2 audit follow-up: available width now comes from the block's
        # own width (PIN_LABEL_SIDE_FRACTION per side, a no-man's-land left
        # in the middle) instead of a fixed 50px rect that both ignored the
        # block's actual size and — combined with AlignRight on the output
        # side — silently dropped the BEGINNING of a long name via Qt's own
        # clipping instead of an explicit ellipsis (analog.quality's
        # "Out Of Range" rendered as "Of Range", the opposite of what the
        # pin means). Eliding explicitly, before drawText, keeps the
        # ellipsis at the END regardless of which side the label is on.
        gap = style.PIN_LABEL_GAP
        block_width = getattr(self.parentItem(), 'width', 100.0) if parent_block else 100.0
        side_width = max(10.0, block_width * style.PIN_LABEL_SIDE_FRACTION)
        elided = fm.elidedText(self.pin.name, Qt.ElideRight, side_width)

        from logic_studio.blocks.pin import Pin
        if self.pin.direction == Pin.DIR_INPUT:
            rect = QRectF(self.radius + gap, -10, side_width, 20)
            painter.drawText(rect, Qt.AlignLeft | Qt.AlignVCenter, elided)
        else:
            rect = QRectF(-side_width - self.radius - gap, -10, side_width, 20)
            painter.drawText(rect, Qt.AlignRight | Qt.AlignVCenter, elided)
