def register_builtin_blocks():
    """Explicitly imports and registers all builtin blocks during startup."""
    import logic_studio.blocks.io_blocks
    import logic_studio.blocks.logic_gates
    import logic_studio.blocks.timers
    import logic_studio.blocks.counters
    import logic_studio.blocks.memory
    import logic_studio.blocks.math_blocks
    import logic_studio.blocks.comparators
    import logic_studio.blocks.virtual_io
    import logic_studio.blocks.system_signals
    import logic_studio.blocks.constants
    import logic_studio.blocks.edges
    import logic_studio.blocks.analog_processing
    import logic_studio.blocks.documentation
