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
# deterministic grid intersection in scene coordinates. Two tiers:
#   - GRID_SIZE (20) is the coarse BLOCK-placement grid — block origins snap
#     to it (drag-and-drop, snap-on-move), and it's the background's major
#     grid line spacing.
#   - PORT_PITCH (10, a divisor of GRID_SIZE) is the finer PIN-spacing
#     sub-grid — the distance between consecutive ports within a multi-pin
#     block. A grid-aligned block origin combined with PORT_MARGIN/PORT_PITCH
#     both being GRID_SIZE divisors is still enough to put every port on a
#     deterministic grid line in scene coordinates — just the finer one.
# PORT_PITCH used to equal GRID_SIZE (both 20): a 4-input gate's height then
# grew by a full 20px per extra input, needlessly tall relative to its fixed
# width and — combined with the D-shape's curve, whose vertical extent
# follows the body's height — visibly flattening the curve for anything past
# 2 inputs ("bramki są spłaszczone... zagęścisz siatkę... rozmieścić
# przyłącza symetrycznie"). PORT_MARGIN stays at GRID_SIZE (the outer margin
# before the first/after the last port doesn't need to shrink, only the
# spacing between consecutive pins does).
PORT_PITCH = 10
PORT_MARGIN = GRID_SIZE

DOC_NOTE_RESIZE_HANDLE = 10

# Wire selection uses a different accent (cyan) than block selection (blue) —
# kept as its own constant rather than unified, to not change either's
# existing on-screen appearance while still centralizing the value.
COLOR_GRID = QColor(200, 200, 200)
COLOR_GRID_MINOR = QColor(228, 228, 228)  # fainter PORT_PITCH sub-grid, drawn
                                            # between the major GRID_SIZE dots
                                            # so the finer pin-pitch grid is
                                            # visible on the canvas too
COLOR_WIRE_SELECTED = QColor(0, 255, 255)
