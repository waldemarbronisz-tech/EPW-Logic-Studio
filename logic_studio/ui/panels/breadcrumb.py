"""feat/macro-blocks — the breadcrumb trail shown above the canvas while
"inside" a macro instance's own internal blocks
(MainWindow.enter_macro_instance()/_navigate_to_breadcrumb_index()).
Also carries the "Piny makrobloku..." button (feat/macro-editable-pins)
that opens MainWindow's pin-management dialog for the current level —
it lives here rather than as a separate toolbar action because it's
only ever meaningful (and only ever shown) in the exact same
"currently inside a macro" state this whole bar already tracks.

Qt-thin, like every other panel here: this widget knows nothing about
Project/LogicScene/macro definitions — it just renders whatever path it's
given and reports which entry was clicked (or the button pressed),
mirroring core/crossref.py vs. ui/panels/signals.py's own split."""
from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QLabel
from PySide6.QtCore import Qt, Signal


class BreadcrumbBar(QWidget):
    # Index into the `names` list last given to set_path() — never fired
    # for the LAST entry (the current level itself; nothing to navigate
    # to by clicking where you already are).
    navigate_to = Signal(int)

    # feat/macro-editable-pins: "Piny makrobloku..." — opens
    # MainWindow's pin-management dialog for the CURRENT level. Only
    # meaningful (and only ever visible) while actually inside a macro,
    # same as the rest of this bar.
    manage_pins_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._row = QHBoxLayout(self)
        self._row.setContentsMargins(6, 2, 6, 2)
        self._row.setSpacing(4)
        self._row.addStretch(1)

        self._pins_button = QPushButton("Piny makrobloku...")
        self._pins_button.setFlat(True)
        self._pins_button.clicked.connect(self.manage_pins_requested)
        self._row.addWidget(self._pins_button)

        # Hidden at the root level (a lone "Główny" crumb is clutter, not
        # information) — set_path() below is what makes it visible.
        self.setVisible(False)

    def set_path(self, names: list):
        """`names` is the FULL path from the root ("Główny") to the
        current level, inclusive — e.g. `["Główny", "Blokada"]` while
        editing macro "Blokada" placed directly on the main canvas, or
        `["Główny", "Blokada", "Zatrzask"]` one level deeper. Every entry
        except the last is a clickable button; the last is the current
        level, shown bold, not clickable. Shown only when there's more
        than one entry — the plain top-level view has nothing to show.

        Layout has two permanent anchors that must survive every call —
        the leading stretch (index 0) and the trailing "Piny makrobloku..."
        button (the last index) — crumbs are always cleared from, and
        re-inserted into, strictly BETWEEN the two."""
        while self._row.count() > 2:
            item = self._row.takeAt(1)
            widget = item.widget()
            if widget is not None:
                # setParent(None) detaches it from the widget tree
                # IMMEDIATELY (unlike deleteLater() alone, which only
                # schedules the actual C++ destruction for the next event-
                # loop spin — a rapid-fire set_path()/set_path() with no
                # event loop in between, e.g. breadcrumb navigation two
                # levels in one call, would otherwise leave the previous
                # call's widgets as invisible but still-attached QObject
                # children, findChildren()-visible until whenever the next
                # spin happens to land).
                widget.setParent(None)
                widget.deleteLater()

        for i, name in enumerate(names):
            if i == len(names) - 1:
                label = QLabel(name)
                label.setStyleSheet("font-weight: bold;")
                self._row.insertWidget(self._row.count() - 1, label)
            else:
                button = QPushButton(name)
                button.setFlat(True)
                button.setCursor(Qt.PointingHandCursor)
                button.clicked.connect(lambda checked=False, index=i: self.navigate_to.emit(index))
                self._row.insertWidget(self._row.count() - 1, button)
                separator = QLabel("›")  # ›
                self._row.insertWidget(self._row.count() - 1, separator)

        self.setVisible(len(names) > 1)
