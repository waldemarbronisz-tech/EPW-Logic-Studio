"""feat/macro-editable-pins — end-to-end: adding/removing a macro's own
boundary pins from inside its breadcrumb edit view, and the resync onto
every placed instance. See test_macros.py for the underlying core/macros.py
logic (add_boundary_pin()/remove_boundary_pin()/resync_all_instances()) in
isolation, and test_macro_pins_dialog.py for MacroPinsDialog itself."""
import pytest
from PySide6.QtWidgets import QApplication, QMenu

from logic_studio.blocks import register_builtin_blocks
from logic_studio.blocks.pin import Pin
from logic_studio.blocks.macro_instance import MacroInstanceBlock
from logic_studio.ui.canvas.block_item import BlockItem
from logic_studio.core.macros import get_definition

register_builtin_blocks()


def _app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _close(window):
    window.is_dirty = False
    window.close()


def _block_items(window):
    return [i for i in window.scene.items() if isinstance(i, BlockItem)]


def _make_window_with_macro(qsettings):
    """A window with one AndGate collapsed into macro "MojMakro", wired
    between a DI and a DO — In1/In2/Out all exposed. Same fixture shape as
    test_macro_navigation.py's own (kept separate/local rather than
    imported, matching this suite's existing one-helper-per-file norm)."""
    from logic_studio.ui.main_window import MainWindow
    from logic_studio.blocks.io_blocks import DigitalInputBlock, DigitalOutputBlock

    window = MainWindow(settings=qsettings)
    window.scene.clear()
    window.scene.add_block_from_library("input.di", 0, 0)
    window.scene.add_block_from_library("logic.and", 200, 0)
    window.scene.add_block_from_library("output.do", 400, 0)
    di, gate, do = window.project.blocks
    di.outputs[0].connect(gate.inputs[0])
    gate.outputs[0].connect(do.inputs[0])
    for item in _block_items(window):
        if item.logic_block is gate:
            item.setSelected(True)
    window.scene.create_macro_from_selection("MojMakro")

    instance = next(b for b in window.project.blocks if isinstance(b, MacroInstanceBlock))
    return window, di, do, instance


def _block_item(window, logic_block):
    return next(i for i in _block_items(window) if i.logic_block is logic_block)


# ---- MainWindow.expose_macro_pin() ----------------------------------------

def test_expose_macro_pin_adds_a_new_boundary_pin_and_resyncs(qsettings):
    _app()
    window, di, do, instance = _make_window_with_macro(qsettings)
    def_id = instance.def_id

    window.enter_macro_instance(instance)
    window.scene.add_block_from_library("logic.not", 0, 200)
    not_gate = next(b for b in window.project.blocks if b.type_id == "logic.not")

    window.expose_macro_pin(not_gate.uuid, not_gate.inputs[0].name, Pin.DIR_INPUT)

    # the fixture's own AND gate only has "In1" exposed (In2 was never
    # externally connected at build time — build_definition() only
    # exposes a pin that was) — so this is the SECOND exposed input.
    definition = get_definition(window.project, def_id)
    assert len(definition["input_pins"]) == 2
    assert definition["input_pins"][1]["block_uuid"] == not_gate.uuid

    window._navigate_to_breadcrumb_index(0)
    assert len(instance.inputs) == 2
    assert instance.inputs[1].name == not_gate.inputs[0].name
    assert instance.inputs[1].connections == []
    _close(window)

def test_expose_macro_pin_is_a_no_op_outside_a_macro_edit_view(qsettings):
    _app()
    window, di, do, instance = _make_window_with_macro(qsettings)
    assert window.current_macro_def_id is None

    window.expose_macro_pin(di.uuid, di.outputs[0].name, Pin.DIR_OUTPUT)

    assert len(get_definition(window.project, instance.def_id)["output_pins"]) == 1  # unchanged
    _close(window)

def test_expose_macro_pin_marks_the_project_dirty(qsettings):
    _app()
    window, di, do, instance = _make_window_with_macro(qsettings)
    window.enter_macro_instance(instance)
    window.scene.add_block_from_library("logic.not", 0, 200)
    not_gate = next(b for b in window.project.blocks if b.type_id == "logic.not")
    window.is_dirty = False

    window.expose_macro_pin(not_gate.uuid, not_gate.inputs[0].name, Pin.DIR_INPUT)

    assert window.is_dirty is True
    _close(window)


# ---- MainWindow._remove_macro_pin() / _resync_macro_instances() ----------

def test_remove_macro_pin_returns_the_fresh_definition_and_resyncs(qsettings):
    _app()
    window, di, do, instance = _make_window_with_macro(qsettings)
    def_id = instance.def_id
    window.enter_macro_instance(instance)
    window.scene.add_block_from_library("logic.not", 0, 200)
    not_gate = next(b for b in window.project.blocks if b.type_id == "logic.not")
    window.expose_macro_pin(not_gate.uuid, not_gate.inputs[0].name, Pin.DIR_INPUT)  # 2nd input, so removing one leaves a survivor to check

    result = window._remove_macro_pin(Pin.DIR_INPUT, 1)  # removes the NOT gate's pin, not the fixture's own "In1"

    assert result is not None
    assert len(result["input_pins"]) == 1

    window._navigate_to_breadcrumb_index(0)
    assert len(instance.inputs) == 1
    assert instance.inputs[0].name == "In1"
    _close(window)

def test_remove_macro_pin_returns_none_outside_a_macro_edit_view(qsettings):
    _app()
    window, di, do, instance = _make_window_with_macro(qsettings)
    assert window.current_macro_def_id is None

    assert window._remove_macro_pin(Pin.DIR_INPUT, 0) is None
    _close(window)

def test_remove_macro_pin_disconnects_live_instance_wiring(qsettings):
    _app()
    window, di, do, instance = _make_window_with_macro(qsettings)
    def_id = instance.def_id
    # instance.inputs[0] ("In1") is wired to di — confirm before removing.
    assert di.outputs[0].uuid in instance.inputs[0].connections

    window.enter_macro_instance(instance)
    window._remove_macro_pin(Pin.DIR_INPUT, 0)  # removes the fixture's only exposed input, "In1"
    window._navigate_to_breadcrumb_index(0)

    assert len(instance.inputs) == 0
    assert di.outputs[0].connections == []
    _close(window)


# ---- BlockItem.populate_expose_pin_menu() ---------------------------------

def test_expose_pin_menu_lists_unexposed_pins_while_inside_a_macro(qsettings):
    _app()
    window, di, do, instance = _make_window_with_macro(qsettings)
    window.enter_macro_instance(instance)
    window.scene.add_block_from_library("logic.not", 0, 200)
    not_gate = next(b for b in window.project.blocks if b.type_id == "logic.not")
    item = _block_item(window, not_gate)

    menu = QMenu()
    submenu = item.populate_expose_pin_menu(menu)

    assert submenu is not None
    action_texts = [a.text() for a in submenu.actions()]
    assert any("In" in t for t in action_texts)
    assert any("Out" in t for t in action_texts)
    assert submenu.menuAction().isEnabled() is True
    _close(window)

def test_expose_pin_menu_excludes_already_exposed_pins(qsettings):
    """The fixture's own AND gate has "In1"/"Out" exposed but NOT "In2"
    (never externally connected at build time — build_definition() only
    exposes a pin that was) — the menu must offer In2, but never the two
    already-exposed pins."""
    _app()
    window, di, do, instance = _make_window_with_macro(qsettings)
    window.enter_macro_instance(instance)
    gate = window.project.blocks[0]
    item = _block_item(window, gate)

    menu = QMenu()
    submenu = item.populate_expose_pin_menu(menu)

    assert submenu is not None
    action_texts = [a.text() for a in submenu.actions()]
    assert action_texts == ["Wejście: In2"]
    assert submenu.menuAction().isEnabled() is True
    _close(window)

def test_expose_pin_menu_disabled_when_every_pin_is_already_exposed(qsettings):
    _app()
    window, di, do, instance = _make_window_with_macro(qsettings)
    window.enter_macro_instance(instance)
    gate = window.project.blocks[0]
    # expose the one remaining unexposed pin ("In2") so the block has
    # nothing left to offer.
    window.expose_macro_pin(gate.uuid, gate.inputs[1].name, Pin.DIR_INPUT)
    item = _block_item(window, gate)

    menu = QMenu()
    submenu = item.populate_expose_pin_menu(menu)

    assert submenu is not None
    assert submenu.actions() == []
    assert submenu.menuAction().isEnabled() is False
    _close(window)

def test_expose_pin_menu_absent_outside_a_macro_edit_view(qsettings):
    _app()
    window, di, do, instance = _make_window_with_macro(qsettings)
    assert window.current_macro_def_id is None
    item = _block_item(window, di)

    menu = QMenu()
    submenu = item.populate_expose_pin_menu(menu)

    assert submenu is None
    assert menu.actions() == []
    _close(window)

def test_expose_pin_menu_action_triggers_expose_macro_pin(qsettings):
    _app()
    window, di, do, instance = _make_window_with_macro(qsettings)
    def_id = instance.def_id
    window.enter_macro_instance(instance)
    window.scene.add_block_from_library("logic.not", 0, 200)
    not_gate = next(b for b in window.project.blocks if b.type_id == "logic.not")
    item = _block_item(window, not_gate)

    menu = QMenu()
    submenu = item.populate_expose_pin_menu(menu)
    input_action = next(a for a in submenu.actions() if "In" in a.text())
    input_action.trigger()

    definition = get_definition(window.project, def_id)
    assert len(definition["input_pins"]) == 2  # the fixture's own "In1" plus this new one
    _close(window)


# ---- MainWindow._open_macro_pins_dialog() ---------------------------------

def test_open_macro_pins_dialog_constructs_with_the_current_definition(qsettings, monkeypatch):
    _app()
    window, di, do, instance = _make_window_with_macro(qsettings)
    window.enter_macro_instance(instance)

    from logic_studio.ui.macro_pins_dialog import MacroPinsDialog
    captured = {}
    original_init = MacroPinsDialog.__init__

    def fake_init(self, definition, on_remove, parent=None, on_parameter_change=None):
        captured["definition"] = definition
        captured["on_remove"] = on_remove
        original_init(self, definition, on_remove, parent=parent, on_parameter_change=on_parameter_change)

    monkeypatch.setattr(MacroPinsDialog, "__init__", fake_init)
    monkeypatch.setattr(MacroPinsDialog, "exec", lambda self: None)

    window._open_macro_pins_dialog()

    assert captured["definition"]["name"] == "MojMakro"
    assert captured["on_remove"] == window._remove_macro_pin
    _close(window)

def test_open_macro_pins_dialog_is_a_no_op_outside_a_macro_edit_view(qsettings, monkeypatch):
    _app()
    window, di, do, instance = _make_window_with_macro(qsettings)
    assert window.current_macro_def_id is None

    from logic_studio.ui.macro_pins_dialog import MacroPinsDialog
    called = []
    monkeypatch.setattr(MacroPinsDialog, "exec", lambda self: called.append(True))

    window._open_macro_pins_dialog()

    assert called == []
    _close(window)

def test_breadcrumb_pins_button_opens_the_dialog(qsettings, monkeypatch):
    _app()
    window, di, do, instance = _make_window_with_macro(qsettings)
    window.enter_macro_instance(instance)

    from logic_studio.ui.macro_pins_dialog import MacroPinsDialog
    called = []
    monkeypatch.setattr(MacroPinsDialog, "exec", lambda self: called.append(True))

    window.breadcrumb_bar._pins_button.click()

    assert called == [True]
    _close(window)
