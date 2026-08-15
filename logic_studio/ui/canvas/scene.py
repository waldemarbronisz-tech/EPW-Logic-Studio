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

        # Wiring State
        self.current_wire = None
        self.wiring_start_port = None

    def add_block_from_library(self, block_name: str, x: float, y: float):
        """Called by the view upon drop event. Instantiates and adds to scene."""
        from logic_studio.blocks.registry import BlockRegistry
        from logic_studio.ui.canvas.block_item import BlockItem

        # We need to find the category to instantiate. In future, view drag drop
        # should pass both cat and name. For now search registry.
        block = None
        for cat in BlockRegistry.get_categories():
            if block_name in BlockRegistry.get_blocks_in_category(cat):
                block = BlockRegistry.create_block(cat, block_name)
                break

        if not block:
            return # Invalid drop

        block.set_position(x, y)

        item = BlockItem(block)
        self.addItem(item)

        # Add to project state (later)
        # project.add_block(block)

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

    def mousePressEvent(self, event):
        item = self.itemAt(event.scenePos(), self.views()[0].transform())

        from logic_studio.ui.canvas.port_item import PortItem
        from logic_studio.ui.canvas.wire_item import WireItem

        if event.button() == Qt.LeftButton and isinstance(item, PortItem):
            self.wiring_start_port = item
            self.current_wire = WireItem(source_port=item)
            self.current_wire.temp_end_point = event.scenePos()
            self.addItem(self.current_wire)
            event.accept()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.current_wire:
            self.current_wire.temp_end_point = event.scenePos()
            self.current_wire.update_path()
            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.current_wire:
            item = self.itemAt(event.scenePos(), self.views()[0].transform())

            from logic_studio.ui.canvas.port_item import PortItem

            if isinstance(item, PortItem) and item != self.wiring_start_port:
                # Attempt Connection
                success = self.wiring_start_port.pin.connect(item.pin)
                if success:
                    self.current_wire.dest_port = item
                    self.current_wire.update_path()
                else:
                    self.removeItem(self.current_wire)
            else:
                self.removeItem(self.current_wire)

            self.current_wire = None
            self.wiring_start_port = None
            event.accept()
            return

        super().mouseReleaseEvent(event)
