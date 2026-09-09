"""test/panel-width-guard — a single parametrized guard against the "this
panel's own minimum content width exceeds the width it's actually allotted"
bug class, which has now hit this app three times, in three different
panels, for three unrelated root causes:

  - Sygnały: 5 mutually-exclusive filter QPushButtons in one un-wrapped
    QHBoxLayout — the row's minimum width was the SUM of every button's
    minimum width (830px measured) vs. a 300px-wide left dock. Fixed by the
    tree-based rebuild (feat/signals-panel-tree); the branch that had
    fixed it directly (fix/signals-panel-narrow-filter) was closed as
    superseded once that tree rebuild was confirmed, by measurement, to
    have already fixed it as a side effect.
  - Symulacja: channel-table columns wider than the panel.
  - Biblioteka: the element-preview table forcing width onto the same
    vertical splitter as the library tree.

Same bug shape every time: a panel (or, for Library, the splitter pane it
shares with a sibling widget) whose Qt-computed minimumSizeHint().width()
is larger than the space MainWindow actually gives it. This test measures
that directly, for every dockable panel MainWindow has today, against the
SAME width numbers MainWindow itself builds its layout from
(ui/panel_layout.py — see that module's own docstring) — no hardcoded
pixel value here that could drift from the real layout, and no per-panel
test case to remember to add: a newly added dockable panel is covered the
moment it's registered in PANEL_DOCK_TARGETS, which MainWindow's own
_setup_layout() has to be touched to add anyway.
"""
import pytest

from logic_studio.blocks import register_builtin_blocks
from logic_studio.ui.main_window import MainWindow
from logic_studio.ui.panel_layout import PANEL_DOCK_TARGETS


@pytest.fixture
def main_window(qapp, qsettings, qt_cleanup):
    register_builtin_blocks()
    window = MainWindow(settings=qsettings)
    qt_cleanup(window)
    return window


@pytest.mark.parametrize(
    "display_name, attr_name, target_width", PANEL_DOCK_TARGETS,
    ids=[name for name, _attr, _width in PANEL_DOCK_TARGETS],
)
def test_panel_minimum_width_fits_its_dock(main_window, display_name, attr_name, target_width):
    panel = getattr(main_window, attr_name)
    actual = panel.minimumSizeHint().width()
    assert actual <= target_width, (
        f'"{display_name}" (MainWindow.{attr_name}): minimumSizeHint().width() '
        f"= {actual}px exceeds its {target_width}px dock width. This is the "
        f"same bug class as the Sygnały/Symulacja/Biblioteka cases documented "
        f"in this file's own module docstring — the panel's own content is "
        f"forcing a wider minimum than the space it's actually allotted."
    )


def test_every_registered_panel_attribute_actually_exists(main_window):
    """Guards PANEL_DOCK_TARGETS itself against a typo'd/renamed attribute
    silently turning into an AttributeError inside the parametrized test
    above rather than a clear failure naming which entry is broken."""
    for display_name, attr_name, _width in PANEL_DOCK_TARGETS:
        assert hasattr(main_window, attr_name), (
            f'PANEL_DOCK_TARGETS entry "{display_name}" points at '
            f"MainWindow.{attr_name}, which doesn't exist."
        )
