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
