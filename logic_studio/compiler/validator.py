def _block_owning_pin(pin_uuid, blocks):
    """feat/wire-labels §2.5: the block that owns the pin named
    `pin_uuid` (input or output, either direction) — used to name the
    block a free-end wire is still attached to. Distinct from
    `_direct_source_block()` below, which looks up a specific input's
    SOURCE by INDEX, not an arbitrary pin by its own uuid."""
    for block in blocks:
        for pin in block.inputs + block.outputs:
            if pin.uuid == pin_uuid:
                return block
    return None


def _direct_source_block(block, input_index, blocks):
    """fix/safety-block-semantics §4: see compiler/core.py's identical
    helper for the full rationale — duplicated here rather than imported
    across the module boundary."""
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


class Validator:
    def __init__(self, project):
        self.project = project

    def _block_ref(self, block) -> str:
        """feat/io-labels-and-ids §4.3/§3.3: every compiler/validator
        message identifies a block by its short_id — short, unique, and
        speakable over the phone, unlike the raw UUID or the possibly-
        shared display_name several untitled gates of the same type carry
        identically. For an I/O block with an assigned Address that also
        has a descriptive label (DeviceModel.get_io_label()), the address
        and label are appended in parens: "i3 (ELA01.DI01 — Wyłącznik Q1
        zamknięty)" — the single most useful extra context a message about
        an I/O block can carry."""
        from logic_studio.core.device_model import DeviceModel
        ref = getattr(block, 'short_id', '') or block.display_name  # defensive: a block never added to a project has no short_id yet
        properties = getattr(block, 'properties', None)
        addr = properties.get("Address", "") if isinstance(properties, dict) else ""
        if addr:
            label = DeviceModel.get_io_label(self.project, addr)
            if label:
                return f"{ref} ({addr} — {label})"
        return ref

    def run(self, errors: list, warnings: list):
        import math
        from logic_studio.core.device_model import DeviceModel

        blocks = self.project.blocks

        if not blocks:
            warnings.append("Project contains no logic blocks.")
            # Falls through to §5 below rather than returning — the
            # internal-signal registry (bad names, unused entries) is
            # worth validating independent of whether any block exists
            # yet, e.g. right after defining signals in Project Settings.

        for block in blocks:
            # 1. Ask block to self-validate
            block_errors = block.validate()
            for err in block_errors:
                errors.append(f"[{self._block_ref(block)}] {err}")

            # 2. Pin Level Validation
            # feat/editor-modes-and-geometry §2.4: a disabled ("zaślepione")
            # input is excluded from validation the same way it's excluded
            # from evaluate() (base.py's _active_inputs()) — no "unconnected"
            # warning for it. Instead: an active-input-count check runs once
            # per block below (only for block types that opt in at all —
            # multi-input logic gates), covering the "too few active inputs"
            # and "every input disabled" cases §2.4 requires.
            has_inputs = False
            active_input_count = 0
            for pin in block.inputs:
                has_inputs = True
                if pin.disabled:
                    if not getattr(block, 'allows_disabled_inputs', False):
                        # Defensive: this state should be unreachable through
                        # the UI (PortItem only offers the toggle when the
                        # block opted in) but a hand-edited/older file could
                        # still carry it — never silently accept it.
                        errors.append(
                            f"[{self._block_ref(block)}] Wejście '{pin.name}' jest zaślepione, "
                            "ale ten typ bloku nie zezwala na zaślepianie wejść."
                        )
                    continue
                active_input_count += 1
                if not pin.connections:
                    warnings.append(f"[{self._block_ref(block)}] Input '{pin.name}' is unconnected.")

            if has_inputs and getattr(block, 'allows_disabled_inputs', False):
                if active_input_count == 0:
                    errors.append(
                        f"[{self._block_ref(block)}] Wszystkie wejścia bloku są zaślepione — "
                        "blok nie ma żadnego aktywnego wejścia."
                    )
                elif active_input_count == 1:
                    warnings.append(
                        f"Bramka {self._block_ref(block)} ma tylko 1 aktywne wejście — "
                        "działa jak przekaźnik powtarzający."
                    )

            # fix/safety-block-semantics §6: a new category of rule, not the
            # same as "Input is unconnected" above — not every unconnected
            # OUTPUT is a problem (most are genuinely optional), but a pin
            # marked safety_relevant carries information about whether the
            # logic built on it can be trusted at all, so leaving it
            # unconnected means nothing downstream is even looking. Never
            # an error: an engineer may deliberately decide the quality
            # check isn't needed for a given signal.
            for pin in block.outputs:
                if pin.safety_relevant and not pin.connections:
                    warnings.append(
                        f"[{self._block_ref(block)}] Wyjście '{pin.name}' informujące o wiarygodności pomiaru "
                        "nie jest nigdzie użyte. Logika będzie działać bez kontroli jakości sygnału."
                    )

            # 3. Explicit IO Address Validation
            if block.type_id == "input.di":
                addr = block.properties.get("Address", "")
                if addr not in DeviceModel.get_ela_addresses(self.project):
                    errors.append(f"[{self._block_ref(block)}] Invalid DI Address: '{addr}'. Must be valid DI01 to DI32 on a defined ELA device.")
            elif block.type_id == "output.do":
                addr = block.properties.get("Address", "")
                if addr not in DeviceModel.get_ada_addresses(self.project):
                    errors.append(f"[{self._block_ref(block)}] Invalid DO Address: '{addr}'. Must be valid DO01 to DO32 on a defined ADA device.")
            elif block.type_id == "input.ai":
                # Analog points are project-defined, not fixed hardware channels
                # (AUDIT_REPORT.md §1) — the address must name a point with
                # direction="input" in project.settings["analog_points"].
                addr = block.properties.get("Address", "")
                if addr not in DeviceModel.get_analog_input_addresses(self.project):
                    errors.append(f"[{self._block_ref(block)}] Invalid AI Address: '{addr}'. Must match an analog point with direction=input.")
            elif block.type_id == "output.ao":
                addr = block.properties.get("Address", "")
                if addr not in DeviceModel.get_analog_output_addresses(self.project):
                    errors.append(f"[{self._block_ref(block)}] Invalid AO Address: '{addr}'. Must match an analog point with direction=output.")
            elif block.type_id == "system.signal":
                # §3.4 migration note: an old/unrecognized signal id is a
                # WARNING (the block runs safe — False/0.0 — not a hard
                # compile failure), so a project doesn't stop compiling the
                # moment the catalog gains/loses a signal.
                sig_id = block.properties.get("Sygnał", "")
                if sig_id:
                    from logic_studio.core import system_signals
                    if system_signals.get_signal(sig_id, self.project) is None:
                        warnings.append(f"[{self._block_ref(block)}] Nierozpoznany sygnał systemowy: '{sig_id}' (spoza katalogu).")
            elif block.type_id == "const.real":
                # feat/const-property-validation: ConstantBase.evaluate()
                # (blocks/constants.py) only catches ValueError around
                # float()/int() — a property holding None/a list/a dict
                # (possible from a hand-edited or corrupted .epwlogic file;
                # the property panel's own QDoubleSpinBox/QSpinBox can never
                # produce one) raises TypeError instead, uncaught, crashing
                # the engine mid-scan rather than falling back to the safe
                # default. Caught here as a compile ERROR instead — the same
                # "type checked live in the UI, but ALSO enforced at compile
                # time" belt-and-suspenders already applied to DI/DO/AI/AO
                # addresses above.
                raw = block.properties.get("Value", 0.0)
                try:
                    value = float(raw)
                except (TypeError, ValueError):
                    errors.append(f"[{self._block_ref(block)}] Wartość stałej REAL nie jest poprawną liczbą: {raw!r}.")
                else:
                    if not math.isfinite(value):
                        errors.append(f"[{self._block_ref(block)}] Wartość stałej REAL musi być liczbą skończoną (nie NaN/Inf): {raw!r}.")
            elif block.type_id == "const.int":
                raw = block.properties.get("Value", 0)
                try:
                    int(raw)
                except (TypeError, ValueError):
                    errors.append(f"[{self._block_ref(block)}] Wartość stałej INT nie jest poprawną liczbą całkowitą: {raw!r}.")
            elif block.type_id == "analog.quality":
                # §4.2: "Z punktu analogowego" only makes sense wired
                # directly to an input.ai block — that's the only place a
                # min/max range for this block to inherit even exists.
                if block.properties.get("Range Source", "Własny") == "Z punktu analogowego":
                    source = _direct_source_block(block, 0, blocks)
                    if source is None or source.type_id != "input.ai":
                        errors.append(
                            f"[{self._block_ref(block)}] Range Source = Z punktu analogowego wymaga, "
                            "by wejście In pochodziło bezpośrednio z bloku AI."
                        )
                # fix/safety-block-semantics §1.4: Stuck Tolerance=0 means
                # bit-exact equality, which a real measurement chain's own
                # ADC noise essentially never produces — the check would
                # compile clean and pass every unit test, then silently
                # never fire in the field. Warn, don't error: a purely
                # digital/simulated signal source genuinely IS bit-exact.
                stuck_scans = int(block.properties.get("Stuck Scans", 0) or 0)
                tolerance = float(block.properties.get("Stuck Tolerance", 0.0) or 0.0)
                if stuck_scans > 0 and tolerance == 0.0:
                    warnings.append(
                        f"[{self._block_ref(block)}] Detekcja zamrożenia sygnału z tolerancją 0 nie zadziała "
                        "na realnym torze pomiarowym (szum ostatniego bitu przetwornika). "
                        "Ustaw Stuck Tolerance."
                    )
                # §2.4: one-shot notice right after a v8->v9 schema
                # migration converted this block's old per-scan "Max Rate"
                # into the new per-second property. Lives in
                # simulation_state, same mechanism as _legacy_force_state
                # (core/project.py). NOTE: `block` here is an ISOLATED
                # CLONE (core/macros.py's expand_project() clones every
                # top-level block for compile-time isolation — see
                # base.py's clone()), so deleting the key HERE only clears
                # the clone's own copy; Compiler.compile() clears the same
                # key on the live project's own blocks right after this
                # runs, which is what actually makes it fire once.
                migration = block.simulation_state.get("_max_rate_migration_notice")
                if migration:
                    old_rate, new_rate = migration["old"], migration["new"]
                    warnings.append(
                        f"[{self._block_ref(block)}] Max Rate przeliczono przy migracji projektu: "
                        f"{old_rate:g}/skan -> {new_rate:g}/s (ta sama fizyczna szybkość zmiany, nowa jednostka)."
                    )
            elif block.type_id == "const.time":
                raw = block.properties.get("Time (ms)", 1000)
                try:
                    value = int(raw)
                except (TypeError, ValueError):
                    errors.append(f"[{self._block_ref(block)}] Czas stałej TIME nie jest poprawną liczbą całkowitą (ms): {raw!r}.")
                else:
                    if value < 0:
                        errors.append(f"[{self._block_ref(block)}] Czas stałej TIME nie może być ujemny: {value} ms.")

        # 4. Duplicate Output Detection
        output_addresses = {}
        analog_output_addresses = {}
        analog_input_addresses = {}
        for block in blocks:
            if block.type_id == "output.do":
                addr = block.properties.get("Address", "")
                if addr in output_addresses:
                    errors.append(f"Multiple outputs assigned to address: {addr} ({output_addresses[addr]} and {self._block_ref(block)})")
                else:
                    output_addresses[addr] = self._block_ref(block)
            elif block.type_id == "output.ao":
                addr = block.properties.get("Address", "")
                if addr in analog_output_addresses:
                    errors.append(f"Multiple analog outputs assigned to address: {addr} ({analog_output_addresses[addr]} and {self._block_ref(block)})")
                else:
                    analog_output_addresses[addr] = self._block_ref(block)
            elif block.type_id == "input.ai":
                # Several blocks reading the same analog measurement is legal
                # (e.g. one for logic, one for a display) — warn, don't fail.
                addr = block.properties.get("Address", "")
                if addr in analog_input_addresses:
                    warnings.append(f"Multiple AI blocks read address: {addr} ({analog_input_addresses[addr]} and {self._block_ref(block)})")
                else:
                    analog_input_addresses[addr] = self._block_ref(block)

        # 5. Internal signal registry (feat/internal-bits §4).
        from logic_studio.core.internal_bits import validate_internal_bits_registry, internal_bit_id
        errors.extend(validate_internal_bits_registry(self.project.settings.get("internal_bits", [])))

        BOOL_SIGNAL_TYPE_IDS = ("virtual.input", "virtual.output")
        REAL_SIGNAL_TYPE_IDS = ("internal.reg_in", "internal.reg_out")
        WRITER_TYPE_IDS = ("virtual.output", "internal.reg_out")

        writers = {}  # name.lower() -> [display_name, ...]
        readers = {}  # name.lower() -> [display_name, ...]
        referenced_lower_names = set()

        for block in blocks:
            if block.type_id not in BOOL_SIGNAL_TYPE_IDS and block.type_id not in REAL_SIGNAL_TYPE_IDS:
                continue
            name = block.properties.get("Bit", "")
            if not name:
                continue  # unconfigured — the "???" canvas warning already covers this

            entry = DeviceModel.get_internal_bit(self.project, name)
            # §4.4: signal not in the registry at all -> ERROR. Exactly the
            # point of replacing free-text "Tag" with a registry: a typo is
            # now a compile error instead of silently creating a new signal.
            if entry is None:
                errors.append(f"[{self._block_ref(block)}] Sygnał wewnętrzny '{name}' nie istnieje w rejestrze projektu (Ustawienia projektu -> Sygnały wewnętrzne).")
                continue

            # §4.5: a BOOL block (virtual.*) pointing at a REAL entry, or vice versa -> ERROR.
            expected_type = "REAL" if block.type_id in REAL_SIGNAL_TYPE_IDS else "BOOL"
            if entry.get("type") != expected_type:
                errors.append(f"[{self._block_ref(block)}] Sygnał '{name}' jest typu {entry.get('type')}, a ten blok wymaga {expected_type}.")
                continue

            lname = name.lower()
            referenced_lower_names.add(lname)
            if block.type_id in WRITER_TYPE_IDS:
                writers.setdefault(lname, []).append(self._block_ref(block))
            else:
                readers.setdefault(lname, []).append(self._block_ref(block))

        # §4.1: more than one writer for the same signal -> ERROR, exactly
        # like output.do above — must name every writing block.
        for entry in self.project.settings.get("internal_bits", []):
            lname = entry.get("name", "").lower()
            writer_names = writers.get(lname, [])
            if len(writer_names) > 1:
                errors.append(
                    f"Sygnał wewnętrzny '{internal_bit_id(entry)}' ma więcej niż jeden blok zapisujący: "
                    + ", ".join(writer_names) + "."
                )

        # §4.2: read but never written -> WARNING (can be legitimate while
        # a schematic is still being built).
        registry_by_lname = {e.get("name", "").lower(): e for e in self.project.settings.get("internal_bits", [])}
        for lname, reader_names in readers.items():
            if lname not in writers:
                entry = registry_by_lname.get(lname)
                sig_label = internal_bit_id(entry) if entry else lname
                warnings.append(f"Sygnał wewnętrzny '{sig_label}' odczytywany, ale niezapisywany przez żaden blok: " + ", ".join(reader_names) + ".")

        # §4.3: registered but unused by any block -> WARNING (housekeeping aid).
        for entry in self.project.settings.get("internal_bits", []):
            lname = entry.get("name", "").lower()
            if lname not in referenced_lower_names:
                warnings.append(f"Zdefiniowany sygnał wewnętrzny '{entry.get('name', '')}' nie jest używany przez żaden blok.")

        # 6. I/O label registry (feat/io-labels-and-ids §1.2): a label whose
        # address no longer names a real ELA/ADA channel or project analog
        # point -> WARNING, not an error — the address may simply have
        # disappeared after a reconfiguration (a deleted analog point, a
        # DeviceModel change), and the label itself is otherwise harmless.
        valid_addresses = set(DeviceModel.all_addresses(self.project))
        for address in DeviceModel.get_labelled_addresses(self.project):
            if address not in valid_addresses:
                warnings.append(
                    f"Etykieta zdefiniowana dla adresu '{address}', który nie istnieje w projekcie."
                )

        # 7. Macro parameters (fix/safety-and-macro-params §C4) — validated
        # against `self.project.settings["macro_definitions"]` (the
        # registry ITSELF, present here regardless of whether
        # expand_project() found any live instance to substitute onto for
        # THIS compile — same "validate the registry, not just what's
        # currently wired up" spirit as §5's internal-signal-registry
        # checks above), once per definition, independent of how many
        # instances (if any) exist right now. A "value out of range for
        # the bound property" rule (e.g. a negative TIME) needs no code
        # here at all: substitution (core/macros.py's own §C3.1, run
        # BEFORE this Validator ever sees the expanded graph) has already
        # overwritten the target block's property with the instance's own
        # value by the time this runs, so whatever range check that block
        # TYPE already has for that property (const.time's own "nie może
        # być ujemny", say) fires on the substituted value exactly as it
        # would on one typed in directly — no macro-aware duplicate rule
        # needed, or wanted, for that one bullet.
        from logic_studio.core import macros as macros_module
        macro_definitions = self.project.settings.get(macros_module.SETTINGS_KEY, {})
        for def_id, definition in macro_definitions.items():
            def_name = definition.get("name") or def_id
            ref = f"makroblok '{def_name}'"
            blocks_by_uuid = {b.get("uuid"): b for b in definition.get("blocks", [])}
            params_by_name = {p.get("name"): p for p in definition.get("parameters", [])}

            bound_param_names = set()
            property_targets = {}  # (block_uuid, property_name) -> [display_name, ...]

            for binding in definition.get("parameter_bindings", []):
                param_name = binding.get("parameter")
                block_uuid = binding.get("block_uuid")
                property_name = binding.get("property_name")
                param = params_by_name.get(param_name)

                if param is None:
                    errors.append(f"[{ref}] Powiązanie parametru wskazuje na nieistniejący parametr '{param_name}'.")
                    continue
                block_data = blocks_by_uuid.get(block_uuid)
                if block_data is None or property_name not in block_data.get("properties", {}):
                    errors.append(
                        f"[{ref}] Powiązanie parametru '{param.get('display_name', param_name)}' wskazuje na "
                        "nieistniejący blok wewnętrzny lub nieistniejącą właściwość."
                    )
                    continue

                bound_param_names.add(param_name)
                current_value = block_data["properties"][property_name]
                if not macros_module.value_matches_param_type(current_value, param.get("type", "STRING")):
                    errors.append(
                        f"[{ref}] Parametr '{param.get('display_name', param_name)}' (typ {param.get('type')}) "
                        f"nie zgadza się z typem właściwości '{property_name}'."
                    )
                property_targets.setdefault((block_uuid, property_name), []).append(param.get("display_name", param_name))

            # §C4: defined but never bound to anything -> WARNING (an
            # engineer may still be wiring up a brand-new macro).
            for param in definition.get("parameters", []):
                if param.get("name") not in bound_param_names:
                    warnings.append(
                        f"[{ref}] Parametr '{param.get('display_name', param.get('name'))}' "
                        "nie jest powiązany z żadną właściwością."
                    )

            # §C4: two parameters aimed at the same (block, property) ->
            # WARNING, not an error — legal but misleading (whichever
            # binding core/macros.py's own substitution loop iterates last
            # silently wins).
            for (block_uuid, property_name), names in property_targets.items():
                if len(names) > 1:
                    warnings.append(
                        f"[{ref}] Więcej niż jeden parametr powiązany z tą samą właściwością "
                        f"'{property_name}': {', '.join(names)} — wygrywa ostatnie podstawienie."
                    )

        # feat/wire-labels §2.5: a free end with no label is a normal
        # PENDING state while a wire is being drawn or a label is about
        # to be typed in — a warning, not an error, naming whichever
        # block the wire is still actually attached to. fix/wire-labels-
        # and-project-integrity §A2 (confirmed, not a leftover): kept
        # exactly as a warning even now that labels merge nodes
        # (compiler/label_merge.py) — a free-end wire with no label
        # carries no signal and breaks nothing else either; it's an
        # UNFINISHED DRAWING, not faulty logic, so it stays a warning,
        # never an error, regardless of how far label-merging itself
        # grows. An unlabeled free end names no node to validate yet, so
        # there is nothing for label_merge.py to check here; this is the
        # only free-end/label check that stays independent of it. Every
        # STRONGER check (a labeled node with no source, more than one,
        # or no receiver) now lives in compiler/label_merge.py instead,
        # run right after this stage in compiler/core.py. A label of
        # only whitespace counts as no label at all here — same
        # reasoning group_labeled_pins() already applies via its own
        # .strip() before grouping.
        for wire in getattr(self.project, 'wires', []):
            if (wire.label or "").strip() or not wire.has_free_end():
                continue
            attached_pin = wire.source_pin if wire.source_pin is not None else wire.dest_pin
            attached_block = _block_owning_pin(attached_pin, blocks) if attached_pin else None
            ref = self._block_ref(attached_block) if attached_block else "?"
            warnings.append(f"[{ref}] Niedokończony przewód (wolny koniec bez etykiety).")
