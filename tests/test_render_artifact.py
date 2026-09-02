"""§0.6 audit follow-up: three of the six §0 bugs (input.ai's overlapping
ports, clipped pin labels, off-center gate outputs) sailed through 276
passing tests, because the existing suite checks NUMBERS derived from the
geometry — not the RELATIONSHIPS between rendered elements (do two things
overlap, does text fit, is something aligned with something else). A
numeric assertion can't see "this looks wrong" the way a human glancing at
a rendered gallery can.

This is not a regression test — it has no assertions on pixels. It's an
artifact: renders every registered block type to one PNG in a tmp_path and
prints the path, so a human (or a future audit) can open it and look, after
any PR that touches the canvas. Run it explicitly when that matters:

    QT_QPA_PLATFORM=offscreen python -m pytest tests/test_render_artifact.py -v -s
"""
from PySide6.QtWidgets import QApplication, QGraphicsScene
from PySide6.QtGui import QPainter, QImage
from PySide6.QtCore import QRectF, Qt

from logic_studio.blocks import register_builtin_blocks
from logic_studio.blocks.registry import BlockRegistry
from logic_studio.ui.canvas.block_item import BlockItem


def _app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


register_builtin_blocks()


def test_render_every_block_type_to_one_png(tmp_path):
    _app()

    type_ids = [
        type_id
        for category in BlockRegistry.get_categories()
        for type_id in BlockRegistry.get_blocks_in_category(category)
    ]
    assert len(type_ids) >= 60  # sanity: the registry actually populated

    scene = QGraphicsScene()
    scene.setSceneRect(-5000, -5000, 10000, 10000)

    cols = 6
    col_w, row_h = 220, 140
    for i, type_id in enumerate(sorted(type_ids)):
        block = BlockRegistry.create_block(type_id)
        # A representative non-empty identifier so IO/address text actually
        # renders instead of showing blank — same address the audit's own
        # analog.quality/ADA01.DO01 examples use where applicable.
        if "Address" in block.properties and not block.properties["Address"]:
            block.properties["Address"] = "TEST.01"
        item = BlockItem(block)
        col, row = i % cols, i // cols
        item.setPos(col * col_w + 40, row * row_h + 60)
        scene.addItem(item)

    rect = scene.itemsBoundingRect().adjusted(-20, -20, 20, 20)
    img = QImage(int(rect.width()), int(rect.height()), QImage.Format_ARGB32)
    img.fill(Qt.white)
    painter = QPainter(img)
    painter.setRenderHint(QPainter.Antialiasing)
    scene.render(painter, QRectF(0, 0, rect.width(), rect.height()), rect)
    painter.end()

    out_path = tmp_path / "block_gallery.png"
    img.save(str(out_path))
    assert out_path.exists()
    print(f"\nRendered {len(type_ids)} block types to: {out_path}")
