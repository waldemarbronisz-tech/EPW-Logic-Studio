"""Single source of truth for every visual constant used on the FBD canvas
(block_item.py, port_item.py, wire_item.py, scene.py, icons.py). Not a theme
system yet — just a place to centralize values that used to be bare literals
scattered across those files, ready for a future theme switch to redefine
(AUDIT_REPORT.md / feat/block-rendering-library §7).
"""
from PySide6.QtGui import QColor

from logic_studio.core.grid import GRID_SIZE

# ---- Fonts -------------------------------------------------------------
FONT_FAMILY = "Arial"

FONT_SIZE_PIN_LABEL = 8      # pin names, gate type name under/inside the body
FONT_SIZE_TAG = 9            # Tag, bold, above the block
FONT_SIZE_COMMENT = 7        # Comment, italic, below the Tag — secondary info,
                              # deliberately smaller than the 8pt label floor.

# ---- Colors --------------------------------------------------------------
COLOR_BACKGROUND = QColor(255, 255, 255)
COLOR_OUTLINE = QColor(0, 0, 0)
COLOR_SELECTION = QColor(0, 120, 215)

COLOR_LOGIC_HIGH = QColor(0, 170, 0)     # boolean 1 / live green
COLOR_LOGIC_LOW = QColor(0, 0, 0)        # boolean 0
COLOR_ANALOG_VALUE = QColor(0, 100, 180) # non-boolean live data on a wire/port

COLOR_WARNING = QColor(200, 120, 0)
COLOR_ERROR = QColor(220, 0, 0)

COLOR_TAG_TEXT = QColor(0, 0, 0)
COLOR_COMMENT_TEXT = QColor(90, 90, 90)
COLOR_TYPE_LABEL_TEXT = QColor(0, 100, 0)
COLOR_DOC_TEXT = QColor(60, 60, 60)
COLOR_DOC_NOTE_BACKGROUND = QColor(255, 255, 224)  # pale yellow "sticky note"
COLOR_DOC_NOTE_BORDER = QColor(210, 210, 160)

FONT_SIZE_DOC_SECTION = 14
FONT_SIZE_DOC_TEXT = 9
FONT_SIZE_DOC_NOTE = 8

# ---- Metrics ---------------------------------------------------------------
BUBBLE_RADIUS = 5            # negation bubble on NOT/NAND/NOR/XNOR outputs
BUBBLE_PORT_GAP = 3          # clear space between the bubble's right edge and
                              # the output port square — previously 0, so the
                              # (opaque) port square painted right over half
                              # the bubble, making NAND/NOR/XNOR/NOT's
                              # negation hard to see at all
PORT_RADIUS = 3
GATE_LEAD = 8                # visible connection "lead" between a gate's port
                              # square and its body — every input, and a
                              # non-negated output, is pulled back from the
                              # port by this much and joined to it with a
                              # drawn line, instead of the body touching the
                              # port square directly (reference: distinct
                              # short lead wires on every pin, IEC/ANSI-style)
PORT_CLICK_MARGIN = 4        # extra hit-test margin around a port square
BLOCK_SELECTION_MARGIN = 4   # dashed selection rect padding beyond the body
BOUNDING_RECT_MARGIN = 15    # default margin for BlockItem.boundingRect()
XOR_ACCENT_OFFSET = 6        # gap between the XOR/XNOR extra curve and the shield

GRID_LINE_WIDTH = 1
WIRE_THICKNESS = 2

# Port geometry (feat/block-rendering-library §4 — "the most important
# section of this PR"): every port, on every block type, must land on a
# grid intersection in scene coordinates. PORT_MARGIN is the offset of the
# first port from the block's top/left edge; PORT_PITCH is the spacing
# between consecutive ports. Both are GRID_SIZE so a block's own origin
# being grid-aligned (enforced by snap-on-drop and snap-on-move) is
# sufficient to put every port on the grid too.
PORT_PITCH = 20
PORT_MARGIN = 20

DOC_NOTE_RESIZE_HANDLE = 10

# Wire selection uses a different accent (cyan) than block selection (blue) —
# kept as its own constant rather than unified, to not change either's
# existing on-screen appearance while still centralizing the value.
COLOR_GRID = QColor(200, 200, 200)
COLOR_WIRE_SELECTED = QColor(0, 255, 255)
