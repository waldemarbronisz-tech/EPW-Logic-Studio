import json
import os

os.makedirs("examples", exist_ok=True)

# Generate Logic Digital Test
with open("examples/LOGIC_DIGITAL_TEST.epwlogic", "w") as f:
    json.dump({
        "version": "1.0",
        "blocks": [
            {"id": "b1", "type_id": "logic.and4", "x": 100, "y": 100, "properties": {}, "connections": []},
            {"id": "b2", "type_id": "logic.or3", "x": 100, "y": 300, "properties": {}, "connections": []}
        ]
    }, f)

# Generate Logic Edge Test
with open("examples/LOGIC_EDGE_TEST.epwlogic", "w") as f:
    json.dump({
        "version": "1.0",
        "blocks": [
            {"id": "b1", "type_id": "edge.rtrig", "x": 100, "y": 100, "properties": {}, "connections": []}
        ]
    }, f)

# Generate Logic Analog Test
with open("examples/LOGIC_ANALOG_TEST.epwlogic", "w") as f:
    json.dump({
        "version": "1.0",
        "blocks": [
            {"id": "b1", "type_id": "analog.scale", "x": 100, "y": 100, "properties": {}, "connections": []}
        ]
    }, f)

# Generate Logic Timer Test
with open("examples/LOGIC_TIMER_TEST.epwlogic", "w") as f:
    json.dump({
        "version": "1.0",
        "blocks": [
            {"id": "b1", "type_id": "timer.ton", "x": 100, "y": 100, "properties": {}, "connections": []}
        ]
    }, f)

# Generate Logic System Test
with open("examples/LOGIC_SYSTEM_TEST.epwlogic", "w") as f:
    json.dump({
        "version": "1.0",
        "blocks": [
            {"id": "b1", "type_id": "system.button", "x": 100, "y": 100, "properties": {}, "connections": []},
            {"id": "b2", "type_id": "system.led", "x": 300, "y": 100, "properties": {}, "connections": []},
            {"id": "b3", "type_id": "system.message", "x": 100, "y": 300, "properties": {}, "connections": []},
            {"id": "b4", "type_id": "system.generator", "x": 300, "y": 300, "properties": {}, "connections": []}
        ]
    }, f)
