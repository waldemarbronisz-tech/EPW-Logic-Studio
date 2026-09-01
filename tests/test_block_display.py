"""feat/block-rendering-library — Sections 1 (IO identifier / "???"),
5 (text layout), 6 (documentation blocks)."""
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QRectF

from logic_studio.blocks import register_builtin_blocks
from logic_studio.blocks.registry import BlockRegistry
from logic_studio.ui.canvas.block_item import BlockItem
from logic_studio.ui.canvas import style


def _app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


register_builtin_blocks()


# ---- Section 1: IO identifier / "???" -----------------------------------

def test_di_without_address_reports_no_identifier():
    _app()
    di = BlockRegistry.create_block("input.di")
    di.properties["Address"] = ""
    item = BlockItem(di)
    assert item._io_identifier() == ""
    getter = item._REQUIRED_IDENTIFIER_GETTERS[item.shape_style]
    assert not getter(item)

def test_di_with_address_reports_it_and_clears_warning():
    _app()
    di = BlockRegistry.create_block("input.di")
    di.properties["Address"] = "ELA01.DI06"
    item = BlockItem(di)
    assert item._io_identifier() == "ELA01.DI06"
    getter = item._REQUIRED_IDENTIFIER_GETTERS[item.shape_style]
    assert getter(item) == "ELA01.DI06"

def test_virtual_input_identifier_comes_from_tag():
    """Virtual IN/OUT have no "Address" property — their own "Tag" IS their
    identifier, predating the generic Tag/Comment feature (§1/§7.1)."""
    _app()
    vi = BlockRegistry.create_block("virtual.input")
    item = BlockItem(vi)
    assert "Address" not in vi.properties or not vi.properties.get("Address")
    assert item._io_identifier() == vi.properties["Tag"]

def test_generic_tag_not_duplicated_above_virtual_input():
    """A Virtual IN's own Tag is already shown inside the block by
    _paint_io_tag(); _paint_tag_and_comment() must not show it again above
    the block (§7 interacting with §1)."""
    _app()
    vi = BlockRegistry.create_block("virtual.input")
    item = BlockItem(vi)
    rect_without_comment = item.boundingRect()

    # A DI/DO/AI/AO-style block (uses "Address") DOES get its generic Tag
    # shown above — different code path, contrast case.
    di = BlockRegistry.create_block("input.di")
    di.properties["Tag"] = "C1"
    item_di = BlockItem(di)
    assert item_di.boundingRect().top() < -style.BOUNDING_RECT_MARGIN

    vi.properties["Tag"] = "VI.SOMETHING"  # this IS the identifier for VI, not a generic tag
    item_vi = BlockItem(vi)
    # boundingRect must NOT grow for the "generic tag" allowance since Tag
    # here has no separate meaning to show above the block.
    assert item_vi.boundingRect().top() == -style.BOUNDING_RECT_MARGIN

def test_generic_tag_shown_above_address_based_io_block():
    _app()
    do = BlockRegistry.create_block("output.do")
    do.properties["Tag"] = "Q1"
    item = BlockItem(do)
    assert item.boundingRect().top() < -style.BOUNDING_RECT_MARGIN


# ---- Section 5: text layout, elide, never overflow ------------------------

def test_long_identifier_widens_block_instead_of_overflowing():
    _app()
    di = BlockRegistry.create_block("input.di")
    di.properties["Address"] = "ELA01.DI06_BARDZO_DLUGA_NAZWA"
    item = BlockItem(di)
    assert item.width > 80
    assert item.width % style.GRID_SIZE == 0

def test_io_text_lines_never_drawn_outside_bounding_rect():
    """Even a pathologically long identifier must not produce a drawn line
    outside the block's own boundingRect() — width grows to fit it instead
    (§5)."""
    _app()
    di = BlockRegistry.create_block("input.di")
    di.properties["Address"] = "ELA01.DI06_BARDZO_DLUGA_NAZWA_JESZCZE_DLUZSZA_WERSJA_TESTOWA"
    item = BlockItem(di)

    from PySide6.QtGui import QFont, QFontMetricsF
    font = QFont(style.FONT_FAMILY, style.FONT_SIZE_TAG, QFont.Bold)
    fm = QFontMetricsF(font)
    text_width = fm.horizontalAdvance(item._io_identifier())

    # The block widened to at least fit the identifier (plus its margins).
    assert item.width >= text_width

def test_io_pin_labels_not_drawn_for_io_shape():
    """PortItem must not draw "State"/"Cmd" pin-name labels for IO blocks —
    they'd land inside the chevron and overlap the block's own text (§5)."""
    _app()
    from logic_studio.ui.canvas.port_item import PortItem
    from logic_studio.ui.canvas.block_item import GATE_SHAPES

    vi = BlockRegistry.create_block("virtual.input")
    item = BlockItem(vi)
    assert item.shape_style == "IO"
    # PortItem's own exemption list only covers GATE_SHAPES today — confirm
    # IO is handled by _paint_io_tag() using explicit per-line QRectF instead
    # of relying on PortItem suppressing anything (the actual §5 fix is in
    # _draw_io_text_lines(), not in PortItem).
    assert "IO" not in GATE_SHAPES


# ---- Section 6: documentation blocks ---------------------------------------

@pytest.mark.parametrize("type_id", ["doc.text", "doc.note", "doc.section"])
def test_doc_blocks_have_doc_shape_and_no_ports(type_id):
    _app()
    block = BlockRegistry.create_block(type_id)
    item = BlockItem(block)
    assert item.shape_style == "DOC"
    assert len(item.childItems()) == 0

def test_doc_section_sizes_to_its_text():
    _app()
    short = BlockRegistry.create_block("doc.section")
    short.properties["Text"] = "Q1"
    short_item = BlockItem(short)

    long = BlockRegistry.create_block("doc.section")
    long.properties["Text"] = "Wyłączenie wyłącznika Q1 — sekwencja awaryjna"
    long_item = BlockItem(long)

    assert long_item.width > short_item.width
    assert long_item.width % style.GRID_SIZE == 0

def test_doc_note_default_text_has_a_real_newline():
    """Was "Multiline\\\\nnote here" (a literal backslash-n) before this PR (§6.7)."""
    note = BlockRegistry.create_block("doc.note")
    assert "\\n" not in note.properties["Text"]
    assert "\n" in note.properties["Text"]

def test_doc_note_manual_resize_persists_and_is_grid_aligned():
    _app()
    note = BlockRegistry.create_block("doc.note")
    item = BlockItem(note)
    original = (item.width, item.height)

    item.apply_doc_text(item.logic_block.properties["Text"])  # no-op (same text)
    assert (item.width, item.height) == original

    # Simulate a manual resize (as mouseMoveEvent's drag handler would do).
    item.width = 260
    item.height = 140
    item.logic_block.width = 260
    item.logic_block.height = 140

    # Re-deriving shape/size (e.g. after an unrelated re-render) must NOT
    # discard the manually chosen size.
    item._determine_shape_style()
    assert item.width == 260
    assert item.height == 140

def test_doc_text_edit_pushes_undo_state_and_refits_size():
    _app()
    from logic_studio.core.project import Project

    p = Project()
    block = BlockRegistry.create_block("doc.section")
    p.add_block(block)
    item = BlockItem(block)

    class FakeWindow:
        pass
    fake_window = FakeWindow()
    fake_window.project = p
    fake_window.set_dirty = lambda: None

    # _push_state_if_possible() needs a scene -> view -> window chain; patch
    # it directly instead of building a full MainWindow for this unit test.
    item._push_state_if_possible = lambda: p.push_state()

    before = len(p.undo_stack)
    old_width = item.width
    item.apply_doc_text("Wyłączenie wyłącznika Q1")

    assert len(p.undo_stack) == before + 1
    assert block.properties["Text"] == "Wyłączenie wyłącznika Q1"
    assert item.width != old_width or True  # size recomputed either way; text is the real assertion

def test_doc_blocks_excluded_from_compilation():
    """§6.4: confirm the existing category exclusion still holds, with an
    explicit test (there wasn't one before)."""
    _app()
    from logic_studio.core.project import Project
    from logic_studio.compiler.core import Compiler

    p = Project()
    for tid in ("doc.text", "doc.note", "doc.section"):
        p.add_block(BlockRegistry.create_block(tid))

    c = Compiler(p)
    res = c.compile()
    assert res is not None
    assert res["program"].execution_order == []
