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
PIN_LABEL_GAP = 5            # space between a port square and its pin-name
                              # label (§0.2 audit follow-up — was a bare `2`
                              # inline in port_item.py)
PIN_LABEL_SIDE_FRACTION = 0.45  # max width of a pin label, as a fraction of
                              # the block's own width — leaves a 10% no-
                              # man's-land in the middle so a long input
                              # label and a long output label can never grow
                              # to meet (§0.2)
BLOCK_SELECTION_MARGIN = 4   # dashed selection rect padding beyond the body
BOUNDING_RECT_MARGIN = 15    # default margin for BlockItem.boundingRect()
XOR_ACCENT_OFFSET = 6        # gap between the XOR/XNOR extra curve and the shield

GRID_LINE_WIDTH = 1
WIRE_THICKNESS = 2

# Port/body geometry (feat/editor-modes-and-geometry §1 — supersedes the
# earlier "denser pin-pitch grid" fix from feat/block-rendering-library,
# which made multi-input gates less flattened but never fully square: a
# 4-input gate was still 40x80, its D-shape curve stretched over that full
# 80px height. This redesign fixes the ROOT cause instead: the gate BODY is
# now a fixed GATE_BODY x GATE_BODY square, period, regardless of input
# count — the D-shape/shield curve is therefore always drawn at the exact
# same proportions. Inputs beyond what fits inside that fixed body spread
# out symmetrically above/below it and are collected by a vertical "rail"
# entering the body's own left edge (§1.3) — the standard multi-input-gate
# convention in protection/relay schematics (e²TANGO-Studio among them).
#
# Two independent constants now, not one two-tier system:
#   - GRID_SNAP (10) is the block-PLACEMENT grid — block origins snap to it
#     (drag-and-drop, snap-on-move), and it's the finer of the two
#     background dot spacings (GRID_MINOR below).
#   - PORT_PITCH (20) is the spacing between a gate's/COMPLEX block's own
#     consecutive ports, and GATE_BODY (40) is the gate body's fixed size —
#     both independent of GRID_SNAP; a port position is `PORT_PITCH * k`
#     from the block's own center, and since PORT_PITCH is a GRID_SNAP
#     multiple, every port still lands on the placement grid in scene
#     coordinates once a grid-aligned block origin is added — same
#     invariant as before, just no longer requiring the same NUMBER for
#     both purposes.
GATE_BODY = 40    # gate body, always GATE_BODY x GATE_BODY — see above
PORT_PITCH = 20   # spacing between a block's own consecutive ports
GRID_SNAP = GRID_SIZE   # block placement / port-grid alignment unit (10)
GRID_MINOR = GRID_SNAP  # background dot grid — fine dots, same unit ports align to
GRID_MAJOR = 2 * GRID_SNAP  # background dot grid — a stronger dot every other fine one

DOC_NOTE_RESIZE_HANDLE = 10

# Wire selection uses a different accent (cyan) than block selection (blue) —
# kept as its own constant rather than unified, to not change either's
# existing on-screen appearance while still centralizing the value.
COLOR_GRID = QColor(160, 160, 160)         # GRID_MAJOR dots — stronger
COLOR_GRID_MINOR = QColor(220, 220, 220)   # GRID_MINOR dots — fainter, drawn
                                            # between the major ones
COLOR_WIRE_SELECTED = QColor(0, 255, 255)
