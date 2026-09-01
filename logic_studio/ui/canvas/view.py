from PySide6.QtWidgets import QGraphicsView
from PySide6.QtCore import Qt, QEvent, Signal
from PySide6.QtGui import QPainter, QWheelEvent, QMouseEvent

class LogicView(QGraphicsView):
    # Emitted on every mouse move over the viewport, in scene coordinates.
    cursor_moved = Signal(float, float)
    # Emitted whenever the view scale changes, as a multiplier (1.0 == 100%).
    zoom_changed = Signal(float)

    MIN_ZOOM = 0.1
    MAX_ZOOM = 4.0

    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHint(QPainter.Antialiasing)
        self.setAcceptDrops(True)
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setMouseTracking(True)

        # Drag mode
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self._is_panning = False
        self._pan_start = None

    def current_zoom(self) -> float:
        return self.transform().m11()

    def _apply_zoom(self, factor: float):
        """Scale the view by `factor`, clamped to [MIN_ZOOM, MAX_ZOOM]."""
        current = self.current_zoom()
        target = max(self.MIN_ZOOM, min(self.MAX_ZOOM, current * factor))
        if current <= 0:
            return
        actual_factor = target / current
        if actual_factor == 1.0:
            return
        self.scale(actual_factor, actual_factor)
        self.zoom_changed.emit(self.current_zoom())

    def zoom_in(self):
        self._apply_zoom(1.15)

    def zoom_out(self):
        self._apply_zoom(1.0 / 1.15)

    def reset_zoom(self):
        self.resetTransform()
        self.zoom_changed.emit(self.current_zoom())

    def wheelEvent(self, event: QWheelEvent):
        """Handle zoom in/out with scroll wheel."""
        if event.angleDelta().y() > 0:
            self._apply_zoom(1.15)
        else:
            self._apply_zoom(1.0 / 1.15)

    def mousePressEvent(self, event: QMouseEvent):
        """Middle click to pan."""
        if event.button() == Qt.MiddleButton:
            self._is_panning = True
            self._pan_start = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MiddleButton:
            self._is_panning = False
            self.setCursor(Qt.ArrowCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        self.cursor_moved.emit(*self._scene_pos_tuple(event))

        if self._is_panning and self._pan_start is not None:
            delta = event.pos() - self._pan_start
            self._pan_start = event.pos()

            # Pan the view by adjusting scrollbars, even if hidden
            h_bar = self.horizontalScrollBar()
            v_bar = self.verticalScrollBar()
            h_bar.setValue(h_bar.value() - delta.x())
            v_bar.setValue(v_bar.value() - delta.y())

            event.accept()
            return
        super().mouseMoveEvent(event)

    def _scene_pos_tuple(self, event: QMouseEvent):
        scene_pos = self.mapToScene(event.pos())
        return scene_pos.x(), scene_pos.y()

    def dragEnterEvent(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        if event.mimeData().hasText():
            block_type = event.mimeData().text()
            scene_pos = self.mapToScene(event.position().toPoint())

            if getattr(self.scene(), 'snap_enabled', True):
                grid = self.scene().grid_size
                x = round(scene_pos.x() / grid) * grid
                y = round(scene_pos.y() / grid) * grid
            else:
                x, y = scene_pos.x(), scene_pos.y()

            self.scene().add_block_from_library(block_type, x, y)
            event.acceptProposedAction()
        else:
            event.ignore()
