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
