"""feat/macro-editable-pins — ui/macro_pins_dialog.py's MacroPinsDialog.
Qt-thin: never touches core/macros.py itself, just renders whatever
definition it's given and delegates every actual removal to the
`on_remove` callback — see test_macro_pin_editing.py for the end-to-end
MainWindow wiring built on top of this."""
import pytest
from PySide6.QtWidgets import QApplication

from logic_studio.blocks.pin import Pin
from logic_studio.ui.macro_pins_dialog import MacroPinsDialog


def _app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _definition():
    return {
        "name": "MojMakro",
        "blocks": [],
        "input_pins": [
            {"block_uuid": "b1", "pin_name": "In1", "data_type": Pin.TYPE_BOOLEAN, "label": "In1"},
            {"block_uuid": "b1", "pin_name": "In2", "data_type": Pin.TYPE_BOOLEAN, "label": "In2"},
        ],
        "output_pins": [
            {"block_uuid": "b1", "pin_name": "Out", "data_type": Pin.TYPE_BOOLEAN, "label": "Out"},
        ],
    }


def test_lists_are_populated_from_the_definition():
    _app()
    dialog = MacroPinsDialog(_definition(), on_remove=lambda d, i: None)
    assert [dialog.input_list.item(i).text() for i in range(dialog.input_list.count())] == ["In1", "In2"]
    assert [dialog.output_list.item(i).text() for i in range(dialog.output_list.count())] == ["Out"]

def test_remove_selected_input_calls_on_remove_with_direction_and_index():
    _app()
    received = []
    def on_remove(direction, index):
        received.append((direction, index))
        return None
    dialog = MacroPinsDialog(_definition(), on_remove=on_remove)
    dialog.input_list.setCurrentRow(1)  # "In2"

    dialog._remove_selected(dialog.input_list, Pin.DIR_INPUT)

    assert received == [(Pin.DIR_INPUT, 1)]

def test_remove_selected_output_calls_on_remove():
    _app()
    received = []
    dialog = MacroPinsDialog(_definition(), on_remove=lambda d, i: received.append((d, i)))
    dialog.output_list.setCurrentRow(0)

    dialog._remove_selected(dialog.output_list, Pin.DIR_OUTPUT)

    assert received == [(Pin.DIR_OUTPUT, 0)]

def test_remove_with_nothing_selected_is_a_no_op():
    _app()
    received = []
    dialog = MacroPinsDialog(_definition(), on_remove=lambda d, i: received.append((d, i)))
    dialog.input_list.setCurrentRow(-1)

    dialog._remove_selected(dialog.input_list, Pin.DIR_INPUT)

    assert received == []

def test_successful_removal_refreshes_the_lists():
    _app()
    definition = _definition()

    def on_remove(direction, index):
        # simulate a real removal: pop the entry and hand back the updated definition
        key = "input_pins" if direction == Pin.DIR_INPUT else "output_pins"
        definition[key].pop(index)
        return definition

    dialog = MacroPinsDialog(definition, on_remove=on_remove)
    dialog.input_list.setCurrentRow(0)  # "In1"

    dialog._remove_selected(dialog.input_list, Pin.DIR_INPUT)

    assert [dialog.input_list.item(i).text() for i in range(dialog.input_list.count())] == ["In2"]

def test_failed_removal_leaves_the_lists_untouched():
    _app()
    dialog = MacroPinsDialog(_definition(), on_remove=lambda d, i: None)  # simulates a stale/failed removal
    dialog.input_list.setCurrentRow(0)

    dialog._remove_selected(dialog.input_list, Pin.DIR_INPUT)

    assert [dialog.input_list.item(i).text() for i in range(dialog.input_list.count())] == ["In1", "In2"]

def test_refresh_reflects_a_definition_with_no_boundary_pins_at_all():
    _app()
    dialog = MacroPinsDialog(_definition(), on_remove=lambda d, i: None)
    dialog.refresh({"name": "X", "blocks": [], "input_pins": [], "output_pins": []})
    assert dialog.input_list.count() == 0
    assert dialog.output_list.count() == 0
