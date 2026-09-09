import logging


def _direct_source_block(block, input_index, blocks):
    """fix/safety-block-semantics §4: the block whose OUTPUT pin directly
    drives `block.inputs[input_index]`, or None if that input is
    unconnected or its source can't be found in `blocks`. Inputs are
    single-driver (blocks/pin.py's Pin.connect()), so there is at most one
    connection to resolve. Shared verbatim (same logic, same signature) by
    compiler/validator.py — duplicated rather than imported across that
    module boundary, since it's a handful of lines and neither module
    otherwise depends on the other."""
    if input_index >= len(block.inputs):
        return None
    connections = block.inputs[input_index].connections
    if not connections:
        return None
    source_pin_uuid = connections[0]
    for candidate in blocks:
        for pin in candidate.outputs:
            if pin.uuid == source_pin_uuid:
                return candidate
    return None


class _ExpandedProjectView:
    """feat/macro-blocks — the object Validator/GraphBuilder/Exporter
    actually run against inside Compiler.compile(): same `.settings` as the
    real project (every DeviceModel/system_signals lookup those stages make
    reads settings, never blocks), but `.blocks` is a macro-EXPANDED list
    (core/macros.py::expand_project()) instead of the live project's own
    blocks. Those three stages only ever read `.blocks`/`.settings` off
    whatever `project` they're given (never call a Project-specific method
    like add_block()/serialize()) — confirmed by grepping every
    `self.project.` use in validator.py/graph.py/exporter.py — so this
    minimal stand-in is all they need, and none of them has to know macros
    exist at all, the same reasoning that keeps them hardware-agnostic
    (ARCHITECTURE.md §1)."""

    def __init__(self, blocks, settings, wires=None):
        self.blocks = blocks
        self.settings = settings
        # feat/wire-labels §2.5/§5: Validator's free-end/label checks and
        # (from §5 onward) the label-node-merging step all need the
        # live project's Wire records too — passed through UNCHANGED
        # (never macro-expanded; a Wire's pin uuids stay valid against
        # expanded_blocks because top-level pins keep their uuid through
        # clone(preserve_uuid=True), see core/macros.py).
        self.wires = wires if wires is not None else []


class Compiler:
    """Orchestrates the process of converting Logic Studio project to Runtime JSON."""

    def __init__(self, project):
        self.project = project
        self.errors = []
        self.warnings = []
        # "info" severity (feat/internal-bits §5.2) — never blocks
        # compilation, just surfaces something worth knowing (cycle-delayed
        # internal-signal reads).
        self.infos = []

    def compile(self) -> dict:
        """Executes the compilation pipeline."""
        self.errors.clear()
        self.warnings.clear()
        self.infos.clear()
        self.last_execution_order = []
        self.status = "UNCOMPILED"

        # 0. Macro expansion (feat/macro-blocks): every macro instance is
        # recursively replaced by a fresh, independently-uuid'd copy of its
        # definition's own blocks BEFORE any other stage runs — never
        # mutates self.project (core/macros.py::expand_project()). A cycle
        # or a reference to a missing/deleted definition is surfaced here
        # exactly like a Validator error, aborting before Validator itself
        # ever sees the project.
        from logic_studio.core import macros
        expanded_blocks, wire_scopes, macro_errors = macros.expand_project(self.project)
        if macro_errors:
            self.errors.extend(macro_errors)
            self.status = "COMPILE_FAILED"
            return None

        # fix/wire-labels-and-project-integrity §B1.3: `wire_scopes` is
        # ALREADY split (project-level wires, plus one entry per macro
        # instance's own internal wires, remapped) — Validator's own
        # checks (§2.5's free-end/no-label warning) don't care about
        # scope, so they get the flat union; label-merging below runs
        # ONCE PER SCOPE instead, precisely so it never does.
        all_wires = [w for scope in wire_scopes for w in scope]
        compile_view = _ExpandedProjectView(expanded_blocks, self.project.settings, wires=all_wires)

        # 1. Label-based node merging (fix/wire-labels-and-project-
        # integrity §A1/§A2) — BEFORE Validator, deliberately: this
        # connects each label group's single source pin DIRECTLY to
        # every receiver pin (Pin.connect(), the exact same call a
        # physically-drawn wire goes through) on compile_view's already-
        # cloned pins, so by the time Validator's own generic "Input is
        # unconnected" check runs below, an input fed only through a
        # label already shows up as connected — exactly as it should,
        # since from here on GraphBuilder/Exporter/Validator never learn
        # labels exist at all; they just see Pin.connections, same as
        # always. Running this AFTER Validator instead would leave every
        # labeled input wrongly flagged "unconnected" one stage too
        # early — caught by this PR's own manual verification before
        # settling on this order.
        #
        # §B1.3: run ONCE PER SCOPE (never on the flattened `all_wires`)
        # — a label named "X" inside a macro definition must never merge
        # with a top-level "X", nor with the SAME macro's own "X" in a
        # different placed instance. Each call only ever sees its own
        # scope's wires; `expanded_blocks` is passed in full every time
        # purely for pin lookup (safe: post-expansion pin uuids are
        # unique per instance, so a scope's own wires can only ever
        # resolve to pins that are actually its own).
        from logic_studio.compiler.label_merge import merge_and_validate_labels
        for wires_in_scope in wire_scopes:
            scoped_view = _ExpandedProjectView(expanded_blocks, self.project.settings, wires=wires_in_scope)
            merge_and_validate_labels(scoped_view, self.errors, self.warnings)

        # 2. Validation Stage
        from logic_studio.compiler.validator import Validator
        validator = Validator(compile_view)
        validator.run(self.errors, self.warnings)

        # fix/safety-block-semantics §2.4: Validator just read (and, if
        # present, warned about) each analog.quality block's one-shot
        # "_max_rate_migration_notice" — but it saw an ISOLATED CLONE
        # (expand_project() clones every top-level block; see base.py's
        # clone()), so clearing the key there never reaches the live
        # project block. Cleared here, on self.project.blocks itself,
        # right after Validator's one chance to see it — this is what
        # actually makes the notice fire on the first compile only, not
        # every compile for the rest of the session.
        for block in self.project.blocks:
            block.simulation_state.pop("_max_rate_migration_notice", None)

        if self.errors:
            self.status = "COMPILE_FAILED"
            return None # Abort on validation errors

        # 3. Dependency Graph and Execution Order (Topological Sort)
        from logic_studio.compiler.graph import GraphBuilder
        graph = GraphBuilder(compile_view)
        execution_order = graph.build_and_sort(self.errors)

        if self.errors:
            self.status = "COMPILE_FAILED"
            return None

        # 4. Export Intermediate JSON
        self.last_execution_order = execution_order
        self.status = "COMPILED_VALID"
        from logic_studio.compiler.exporter import Exporter
        exporter = Exporter(compile_view, execution_order)
        compiled_data = exporter.export()
        self.warnings.extend(exporter.warnings)

        # 5. Generate isolated CompiledProgram for the ExecutionEngine.
        # Reuses `expanded_blocks` itself rather than expanding a SECOND
        # time: expand_project() already returns fresh clones distinct from
        # self.project.blocks (the isolation the old serialize()/
        # deserialize() round trip existed for, AUDIT_REPORT.md §2.1) —
        # Validator/GraphBuilder/Exporter above only ever READ block state,
        # never mutate it, so handing the ExecutionEngine these same
        # objects is safe. A second expand_project() call would NOT be
        # equivalent: it mints fresh random uuids for every macro-internal
        # block on each call (deliberately, so independent placed instances
        # of the same macro never collide — core/macros.py's
        # _expand_instance()) so a second call's uuids would silently stop
        # matching `execution_order`, built from this first call's blocks.
        from logic_studio.engine.program import CompiledProgram
        isolated_blocks = expanded_blocks

        # Resolve each AI block's analog point range once, here, since the
        # ExecutionEngine/CompiledProgram deliberately never holds a live
        # Project reference (see AUDIT_REPORT.md §2.1). Validator has already
        # confirmed the address exists with direction="input". Runs over the
        # EXPANDED list so an AI block living inside a macro's own
        # definition is resolved exactly like a top-level one.
        from logic_studio.core.device_model import DeviceModel
        for block in isolated_blocks:
            if block.type_id == "input.ai" and hasattr(block, 'set_range'):
                point = DeviceModel.get_analog_point(self.project, block.properties.get("Address", ""))
                if point:
                    block.set_range(point.get("min"), point.get("max"))

        # fix/safety-block-semantics §4.2: same reasoning as the AI range
        # resolution just above — a QualityBlock with Range Source == "Z
        # punktu analogowego" resolves ITS [min, max] from the analog
        # point of the input.ai block feeding its In pin, not from its own
        # (independently editable) Min/Max properties. Validator has
        # already confirmed In is wired directly to an input.ai block for
        # every such block that reaches here (§4.2's own error).
        for block in isolated_blocks:
            if block.type_id != "analog.quality" or not hasattr(block, 'set_range'):
                continue
            if block.properties.get("Range Source", "Własny") != "Z punktu analogowego":
                continue
            source = _direct_source_block(block, 0, isolated_blocks)
            if source is not None and source.type_id == "input.ai":
                point = DeviceModel.get_analog_point(self.project, source.properties.get("Address", ""))
                if point:
                    block.set_range(point.get("min"), point.get("max"))

        # Same reasoning, for internal-signal blocks (feat/internal-bits
        # §2): a block's "Bit" property only names a registry entry — its
        # type/retentive flag (which together determine the actual
        # M./MR./MW./MWR.<name> id) live in the registry, not on the block.
        # Validator has already confirmed every "Bit" resolves to a
        # registry entry of the matching type (§4.4/§4.5).
        from logic_studio.core.internal_bits import internal_bit_id
        _INTERNAL_SIGNAL_TYPE_IDS = ("virtual.input", "virtual.output", "internal.reg_in", "internal.reg_out")
        for block in isolated_blocks:
            if block.type_id in _INTERNAL_SIGNAL_TYPE_IDS and hasattr(block, 'set_signal_id'):
                entry = DeviceModel.get_internal_bit(self.project, block.properties.get("Bit", ""))
                if entry:
                    block.set_signal_id(internal_bit_id(entry))

        # feat/internal-bits §5: detect internal-signal reads that lag a
        # scan behind their writer, purely from execution_order position —
        # a diagnostic no reference tool offers, since finding this by hand
        # means reading execution_order directly. Runs over the EXPANDED
        # list (execution_order's own uuids are the expanded blocks' —
        # GraphBuilder/Exporter above never saw the live, macro-instance
        # project blocks either).
        delayed_reader_uuids, info_messages = self._compute_cycle_delayed_reads(execution_order, expanded_blocks)
        self.infos.extend(info_messages)

        # isolated_blocks IS expanded_blocks (see above) — execution_order,
        # built from the very same objects, matches by construction.
        program = CompiledProgram(
            blocks=isolated_blocks,
            execution_order=execution_order,
            cycle_time_ms=self.project.settings.get("cycle_time_ms", 100),
            cycle_delayed_reads=delayed_reader_uuids,
        )

        compiled_data["program"] = program
        compiled_data["cycle_delayed_reads"] = delayed_reader_uuids

        return compiled_data

    def _compute_cycle_delayed_reads(self, execution_order, blocks):
        """feat/internal-bits §5.1: for each internal signal, compares the
        execution_order INDEX of its writer against each reader's — if the
        writer's index is greater (comes later in the compiled scan), that
        reader only sees this scan's write AFTER it has already run, i.e.
        it evaluates on last scan's value. A purely structural/compile-time
        comparison, independent of how the engine happens to sequence
        is_source blocks at runtime (virtual.input/internal.reg_in are
        is_source — see virtual_io.py — so still land at a definite
        execution_order position even though the engine evaluates all
        is_source blocks in its own separate first pass each scan).

        `blocks` is the macro-EXPANDED list (execution_order's own uuids are
        theirs, not self.project.blocks' — a virtual.input/internal.reg_in
        pair living inside a macro's own definition is checked exactly like
        a top-level one).

        Returns (delayed_reader_uuids, info_messages) — the message format
        is exactly §5.2's: "[M.BLOKADA_ZS] Odczyt w bloku <tag> wyprzedza
        zapis — wartość z poprzedniego cyklu."
        """
        from logic_studio.core.device_model import DeviceModel
        from logic_studio.core.internal_bits import internal_bit_id

        WRITER_TYPE_IDS = ("virtual.output", "internal.reg_out")
        READER_TYPE_IDS = ("virtual.input", "internal.reg_in")

        order_index = {uuid: i for i, uuid in enumerate(execution_order)}
        writers_by_name = {}  # name.lower() -> (block, index)
        readers_by_name = {}  # name.lower() -> [(block, index), ...]

        for block in blocks:
            if block.type_id not in WRITER_TYPE_IDS and block.type_id not in READER_TYPE_IDS:
                continue
            name = block.properties.get("Bit", "")
            if not name or block.uuid not in order_index:
                continue
            lname = name.lower()
            idx = order_index[block.uuid]
            if block.type_id in WRITER_TYPE_IDS:
                # Validator (§4.1) already rejects more than one writer per
                # signal — compiling never reaches here with two, but guard
                # with the first one found anyway rather than assuming.
                writers_by_name.setdefault(lname, (block, idx))
            else:
                readers_by_name.setdefault(lname, []).append((block, idx))

        delayed_reader_uuids = []
        info_messages = []
        for lname, readers in readers_by_name.items():
            writer_entry = writers_by_name.get(lname)
            if writer_entry is None:
                continue  # no writer at all — §4.2 already warns about this
            writer_block, writer_idx = writer_entry
            entry = DeviceModel.get_internal_bit(self.project, writer_block.properties.get("Bit", ""))
            signal_label = internal_bit_id(entry) if entry else writer_block.properties.get("Bit", "")
            for reader_block, reader_idx in readers:
                if writer_idx > reader_idx:
                    delayed_reader_uuids.append(reader_block.uuid)
                    # feat/io-labels-and-ids §4.3: short_id, not display_name.
                    reader_ref = reader_block.short_id or reader_block.display_name
                    info_messages.append(
                        f"[{signal_label}] Odczyt w bloku {reader_ref} wyprzedza zapis — "
                        f"wartość z poprzedniego cyklu."
                    )
        return delayed_reader_uuids, info_messages
