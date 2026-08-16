from PySide6.QtCore import QTimer, QObject, Signal

class ExecutionEngine(QObject):
    """
    Simulates the PLC execution cycle:
    1. Read inputs (ELA)
    2. Evaluate topological graph
    3. Write outputs (ADA)
    """

    # Signal emitted after every successful cycle to update UI
    cycle_completed = Signal()

    def __init__(self, project, simulation_panel, execution_order):
        super().__init__()
        self.project = project
        self.simulation_panel = simulation_panel
        self.execution_order = execution_order # List of block UUIDs
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.interval_ms = 100 # 100ms cycle time

    def start(self):
        if not self.execution_order:
            print("Cannot start simulation without a valid compiled execution order.")
            return
        self.timer.start(self.interval_ms)

    def pause(self):
        self.timer.stop()

    def stop(self):
        self.timer.stop()
        # Reset state logic could go here

    def _tick(self):
        # Build lookup for fast access
        block_map = {b.uuid: b for b in self.project.blocks}

        # We process inputs/outputs via specialized blocks.
        # (ELA / ADA blocks will read/write to simulation_panel internally during evaluate)

        # 1. Read ELA inputs (These blocks are handled independently or evaluated first naturally
        # but to enforce strict propagation, we can pre-evaluate input blocks)
        for uuid in self.execution_order:
            b = block_map.get(uuid)
            if b and b.__class__.__name__ == "DigitalInputBlock":
                b.evaluate()

        # 2. Execute remaining logic graph in topological order
        for uuid in self.execution_order:
            if uuid in block_map:
                block = block_map[uuid]

                # Signal propagation: Copy output values from upstream connections to this block's inputs
                for pin in block.inputs:
                    for conn_uuid in pin.connections:
                        source_pin = self._find_pin_by_uuid(conn_uuid, block_map)
                        if source_pin:
                            pin.value = source_pin.value

                # Execute block specific logic (skip DI since they were pre-evaluated)
                if block.__class__.__name__ != "DigitalInputBlock":
                    block.evaluate()

        # 3. Output ADA states handled by update_simulation_panel in MainWindow
        self.cycle_completed.emit()

    def _find_pin_by_uuid(self, pin_uuid, block_map):
        # In a highly optimized engine, we'd cache pin lookup.
        for block in block_map.values():
            for p in block.outputs: # Only look at outputs since inputs receive from outputs
                if p.uuid == pin_uuid:
                    return p
        return None
