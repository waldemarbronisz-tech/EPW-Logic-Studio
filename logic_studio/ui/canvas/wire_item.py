from PySide6.QtWidgets import QGraphicsPathItem, QMenu
from PySide6.QtGui import QPainterPath, QPen, QColor, QCursor, QFont
from PySide6.QtCore import Qt, QPointF, QRectF

from logic_studio.ui.canvas import style
from logic_studio.ui.canvas import routing


def _port_facing(port) -> int:
    """+1 if `port` is mounted on the RIGHT edge of its parent block, -1
    if on the LEFT edge — every port in this app sits at local x=0 or
    x=width (see BlockItem's own pin-layout code), so this threshold is
    safe regardless of block type, and regardless of whether the port is
    nominally an input or an output: a WireItem's source_port/dest_port
    only record which end the user clicked FIRST/SECOND while dragging a
    new wire, not which one is logically the output — routing off of each
    port's own mounted side, rather than off source-vs-dest or relative
    on-screen position, is what makes a wire always leave/enter a module
    from the side its own connector is actually on."""
    parent = port.parentItem()
    width = getattr(parent, 'width', None)
    if not width:
        return 1
    return 1 if port.pos().x() >= width / 2.0 else -1


class WireItem(QGraphicsPathItem):
    def __init__(self, source_port, dest_port=None, parent=None, wire=None,
                 fixed_free_end=None, label_info=None):
        """`wire` (fix/wire-labels-and-project-integrity §A4): the
        core.wire.Wire record this item renders a label for, or None
        for the common plain wire with no metadata at all
        (core/wire.py's own "gets NO Wire record at all" case).
        `fixed_free_end` (QPointF, scene coords): set ONLY for a
        PERSISTED free end (main_window.py's own scene-reconstruction
        code) — distinct from `temp_end_point`, which follows the
        cursor live while a NEW wire is still being dragged and must
        never be treated as a free end's fixed position. `label_info`:
        the precomputed dict from compiler/label_merge.py's
        describe_label_groups() for this wire's own label, or None —
        computed ONCE per scene rebuild, never inside paint()."""
        super().__init__(parent)
        self.source_port = source_port
        self.dest_port = dest_port
        self.wire = wire
        self.fixed_free_end = fixed_free_end
        self.label_info = label_info
        self.temp_end_point = None # Used when dragging a new wire

        self.setZValue(-1) # Draw wires behind blocks
        self.setFlag(QGraphicsPathItem.ItemIsSelectable, True)

        self.color = style.COLOR_LOGIC_LOW # OFF state
        self.thickness = style.WIRE_THICKNESS

        self.update_path()

    def _obstacle_rects(self):
        """Every OTHER block's scene bounding rect — never this wire's own
        source/destination block, which the wire obviously has to touch.
        feat/wire-routing-obstacle-avoidance."""
        scene = self.scene()
        if scene is None:
            return []
        from logic_studio.ui.canvas.block_item import BlockItem
        own_blocks = set()
        source_block = self.source_port.parentItem() if self.source_port else None
        if source_block is not None:
            own_blocks.add(source_block)
        if self.dest_port is not None:
            dest_block = self.dest_port.parentItem()
            if dest_block is not None:
                own_blocks.add(dest_block)
        return [
            item.sceneBoundingRect()
            for item in scene.items()
            if isinstance(item, BlockItem) and item not in own_blocks
        ]

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
        # §A4: a PERSISTED free end (fixed_free_end) takes priority over
        # temp_end_point — the latter is only ever set while a brand new
        # wire is actively being dragged, and must never be confused
        # with a saved Wire's own free-end coordinates.
        if self.dest_port is not None:
            end_pos = self.dest_port.scenePos()
        elif self.fixed_free_end is not None:
            end_pos = self.fixed_free_end
        else:
            end_pos = self.temp_end_point

        if not end_pos:
            return

        path = QPainterPath(start_pos)

        # Orthogonal Manhattan routing, rigid/square (no rounding), built
        # from a padded "stub" at each end that always points OUT of its
        # own connector — rightward from a right-mounted port, leftward
        # from a left-mounted one (see _port_facing()) — instead of
        # deciding direction from which end is source vs dest or from
        # their relative on-screen X. That old relative-position test
        # (previously: route straight across only when the dest was
        # comfortably to the right; loop around otherwise) could make a
        # module's own wires leave/enter from whichever side happened to
        # face the other end that particular time, and looked especially
        # wrong for a short vertical offset with little horizontal room:
        # the "loop around" shape's own 15px final approach segment is
        # easy to miss at a glance next to a 40px+ forced detour, reading
        # as "enters from below" even though it technically still entered
        # from the left. Padding BOTH ends first and only THEN connecting
        # the two stub points (which — since both already face the right
        # way — can always be joined by a plain 2-bend Manhattan path, no
        # separate "is there room" case) makes every wire's own
        # first/last segment the same fixed length in the correct
        # direction regardless of geometry, forward or backward.
        offset = 15  # Minimum extension before turning

        start_stub = QPointF(start_pos.x() + offset * _port_facing(self.source_port), start_pos.y())

        if self.dest_port is not None:
            end_stub = QPointF(end_pos.x() + offset * _port_facing(self.dest_port), end_pos.y())
        else:
            # Dragging a new wire with no real pin at the far end yet —
            # just follow the cursor directly, no padding to fake.
            end_stub = end_pos

        # feat/wire-routing-obstacle-avoidance: the stub-to-stub middle
        # section — previously always the plain 1-2-bend path above — now
        # goes through routing.route(), which tries that exact same cheap
        # path FIRST and only reaches for a grid-based A* search around
        # every other block when it actually crosses one. A wire between
        # two blocks with a clear line between them (the common case)
        # costs exactly what it did before this module existed; only a
        # backward/crossing connection in a tight layout pays for the
        # search.
        obstacles = self._obstacle_rects() if self.dest_port is not None else []
        middle = routing.route(start_stub, end_stub, obstacles)  # starts with start_stub itself
        for point in middle:
            path.lineTo(point.x(), point.y())
        if end_stub != end_pos:
            path.lineTo(end_pos.x(), end_pos.y())

        self.setPath(path)

        # SquareCap and MiterJoin ensure strict 90-degree visually sharp lines
        pen = QPen(self.color, self.thickness, Qt.SolidLine, Qt.SquareCap, Qt.MiterJoin)
        if self.isSelected():
            pen.setColor(style.COLOR_WIRE_SELECTED)
            pen.setWidth(self.thickness) # Keep thickness same but change color
        self.setPen(pen)

    # ---- fix/wire-labels-and-project-integrity §A4: label rendering -----------
    # A4.1 (fully-connected, labeled): text above the wire, canvas-colored
    # background patch. A4.2 (free end, labeled): bold name above the
    # wire, a short vertical tick down to it, and an X marker ON the wire
    # at the free end itself — deliberately NOT the same shape as
    # PortItem's own disabled-input stub (a short segment ending in a
    # perpendicular dash), so the two "why is this not wired further"
    # annotations are never mistaken for each other. A4.3: smaller sub-
    # text below the name — only for a free end (a fully-connected
    # wire's other end is already visible on screen, nothing more to
    # say) — the resolved source's rounded position for a receiver stub,
    # or the receiver count for a source stub; both come from
    # `label_info` (compiler/label_merge.py's describe_label_groups()),
    # precomputed once per scene rebuild, never here. A4.4: the error
    # color from style.py when `label_info["has_error"]`, no other
    # color decided in this file.

    _LABEL_MARGIN = 40  # boundingRect() padding above the path for the label/tick/marker

    def boundingRect(self):
        base = super().boundingRect()
        if self.wire is None or not self.wire.has_label():
            return base
        return base.adjusted(-40, -self._LABEL_MARGIN, 40, 10)

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        if self.wire is None or not self.wire.has_label():
            return
        self._paint_label(painter)

    def _label_anchor_point(self):
        path = self.path()
        if path.elementCount() == 0:
            return None
        if self.fixed_free_end is not None:
            return path.pointAtPercent(1.0)
        return path.pointAtPercent(0.5)

    def _label_color(self):
        info = self.label_info
        if info is not None and info.get("has_error"):
            return style.COLOR_ERROR
        return style.COLOR_TAG_TEXT

    def label_geometry(self):
        """Computed WITHOUT a painter (QFontMetricsF alone) so both
        _paint_label() and §A4.6's geometric non-overlap test can use
        the exact same rects — "the text itself", not this whole wire's
        path bounding box, which necessarily touches its own block at
        the connecting end and would make any overlap check against
        that meaningless. Returns None if there's nothing to draw."""
        from PySide6.QtGui import QFont, QFontMetricsF

        anchor = self._label_anchor_point()
        if anchor is None or self.wire is None or not self.wire.has_label():
            return None
        is_free_end = self.fixed_free_end is not None
        text = self.wire.label

        font = QFont(style.FONT_FAMILY, style.FONT_SIZE_TAG, QFont.Bold if is_free_end else QFont.Normal)
        metrics = QFontMetricsF(font)
        text_width = metrics.horizontalAdvance(text)
        label_y = anchor.y() - (28 if is_free_end else 8)
        text_rect = QRectF(anchor.x() - text_width / 2, label_y - metrics.ascent(), text_width, metrics.height())

        sub_rect = None
        if is_free_end:
            sub_text = self._sub_label_text()
            if sub_text:
                sub_font = QFont(style.FONT_FAMILY, style.FONT_SIZE_COMMENT)
                sub_metrics = QFontMetricsF(sub_font)
                sub_width = sub_metrics.horizontalAdvance(sub_text)
                sub_rect = QRectF(anchor.x() - sub_width / 2, text_rect.bottom(), sub_width, sub_metrics.height())

        return {"anchor": anchor, "is_free_end": is_free_end, "text": text,
                "text_rect": text_rect, "sub_rect": sub_rect}

    def _paint_label(self, painter):
        geometry = self.label_geometry()
        if geometry is None:
            return
        anchor = geometry["anchor"]
        is_free_end = geometry["is_free_end"]
        text_rect = geometry["text_rect"]
        text_color = self._label_color()

        # A4.1: canvas-colored patch behind the text so it never blends
        # into the background grid dots.
        painter.setFont(QFont(style.FONT_FAMILY, style.FONT_SIZE_TAG, QFont.Bold if is_free_end else QFont.Normal))
        painter.fillRect(text_rect.adjusted(-2, -1, 2, 1), style.COLOR_BACKGROUND)
        painter.setPen(QPen(text_color))
        painter.drawText(text_rect, Qt.AlignCenter, geometry["text"])

        if not is_free_end:
            return  # A4.3/A4.2 marker: free ends only, see class docstring above

        # A4.2: short vertical tick from the name down to the wire.
        painter.setPen(QPen(text_color, 1))
        painter.drawLine(QPointF(anchor.x(), text_rect.bottom()), QPointF(anchor.x(), anchor.y() - 6))

        # A4.2: X marker on the wire at the free end itself — an X, not
        # PortItem's own perpendicular-dash stub shape.
        half = 4
        painter.drawLine(QPointF(anchor.x() - half, anchor.y() - half), QPointF(anchor.x() + half, anchor.y() + half))
        painter.drawLine(QPointF(anchor.x() - half, anchor.y() + half), QPointF(anchor.x() + half, anchor.y() - half))

        # A4.3: sub-label, smaller/lighter, right under the name.
        sub_rect = geometry["sub_rect"]
        if sub_rect is None:
            return
        painter.setFont(QFont(style.FONT_FAMILY, style.FONT_SIZE_COMMENT))
        painter.fillRect(sub_rect.adjusted(-2, 0, 2, 0), style.COLOR_BACKGROUND)
        painter.setPen(QPen(style.COLOR_COMMENT_TEXT))
        painter.drawText(sub_rect, Qt.AlignCenter, self._sub_label_text())

    def _sub_label_text(self) -> str:
        """A4.3: for a RECEIVER stub (this end is a Pin.DIR_INPUT), the
        resolved source's position rounded to the nearest hundred; for a
        SOURCE stub, the receiver count. Empty when label_info wasn't
        supplied (e.g. a wire drawn but not yet part of a rebuilt scene)
        or the group currently has no resolvable single source."""
        if self.label_info is None:
            return ""
        from logic_studio.blocks.pin import Pin
        anchor_pin = self.source_port.pin
        if anchor_pin.direction == Pin.DIR_OUTPUT:
            return f"-> {self.label_info['receiver_count']} odb."
        source_pos = self.label_info.get("source_pos")
        if source_pos is None:
            return ""
        rx = round(source_pos[0] / 100.0) * 100
        ry = round(source_pos[1] / 100.0) * 100
        return f"z ({rx}, {ry})"

    # ---- fix/wire-labels-and-project-integrity §A4.5: navigation --------------

    def _other_end_pins(self):
        """Every OTHER real pin in this label's own network node
        (compiler/label_merge.py's grouping) — the target(s) a double-
        click/Enter on a labeled free end navigates to. Empty for an
        unlabeled free end (nothing to navigate to) or one whose group
        can't be resolved right now."""
        if self.wire is None or not self.wire.has_label():
            return []
        project = self._current_project()
        if project is None:
            return []
        from logic_studio.compiler.label_merge import group_labeled_pins
        groups = group_labeled_pins(project.wires, project.blocks)
        group = groups.get(self.wire.label.strip().lower())
        if group is None:
            return []
        anchor_pin = self.source_port.pin
        return [p for p in group["pins"] if p.uuid != anchor_pin.uuid]

    def _ref_for_target_pin(self, pin, blocks) -> str:
        for block in blocks:
            if pin in block.inputs or pin in block.outputs:
                return block.short_id or block.display_name
        return "?"

    def navigate_to_other_end(self):
        """§A4.5: "przenosi widok do drugiego końca węzła" — a single
        target jumps straight there; several (a fanned-out source)
        raises a menu to pick which one, rather than guessing."""
        targets = self._other_end_pins()
        if not targets:
            return
        scene = self.scene()
        if scene is None or not scene.views():
            return
        view = scene.views()[0]
        from logic_studio.ui.canvas.navigation import jump_to_pin

        if len(targets) == 1:
            jump_to_pin(scene, view, targets[0].uuid)
            return

        project = self._current_project()
        blocks = project.blocks if project is not None else []
        menu = QMenu()
        action_by_pin = {}
        for pin in targets:
            action = menu.addAction(self._ref_for_target_pin(pin, blocks))
            action_by_pin[action] = pin
        chosen = menu.exec(QCursor.pos())
        target_pin = action_by_pin.get(chosen)
        if target_pin is not None:
            jump_to_pin(scene, view, target_pin.uuid)

    def mouseDoubleClickEvent(self, event):
        if self.fixed_free_end is not None:
            self.navigate_to_other_end()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    # ---- fix/wire-labels-and-project-integrity §A3.1: context menu -----------

    def _current_window(self):
        try:
            return self.scene().views()[0].window()
        except Exception:
            return None

    def _current_project(self):
        window = self._current_window()
        return getattr(window, 'project', None) if window is not None else None

    def _existing_wire_record(self, project):
        if self.dest_port is None:
            return None
        from logic_studio.ui.canvas.wire_ops import find_wire_for_pins
        return find_wire_for_pins(project, self.source_port.pin.uuid, self.dest_port.pin.uuid)

    def contextMenuEvent(self, event):
        # §A3.1 only applies to a REAL, fully-connected wire — never the
        # live rubber-band while dragging a new one (self.dest_port is
        # None during that, temp_end_point following the cursor instead).
        if self.dest_port is None:
            event.ignore()
            return
        project = self._current_project()
        if project is None:
            event.ignore()
            return

        existing_wire = self._existing_wire_record(project)
        has_label = existing_wire is not None and existing_wire.has_label()

        menu = QMenu()
        menu.setStyleSheet("""
            QMenu { background-color: #F0F0F0; border: 1px solid #A0A0A0; }
            QMenu::item { padding: 4px 20px; color: black; }
            QMenu::item:selected { background-color: #0078D7; color: white; }
            QMenu::item:disabled { color: #A0A0A0; }
        """)
        set_label_action = menu.addAction("Nadaj etykietę...")
        remove_label_action = menu.addAction("Usuń etykietę")
        remove_label_action.setEnabled(has_label)
        menu.addSeparator()
        convert_action = menu.addAction("Zamień na odnośnik")

        chosen = menu.exec(QCursor.pos())
        if chosen == set_label_action:
            self._prompt_set_label(project, existing_wire)
        elif chosen == remove_label_action:
            self._remove_label(project, existing_wire)
        elif chosen == convert_action:
            self._convert_to_stubs(project)
        event.accept()

    def _push_state_if_possible(self, project, window):
        project.push_state()
        if window is not None:
            window.set_dirty()

    def _refresh_scene(self, window):
        scene = self.scene()
        if scene is not None and window is not None:
            scene.clear()
            window._reconstruct_scene()

    def _prompt_set_label(self, project, existing_wire):
        from logic_studio.ui.canvas.wire_ops import get_or_create_wire_for_pins
        from logic_studio.ui.label_dialog import prompt_for_label

        window = self._current_window()
        initial = existing_wire.label if existing_wire is not None else ""
        text, similar = prompt_for_label(window, project, initial=initial, title="Nadaj etykietę")
        if text is None:
            return  # cancelled

        self._push_state_if_possible(project, window)
        wire = get_or_create_wire_for_pins(project, self.source_port.pin.uuid, self.dest_port.pin.uuid)
        wire.label = text
        if similar and window is not None:
            window.statusBar().showMessage(f"Podobna etykieta w projekcie: {similar}", 5000)
        self._refresh_scene(window)

    def _remove_label(self, project, existing_wire):
        if existing_wire is None:
            return
        window = self._current_window()
        self._push_state_if_possible(project, window)
        from logic_studio.ui.canvas.wire_ops import clear_label_and_prune_if_pointless
        clear_label_and_prune_if_pointless(project, existing_wire)
        self._refresh_scene(window)

    def _convert_to_stubs(self, project):
        from logic_studio.ui.canvas.wire_ops import convert_wire_to_stubs
        from logic_studio.ui.label_dialog import prompt_for_label

        window = self._current_window()
        self._push_state_if_possible(project, window)
        wire_at_source, wire_at_dest = convert_wire_to_stubs(project, self.source_port, self.dest_port)

        text, similar = prompt_for_label(window, project, initial="", title="Zamień na odnośnik")
        if text:
            wire_at_source.label = text
            wire_at_dest.label = text
            if similar and window is not None:
                window.statusBar().showMessage(f"Podobna etykieta w projekcie: {similar}", 5000)
        self._refresh_scene(window)
