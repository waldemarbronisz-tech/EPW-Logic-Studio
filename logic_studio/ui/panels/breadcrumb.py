"""feat/macro-blocks — the breadcrumb trail shown above the canvas while
"inside" a macro instance's own internal blocks
(MainWindow.enter_macro_instance()/_navigate_to_breadcrumb_index()).
Qt-thin, like every other panel here: this widget knows nothing about
Project/LogicScene/macro definitions — it just renders whatever path it's
given and reports which entry was clicked, mirroring core/crossref.py vs.
ui/panels/signals.py's own split."""
from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QLabel
from PySide6.QtCore import Qt, Signal


class BreadcrumbBar(QWidget):
    # Index into the `names` list last given to set_path() — never fired
    # for the LAST entry (the current level itself; nothing to navigate
    # to by clicking where you already are).
    navigate_to = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._row = QHBoxLayout(self)
        self._row.setContentsMargins(6, 2, 6, 2)
        self._row.setSpacing(4)
        self._row.addStretch(1)
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
        than one entry — the plain top-level view has nothing to show."""
        while self._row.count() > 1:
            item = self._row.takeAt(0)
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
