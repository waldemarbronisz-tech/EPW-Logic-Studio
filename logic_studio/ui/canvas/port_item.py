from PySide6.QtWidgets import QGraphicsItem, QStyleOptionGraphicsItem, QMenu
from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QFont, QFontMetricsF, QCursor
from PySide6.QtCore import Qt, QRectF, QPointF

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
        rect = QRectF(-self.radius - margin, -self.radius - margin,
                       self.radius*2 + margin*2, self.radius*2 + margin*2)
        if self.pin.disabled:
            # §2.3: the disabled-input stub is drawn further out (toward
            # negative x, away from the body) than the ordinary port click
            # box — widen so it isn't clipped/misses repaint updates.
            stub_reach = style.PORT_PITCH + margin
            rect = rect.united(QRectF(-stub_reach, -stub_reach, stub_reach * 2, stub_reach * 2))
        return rect

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget=None):
        painter.setPen(QPen(style.COLOR_OUTLINE, 1))

        if self.pin.disabled:
            self._paint_disabled_stub(painter)
        else:
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

    def _paint_disabled_stub(self, painter: QPainter):
        """§2.3: draws the 'zaślepione wejście' symbol in place of the
        normal port square — a short segment of length PORT_PITCH extending
        away from the body, capped with a perpendicular tick. Only ever
        meaningful for an input pin (the only kind that can be disabled,
        §2.4); inputs sit at the block's own x=0 (see block_item._create_
        ports()), so 'away from the body' is the negative-x direction."""
        pen = QPen(style.COLOR_DISABLED_INPUT, 2)
        painter.setPen(pen)
        stub_x = -self.radius - style.PORT_PITCH
        painter.drawLine(QPointF(-self.radius, 0), QPointF(stub_x, 0))
        tick = style.PORT_RADIUS * 2
        painter.drawLine(QPointF(stub_x, -tick), QPointF(stub_x, tick))

    # ---- Disabled-input toggle (§2.2) --------------------------------------

    def _disable_eligibility(self):
        """Returns (eligible, blocked_reason) for toggling this pin's
        disabled flag. `eligible` False means this port has nothing to do
        with §2 at all (an output port, or an input on a block type that
        never opted in) — callers must fall back to whatever happened
        before this feature existed. `blocked_reason`, when set, is a
        human-readable reason the toggle is currently unavailable even
        though the port IS the right kind (e.g. a wire is attached) — used
        to grey out the context menu action rather than hide it."""
        from logic_studio.blocks.pin import Pin

        if self.pin.direction != Pin.DIR_INPUT:
            return False, None

        parent_block = self.parentItem()
        logic_block = getattr(parent_block, 'logic_block', None)
        if logic_block is None or not getattr(logic_block, 'allows_disabled_inputs', False):
            return False, None

        if not self.pin.disabled and len(self.pin.connections) > 0:
            return True, "Odłącz przewód, aby zaślepić to wejście."

        return True, None

    def _push_state_if_possible(self):
        if self.scene() and self.scene().views():
            window = self.scene().views()[0].window()
            project = getattr(window, 'project', None)
            if project:
                project.push_state()
                window.set_dirty()

    def _toggle_disabled(self):
        self._push_state_if_possible()
        self.pin.disabled = not self.pin.disabled
        self.prepareGeometryChange()
        self.update()
        parent_block = self.parentItem()
        if parent_block is not None:
            parent_block.update()

    def mouseDoubleClickEvent(self, event):
        eligible, blocked_reason = self._disable_eligibility()
        if eligible and blocked_reason is None:
            self._toggle_disabled()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event):
        eligible, blocked_reason = self._disable_eligibility()
        if not eligible:
            # Not an input, or this block type doesn't allow disabling any
            # of its inputs at all (§2.4) — nothing of ours to show here;
            # ignore so the event falls through to the block's own
            # Properties/Duplicate/Delete menu underneath, unchanged.
            event.ignore()
            return

        menu = QMenu()
        menu.setStyleSheet("""
            QMenu { background-color: #F0F0F0; border: 1px solid #A0A0A0; }
            QMenu::item { padding: 4px 20px; color: black; }
            QMenu::item:selected { background-color: #0078D7; color: white; }
            QMenu::item:disabled { color: #A0A0A0; }
        """)
        label = "Odblokuj wejście" if self.pin.disabled else "Zaślep wejście"
        action = menu.addAction(label)
        action.setEnabled(blocked_reason is None)
        if blocked_reason:
            action.setToolTip(blocked_reason)

        chosen = menu.exec(QCursor.pos())
        if chosen == action and blocked_reason is None:
            self._toggle_disabled()
        event.accept()
