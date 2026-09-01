"""Single source of truth for every visual constant used on the FBD canvas
(block_item.py, port_item.py, wire_item.py, scene.py, icons.py). Not a theme
system yet — just a place to centralize values that used to be bare literals
scattered across those files, ready for a future theme switch to redefine
(AUDIT_REPORT.md / feat/block-rendering-library §7).
"""
from PySide6.QtGui import QColor

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

# ---- Metrics ---------------------------------------------------------------
BUBBLE_RADIUS = 4            # negation bubble on NOT/NAND/NOR/XNOR outputs
PORT_RADIUS = 3
PORT_CLICK_MARGIN = 4        # extra hit-test margin around a port square
BLOCK_SELECTION_MARGIN = 4   # dashed selection rect padding beyond the body
BOUNDING_RECT_MARGIN = 15    # default margin for BlockItem.boundingRect()
XOR_ACCENT_OFFSET = 6        # gap between the XOR/XNOR extra curve and the shield
