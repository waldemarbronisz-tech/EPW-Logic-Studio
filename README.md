# EPW Logic Studio

EPW Logic Studio is a classic-styled, node-based engineering environment for writing, compiling, and simulating PLC-like combinational and stateful logic.

## Architecture
- Object-Oriented Component library (Inputs, Outputs, Logic Gates, Timers, Memory, Math, Comparators).
- Python 3 / PySide6 User Interface modeled strictly after late 90's tools (e.g. Siemens STEP7, Windows 98 SE).
- Pluggable block `BlockRegistry`.
- Independent `ExecutionEngine` to simulate logic evaluation topologies cyclically.

## Requirements
- Python 3.10+
- PySide6
- (Optional) pytest for unit testing

## Installation & Windows Startup
Run `START_EPW_LOGIC.bat` to automatically instantiate a virtual environment, install requirements, and run the interface.

## Manual Startup
`pip install -r requirements.txt`
`python main.py`

## Features
- **Project Format**: Native `.epwlogic` JSON tracks schema logic and canvas layouts seamlessly via `type_id` mapping.
- **Compiler**: Verifies topological loops and pin validation.
- **Simulation**: Live ELA -> Evaluation -> ADA loop checking. Modifying live checkboxes in the UI instantly cascades logic states back through visual color-coded wiring.
- **Runtime Export**: Exports `*.epwlogic.runtime.json` devoid of UI fluff for future headless runtimes.

## Current Limitations
- Missing automated IEC 61131 text-parser representations.
- Hardware IO/Modbus binding is currently simulated.
