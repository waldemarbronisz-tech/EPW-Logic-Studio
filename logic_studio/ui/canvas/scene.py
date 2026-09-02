from PySide6.QtWidgets import QGraphicsScene
from PySide6.QtGui import QPen, QColor, QCursor
from PySide6.QtCore import Qt, QLineF, QPointF, Signal

from logic_studio.ui.canvas import style

class LogicScene(QGraphicsScene):
    # Emitted whenever a block is placed via the library (drag or double-click)
    # — MainWindow connects this to LibraryPanel.record_recently_used() (§4.7)
    # so "recently used" reflects every insertion path, not just one of them.
    block_added = Signal(str)
    # feat/clipboard-and-align §1.5: emitted whenever copy/cut/paste changes
    # whether the clipboard is empty — MainWindow updates the Paste action's
    # enabled state from this instead of polling.
    clipboard_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSceneRect(-5000, -5000, 10000, 10000)

        # feat/clipboard-and-align §1.1: an IN-APP clipboard, not QClipboard
        # — exchanging schematic fragments between separate instances of
        # the program is out of scope. Shaped like the project file's own
        # "blocks" section (each block's serialize() dict, pin connections
        # embedded exactly as project.py stores them) — there is no
        # separate top-level "wires" key in the current .epwlogic format to
        # mirror; see ARCHITECTURE.md's clipboard section for why this
        # shape was chosen anyway.
        self.clipboard_data = None
        # §1.4: repeated Ctrl+V without a fresh copy/cut cascades so copies
        # don't stack — reset to 0 on every copy_selected_items()/
        # cut_selected_items() call, incremented on every paste.
        self._paste_cascade = 0

        # feat/clipboard-and-align §2.2: BlockItems in the order they
        # entered the CURRENT selection — maintained by
        # _on_item_selected_changed(), called from BlockItem.itemChange()
        # on ItemSelectedHasChanged, the one place every selection change
        # already passes through.
        self.selection_order = []
        # Block placement / port-grid snap unit (feat/editor-modes-and-
        # geometry §1.1) — equal to GRID_MINOR, the finer of the two
        # background dot spacings below.
        self.grid_size = style.GRID_SNAP
        self.grid_visible = True
        self.snap_enabled = True

        # Industrial visual style for grid: fine dots everywhere at
        # GRID_MINOR (== the snap unit blocks/ports actually align to),
        # with a stronger dot every GRID_MAJOR (every other fine one) purely
        # as a visual rhythm aid — GRID_MAJOR itself is NOT a separate snap
        # unit, unlike the old (pre-§1) two-tier grid where the coarser
        # value doubled as both.
        self.minor_grid_size = style.GRID_MINOR
        self.minor_grid_pen = QPen(style.COLOR_GRID_MINOR)
        self.minor_grid_pen.setWidth(style.GRID_LINE_WIDTH)
        self.minor_grid_pen.setStyle(Qt.DotLine)

        self.major_grid_size = style.GRID_MAJOR
        self.grid_color = style.COLOR_GRID
        self.grid_pen = QPen(self.grid_color)
        self.grid_pen.setWidth(style.GRID_LINE_WIDTH)
        self.grid_pen.setStyle(Qt.DotLine)

        # Wiring State
        self.current_wire = None
        self.wiring_start_port = None

        # feat/clipboard-and-align §3.1: selected blocks' positions AT
        # PRESS TIME, set in mousePressEvent and consumed in
        # mouseReleaseEvent — lets release tell an actual drag from a mere
        # click on an already-selected block (which used to push_state()
        # unconditionally, flooding the undo stack with no-op entries).
        self._press_positions = {}
        # §3.2: the project's full serialized state AT PRESS TIME, pushed
        # instead of a post-mutation snapshot when a drag or wire-connect
        # actually happens — see mousePressEvent/mouseReleaseEvent.
        self._press_state_snapshot = None

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
        """feat/clipboard-and-align §1.6: shares its implementation with
        copy+paste instead of keeping a second, connection-losing
        duplication path — the old body cloned each block independently
        with no attempt to preserve wires between them at all. Shortcut
        (Ctrl+D, keyPressEvent below) and user-visible behavior (the
        duplicate lands near the original, already selected) are
        unchanged; connections between duplicated blocks now survive,
        which they never did before."""
        if self.copy_selected_items():
            self.paste_clipboard()

    # ---- Clipboard: copy / cut / paste (§1) ------------------------------------

    def copy_selected_items(self) -> bool:
        """§1.2: serializes every selected block, keeping only the
        connections that land INSIDE the selection (a connection to a pin
        outside it is silently dropped — expected, not an error). Returns
        False (clipboard left untouched) when nothing was selected."""
        from logic_studio.ui.canvas.block_item import BlockItem

        blocks = [item.logic_block for item in self.selectedItems() if isinstance(item, BlockItem)]
        if not blocks:
            return False

        selected_pin_uuids = {p.uuid for b in blocks for p in (b.inputs + b.outputs)}

        blocks_data = []
        for block in blocks:
            data = block.serialize()
            # serialize() returns a FRESH dict/lists each call — safe to
            # mutate here without touching the live block's own pins.
            for key in ("inputs", "outputs"):
                for pin_data in data[key]:
                    pin_data["connections"] = [c for c in pin_data["connections"] if c in selected_pin_uuids]
            blocks_data.append(data)

        # §1.2: relative positions, counted from the top-left corner of the
        # rectangle bounding the selection — block.x/y is already each
        # block's own top-left in scene coordinates.
        origin_x = min(b.x for b in blocks)
        origin_y = min(b.y for b in blocks)

        self.clipboard_data = {"blocks": blocks_data, "origin": (origin_x, origin_y)}
        self._paste_cascade = 0
        self.clipboard_changed.emit()
        return True

    def cut_selected_items(self):
        """§1.3: copy, then delete the selection AND every wire touching
        it — including ones leaving the selection, which delete_selected_
        items() already removes regardless of copy's own internal-only
        filtering. delete_selected_items() pushes exactly one undo
        snapshot; copy itself pushes none, so cut is one undo entry."""
        if self.copy_selected_items():
            self.delete_selected_items()

    def clipboard_is_empty(self) -> bool:
        return not self.clipboard_data

    def paste_clipboard(self):
        """§1.4. Fresh UUIDs for every block and pin; new short_id per
        Project.add_block()'s existing rules (never re-densified — see
        core/short_id.py); internal connections remapped to the new pin
        UUIDs; properties (Address/Bit/Tag/Comment/...) copied unchanged.
        One undo entry regardless of how many blocks are in the
        clipboard."""
        if not self.clipboard_data or not self.views():
            return

        from logic_studio.blocks.registry import BlockRegistry
        from logic_studio.blocks.pin import Pin
        from logic_studio.ui.canvas.block_item import BlockItem

        window = self.views()[0].window()
        project = getattr(window, 'project', None)
        if project is None:
            return

        anchor = self._paste_anchor()
        origin_x, origin_y = self.clipboard_data["origin"]
        delta_x = anchor.x() - origin_x
        delta_y = anchor.y() - origin_y

        project.push_state()
        window.set_dirty()

        # Fields restored per-pin from the copied data, deliberately
        # EXCLUDING uuid/direction/name/data_type (the pin's own identity,
        # already correct — freshly minted by the new block's own
        # constructor) and connections (remapped separately, below, since
        # they still point at the ORIGINAL pins' now-stale UUIDs).
        pin_copy_fields = tuple(
            f for f in Pin.SERIALIZED_FIELDS
            if f not in Pin._IDENTITY_FIELDS and f != "uuid" and f != "connections"
        )

        uuid_map = {}   # old pin uuid -> new pin uuid
        new_blocks = []
        for b_data in self.clipboard_data["blocks"]:
            block_class = BlockRegistry.get_block_class(b_data.get("type_id"))
            if block_class is None:
                continue  # defensive: shouldn't happen, the type existed when copied

            new_block = block_class.deserialize(b_data)
            # deserialize() restores SERIALIZED_FIELDS values PRESENT in
            # b_data — including the ORIGINAL's uuid and short_id. Both
            # must be fresh for a paste (§1.4): a new uuid so the pasted
            # block is a genuinely distinct object, and short_id cleared so
            # Project.add_block() below mints the next free one instead of
            # colliding with the block it was copied from (core/short_id.py
            # §4.2's same rule clone() already follows).
            import uuid as uuid_module
            new_block.uuid = str(uuid_module.uuid4())
            new_block.short_id = ""

            # Pass 1 (per block): copy the non-identity pin fields, and
            # seed `connections` with the COPIED (still stale, still
            # pointing at the ORIGINAL pins') UUIDs — pass 2, after every
            # block in the clipboard has been through this loop and
            # uuid_map is complete, rewrites them onto the new pins.
            # Forgetting this seed step (and just letting the new pin's own
            # constructor-default empty `connections` stand) was a real bug
            # caught by test_copy_paste_two_connected_blocks: the remap
            # loop below has nothing to remap if connections was never
            # populated from pin_data in the first place.
            for i, pin_data in enumerate(b_data.get("inputs", [])):
                if i < len(new_block.inputs):
                    uuid_map[pin_data["uuid"]] = new_block.inputs[i].uuid
                    new_block.inputs[i].connections = list(pin_data.get("connections", []))
                    for field in pin_copy_fields:
                        if field in pin_data:
                            setattr(new_block.inputs[i], field, pin_data[field])
            for i, pin_data in enumerate(b_data.get("outputs", [])):
                if i < len(new_block.outputs):
                    uuid_map[pin_data["uuid"]] = new_block.outputs[i].uuid
                    new_block.outputs[i].connections = list(pin_data.get("connections", []))
                    for field in pin_copy_fields:
                        if field in pin_data:
                            setattr(new_block.outputs[i], field, pin_data[field])

            new_x = new_block.x + delta_x
            new_y = new_block.y + delta_y
            if self.snap_enabled:
                new_x = round(new_x / self.grid_size) * self.grid_size
                new_y = round(new_y / self.grid_size) * self.grid_size
            new_block.set_position(new_x, new_y)

            project.add_block(new_block)  # assigns the fresh short_id
            new_blocks.append(new_block)

        # Remap connections onto the new pin UUIDs. copy() already limited
        # every connection to pins inside the selection, so every UUID here
        # is expected to be in uuid_map — the extra membership check is
        # defensive, not load-bearing.
        for block in new_blocks:
            for pin in block.inputs + block.outputs:
                pin.connections = [uuid_map[c] for c in pin.connections if c in uuid_map]

        self._warn_about_duplicate_output_addresses(new_blocks, project, window)

        self.clearSelection()
        new_items = []
        for block in new_blocks:
            item = BlockItem(block)
            self.addItem(item)
            new_items.append(item)
        self._create_wire_items(new_items)
        for item in new_items:
            item.setSelected(True)

        self._paste_cascade += 1

    def _paste_anchor(self) -> QPointF:
        """§1.4 paste position: the selection's top-left lands at the
        cursor (snapped) when it's over the canvas; otherwise one grid
        cell past the copied origin. Either way, repeated pastes without a
        fresh copy/cut cascade by one more grid cell each time so copies
        don't stack."""
        grid = self.grid_size
        cascade = self._paste_cascade * grid if self.snap_enabled else self._paste_cascade * 10

        view = self.views()[0]
        local_pos = view.mapFromGlobal(QCursor.pos())
        if view.viewport().rect().contains(local_pos):
            scene_pos = view.mapToScene(local_pos)
            if self.snap_enabled:
                x = round(scene_pos.x() / grid) * grid
                y = round(scene_pos.y() / grid) * grid
            else:
                x, y = scene_pos.x(), scene_pos.y()
            return QPointF(x + cascade, y + cascade)

        origin_x, origin_y = self.clipboard_data["origin"]
        step = grid if self.snap_enabled else 10
        return QPointF(origin_x + step + cascade, origin_y + step + cascade)

    def _create_wire_items(self, new_items):
        """Recreates WireItem graphics for connections between the given
        (freshly pasted) BlockItems — copy_selected_items() already
        limited every connection to pins inside the selection, so every
        connection here is between two of these same new blocks."""
        from logic_studio.ui.canvas.wire_item import WireItem
        from logic_studio.ui.canvas.port_item import PortItem

        port_by_pin_uuid = {}
        for item in new_items:
            for child in item.childItems():
                if isinstance(child, PortItem):
                    port_by_pin_uuid[child.pin.uuid] = child

        for item in new_items:
            for out_pin in item.logic_block.outputs:
                for conn_uuid in out_pin.connections:
                    source_port = port_by_pin_uuid.get(out_pin.uuid)
                    dest_port = port_by_pin_uuid.get(conn_uuid)
                    if source_port and dest_port:
                        self.addItem(WireItem(source_port, dest_port))

    # type_id -> the property naming its address/signal, for output-shaped
    # blocks only (§1.4's duplicate-source warning). "virtual.output" is
    # "Wyjście bitowe" in the library.
    _OUTPUT_ADDRESS_PROPERTY = {
        "output.do": "Address",
        "output.ao": "Address",
        "virtual.output": "Bit",
    }

    def _warn_about_duplicate_output_addresses(self, new_blocks, project, window):
        """§1.4: pasting an output block (DO/AO/Wyjście bitowe) creates a
        second source for its address — a compile error. Deliberately NOT
        cleared silently and NOT blocked here: the address is very often
        exactly what the engineer is about to edit next, and clearing it
        would force retyping it from scratch. Instead: paste it as-is and
        say so on the status bar."""
        count = 0
        for new_block in new_blocks:
            prop = self._OUTPUT_ADDRESS_PROPERTY.get(new_block.type_id)
            if prop is None:
                continue
            value = new_block.properties.get(prop, "")
            if not value:
                continue
            collides = any(
                b.uuid != new_block.uuid and b.type_id == new_block.type_id and b.properties.get(prop, "") == value
                for b in project.blocks
            )
            if collides:
                count += 1

        if count and hasattr(window, 'statusBar'):
            window.statusBar().showMessage(
                f"Wklejono {count} bloków wyjściowych z powielonymi adresami — popraw je przed kompilacją."
            )

    def refresh_live_states(self):
        """Called by ExecutionEngine after a cycle to repaint dynamic values."""
        from logic_studio.ui.canvas.wire_item import WireItem
        from logic_studio.ui.canvas.port_item import PortItem

        for item in self.items():
            if isinstance(item, WireItem):
                item.update_live_state()
            elif isinstance(item, PortItem):
                item.update_live_state()

    def add_block_from_library(self, type_id: str, x: float, y: float, address: str = None):
        """Called by the view upon drop event (also by the library panel's
        double-click insert). Instantiates and adds to scene. `address`, if
        given, is written straight into the new block's "Address" property
        — used when dragging a DI/DO/AI/AO leaf from DeviceExplorerPanel, so
        the block lands already configured instead of needing a property-
        grid detour to set its Address."""
        from logic_studio.blocks.registry import BlockRegistry
        from logic_studio.ui.canvas.block_item import BlockItem

        block = BlockRegistry.create_block(type_id)

        if not block:
            return # Invalid drop

        if address and "Address" in block.properties:
            block.properties["Address"] = address

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

        self.block_added.emit(type_id)

    def drawBackground(self, painter, rect):
        """Draws an industrial engineering dot grid background: fine dots
        every GRID_MINOR (the actual block-placement/port-alignment unit),
        with a stronger dot every GRID_MAJOR (every other fine one, §1.1) —
        a visual rhythm aid only; GRID_MAJOR is not itself a snap unit."""
        super().drawBackground(painter, rect)

        if not self.grid_visible:
            return

        minor_left = int(rect.left()) - (int(rect.left()) % self.minor_grid_size)
        minor_top = int(rect.top()) - (int(rect.top()) % self.minor_grid_size)

        minor_lines = []
        for x in range(minor_left, int(rect.right()), self.minor_grid_size):
            if x % self.major_grid_size != 0:
                minor_lines.append(QLineF(x, rect.top(), x, rect.bottom()))
        for y in range(minor_top, int(rect.bottom()), self.minor_grid_size):
            if y % self.major_grid_size != 0:
                minor_lines.append(QLineF(rect.left(), y, rect.right(), y))

        painter.setPen(self.minor_grid_pen)
        painter.drawLines(minor_lines)

        major_left = int(rect.left()) - (int(rect.left()) % self.major_grid_size)
        major_top = int(rect.top()) - (int(rect.top()) % self.major_grid_size)

        lines = []
        for x in range(major_left, int(rect.right()), self.major_grid_size):
            lines.append(QLineF(x, rect.top(), x, rect.bottom()))
        for y in range(major_top, int(rect.bottom()), self.major_grid_size):
            lines.append(QLineF(rect.left(), y, rect.right(), y))

        painter.setPen(self.grid_pen)
        painter.drawLines(lines)

    def mousePressEvent(self, event):
        item = self.itemAt(event.scenePos(), self.views()[0].transform())

        from logic_studio.ui.canvas.port_item import PortItem
        from logic_studio.ui.canvas.wire_item import WireItem

        # feat/clipboard-and-align §3.1/§3.2: snapshot the project's state
        # BEFORE any live mutation this press might lead to (a block drag,
        # applied live by BlockItem.itemChange() as the mouse moves; or a
        # successful wire connection, applied live by Pin.connect() below)
        # — mouseReleaseEvent pushes THIS pre-mutation snapshot rather than
        # a fresh one taken after the fact, so undo actually restores the
        # pre-drag/pre-connect state. Left-button only, matching the same
        # gesture the release side already restricts itself to.
        if event.button() == Qt.LeftButton:
            window = self.views()[0].window()
            project = getattr(window, 'project', None)
            self._press_state_snapshot = project.serialize() if project else None
        else:
            self._press_state_snapshot = None

        if event.button() == Qt.LeftButton and isinstance(item, PortItem):
            self.wiring_start_port = item
            self.current_wire = WireItem(source_port=item)
            self.current_wire.temp_end_point = event.scenePos()
            self.addItem(self.current_wire)
            event.accept()
            return

        super().mousePressEvent(event)

        # snapshot AFTER Qt's own default click-to-select handling above
        # has run, so this reflects the set of blocks that will actually
        # be dragged (or merely clicked) — compared against their
        # positions again in mouseReleaseEvent.
        from logic_studio.ui.canvas.block_item import BlockItem
        self._press_positions = {
            i: (i.pos().x(), i.pos().y())
            for i in self.selectedItems() if isinstance(i, BlockItem)
        }

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
        # feat/clipboard-and-align §3.1: push_state() only when a selected
        # block's position ACTUALLY changed between press and release —
        # this used to fire on EVERY release over a selected block
        # (comment used to read "for MVP forcing state on release if
        # selected works"), flooding the undo stack with a no-op entry on
        # every plain click. _press_positions is set in mousePressEvent.
        window = self.views()[0].window()
        project = getattr(window, 'project', None)

        from logic_studio.ui.canvas.block_item import BlockItem
        moved_items = [i for i in self.selectedItems() if isinstance(i, BlockItem)]
        actually_moved = any(
            self._press_positions.get(i) != (i.pos().x(), i.pos().y())
            for i in moved_items
        )
        if project and actually_moved and event.button() == Qt.LeftButton:
            # §3.2: push the snapshot taken BEFORE the drag (in
            # mousePressEvent), not project.serialize() taken now — by
            # release time BlockItem.itemChange() has already applied the
            # move live, so serializing now would push the POST-move
            # state and make undo() a no-op.
            project.push_state(self._press_state_snapshot)
            window.set_dirty()
        self._press_positions = {}

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
                        # §3.2: same reasoning as the drag case above —
                        # pin.connect() just mutated the pins live, so
                        # push the pre-connect snapshot from press time.
                        project.push_state(self._press_state_snapshot)
                        window.set_dirty()
                else:
                    self.removeItem(self.current_wire)
            else:
                self.removeItem(self.current_wire)

            self.current_wire = None
            self.wiring_start_port = None
            self._press_state_snapshot = None
            event.accept()
            return

        self._press_state_snapshot = None

        super().mouseReleaseEvent(event)

    # ---- Selection order tracking (§2.2) ---------------------------------

    def _on_item_selected_changed(self, item, is_selected: bool):
        """Called from BlockItem.itemChange() on ItemSelectedHasChanged —
        the only place selection order is recorded. A fresh click (which
        clears the old selection first) naturally empties this list before
        the newly-clicked item(s) re-enter it, so "first selected" always
        means first in THIS selection, not some previous one."""
        if is_selected:
            if item not in self.selection_order:
                self.selection_order.append(item)
        else:
            if item in self.selection_order:
                self.selection_order.remove(item)

    def _selected_block_items_in_order(self):
        """Selected BlockItems, first-selected first. Falls back to
        appending anything selected-but-missing from selection_order at
        the end (defensive — every current selection path goes through
        itemChange(), so this should never actually trigger)."""
        from logic_studio.ui.canvas.block_item import BlockItem
        selected = [i for i in self.selectedItems() if isinstance(i, BlockItem)]
        selected_set = set(selected)
        ordered = [i for i in self.selection_order if i in selected_set]
        for item in selected:
            if item not in ordered:
                ordered.append(item)
        return ordered

    # ---- Align & distribute (§2) -------------------------------------------

    def _apply_block_positions(self, target_positions: dict):
        """target_positions: {BlockItem: (x, y)}. Applied via item.setPos()
        so the EXISTING BlockItem.itemChange() intercept — snap-to-grid
        (§2.2's "przyciągane do siatki, gdy Snap jest włączony", already
        implemented there for ordinary dragging), logic_block.
        set_position() sync, and wire-path updates — does all the real
        work; align/distribute need no snap logic of their own. Exactly
        ONE undo entry (§2.2), regardless of how many blocks actually move,
        pushed even when target_positions ends up empty (the operation was
        still "performed")."""
        if not self.views():
            return
        window = self.views()[0].window()
        project = getattr(window, 'project', None)
        if project is None:
            return
        project.push_state()
        window.set_dirty()
        for item, (x, y) in target_positions.items():
            item.setPos(x, y)

    def _run_align(self, compute_positions, min_selection: int = 2):
        blocks = self._selected_block_items_in_order()
        if len(blocks) < min_selection:
            return
        reference = blocks[0]
        self._apply_block_positions(compute_positions(blocks, reference))

    def align_left(self):
        self._run_align(lambda blocks, ref: {
            b: (ref.pos().x(), b.pos().y()) for b in blocks if b is not ref
        })

    def align_right(self):
        self._run_align(lambda blocks, ref: {
            b: (ref.pos().x() + ref.width - b.width, b.pos().y()) for b in blocks if b is not ref
        })

    def align_top(self):
        self._run_align(lambda blocks, ref: {
            b: (b.pos().x(), ref.pos().y()) for b in blocks if b is not ref
        })

    def align_bottom(self):
        self._run_align(lambda blocks, ref: {
            b: (b.pos().x(), ref.pos().y() + ref.height - b.height) for b in blocks if b is not ref
        })

    def align_center_vertical(self):
        """§2.1: "Wyśrodkuj w pionie" — aligns HORIZONTAL axes (same Y),
        i.e. every block's own vertical center lands on the reference's."""
        def compute(blocks, ref):
            center_y = ref.pos().y() + ref.height / 2.0
            return {b: (b.pos().x(), center_y - b.height / 2.0) for b in blocks if b is not ref}
        self._run_align(compute)

    def align_center_horizontal(self):
        """§2.1: "Wyśrodkuj w poziomie" — aligns VERTICAL axes (same X)."""
        def compute(blocks, ref):
            center_x = ref.pos().x() + ref.width / 2.0
            return {b: (center_x - b.width / 2.0, b.pos().y()) for b in blocks if b is not ref}
        self._run_align(compute)

    def _run_distribute(self, axis: str):
        """§2.2: distribution ignores selection ORDER entirely — it keeps
        whichever two blocks are CURRENTLY the extremes along `axis` fixed
        and spaces the rest evenly between them (equal gaps between edges,
        not equal spacing between reference points — matters once blocks
        have different widths/heights)."""
        blocks = self._selected_block_items_in_order()
        if len(blocks) < 3:
            return

        if axis == "x":
            ordered = sorted(blocks, key=lambda b: b.pos().x())
            size_attr = "width"
        else:
            ordered = sorted(blocks, key=lambda b: b.pos().y())
            size_attr = "height"

        first, last = ordered[0], ordered[-1]
        middle = ordered[1:-1]

        first_pos = first.pos().x() if axis == "x" else first.pos().y()
        last_pos = last.pos().x() if axis == "x" else last.pos().y()
        first_size = getattr(first, size_attr)
        middle_sizes = sum(getattr(b, size_attr) for b in middle)

        span = last_pos - (first_pos + first_size) - middle_sizes
        gap = span / (len(middle) + 1)

        positions = {}
        cursor = first_pos + first_size + gap
        for b in middle:
            if axis == "x":
                positions[b] = (cursor, b.pos().y())
            else:
                positions[b] = (b.pos().x(), cursor)
            cursor += getattr(b, size_attr) + gap

        self._apply_block_positions(positions)

    def distribute_horizontal(self):
        self._run_distribute("x")

    def distribute_vertical(self):
        self._run_distribute("y")


# feat/clipboard-and-align §2.1/§2.3: the 8 operations, shared between the
# Edit menu ("Wyrównaj" submenu, main_window.py) and the canvas/block
# context menu (block_item.py) so the list — and each operation's minimum
# selection size — lives in exactly one place.
ALIGN_OPERATIONS = [
    ("Wyrównaj do lewej", "align_left", 2),
    ("Wyrównaj do prawej", "align_right", 2),
    ("Wyrównaj do góry", "align_top", 2),
    ("Wyrównaj do dołu", "align_bottom", 2),
    ("Wyśrodkuj w pionie", "align_center_vertical", 2),
    ("Wyśrodkuj w poziomie", "align_center_horizontal", 2),
    (None, None, None),  # separator marker
    ("Rozłóż równomiernie w poziomie", "distribute_horizontal", 3),
    ("Rozłóż równomiernie w pionie", "distribute_vertical", 3),
]


def populate_align_menu(menu, scene: "LogicScene"):
    """§2.3: adds the 8 operations to `menu`, each enabled only when the
    current selection is large enough, wired straight to `scene`'s own
    methods."""
    selected_count = len(scene.selectedItems())
    for label, method_name, min_count in ALIGN_OPERATIONS:
        if label is None:
            menu.addSeparator()
            continue
        action = menu.addAction(label)
        action.setEnabled(selected_count >= min_count)
        action.triggered.connect(getattr(scene, method_name))
    return menu
