class DeviceModel:
    """Centralized definition of EPW Controller IO topology."""
    ELA_CHANNELS = 32
    ADA_CHANNELS = 32

    @classmethod
    def get_ela_addresses(cls):
        """Returns zero-padded ELA inputs."""
        return [f"DI{i:02d}" for i in range(1, cls.ELA_CHANNELS + 1)]

    @classmethod
    def get_ada_addresses(cls):
        """Returns zero-padded ADA outputs."""
        return [f"DO{i:02d}" for i in range(1, cls.ADA_CHANNELS + 1)]
