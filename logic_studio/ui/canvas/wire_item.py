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

        self.color = QColor(50, 50, 50)
        self.thickness = 2

        self.update_path()

    def update_path(self):
        if not self.source_port:
            return

        start_pos = self.source_port.scenePos()
        end_pos = self.dest_port.scenePos() if self.dest_port else self.temp_end_point

        if not end_pos:
            return

        path = QPainterPath(start_pos)

        # Orthogonal Manhattan Routing (Foundation)
        # We go right from source, then up/down, then right to dest
        mid_x = start_pos.x() + (end_pos.x() - start_pos.x()) / 2

        path.lineTo(mid_x, start_pos.y())
        path.lineTo(mid_x, end_pos.y())
        path.lineTo(end_pos.x(), end_pos.y())

        self.setPath(path)

        pen = QPen(self.color, self.thickness, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        if self.isSelected():
            pen.setColor(QColor(0, 120, 215))
            pen.setWidth(self.thickness + 1)
        self.setPen(pen)
