"""test/panel-width-guard -- single declared source of truth for the pixel
widths MainWindow._setup_layout() hands to horizontal_splitter.setSizes(),
and for which widget occupies each of those panes.

Why this exists: three separate times now, a dockable panel's own minimum
content width has quietly grown past the width the window actually allots
it -- Sygnały (5 mutually-exclusive filter buttons in one un-wrapped row,
830px minimum vs. a 300px-wide left dock; see the closed/superseded
fix/signals-panel-narrow-filter and its replacement, the tree-based
rebuild in feat/signals-panel-tree), Symulacja (channel-table columns
wider than the panel), and Biblioteka (the element-preview table forcing
width onto the same splitter as the library tree). Same bug shape, three
different panels, three unrelated root causes -- see
tests/test_panel_width_guard.py, which guards all of them (and any future
one) from ONE parametrized test driven by PANEL_DOCK_TARGETS below.

Both MainWindow and that test import LEFT/CENTER/RIGHT_PANEL_DOCK_WIDTH
and PANEL_DOCK_TARGETS from here -- neither keeps its own copy that could
silently drift out of sync with the other.
"""

# The 3 widths handed to horizontal_splitter.setSizes() at startup --
# Left(15%) / Center(70%) / Right(15%) of the 1920px reference layout.
LEFT_PANEL_DOCK_WIDTH = 300
CENTER_PANEL_DOCK_WIDTH = 1320
RIGHT_PANEL_DOCK_WIDTH = 300

# (display name, MainWindow attribute holding the widget actually placed
# in that pane/tab, target dock width). "Attribute holding the widget
# actually placed" matters for Library specifically: self.library_panel
# alone would miss the element-preview table stacked below it in the
# same vertical splitter (self.library_splitter) -- exactly the widget
# whose own width contribution was the historical bug.
#
# To add a new dockable panel: add it to MainWindow's layout as usual,
# store the widget actually placed in its pane as a `self.` attribute,
# and add one line here. tests/test_panel_width_guard.py needs no
# changes -- it's parametrized directly over this list.
PANEL_DOCK_TARGETS = [
    ("Library", "library_splitter", LEFT_PANEL_DOCK_WIDTH),
    ("Device Explorer", "device_panel", LEFT_PANEL_DOCK_WIDTH),
    ("Sygnały", "signals_panel", LEFT_PANEL_DOCK_WIDTH),
    ("Etykiety", "labels_panel", LEFT_PANEL_DOCK_WIDTH),
    ("Właściwości", "property_panel", RIGHT_PANEL_DOCK_WIDTH),
    ("Symulacja", "simulation_panel", RIGHT_PANEL_DOCK_WIDTH),
    ("Obserwowane", "watch_panel", CENTER_PANEL_DOCK_WIDTH),
    ("Konsola", "output_panel", CENTER_PANEL_DOCK_WIDTH),
]
