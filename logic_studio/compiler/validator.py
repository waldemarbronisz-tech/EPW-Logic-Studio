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

            # 3. Explicit IO Address Validation
            if block.type_id == "input.di":
                addr = block.properties.get("Address", "")
                if addr not in DeviceModel.get_ela_addresses():
                    errors.append(f"[{self._block_ref(block)}] Invalid DI Address: '{addr}'. Must be valid DI01 to DI32.")
            elif block.type_id == "output.do":
                addr = block.properties.get("Address", "")
                if addr not in DeviceModel.get_ada_addresses():
                    errors.append(f"[{self._block_ref(block)}] Invalid DO Address: '{addr}'. Must be valid DO01 to DO32.")
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
                    if system_signals.get_signal(sig_id) is None:
                        warnings.append(f"[{self._block_ref(block)}] Nierozpoznany sygnał systemowy: '{sig_id}' (spoza katalogu).")

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
