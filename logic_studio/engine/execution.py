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

        # Execute logic graph in topological order
        for uuid in self.execution_order:
            if uuid in block_map:
                block = block_map[uuid]

                # Signal propagation: Copy output values from upstream connections to this block's inputs
                for pin in block.inputs:
                    for conn_uuid in pin.connections:
                        # Find source pin
                        source_pin = self._find_pin_by_uuid(conn_uuid, block_map)
                        if source_pin:
                            pin.value = source_pin.value

                # Execute block specific logic
                block.evaluate()

        self.cycle_completed.emit()

    def _find_pin_by_uuid(self, pin_uuid, block_map):
        # In a highly optimized engine, we'd cache pin lookup.
        for block in block_map.values():
            for p in block.outputs: # Only look at outputs since inputs receive from outputs
                if p.uuid == pin_uuid:
                    return p
        return None
