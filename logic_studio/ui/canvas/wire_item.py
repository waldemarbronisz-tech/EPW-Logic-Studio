from PySide6.QtWidgets import QGraphicsPathItem
from PySide6.QtGui import QPainterPath, QPen, QColor
from PySide6.QtCore import Qt, QPointF

from logic_studio.ui.canvas import style

class WireItem(QGraphicsPathItem):
    def __init__(self, source_port, dest_port=None, parent=None):
        super().__init__(parent)
        self.source_port = source_port
        self.dest_port = dest_port
        self.temp_end_point = None # Used when dragging a new wire

        self.setZValue(-1) # Draw wires behind blocks
        self.setFlag(QGraphicsPathItem.ItemIsSelectable, True)

        self.color = style.COLOR_LOGIC_LOW # OFF state
        self.thickness = style.WIRE_THICKNESS

        self.update_path()

    def update_live_state(self):
        """Update wire color based on source port pin value."""
        if not self.source_port or not self.source_port.pin:
            return

        val = self.source_port.pin.value
        if isinstance(val, bool):
            self.color = style.COLOR_LOGIC_HIGH if val else style.COLOR_LOGIC_LOW
        elif val is not None:
            self.color = style.COLOR_ANALOG_VALUE
        else:
            self.color = style.COLOR_LOGIC_LOW

        self.update_path()

    def update_path(self):
        if not self.source_port:
            return

        # feat/clipboard-and-align §4.3: a wire LEAVING a disabled block
        # (i.e. this wire's SOURCE pin belongs to one) is dimmed right
        # along with the block itself — recomputed on every path update, so
        # toggling a block's enabled state (scene.set_blocks_enabled())
        # takes effect immediately without needing a fresh connection.
        source_block = self.source_port.parentItem()
        source_logic_block = getattr(source_block, 'logic_block', None)
        self.setOpacity(0.35 if source_logic_block is not None and not source_logic_block.enabled else 1.0)

        start_pos = self.source_port.scenePos()
        end_pos = self.dest_port.scenePos() if self.dest_port else self.temp_end_point

        if not end_pos:
            return

        path = QPainterPath(start_pos)

        # Orthogonal Manhattan Routing
        # We go right from source, then up/down, then right to dest.
        # To make it rigid and classic: Flat/Square joins, no rounding.

        offset = 15 # Minimum extension before turning

        # If destination is to the right
        if end_pos.x() > start_pos.x() + offset:
            mid_x = start_pos.x() + (end_pos.x() - start_pos.x()) / 2
            path.lineTo(mid_x, start_pos.y())
            path.lineTo(mid_x, end_pos.y())
            path.lineTo(end_pos.x(), end_pos.y())
        else:
            # Destination is to the left (feedback loop)
            # Route down and around
            mid_y = start_pos.y() + (end_pos.y() - start_pos.y()) / 2
            if abs(start_pos.y() - end_pos.y()) < 40:
                mid_y = start_pos.y() + 40 # Force it to go around the block

            path.lineTo(start_pos.x() + offset, start_pos.y())
            path.lineTo(start_pos.x() + offset, mid_y)
            path.lineTo(end_pos.x() - offset, mid_y)
            path.lineTo(end_pos.x() - offset, end_pos.y())
            path.lineTo(end_pos.x(), end_pos.y())

        self.setPath(path)

        # SquareCap and MiterJoin ensure strict 90-degree visually sharp lines
        pen = QPen(self.color, self.thickness, Qt.SolidLine, Qt.SquareCap, Qt.MiterJoin)
        if self.isSelected():
            pen.setColor(style.COLOR_WIRE_SELECTED)
            pen.setWidth(self.thickness) # Keep thickness same but change color
        self.setPen(pen)
