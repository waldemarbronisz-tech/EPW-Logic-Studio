def register_builtin_blocks():
    """Explicitly imports and registers all builtin blocks during startup."""
    import logic_studio.blocks.io_blocks
    import logic_studio.blocks.logic_gates
    import logic_studio.blocks.timers
    import logic_studio.blocks.counters
    import logic_studio.blocks.memory
    import logic_studio.blocks.math_blocks
    import logic_studio.blocks.comparators
