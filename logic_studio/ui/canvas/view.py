from PySide6.QtWidgets import QGraphicsView
from PySide6.QtCore import Qt, Signal
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

    # feat/wire-detour-and-text-size §B4: matches property_grid.py's own
    # _int_floor()/_int_ceiling() for the "Rozmiar tekstu" property key —
    # duplicated (this codebase has no shared per-property range schema
    # to hang it on instead, see that module's own comment) rather than
    # imported, since ui/canvas/view.py has no reason to depend on
    # ui/panels/property_grid.py otherwise.
    _DOC_TEXT_SIZE_MIN = 6
    _DOC_TEXT_SIZE_MAX = 48
    _DOC_TEXT_SIZE_KEY = "Rozmiar tekstu (pkt)"
    _DOC_TYPE_IDS = ("doc.text", "doc.note", "doc.section")

    def wheelEvent(self, event: QWheelEvent):
        """Handle zoom in/out with scroll wheel.

        feat/wire-detour-and-text-size §B4: every scroll tick already
        zoomed regardless of modifiers before this — Ctrl+scroll had no
        dedicated behavior of its own to preserve. Ctrl+scroll
        specifically, with the cursor over a SELECTED documentation
        block, now nudges that block's own text size by one point per
        tick instead; every other case (plain scroll anywhere, Ctrl+
        scroll anywhere else) falls through to the exact same zoom
        behavior as before, unchanged."""
        if event.modifiers() & Qt.ControlModifier:
            doc_item = self._selected_doc_block_at(event.position().toPoint())
            if doc_item is not None:
                self._nudge_doc_text_size(doc_item, 1 if event.angleDelta().y() > 0 else -1)
                event.accept()
                return

        if event.angleDelta().y() > 0:
            self._apply_zoom(1.15)
        else:
            self._apply_zoom(1.0 / 1.15)

    def _selected_doc_block_at(self, viewport_pos):
        """The selected documentation BlockItem under `viewport_pos`, or
        None — covers both "nothing there" and "something there, but not
        a selected doc block" identically, since §B4 treats both the same
        way (fall through to zoom)."""
        from logic_studio.ui.canvas.block_item import BlockItem
        item = self.itemAt(viewport_pos)
        while item is not None and not isinstance(item, BlockItem):
            item = item.parentItem()
        if item is None or not item.isSelected():
            return None
        if item.logic_block.type_id not in self._DOC_TYPE_IDS:
            return None
        return item

    def _nudge_doc_text_size(self, item, delta: int):
        key = self._DOC_TEXT_SIZE_KEY
        current = item.logic_block.properties.get(key, 9)
        new_value = max(self._DOC_TEXT_SIZE_MIN, min(self._DOC_TEXT_SIZE_MAX, int(current) + delta))
        if new_value == int(current):
            return  # already at the clamped end -- nothing to push/undo

        window = self.window()
        if hasattr(window, 'project'):
            window.project.push_state()
            if hasattr(window, 'set_dirty'):
                window.set_dirty()

        item.logic_block.update_property(key, str(new_value))
        item.prepareGeometryChange()
        item._determine_shape_style()
        item.update()

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
            payload = event.mimeData().text()
            # DeviceExplorerPanel encodes "type_id|address" so a DI/DO/AI/AO
            # dragged from there arrives already configured; the library
            # panel drags plain type_id text, unchanged.
            if "|" in payload:
                block_type, address = payload.split("|", 1)
            else:
                block_type, address = payload, None

            scene_pos = self.mapToScene(event.position().toPoint())

            if getattr(self.scene(), 'snap_enabled', True):
                grid = self.scene().grid_size
                x = round(scene_pos.x() / grid) * grid
                y = round(scene_pos.y() / grid) * grid
            else:
                x, y = scene_pos.x(), scene_pos.y()

            self.scene().add_block_from_library(block_type, x, y, address=address)
            event.acceptProposedAction()
        else:
            event.ignore()
