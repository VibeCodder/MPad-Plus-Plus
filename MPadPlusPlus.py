import sys
import json
import os
import re
import webbrowser
from PySide6.QtWidgets import (QApplication, QMainWindow, QTextEdit, QVBoxLayout, 
                               QHBoxLayout, QWidget, QToolBar, QDialog, 
                               QLabel, QLineEdit, QDialogButtonBox, QColorDialog, 
                               QPushButton, QFormLayout, QSpinBox, QFontDialog, 
                               QMessageBox, QFileDialog, QMenu, QToolButton, QCheckBox,
                               QTabWidget, QTabBar, QSizePolicy, QScrollArea, QPlainTextEdit,
                               QRadioButton, QButtonGroup, QListWidget, QListWidgetItem,
                               QComboBox)
from PySide6.QtGui import (QColor, QTextCharFormat, QTextBlockFormat, QTextListFormat,
                           QKeySequence, QShortcut, QFont, QPalette,
                           QAction, QActionGroup, QTextCursor, QDragEnterEvent, QDropEvent, 
                           QTextDocument, QBrush, QPainter, QTextFormat, QPen, QIcon, QPixmap,
                           QSyntaxHighlighter, QTextTableFormat, QTextLength, QTextFrameFormat)
from PySide6.QtCore import (QRegularExpression, Qt, QFileInfo, QPoint, QSize, QRect, QRectF,
                            QTimer, QObject, QThread, Signal)

try:
    from PySide6.QtSvg import QSvgRenderer
except ImportError:
    # Toolbar icons degrade gracefully to text-only buttons if the
    # optional QtSvg module isn't installed alongside PySide6.
    QSvgRenderer = None

try:
    import phunspell
except ImportError:
    # Spell checking degrades gracefully (feature disabled, with an
    # explanatory tooltip in the Spelling menu) if the optional
    # 'phunspell' package isn't installed. Install with: pip install phunspell
    phunspell = None

# --- Spell checking ---
# (display name, phunspell locale code). phunspell bundles Hunspell
# dictionaries for all of these out of the box.
SPELLCHECK_LANGUAGES = [
    ("English (US)", "en_US"),
    ("English (UK)", "en_GB"),
    ("Polski", "pl_PL"),
    ("Deutsch", "de_DE"),
    ("Français", "fr_FR"),
    ("Español", "es"),
    ("Italiano", "it_IT"),
    ("Português (PT)", "pt_PT"),
    ("Português (BR)", "pt_BR"),
    ("Русский", "ru_RU"),
    ("Українська", "uk_UA"),
    ("Nederlands", "nl_NL"),
    ("Čeština", "cs_CZ"),
    ("Svenska", "sv_SE"),
]

# Matches "words" for spell-check purposes: runs of Unicode letters
# (so Polish ąćęłńóśźż etc. are included, digits/underscore are not),
# optionally joined by a single internal apostrophe or hyphen so
# contractions and hyphenated words ("don't", "wielko-formatowy")
# aren't split into bogus fragments.
SPELLCHECK_WORD_RE = re.compile(r"[^\W\d_]+(?:['\u2019-][^\W\d_]+)*", re.UNICODE)


# --- Default settings ---
DEFAULT_SETTINGS = {
    "app_bg": "#1e1e1e",
    "app_text": "#d4d4d4",
    "editor_bg": "#1e1e1e",
    "editor_text": "#d4d4d4",
    "current_line_highlight": "#2a2a2a",
    "font_family": "Consolas",
    "font_size": 12,
    
    "h1": "#569cd6", "h1_size": 24,
    "h2": "#569cd6", "h2_size": 20,
    "h3": "#569cd6", "h3_size": 18,
    "h4": "#569cd6", "h4_size": 16,
    "h5": "#569cd6", "h5_size": 14,
    "h6": "#569cd6", "h6_size": 13,
    "bold": "#ce9178", "bold_size": 0,
    "italic": "#c586c0", "italic_size": 0,
    "underline": "#dcdcaa", "underline_size": 0,
    "code": "#b5cea8", "code_bg": "#2d2d2d", "code_size": 0,
    "quote": "#6a9955", "quote_size": 0,
    "quote_line_color": "#5c5c5c",
    "quote_line_width": 3,

    "hr_color": "#5c5c5c",
    "hr_thickness": 2,
    "link": "#3794ff", "link_size": 0,
    "link_underline": True,
    
    "table_header_bg": "#673AB7",
    "table_header_text": "#FFFFFF",
    "table_row1_bg": "#252526",
    "table_row2_bg": "#2d2d2d",
    "table_header_align": "left",
    "table_row_align": "left",
    
    "tab_active_bg": "#1e1e1e",
    "tab_inactive_bg": "#2d2d2d",
    "tab_active_bar_color": "#007acc",

    # How a Shift+Enter soft line break (within the same paragraph) is
    # written to Markdown on save. One of: "br" (<br/>), "double_space"
    # (two trailing spaces + newline), "backslash" (\ + newline).
    "line_break_style": "double_space",

    # Spell checking
    "spellcheck_enabled": False,
    "spellcheck_langs": ["pl_PL"],
    "spellcheck_custom_words": [],
}

CODE_PROP = QTextFormat.UserProperty + 1
QUOTE_PROP = QTextFormat.UserProperty + 2
BLOCK_CODE_PROP = QTextFormat.UserProperty + 3
HR_PROP = QTextFormat.UserProperty + 4
# Per-table text alignment OVERRIDE, set from a specific table's "Edit
# Table" dialog (see MainWindow.open_table_editor()) and stored on that
# QTextTableFormat. When absent, apply_table_style() falls back to the
# app-wide default set in Preferences > General (settings keys
# "table_header_align"/"table_row_align") - so alignment is global by
# default, but any individual table can opt out and pick its own.
TABLE_HEADER_ALIGN_PROP = QTextFormat.UserProperty + 5
TABLE_ROW_ALIGN_PROP = QTextFormat.UserProperty + 6

# --- Toolbar icons ---
# Simple, original monoline glyphs (20x20 viewBox). "{color}" is filled in
# at render time with the current theme's toolbar text color, so icons stay
# legible across light/dark themes without needing separate asset files.
TOOLBAR_SVG_ICONS = {
    "bold": """
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20">
          <path fill="{color}" d="M5 3h6a3.5 3.5 0 0 1 2.4 6.05A3.75 3.75 0 0 1 11.5 16H5a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z
                   M7 5.5v3.5h4a1.75 1.75 0 0 0 0-3.5H7z
                   M7 11v3.5h4.5a1.75 1.75 0 0 0 0-3.5H7z"/>
        </svg>""",
    "italic": """
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20">
          <path fill="{color}" d="M8 3.5h6.5a1 1 0 1 1 0 2H12l-3 9h2.5a1 1 0 1 1 0 2H5a1 1 0 1 1 0-2h2.5l3-9H8a1 1 0 1 1 0-2z"/>
        </svg>""",
    "underline": """
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20">
          <path fill="{color}" d="M5.5 3a1 1 0 0 1 1 1v5.2a3.5 3.5 0 0 0 7 0V4a1 1 0 1 1 2 0v5.2a5.5 5.5 0 0 1-11 0V4a1 1 0 0 1 1-1z"/>
          <rect fill="{color}" x="4" y="16" width="12" height="1.6" rx="0.8"/>
        </svg>""",
    "code": """
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20">
          <path fill="none" stroke="{color}" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"
                d="M7 5.5 2.8 10 7 14.5 M13 5.5 17.2 10 13 14.5"/>
        </svg>""",
    "quote": """
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20">
          <path fill="{color}" d="M4 6.5a3 3 0 0 1 3-3h.3a1 1 0 1 1 0 2H7a1 1 0 0 0-1 1v.3c1.4.2 2.5 1.4 2.5 2.9a3 3 0 0 1-3 3A3 3 0 0 1 2.5 9.7V9.6A3 3 0 0 1 4 6.5z
                   M11.7 6.5a3 3 0 0 1 3-3h.3a1 1 0 1 1 0 2h-.3a1 1 0 0 0-1 1v.3c1.4.2 2.5 1.4 2.5 2.9a3 3 0 0 1-3 3 3 3 0 0 1-3-2.9v-.1a3 3 0 0 1 1.5-3.2z"/>
        </svg>""",
    "ul": """
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20">
          <circle fill="{color}" cx="3.3" cy="5" r="1.4"/>
          <circle fill="{color}" cx="3.3" cy="10" r="1.4"/>
          <circle fill="{color}" cx="3.3" cy="15" r="1.4"/>
          <rect fill="{color}" x="7" y="4.1" width="10" height="1.8" rx="0.9"/>
          <rect fill="{color}" x="7" y="9.1" width="10" height="1.8" rx="0.9"/>
          <rect fill="{color}" x="7" y="14.1" width="10" height="1.8" rx="0.9"/>
        </svg>""",
    "ol": """
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20">
          <text x="1" y="6.6" font-family="sans-serif" font-size="5.4" fill="{color}">1</text>
          <text x="1" y="11.6" font-family="sans-serif" font-size="5.4" fill="{color}">2</text>
          <text x="1" y="16.6" font-family="sans-serif" font-size="5.4" fill="{color}">3</text>
          <rect fill="{color}" x="7" y="4.1" width="10" height="1.8" rx="0.9"/>
          <rect fill="{color}" x="7" y="9.1" width="10" height="1.8" rx="0.9"/>
          <rect fill="{color}" x="7" y="14.1" width="10" height="1.8" rx="0.9"/>
        </svg>""",
    "table": """
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20">
          <rect fill="none" stroke="{color}" stroke-width="1.6" x="3" y="4" width="14" height="12" rx="1.2"/>
          <path fill="none" stroke="{color}" stroke-width="1.6" d="M3 8.3h14 M3 12.6h14 M9 4v12"/>
        </svg>""",
    "line": """
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20">
          <rect fill="{color}" x="3" y="9.1" width="14" height="1.8" rx="0.9"/>
        </svg>""",
    "link": """
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20">
          <path fill="none" stroke="{color}" stroke-width="1.8" stroke-linecap="round"
                d="M8.2 11.8 11.8 8.2 M7.8 5.9l1.2-1.2a3 3 0 0 1 4.3 4.3l-1.2 1.2
                   M12.2 14.1 11 15.3a3 3 0 0 1-4.3-4.3l1.2-1.2"/>
        </svg>""",
    "spellcheck": """
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20">
          <text x="1" y="12.5" font-family="sans-serif" font-size="11" font-weight="bold" fill="{color}">Aa</text>
          <path fill="none" stroke="#ff5555" stroke-width="1.6" stroke-linecap="round"
                d="M2 16.3q1.1-1.5 2.3 0t2.3 0 2.3 0 2.3 0 2.3 0 2.3 0"/>
        </svg>""",
    "close": """
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20">
          <path fill="none" stroke="{color}" stroke-width="1.8" stroke-linecap="round"
                d="M5.5 5.5 14.5 14.5 M14.5 5.5 5.5 14.5"/>
        </svg>""",
}


def make_svg_icon(name, color, size=18):
    """Render one of TOOLBAR_SVG_ICONS, tinted to `color`, as a QIcon.
    Returns a blank QIcon if QtSvg isn't available, so toolbar buttons
    still work (just without an icon) rather than crashing the app."""
    if QSvgRenderer is None or name not in TOOLBAR_SVG_ICONS:
        return QIcon()
    svg_data = TOOLBAR_SVG_ICONS[name].format(color=color).encode("utf-8")
    renderer = QSvgRenderer(svg_data)
    if not renderer.isValid():
        return QIcon()
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return QIcon(pixmap)

class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self):
        return QSize(self.editor.line_number_area_width(), 0)

    def paintEvent(self, event):
        self.editor.line_number_area_paint_event(event)


class _DictionaryLoaderThread(QThread):
    """Builds a phunspell.Phunspell() dictionary object off the UI thread.
    Parsing the .dic/.aff files takes a noticeable fraction of a second
    (longer for the first, large languages), which would otherwise cause a
    visible freeze the first time spell check is enabled or the language
    is changed."""
    loaded = Signal(str, object)

    def __init__(self, lang_code, parent=None):
        super().__init__(parent)
        self.lang_code = lang_code

    def run(self):
        try:
            dictionary = phunspell.Phunspell(self.lang_code)
        except Exception:
            dictionary = None
        self.loaded.emit(self.lang_code, dictionary)


class _SuggestionLoaderThread(QThread):
    """Computes spelling suggestions for one word off the UI thread.
    phunspell.suggest() walks the whole loaded dictionary computing edit
    distances, which can take a noticeable moment (worse with several
    languages active) - running it synchronously inside
    Editor.contextMenuEvent is what made the right-click menu feel slow
    to appear."""
    ready = Signal(str, list)

    def __init__(self, word, dictionaries, limit=6, parent=None):
        super().__init__(parent)
        self.word = word
        self.dictionaries = dictionaries
        self.limit = limit

    def run(self):
        results = []
        for dictionary in self.dictionaries:
            try:
                for suggestion in dictionary.suggest(self.word):
                    if suggestion not in results:
                        results.append(suggestion)
                    if len(results) >= self.limit:
                        break
            except Exception:
                continue
            if len(results) >= self.limit:
                break
        self.ready.emit(self.word, results)


class SpellCheckManager(QObject):
    """Owns the spell-check state (on/off, active languages, loaded
    dictionaries, personal dictionary) shared by every open Editor tab, so
    all tabs stay in sync and each dictionary is only ever loaded once.

    Multiple languages can be active at once (e.g. Polish + English in the
    same document): a word is considered correct if it's found in ANY of
    the enabled languages' dictionaries, or in the user's personal
    dictionary.

    `settings` is the same dict the rest of the app reads/writes and gets
    persisted via MainWindow.save_settings(), so enabled/languages/custom
    words survive a restart without any separate storage."""

    dictionary_changed = Signal()
    suggestions_ready = Signal(str, list)

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.available = phunspell is not None
        self._dictionaries = {}   # lang_code -> Phunspell instance or None (failed)
        self._loading = set()     # lang_codes currently loading in a thread
        self._threads = []
        self._suggestion_cache = {}    # (lang_codes, word_lower) -> list[str]
        self._suggestion_threads = []
        self.custom_words = set(w.lower() for w in settings.get("spellcheck_custom_words", []))

    @property
    def enabled(self):
        return self.available and bool(self.settings.get("spellcheck_enabled", False))

    @property
    def lang_codes(self):
        codes = self.settings.get("spellcheck_langs")
        if not codes:
            # Backward compatibility with the earlier single-language setting.
            legacy = self.settings.get("spellcheck_lang")
            codes = [legacy] if legacy else ["en_US"]
        return list(codes)

    def set_enabled(self, value):
        self.settings["spellcheck_enabled"] = bool(value)
        if value:
            for code in self.lang_codes:
                self._ensure_loaded(code)
        self.dictionary_changed.emit()

    def set_languages(self, lang_codes):
        lang_codes = list(lang_codes) or ["en_US"]
        self.settings["spellcheck_langs"] = lang_codes
        if self.enabled:
            for code in lang_codes:
                self._ensure_loaded(code)
        self.dictionary_changed.emit()

    def is_language_active(self, lang_code):
        return lang_code in self.lang_codes

    def _ensure_loaded(self, lang_code):
        if not self.available or lang_code in self._dictionaries or lang_code in self._loading:
            return
        self._loading.add(lang_code)
        self._threads = [t for t in self._threads if t.isRunning()]
        thread = _DictionaryLoaderThread(lang_code, self)
        thread.loaded.connect(self._on_dictionary_loaded)
        self._threads.append(thread)
        thread.start()

    def _on_dictionary_loaded(self, lang_code, dictionary):
        self._dictionaries[lang_code] = dictionary
        self._loading.discard(lang_code)
        self.dictionary_changed.emit()

    def current_dictionaries(self):
        """Every loaded dictionary for the currently active language(s).
        Triggers a background load for any active language not loaded yet."""
        if not self.enabled:
            return []
        dictionaries = []
        for code in self.lang_codes:
            dic = self._dictionaries.get(code)
            if dic is None and code not in self._loading:
                self._ensure_loaded(code)
            if dic is not None:
                dictionaries.append(dic)
        return dictionaries

    def is_custom_word(self, word):
        return word.lower() in self.custom_words

    def add_custom_word(self, word):
        """Permanently add `word` to the user's personal dictionary (it
        will never be flagged as misspelled again), persisted in settings
        and manageable later via Preferences."""
        self.custom_words.add(word.lower())
        self.settings["spellcheck_custom_words"] = sorted(self.custom_words)
        self.dictionary_changed.emit()

    def remove_custom_word(self, word):
        self.custom_words.discard(word.lower())
        self.settings["spellcheck_custom_words"] = sorted(self.custom_words)
        self.dictionary_changed.emit()

    def set_custom_words(self, words):
        self.custom_words = set(w.lower() for w in words)
        self.settings["spellcheck_custom_words"] = sorted(self.custom_words)
        self.dictionary_changed.emit()

    def is_correct(self, word):
        if self.is_custom_word(word):
            return True
        dictionaries = self.current_dictionaries()
        if not dictionaries:
            # No dictionary available/loaded yet: don't flag anything as
            # wrong until we can actually check it (avoids a flash of
            # false positives while a dictionary loads in the background).
            return True
        for dictionary in dictionaries:
            try:
                if dictionary.lookup(word):
                    return True
            except Exception:
                return True
        return False

    def suggestions(self, word, limit=6):
        results = []
        for dictionary in self.current_dictionaries():
            try:
                for suggestion in dictionary.suggest(word):
                    if suggestion not in results:
                        results.append(suggestion)
                    if len(results) >= limit:
                        return results
            except Exception:
                continue
        return results

    def _suggestion_cache_key(self, word):
        return (tuple(sorted(self.lang_codes)), word.lower())

    def suggestions_cached(self, word):
        """Returns already-computed suggestions for `word` if we have them,
        or None if they haven't been fetched yet. Never blocks."""
        return self._suggestion_cache.get(self._suggestion_cache_key(word))

    def request_suggestions(self, word, limit=6):
        """Non-blocking counterpart to suggestions(): returns cached
        suggestions immediately if available, otherwise kicks off a
        background computation and returns None. `suggestions_ready`
        fires with the same word once that background thread finishes,
        so callers (the right-click menu) can open instantly with a
        placeholder instead of freezing while phunspell searches its
        dictionary, then fill in the real list a moment later."""
        key = self._suggestion_cache_key(word)
        cached = self._suggestion_cache.get(key)
        if cached is not None:
            return cached
        self._suggestion_threads = [t for t in self._suggestion_threads if t.isRunning()]
        thread = _SuggestionLoaderThread(word, self.current_dictionaries(), limit, self)
        thread.ready.connect(lambda w, results, k=key: self._on_suggestions_ready(k, results))
        self._suggestion_threads.append(thread)
        thread.start()
        return None

    def _on_suggestions_ready(self, key, results):
        self._suggestion_cache[key] = results
        self.suggestions_ready.emit(key[1], results)

    def shutdown(self):
        """Stop cleanly on app exit so no background QThread outlives
        the SpellCheckManager (which would print a Qt warning / risk a
        crash on interpreter shutdown)."""
        for thread in self._threads:
            thread.wait(2000)
        for thread in self._suggestion_threads:
            thread.wait(2000)


class SpellCheckHighlighter(QSyntaxHighlighter):
    """Underlines words not found in the active dictionary with a red
    wavy line, the same way as in Word/most text editors. Attached to
    one Editor's document; Editor connects SpellCheckManager's
    dictionary_changed signal to rehighlight() so every open tab updates
    together when spell check is toggled, the language changes, a
    dictionary finishes loading, or a word is added/ignored."""

    def __init__(self, document, editor):
        super().__init__(document)
        self.editor = editor
        self._format = QTextCharFormat()
        self._format.setUnderlineStyle(QTextCharFormat.UnderlineStyle.WaveUnderline)
        self._format.setUnderlineColor(QColor("#ff3333"))

    def highlightBlock(self, text):
        window = self.editor.window()
        manager = getattr(window, "spell_manager", None)
        if manager is None or not manager.enabled:
            return

        block = self.currentBlock()
        block_fmt = block.blockFormat()
        if block_fmt.hasProperty(BLOCK_CODE_PROP) and block_fmt.property(BLOCK_CODE_PROP) == True:
            return  # skip code blocks entirely

        doc = self.document()
        probe = QTextCursor(doc)
        for match in SPELLCHECK_WORD_RE.finditer(text):
            word = match.group()
            if len(word) < 2:
                continue

            # Skip inline code and hyperlinks - neither should be flagged
            # as misspelled (code identifiers and URLs rarely are words).
            probe.setPosition(block.position() + match.start() + 1)
            cf = probe.charFormat()
            if cf.isAnchor() or (cf.hasProperty(CODE_PROP) and cf.property(CODE_PROP) == True):
                continue

            if not manager.is_correct(word):
                self.setFormat(match.start(), len(word), self._format)


class Editor(QTextEdit):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.current_file = None
        self.view_mode = "formatted"
        self.setAcceptDrops(True)
        self.apply_settings()

        # --- Custom cursor rendering ---
        # Qt's built-in text cursor (driven by QWidgetTextControl's internal
        # blink timer) has been observed to stop rendering visually on Windows
        # after the document is replaced via setMarkdown() during file load,
        # even though the cursor's logical position, focus state, and
        # cursorRect() all remain correct. To make the caret reliable
        # regardless of that platform quirk, we disable Qt's own cursor
        # painting entirely and draw it ourselves in paintEvent, driven by our
        # own QTimer. This never depends on QWidgetTextControl's internal
        # blink/focus bookkeeping surviving a document reload.
        self.setCursorWidth(0)
        self._caret_visible = True
        self._caret_timer = QTimer(self)
        self._caret_timer.timeout.connect(self._toggle_caret)
        flash_time = QApplication.cursorFlashTime()
        self._caret_timer.setInterval(flash_time // 2 if flash_time > 0 else 500)
        self._caret_timer.start()

        # setCursorWidth(0) stops Qt from *drawing* its own cursor, but it
        # does NOT stop QWidgetTextControl from running its own internal
        # cursorBlinkTimer (see QWidgetTextControlPrivate::updateCursorBlinking
        # in Qt's source: it only skips starting that timer when the
        # application's cursorFlashTime is < 2ms). That internal timer keeps
        # firing on its own schedule and, every time it does, emits an
        # updateRequest for a *narrow, cursor-sized rect* (via repaintCursor()
        # -> cursorRectPlusUnicodeDirectionMarkers) which gets forwarded to a
        # PARTIAL viewport update - completely independent of, and out of
        # phase with, our own _caret_timer above. Two consequences of that:
        # 1) our caret_width-wide fillRect gets clipped down to Qt's much
        #    narrower internal cursor rect whenever THAT timer's repaint
        #    fires, so the caret visibly alternates between full width and a
        #    1px sliver ("flat, then thicker") independent of our own blink.
        # 2) if that narrow rect is computed just before a scroll/reload and
        #    only delivered just after, it can invalidate/repaint the wrong
        #    on-screen location - a second, stale-looking caret.
        # Setting the app-wide flash time to 0 stops Qt from ever starting
        # that internal timer, so ours is the only thing driving the blink.
        QApplication.instance().setCursorFlashTime(0)

        self.line_number_area = LineNumberArea(self)
        self.textChanged.connect(self.update_line_number_area_width)
        self.verticalScrollBar().valueChanged.connect(self.line_number_area.update)
        self.cursorPositionChanged.connect(self.highlight_current_line)
        self.cursorPositionChanged.connect(self.line_number_area.update)
        self.cursorPositionChanged.connect(self._reset_caret_blink)
        self.textChanged.connect(self._reset_caret_blink)
        
        self.table_btn = QToolButton(self)
        self.table_btn.setText("⚙")
        self.table_btn.setToolTip("Edit Table")
        self.table_btn.setStyleSheet("""
            QToolButton {
                background-color: #007acc; color: white; border: none;
                border-radius: 5px; padding: 5px; font-size: 16px; font-weight: bold;
            }
            QToolButton:hover { background-color: #1a8cff; }
        """)
        self.table_btn.setFixedSize(32, 32)
        self.table_btn.hide()
        self.table_btn.clicked.connect(self.window().open_table_editor)
        
        self.cursorPositionChanged.connect(self.update_table_button)
        self.verticalScrollBar().valueChanged.connect(self.update_table_button)
        
        self.update_line_number_area_width()
        self.highlight_current_line()
        self.setMouseTracking(True)

        # --- Spell checking ---
        self.spell_highlighter = SpellCheckHighlighter(self.document(), self)
        spell_manager = getattr(self.window(), "spell_manager", None)
        if spell_manager is not None:
            spell_manager.dictionary_changed.connect(self.spell_highlighter.rehighlight)

    def _toggle_caret(self):
        self._caret_visible = not self._caret_visible
        # viewport().update() only *schedules* a repaint and lets Qt/the OS
        # coalesce it with other pending paint messages. On Windows this
        # coalescing has been observed to occasionally drop or truncate the
        # scheduled region right after a focus change or document reload,
        # which is exactly how a "phantom" second caret survives: the old
        # caret's pixels were never actually part of a paint that ran.
        # repaint() forces the paint to happen synchronously, right now,
        # covering the whole viewport, so there is no window in which a
        # stale caret can be left un-repainted.
        self.viewport().repaint()

    def _reset_caret_blink(self):
        # Make the caret solid-visible immediately after any cursor move or
        # edit (standard caret UX), then let it resume blinking.
        self._caret_visible = True
        self.viewport().repaint()

    def focusInEvent(self, event):
        super().focusInEvent(event)
        # Windows re-syncs Qt's style hints (including cursorFlashTime) from
        # the system theme at various points after startup (e.g. on the
        # first show, or WM_SETTINGCHANGE), which can silently overwrite the
        # 0-override set once in __init__. QWidgetTextControl reads
        # cursorFlashTime right here, on focus-in, to decide whether to
        # (re)start its own internal blink timer - so re-assert 0 at this
        # exact point rather than trusting the earlier one-time override to
        # have survived.
        QApplication.instance().setCursorFlashTime(0)
        self._caret_visible = True
        if not self._caret_timer.isActive():
            self._caret_timer.start()
        self.viewport().repaint()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self._caret_timer.stop()
        self._caret_visible = False
        self.viewport().repaint()

    def apply_settings(self):
        self.setStyleSheet(f"QTextEdit {{ background-color: {self.settings['editor_bg']}; color: {self.settings['editor_text']}; border: none; }}")
        font = QFont(self.settings["font_family"], self.settings["font_size"])
        self.setFont(font)

        # setStyleSheet does NOT update QPalette, but Qt draws the text cursor
        # using QPalette::Text. On Windows the default palette Text is black,
        # making the cursor invisible on a dark background. Set it explicitly.
        palette = self.palette()
        palette.setColor(palette.ColorRole.Base,            QColor(self.settings['editor_bg']))
        palette.setColor(palette.ColorRole.Text,            QColor(self.settings['editor_text']))
        palette.setColor(palette.ColorRole.Window,          QColor(self.settings['editor_bg']))
        palette.setColor(palette.ColorRole.WindowText,      QColor(self.settings['editor_text']))
        palette.setColor(palette.ColorRole.Highlight,       QColor(self.settings['editor_bg']).lighter(160))
        palette.setColor(palette.ColorRole.HighlightedText, QColor(self.settings['editor_text']))
        self.setPalette(palette)

        css = f"""
            body {{ color: {self.settings['editor_text']}; font-family: '{self.settings['font_family']}'; font-size: {self.settings['font_size']}pt; }}
            h1 {{ color: {self.settings['h1']}; font-size: {self.settings.get('h1_size', 24)}pt; }}
            h2 {{ color: {self.settings['h2']}; font-size: {self.settings.get('h2_size', 20)}pt; }}
            h3 {{ color: {self.settings['h3']}; font-size: {self.settings.get('h3_size', 18)}pt; }}
            h4 {{ color: {self.settings['h4']}; font-size: {self.settings.get('h4_size', 16)}pt; }}
            h5 {{ color: {self.settings['h5']}; font-size: {self.settings.get('h5_size', 14)}pt; }}
            h6 {{ color: {self.settings['h6']}; font-size: {self.settings.get('h6_size', 13)}pt; }}
            code {{ color: {self.settings['code']}; background-color: {self.settings['code_bg']}; }}
            a {{ color: {self.settings['link']}; }}
            blockquote {{ color: {self.settings['quote']}; }}
        """
        self.document().setDefaultStyleSheet(css)

    def line_number_area_width(self):
        digits = 1
        max_num = max(1, self.document().blockCount())
        while max_num >= 10:
            max_num /= 10
            digits += 1
        space = 3 + self.fontMetrics().horizontalAdvance('9') * digits + 10
        return space

    def update_line_number_area_width(self):
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)
        if self.window():
            self.window().update_toolbar_margin()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.line_number_area.setGeometry(QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height()))

    def scrollContentsBy(self, dx, dy):
        # QTextEdit's own scrollContentsBy (see qtextedit.cpp) does
        # viewport().scroll(dx, dy): it blits the existing viewport pixels
        # to their new position and only schedules a repaint for the
        # newly-exposed strip, not the whole viewport. That's fine for
        # Qt's own text rendering, which knows how to redraw correctly
        # inside that small strip, but our current-line highlight, quote
        # bars, and hand-drawn caret in paintEvent() below are manual
        # overlays: they get shifted along with the blit like any other
        # pixel. viewport().scroll() performs that blit (and paints the
        # newly-exposed strip) synchronously, before a later, merely
        # *scheduled* full update() ever runs - so the old caret can still
        # flash into view, or even stay, as a frozen "second cursor" that
        # then rides along with any further blit (e.g. when lines are
        # inserted/deleted above it, which also triggers a scroll to keep
        # the cursor visible). The only reliable fix is to skip Qt's blit
        # shortcut entirely: don't call the base implementation at all,
        # just repaint the whole viewport from scratch every time. Qt's
        # own text painting (called from our paintEvent via
        # super().paintEvent()) always draws at the *current* scrollbar
        # offset regardless of whether a blit happened, so this is safe -
        # it just means every scroll does a full, artifact-free redraw.
        # Use repaint() rather than update(): update() only schedules the
        # redraw and lets Qt coalesce/collapse it with other pending paint
        # messages, which on Windows can end up dropping the repaint for
        # this specific region - letting a stale caret survive the scroll
        # instead of being wiped by the full redraw we're asking for here.
        self.viewport().repaint()

    def paintEvent(self, event):
        # Draw current-line highlight as background BEFORE Qt renders text+cursor.
        # Using ExtraSelection for this caused a Windows-specific bug where Qt
        # rendered the cursor in the selection's default foreground (black),
        # making it invisible on the dark background.
        line_color = QColor(self.settings['current_line_highlight'])
        cursor_block = self.textCursor().block()
        if cursor_block.isValid():
            block_rect = self.document().documentLayout().blockBoundingRect(cursor_block)
            scroll_y = self.verticalScrollBar().value()
            y_top = int(block_rect.top()    - scroll_y)
            y_h   = int(block_rect.height())
            bg_painter = QPainter(self.viewport())
            bg_painter.fillRect(0, y_top, self.viewport().width(), y_h, line_color)
            bg_painter.end()

        super().paintEvent(event)

        # Draw quote-group bars on top of text.
        painter = QPainter(self.viewport())
        line_width = self.settings.get('quote_line_width', 3)
        line_qcolor = QColor(self.settings.get('quote_line_color', '#5c5c5c'))
        painter.setPen(QPen(line_qcolor, line_width))

        block = self.document().firstBlock()
        viewport_height = self.viewport().height()

        def is_quote_block(b):
            return (b.isValid() and b.isVisible()
                    and b.blockFormat().hasProperty(QUOTE_PROP)
                    and b.blockFormat().property(QUOTE_PROP) == True)

        while block.isValid():
            if not is_quote_block(block):
                block = block.next()
                continue
            group_start = block
            group_end   = block
            nxt = block.next()
            while is_quote_block(nxt):
                group_end = nxt
                nxt = nxt.next()
            start_rect = self.document().documentLayout().blockBoundingRect(group_start)
            end_rect   = self.document().documentLayout().blockBoundingRect(group_end)
            top    = int(start_rect.top()    - self.verticalScrollBar().value())
            bottom = int(end_rect.bottom()   - self.verticalScrollBar().value())
            if bottom > 0 and top < viewport_height:
                x = max(2, line_width // 2)
                painter.drawLine(x, top, x, bottom)
            block = nxt
        painter.end()

        # Draw horizontal line (thematic break) blocks.
        # Using fillRect() instead of drawLine()+thick QPen: a stroked
        # drawLine() is centered on the (float) y coordinate, so for a
        # multi-pixel-wide pen the rasterizer has to decide how to split
        # that width across pixel rows, and without antialiasing that
        # rounding isn't guaranteed consistent from one y position to the
        # next - producing lines that visibly differ in thickness. A
        # filled rect of an exact integer height has no such ambiguity.
        # On fractional display scaling (e.g. 125%/150%), a logical-pixel
        # fillRect still has to land on the *device* pixel grid, and Qt/the
        # OS rounds each line's top/bottom edge independently - so with a
        # scale factor like 1.25, some lines round up to an extra device
        # pixel and others don't, giving a visibly inconsistent 2px/3px mix
        # even though the logical height is identical every time. Fix:
        # compute the device-pixel height once (a constant), and only let
        # the top edge - not the thickness - jitter by rounding.
        hr_painter = QPainter(self.viewport())
        hr_thickness = max(1, int(round(self.settings.get('hr_thickness', 2))))
        hr_qcolor = QColor(self.settings.get('hr_color', '#5c5c5c'))
        dpr = self.devicePixelRatioF() or 1.0
        height_dev = max(1, round(hr_thickness * dpr))
        hr_block = self.document().firstBlock()
        while hr_block.isValid():
            hbf = hr_block.blockFormat()
            if (hr_block.isValid() and hr_block.isVisible()
                    and hbf.hasProperty(HR_PROP) and hbf.property(HR_PROP) == True):
                rect = self.document().documentLayout().blockBoundingRect(hr_block)
                center_y = rect.top() + rect.height() / 2 - self.verticalScrollBar().value()
                top_dev = round((center_y - hr_thickness / 2) * dpr)
                top = top_dev / dpr
                height = height_dev / dpr
                if top + height >= 0 and top <= viewport_height:
                    left = 4
                    right = self.viewport().width() - 4
                    if right > left:
                        hr_painter.fillRect(QRectF(left, top, right - left, height), hr_qcolor)
            hr_block = hr_block.next()
        hr_painter.end()

        # Draw our own caret (see __init__ comment for why Qt's built-in
        # cursor rendering is disabled). Drawn last so it's always on top.
        if self.hasFocus() and self._caret_visible and not self.textCursor().hasSelection():
            rect = self.cursorRect()
            caret_painter = QPainter(self.viewport())
            # Explicitly force crisp, pixel-aligned, non-antialiased fill.
            # Without this, on displays with fractional DPI scaling
            # (125%/150%), the same logical-pixel rect can end up covering a
            # different number of *device* pixels from one blink to the
            # next depending on how the fractional edges land, which reads
            # as the caret's width visibly changing between blinks.
            caret_painter.setRenderHint(QPainter.Antialiasing, False)
            caret_width = max(1, int(round(self.settings.get('caret_width', 2))))
            caret_painter.fillRect(int(rect.x()), int(rect.y()), caret_width, int(rect.height()),
                                    QColor(self.settings['editor_text']))
            caret_painter.end()

    def highlight_current_line(self):
        # Highlight is drawn in paintEvent; just schedule a repaint.
        self.setExtraSelections([])
        self.viewport().update()

    def line_number_area_paint_event(self, event):
        painter = QPainter(self.line_number_area)
        painter.fillRect(event.rect(), QColor(self.settings['editor_bg']).darker(110))

        # QTextDocumentLayout caches each block's bounding rect and only
        # recomputes it lazily, on its own schedule. Touching documentSize()
        # forces Qt to finish any pending layout pass before we read a
        # single rect below, so every position is current.
        self.document().documentLayout().documentSize()

        viewport_height = self.viewport().height()
        fm_height = self.fontMetrics().height()
        scroll_y = self.verticalScrollBar().value()
        painter.setPen(QColor("#858585"))

        def draw(top, number):
            if top + fm_height >= 0 and top <= viewport_height:
                painter.drawText(0, int(top), self.line_number_area.width() - 5, fm_height,
                                 Qt.AlignRight | Qt.AlignVCenter, str(number))

        block_number = 0
        block = self.document().firstBlock()

        while block.isValid():
            table = QTextCursor(block).currentTable()

            if table is not None:
                # A table's cells are each their own block, visited once per
                # CELL in document order - naively walking block.next() over
                # them hands out a separate gutter number per cell instead
                # of per row (the "1/2" then "4/5" split seen around a
                # 3-column table). blockBoundingRect() also can't be
                # trusted for these blocks: it's expressed in the cell's
                # own local coordinate system, not the document's, which is
                # what caused the actual vertical misalignment. cursorRect()
                # resolves the correct on-screen position for a cursor
                # anywhere in the document - including inside table cells -
                # without manual coordinate math, so it's used here to number
                # the table exactly once per row (column 0 of each row),
                # then the whole table is skipped in one jump.
                last_top = 0
                for r in range(table.rows()):
                    row_cursor = QTextCursor(self.document())
                    row_cursor.setPosition(table.cellAt(r, 0).firstPosition())
                    last_top = self.cursorRect(row_cursor).top()
                    block_number += 1
                    draw(last_top, block_number)

                if last_top > viewport_height:
                    break

                next_block = self.document().findBlock(table.lastPosition() + 1)
                # Qt requires a real paragraph immediately after a table
                # (nowhere else to put the cursor to type below it) - if
                # it's still empty, it's purely that structural placeholder,
                # not a line the person actually wrote. Skip its own gutter
                # number so "N rows" reads as exactly N numbers instead of
                # N+1; the moment they type something into it, it's a real
                # line again and gets numbered normally.
                if next_block.isValid() and next_block.text() == "":
                    block = next_block.next()
                else:
                    block = next_block
                continue

            # Mirror image of the above: an empty paragraph sitting right
            # before a table is that same Qt-mandated placeholder (this
            # time for typing *above* the table) rather than a line someone
            # deliberately left blank - skip it too so the table's first
            # row gets the very next number.
            next_block = block.next()
            if (block.text() == "" and next_block.isValid()
                    and QTextCursor(next_block).currentTable() is not None):
                block = next_block
                continue

            rect = self.document().documentLayout().blockBoundingRect(block)
            top = rect.top() - scroll_y

            if top > viewport_height:
                break

            if block.isVisible():
                block_number += 1
                draw(top, block_number)

            block = block.next()

    def update_table_button(self):
        cursor = self.textCursor()
        table = cursor.currentTable()
        if table:
            frame_rect = self.document().documentLayout().frameBoundingRect(table)
            x = int(frame_rect.right()) - self.table_btn.width() - 5
            y = int(frame_rect.bottom()) - self.verticalScrollBar().value() + 2
            
            if x < 5: x = 5
            if y < 0: y = 0
                
            self.table_btn.move(x, y)
            self.table_btn.raise_()
            self.table_btn.show()
        else:
            self.table_btn.hide()

    def mouseMoveEvent(self, event):
        pos = event.position().toPoint()
        if self.anchorAt(pos):
            self.viewport().setCursor(Qt.PointingHandCursor)
        else:
            self.viewport().setCursor(Qt.IBeamCursor)
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            pos = event.position().toPoint()
            anchor = self.anchorAt(pos)
            if anchor:
                webbrowser.open(anchor, new=2)
        super().mousePressEvent(event)

    def _find_char_run(self, click_pos, predicate):
        """Find the contiguous run of characters around click_pos for which
        predicate(char_format) is True, and return a QTextCursor selecting
        it (or None if the clicked spot doesn't match at all).

        Mirrors the hyperlink boundary-detection above: charFormat() always
        reports the format of the character BEFORE the cursor's position,
        never the one at/after it, so the cursor has to be nudged forward
        by one to test the character actually under the click.
        """
        doc = self.document()
        last = doc.characterCount() - 1

        probe = QTextCursor(doc)
        probe.setPosition(click_pos)
        pos = click_pos
        if not predicate(probe.charFormat()):
            if click_pos < last:
                probe.setPosition(click_pos + 1)
                if predicate(probe.charFormat()):
                    pos = click_pos + 1
                else:
                    return None
            else:
                return None

        start_pos = end_pos = pos
        while start_pos > 0:
            probe.setPosition(start_pos)
            if not predicate(probe.charFormat()):
                break
            start_pos -= 1
        while end_pos < last:
            probe.setPosition(end_pos + 1)
            if not predicate(probe.charFormat()):
                break
            end_pos += 1

        run = QTextCursor(doc)
        run.setPosition(start_pos)
        run.setPosition(end_pos, QTextCursor.KeepAnchor)
        return run

    def _spellcheck_word_at(self, position):
        """Return (word, start_pos, end_pos) for the misspelled word under
        `position`, or (None, None, None) if that spot isn't a misspelled
        word (or spell check is off)."""
        spell_manager = getattr(self.window(), "spell_manager", None)
        if spell_manager is None or not spell_manager.enabled:
            return None, None, None
        block = self.document().findBlock(position)
        offset = position - block.position()
        for match in SPELLCHECK_WORD_RE.finditer(block.text()):
            if match.start() <= offset <= match.end():
                word = match.group()
                if len(word) >= 2 and not spell_manager.is_correct(word):
                    return word, block.position() + match.start(), block.position() + match.end()
                return None, None, None
        return None, None, None

    def _replace_spelling(self, start, end, replacement):
        cursor = QTextCursor(self.document())
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.KeepAnchor)
        cursor.insertText(replacement)

    def _add_word_to_dictionary(self, word):
        spell_manager = getattr(self.window(), "spell_manager", None)
        if spell_manager is not None:
            spell_manager.add_custom_word(word)

    def contextMenuEvent(self, event):
        click_pos = self.cursorForPosition(event.pos()).position()
        cursor = self.cursorForPosition(event.pos())
        fmt = cursor.charFormat()
        
        if not fmt.isAnchor():
            temp = QTextCursor(cursor)
            if temp.position() < self.document().characterCount() - 1:
                temp.setPosition(temp.position() + 1)
                if temp.charFormat().isAnchor():
                    cursor = temp
                    fmt = temp.charFormat()

        misspelled_word, ms_start, ms_end = self._spellcheck_word_at(click_pos)

        menu = self.createStandardContextMenu()

        if misspelled_word is not None:
            spell_manager = self.window().spell_manager
            prepend_actions = []

            suggestions = spell_manager.suggestions_cached(misspelled_word)
            if suggestions is None:
                # Not computed yet: don't block menu-opening on phunspell's
                # dictionary search (which is what made this menu feel slow
                # to appear). Show a placeholder now and fill in the real
                # suggestions in place once the background thread finishes -
                # menu.exec() below runs its own event loop, so the queued
                # signal can still update this menu while it's open.
                loading_action = QAction("Loading suggestions…", menu)
                loading_action.setEnabled(False)
                prepend_actions.append(loading_action)

                def _on_bg_suggestions(word, results, target_word=misspelled_word,
                                        ph=loading_action, target_menu=menu,
                                        a=ms_start, b=ms_end, mgr=spell_manager):
                    if word != target_word:
                        return
                    try:
                        mgr.suggestions_ready.disconnect(_on_bg_suggestions)
                    except (TypeError, RuntimeError):
                        pass
                    try:
                        if not target_menu.isVisible():
                            return
                    except RuntimeError:
                        return  # menu already closed/destroyed
                    new_actions = []
                    if results:
                        for suggestion in results:
                            action = QAction(suggestion, target_menu)
                            bold_font = action.font()
                            bold_font.setBold(True)
                            action.setFont(bold_font)
                            action.triggered.connect(
                                lambda checked=False, s=suggestion, a=a, b=b: self._replace_spelling(a, b, s))
                            new_actions.append(action)
                    else:
                        no_suggestions_action = QAction("(no suggestions)", target_menu)
                        no_suggestions_action.setEnabled(False)
                        new_actions.append(no_suggestions_action)
                    target_menu.insertActions(ph, new_actions)
                    target_menu.removeAction(ph)

                spell_manager.suggestions_ready.connect(_on_bg_suggestions)
                spell_manager.request_suggestions(misspelled_word)
            elif suggestions:
                for suggestion in suggestions:
                    action = QAction(suggestion, menu)
                    bold_font = action.font()
                    bold_font.setBold(True)
                    action.setFont(bold_font)
                    action.triggered.connect(
                        lambda checked=False, s=suggestion, a=ms_start, b=ms_end: self._replace_spelling(a, b, s))
                    prepend_actions.append(action)
            else:
                no_suggestions_action = QAction("(no suggestions)", menu)
                no_suggestions_action.setEnabled(False)
                prepend_actions.append(no_suggestions_action)

            sep_1 = QAction(menu)
            sep_1.setSeparator(True)
            prepend_actions.append(sep_1)

            add_action = QAction(f'Add "{misspelled_word}" to Dictionary', menu)
            add_action.triggered.connect(lambda checked=False, w=misspelled_word: self._add_word_to_dictionary(w))
            prepend_actions.append(add_action)

            sep_2 = QAction(menu)
            sep_2.setSeparator(True)
            prepend_actions.append(sep_2)

            existing_actions = menu.actions()
            menu.insertActions(existing_actions[0] if existing_actions else None, prepend_actions)
        
        if fmt.isAnchor():
            href = fmt.anchorHref()
            start_pos = cursor.position()
            end_pos = cursor.position()
            
            while start_pos > 0:
                temp = QTextCursor(self.document())
                # charFormat() reports the format of the character BEFORE
                # the cursor position, not at it - so to test the character
                # at index (start_pos - 1) the cursor must sit at start_pos.
                temp.setPosition(start_pos)
                if not temp.charFormat().isAnchor() or temp.charFormat().anchorHref() != href:
                    break
                start_pos -= 1
                
            while end_pos < self.document().characterCount() - 1:
                temp = QTextCursor(self.document())
                temp.setPosition(end_pos + 1)
                if not temp.charFormat().isAnchor() or temp.charFormat().anchorHref() != href:
                    break
                end_pos += 1
                
            anchor_cursor = QTextCursor(self.document())
            anchor_cursor.setPosition(start_pos)
            anchor_cursor.setPosition(end_pos, QTextCursor.KeepAnchor)
            text = anchor_cursor.selectedText()

            menu.addSeparator()

            # The standard "Copy" action above is only enabled when there's
            # an active text selection, which right-clicking a link doesn't
            # create - so it's greyed out here. These two are always
            # available and copy exactly what you'd want from a link.
            copy_link_action = QAction("Copy Hyperlink", menu)
            copy_link_action.triggered.connect(lambda: QApplication.clipboard().setText(href))
            menu.addAction(copy_link_action)

            copy_md_action = QAction("Copy MD Hyperlink", menu)
            copy_md_action.triggered.connect(lambda: QApplication.clipboard().setText(f"[{text}]({href})"))
            menu.addAction(copy_md_action)

            menu.addSeparator()

            edit_action = QAction("Edit Hyperlink", menu)
            edit_action.triggered.connect(lambda: self.window().edit_link_from_menu(self, anchor_cursor, text, href))
            menu.addAction(edit_action)

            remove_action = QAction("Remove Hyperlink", menu)
            remove_action.triggered.connect(lambda: self.window().remove_hyperlink(self, anchor_cursor))
            menu.addAction(remove_action)

        # --- Remove Bold/Italic/Underline/Code/Quote/Heading ---
        # Only offer removal for formatting actually present at the
        # clicked spot, so the menu stays clean everywhere else.
        format_removals = []

        bold_run = self._find_char_run(click_pos, lambda f: f.fontWeight() == QFont.Bold)
        if bold_run is not None:
            format_removals.append(("Remove Bold", lambda checked=False, r=bold_run: self.window().remove_bold_format(self, r)))

        italic_run = self._find_char_run(click_pos, lambda f: f.fontItalic())
        if italic_run is not None:
            format_removals.append(("Remove Italic", lambda checked=False, r=italic_run: self.window().remove_italic_format(self, r)))

        underline_run = self._find_char_run(click_pos, lambda f: f.fontUnderline())
        if underline_run is not None:
            format_removals.append(("Remove Underline", lambda checked=False, r=underline_run: self.window().remove_underline_format(self, r)))

        code_run = self._find_char_run(click_pos, lambda f: f.hasProperty(CODE_PROP) and f.property(CODE_PROP) == True)
        if code_run is not None:
            format_removals.append(("Remove Code", lambda checked=False, r=code_run: self.window().remove_code_format(self, r)))

        click_block = QTextCursor(self.document()); click_block.setPosition(click_pos)
        block = click_block.block()
        block_fmt = block.blockFormat()

        if block_fmt.hasProperty(BLOCK_CODE_PROP) and block_fmt.property(BLOCK_CODE_PROP) == True:
            format_removals.append(("Remove Code Block", lambda checked=False, b=block: self.window().remove_code_block_format(self, b)))

        if block_fmt.hasProperty(QUOTE_PROP) and block_fmt.property(QUOTE_PROP) == True:
            format_removals.append(("Remove Quote", lambda checked=False, b=block: self.window().remove_quote_format(self, b)))

        level = block_fmt.headingLevel()
        if level > 0:
            format_removals.append((f"Remove Heading (H{level})", lambda checked=False, b=block: self.window().remove_heading_format(self, b)))

        if format_removals:
            menu.addSeparator()
            for label, handler in format_removals:
                action = QAction(label, menu)
                action.triggered.connect(handler)
                menu.addAction(action)

        menu.exec(event.globalPos())

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        # QTextEdit's base dragMoveEvent (which we'd otherwise inherit
        # unchanged) drives QWidgetTextControl's own internal drag-feedback
        # cursor: a preview insertion-point line that follows the mouse
        # while dragging over the widget, separate from the real text
        # cursor. It's drawn as part of Qt's own text rendering inside
        # super().paintEvent(), and Qt only clears it as part of its own
        # dropEvent handling. Since dropEvent() below never calls
        # super().dropEvent() for file URLs (the load is deferred/handled
        # ourselves instead), that cleanup never runs, and the preview line
        # is left frozen at wherever the mouse last was - the "dead" ghost
        # cursor. Skip the base implementation entirely for file drags so
        # that indicator is never created in the first place.
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def keyPressEvent(self, event):
        cur_block_fmt = self.textCursor().block().blockFormat()
        if (event.text() and event.key() not in (Qt.Key_Return, Qt.Key_Enter)
                and cur_block_fmt.hasProperty(HR_PROP)
                and cur_block_fmt.property(HR_PROP) == True):
            # Typing directly into an empty horizontal-line block: drop the
            # HR formatting first (it's always an empty block, so there's
            # nothing to preserve) and let the keystroke insert normally.
            cursor = self.textCursor()
            cursor.beginEditBlock()
            new_fmt = QTextBlockFormat(cur_block_fmt)
            new_fmt.setProperty(HR_PROP, False)
            cursor.setBlockFormat(new_fmt)
            cursor.endEditBlock()
            self.setTextCursor(cursor)

        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            cursor = self.textCursor()
            block = cursor.block()
            block_fmt = block.blockFormat()
            is_quote = (block_fmt.hasProperty(QUOTE_PROP)
                        and block_fmt.property(QUOTE_PROP) == True)
            is_block_code = (block_fmt.hasProperty(BLOCK_CODE_PROP)
                             and block_fmt.property(BLOCK_CODE_PROP) == True)
            is_hr = (block_fmt.hasProperty(HR_PROP)
                     and block_fmt.property(HR_PROP) == True)

            if is_hr:
                # A horizontal-line block is always empty; pressing Enter on
                # it just turns it back into a normal empty paragraph
                # in-place (same convention as exiting an empty quote/code
                # line below), so the user can keep typing right below the
                # line instead of getting stuck inside it.
                cursor.beginEditBlock()
                new_fmt = QTextBlockFormat(block_fmt)
                new_fmt.setProperty(HR_PROP, False)
                cursor.setBlockFormat(new_fmt)
                new_char = QTextCharFormat()
                new_char.setForeground(QColor(self.settings['editor_text']))
                cursor.select(QTextCursor.BlockUnderCursor)
                cursor.mergeCharFormat(new_char)
                cursor.clearSelection()
                cursor.endEditBlock()
                self.setTextCursor(cursor)
                self.window().update_toolbar_state()
                return

            if is_quote:
                if block.text().strip() == '':
                    cursor.beginEditBlock()
                    new_fmt = QTextBlockFormat(block_fmt)
                    new_fmt.setProperty(QUOTE_PROP, False)
                    new_fmt.setLeftMargin(0)
                    cursor.setBlockFormat(new_fmt)
                    new_char = QTextCharFormat()
                    new_char.setFontItalic(False)
                    new_char.setForeground(QColor(self.settings['editor_text']))
                    new_char.setProperty(CODE_PROP, False)
                    cursor.select(QTextCursor.BlockUnderCursor)
                    cursor.mergeCharFormat(new_char)
                    cursor.clearSelection()
                    cursor.endEditBlock()
                    self.setTextCursor(cursor)
                    self.window().update_toolbar_state()
                    return
                else:
                    cursor.beginEditBlock()
                    cursor.insertBlock()
                    new_block_fmt = QTextBlockFormat(block_fmt)
                    cursor.setBlockFormat(new_block_fmt)
                    new_char = QTextCharFormat()
                    new_char.setFontItalic(True)
                    new_char.setForeground(QColor(self.settings['quote']))
                    new_char.setProperty(CODE_PROP, False)
                    cursor.setCharFormat(new_char)
                    cursor.endEditBlock()
                    self.setTextCursor(cursor)
                    self.window().update_toolbar_state()
                    return

            elif is_block_code:
                if block.text().strip() == '':
                    cursor.beginEditBlock()
                    new_fmt = QTextBlockFormat(block_fmt)
                    new_fmt.setProperty(BLOCK_CODE_PROP, False)
                    new_fmt.setBackground(Qt.transparent)
                    cursor.setBlockFormat(new_fmt)
                    new_char = QTextCharFormat()
                    new_char.setForeground(QColor(self.settings['editor_text']))
                    new_char.setFontFamilies([self.settings['font_family']])
                    new_char.setProperty(CODE_PROP, False)
                    new_char.setBackground(Qt.transparent)
                    cursor.select(QTextCursor.BlockUnderCursor)
                    cursor.mergeCharFormat(new_char)
                    cursor.clearSelection()
                    cursor.endEditBlock()
                    self.setTextCursor(cursor)
                    self.window().update_toolbar_state()
                    return
                else:
                    cursor.beginEditBlock()
                    cursor.insertBlock()
                    new_block_fmt = QTextBlockFormat(block_fmt)
                    cursor.setBlockFormat(new_block_fmt)
                    new_char = QTextCharFormat()
                    new_char.setForeground(QColor(self.settings['code']))
                    new_char.setFontFamilies(["Consolas"])
                    new_char.setProperty(CODE_PROP, True)
                    new_char.setBackground(Qt.transparent)
                    cursor.setCharFormat(new_char)
                    cursor.endEditBlock()
                    self.setTextCursor(cursor)
                    self.window().update_toolbar_state()
                    return

        super().keyPressEvent(event)

    def dropEvent(self, event: QDropEvent):
        if event.mimeData().hasUrls():
            url = event.mimeData().urls()[0]
            if url.isLocalFile():
                file_path = url.toLocalFile()
                if file_path.endswith('.md') or file_path.endswith('.txt'):
                    # Accept the drop immediately so the native drag-and-drop
                    # operation completes cleanly, but defer the actual file
                    # load. On Windows, the drop is delivered from *inside*
                    # DoDragDrop's own nested message loop (mouse still
                    # effectively captured, native DnD feedback still being
                    # torn down). Doing the heavy work here - setMarkdown(),
                    # setTextCursor(), setFocus(), and the repaints those
                    # trigger - runs while that nested loop hasn't unwound
                    # yet, which is exactly the state where Windows has been
                    # seen to leave a stale caret behind. Running it a tick
                    # later, once we're back in normal event processing,
                    # avoids that context entirely (this mirrors why File >
                    # Open, which never runs inside that nested loop, has
                    # never shown the problem).
                    event.acceptProposedAction()
                    QTimer.singleShot(0, lambda fp=file_path: self.window().open_file_path(fp, target_editor=self))
                    return
        super().dropEvent(event)
        
    def post_process_markdown(self):
        cursor = QTextCursor(self.document())
        cursor.beginEditBlock()
        
        block = self.document().firstBlock()
        while block.isValid():
            next_block = block.next()
            temp_cursor = QTextCursor(block)
            
            if temp_cursor.currentTable():
                block = next_block
                continue

            # Qt's Markdown importer gives ordinary paragraphs a 6px
            # top/bottom margin. QTextCursor.insertBlock() copies whatever
            # format the current block has, so once a document has been
            # loaded from Markdown every further Enter keeps propagating
            # (and stacking with the document's own paragraph spacing)
            # that margin, making each new line look like it has extra
            # blank space above and below it. Strip it back to 0 so a
            # block-format created by Enter never carries margins forward.
            margin_fmt = block.blockFormat()
            if margin_fmt.topMargin() != 0 or margin_fmt.bottomMargin() != 0:
                new_margin_fmt = QTextBlockFormat(margin_fmt)
                new_margin_fmt.setTopMargin(0)
                new_margin_fmt.setBottomMargin(0)
                temp_cursor.setBlockFormat(new_margin_fmt)

            block_fmt_hr = block.blockFormat()
            if block_fmt_hr.hasProperty(QTextFormat.BlockTrailingHorizontalRulerWidth):
                # Qt's own Markdown importer already recognizes "---" as a
                # thematic break and marks the (empty) block with this
                # property. Take over its rendering with our own HR_PROP so
                # the line uses the user-configurable color/thickness
                # instead of Qt's built-in style, and drop the native
                # property so Qt doesn't also draw its own rule underneath.
                new_hr_fmt = QTextBlockFormat(block_fmt_hr)
                new_hr_fmt.clearProperty(QTextFormat.BlockTrailingHorizontalRulerWidth)
                new_hr_fmt.setProperty(HR_PROP, True)
                temp_cursor.setBlockFormat(new_hr_fmt)
                block = next_block
                continue

            text_list = temp_cursor.currentList()
            is_list = text_list is not None
            if is_list:
                fmt = text_list.format()
                style = fmt.style()
                prefix = ""
                if style == QTextListFormat.Style.ListDisc or style == QTextListFormat.Style.ListCircle:
                    prefix = "• "
                elif style == QTextListFormat.Style.ListSquare:
                    prefix = "■ "
                elif style == QTextListFormat.Style.ListDecimal:
                    idx = text_list.itemNumber(block) + 1
                    prefix = f"{idx}. "
                else:
                    prefix = "• "
                    
                text_list.remove(block)
                temp_cursor.insertText(prefix)
                is_list = False
                
            block_fmt = block.blockFormat()
            
            is_code_block = False
            if block_fmt.hasProperty(QTextFormat.BackgroundBrush):
                bg = block_fmt.background().color()
                editor_bg = QColor(self.settings['editor_bg'])
                if bg.isValid() and bg != Qt.transparent and bg != editor_bg:
                    is_code_block = True

            if not is_code_block:
                frags_total = 0
                frags_code = 0
                it = block.begin()
                while not it.atEnd():
                    frag = it.fragment()
                    if frag.isValid() and frag.length() > 0:
                        frags_total += 1
                        f_fmt = frag.charFormat()
                        frag_bg = f_fmt.background().color() if f_fmt.hasProperty(QTextFormat.BackgroundBrush) else QColor(Qt.transparent)
                        editor_bg = QColor(self.settings['editor_bg'])
                        if frag_bg.isValid() and frag_bg != Qt.transparent and frag_bg != editor_bg:
                            frags_code += 1
                        else:
                            fam_list = f_fmt.fontFamilies()
                            fam = fam_list[0].lower() if fam_list else ""
                            if fam and ("courier" in fam or "mono" in fam or "consolas" in fam):
                                frags_code += 1
                    it += 1
                if frags_total > 0 and frags_total == frags_code:
                    is_code_block = True

            if is_code_block and block_fmt.hasProperty(QTextFormat.BackgroundBrush):
                block_fmt.clearBackground()
                temp_cursor.setBlockFormat(block_fmt)

            if is_code_block:
                if not (block_fmt.hasProperty(BLOCK_CODE_PROP) and block_fmt.property(BLOCK_CODE_PROP) == True):
                    block_fmt.setProperty(BLOCK_CODE_PROP, True)
                    temp_cursor.setBlockFormat(block_fmt)
            else:
                if not is_list and block_fmt.leftMargin() > 10:
                    block_fmt.setProperty(QUOTE_PROP, True)
                    block_fmt.setLeftMargin(15)
                    temp_cursor.setBlockFormat(block_fmt)
                else:
                    if block_fmt.hasProperty(QUOTE_PROP) and block_fmt.property(QUOTE_PROP) == True:
                        block_fmt.setProperty(QUOTE_PROP, False)
                        temp_cursor.setBlockFormat(block_fmt)
                
            block = next_block
            
        cursor.endEditBlock()
        
    def apply_settings_to_document(self, restore_cursor=True):
        orig_cursor = self.textCursor()
        char_updates = []
        block_updates = []
        block = self.document().firstBlock()
        
        while block.isValid():
            cursor = QTextCursor(block)
            if cursor.currentTable():
                block = block.next()
                continue
                
            block_fmt = block.blockFormat()
            level = block_fmt.headingLevel()
            is_quote = block_fmt.hasProperty(QUOTE_PROP) and block_fmt.property(QUOTE_PROP) == True
            is_block_code = block_fmt.hasProperty(BLOCK_CODE_PROP) and block_fmt.property(BLOCK_CODE_PROP) == True
            
            if is_block_code:
                current_bg = block_fmt.background().color() if block_fmt.hasProperty(QTextFormat.BackgroundBrush) else QColor(Qt.transparent)
                if current_bg != QColor(self.settings['code_bg']):
                    new_block_fmt = QTextBlockFormat(block_fmt)
                    new_block_fmt.setBackground(QColor(self.settings['code_bg']))
                    block_updates.append((block.position(), new_block_fmt))
            else:
                if block_fmt.hasProperty(QTextFormat.BackgroundBrush) and block_fmt.background().color() == QColor(self.settings['code_bg']):
                    new_block_fmt = QTextBlockFormat(block_fmt)
                    new_block_fmt.setBackground(Qt.transparent)
                    block_updates.append((block.position(), new_block_fmt))
                    
            it = block.begin()
            while not it.atEnd():
                frag = it.fragment()
                if frag.isValid() and frag.length() > 0:
                    fmt = QTextCharFormat(frag.charFormat())
                    changed = False
                    
                    is_code = (fmt.hasProperty(CODE_PROP) and fmt.property(CODE_PROP) == True) or is_block_code
                    fam_list = fmt.fontFamilies()
                    fam = fam_list[0] if fam_list else ""
                    if not is_code and fam:
                        if "mono" in fam.lower() or "consolas" in fam.lower() or "courier" in fam.lower():
                            is_code = True
                            fmt.setProperty(CODE_PROP, True)
                            
                    is_anchor = fmt.isAnchor()
                    is_bold = (fmt.fontWeight() == QFont.Bold)
                    is_italic = fmt.fontItalic()
                    is_underline = fmt.fontUnderline()
                    
                    if is_code:
                        fmt.setForeground(QColor(self.settings['code']))
                        fmt.setFontFamilies(["Consolas"])
                        fmt.setProperty(CODE_PROP, True)
                        if is_block_code:
                            fmt.setBackground(Qt.transparent)
                        else:
                            fmt.setBackground(QColor(self.settings['code_bg']))
                        changed = True
                    elif is_anchor:
                        fmt.setForeground(QColor(self.settings['link']))
                        fmt.setFontUnderline(self.settings.get("link_underline", True))
                        changed = True
                    elif level > 0:
                        fmt.setForeground(QColor(self.settings[f"h{level}"]))
                        size = self.settings.get(f"h{level}_size", 0)
                        if size == 0: size = self.settings["font_size"]
                        fmt.setFontFamilies([self.settings['font_family']])
                        fmt.setFontPointSize(size)
                        fmt.setFontWeight(QFont.Bold)
                        changed = True
                    elif is_quote:
                        fmt.setForeground(QColor(self.settings['quote']))
                        size = self.settings.get('quote_size', 0)
                        if size == 0: size = self.settings["font_size"]
                        fmt.setFontFamilies([self.settings['font_family']])
                        fmt.setFontPointSize(size)
                        fmt.setFontItalic(True)
                        changed = True
                    else:
                        fmt.setForeground(QColor(self.settings['editor_text']))
                        fmt.setFontFamilies([self.settings['font_family']])
                        fmt.setFontPointSize(self.settings['font_size'])
                        changed = True
                        if is_bold:
                            fmt.setForeground(QColor(self.settings['bold']))
                        if is_italic:
                            fmt.setForeground(QColor(self.settings['italic']))
                        if is_underline:
                            fmt.setForeground(QColor(self.settings['underline']))
                            
                    if changed:
                        char_updates.append((frag.position(), frag.length(), fmt))
                it += 1
            block = block.next()
            
        cur = QTextCursor(self.document())
        cur.beginEditBlock()
        for pos, fmt in block_updates:
            cur.setPosition(pos)
            cur.setBlockFormat(fmt)
        for pos, length, fmt in char_updates:
            cur.setPosition(pos)
            cur.setPosition(pos + length, QTextCursor.KeepAnchor)
            cur.setCharFormat(fmt)
        cur.endEditBlock()

        if restore_cursor:
            self.setTextCursor(orig_cursor)
            self.highlight_current_line()

    def style_tables(self):
        cursor = QTextCursor(self.document())
        cursor.movePosition(QTextCursor.Start)
        while not cursor.atEnd():
            table = cursor.currentTable()
            if table:
                self.apply_table_style(table)
                cursor.setPosition(table.lastPosition() + 1, QTextCursor.MoveAnchor)
            else:
                if not cursor.movePosition(QTextCursor.NextBlock): break

    def apply_table_style(self, table):
        rows = table.rows()
        cols = table.columns()

        table_fmt = table.format()
        # Qt requires a real (editable) paragraph immediately before and
        # after every table - there's nowhere else to put the cursor to
        # type outside it. With zero margin that paragraph sits pixel-tight
        # against the table's first/last row, so on screen (and in the line
        # number gutter) it reads as if that row got an extra number
        # instead of "table row + separate blank line right above/below
        # it". A small top/bottom margin on the table's own frame just
        # gives that line breathing room so it visually reads as its own
        # line, without changing what's actually in the document.
        table_fmt.setTopMargin(8)
        table_fmt.setBottomMargin(8)

        # Qt only applies the column width constraints that were set when
        # the table was first inserted; adding/removing a row or column
        # afterward (Table Editor, undo/redo, ...) does NOT extend or
        # shrink that list to match the new column count. Any column left
        # without an explicit constraint then collapses to near-zero, and
        # anything typed into it wraps one letter per line, ballooning the
        # row height. Re-apply a constraint to every column the table
        # actually has right now, every time this runs, so the table can
        # never end up in that state. VariableLength (rather than a fixed
        # percentage share) tells Qt's layout to size each column to fit
        # its own content, re-measured on every layout pass - so columns
        # naturally widen/narrow with the text typed into them instead of
        # being locked to an equal split of the table width.
        table_fmt.setColumnWidthConstraints(
            [QTextLength(QTextLength.VariableLength, 0)] * cols
        )
        table.setFormat(table_fmt)

        header_bg = QColor(self.settings["table_header_bg"])
        header_text = QColor(self.settings["table_header_text"])
        row1_bg = QColor(self.settings["table_row1_bg"])
        row2_bg = QColor(self.settings["table_row2_bg"])

        align_map = {
            "left": Qt.AlignLeft,
            "center": Qt.AlignHCenter,
            "right": Qt.AlignRight,
        }
        # Alignment is per-table (set from Edit Table, not the app-wide
        # Settings dialog). Fall back to the old global default for tables
        # that don't have their own value yet (e.g. freshly opened files).
        if table_fmt.hasProperty(TABLE_HEADER_ALIGN_PROP):
            header_align_key = table_fmt.property(TABLE_HEADER_ALIGN_PROP)
        else:
            header_align_key = self.settings.get("table_header_align", "left")
        if table_fmt.hasProperty(TABLE_ROW_ALIGN_PROP):
            row_align_key = table_fmt.property(TABLE_ROW_ALIGN_PROP)
        else:
            row_align_key = self.settings.get("table_row_align", "left")
        header_align = align_map.get(header_align_key, Qt.AlignLeft)
        row_align = align_map.get(row_align_key, Qt.AlignLeft)

        for r in range(rows):
            for c in range(cols):
                cell = table.cellAt(r, c)
                fmt = cell.format()
                if r == 0:
                    fmt.setBackground(header_bg)
                    fmt.setForeground(header_text)
                    fmt.setFontWeight(QFont.Bold)
                else:
                    fmt.setBackground(row1_bg if r % 2 == 1 else row2_bg)
                    fmt.setForeground(QColor(self.settings['editor_text']))
                    fmt.setFontWeight(QFont.Normal)
                cell.setFormat(fmt)

                # Alignment lives on the paragraph(s) inside the cell, not
                # on the cell's char format, so it has to be applied via a
                # cursor over each block the cell contains (usually one,
                # but a cell can hold several paragraphs).
                align = header_align if r == 0 else row_align
                it = cell.begin()
                while not it.atEnd():
                    blk = it.currentBlock()
                    if blk.isValid():
                        blk_cursor = QTextCursor(blk)
                        blk_fmt = blk_cursor.blockFormat()
                        if blk_fmt.alignment() != align:
                            blk_fmt.setAlignment(align)
                            blk_cursor.setBlockFormat(blk_fmt)
                    it += 1


class EditorTabs(QTabWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        # Qt's built-in close-button subcontrol is disabled (see the
        # "image: none" rule in apply_app_theme) because styling its
        # default glyph reliably via QSS across platforms/styles isn't
        # possible - so tab-closing is handled with our own themed
        # QToolButton per tab (see add_close_button) instead.
        self.setTabsClosable(False)
        self.setMovable(True)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)
        
        self.plus_btn = QToolButton(self)
        self.plus_btn.setText("+")
        self.plus_btn.setToolTip("New Tab")
        self.plus_btn.setAutoRaise(True)
        self.setCornerWidget(self.plus_btn, Qt.TopRightCorner)

    def add_close_button(self, editor):
        """Create and attach a themed SVG 'x' close button for the tab
        hosting `editor`. Looked up by widget identity (via indexOf) at
        click time, rather than a captured index, so it keeps closing the
        right tab even after other tabs are reordered/closed."""
        btn = QToolButton(self)
        btn.setAutoRaise(True)
        btn.setToolTip("Close Tab")
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFixedSize(18, 18)
        btn.setIconSize(QSize(12, 12))
        btn.setStyleSheet(
            "QToolButton { background: transparent; border: none; border-radius: 2px; }"
            "QToolButton:hover { background: #ff4d4d; }"
        )
        btn.clicked.connect(lambda checked=False, ed=editor: self.window().close_tab(self.indexOf(ed)))
        self.update_close_button_icon(btn)
        self.tabBar().setTabButton(self.indexOf(editor), QTabBar.RightSide, btn)
        return btn

    def update_close_button_icon(self, btn):
        window = self.window()
        color = window.settings.get("app_text", "#d4d4d4") if window else "#d4d4d4"
        btn.setIcon(make_svg_icon("close", color, size=14))

    def refresh_close_button_icons(self):
        """Re-tint every tab's close icon - call after the theme changes."""
        for i in range(self.count()):
            btn = self.tabBar().tabButton(i, QTabBar.RightSide)
            if btn is not None:
                self.update_close_button_icon(btn)

    def show_context_menu(self, pos):
        index = self.tabBar().tabAt(self.tabBar().mapFrom(self, pos))
        
        menu = QMenu(self)
        action_new = menu.addAction("New Tab")
        
        if index != -1:
            menu.addSeparator()
            action_close = menu.addAction("Close Tab")
            action_dup = menu.addAction("Duplicate Tab")
            menu.addSeparator()
            action_close_others = menu.addAction("Close Other Tabs")
            action_close_all = menu.addAction("Close All Tabs")
            
        action = menu.exec(self.mapToGlobal(pos))
        if action == action_new:
            self.window().new_tab()
        elif index != -1:
            if action == action_close:
                self.window().close_tab(index)
            elif action == action_dup:
                self.window().duplicate_tab(index)
            elif action == action_close_others:
                self.window().close_other_tabs(index)
            elif action == action_close_all:
                self.window().close_all_tabs()


class SettingsDialog(QDialog):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings.copy()
        self.setWindowTitle("Style Configuration - MPad++")
        self.setMinimumWidth(450)
        self.setMinimumHeight(500)
        
        main_layout = QVBoxLayout(self)
        
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        layout = QFormLayout(scroll_content)
        
        self.color_buttons = {}
        self.size_spins = {}

        self.add_color_picker(layout, "App Background", "app_bg")
        self.add_color_picker(layout, "Editor Background", "editor_bg")
        self.add_color_picker(layout, "Normal Text", "editor_text")
        self.add_color_picker(layout, "Current Line Highlight", "current_line_highlight")

        font_btn = QPushButton("Select font and size (global)")
        font_btn.clicked.connect(self.choose_font)
        layout.addRow("Global Font:", font_btn)

        elements = {
            "h1": ("Header H1", "h1_size", 72),
            "h2": ("Header H2", "h2_size", 72),
            "h3": ("Header H3", "h3_size", 72),
            "h4": ("Header H4", "h4_size", 72),
            "h5": ("Header H5", "h5_size", 72),
            "h6": ("Header H6", "h6_size", 72),
            "bold": ("Bold", "bold_size", 72),
            "italic": ("Italic", "italic_size", 72),
            "underline": ("Underline", "underline_size", 72),
            "code": ("Code (font)", "code_size", 72),
            "code_bg": ("Code (background)", None, 0),
            "quote": ("Quote (text)", "quote_size", 72),
            "link": ("Hyperlink (text)", "link_size", 72)
        }
        
        for key, (label_text, size_key, max_size) in elements.items():
            self.add_format_setting(layout, label_text, key, size_key, max_size)

        self.add_color_picker(layout, "Quote (line)", "quote_line_color")
        
        self.quote_line_width_spin = QSpinBox()
        self.quote_line_width_spin.setRange(1, 20)
        self.quote_line_width_spin.setValue(self.settings.get("quote_line_width", 3))
        self.quote_line_width_spin.setSuffix(" px")
        layout.addRow("Quote line thickness:", self.quote_line_width_spin)
        
        self.underline_check = QCheckBox()
        self.underline_check.setChecked(self.settings.get("link_underline", True))
        layout.addRow("Underline hyperlink:", self.underline_check)

        self.add_color_picker(layout, "Horizontal Line", "hr_color")

        self.hr_thickness_spin = QSpinBox()
        self.hr_thickness_spin.setRange(1, 20)
        self.hr_thickness_spin.setValue(self.settings.get("hr_thickness", 2))
        self.hr_thickness_spin.setSuffix(" px")
        layout.addRow("Horizontal line thickness:", self.hr_thickness_spin)

        layout.addRow(QLabel("--- Table Colors ---"))
        self.add_color_picker(layout, "Header (background)", "table_header_bg")
        self.add_color_picker(layout, "Header (text)", "table_header_text")
        self.add_color_picker(layout, "Row 1 (background)", "table_row1_bg")
        self.add_color_picker(layout, "Row 2 (background)", "table_row2_bg")

        # Text alignment moved to the per-table "Edit Table" dialog (see
        # MainWindow.open_table_editor()) so each table can set its own,
        # instead of one alignment for every table in every document.
        self.align_combos = {}

        layout.addRow(QLabel("--- Tab Colors ---"))
        self.add_color_picker(layout, "Active tab (background)", "tab_active_bg")
        self.add_color_picker(layout, "Inactive tab (background)", "tab_inactive_bg")
        self.add_color_picker(layout, "Active tab bar", "tab_active_bar_color")

        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll)
        
        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        main_layout.addWidget(btn_box)
        
        self.setLayout(main_layout)

    def add_color_picker(self, layout, label_text, color_key):
        btn = QPushButton()
        btn.setFixedWidth(100)
        btn.setStyleSheet(f"background-color: {self.settings[color_key]};")
        btn.clicked.connect(lambda _, k=color_key, b=btn: self.pick_color(k, b))
        layout.addRow(label_text, btn)
        self.color_buttons[color_key] = btn

    def add_format_setting(self, layout, label_text, color_key, size_key=None, max_size=72):
        btn = QPushButton()
        btn.setFixedWidth(100)
        btn.setStyleSheet(f"background-color: {self.settings[color_key]};")
        btn.clicked.connect(lambda _, k=color_key, b=btn: self.pick_color(k, b))
        
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0,0,0,0)
        row_layout.addWidget(btn)
        
        if size_key is not None:
            spin = QSpinBox()
            spin.setRange(0, max_size)
            spin.setValue(self.settings.get(size_key, 0))
            spin.setSpecialValueText("Default")
            row_layout.addWidget(QLabel("Size:"))
            row_layout.addWidget(spin)
            self.size_spins[size_key] = spin
            
        layout.addRow(label_text, row_widget)

    def add_alignment_setting(self, layout, label_text, align_key):
        combo = QComboBox()
        combo.addItem("Left", "left")
        combo.addItem("Center", "center")
        combo.addItem("Right", "right")
        current = self.settings.get(align_key, "left")
        idx = combo.findData(current)
        combo.setCurrentIndex(idx if idx >= 0 else 0)
        layout.addRow(label_text, combo)
        self.align_combos[align_key] = combo

    def pick_color(self, key, btn):
        color = QColorDialog.getColor(QColor(self.settings[key]))
        if color.isValid():
            self.settings[key] = color.name()
            btn.setStyleSheet(f"background-color: {color.name()};")

    def choose_font(self):
        dialog = QFontDialog(self)
        dialog.setCurrentFont(QFont(self.settings["font_family"], self.settings["font_size"]))
        if dialog.exec():
            font = dialog.currentFont()
            self.settings["font_family"] = font.family()
            self.settings["font_size"] = font.pointSize()

    def accept(self):
        for key, spin in self.size_spins.items():
            self.settings[key] = spin.value()
        self.settings["link_underline"] = self.underline_check.isChecked()
        self.settings["quote_line_width"] = self.quote_line_width_spin.value()
        self.settings["hr_thickness"] = self.hr_thickness_spin.value()
        for key, combo in self.align_combos.items():
            self.settings[key] = combo.currentData()
        super().accept()

    def get_settings(self):
        return self.settings


class PreferencesDialog(QDialog):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings.copy()
        self.setWindowTitle("Preferences - MPad++")
        self.setMinimumWidth(400)

        outer_layout = QVBoxLayout(self)

        self.tabs = QTabWidget()
        outer_layout.addWidget(self.tabs)

        # --- General tab ---
        general_tab = QWidget()
        layout = QFormLayout(general_tab)

        line_break_widget = QWidget()
        line_break_layout = QVBoxLayout(line_break_widget)
        line_break_layout.setContentsMargins(0, 0, 0, 0)

        self.line_break_group = QButtonGroup(line_break_widget)
        self.line_break_radios = {}

        line_break_options = [
            ("br", "<br>"),
            ("double_space", "[double space]"),
            ("backslash", "\\ and enter"),
        ]
        current_line_break = self.settings.get("line_break_style", "double_space")
        for value, label_text in line_break_options:
            radio = QRadioButton(label_text)
            if value == current_line_break:
                radio.setChecked(True)
            self.line_break_group.addButton(radio)
            self.line_break_radios[value] = radio
            line_break_layout.addWidget(radio)

        layout.addRow("New line (character):", line_break_widget)

        # Default table text alignment - applies to any table that hasn't
        # been given its own alignment via that table's "Edit Table" dialog
        # (see MainWindow.open_table_editor()), so this is the app-wide
        # default while individual tables can still opt out and pick their
        # own alignment locally.
        self.align_combos = {}

        def make_align_combo(settings_key):
            combo = QComboBox()
            combo.addItem("Left", "left")
            combo.addItem("Center", "center")
            combo.addItem("Right", "right")
            current = self.settings.get(settings_key, "left")
            idx = combo.findData(current)
            combo.setCurrentIndex(idx if idx >= 0 else 0)
            self.align_combos[settings_key] = combo
            return combo

        layout.addRow("Default first row alignment:", make_align_combo("table_header_align"))
        layout.addRow("Default other rows alignment:", make_align_combo("table_row_align"))

        self.tabs.addTab(general_tab, "General")

        # --- Spell Check tab ---
        spell_tab = QWidget()
        spell_layout = QFormLayout(spell_tab)

        # --- Spell check languages (multi-select via checkboxes) ---
        lang_widget = QWidget()
        lang_layout = QVBoxLayout(lang_widget)
        lang_layout.setContentsMargins(0, 0, 0, 0)
        lang_scroll = QScrollArea()
        lang_scroll.setWidgetResizable(True)
        lang_scroll.setFixedHeight(150)
        lang_inner = QWidget()
        lang_inner_layout = QVBoxLayout(lang_inner)
        lang_inner_layout.setContentsMargins(4, 4, 4, 4)
        lang_scroll.setWidget(lang_inner)
        lang_layout.addWidget(lang_scroll)

        self.spell_lang_checks = {}
        active_langs = set(self.settings.get("spellcheck_langs", ["pl_PL"]))
        for lang_name, lang_code in SPELLCHECK_LANGUAGES:
            check = QCheckBox(lang_name)
            check.setChecked(lang_code in active_langs)
            self.spell_lang_checks[lang_code] = check
            lang_inner_layout.addWidget(check)
        lang_inner_layout.addStretch()

        if phunspell is None:
            lang_widget.setEnabled(False)
            lang_widget.setToolTip("Requires the 'phunspell' package: pip install phunspell")

        spell_layout.addRow("Spell check languages:", lang_widget)

        # --- Personal dictionary (custom words added via the editor's
        # right-click "Add to Dictionary") ---
        dict_widget = QWidget()
        dict_layout = QVBoxLayout(dict_widget)
        dict_layout.setContentsMargins(0, 0, 0, 0)

        self.custom_word_search = QLineEdit()
        self.custom_word_search.setPlaceholderText("Search words...")
        self.custom_word_search.textChanged.connect(self._filter_custom_words)
        dict_layout.addWidget(self.custom_word_search)

        self.custom_words_list = QListWidget()
        self.custom_words_list.setFixedHeight(120)
        self.custom_words_list.setSelectionMode(QListWidget.ExtendedSelection)
        for word in sorted(self.settings.get("spellcheck_custom_words", [])):
            self.custom_words_list.addItem(QListWidgetItem(word))
        dict_layout.addWidget(self.custom_words_list)

        dict_add_row = QHBoxLayout()
        self.custom_word_input = QLineEdit()
        self.custom_word_input.setPlaceholderText("New word...")
        add_word_btn = QPushButton("Add")
        add_word_btn.clicked.connect(self._add_custom_word)
        self.custom_word_input.returnPressed.connect(self._add_custom_word)
        dict_add_row.addWidget(self.custom_word_input)
        dict_add_row.addWidget(add_word_btn)
        dict_layout.addLayout(dict_add_row)

        remove_word_btn = QPushButton("Remove selected")
        remove_word_btn.clicked.connect(self._remove_selected_custom_words)
        dict_layout.addWidget(remove_word_btn)

        if phunspell is None:
            dict_widget.setEnabled(False)

        spell_layout.addRow("Personal dictionary:", dict_widget)

        self.tabs.addTab(spell_tab, "Spell Check")

        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        outer_layout.addWidget(btn_box)

    def _add_custom_word(self):
        word = self.custom_word_input.text().strip()
        if not word:
            return
        existing = [self.custom_words_list.item(i).text().lower()
                    for i in range(self.custom_words_list.count())]
        if word.lower() not in existing:
            self.custom_words_list.addItem(QListWidgetItem(word))
        self.custom_word_input.clear()

    def _remove_selected_custom_words(self):
        for item in self.custom_words_list.selectedItems():
            self.custom_words_list.takeItem(self.custom_words_list.row(item))

    def _filter_custom_words(self, text):
        """Hides list rows that don't contain the search text (case-insensitive),
        without touching the underlying items, so removal/adding still works
        normally on the full (unfiltered) set."""
        query = text.strip().lower()
        for i in range(self.custom_words_list.count()):
            item = self.custom_words_list.item(i)
            item.setHidden(bool(query) and query not in item.text().lower())

    def accept(self):
        for value, radio in self.line_break_radios.items():
            if radio.isChecked():
                self.settings["line_break_style"] = value
                break

        for key, combo in self.align_combos.items():
            self.settings[key] = combo.currentData()

        selected_langs = [code for code, check in self.spell_lang_checks.items() if check.isChecked()]
        if selected_langs:
            self.settings["spellcheck_langs"] = selected_langs

        self.settings["spellcheck_custom_words"] = sorted(
            self.custom_words_list.item(i).text().lower() for i in range(self.custom_words_list.count())
        )
        super().accept()

    def get_settings(self):
        return self.settings


class LinkDialog(QDialog):
    def __init__(self, selected_text, selected_url="https://", parent=None, allow_remove=False):
        super().__init__(parent)
        self.setWindowTitle("Hyperlink - MPad++")
        # Wide and tall enough that a normal (or long) URL/display text is
        # fully visible - wrapped across a couple of lines - instead of
        # being scrolled/clipped inside a single-line field.
        self.setMinimumWidth(640)
        self.setMinimumHeight(340)
        self.resize(680, 380)
        layout = QFormLayout(self)

        # Multi-line boxes so long values wrap onto several visible lines
        # instead of scrolling sideways inside a thin bar. These still
        # represent single-line values though, so Tab moves focus instead
        # of indenting, and any stray Enter presses are stripped back out
        # in get_data() rather than ending up inside the link's text/href.
        self.text_input = QPlainTextEdit(selected_text)
        self.text_input.setTabChangesFocus(True)
        self.text_input.setMinimumHeight(90)

        self.url_input = QPlainTextEdit(selected_url)
        self.url_input.setTabChangesFocus(True)
        self.url_input.setMinimumHeight(90)
        # Make sure editing (or re-reading) an existing link always starts
        # showing its beginning rather than wherever the field happened to
        # scroll to.
        url_cursor = self.url_input.textCursor()
        url_cursor.movePosition(QTextCursor.Start)
        self.url_input.setTextCursor(url_cursor)
        self.url_input.selectAll()

        layout.addRow("Display text:", self.text_input)
        layout.addRow("URL Address:", self.url_input)

        self._removed = False

        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        if allow_remove:
            remove_btn = btn_box.addButton("Remove Link", QDialogButtonBox.DestructiveRole)
            remove_btn.clicked.connect(self._on_remove)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addRow(btn_box)

    def _on_remove(self):
        self._removed = True
        self.accept()

    def is_removed(self):
        return self._removed

    def get_data(self):
        # Collapse any Enter presses back to spaces - these boxes are for
        # comfortable editing of single-line values, not real multi-line
        # text, so a stray newline should never end up inside the anchor's
        # display text or href.
        text = " ".join(self.text_input.toPlainText().splitlines()).strip()
        url = " ".join(self.url_input.toPlainText().splitlines()).strip()
        return text, url


class TableDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Insert Table - MPad++")
        layout = QFormLayout(self)

        self.rows_spin = QSpinBox()
        self.rows_spin.setRange(1, 50)
        self.rows_spin.setValue(3)
        
        self.cols_spin = QSpinBox()
        self.cols_spin.setRange(1, 20)
        self.cols_spin.setValue(3)

        layout.addRow("Number of rows:", self.rows_spin)
        layout.addRow("Number of columns:", self.cols_spin)

        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addRow(btn_box)

    def get_data(self):
        return self.rows_spin.value(), self.cols_spin.value()


class FindReplaceDialog(QDialog):
    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self.setWindowTitle("Find & Replace - MPad++")
        self.setMinimumWidth(380)
        # Non-modal "tool" style: stays on top of the editor without
        # blocking interaction with it, like the find bar in most editors.
        self.setWindowFlags(self.windowFlags() | Qt.Tool)

        layout = QFormLayout(self)

        self.find_input = QLineEdit()
        self.find_input.returnPressed.connect(self.find_next)
        layout.addRow("Find:", self.find_input)

        self.replace_input = QLineEdit()
        self.replace_input.returnPressed.connect(self.replace_current)
        layout.addRow("Replace with:", self.replace_input)

        self.case_check = QCheckBox("Case sensitive")
        layout.addRow("", self.case_check)

        find_btn_row = QWidget()
        find_btn_layout = QHBoxLayout(find_btn_row)
        find_btn_layout.setContentsMargins(0, 0, 0, 0)
        self.btn_prev = QPushButton("Find Previous")
        self.btn_prev.clicked.connect(self.find_previous)
        find_btn_layout.addWidget(self.btn_prev)
        self.btn_next = QPushButton("Find Next")
        self.btn_next.clicked.connect(self.find_next)
        find_btn_layout.addWidget(self.btn_next)
        layout.addRow(find_btn_row)

        replace_btn_row = QWidget()
        replace_btn_layout = QHBoxLayout(replace_btn_row)
        replace_btn_layout.setContentsMargins(0, 0, 0, 0)
        self.btn_replace = QPushButton("Replace")
        self.btn_replace.clicked.connect(self.replace_current)
        replace_btn_layout.addWidget(self.btn_replace)
        self.btn_replace_all = QPushButton("Replace All")
        self.btn_replace_all.clicked.connect(self.replace_all)
        replace_btn_layout.addWidget(self.btn_replace_all)
        layout.addRow(replace_btn_row)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #999;")
        layout.addRow(self.status_label)

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.close)
        layout.addRow(btn_close)

    def get_editor(self):
        return self.main_window.get_editor()

    def _flags(self, backward=False):
        flags = QTextDocument.FindFlags()
        if self.case_check.isChecked():
            flags |= QTextDocument.FindCaseSensitively
        if backward:
            flags |= QTextDocument.FindBackward
        return flags

    def _find(self, backward):
        editor = self.get_editor()
        if not editor:
            return
        text = self.find_input.text()
        if not text:
            self.status_label.setText("")
            return
        found = editor.find(text, self._flags(backward))
        if not found:
            # Wrap around: retry once from the start (or end, for backward
            # searches) instead of leaving the user stuck at the boundary.
            cursor = editor.textCursor()
            cursor.movePosition(QTextCursor.End if backward else QTextCursor.Start)
            editor.setTextCursor(cursor)
            found = editor.find(text, self._flags(backward))
        if found:
            self.status_label.setText("")
        else:
            self.status_label.setText("Phrase not found")

    def find_next(self):
        self._find(backward=False)

    def find_previous(self):
        self._find(backward=True)

    def replace_current(self):
        editor = self.get_editor()
        if not editor:
            return
        text = self.find_input.text()
        if not text:
            return
        cursor = editor.textCursor()
        selected = cursor.selectedText()
        if self.case_check.isChecked():
            matches = (selected == text)
        else:
            matches = (selected.lower() == text.lower())

        if cursor.hasSelection() and matches:
            cursor.insertText(self.replace_input.text())
            editor.setTextCursor(cursor)

        self.find_next()

    def replace_all(self):
        editor = self.get_editor()
        if not editor:
            return
        text = self.find_input.text()
        if not text:
            return
        replace_text = self.replace_input.text()
        flags = self._flags(backward=False)

        cursor = editor.textCursor()
        cursor.beginEditBlock()

        start_cursor = QTextCursor(editor.document())
        start_cursor.movePosition(QTextCursor.Start)
        editor.setTextCursor(start_cursor)

        count = 0
        while editor.find(text, flags):
            match_cursor = editor.textCursor()
            match_cursor.insertText(replace_text)
            editor.setTextCursor(match_cursor)
            count += 1

        cursor.endEditBlock()
        self.status_label.setText(f"Replaced {count} occurrence(s)" if count else "Phrase not found")

    def showEvent(self, event):
        super().showEvent(event)
        editor = self.get_editor()
        if editor:
            selected = editor.textCursor().selectedText()
            if selected and "\u2029" not in selected:
                self.find_input.setText(selected)
        self.find_input.setFocus()
        self.find_input.selectAll()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MPad++")
        self.resize(800, 600)
        
        icon_path = os.path.join("icons", "notepad_yellow_icon.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.settings_file = "mpad_settings.json"
        self.settings = self.load_settings()

        self.spell_manager = SpellCheckManager(self.settings, self)
        if self.spell_manager.enabled:
            for lang_code in self.spell_manager.lang_codes:
                self.spell_manager._ensure_loaded(lang_code)

        self.apply_app_theme()

        self.tab_widget = EditorTabs(self)
        self.tab_widget.tabCloseRequested.connect(self.close_tab)
        self.tab_widget.currentChanged.connect(self.on_tab_changed)
        self.tab_widget.plus_btn.clicked.connect(lambda: self.new_tab())
        
        container = QWidget()
        container.setObjectName("TopGapContainer")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 3, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.tab_widget)
        self.setCentralWidget(container)
        
        self.find_dialog = None

        self.create_menu()
        self.create_toolbar()
        self.create_shortcuts()
        
        self.new_tab()

    def load_settings(self):
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    saved_settings = json.load(f)
                    defaults = DEFAULT_SETTINGS.copy()
                    defaults.update(saved_settings)
                    return defaults
            except:
                pass
        return DEFAULT_SETTINGS.copy()

    def save_settings(self):
        with open(self.settings_file, 'w', encoding='utf-8') as f:
            json.dump(self.settings, f, indent=4)

    def apply_app_theme(self):
        self.setStyleSheet(f"""
            QMainWindow {{ background-color: {self.settings['app_bg']}; }}
            #TopGapContainer {{ background-color: {self.settings['app_bg']}; }}
            QTabWidget::pane {{ border: none; background: {self.settings['editor_bg']}; }}
            QTabBar::tab {{ background: {self.settings['tab_inactive_bg']}; color: #888; padding: 5px 12px 8px 12px; border: 1px solid #1e1e1e; border-top: 3px solid transparent; }}
            QTabBar::tab:selected {{ background: {self.settings['tab_active_bg']}; color: {self.settings['app_text']}; border-bottom: none; border-top: 3px solid {self.settings['tab_active_bar_color']}; }}
            QTabBar::tab:hover:!selected {{ background: #383838; }}
            QToolBar {{ background-color: #2d2d2d; border: none; spacing: 2px; }}
            QToolButton {{ background-color: #3e3e42; color: {self.settings['app_text']}; border: 1px solid #555; padding: 5px; border-radius: 3px; }}
            QToolButton:hover {{ background-color: #505050; }}
            QToolButton:checked {{ background-color: #007acc; border: 1px solid #007acc; }}
            QStatusBar {{ background-color: #2d2d2d; color: #ccc; }}
            QMenuBar {{ background-color: #2d2d2d; color: {self.settings['app_text']}; }}
            QMenuBar::item:selected {{ background-color: #505050; }}
            QMenu {{ background-color: #2d2d2d; color: {self.settings['app_text']}; border: 1px solid #555; }}
            QMenu::item:selected {{ background-color: #505050; }}
        """)

    def create_menu(self):
        menubar = self.menuBar()
        file_menu = menubar.addMenu("File")
        
        open_action = QAction("Open", self)
        open_action.setShortcut(QKeySequence.Open)
        open_action.triggered.connect(lambda: self.open_file_dialog(False))
        file_menu.addAction(open_action)
        
        open_new_tab_action = QAction("Open in New Tab", self)
        open_new_tab_action.triggered.connect(lambda: self.open_file_dialog(True))
        file_menu.addAction(open_new_tab_action)
        
        new_tab_action = QAction("New Tab", self)
        new_tab_action.setShortcut(QKeySequence.New)
        new_tab_action.triggered.connect(self.new_tab)
        file_menu.addAction(new_tab_action)
        
        file_menu.addSeparator()
        
        save_action = QAction("Save", self)
        save_action.setShortcut(QKeySequence.Save)
        save_action.triggered.connect(self.save_file)
        file_menu.addAction(save_action)
        
        save_as_action = QAction("Save As", self)
        save_as_action.setShortcut(QKeySequence.SaveAs)
        save_as_action.triggered.connect(self.save_as_file)
        file_menu.addAction(save_as_action)
        
        edit_menu = menubar.addMenu("Edit")

        cut_action = QAction("Cut", self)
        cut_action.setShortcut(QKeySequence.Cut)
        cut_action.triggered.connect(self.edit_cut)
        edit_menu.addAction(cut_action)

        copy_action = QAction("Copy", self)
        copy_action.setShortcut(QKeySequence.Copy)
        copy_action.triggered.connect(self.edit_copy)
        edit_menu.addAction(copy_action)

        paste_action = QAction("Paste", self)
        paste_action.setShortcut(QKeySequence.Paste)
        paste_action.triggered.connect(self.edit_paste)
        edit_menu.addAction(paste_action)

        edit_menu.addSeparator()

        find_replace_action = QAction("Find && Replace", self)
        find_replace_action.setShortcut(QKeySequence("Ctrl+F"))
        find_replace_action.triggered.connect(self.open_find_replace)
        edit_menu.addAction(find_replace_action)

        view_menu = menubar.addMenu("View")
        self.view_action_group = QActionGroup(self)
        self.view_action_group.setExclusive(True)

        self.act_view_formatted = QAction("Formatted", self)
        self.act_view_formatted.setCheckable(True)
        self.act_view_formatted.setChecked(True)
        self.act_view_formatted.triggered.connect(lambda: self.set_view_mode("formatted"))
        self.view_action_group.addAction(self.act_view_formatted)
        view_menu.addAction(self.act_view_formatted)

        self.act_view_plain = QAction("Plain text", self)
        self.act_view_plain.setCheckable(True)
        self.act_view_plain.triggered.connect(lambda: self.set_view_mode("plain"))
        self.view_action_group.addAction(self.act_view_plain)
        view_menu.addAction(self.act_view_plain)

        settings_menu = menubar.addMenu("Settings")
        config_action = QAction("Configure Styles", self)
        config_action.triggered.connect(self.open_settings)
        settings_menu.addAction(config_action)

        prefs_action = QAction("Preferences", self)
        prefs_action.triggered.connect(self.open_preferences)
        settings_menu.addAction(prefs_action)

        settings_menu.addSeparator()

        self.act_spellcheck_menu = QAction("Spell Check", self)
        self.act_spellcheck_menu.setCheckable(True)
        self.act_spellcheck_menu.setChecked(self.settings.get("spellcheck_enabled", False))
        self.act_spellcheck_menu.triggered.connect(self.toggle_spellcheck)
        settings_menu.addAction(self.act_spellcheck_menu)

        if not self.spell_manager.available:
            self.act_spellcheck_menu.setEnabled(False)
            self.act_spellcheck_menu.setToolTip(
                "Spell checking requires the 'phunspell' package.\nInstall it with: pip install phunspell")

    def create_toolbar(self):
        toolbar = QToolBar("Formatting")
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.addToolBar(toolbar)
        
        self.toolbar_spacer = QWidget()
        self.toolbar_spacer.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        toolbar.addWidget(self.toolbar_spacer)

        self.h_actions = {}
        for i in range(1, 7):
            action = QAction(f"H{i}", self)
            action.setCheckable(True)
            action.triggered.connect(lambda checked, x=i: self.toggle_heading(x))
            toolbar.addAction(action)
            self.h_actions[i] = action

        toolbar.addSeparator()

        self.act_bold = QAction("", self); self.act_bold.setCheckable(True)
        self.act_bold.setToolTip("Bold")
        self.act_bold.triggered.connect(self.toggle_bold)
        toolbar.addAction(self.act_bold)

        self.act_italic = QAction("", self); self.act_italic.setCheckable(True)
        self.act_italic.setToolTip("Italic")
        self.act_italic.triggered.connect(self.toggle_italic)
        toolbar.addAction(self.act_italic)

        self.act_underline = QAction("", self); self.act_underline.setCheckable(True)
        self.act_underline.setToolTip("Underline")
        self.act_underline.triggered.connect(self.toggle_underline)
        toolbar.addAction(self.act_underline)

        self.act_code = QAction("", self); self.act_code.setCheckable(True)
        self.act_code.setToolTip("Inline code")
        self.act_code.triggered.connect(self.toggle_code)
        toolbar.addAction(self.act_code)

        self.act_quote = QAction("", self); self.act_quote.setCheckable(True)
        self.act_quote.setToolTip("Quote block")
        self.act_quote.triggered.connect(self.toggle_quote)
        toolbar.addAction(self.act_quote)

        toolbar.addSeparator()

        self.act_ul = QAction("", self); self.act_ul.setCheckable(True)
        self.act_ul.setToolTip("Bulleted list")
        self.act_ul.triggered.connect(lambda: self.toggle_list("ul"))
        toolbar.addAction(self.act_ul)

        self.act_ol = QAction("", self); self.act_ol.setCheckable(True)
        self.act_ol.setToolTip("Numbered list")
        self.act_ol.triggered.connect(lambda: self.toggle_list("ol"))
        toolbar.addAction(self.act_ol)

        self.act_table = QAction("", self)
        self.act_table.setToolTip("Insert table")
        self.act_table.triggered.connect(self.insert_table)
        toolbar.addAction(self.act_table)

        self.act_hr = QAction("", self)
        self.act_hr.setToolTip("Insert horizontal line (---)")
        self.act_hr.triggered.connect(self.insert_horizontal_line)
        toolbar.addAction(self.act_hr)

        toolbar.addSeparator()

        self.act_link = QAction("", self); self.act_link.setCheckable(True)
        self.act_link.setToolTip("Insert / edit link")
        self.act_link.triggered.connect(self.insert_link)
        toolbar.addAction(self.act_link)

        toolbar.addSeparator()

        self.act_spellcheck_toolbar = QAction("", self); self.act_spellcheck_toolbar.setCheckable(True)
        self.act_spellcheck_toolbar.setToolTip("Spell Check")
        self.act_spellcheck_toolbar.setChecked(self.settings.get("spellcheck_enabled", False))
        self.act_spellcheck_toolbar.triggered.connect(self.toggle_spellcheck)
        if not self.spell_manager.available:
            self.act_spellcheck_toolbar.setEnabled(False)
            self.act_spellcheck_toolbar.setToolTip(
                "Spell checking requires the 'phunspell' package.\nInstall it with: pip install phunspell")
        toolbar.addAction(self.act_spellcheck_toolbar)

        # Icons are tinted to the current theme's toolbar text color, so
        # collect the actions once here and reuse this map to re-tint them
        # if the theme changes later (see refresh_toolbar_icons()).
        self._icon_actions = {
            "bold": self.act_bold, "italic": self.act_italic, "underline": self.act_underline,
            "code": self.act_code, "quote": self.act_quote, "ul": self.act_ul, "ol": self.act_ol,
            "table": self.act_table, "line": self.act_hr, "link": self.act_link,
            "spellcheck": self.act_spellcheck_toolbar,
        }
        self.refresh_toolbar_icons()

        # All formatting buttons (bold/italic/underline/code/quote/ul/ol/
        # table/line/link) are icon-only, same as before this only applied
        # to B/I/U. Every toolbar button - the H1-H6 buttons and all the
        # icon buttons - is then forced to one identical square size, so
        # the whole row reads as one uniform grid instead of a ragged mix
        # of narrow and wide buttons.
        format_buttons = [toolbar.widgetForAction(a) for a in self._icon_actions.values()]
        format_buttons = [b for b in format_buttons if b is not None]
        for b in format_buttons:
            b.setToolButtonStyle(Qt.ToolButtonIconOnly)

        h_buttons = [toolbar.widgetForAction(a) for a in self.h_actions.values()]
        h_buttons = [b for b in h_buttons if b is not None]

        all_buttons = h_buttons + format_buttons
        if all_buttons:
            button_size = max(max(b.sizeHint().width(), b.sizeHint().height()) for b in all_buttons)
            for b in all_buttons:
                b.setFixedSize(button_size, button_size)

    def refresh_toolbar_icons(self):
        """(Re)apply SVG icons to the formatting toolbar, tinted to the
        current theme's text color. Safe to call any time the theme
        changes, and a no-op (blank icons) if QtSvg isn't installed."""
        color = self.settings.get("app_text", "#d4d4d4")
        for name, action in self._icon_actions.items():
            action.setIcon(make_svg_icon(name, color, size=20))
        self.tab_widget.refresh_close_button_icons()

    def update_toolbar_margin(self):
        editor = self.tab_widget.currentWidget()
        if editor:
            self.toolbar_spacer.setFixedWidth(editor.line_number_area_width())

    def create_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+D"), self, activated=self.duplicate_line)
        QShortcut(QKeySequence("Alt+Up"), self, activated=lambda: self.move_line(-1))
        QShortcut(QKeySequence("Alt+Down"), self, activated=lambda: self.move_line(1))

    # --- Spell Checking ---
    def toggle_spellcheck(self, checked):
        self.spell_manager.set_enabled(checked)
        self.save_settings()
        # The menu checkbox and the toolbar "Aa" button both control the
        # same setting - keep them in sync no matter which one was clicked,
        # without re-triggering each other.
        for action in (getattr(self, "act_spellcheck_menu", None), getattr(self, "act_spellcheck_toolbar", None)):
            if action is not None and action.isChecked() != checked:
                action.blockSignals(True)
                action.setChecked(checked)
                action.blockSignals(False)

    # --- Tab Management ---
    def new_tab(self, switch=True):
        editor = Editor(self.settings, self)
        index = self.tab_widget.addTab(editor, "New")
        self.tab_widget.add_close_button(editor)
        editor.selectionChanged.connect(self.update_toolbar_state)
        editor.document().modificationChanged.connect(lambda mod, e=editor: self.on_modification_changed(e))
        if switch:
            self.tab_widget.setCurrentIndex(index)
        return editor

    def on_modification_changed(self, editor):
        self.update_tab_title(editor)
        if editor == self.tab_widget.currentWidget():
            self.update_window_title()

    def close_tab(self, index):
        editor = self.tab_widget.widget(index)
        if editor and editor.document().isModified():
            reply = QMessageBox.question(self, "Close Tab", "The tab has unsaved changes. Are you sure you want to close it?", QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.No: return
        self.tab_widget.removeTab(index)
        if self.tab_widget.count() == 0:
            self.new_tab()

    def duplicate_tab(self, index):
        editor = self.tab_widget.widget(index)
        new_editor = self.new_tab(switch=False)
        
        cursor = editor.textCursor()
        cursor.select(QTextCursor.Document)
        frag = cursor.selection()
        
        new_cursor = new_editor.textCursor()
        new_cursor.insertFragment(frag)
        new_editor.current_file = editor.current_file
        new_editor.view_mode = editor.view_mode
        self.update_tab_title(new_editor)
        self.tab_widget.setTabText(self.tab_widget.indexOf(new_editor), self.tab_widget.tabText(index) + " (Copy)")
        new_editor.style_tables()

    def close_other_tabs(self, index):
        for i in range(self.tab_widget.count() - 1, -1, -1):
            if i != index: self.close_tab(i)

    def close_all_tabs(self):
        for i in range(self.tab_widget.count() - 1, -1, -1):
            self.close_tab(i)

    def on_tab_changed(self, index):
        editor = self.tab_widget.widget(index)
        if editor:
            self.update_toolbar_margin()
            self.update_window_title()
            self.update_toolbar_state()
            self.update_view_menu_state()

    def update_tab_title(self, editor):
        idx = self.tab_widget.indexOf(editor)
        title = "New"
        if editor.current_file:
            title = os.path.basename(editor.current_file)
        if editor.document().isModified():
            title = f"*{title}"
        self.tab_widget.setTabText(idx, title)
        if editor.current_file:
            self.tab_widget.setTabToolTip(idx, editor.current_file)
        else:
            self.tab_widget.setTabToolTip(idx, "")

    def update_window_title(self):
        editor = self.tab_widget.currentWidget()
        if not editor:
            self.setWindowTitle("MPad++")
            return
        base_title = "New"
        if editor.current_file:
            base_title = os.path.basename(editor.current_file)
        
        modified_str = "*" if editor.document().isModified() else ""
        self.setWindowTitle(f"MPad++ - {modified_str}{base_title}")

    # --- Custom Markdown Export/Import ---
    def export_markdown(self, editor):
        doc = editor.document()
        cursor = QTextCursor(doc)
        cursor.movePosition(QTextCursor.Start)
        
        md_lines = []
        in_code_block = False
        prev_was_quote = False
        # When the "<br>" line-break style bridges two adjacent plain
        # paragraphs, the next block's text must be appended onto the
        # SAME md_lines entry (no extra raw "\n" in between) - see the
        # comment on needs_paragraph_break_marker() below for why.
        pending_br_merge = False

        def ensure_blank_separator():
            if md_lines and md_lines[-1] != "":
                md_lines.append("")

        def needs_paragraph_break_marker(block):
            # Two adjacent plain paragraph blocks (created by pressing
            # Enter, not Shift+Enter) are joined below by a single '\n'
            # with no blank line between them. CommonMark's "lazy
            # continuation" rule means that, read back with no marker,
            # they'd silently merge into one re-wrapped paragraph - so
            # the configured hard-line-break style has to be applied
            # here too, not just at Shift+Enter (U+2028) points.
            #
            # Special case for the "<br>" style: unlike the backslash
            # and double-space CommonMark constructs (which consume the
            # newline right after them as part of the break itself),
            # "<br/>" is just inline raw HTML - a literal "\n" straight
            # after it is parsed as a *separate*, ordinary soft line
            # break, which renders as an extra leading space on the next
            # line. So when "<br>" is selected, the next block's text is
            # merged onto the same md_lines entry (pending_br_merge)
            # instead of starting a new one, keeping the tag and the
            # following text on the same raw source line.
            next_block = block.next()
            if not next_block.isValid():
                return False
            next_text = next_block.text()
            if next_text == "":
                return False
            if QTextCursor(next_block).currentTable():
                return False
            next_fmt = next_block.blockFormat()
            if next_fmt.headingLevel() > 0:
                return False
            if next_fmt.hasProperty(QUOTE_PROP) and next_fmt.property(QUOTE_PROP) == True:
                return False
            if next_fmt.hasProperty(HR_PROP) and next_fmt.property(HR_PROP) == True:
                return False
            if next_fmt.hasProperty(BLOCK_CODE_PROP) and next_fmt.property(BLOCK_CODE_PROP) == True:
                return False
            next_stripped = next_text.lstrip()
            if next_stripped.startswith(("• ", "- ", "* ")):
                return False
            if len(next_stripped) > 2 and next_stripped[0].isdigit() and next_stripped[1] == '.' and next_stripped[2] == ' ':
                return False
            return True

        def line_break_suffix():
            style = self.settings.get("line_break_style", "double_space")
            if style == "br":
                # Written out exactly as "<br>" (no self-closing slash) so
                # the saved file / Plain Text source matches what someone
                # would naturally type by hand. preprocess_markdown()
                # still upgrades it to the self-closing "<br/>" form
                # in-memory, right before handing text to Qt's Markdown
                # importer, since that's the only form Qt reliably reads
                # back as a real line break - but that upgrade is never
                # written back to disk, so the on-disk/Plain Text text
                # stays "<br>".
                return "<br>"
            elif style == "backslash":
                return "\\"
            else:
                return "  "

        block = doc.firstBlock()
        while block.isValid():
            temp_cursor = QTextCursor(block)
            table = temp_cursor.currentTable()
            if table:
                if block.position() == table.firstCursorPosition().block().position():
                    if prev_was_quote:
                        ensure_blank_separator()
                        prev_was_quote = False
                    pending_br_merge = False
                    self.export_table_to_md(table, md_lines)
                    temp_cursor.setPosition(table.lastPosition() + 1)
                    block = temp_cursor.block()
                    continue
                else:
                    block = block.next()
                    continue
                    
            text = block.text()
            block_fmt = block.blockFormat()
            
            is_block_code = block_fmt.hasProperty(BLOCK_CODE_PROP) and block_fmt.property(BLOCK_CODE_PROP) == True
            is_quote = block_fmt.hasProperty(QUOTE_PROP) and block_fmt.property(QUOTE_PROP) == True
            is_hr = block_fmt.hasProperty(HR_PROP) and block_fmt.property(HR_PROP) == True
            level = block_fmt.headingLevel()

            # CommonMark "lazily" folds a line straight after a blockquote
            # into that same blockquote paragraph unless a blank line
            # closes it off first, so any transition out of a quote block
            # needs one inserted.
            if prev_was_quote and not is_quote:
                ensure_blank_separator()
            prev_was_quote = is_quote
            
            if is_hr:
                pending_br_merge = False
                if in_code_block:
                    md_lines.append("```")
                    in_code_block = False
                # A bare "---" only reads back as a thematic break (rather
                # than a Setext heading underline for whatever text came
                # right before it) when it sits on its own blank-line-
                # delimited paragraph.
                ensure_blank_separator()
                md_lines.append("---")
                md_lines.append("")
                block = block.next()
                continue

            if is_block_code:
                pending_br_merge = False
                if not in_code_block:
                    md_lines.append("```")
                    in_code_block = True
                md_lines.append(text)
                block = block.next()
                continue
            else:
                if in_code_block:
                    md_lines.append("```")
                    in_code_block = False
                    
            if level > 0:
                pending_br_merge = False
                md_lines.append("#" * level + " " + self.get_inline_md(block))
            elif is_quote:
                pending_br_merge = False
                md_lines.append("> " + self.get_inline_md(block))
            else:
                stripped = text.lstrip()
                prefix = ""
                skip = 0
                if stripped.startswith("• "):
                    prefix = "- "
                    skip = 2
                elif stripped.startswith("- ") or stripped.startswith("* "):
                    prefix = "- "
                    skip = 2
                elif len(stripped) > 2 and stripped[0].isdigit() and stripped[1] == '.' and stripped[2] == ' ':
                    prefix = stripped[:3]
                    skip = 3
                    
                if prefix:
                    pending_br_merge = False
                    md_lines.append(prefix + self.get_inline_md(block, skip))
                else:
                    if text == "":
                        pending_br_merge = False
                        md_lines.append("")
                    else:
                        line = self.get_inline_md(block)
                        if pending_br_merge:
                            md_lines[-1] += line
                        else:
                            md_lines.append(line)
                        pending_br_merge = False

                        if needs_paragraph_break_marker(block):
                            style = self.settings.get("line_break_style", "double_space")
                            if style == "br":
                                md_lines[-1] += "<br>"
                                pending_br_merge = True
                            else:
                                md_lines[-1] += line_break_suffix()
                        
            block = block.next()
            
        if in_code_block:
            md_lines.append("```")
            
        return "\n".join(md_lines)

    def export_table_to_md(self, table, md_lines):
        rows = table.rows()
        cols = table.columns()
        
        header = []
        for c in range(cols):
            cell = table.cellAt(0, c)
            cursor = cell.firstCursorPosition()
            cursor.movePosition(QTextCursor.EndOfCell, QTextCursor.KeepAnchor)
            header.append(cursor.selectedText().replace('\n', ' '))
        md_lines.append("| " + " | ".join(header) + " |")
        
        sep = ["---"] * cols
        md_lines.append("| " + " | ".join(sep) + " |")
        
        for r in range(1, rows):
            row_data = []
            for c in range(cols):
                cell = table.cellAt(r, c)
                cursor = cell.firstCursorPosition()
                cursor.movePosition(QTextCursor.EndOfCell, QTextCursor.KeepAnchor)
                row_data.append(cursor.selectedText().replace('\n', ' '))
            md_lines.append("| " + " | ".join(row_data) + " |")

    def get_inline_md(self, block, skip_chars=0):
        result = ""
        level = block.blockFormat().headingLevel()
        is_quote = block.blockFormat().hasProperty(QUOTE_PROP) and block.blockFormat().property(QUOTE_PROP) == True
        
        it = block.begin()
        while not it.atEnd():
            frag = it.fragment()
            if frag.isValid() and frag.length() > 0:
                text = frag.text()
                if skip_chars > 0:
                    if len(text) <= skip_chars:
                        skip_chars -= len(text)
                        continue
                    else:
                        text = text[skip_chars:]
                        skip_chars = 0
                        
                if not text:
                    continue

                fmt = frag.charFormat()
                is_code = fmt.hasProperty(CODE_PROP) and fmt.property(CODE_PROP) == True
                is_anchor = fmt.isAnchor()
                is_bold = fmt.fontWeight() == QFont.Bold
                is_italic = fmt.fontItalic()
                is_underline = fmt.fontUnderline()
                
                if is_code:
                    piece = f"`{text}`"
                elif is_anchor:
                    piece = f"[{self.escape_md_text(text)}]({fmt.anchorHref()})"
                else:
                    # Any of these characters, typed as literal text rather
                    # than intended as markup, would otherwise be misread
                    # as real Markdown syntax on reload (turning a literal
                    # "*note*" into italics, a stray "_" into an
                    # underscore-emphasis marker, "<tag>" into raw HTML,
                    # etc.) - escaping them here keeps plain typed text
                    # showing up as plain text, both in the Plain Text view
                    # and after switching back to Formatted.
                    tmp = self.escape_md_text(text)
                    if is_bold and level == 0:
                        tmp = f"**{tmp}**"
                    if is_italic and level == 0 and not is_quote:
                        tmp = f"*{tmp}*"
                    if is_underline:
                        tmp = f"<u>{tmp}</u>"
                    piece = tmp

                # Shift+Enter inserts a U+2028 LINE SEPARATOR inside the
                # current block rather than starting a new one. Left as-is
                # it's an invisible character that Markdown (and most text
                # editors) don't understand, so a shift+enter line break
                # would silently vanish on save/reload. Turn it into
                # whichever hard-line-break syntax is configured in
                # Settings > Preferences so it survives the round trip -
                # it comes back as a normal line break on reopen.
                #
                # This substitution happens *after* escape_md_text() above,
                # not before: escaping runs over whatever literal text the
                # user typed, and U+2028 itself is never part of that
                # escape-char set, so it passes through untouched either
                # way. Doing the replacement first (on `text`) used to mean
                # the freshly-inserted "<br/>" (or backslash) got escaped
                # right along with it, turning it into a literal
                # "\<br/\>" that Qt's Markdown reader doesn't recognize as
                # a tag at all - it showed up as visible backslash-escaped
                # text in the reopened document instead of an actual line
                # break.
                if '\u2028' in piece:
                    style = self.settings.get("line_break_style", "double_space")
                    if style == "br":
                        # Written out exactly as "<br>" - preprocess_markdown()
                        # is what upgrades a bare "<br>" to the self-closing
                        # "<br/>" form Qt's importer needs, but only
                        # in-memory right before parsing, never back to the
                        # saved file/Plain Text source. This is also the
                        # only one of the three styles that reopens as a
                        # genuine same-block soft break (mirroring the
                        # original Shift+Enter).
                        #
                        # No trailing "\n" here (unlike the other two
                        # styles below): a literal newline right after
                        # "<br>" isn't consumed as part of the tag the
                        # way it is for the backslash/double-space hard-
                        # break constructs - it's parsed as a *separate*
                        # ordinary soft break, which would add a spurious
                        # leading space to the next line on reload.
                        replacement = "<br>"
                    elif style == "backslash":
                        # CommonMark hard break. Reopens as two separate
                        # blocks/paragraphs rather than one block with an
                        # internal soft break - visually identical, but
                        # worth knowing if later code walks blocks.
                        replacement = "\\\n"
                    else:
                        # CommonMark hard break (two trailing spaces).
                        # Same two-block caveat as the backslash style above.
                        replacement = "  \n"
                    piece = piece.replace('\u2028', replacement)

                result += piece
            it += 1
        return result

    # Previously this backslash-escaped literal Markdown-special characters
    # (\ ` * _ [ ] < > ~ |) in plain typed text before export, so they'd
    # read back as the exact same literal characters instead of being
    # reinterpreted as emphasis, code spans, links, or raw HTML. Disabled
    # on request, to match how other editors export - typed text is now
    # written out as-is. Trade-off: a literally typed "*note*", "_x_",
    # "<tag>", etc. can be reinterpreted as real Markdown syntax the next
    # time the file is reopened.
    MD_ESCAPE_CHARS = r'\`*_[]<>~|'

    def escape_md_text(self, text):
        return text

    # --- File Operations ---
    def preprocess_markdown(self, content):
        lines = content.split('\n')
        new_lines = []
        prev_type = 'normal'
        in_md_code_block = False

        for line in lines:
            stripped = line.lstrip()

            if in_md_code_block:
                if stripped.startswith('```'):
                    in_md_code_block = False
                    new_lines.append(line)
                    prev_type = 'code'
                else:
                    new_lines.append(line)
                    prev_type = 'code'
                continue

            # Normalize the recognized hard-line-break tag before Qt's
            # own Markdown importer ever sees it. Qt's importer only
            # reliably turns a self-closing "<br/>" into a real in-
            # paragraph line break; a bare "<br>" (no closing slash)
            # makes it drop the rest of that paragraph on load instead.
            # The primary symbol looked for on read is the bare "<br>"
            # (matching what someone would naturally type by hand), and
            # the self-closing "<br/>" is also recognized as an
            # alternate - both are rewritten here to the self-closing
            # form so either one reopens correctly. Left alone inside
            # fenced code blocks (handled above) so example HTML isn't
            # rewritten.
            #
            # Also tolerates the backslash-escaped "\<br/\>" that older
            # versions of this app used to write (a since-fixed export
            # bug used to run "<" and ">" through Markdown-escaping
            # *after* inserting the literal "<br/>" tag, corrupting it).
            # Files saved back then have that broken form baked in on
            # disk; this normalizes it back to a real line break too so
            # such files self-heal on open instead of showing literal
            # "<br/>" text forever.
            line = re.sub(r'\\?<br\s*/?\\?>', '<br/>', line)
            stripped = line.lstrip()

            if stripped.startswith('```'):
                current_type = 'code'
                in_md_code_block = True
            elif stripped.startswith('> '):
                current_type = 'quote'
            elif stripped.startswith('#'):
                current_type = 'header'
            elif re.fullmatch(r'-{1,}\s*', stripped) or re.fullmatch(r'={1,}\s*', stripped):
                # A run of "-" or "=" directly under a text line is what
                # CommonMark reads as a Setext heading underline (H2/H1),
                # not a horizontal rule - so a line like this left over
                # from an older save (or a hand-edited file) would
                # silently swallow the paragraph above it into a heading.
                # This app only ever writes headings as "#"/"##" ATX
                # syntax, so any such underline is forced onto its own
                # blank-line-delimited paragraph below, which reads back
                # as a horizontal rule (or, for "=", inert plain text)
                # instead.
                current_type = 'hr_underline'
            elif stripped.startswith(('- ', '* ', '• ')) or (
                    len(stripped) > 2 and stripped[0].isdigit()
                    and stripped[1] == '.' and stripped[2] == ' '):
                current_type = 'list'
            else:
                current_type = 'normal'

            if current_type != prev_type:
                if current_type in ('quote', 'header', 'hr_underline') or prev_type in ('quote', 'header'):
                    if new_lines and new_lines[-1].strip() != '':
                        new_lines.append('')

            new_lines.append(line)
            if line.strip() == '':
                prev_type = 'normal'
            else:
                prev_type = current_type

        return '\n'.join(new_lines)

    def open_file_dialog(self, in_new_tab=False):
        file_path, _ = QFileDialog.getOpenFileName(self, "Open File", "", "Markdown (*.md);;Text files (*.txt)")
        if file_path:
            self.open_file_path(file_path, in_new_tab=in_new_tab)

    def open_files_from_args(self, file_paths):
        # Called once at startup for files passed on the command line
        # (e.g. `python MPadPlusPlus.py notes.md other.md`). The very first
        # one reuses the empty tab MainWindow already created in __init__
        # (open_file_path loads straight into it without prompting, since
        # an empty tab never triggers the "Tab Not Empty" dialog); every
        # subsequent path gets its own new tab.
        valid_paths = [p for p in file_paths if os.path.isfile(p)]
        missing = [p for p in file_paths if not os.path.isfile(p)]

        for i, path in enumerate(valid_paths):
            self.open_file_path(path, in_new_tab=(i > 0))

        if missing:
            QMessageBox.warning(
                self, "File Not Found",
                "The following file(s) could not be found:\n" + "\n".join(missing)
            )

    def open_file_path(self, file_path, target_editor=None, in_new_tab=False):
        editor = target_editor if target_editor else self.tab_widget.currentWidget()
        
        if not in_new_tab and editor and not editor.document().isEmpty():
            msg = QMessageBox(self)
            msg.setWindowTitle("Tab Not Empty")
            msg.setText("The current tab is not empty. What do you want to do?")
            btn_replace = msg.addButton("Replace content", QMessageBox.AcceptRole)
            btn_new_tab = msg.addButton("Open in new tab", QMessageBox.AcceptRole)
            btn_cancel = msg.addButton("Cancel", QMessageBox.RejectRole)
            msg.exec()
            if msg.clickedButton() == btn_cancel: return
            if msg.clickedButton() == btn_new_tab:
                editor = self.new_tab()
                
        if in_new_tab or not editor:
            editor = self.new_tab()
            
        try:
            # If this editor already has focus (reusing the current tab via
            # drag-drop or File > Open, as opposed to a freshly-created
            # tab), calling setFocus() again later in this function is a
            # no-op as far as Qt is concerned - focusInEvent() only fires on
            # an actual no-focus -> focus transition. That means our
            # focusInEvent cleanup (reasserting cursorFlashTime, restarting
            # the blink timer, forcing a full repaint) never runs for the
            # reuse case, which is exactly the case where the ghost/dead
            # second cursor has been seen. Force a real focus-out/focus-in
            # cycle around the swap so that cleanup always runs, regardless
            # of whether this editor already had focus coming in.
            had_focus = editor.hasFocus()
            if had_focus:
                editor.clearFocus()

            editor._caret_visible = False
            editor.viewport().repaint()

            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            content = self.preprocess_markdown(content)

            editor.document().setUndoRedoEnabled(False)
            editor.setExtraSelections([])
            editor.document().setMarkdown(content, QTextDocument.MarkdownDialectGitHub)
            editor.current_file = file_path
            editor.view_mode = "formatted"
            editor.post_process_markdown()
            editor.style_tables()
            editor.apply_settings_to_document(restore_cursor=False)
            editor.document().setModified(False)

            # Move cursor to Start BEFORE re-enabling undo so that
            # setUndoRedoEnabled(True) cannot fire cursorPositionChanged
            # with a stale end-of-document position.
            cursor = QTextCursor(editor.document())
            cursor.movePosition(QTextCursor.Start)
            editor.setTextCursor(cursor)

            editor.document().setUndoRedoEnabled(True)

            self.update_tab_title(editor)
            self.update_window_title()
            self.update_toolbar_state()

            editor.window().activateWindow()
            editor.setFocus(Qt.OtherFocusReason)

            # Defer scrolling the cursor into view and repainting to the next
            # event-loop tick. Right after document().setMarkdown() replaces
            # the content, Qt's internal layout for the new document can
            # still be settling, so calling ensureCursorVisible()/update()
            # synchronously here can use stale geometry and leave our custom
            # caret painted in the wrong spot. Running this on the next tick
            # guarantees the new layout is fully resolved first.
            def _finish_open_file_visuals(ed=editor):
                ed.ensureCursorVisible()
                ed._reset_caret_blink()
                ed.line_number_area.update()
            QTimer.singleShot(0, _finish_open_file_visuals)

        except Exception as e:
            editor.document().setUndoRedoEnabled(True)
            QMessageBox.critical(self, "Error", f"Cannot open file:\n{str(e)}")

    def save_file(self):
        editor = self.tab_widget.currentWidget()
        if not editor: return
        if not editor.current_file:
            self.save_as_file()
            return
        try:
            markdown_content = self.export_markdown(editor)
            with open(editor.current_file, 'w', encoding='utf-8') as f:
                f.write(markdown_content)
            editor.document().setModified(False)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Cannot save file:\n{str(e)}")

    def save_as_file(self):
        editor = self.tab_widget.currentWidget()
        if not editor: return
        file_path, _ = QFileDialog.getSaveFileName(self, "Save As", "", "Markdown (*.md);;Text files (*.txt)")
        if file_path:
            if not file_path.endswith('.md') and not file_path.endswith('.txt'):
                file_path += '.md'
            editor.current_file = file_path
            self.save_file()
            self.update_tab_title(editor)
            self.update_window_title()

    def closeEvent(self, event):
        for i in range(self.tab_widget.count()):
            editor = self.tab_widget.widget(i)
            if editor and editor.document().isModified():
                reply = QMessageBox.question(self, "Exit", "Some tabs have unsaved changes. Are you sure you want to close the program?", QMessageBox.Yes | QMessageBox.No)
                if reply == QMessageBox.No:
                    event.ignore()
                    return
                break
        self.spell_manager.shutdown()
        event.accept()

    # --- WYSIWYG Formatting ---
    def get_editor(self):
        return self.tab_widget.currentWidget()

    def edit_cut(self):
        editor = self.get_editor()
        if editor:
            editor.cut()

    def edit_copy(self):
        editor = self.get_editor()
        if editor:
            editor.copy()

    def edit_paste(self):
        editor = self.get_editor()
        if editor:
            editor.paste()

    def toggle_bold(self):
        editor = self.get_editor()
        if not editor: return
        cursor = editor.textCursor()
        if not cursor.hasSelection():
            fmt = cursor.charFormat()
            fmt.setFontWeight(QFont.Normal if fmt.fontWeight() == QFont.Bold else QFont.Bold)
            fmt.setForeground(QColor(self.settings['bold'] if fmt.fontWeight() == QFont.Bold else self.settings['editor_text']))
            cursor.setCharFormat(fmt)
            editor.setTextCursor(cursor)
            return
            
        fmt = cursor.charFormat()
        is_bold = (fmt.fontWeight() == QFont.Bold)
        new_fmt = QTextCharFormat()
        new_fmt.setFontWeight(QFont.Normal if is_bold else QFont.Bold)
        new_fmt.setForeground(QColor(self.settings['editor_text'] if is_bold else self.settings['bold']))
        cursor.mergeCharFormat(new_fmt)
        editor.setTextCursor(cursor)
        self.update_toolbar_state()

    def toggle_italic(self):
        editor = self.get_editor()
        if not editor: return
        cursor = editor.textCursor()
        if not cursor.hasSelection():
            fmt = cursor.charFormat()
            fmt.setFontItalic(not fmt.fontItalic())
            fmt.setForeground(QColor(self.settings['italic'] if fmt.fontItalic() else self.settings['editor_text']))
            cursor.setCharFormat(fmt)
            editor.setTextCursor(cursor)
            return
            
        fmt = cursor.charFormat()
        is_italic = fmt.fontItalic()
        new_fmt = QTextCharFormat()
        new_fmt.setFontItalic(not is_italic)
        new_fmt.setForeground(QColor(self.settings['editor_text'] if is_italic else self.settings['italic']))
        cursor.mergeCharFormat(new_fmt)
        editor.setTextCursor(cursor)
        self.update_toolbar_state()

    def toggle_underline(self):
        editor = self.get_editor()
        if not editor: return
        cursor = editor.textCursor()
        if not cursor.hasSelection():
            fmt = cursor.charFormat()
            fmt.setFontUnderline(not fmt.fontUnderline())
            fmt.setForeground(QColor(self.settings['underline'] if fmt.fontUnderline() else self.settings['editor_text']))
            cursor.setCharFormat(fmt)
            editor.setTextCursor(cursor)
            return
            
        fmt = cursor.charFormat()
        is_underline = fmt.fontUnderline()
        new_fmt = QTextCharFormat()
        new_fmt.setFontUnderline(not is_underline)
        new_fmt.setForeground(QColor(self.settings['editor_text'] if is_underline else self.settings['underline']))
        cursor.mergeCharFormat(new_fmt)
        editor.setTextCursor(cursor)
        self.update_toolbar_state()

    def toggle_code(self):
        editor = self.get_editor()
        if not editor: return
        cursor = editor.textCursor()
        
        is_block = False
        if cursor.hasSelection():
            temp = QTextCursor(cursor)
            temp.setPosition(cursor.selectionStart())
            starts_at_beginning = temp.atBlockStart()
            temp.setPosition(cursor.selectionEnd())
            ends_at_end = temp.atBlockEnd()
            if starts_at_beginning and ends_at_end:
                is_block = True
        else:
            is_block = True
            
        if is_block:
            cursor.beginEditBlock()
            start = cursor.selectionStart()
            end = cursor.selectionEnd()
            cursor.setPosition(start)
            
            first_block_fmt = cursor.blockFormat()
            toggle_off = (first_block_fmt.hasProperty(BLOCK_CODE_PROP) and first_block_fmt.property(BLOCK_CODE_PROP) == True)
            
            while cursor.position() <= end:
                block_fmt = cursor.blockFormat()
                new_block_fmt = QTextBlockFormat()
                new_char_fmt = QTextCharFormat()
                
                if toggle_off:
                    new_block_fmt.setProperty(BLOCK_CODE_PROP, False)
                    new_block_fmt.setBackground(Qt.transparent)
                    new_char_fmt.setForeground(QColor(self.settings['editor_text']))
                    new_char_fmt.setFontFamilies([self.settings['font_family']])
                    new_char_fmt.setProperty(CODE_PROP, False)
                    new_char_fmt.setBackground(Qt.transparent)
                else:
                    new_block_fmt.setProperty(BLOCK_CODE_PROP, True)
                    new_block_fmt.setBackground(QColor(self.settings['code_bg']))
                    new_char_fmt.setForeground(QColor(self.settings['code']))
                    new_char_fmt.setFontFamilies(["Consolas"])
                    new_char_fmt.setProperty(CODE_PROP, True)
                    new_char_fmt.setBackground(Qt.transparent)
                    
                cursor.setBlockFormat(new_block_fmt)
                cursor.mergeCharFormat(new_char_fmt)
                
                if not cursor.movePosition(QTextCursor.Down):
                    break
            cursor.endEditBlock()
            editor.setTextCursor(cursor)
        else:
            fmt = cursor.charFormat()
            is_code = (fmt.hasProperty(CODE_PROP) and fmt.property(CODE_PROP) == True)
            new_fmt = QTextCharFormat()
            if is_code:
                new_fmt.setBackground(Qt.transparent)
                new_fmt.setForeground(QColor(self.settings['editor_text']))
                new_fmt.setFontFamilies([self.settings['font_family']])
                new_fmt.setProperty(CODE_PROP, False)
            else:
                new_fmt.setBackground(QColor(self.settings['code_bg']))
                new_fmt.setForeground(QColor(self.settings['code']))
                new_fmt.setFontFamilies(["Consolas"])
                new_fmt.setProperty(CODE_PROP, True)
            cursor.mergeCharFormat(new_fmt)
            editor.setTextCursor(cursor)
            
        self.update_toolbar_state()

    def toggle_heading(self, level):
        editor = self.get_editor()
        if not editor: return
        cursor = editor.textCursor()
        cursor.beginEditBlock()
        start = cursor.selectionStart()
        end = cursor.selectionEnd()
        cursor.setPosition(start)
        cursor.movePosition(QTextCursor.StartOfLine)
        
        block_fmt_check = cursor.blockFormat()
        toggle_off = (block_fmt_check.headingLevel() == level)
        
        while cursor.position() <= end:
            line_start = cursor.position()
            cursor.movePosition(QTextCursor.EndOfLine)
            line_end = cursor.position()
            cursor.setPosition(line_start)
            cursor.setPosition(line_end, QTextCursor.KeepAnchor)
            
            block_fmt = cursor.blockFormat()
            char_fmt = QTextCharFormat()
            
            if toggle_off:
                block_fmt.setHeadingLevel(0)
                char_fmt.setFontPointSize(self.settings["font_size"])
                char_fmt.setForeground(QColor(self.settings["editor_text"]))
                char_fmt.setFontWeight(QFont.Normal)
            else:
                block_fmt.setHeadingLevel(level)
                size = self.settings.get(f"h{level}_size", 0)
                if size == 0: size = self.settings["font_size"]
                char_fmt.setFontPointSize(size)
                char_fmt.setForeground(QColor(self.settings[f"h{level}"]))
                char_fmt.setFontWeight(QFont.Bold)
                
            cursor.setBlockFormat(block_fmt)
            cursor.mergeCharFormat(char_fmt)
            if not cursor.movePosition(QTextCursor.Down): break
        cursor.endEditBlock()
        editor.setTextCursor(cursor)
        self.update_toolbar_state()

    def toggle_quote(self):
        editor = self.get_editor()
        if not editor: return
        cursor = editor.textCursor()
        cursor.beginEditBlock()
        start = cursor.selectionStart()
        end = cursor.selectionEnd()
        cursor.setPosition(start)
        cursor.movePosition(QTextCursor.StartOfLine)
        
        block_fmt_check = cursor.blockFormat()
        toggle_off = (block_fmt_check.hasProperty(QUOTE_PROP) and block_fmt_check.property(QUOTE_PROP) == True)
        
        while cursor.position() <= end:
            line_start = cursor.position()
            cursor.movePosition(QTextCursor.EndOfLine)
            line_end = cursor.position()
            cursor.setPosition(line_start)
            cursor.setPosition(line_end, QTextCursor.KeepAnchor)
            
            block_fmt = cursor.blockFormat()
            char_fmt = QTextCharFormat()
            
            if toggle_off:
                block_fmt.setLeftMargin(0)
                block_fmt.setProperty(QUOTE_PROP, False)
                char_fmt.setFontItalic(False)
                char_fmt.setForeground(QColor(self.settings['editor_text']))
            else:
                block_fmt.setLeftMargin(15)
                block_fmt.setProperty(QUOTE_PROP, True)
                char_fmt.setFontItalic(True)
                char_fmt.setForeground(QColor(self.settings['quote']))
                
            cursor.setBlockFormat(block_fmt)
            cursor.mergeCharFormat(char_fmt)
            if not cursor.movePosition(QTextCursor.Down): break
        cursor.endEditBlock()
        editor.setTextCursor(cursor)
        self.update_toolbar_state()

    def toggle_list(self, list_type):
        editor = self.get_editor()
        if not editor: return
        cursor = editor.textCursor()
        cursor.beginEditBlock()
        
        start = cursor.selectionStart()
        end = cursor.selectionEnd()
        
        cursor.setPosition(start)
        cursor.movePosition(QTextCursor.StartOfLine)
        
        line_text = cursor.block().text().strip()
        toggle_off = False
        
        is_ul = line_text.startswith("• ") or line_text.startswith("- ") or line_text.startswith("* ")
        is_ol = len(line_text) > 2 and line_text[0].isdigit() and line_text[1] == '.' and line_text[2] == ' '
        
        if list_type == "ul":
            if is_ul: toggle_off = True
        else:
            if is_ol: toggle_off = True
                
        counter = 1
        while cursor.position() <= end:
            line_start = cursor.position()
            cursor.movePosition(QTextCursor.EndOfLine)
            line_end = cursor.position()
            
            cursor.setPosition(line_start)
            cursor.setPosition(line_end, QTextCursor.KeepAnchor)
            text = cursor.selectedText()
            
            if text.startswith("• ") or text.startswith("- ") or text.startswith("* "):
                text = text[2:]
            elif len(text) > 2 and text[0].isdigit() and text[1] == '.' and text[2] == ' ':
                text = text[3:]
                
            if not toggle_off:
                if list_type == "ul":
                    new_text = "• " + text
                else:
                    new_text = f"{counter}. " + text
                cursor.insertText(new_text)
                counter += 1
            else:
                cursor.insertText(text)
                
            if not cursor.movePosition(QTextCursor.Down): break
            
        cursor.endEditBlock()
        editor.setTextCursor(cursor)
        self.update_toolbar_state()

    def insert_horizontal_line(self):
        editor = self.get_editor()
        if not editor: return
        cursor = editor.textCursor()
        if cursor.currentTable(): return

        # Remember where the caret was so we can put it back afterwards -
        # inserting the line below shouldn't drag the cursor along with it.
        orig_pos = cursor.position()

        cursor.beginEditBlock()
        cursor.movePosition(QTextCursor.EndOfBlock)
        if cursor.block().text() != "" or cursor.block().blockFormat().hasProperty(HR_PROP):
            cursor.insertBlock()

        hr_fmt = QTextBlockFormat()
        hr_fmt.setProperty(HR_PROP, True)
        cursor.setBlockFormat(hr_fmt)
        cursor.setCharFormat(QTextCharFormat())
        cursor.endEditBlock()

        # No extra blank paragraph is inserted after the line - the caret
        # goes right back to where it was before the line was added.
        restore_cursor = QTextCursor(editor.document())
        restore_cursor.setPosition(orig_pos)
        editor.setTextCursor(restore_cursor)
        editor.setFocus()

    def insert_table(self):
        editor = self.get_editor()
        if not editor: return
        dialog = TableDialog(self)
        if dialog.exec() == QDialog.Accepted:
            rows, cols = dialog.get_data()
            cursor = editor.textCursor()
            # A bare insertTable(rows, cols) leaves every column's width
            # unconstrained, so Qt shrinks empty columns down to ~0px - the
            # table renders as a sliver of stacked cell backgrounds/borders
            # instead of a real grid. Explicitly stretch columns to share
            # the available width equally, and give cells padding/borders
            # so they're visible even before any text is typed into them.
            fmt = QTextTableFormat()
            fmt.setCellPadding(6)
            fmt.setCellSpacing(0)
            fmt.setBorder(1)
            fmt.setBorderStyle(QTextFrameFormat.BorderStyle_Solid)
            fmt.setBorderBrush(QColor("#555555"))
            fmt.setColumnWidthConstraints(
                [QTextLength(QTextLength.VariableLength, 0)] * cols
            )
            cursor.insertTable(rows, cols, fmt)
            editor.style_tables()

    def open_table_editor(self):
        editor = self.get_editor()
        if not editor: return
        cursor = editor.textCursor()
        table = cursor.currentTable()
        if not table: return
        
        cell = table.cellAt(cursor)
        row = cell.row()
        col = cell.column()
        
        dialog = QDialog(self)
        dialog.setWindowTitle("Edit Table")
        layout = QVBoxLayout(dialog)
        
        btn_add_row = QPushButton("Add row below cursor")
        btn_add_row.clicked.connect(lambda: (table.insertRows(row + 1, 1), editor.style_tables()))
        layout.addWidget(btn_add_row)
        
        btn_del_row = QPushButton("Delete cursor row")
        def del_row():
            if table.rows() > 1: table.removeRows(row, 1)
            editor.style_tables()
        btn_del_row.clicked.connect(del_row)
        layout.addWidget(btn_del_row)
        
        btn_add_col = QPushButton("Add column to the right")
        btn_add_col.clicked.connect(lambda: (table.insertColumns(col + 1, 1), editor.style_tables()))
        layout.addWidget(btn_add_col)
        
        btn_del_col = QPushButton("Delete cursor column")
        def del_col():
            if table.columns() > 1: table.removeColumns(col, 1)
            editor.style_tables()
        btn_del_col.clicked.connect(del_col)
        layout.addWidget(btn_del_col)

        # Text alignment - per-TABLE override (stored on this table's own
        # format via TABLE_HEADER_ALIGN_PROP/TABLE_ROW_ALIGN_PROP). The
        # app-wide default lives in Preferences > General and is what a
        # table uses until this combo is changed for it specifically.
        align_row = QWidget()
        align_form = QFormLayout(align_row)
        align_form.setContentsMargins(0, 0, 0, 0)

        table_fmt = table.format()

        def make_align_combo(prop, settings_key):
            combo = QComboBox()
            combo.addItem("Left", "left")
            combo.addItem("Center", "center")
            combo.addItem("Right", "right")
            current = table_fmt.property(prop) if table_fmt.hasProperty(prop) \
                else self.settings.get(settings_key, "left")
            idx = combo.findData(current)
            combo.setCurrentIndex(idx if idx >= 0 else 0)

            def on_change(_, prop=prop):
                fmt = table.format()
                fmt.setProperty(prop, combo.currentData())
                table.setFormat(fmt)
                editor.style_tables()
            combo.currentIndexChanged.connect(on_change)
            return combo

        align_form.addRow("First row text alignment:",
                           make_align_combo(TABLE_HEADER_ALIGN_PROP, "table_header_align"))
        align_form.addRow("Other rows text alignment:",
                           make_align_combo(TABLE_ROW_ALIGN_PROP, "table_row_align"))
        layout.addWidget(align_row)

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(dialog.accept)
        layout.addWidget(btn_close)
        
        dialog.exec()
        editor.style_tables()

    def insert_link(self):
        editor = self.get_editor()
        if not editor: return
        cursor = editor.textCursor()
        selected_text = cursor.selectedText() if cursor.hasSelection() else ""
        
        if cursor.charFormat().isAnchor():
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(self.settings['editor_text']))
            fmt.setAnchor(False)
            fmt.setAnchorHref("")
            fmt.setFontUnderline(False)
            cursor.mergeCharFormat(fmt)
            editor.setTextCursor(cursor)
            return

        dialog = LinkDialog(selected_text, "https://", self)
        if dialog.exec() == QDialog.Accepted:
            text, url = dialog.get_data()
            if text and url:
                fmt = QTextCharFormat()
                fmt.setAnchor(True)
                fmt.setAnchorHref(url)
                fmt.setForeground(QColor(self.settings['link']))
                fmt.setFontUnderline(self.settings.get("link_underline", True))
                cursor.insertText(text, fmt)
                editor.setTextCursor(cursor)

    def edit_link_from_menu(self, editor, cursor, old_text, old_url):
        # allow_remove=True adds a "Remove Link" button, so removing a
        # hyperlink no longer depends on fiddling with selections/toolbar
        # toggles - it's always available right here.
        dialog = LinkDialog(old_text, old_url, self, allow_remove=True)
        if dialog.exec() == QDialog.Accepted:
            if dialog.is_removed():
                self.remove_hyperlink(editor, cursor)
                return
            new_text, new_url = dialog.get_data()
            if new_text and new_url:
                fmt = QTextCharFormat()
                fmt.setAnchor(True)
                fmt.setAnchorHref(new_url)
                fmt.setForeground(QColor(self.settings['link']))
                fmt.setFontUnderline(self.settings.get("link_underline", True))
                cursor.insertText(new_text, fmt)
                editor.setTextCursor(cursor)

    def remove_hyperlink(self, editor, cursor):
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(self.settings['editor_text']))
        fmt.setAnchor(False)
        fmt.setAnchorHref("")
        fmt.setFontUnderline(False)
        cursor.mergeCharFormat(fmt)
        editor.setTextCursor(cursor)

    # --- Remove <format> from context menu (PPM > Remove Bold/Headline/etc.) ---
    def remove_bold_format(self, editor, run_cursor):
        fmt = QTextCharFormat()
        fmt.setFontWeight(QFont.Normal)
        fmt.setForeground(QColor(self.settings['editor_text']))
        run_cursor.mergeCharFormat(fmt)
        editor.setTextCursor(run_cursor)
        self.update_toolbar_state()

    def remove_italic_format(self, editor, run_cursor):
        fmt = QTextCharFormat()
        fmt.setFontItalic(False)
        fmt.setForeground(QColor(self.settings['editor_text']))
        run_cursor.mergeCharFormat(fmt)
        editor.setTextCursor(run_cursor)
        self.update_toolbar_state()

    def remove_underline_format(self, editor, run_cursor):
        fmt = QTextCharFormat()
        fmt.setFontUnderline(False)
        fmt.setForeground(QColor(self.settings['editor_text']))
        run_cursor.mergeCharFormat(fmt)
        editor.setTextCursor(run_cursor)
        self.update_toolbar_state()

    def remove_code_format(self, editor, run_cursor):
        fmt = QTextCharFormat()
        fmt.setBackground(Qt.transparent)
        fmt.setForeground(QColor(self.settings['editor_text']))
        fmt.setFontFamilies([self.settings['font_family']])
        fmt.setProperty(CODE_PROP, False)
        run_cursor.mergeCharFormat(fmt)
        editor.setTextCursor(run_cursor)
        self.update_toolbar_state()

    def remove_code_block_format(self, editor, block):
        cursor = QTextCursor(block)
        cursor.movePosition(QTextCursor.StartOfBlock)
        cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
        block_fmt = QTextBlockFormat(block.blockFormat())
        block_fmt.setProperty(BLOCK_CODE_PROP, False)
        block_fmt.setBackground(Qt.transparent)
        char_fmt = QTextCharFormat()
        char_fmt.setForeground(QColor(self.settings['editor_text']))
        char_fmt.setFontFamilies([self.settings['font_family']])
        char_fmt.setProperty(CODE_PROP, False)
        char_fmt.setBackground(Qt.transparent)
        cursor.beginEditBlock()
        cursor.setBlockFormat(block_fmt)
        cursor.mergeCharFormat(char_fmt)
        cursor.endEditBlock()
        editor.setTextCursor(cursor)
        self.update_toolbar_state()

    def remove_quote_format(self, editor, block):
        cursor = QTextCursor(block)
        cursor.movePosition(QTextCursor.StartOfBlock)
        cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
        block_fmt = QTextBlockFormat(block.blockFormat())
        block_fmt.setLeftMargin(0)
        block_fmt.setProperty(QUOTE_PROP, False)
        char_fmt = QTextCharFormat()
        char_fmt.setFontItalic(False)
        char_fmt.setForeground(QColor(self.settings['editor_text']))
        cursor.beginEditBlock()
        cursor.setBlockFormat(block_fmt)
        cursor.mergeCharFormat(char_fmt)
        cursor.endEditBlock()
        editor.setTextCursor(cursor)
        self.update_toolbar_state()

    def remove_heading_format(self, editor, block):
        cursor = QTextCursor(block)
        cursor.movePosition(QTextCursor.StartOfBlock)
        cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
        block_fmt = QTextBlockFormat(block.blockFormat())
        block_fmt.setHeadingLevel(0)
        char_fmt = QTextCharFormat()
        char_fmt.setFontPointSize(self.settings["font_size"])
        char_fmt.setForeground(QColor(self.settings["editor_text"]))
        char_fmt.setFontWeight(QFont.Normal)
        cursor.beginEditBlock()
        cursor.setBlockFormat(block_fmt)
        cursor.mergeCharFormat(char_fmt)
        cursor.endEditBlock()
        editor.setTextCursor(cursor)
        self.update_toolbar_state()

    # --- Keyboard shortcuts for lines ---
    def duplicate_line(self):
        editor = self.get_editor()
        if not editor: return
        cursor = editor.textCursor()
        if cursor.currentTable(): return
        cursor.beginEditBlock()
        cursor.movePosition(QTextCursor.StartOfLine)
        start = cursor.position()
        cursor.movePosition(QTextCursor.EndOfLine)
        end = cursor.position()
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.KeepAnchor)
        line_text = cursor.selectedText()
        cursor.movePosition(QTextCursor.EndOfLine)
        cursor.insertText("\n" + line_text)
        cursor.endEditBlock()

    def move_line(self, direction):
        editor = self.get_editor()
        if not editor: return
        cursor = editor.textCursor()
        if cursor.currentTable(): return
        cursor.beginEditBlock()
        cursor.movePosition(QTextCursor.StartOfBlock)
        start_pos = cursor.position()
        orig_cursor = editor.textCursor()
        rel_pos = orig_cursor.position() - start_pos
        curr_block = cursor.block()
        curr_fmt = curr_block.blockFormat()
        cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
        curr_frag = cursor.selection()
        
        if direction == 1:
            next_block = curr_block.next()
            if not next_block.isValid(): 
                cursor.endEditBlock()
                return
            next_fmt = next_block.blockFormat()
            cursor.setPosition(next_block.position())
            cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
            next_frag = cursor.selection()
            cursor.insertFragment(curr_frag)
            cursor.setBlockFormat(curr_fmt)
            cursor.setPosition(start_pos)
            cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
            cursor.insertFragment(next_frag)
            cursor.setBlockFormat(next_fmt)
            cursor.setPosition(next_block.position() + rel_pos)
        elif direction == -1:
            prev_block = curr_block.previous()
            if not prev_block.isValid(): 
                cursor.endEditBlock()
                return
            prev_fmt = prev_block.blockFormat()
            cursor.setPosition(prev_block.position())
            cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
            prev_frag = cursor.selection()
            cursor.insertFragment(curr_frag)
            cursor.setBlockFormat(curr_fmt)
            cursor.setPosition(start_pos)
            cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
            cursor.insertFragment(prev_frag)
            cursor.setBlockFormat(prev_fmt)
            cursor.setPosition(prev_block.position() + rel_pos)
        cursor.endEditBlock()
        editor.setTextCursor(cursor)

    # --- Update toolbar state ---
    def update_toolbar_state(self):
        editor = self.get_editor()
        if not editor: return
        cursor = editor.textCursor()
        char_fmt = cursor.charFormat()
        block_fmt = cursor.blockFormat()
        line_text = cursor.block().text().strip()
        
        for i in range(1, 7):
            self.h_actions[i].blockSignals(True)
            self.h_actions[i].setChecked(block_fmt.headingLevel() == i)
            self.h_actions[i].blockSignals(False)
            
        self.act_bold.blockSignals(True)
        self.act_italic.blockSignals(True)
        self.act_underline.blockSignals(True)
        self.act_code.blockSignals(True)
        self.act_quote.blockSignals(True)
        self.act_link.blockSignals(True)
        self.act_ul.blockSignals(True)
        self.act_ol.blockSignals(True)

        self.act_bold.setChecked(char_fmt.fontWeight() == QFont.Bold)
        self.act_italic.setChecked(char_fmt.fontItalic())
        self.act_underline.setChecked(char_fmt.fontUnderline())
        self.act_code.setChecked((char_fmt.hasProperty(CODE_PROP) and char_fmt.property(CODE_PROP) == True) or (block_fmt.hasProperty(BLOCK_CODE_PROP) and block_fmt.property(BLOCK_CODE_PROP) == True))
        self.act_quote.setChecked(block_fmt.hasProperty(QUOTE_PROP) and block_fmt.property(QUOTE_PROP) == True)
        self.act_link.setChecked(char_fmt.isAnchor())
        
        is_ul = line_text.startswith("• ") or line_text.startswith("- ") or line_text.startswith("* ")
        self.act_ul.setChecked(is_ul)
        
        is_ol = len(line_text) > 2 and line_text[0].isdigit() and line_text[1] == '.' and line_text[2] == ' '
        self.act_ol.setChecked(is_ol)

        self.act_bold.blockSignals(False)
        self.act_italic.blockSignals(False)
        self.act_underline.blockSignals(False)
        self.act_code.blockSignals(False)
        self.act_quote.blockSignals(False)
        self.act_link.blockSignals(False)
        self.act_ul.blockSignals(False)
        self.act_ol.blockSignals(False)

        self.update_view_menu_state()
        self.update_formatting_actions_enabled()

    def update_view_menu_state(self):
        editor = self.get_editor()
        if not editor: return
        self.act_view_formatted.blockSignals(True)
        self.act_view_plain.blockSignals(True)
        if editor.view_mode == "plain":
            self.act_view_plain.setChecked(True)
        else:
            self.act_view_formatted.setChecked(True)
        self.act_view_formatted.blockSignals(False)
        self.act_view_plain.blockSignals(False)

    def update_formatting_actions_enabled(self):
        editor = self.get_editor()
        is_plain = bool(editor) and editor.view_mode == "plain"
        actions = [self.act_bold, self.act_italic, self.act_underline, self.act_code,
                   self.act_quote, self.act_ul, self.act_ol, self.act_table,
                   self.act_hr, self.act_link] + list(self.h_actions.values())
        for action in actions:
            action.setEnabled(not is_plain)

    def set_view_mode(self, mode):
        editor = self.get_editor()
        if not editor or editor.view_mode == mode:
            self.update_view_menu_state()
            return

        had_focus = editor.hasFocus()
        if had_focus:
            editor.clearFocus()
        editor._caret_visible = False
        editor.viewport().repaint()

        was_modified = editor.document().isModified()
        editor.document().setUndoRedoEnabled(False)
        editor.setExtraSelections([])

        if mode == "plain":
            # Show the exact markdown source that File > Save would write,
            # in a flat, uncolored style - no rich formatting to keep in
            # sync while the user edits raw syntax directly. This mirrors
            # a plain text editor like Notepad++: what's on screen here
            # is exactly what's on disk, syntax characters included.
            md_text = self.export_markdown(editor)
            editor.setPlainText(md_text)

            flat_fmt = QTextCharFormat()
            flat_fmt.setForeground(QColor(self.settings['editor_text']))
            flat_fmt.setFontFamilies([self.settings['font_family']])
            flat_fmt.setFontPointSize(self.settings['font_size'])
            flat_fmt.setFontWeight(QFont.Normal)
            flat_fmt.setFontItalic(False)
            flat_fmt.setFontUnderline(False)
            flat_fmt.setBackground(Qt.transparent)
            # Custom properties (CODE_PROP here - the only char-level one;
            # QUOTE_PROP/BLOCK_CODE_PROP/HR_PROP are block-level and are
            # already gone since setPlainText() above rebuilds the blocks
            # from scratch) aren't touched by properties simply left unset
            # on flat_fmt, so it's spelled out explicitly rather than
            # relying on it defaulting to "off".
            flat_fmt.setProperty(CODE_PROP, False)
            # Anchor state (link color/underline/href) is explicitly
            # cleared too, for the same reason - otherwise leftover anchor
            # formatting from whatever the editor's live cursor last had
            # active can carry into the freshly-typed plain text.
            flat_fmt.setAnchor(False)
            flat_fmt.setAnchorHref("")
            select_cursor = QTextCursor(editor.document())
            select_cursor.select(QTextCursor.Document)
            # setCharFormat() (not mergeCharFormat()) so this is a full
            # replace: every character in Plain Text view ends up with
            # exactly flat_fmt and nothing else, instead of flat_fmt
            # merged on top of whatever format happened to still be
            # active - the previous merge-based approach could leave
            # invisible leftover formatting (most notably CODE_PROP)
            # sitting on characters that looked plain on screen.
            select_cursor.setCharFormat(flat_fmt)
        else:
            # Route back through the same normalization used for File >
            # Open (currently: <br>/<br/> line-break-tag handling), so
            # raw markdown typed or edited by hand in plain-text mode
            # reads back the same way a saved-and-reopened file would.
            text = self.preprocess_markdown(editor.toPlainText())
            editor.document().setMarkdown(text, QTextDocument.MarkdownDialectGitHub)
            editor.post_process_markdown()
            editor.apply_settings_to_document(restore_cursor=False)
            editor.style_tables()

        editor.view_mode = mode

        start_cursor = QTextCursor(editor.document())
        start_cursor.movePosition(QTextCursor.Start)
        editor.setTextCursor(start_cursor)

        editor.document().setUndoRedoEnabled(True)
        editor.document().setModified(was_modified)

        self.update_view_menu_state()
        self.update_formatting_actions_enabled()

        if had_focus:
            editor.setFocus(Qt.OtherFocusReason)

        def _finish_view_switch(ed=editor):
            ed.ensureCursorVisible()
            ed._reset_caret_blink()
            ed.line_number_area.update()
        QTimer.singleShot(0, _finish_view_switch)

    def open_find_replace(self):
        if self.find_dialog is None:
            self.find_dialog = FindReplaceDialog(self)
        self.find_dialog.show()
        self.find_dialog.raise_()
        self.find_dialog.activateWindow()

    def open_settings(self):
        dialog = SettingsDialog(self.settings, self)
        if dialog.exec() == QDialog.Accepted:
            self.settings.update(dialog.get_settings())
            self.save_settings()
            self.apply_app_theme()
            self.refresh_toolbar_icons()
            
            for i in range(self.tab_widget.count()):
                editor = self.tab_widget.widget(i)
                editor.settings = self.settings
                editor.apply_settings()
                editor.apply_settings_to_document()
                editor.style_tables()
                editor.viewport().update()
                editor.highlight_current_line()
            
            self.update_toolbar_margin()

    def open_preferences(self):
        dialog = PreferencesDialog(self.settings, self)
        if dialog.exec() == QDialog.Accepted:
            self.settings.update(dialog.get_settings())
            self.save_settings()
            # Preferences edited spell-check languages and/or the personal
            # dictionary directly in self.settings - sync SpellCheckManager's
            # in-memory state (and reload/rehighlight) to match.
            self.spell_manager.set_custom_words(self.settings.get("spellcheck_custom_words", []))
            self.spell_manager.set_languages(self.settings.get("spellcheck_langs", ["pl_PL"]))

            # Re-apply table styling in every open tab so a changed default
            # alignment shows immediately on tables that haven't been given
            # their own alignment via Edit Table (apply_table_style() only
            # falls back to this default for tables without that override,
            # so tables customized locally are left alone).
            for i in range(self.tab_widget.count()):
                editor = self.tab_widget.widget(i)
                editor.settings = self.settings
                editor.style_tables()


if __name__ == "__main__":
    app = QApplication(sys.argv)

    # Set this as early as possible, before any Editor/QTextEdit is
    # constructed, so Qt's internal cursor-blink machinery never gets a
    # chance to read a nonzero flash time in the first place. Editor also
    # re-asserts this on every focusInEvent() as a defensive measure, since
    # Windows can re-sync style hints from the system theme later on.
    app.setCursorFlashTime(0)

    icon_path = os.path.join("icons", "notepad_yellow_icon.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
        
    window = MainWindow()
    window.show()

    # Support `python MPadPlusPlus.py file1.md file2.md ...` - anything
    # after the script name (skipping option-like "-x" flags) is treated
    # as a file to open.
    cli_files = [arg for arg in sys.argv[1:] if not arg.startswith('-')]
    if cli_files:
        window.open_files_from_args(cli_files)

    sys.exit(app.exec())