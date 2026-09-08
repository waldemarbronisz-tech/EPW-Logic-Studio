"""feat/help-system §7 — core/help_content.py, the static content tree,
and the shared shortcut/catalog generators, all headless (no
QApplication needed for any of this — see core/help_content.py's own
module docstring for why that split matters).
"""
import json
import re
from pathlib import Path

import pytest

from logic_studio.blocks import register_builtin_blocks
from logic_studio.core.help_content import HelpContentStore, HELP_ROOT
from logic_studio.core import block_catalog, shortcuts

register_builtin_blocks()

_LINK_RE = re.compile(r"\]\(help:([^)\s]+)\)")


def _static_topic_ids(language="pl"):
    """Every plain (non-generated) topic id actually referenced in
    toc.json's chapters -- excludes "shortcuts" (generated, §3.3) and
    anything under the block-catalog chapter (generated, §2)."""
    with open(Path(HELP_ROOT) / language / "toc.json", encoding="utf-8") as f:
        toc = json.load(f)
    ids = []
    for chapter in toc["chapters"]:
        for topic in chapter["topics"]:
            if topic["id"] != "shortcuts":
                ids.append(topic["id"])
    return ids


def _static_md_files(language="pl"):
    return sorted(p.stem for p in (Path(HELP_ROOT) / language).glob("*.md"))


# ---- §7.2: completeness --------------------------------------------------

@pytest.mark.parametrize("language", ["pl", "en"])
def test_every_toc_topic_has_a_content_file(language):
    for topic_id in _static_topic_ids(language):
        path = Path(HELP_ROOT) / language / f"{topic_id}.md"
        assert path.is_file(), f"{language}/toc.json lists {topic_id!r} but {path} does not exist"

@pytest.mark.parametrize("language", ["pl", "en"])
def test_every_content_file_is_listed_in_the_toc(language):
    listed = set(_static_topic_ids(language))
    for stem in _static_md_files(language):
        assert stem in listed, f"{language}/{stem}.md exists but is not listed in toc.json (orphaned topic)"

def test_pl_and_en_trees_have_the_same_topic_ids():
    """§3.4: the English tree is a structural mirror (content may stay
    Polish, marked for translation) -- but the SET of topic ids must
    match, or the two languages' Contents trees would silently diverge."""
    assert set(_static_topic_ids("pl")) == set(_static_topic_ids("en"))
    assert set(_static_md_files("pl")) == set(_static_md_files("en"))


# ---- §7.3: internal links resolve -----------------------------------------

def _all_known_topic_ids():
    known = set(_static_topic_ids("pl")) | {"shortcuts"}
    known |= {f"block:{t}" for t in block_catalog.all_type_ids()}
    known |= {f"category:{c}" for c in block_catalog.generate_catalog()}
    return known

@pytest.mark.parametrize("topic_id", _static_topic_ids("pl"))
def test_internal_links_resolve_to_an_existing_topic(topic_id):
    path = Path(HELP_ROOT) / "pl" / f"{topic_id}.md"
    text = path.read_text(encoding="utf-8")
    known = _all_known_topic_ids()
    for target in _LINK_RE.findall(text):
        assert target in known, f"{topic_id}.md links to help:{target}, which is not a known topic"


# ---- §7.4: generator (also covered more exhaustively in test_block_catalog.py) --

def test_help_content_store_never_raises_for_any_known_topic():
    store = HelpContentStore("pl")
    for topic_id in _all_known_topic_ids():
        md = store.load_topic_markdown(topic_id)
        assert isinstance(md, str) and md.strip()

def test_unknown_topic_returns_a_placeholder_not_an_exception():
    store = HelpContentStore("pl")
    md = store.load_topic_markdown("this-topic-does-not-exist")
    assert "nie została znaleziona" in md.lower() or "not found" in md.lower()

def test_missing_language_falls_back_to_polish():
    """A language with no toc.json/files at all (anything other than
    pl/en) must fall back to Polish rather than crash or come back
    empty."""
    store = HelpContentStore("de")
    toc = store.load_toc()
    assert len(toc["chapters"]) > 0
    assert store.load_topic_markdown("welcome").strip()


# ---- §7.5: shortcuts table matches the registered actions ------------------

def test_shortcuts_extractor_finds_the_known_shortcuts():
    rows = shortcuts.extract_shortcuts()
    as_dict = dict(rows)
    # A representative sample of shortcuts genuinely wired in
    # ui/main_window.py -- if one of these is ever rebound, this test
    # fails with a clear diff instead of silently going stale.
    assert as_dict.get("Save") == "Ctrl+S"
    assert as_dict.get("Compile") == "F5"
    assert as_dict.get("Start") == "F6"

def test_shortcuts_extractor_ignores_actions_without_a_shortcut():
    rows = shortcuts.extract_shortcuts()
    texts = [text for text, _ in rows]
    # "Pause" (ui/main_window.py's act_sim_pause) has no shortcut at all.
    assert "Pause" not in texts

def test_shortcuts_markdown_contains_every_extracted_shortcut():
    md = shortcuts.shortcuts_markdown()
    for text, shortcut in shortcuts.extract_shortcuts():
        assert text in md
        assert shortcut in md

def test_shortcuts_extractor_reflects_a_changed_source_file(tmp_path):
    """§7.5's own core claim: a shortcut changed in the CODE changes in
    the generated table -- proven here by pointing the extractor at a
    throwaway file instead of the real main_window.py."""
    fake_source = tmp_path / "fake_main_window.py"
    fake_source.write_text(
        'class X:\n'
        '    def setup(self):\n'
        '        self.act_new = self._make_action("New", self._new, "Ctrl+N")\n'
        '        self.act_weird = self._make_action("Weird", self._weird, shortcut="Ctrl+Shift+W")\n'
        '        self.act_none = self._make_action("NoShortcut", self._none)\n',
        encoding="utf-8",
    )
    rows = shortcuts.extract_shortcuts(fake_source)
    assert rows == [("New", "Ctrl+N"), ("Weird", "Ctrl+Shift+W")]
