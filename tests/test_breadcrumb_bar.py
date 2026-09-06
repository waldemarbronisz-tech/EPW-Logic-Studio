"""feat/macro-blocks — ui/panels/breadcrumb.py's BreadcrumbBar. Qt-thin:
knows nothing about Project/macros, just renders a path and reports
clicks — see test_macro_navigation.py for the end-to-end MainWindow
wiring built on top of this."""
import pytest
from PySide6.QtWidgets import QApplication, QPushButton, QLabel

from logic_studio.ui.panels.breadcrumb import BreadcrumbBar


def _app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _crumb_buttons(bar):
    """Every clickable crumb button EXCLUDING the permanent "Piny
    makrobloku..." button — the two are tested separately below."""
    return [w for w in bar.findChildren(QPushButton) if w is not bar._pins_button]

def _labels(bar):
    return [w for w in bar.findChildren(QLabel)]


def test_hidden_at_construction():
    _app()
    bar = BreadcrumbBar()
    assert bar.isVisible() is False

def test_hidden_for_a_single_entry_path():
    _app()
    bar = BreadcrumbBar()
    bar.set_path(["Główny"])
    assert bar.isVisible() is False

def test_visible_for_a_multi_entry_path():
    _app()
    bar = BreadcrumbBar()
    bar.set_path(["Główny", "MojMakro"])
    assert bar.isVisible() is True

def test_every_entry_but_the_last_is_a_clickable_button():
    _app()
    bar = BreadcrumbBar()
    bar.set_path(["Główny", "A", "B"])
    buttons = _crumb_buttons(bar)
    assert [b.text() for b in buttons] == ["Główny", "A"]

def test_last_entry_is_a_bold_non_clickable_label():
    _app()
    bar = BreadcrumbBar()
    bar.set_path(["Główny", "A", "B"])
    labels = [l for l in _labels(bar) if l.text() == "B"]
    assert len(labels) == 1
    assert "bold" in labels[0].styleSheet()

def test_clicking_an_earlier_crumb_emits_its_index():
    _app()
    bar = BreadcrumbBar()
    bar.set_path(["Główny", "A", "B"])
    received = []
    bar.navigate_to.connect(received.append)

    buttons = _crumb_buttons(bar)
    buttons[0].click()  # "Główny"
    assert received == [0]

    received.clear()
    buttons[1].click()  # "A"
    assert received == [1]

def test_set_path_replaces_the_previous_path():
    _app()
    bar = BreadcrumbBar()
    bar.set_path(["Główny", "A", "B"])
    bar.set_path(["Główny", "X"])
    assert [b.text() for b in _crumb_buttons(bar)] == ["Główny"]
    assert bar.isVisible() is True

def test_set_path_back_to_a_single_entry_hides_again():
    _app()
    bar = BreadcrumbBar()
    bar.set_path(["Główny", "A"])
    bar.set_path(["Główny"])
    assert bar.isVisible() is False
    assert _crumb_buttons(bar) == []


# ---- "Piny makrobloku..." button (feat/macro-editable-pins) --------------

def test_pins_button_always_present_and_survives_set_path():
    _app()
    bar = BreadcrumbBar()
    assert bar._pins_button.text() == "Piny makrobloku..."
    bar.set_path(["Główny", "A", "B"])
    assert bar._pins_button.text() == "Piny makrobloku..."
    bar.set_path(["Główny"])
    assert bar._pins_button.text() == "Piny makrobloku..."

def test_pins_button_click_emits_manage_pins_requested():
    _app()
    bar = BreadcrumbBar()
    received = []
    bar.manage_pins_requested.connect(lambda: received.append(True))
    bar._pins_button.click()
    assert received == [True]

def test_pins_button_survives_several_set_path_calls_in_a_row():
    """Regression: set_path()'s own clearing loop used to assume exactly
    ONE permanent trailing anchor (just the stretch); adding a second
    (the pins button) without adjusting that loop deleted the button
    outright on the very first call."""
    _app()
    bar = BreadcrumbBar()
    bar.set_path(["Główny", "A"])
    bar.set_path(["Główny", "A", "B"])
    bar.set_path(["Główny", "X"])
    assert bar._pins_button in bar.findChildren(QPushButton)
    assert bar._pins_button.text() == "Piny makrobloku..."
    # and the crumb rebuild itself still works correctly alongside it
    assert [b.text() for b in _crumb_buttons(bar)] == ["Główny"]
