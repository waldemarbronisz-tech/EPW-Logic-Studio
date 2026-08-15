from PySide6.QtWidgets import QGraphicsPathItem
from PySide6.QtGui import QPainterPath, QPen, QColor
from PySide6.QtCore import Qt, QPointF

class WireItem(QGraphicsPathItem):
    def __init__(self, source_port, dest_port=None, parent=None):
        super().__init__(parent)
        self.source_port = source_port
        self.dest_port = dest_port
        self.temp_end_point = None # Used when dragging a new wire

        self.setZValue(-1) # Draw wires behind blocks
        self.setFlag(QGraphicsPathItem.ItemIsSelectable, True)

        self.color = QColor(100, 100, 100) # Dark gray OFF state
        self.thickness = 2

        self.update_path()

    def update_live_state(self):
        """Update wire color based on source port pin value."""
        if not self.source_port or not self.source_port.pin:
            return

        val = self.source_port.pin.value
        if isinstance(val, bool):
            self.color = QColor(0, 255, 0) if val else QColor(100, 100, 100)
        elif val is not None:
            self.color = QColor(0, 200, 255) # Light blue for non-bool active data
        else:
            self.color = QColor(100, 100, 100)

        self.update_path()

    def update_path(self):
        if not self.source_port:
            return

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
            # Cyan selection for better visibility
            pen.setColor(QColor(0, 255, 255))
            pen.setWidth(self.thickness) # Keep thickness same but change color
        self.setPen(pen)
