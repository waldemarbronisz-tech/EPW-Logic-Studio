from PySide6.QtWidgets import QGraphicsScene
from PySide6.QtGui import QPen, QColor
from PySide6.QtCore import Qt, QLineF

class LogicScene(QGraphicsScene):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSceneRect(-5000, -5000, 10000, 10000)
        self.grid_size = 20
        self.grid_visible = True
        self.snap_enabled = True

        # Industrial visual style for grid
        self.grid_color = QColor(200, 200, 200)
        self.grid_pen = QPen(self.grid_color)
        self.grid_pen.setWidth(1)
        self.grid_pen.setStyle(Qt.DotLine)

        # Wiring State
        self.current_wire = None
        self.wiring_start_port = None

    def delete_selected_items(self):
        from logic_studio.ui.canvas.block_item import BlockItem
        from logic_studio.ui.canvas.wire_item import WireItem

        window = self.views()[0].window()
        project = getattr(window, 'project', None)

        if project and len(self.selectedItems()) > 0:
            project.push_state()
            window.set_dirty()

        for item in self.selectedItems():
            if isinstance(item, BlockItem):
                if project:
                    project.remove_block(item.logic_block)

                # Delete connected wires to avoid C++ pointer crashes
                wires_to_remove = []
                for scene_item in self.items():
                    if isinstance(scene_item, WireItem):
                        if (scene_item.source_port and scene_item.source_port.parentItem() == item) or \
                           (scene_item.dest_port and scene_item.dest_port.parentItem() == item):
                            wires_to_remove.append(scene_item)

                for w in wires_to_remove:
                    if w.source_port and w.dest_port:
                        w.source_port.pin.disconnect(w.dest_port.pin)
                    self.removeItem(w)

                self.removeItem(item)

            elif isinstance(item, WireItem):
                if item.source_port and item.dest_port:
                    item.source_port.pin.disconnect(item.dest_port.pin)
                self.removeItem(item)

    def duplicate_selected_items(self):
        from logic_studio.ui.canvas.block_item import BlockItem

        window = self.views()[0].window()
        project = getattr(window, 'project', None)

        if project and len(self.selectedItems()) > 0:
            project.push_state()
            window.set_dirty()

        new_items = []
        for item in self.selectedItems():
            if isinstance(item, BlockItem):
                new_block = item.logic_block.clone()
                # Offset position slightly
                new_block.set_position(new_block.x + 20, new_block.y + 20)

                if project:
                    project.add_block(new_block)

                new_item = BlockItem(new_block)
                new_items.append(new_item)

        self.clearSelection()
        for new_item in new_items:
            self.addItem(new_item)
            new_item.setSelected(True)

    def refresh_live_states(self):
        """Called by ExecutionEngine after a cycle to repaint dynamic values."""
        from logic_studio.ui.canvas.wire_item import WireItem
        from logic_studio.ui.canvas.port_item import PortItem

        for item in self.items():
            if isinstance(item, WireItem):
                item.update_live_state()
            elif isinstance(item, PortItem):
                item.update_live_state()

    def add_block_from_library(self, type_id: str, x: float, y: float):
        """Called by the view upon drop event. Instantiates and adds to scene."""
        from logic_studio.blocks.registry import BlockRegistry
        from logic_studio.ui.canvas.block_item import BlockItem

        block = BlockRegistry.create_block(type_id)

        if not block:
            return # Invalid drop

        block.set_position(x, y)

        item = BlockItem(block)

        self.addItem(item)

        # Add to project state
        if self.views():
            window = self.views()[0].window()
            project = getattr(window, 'project', None)
            if project:
                project.push_state()
                window.set_dirty()
                project.add_block(block)

    def drawBackground(self, painter, rect):
        """Draws an industrial engineering dot grid background."""
        super().drawBackground(painter, rect)

        if not self.grid_visible:
            return

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

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Delete:
            self.delete_selected_items()
            event.accept()
        elif event.key() == Qt.Key_D and event.modifiers() & Qt.ControlModifier:
            self.duplicate_selected_items()
            event.accept()
        else:
            super().keyPressEvent(event)

    def mouseReleaseEvent(self, event):
        # Handle Block Move Dirty State
        # If the user released the mouse after moving an item, we should push state.
        # This is a basic catch-all for mouse release on moved items.
        window = self.views()[0].window()
        project = getattr(window, 'project', None)

        from logic_studio.ui.canvas.block_item import BlockItem
        moved_items = [i for i in self.selectedItems() if isinstance(i, BlockItem)]
        # We ideally track actual drag deltas, but for MVP forcing state on release if selected works
        if project and len(moved_items) > 0 and event.button() == Qt.LeftButton:
            # We don't want to flood the undo stack, so only if it actually moved.
            # Assume itemChange already updated logic_block pos.
            project.push_state()
            window.set_dirty()

        if self.current_wire:
            item = self.itemAt(event.scenePos(), self.views()[0].transform())

            from logic_studio.ui.canvas.port_item import PortItem

            if isinstance(item, PortItem) and item != self.wiring_start_port:
                # Attempt Connection
                success = self.wiring_start_port.pin.connect(item.pin)
                if success:
                    self.current_wire.dest_port = item
                    self.current_wire.update_path()
                    if project:
                        project.push_state()
                        window.set_dirty()
                else:
                    self.removeItem(self.current_wire)
            else:
                self.removeItem(self.current_wire)

            self.current_wire = None
            self.wiring_start_port = None
            event.accept()
            return

        super().mouseReleaseEvent(event)
