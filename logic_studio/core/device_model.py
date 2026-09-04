class DeviceModel:
    """Centralized definition of EPW Controller IO topology.

    feat/multi-device-io: the DEVICE LIST (how many ELA/ADA modules a
    project addresses) is project-defined — project.settings["ela_devices"]/
    ["ada_devices"], defaulting to the single-device ["ELA01"]/["ADA01"]
    every project used to be permanently fixed to (Project.__init__,
    core/project.py's v4->v5 migration). The CHANNEL COUNT per device
    (ELA_CHANNELS/ADA_CHANNELS) stays a fixed platform constant, not
    project-defined — every module of a given kind has the same number of
    channels; only how many modules exist varies.

    Every method below accepts an OPTIONAL `project` — omitted (or None),
    it falls back to the single-device default, so a call site that
    genuinely has no project handy (or hasn't been updated yet) degrades
    to exactly today's pre-multi-device behavior rather than raising."""

    ELA_CHANNELS = 32
    ADA_CHANNELS = 32

    _DEFAULT_ELA_DEVICES = ["ELA01"]
    _DEFAULT_ADA_DEVICES = ["ADA01"]

    @classmethod
    def get_ela_devices(cls, project=None) -> list:
        if project is None:
            return list(cls._DEFAULT_ELA_DEVICES)
        return list(project.settings.get("ela_devices", cls._DEFAULT_ELA_DEVICES))

    @classmethod
    def get_ada_devices(cls, project=None) -> list:
        if project is None:
            return list(cls._DEFAULT_ADA_DEVICES)
        return list(project.settings.get("ada_devices", cls._DEFAULT_ADA_DEVICES))

    @classmethod
    def get_ela_addresses(cls, project=None):
        """Returns device-qualified zero-padded ELA inputs, across EVERY
        ELA device the project defines."""
        addrs = []
        for dev in cls.get_ela_devices(project):
            addrs.extend([f"{dev}.DI{i:02d}" for i in range(1, cls.ELA_CHANNELS + 1)])
        return addrs

    @classmethod
    def get_ada_addresses(cls, project=None):
        """Returns device-qualified zero-padded ADA outputs, across EVERY
        ADA device the project defines."""
        addrs = []
        for dev in cls.get_ada_devices(project):
            addrs.extend([f"{dev}.DO{i:02d}" for i in range(1, cls.ADA_CHANNELS + 1)])
        return addrs

    _DEVICE_NAME_RE_CACHE = {}

    @classmethod
    def _device_name_pattern(cls, prefix: str):
        """"ELA" -> ^ELA\\d{2}$, "ADA" -> ^ADA\\d{2}$ — the naming
        convention every existing device name (and every reference to one
        elsewhere in the app: system_signals_catalog.json's "ELA01.ONLINE"
        etc., every doc/tooltip example) already assumes. Enforced on ADD
        (set_ela_devices/set_ada_devices below), not just documented, so a
        typo can't silently produce addresses like "ELA1.DI01" that would
        never match anything a block's Address combobox offers."""
        import re
        pattern = cls._DEVICE_NAME_RE_CACHE.get(prefix)
        if pattern is None:
            pattern = re.compile(rf"^{prefix}\d{{2}}$")
            cls._DEVICE_NAME_RE_CACHE[prefix] = pattern
        return pattern

    @classmethod
    def is_valid_device_name(cls, prefix: str, name: str) -> bool:
        return bool(cls._device_name_pattern(prefix).match(name or ""))

    @classmethod
    def set_ela_devices(cls, project, devices: list) -> list:
        """Validates (§ is_valid_device_name), de-duplicates (order-
        preserving) and stores `devices` as the project's ELA module list.
        Returns the list actually stored (empty/invalid entries dropped) —
        callers building an editor UI should re-read this back rather than
        assume every entry they passed survived."""
        return cls._set_devices(project, "ela_devices", "ELA", devices)

    @classmethod
    def set_ada_devices(cls, project, devices: list) -> list:
        return cls._set_devices(project, "ada_devices", "ADA", devices)

    @classmethod
    def _set_devices(cls, project, settings_key: str, prefix: str, devices: list) -> list:
        seen = set()
        clean = []
        for name in devices or []:
            name = (name or "").strip().upper()
            if name and cls.is_valid_device_name(prefix, name) and name not in seen:
                seen.add(name)
                clean.append(name)
        if not clean:
            clean = list(getattr(cls, f"_DEFAULT_{prefix}_DEVICES"))
        project.settings[settings_key] = clean
        return clean

    @classmethod
    def next_device_name(cls, prefix: str, existing: list) -> str:
        """The next unused "<prefix><NN>" name — "ELA03" after
        ["ELA01","ELA02"] — for an "Add device" button to prefill rather
        than making the user invent a name by hand."""
        used_numbers = set()
        pattern = cls._device_name_pattern(prefix)
        for name in existing:
            if pattern.match(name or ""):
                used_numbers.add(int(name[len(prefix):]))
        n = 1
        while n in used_numbers:
            n += 1
        return f"{prefix}{n:02d}"

    # ---- Analog points -------------------------------------------------------
    # Unlike DI/DO, analog points have no fixed hardware channel count — they
    # are entirely defined by the project (project.settings["analog_points"]),
    # so these operate on a `project`, not on class-level constants.

    @classmethod
    def get_analog_points(cls, project) -> list:
        return list(project.settings.get("analog_points", []))

    @classmethod
    def get_analog_input_addresses(cls, project) -> list:
        return [p["address"] for p in cls.get_analog_points(project) if p.get("direction") == "input"]

    @classmethod
    def get_analog_output_addresses(cls, project) -> list:
        return [p["address"] for p in cls.get_analog_points(project) if p.get("direction") == "output"]

    @classmethod
    def get_analog_point(cls, project, address):
        for p in cls.get_analog_points(project):
            if p.get("address") == address:
                return p
        return None

    # ---- I/O labels (feat/io-labels-and-ids §1) -------------------------------
    # Descriptive labels for physical (ELA/ADA) and analog addresses —
    # project.settings["io_labels"], address -> label. Reference: e²TANGO's
    # "Etykiety i LED" configuration category (DTR §2.7.7) — labels
    # assigned to addresses are used as fragments of event texts, as
    # descriptions in logic, and on state-overview screens, "available
    # throughout the program interchangeably with physical addresses".
    # Every reader goes through get_io_label()/get_labelled_addresses()
    # here, never project.settings["io_labels"] directly, so the storage
    # shape (currently a flat dict) can change without every call site
    # needing to know.

    MAX_IO_LABEL_LENGTH = 64

    @classmethod
    def get_io_label(cls, project, address: str) -> str:
        """The label assigned to `address`, or "" if none (project.settings
        never stores an empty-string entry — see set_io_label)."""
        return project.settings.get("io_labels", {}).get(address, "")

    @classmethod
    def set_io_label(cls, project, address: str, label: str):
        """§1.2: any text is accepted (Polish diacritics/spaces included —
        unlike an internal-signal name, a label is never used as an
        identifier), truncated to MAX_IO_LABEL_LENGTH rather than rejected.
        An empty (post-strip) label REMOVES the entry instead of storing
        "" — io_labels is meant to answer "does this address have a
        label"; a stored empty string would make every reader re-implement
        that emptiness check itself."""
        io_labels = project.settings.setdefault("io_labels", {})
        label = (label or "").strip()[:cls.MAX_IO_LABEL_LENGTH]
        if label:
            io_labels[address] = label
        else:
            io_labels.pop(address, None)

    @classmethod
    def get_labelled_addresses(cls, project) -> dict:
        """A copy of the full address -> label mapping (never the live
        dict — callers must go through set_io_label() to write)."""
        return dict(project.settings.get("io_labels", {}))

    @classmethod
    def all_addresses(cls, project) -> list:
        """Every address a label (or the §2 editor table) could apply to:
        every ELA/ADA channel across every device the project defines,
        plus every analog point the project currently defines."""
        return (
            cls.get_ela_addresses(project) + cls.get_ada_addresses(project)
            + cls.get_analog_input_addresses(project) + cls.get_analog_output_addresses(project)
        )

    # ---- Internal signal registry (feat/internal-bits §1.4) ------------------
    # Also entirely project-defined (project.settings["internal_bits"]) —
    # see core/internal_bits.py for the entry shape and internal_bit_id().

    @classmethod
    def get_internal_bits(cls, project, type_filter: str = None) -> list:
        entries = list(project.settings.get("internal_bits", []))
        if type_filter is not None:
            entries = [e for e in entries if e.get("type") == type_filter]
        return entries

    @classmethod
    def get_internal_bit(cls, project, name: str):
        for e in cls.get_internal_bits(project):
            if e.get("name", "").lower() == (name or "").lower():
                return e
        return None
