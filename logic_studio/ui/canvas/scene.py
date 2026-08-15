from PySide6.QtWidgets import QGraphicsScene
from PySide6.QtGui import QPen, QColor
from PySide6.QtCore import Qt, QLineF

class LogicScene(QGraphicsScene):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSceneRect(-5000, -5000, 10000, 10000)
        self.grid_size = 20

        # Industrial visual style for grid
        self.grid_color = QColor(200, 200, 200)
        self.grid_pen = QPen(self.grid_color)
        self.grid_pen.setWidth(1)
        self.grid_pen.setStyle(Qt.DotLine)

    def drawBackground(self, painter, rect):
        """Draws an industrial engineering dot grid background."""
        super().drawBackground(painter, rect)

        left = int(rect.left()) - (int(rect.left()) % self.grid_size)
        top = int(rect.top()) - (int(rect.top()) % self.grid_size)

        lines = []
        for x in range(left, int(rect.right()), self.grid_size):
            lines.append(QLineF(x, rect.top(), x, rect.bottom()))
        for y in range(top, int(rect.bottom()), self.grid_size):
            lines.append(QLineF(rect.left(), y, rect.right(), y))

        painter.setPen(self.grid_pen)
        painter.drawLines(lines)
