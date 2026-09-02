class DeviceModel:
    """Centralized definition of EPW Controller IO topology."""

    # In the future this should be dynamic configuration, but we provide standard defaults
    ELA_DEVICES = ["ELA01"]
    ADA_DEVICES = ["ADA01"]

    ELA_CHANNELS = 32
    ADA_CHANNELS = 32

    @classmethod
    def get_ela_addresses(cls):
        """Returns device-qualified zero-padded ELA inputs."""
        addrs = []
        for dev in cls.ELA_DEVICES:
            addrs.extend([f"{dev}.DI{i:02d}" for i in range(1, cls.ELA_CHANNELS + 1)])
        return addrs

    @classmethod
    def get_ada_addresses(cls):
        """Returns device-qualified zero-padded ADA outputs."""
        addrs = []
        for dev in cls.ADA_DEVICES:
            addrs.extend([f"{dev}.DO{i:02d}" for i in range(1, cls.ADA_CHANNELS + 1)])
        return addrs

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
        the 32 fixed ELA + 32 fixed ADA channels, plus every analog point
        the project currently defines."""
        return (
            cls.get_ela_addresses() + cls.get_ada_addresses()
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
