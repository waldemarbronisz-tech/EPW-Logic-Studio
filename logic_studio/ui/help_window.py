"""feat/help-system §4 — Help > Pomoc/Katalog bloków/Skróty klawiszowe:
a Windows-98-Help-style window, deliberately the same shape as EPW-OS's
own epw_os/gui/widgets/help_window.py (§1.2 found that design already
proven and asked to reuse it, not invent a second one): QTextBrowser.
setMarkdown() (built into Qt since 5.14 — no new dependency), a
Contents/Index/Search tab strip on the left, back/forward history, and
an internal `help:<topic_id>` link scheme resolved entirely offline —
never a real browser, no network access of any kind.

Content loading/search/generation itself lives in core/help_content.py
(headless, no PySide6) — this module is purely the Qt presentation
layer on top of it, same split as every other core/ui pair in this
project.

Link scheme note: `help:<topic_id>` (a single colon, no `//`) rather
than EPW-OS's own `help://<topic_id>` — a block topic id contains a
colon of its own ("block:logic.and"), and QUrl parses anything after
`//` as an authority (host[:port]), which breaks on a second colon
(`help://block:logic.and` comes back invalid — the port parser chokes
on "logic.and"). The scheme-only form puts the whole id in `url.path()`
unambiguously, colons included.
"""
import base64

from PySide6.QtCore import Qt, QUrl, QSettings, QBuffer, QIODevice
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTabWidget, QTreeWidget,
    QTreeWidgetItem, QListWidget, QListWidgetItem, QLineEdit, QSplitter,
    QTextBrowser,
)

from logic_studio.core.help_content import HelpContentStore
from logic_studio import __version__
from logic_studio.ui.icons import block_icon

_BLOCK_CATALOG_CHAPTER_ID = "block_catalog"


class HelpWindow(QWidget):
    """Non-modal, independent top-level window — reachable from anywhere
    in the program without blocking the rest of it, and reused across
    repeated F1 presses/menu clicks rather than rebuilt each time, so
    Back/Forward history survives (mirrors EPW-OS's own HelpWindow)."""

    def __init__(self, parent=None, settings=None, language: str = "pl"):
        super().__init__(parent, Qt.WindowType.Window)
        self.settings = settings if settings is not None else QSettings("BroniszLabs", "EPW Logic Studio")
        self.setWindowTitle("Pomoc — EPW Logic Studio")
        self._restore_geometry()

        self._store = HelpContentStore(language)
        self._history = []       # list[topic_id]
        self._history_index = -1  # position within _history currently shown

        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 4, 4, 4)

        toolbar = QHBoxLayout()
        self.btn_hide = QPushButton("Ukryj spis")
        self.btn_hide.clicked.connect(self._toggle_left_panel)
        toolbar.addWidget(self.btn_hide)
        self.btn_back = QPushButton("◄ Wstecz")
        self.btn_back.clicked.connect(self._go_back)
        toolbar.addWidget(self.btn_back)
        self.btn_forward = QPushButton("Dalej ►")
        self.btn_forward.clicked.connect(self._go_forward)
        toolbar.addWidget(self.btn_forward)
        toolbar.addStretch()
        outer.addLayout(toolbar)

        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(self._splitter, stretch=1)

        self.tabs = QTabWidget()
        self._build_contents_tab()
        self._build_index_tab()
        self._build_search_tab()
        self._splitter.addWidget(self.tabs)

        self.viewer = QTextBrowser()
        self.viewer.setOpenExternalLinks(False)
        self.viewer.setOpenLinks(False)
        self.viewer.anchorClicked.connect(self._on_anchor_clicked)
        self._splitter.addWidget(self.viewer)
        self._splitter.setSizes([260, 560])

        self.show_welcome()
        self._update_nav_buttons()

    # ---- window geometry (§4.6) --------------------------------------------

    def _restore_geometry(self):
        geo = self.settings.value("help_window/geometry")
        if geo is not None:
            try:
                self.restoreGeometry(geo)
                # §4.6: a geometry restored from a since-shrunk/rotated
                # screen must never leave the window off-screen or
                # absurdly sized — resize() clamps to a sane default if
                # restoreGeometry() silently produced something unusable
                # (0-sized or wildly larger than any plausible screen).
                if self.width() < 200 or self.height() < 150 or self.width() > 8000 or self.height() > 8000:
                    self.resize(780, 540)
            except Exception:
                self.resize(780, 540)
        else:
            self.resize(780, 540)

    def closeEvent(self, event):
        self.settings.setValue("help_window/geometry", self.saveGeometry())
        super().closeEvent(event)

    # ---- left panel: Contents ------------------------------------------

    def _build_contents_tab(self):
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        for chapter in self._store.load_toc()["chapters"]:
            chapter_item = QTreeWidgetItem([chapter["title"]])
            chapter_item.setData(0, Qt.ItemDataRole.UserRole, None)
            if chapter["id"] == _BLOCK_CATALOG_CHAPTER_ID:
                self._populate_block_catalog_chapter(chapter_item, chapter["topics"])
            else:
                for topic in chapter["topics"]:
                    topic_item = QTreeWidgetItem([topic["title"]])
                    topic_item.setData(0, Qt.ItemDataRole.UserRole, topic["id"])
                    chapter_item.addChild(topic_item)
            self.tree.addTopLevelItem(chapter_item)
        self.tree.itemClicked.connect(self._on_tree_item_clicked)
        self.tabs.addTab(self.tree, "Spis treści")

    def _populate_block_catalog_chapter(self, chapter_item, topics):
        """§2/§4.2: one extra tree level for the generated catalog —
        category nodes (their own topic, "category:<name>") each get
        every block of that category nested under them, rather than one
        flat 69-entry list."""
        category_item = None
        for topic in topics:
            if topic.get("_is_category"):
                category_item = QTreeWidgetItem([topic["title"]])
                category_item.setData(0, Qt.ItemDataRole.UserRole, topic["id"])
                chapter_item.addChild(category_item)
            elif category_item is not None:
                block_item = QTreeWidgetItem([topic["title"]])
                block_item.setData(0, Qt.ItemDataRole.UserRole, topic["id"])
                category_item.addChild(block_item)

    def _on_tree_item_clicked(self, item, _column):
        topic_id = item.data(0, Qt.ItemDataRole.UserRole)
        if topic_id is None:
            item.setExpanded(not item.isExpanded())
            return
        self.navigate_to(topic_id)

    # ---- left panel: Index ------------------------------------------

    def _build_index_tab(self):
        self.index_list = QListWidget()
        for term, topic_id in sorted(self._store.index_terms(), key=lambda pair: pair[0].lower()):
            item = QListWidgetItem(term)
            item.setData(Qt.ItemDataRole.UserRole, topic_id)
            self.index_list.addItem(item)
        self.index_list.itemClicked.connect(
            lambda item: self.navigate_to(item.data(Qt.ItemDataRole.UserRole))
        )
        self.tabs.addTab(self.index_list, "Indeks")

    # ---- left panel: Search ------------------------------------------

    def _build_search_tab(self):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(4, 4, 4, 4)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Szukaj...")
        self.search_edit.textChanged.connect(self._on_search_text_changed)
        layout.addWidget(self.search_edit)
        self.search_results = QListWidget()
        self.search_results.itemClicked.connect(
            lambda item: self.navigate_to(item.data(Qt.ItemDataRole.UserRole))
        )
        layout.addWidget(self.search_results, stretch=1)
        self.tabs.addTab(container, "Szukaj")

    def _on_search_text_changed(self, text):
        self.search_results.clear()
        for topic_id, title in self._store.search(text):
            item = QListWidgetItem(title)
            item.setData(Qt.ItemDataRole.UserRole, topic_id)
            self.search_results.addItem(item)

    # ---- navigation / history ------------------------------------------

    def select_tab(self, tab: str):
        index = {"contents": 0, "index": 1, "search": 2}.get(tab, 0)
        self.tabs.setCurrentIndex(index)

    def show_welcome(self):
        self.navigate_to("welcome")

    def navigate_to(self, topic_id: str, _record_history=True):
        if not topic_id:
            return
        title = self._store.topic_title(topic_id) or topic_id
        markdown = self._store.load_topic_markdown(topic_id, version=__version__)
        markdown = self._with_block_icon(topic_id, markdown)
        self.viewer.setMarkdown(markdown)
        self.setWindowTitle(f"Pomoc — {title}")
        if _record_history:
            self._history = self._history[: self._history_index + 1]
            self._history.append(topic_id)
            self._history_index = len(self._history) - 1
        self._update_nav_buttons()

    def _with_block_icon(self, topic_id: str, markdown: str) -> str:
        """§2.1: "podgląd graficzny renderowany tym samym kodem co kanwa"
        — core/block_catalog.py stays headless (no PySide6, per this
        project's own core/UI split), so the actual QIcon is rendered
        HERE, at the Qt presentation layer, and spliced into the
        markdown as a data: URI right under the title — the one place
        in this window a live Qt render (ui/icons.block_icon(), the
        SAME icon the canvas/library tree use) needs to reach a
        Markdown document. QTextDocument's built-in image loader
        resolves a `data:` URI on its own, no extra resource
        registration needed."""
        if not topic_id.startswith("block:"):
            return markdown
        type_id = topic_id[len("block:"):]
        icon = block_icon(type_id, size=64)
        pixmap = icon.pixmap(64, 64)
        if pixmap.isNull():
            return markdown
        buffer = QBuffer()
        buffer.open(QIODevice.WriteOnly)
        pixmap.save(buffer, "PNG")
        b64 = base64.b64encode(buffer.data().data()).decode("ascii")
        # Non-empty alt text is NOT optional here: Qt's Markdown-to-HTML
        # converter (setMarkdown()) silently drops an image link whose
        # alt text is empty (`![](...)`) -- verified directly, including
        # for an ordinary http(s) URL, not just a data: one -- so this
        # would otherwise render nothing with no error of any kind.
        img_line = f"![Ikona bloku](data:image/png;base64,{b64})"
        # Right after the "# Title" line, before the type_id/category line.
        lines = markdown.split("\n", 1)
        if len(lines) == 2:
            return f"{lines[0]}\n\n{img_line}\n{lines[1]}"
        return f"{markdown}\n\n{img_line}\n"

    def _go_back(self):
        if self._history_index > 0:
            self._history_index -= 1
            self.navigate_to(self._history[self._history_index], _record_history=False)

    def _go_forward(self):
        if self._history_index < len(self._history) - 1:
            self._history_index += 1
            self.navigate_to(self._history[self._history_index], _record_history=False)

    def _update_nav_buttons(self):
        self.btn_back.setEnabled(self._history_index > 0)
        self.btn_forward.setEnabled(self._history_index < len(self._history) - 1)

    def _toggle_left_panel(self):
        showing = self.tabs.isVisible()
        self.tabs.setVisible(not showing)
        self.btn_hide.setText("Pokaż spis" if showing else "Ukryj spis")

    def _on_anchor_clicked(self, url: QUrl):
        """Internal cross-references only (e.g.
        [Zaślepka](help:concept_stubs)) — never opens a real browser, no
        network access of any kind (this help is entirely offline)."""
        if url.scheme() == "help":
            topic_id = url.path() or url.host()
            self.navigate_to(topic_id)
