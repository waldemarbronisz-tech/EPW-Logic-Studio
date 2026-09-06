"""feat/pdf-export — rendering the current schematic (and, optionally,
its signal list) to a PDF file, for as-built documentation / client
sign-off. Genuinely Qt-dependent (QPainter/QPdfWriter/QGraphicsScene) —
lives under ui/ rather than core/, same reasoning ui/canvas/shapes.py
does; unlike most of this app's core/*.py modules, there's no meaningful
Qt-free version of "render a QGraphicsScene onto a page" to split out.

The signal-list TEXT content itself (what to print, not how to lay it
out on paper) is a plain, Qt-free function — signal_list_rows() — kept
separate so it's unit-testable without constructing a real QPdfWriter.
"""
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPageSize, QPageLayout, QPainter, QFont, QPdfWriter

from logic_studio.core.crossref import (
    KIND_PHYSICAL_DI, KIND_PHYSICAL_DO, KIND_ANALOG_IN, KIND_ANALOG_OUT,
    KIND_INTERNAL_BIT, KIND_INTERNAL_REG, KIND_SYSTEM,
)

# Deliberately a SEPARATE, small copy of ui/panels/signals.py's own
# private `_KIND_SHORT` rather than importing it — that name is
# underscore-prefixed there precisely because it's that panel's own
# internal detail, the same reasoning ui/icons.py's _shape_style_for()
# re-derives BlockItem's own shape logic instead of reaching into it.
_KIND_SHORT = {
    KIND_PHYSICAL_DI: "DI", KIND_PHYSICAL_DO: "DO",
    KIND_ANALOG_IN: "AI", KIND_ANALOG_OUT: "AO",
    KIND_INTERNAL_BIT: "BIT", KIND_INTERNAL_REG: "REG",
    KIND_SYSTEM: "SYS",
}

TITLE_BLOCK_HEIGHT = 300  # device pixels at the resolution export_schematic_to_pdf() sets
PAGE_MARGIN = 60


def signal_list_rows(crossref: dict) -> list:
    """Pure, Qt-free: `(signal_id, kind_label, data_type, label,
    writers_text, readers_text)` tuples, sorted by signal_id — the exact
    text content of the signal-list page(s), independent of how it ends
    up laid out on paper. `crossref` is core/crossref.py::build_crossref()'s
    own return value (`{signal_id: SignalUsage}`)."""
    rows = []
    for signal_id in sorted(crossref.keys()):
        usage = crossref[signal_id]
        writers_text = ", ".join(short_id for _uuid, short_id, _pin in usage.writers)
        readers_text = ", ".join(short_id for _uuid, short_id, _pin in usage.readers)
        rows.append((
            signal_id,
            _KIND_SHORT.get(usage.kind, usage.kind),
            usage.data_type,
            usage.label,
            writers_text,
            readers_text,
        ))
    return rows


def export_schematic_to_pdf(scene, project, path: str, include_signal_list: bool = True) -> None:
    """Renders `scene`'s current content (every placed block/wire) onto
    the first page of a landscape A4 PDF at `path`, scaled to fit with a
    title block naming the project and generation time — then, if
    `include_signal_list`, appends one or more further pages listing
    every signal used across the project (core/crossref.py::build_crossref(),
    the same data the Sygnały panel/its own CSV export already show),
    paginating automatically once a page fills up.

    Deselects everything on `scene` first — a selection's dashed
    highlight outline is a live-editing affordance, not something that
    belongs in a printed deliverable."""
    scene.clearSelection()

    writer = QPdfWriter(path)
    writer.setPageSize(QPageSize(QPageSize.A4))
    writer.setPageOrientation(QPageLayout.Landscape)
    writer.setResolution(150)

    painter = QPainter(writer)
    try:
        _draw_schematic_page(painter, writer, scene, project)
        if include_signal_list:
            from logic_studio.core.crossref import build_crossref
            rows = signal_list_rows(build_crossref(project))
            if rows:
                writer.newPage()
                _draw_signal_list_pages(painter, writer, rows)
    finally:
        painter.end()


def _draw_schematic_page(painter: QPainter, writer: QPdfWriter, scene, project):
    page_width = writer.width()
    page_height = writer.height()

    title_font = QFont("Arial", 16)
    painter.setFont(title_font)
    name = project.settings.get("name", "Projekt")
    painter.drawText(
        QRectF(PAGE_MARGIN, 0, page_width - 2 * PAGE_MARGIN, TITLE_BLOCK_HEIGHT / 2),
        Qt.AlignLeft | Qt.AlignVCenter, name,
    )

    subtitle_font = QFont("Arial", 9)
    painter.setFont(subtitle_font)
    from datetime import datetime
    painter.drawText(
        QRectF(PAGE_MARGIN, TITLE_BLOCK_HEIGHT / 2, page_width - 2 * PAGE_MARGIN, TITLE_BLOCK_HEIGHT / 2),
        Qt.AlignLeft | Qt.AlignVCenter,
        f"EPW Logic Studio — wygenerowano {datetime.now().strftime('%Y-%m-%d %H:%M')}",
    )

    # itemsBoundingRect() (real placed content) rather than the scene's
    # own abstract sceneRect (a fixed, enormous -5000..5000 canvas that
    # would print as a nearly-empty page if used directly).
    source = scene.itemsBoundingRect().adjusted(-20, -20, 20, 20)
    if source.width() <= 0 or source.height() <= 0:
        return  # an empty project — nothing to draw beyond the title block
    target = QRectF(PAGE_MARGIN, TITLE_BLOCK_HEIGHT, page_width - 2 * PAGE_MARGIN, page_height - TITLE_BLOCK_HEIGHT - PAGE_MARGIN)
    scene.render(painter, target, source, Qt.KeepAspectRatio)


_COLUMN_X = (0, 380, 480, 620, 1000, 1400)
_COLUMN_HEADERS = ("Sygnał", "Kategoria", "Typ", "Etykieta", "Zapisuje", "Czyta")
_ROW_HEIGHT = 55


def _draw_signal_list_pages(painter: QPainter, writer: QPdfWriter, rows: list):
    page_width = writer.width()
    page_height = writer.height()
    bottom = page_height - PAGE_MARGIN

    def draw_header(y):
        font = QFont("Arial", 10)
        font.setBold(True)
        painter.setFont(font)
        for x, header in zip(_COLUMN_X, _COLUMN_HEADERS):
            painter.drawText(QRectF(PAGE_MARGIN + x, y, 400, _ROW_HEIGHT), Qt.AlignVCenter, header)
        return y + _ROW_HEIGHT

    title_font = QFont("Arial", 14)
    painter.setFont(title_font)
    painter.drawText(QRectF(PAGE_MARGIN, 0, page_width - 2 * PAGE_MARGIN, 100), Qt.AlignLeft | Qt.AlignVCenter, "Lista sygnałów")

    y = draw_header(150)
    body_font = QFont("Arial", 9)
    painter.setFont(body_font)

    for row in rows:
        if y + _ROW_HEIGHT > bottom:
            writer.newPage()
            y = draw_header(PAGE_MARGIN)
            painter.setFont(body_font)
        for x, value in zip(_COLUMN_X, row):
            painter.drawText(QRectF(PAGE_MARGIN + x, y, 400, _ROW_HEIGHT), Qt.AlignVCenter, str(value))
        y += _ROW_HEIGHT
