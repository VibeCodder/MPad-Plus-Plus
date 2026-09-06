import sys
import json
import os
import re
import uuid
import webbrowser
import urllib.request
from collections import deque
from PySide6.QtWidgets import (QApplication, QMainWindow, QTextEdit, QVBoxLayout, 
                               QHBoxLayout, QWidget, QToolBar, QDialog, 
                               QLabel, QLineEdit, QDialogButtonBox, QColorDialog, 
                               QPushButton, QFormLayout, QSpinBox, QFontDialog, 
                               QMessageBox, QFileDialog, QMenu, QToolButton, QCheckBox,
                               QTabWidget, QTabBar, QSizePolicy, QScrollArea, QPlainTextEdit,
                               QRadioButton, QButtonGroup, QListWidget, QListWidgetItem,
                               QComboBox, QToolTip, QInputDialog)
from PySide6.QtGui import (QColor, QTextCharFormat, QTextBlockFormat, QTextListFormat,
                           QKeySequence, QShortcut, QFont, QFontMetrics, QPalette,
                           QAction, QActionGroup, QTextCursor, QDragEnterEvent, QDropEvent, 
                           QTextDocument, QBrush, QPainter, QTextFormat, QPen, QIcon, QPixmap,
                           QSyntaxHighlighter, QTextTableFormat, QTextLength, QTextFrameFormat,
                           QDesktopServices, QPyTextObject, QMovie, QImage)
from PySide6.QtCore import (QRegularExpression, Qt, QFileInfo, QPoint, QSize, QSizeF, QRect, QRectF,
                            QTimer, QObject, QThread, Signal, QUrl, QBuffer, QByteArray, QIODevice)

try:
    from PySide6.QtSvg import QSvgRenderer
except ImportError:
    # Toolbar icons degrade gracefully to text-only buttons if the
    # optional QtSvg module isn't installed alongside PySide6.
    QSvgRenderer = None

try:
    from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput, QVideoSink
    HAVE_MULTIMEDIA = True
except ImportError:
    # Embedded audio/video playback degrades gracefully (a placeholder
    # card with the file name is shown instead of a working player) if
    # the optional QtMultimedia module isn't installed alongside PySide6.
    # Install with: pip install PySide6-Addons
    QMediaPlayer = None
    QAudioOutput = None
    QVideoSink = None
    HAVE_MULTIMEDIA = False

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
LIST_BULLET_RE = re.compile(r'^(\s*)([•\-\*■])( +)(.*)$')
# Supports nested numbering like "2." (top level) or "2.1." / "2.1.3."
# (nested under it) - one leading tab per nesting level, then a
# dot-separated chain of numbers, a final dot, then the item's text. See
# Editor.keyPressEvent()'s Tab/Shift+Tab handling for how a line moves
# between levels and gets renumbered.
LIST_NUMBERED_RE = re.compile(r'^(\t*)((?:\d+\.)*\d+)\.( +)(.*)$')

def _parse_numbered_list_line(text):
    """Returns (depth, numbers, spacing, content) for a numbered-list
    line - depth is the nesting level (0 = top level), numbers is the
    list of int components of its label (e.g. [2, 1] for "2.1."). Returns
    None if the line isn't a numbered-list item at all."""
    m = LIST_NUMBERED_RE.match(text)
    if not m:
        return None
    indent, numbers_str, spacing, content = m.groups()
    return len(indent), [int(p) for p in numbers_str.split('.')], spacing, content

SPELLCHECK_WORD_RE = re.compile(r"[^\W\d_]+(?:['\u2019-][^\W\d_]+)*", re.UNICODE)
# Matches a single "word" character - used to tell whether the cursor is
# still sitting inside/next to a word (still typing it) versus having
# genuinely left it (space, punctuation, newline, click elsewhere).
SPELLCHECK_WORD_CHAR_RE = re.compile(r"[^\W\d_]", re.UNICODE)
# Above this many characters in a single block/paragraph, re-scanning
# every word in it (regex matching + per-word QTextCursor probing + cache
# lookups) on every single keystroke becomes measurable, scaling work on
# the GUI thread even though each individual check is cheap in isolation -
# see SpellCheckHighlighter.highlightBlock().
SPELLCHECK_LARGE_BLOCK_CHARS = 200


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
    # Alignment every column of a brand-new table (Insert > Table) starts
    # with. This only seeds the initial state - once the table exists, its
    # alignment lives in the table itself (real Markdown ":---"/"---:"/
    # ":---:" markers, see set_table_column_alignment()), same as if the
    # user had picked it per-column from Edit Table right after creating it.
    "table_default_align": "left",
    
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

    # Minimum display width (px) for embedded media objects, per type.
    # A media object is never rendered narrower than this, even if its
    # natural (or scaled) size would otherwise be smaller - height follows
    # proportionally, so aspect ratio is always preserved. 0 disables the
    # minimum for that type. See Settings > Preferences > General.
    "media_min_width_image": 0,
    "media_min_width_gif": 0,
    "media_min_width_video": 0,
}

CODE_PROP = QTextFormat.UserProperty + 1
QUOTE_PROP = QTextFormat.UserProperty + 2
BLOCK_CODE_PROP = QTextFormat.UserProperty + 3
HR_PROP = QTextFormat.UserProperty + 4

# --- Embedded media (images / gifs / video / audio) ---
# Rendered as a single custom QTextObjectInterface object (a "media object")
# occupying one ObjectReplacementCharacter, so it flows inline with the rest
# of the document like any other character while being painted as a real
# picture, animated gif, or a small audio/video player. The underlying
# Markdown syntax is always the standard image syntax: ![alt](src).
MEDIA_TYPE_PROP = QTextFormat.UserProperty + 10   # "image" | "gif" | "video" | "audio"
MEDIA_SRC_PROP = QTextFormat.UserProperty + 11    # the path/URL exactly as written in the source
MEDIA_ALT_PROP = QTextFormat.UserProperty + 12    # the "alt" display text between the [ ]
MEDIA_ID_PROP = QTextFormat.UserProperty + 13     # unique id, used to look up the live player/movie
MEDIA_SCALE_PROP = QTextFormat.UserProperty + 14  # float, display-size multiplier set from the "Settings" > resize menu (default 1.0)
MEDIA_OBJECT_TYPE = QTextFormat.UserObject + 1
MEDIA_SCALE_MIN = 0.1
MEDIA_SCALE_MAX = 4.0

IMAGE_MEDIA_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".svg", ".ico", ".tif", ".tiff"}
GIF_MEDIA_EXTENSIONS = {".gif"}
VIDEO_MEDIA_EXTENSIONS = {".mp4", ".avi", ".mkv", ".mov", ".webm", ".wmv", ".flv", ".m4v", ".mpg", ".mpeg"}
AUDIO_MEDIA_EXTENSIONS = {".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac", ".wma", ".opus"}
MEDIA_MAX_WIDTH = 480


def _is_url(src):
    return bool(re.match(r"^[a-zA-Z][a-zA-Z0-9+.\-]*://", src or ""))


def classify_media_path(src):
    """Return "image"/"gif"/"video"/"audio" for a path or URL recognized as
    an embeddable media file by its extension, or None for anything else
    (which should be treated as a plain hyperlink instead)."""
    if not src:
        return None
    clean = src
    if _is_url(clean):
        clean = clean.split("?", 1)[0].split("#", 1)[0]
    ext = os.path.splitext(clean)[1].lower()
    if ext in IMAGE_MEDIA_EXTENSIONS:
        return "image"
    if ext in GIF_MEDIA_EXTENSIONS:
        return "gif"
    if ext in VIDEO_MEDIA_EXTENSIONS:
        return "video"
    if ext in AUDIO_MEDIA_EXTENSIONS:
        return "audio"
    return None


def resolve_media_path(src, base_dir):
    """Resolve a media source exactly like it should be interpreted:
    - a URL (http://, https://, ...) is returned unchanged
    - an absolute local path (C:\\..., /..., a file:// URI, ~/...) is
      returned as an absolute path
    - anything else (".\\pic.png", "pic.png", "..\\folder\\a.mp4") is
      treated as relative to the folder the current .md document is saved
      in (falling back to the current working directory if the document
      hasn't been saved yet)
    Returns (resolved_path_or_url, is_remote_url).
    """
    if not src:
        return src, False
    if src.startswith("file:///") or src.startswith("file://"):
        # Checked before the generic _is_url() test below - "file://" also
        # matches a generic "scheme://" pattern, but it's a local path in
        # disguise, not something to fetch over the network.
        return os.path.normpath(QUrl(src).toLocalFile()), False
    if _is_url(src):
        return src, True
    # Accept both "\" and "/" as a separator regardless of the OS this
    # happens to run on, since Markdown written on Windows (the primary
    # target platform, hence examples like "C:\Videos\video.mp4") is
    # routinely opened/edited elsewhere too.
    path = src.replace("\\", "/")
    path = os.path.expanduser(path)
    is_windows_abs = bool(re.match(r"^[a-zA-Z]:[\\/]", path))
    is_unc = path.startswith("//")
    if not (os.path.isabs(path) or is_windows_abs or is_unc):
        base = base_dir or os.getcwd()
        path = os.path.normpath(os.path.join(base, path))
    return path, False


_MD_IMAGE_SYNTAX_RE = re.compile(r'!\[([^\]]*)\]\(([^)]+)\)')


def extract_media_alt_map(content):
    """Scan raw Markdown source (outside fenced code blocks) for
    ![alt](src) occurrences, in document order, and return them as a list
    of (alt, src) tuples. Needed because Qt's own Markdown importer parses
    this same syntax into an image but silently discards the alt text -
    this is the only way to recover it, matched back up by position right
    after setMarkdown() runs (see Editor.replace_media_placeholders)."""
    results = []
    in_code_block = False
    for line in content.split('\n'):
        stripped = line.lstrip()
        if stripped.startswith('```'):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue
        for m in _MD_IMAGE_SYNTAX_RE.finditer(line):
            alt, src = m.group(1), m.group(2).strip()
            src = src.split(' ', 1)[0].strip('<>')  # drop an optional "title" and any <...> wrapping
            results.append((alt, src))
    return results

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
    "media": """
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20">
          <defs><clipPath id="mediaScreenClip"><rect x="2.5" y="6" width="15" height="10" rx="1.3"/></clipPath></defs>
          <path fill="none" stroke="{color}" stroke-width="1.6" stroke-linecap="round"
                d="M6.5 3.2 3.3 6.2 M13.5 3.2 16.7 6.2"/>
          <g clip-path="url(#mediaScreenClip)">
            <rect fill="{color}" opacity="0.15" x="2.5" y="6" width="15" height="10"/>
            <circle fill="{color}" cx="13.1" cy="9.1" r="1.3"/>
            <path fill="{color}" d="M2.5 16 6.5 10.1 9 12.8 11.5 9.5 17.5 16 Z"/>
          </g>
          <rect fill="none" stroke="{color}" stroke-width="1.6" x="2.5" y="6" width="15" height="10" rx="1.3"/>
          <rect fill="{color}" x="7.7" y="16.6" width="4.6" height="1.1" rx="0.5"/>
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

class _MediaDownloadThread(QThread):
    """Downloads a remote image/gif (http:// or https://) off the UI
    thread, so a slow or unreachable URL never freezes the editor. Video
    and audio don't need this - QMediaPlayer streams URLs on its own."""
    finished_download = Signal(str, object)  # src, bytes or None

    def __init__(self, src, parent=None):
        super().__init__(parent)
        self.src = src

    def run(self):
        data = None
        try:
            req = urllib.request.Request(self.src, headers={"User-Agent": "Mozilla/5.0 (MPad++)"})
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = resp.read()
        except Exception:
            data = None
        self.finished_download.emit(self.src, data)


class MediaPlayerController(QObject):
    """Owns the actual QMediaPlayer for one embedded audio/video object and
    exposes just what the inline player needs to draw and to react to
    clicks: play/pause, current position, and (for video) the latest
    decoded frame as a QImage."""
    changed = Signal()

    def __init__(self, media_type, source, is_remote, parent=None):
        super().__init__(parent)
        self.media_type = media_type
        self.current_frame = None
        self.error_text = None
        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.player.setAudioOutput(self.audio_output)
        self.video_sink = None
        if media_type == "video":
            self.video_sink = QVideoSink(self)
            self.player.setVideoSink(self.video_sink)
            self.video_sink.videoFrameChanged.connect(self._on_frame)
        self.player.setSource(QUrl(source) if is_remote else QUrl.fromLocalFile(source))
        self.player.positionChanged.connect(lambda _v: self.changed.emit())
        self.player.durationChanged.connect(lambda _v: self.changed.emit())
        self.player.playbackStateChanged.connect(lambda _v: self.changed.emit())
        self.player.errorOccurred.connect(self._on_error)

    def _on_error(self, _error, error_string):
        self.error_text = error_string or "unknown error"
        self.changed.emit()

    def _on_frame(self, frame):
        if frame.isValid():
            img = frame.toImage()
            if not img.isNull():
                self.current_frame = img
        self.changed.emit()

    def toggle_play(self):
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def is_playing(self):
        return self.player.playbackState() == QMediaPlayer.PlayingState

    def position_fraction(self):
        dur = self.player.duration()
        return (self.player.position() / dur) if dur > 0 else 0.0

    def seek_fraction(self, frac):
        dur = self.player.duration()
        if dur > 0:
            self.player.setPosition(int(max(0.0, min(1.0, frac)) * dur))

    def time_text(self):
        def fmt(ms):
            s = max(0, ms) // 1000
            return f"{s // 60:02d}:{s % 60:02d}"
        return f"{fmt(self.player.position())} / {fmt(self.player.duration())}"

    def stop_and_release(self):
        try:
            self.player.stop()
        except Exception:
            pass


class MediaTextObject(QPyTextObject):
    """QTextObjectInterface handler registered on each Editor's document
    layout, responsible for sizing and painting every embedded media
    object (image/gif/video/audio). Actual sizing/loading/drawing logic
    lives on the Editor itself (see Editor.media_intrinsic_size /
    Editor.draw_media_object) so it has easy access to per-tab caches.
    Uses QPyTextObject (PySide's QObject+QTextObjectInterface combo
    helper) rather than plain multiple inheritance - the latter silently
    never gets its intrinsicSize()/drawObject() invoked by Qt's layout
    engine in PySide6."""

    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor

    def intrinsicSize(self, doc, posInDocument, fmt):
        return self.editor.media_intrinsic_size(fmt)

    def drawObject(self, painter, rect, doc, posInDocument, fmt):
        self.editor.draw_media_object(painter, rect, fmt)


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


class _CorrectnessCheckThread(QThread):
    """Looks up a batch of words in the loaded dictionaries off the GUI
    thread. phunspell.lookup() does real affix/morphology analysis (not
    just a hash check), and SpellCheckHighlighter.highlightBlock() -
    which calls it - is invoked by Qt synchronously, on the GUI thread,
    after every single keystroke. Running the lookups here instead means
    highlightBlock() itself never blocks on dictionary work: it only
    reads/writes a plain dict cache and hands off anything not yet known
    to this thread, so typing stays responsive regardless of how heavy
    the underlying dictionary check is or how long the paragraph is."""
    ready = Signal(dict)  # word_lower -> bool

    def __init__(self, words, dictionaries, parent=None):
        super().__init__(parent)
        self.words = words
        self.dictionaries = dictionaries

    def run(self):
        results = {}
        for word in self.words:
            correct = False
            for dictionary in self.dictionaries:
                try:
                    if dictionary.lookup(word):
                        correct = True
                        break
                except Exception:
                    correct = True
                    break
            results[word.lower()] = correct
        self.ready.emit(results)


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
        self._suggestion_inflight = set()   # cache keys currently running or queued
        self._suggestion_queue = []         # (key, word, limit) waiting for a free thread slot
        self._max_concurrent_suggestion_threads = 2
        self.custom_words = set(w.lower() for w in settings.get("spellcheck_custom_words", []))
        # (lang_codes, word_lower) -> bool. QSyntaxHighlighter re-runs
        # highlightBlock() for the WHOLE current block/paragraph on every
        # single edit, not just for the word that actually changed - so
        # without caching, every other, unchanged word already in that
        # paragraph gets re-looked-up in the dictionary on every keystroke
        # too (phunspell's lookup does real affix/morphology analysis, not
        # just a hash check, so this was the main source of the typing lag
        # reported with spell check on for longer lines). A word's
        # correctness never changes on its own, so caching it here makes
        # every repeat check an instant dict lookup regardless of how often
        # the surrounding paragraph gets reformatted.
        self._correctness_cache = {}
        self._correctness_inflight = set()   # (lang_key, word_lower) currently being checked
        self._correctness_threads = []
        self._correctness_queue = []   # (words, lang_key, on_done) batches waiting for a free slot
        self._max_concurrent_correctness_threads = 1
        # See check_words_async(): caps how many words go into a single
        # background lookup batch, so one huge block (e.g. a document
        # with no blank-line paragraph breaks, which becomes one giant
        # QTextBlock) can't turn into one multi-second, all-or-nothing
        # background run before anything on screen updates.
        self._CORRECTNESS_CHUNK_WORDS = 150

    def _invalidate_correctness_cache(self):
        self._correctness_cache.clear()

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
        self._invalidate_correctness_cache()
        self.dictionary_changed.emit()

    def set_languages(self, lang_codes):
        lang_codes = list(lang_codes) or ["en_US"]
        self.settings["spellcheck_langs"] = lang_codes
        if self.enabled:
            for code in lang_codes:
                self._ensure_loaded(code)
        self._invalidate_correctness_cache()
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
        self._invalidate_correctness_cache()
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
        self._invalidate_correctness_cache()
        self.dictionary_changed.emit()

    def remove_custom_word(self, word):
        self.custom_words.discard(word.lower())
        self.settings["spellcheck_custom_words"] = sorted(self.custom_words)
        self._invalidate_correctness_cache()
        self.dictionary_changed.emit()

    def set_custom_words(self, words):
        self.custom_words = set(w.lower() for w in words)
        self.settings["spellcheck_custom_words"] = sorted(self.custom_words)
        self._invalidate_correctness_cache()
        self.dictionary_changed.emit()

    def is_correct(self, word):
        """Blocking check - kept for callers that genuinely need an
        immediate answer (right-click menu, "add to dictionary", etc.),
        where a short synchronous dictionary lookup for a SINGLE word is
        fine. The highlighter itself uses is_correct_cached() +
        check_words_async() below instead, precisely to avoid ever
        blocking the GUI thread on this while the user is typing."""
        if self.is_custom_word(word):
            return True
        dictionaries = self.current_dictionaries()
        if not dictionaries:
            # No dictionary available/loaded yet: don't flag anything as
            # wrong until we can actually check it (avoids a flash of
            # false positives while a dictionary loads in the background).
            return True
        key = (tuple(sorted(self.lang_codes)), word.lower())
        cached = self._correctness_cache.get(key)
        if cached is not None:
            return cached
        result = False
        for dictionary in dictionaries:
            try:
                if dictionary.lookup(word):
                    result = True
                    break
            except Exception:
                result = True
                break
        self._correctness_cache[key] = result
        return result

    # Real dictionary words are essentially never this long; a token past
    # this length is almost certainly gibberish/an identifier/a paste
    # artifact, and phunspell's affix-stripping search over such a string
    # is exactly the pathological case that took noticeably longer the
    # longer the "word" got (as reported). Skipping it entirely - no
    # lookup, no underline - avoids that cost outright instead of just
    # moving it to a background thread.
    MAX_CHECKED_WORD_LEN = 25

    def is_correct_cached(self, word):
        """Non-blocking: returns True/False if already known, or None if
        this word hasn't been checked yet (and never touches the
        dictionary itself - safe to call from highlightBlock() on every
        keystroke). Custom words, absurdly long tokens, and the "no
        dictionary loaded" case all resolve immediately since none of them
        need an actual lookup."""
        if len(word) > self.MAX_CHECKED_WORD_LEN:
            return True
        if self.is_custom_word(word):
            return True
        dictionaries = self.current_dictionaries()
        if not dictionaries:
            return True
        key = (tuple(sorted(self.lang_codes)), word.lower())
        return self._correctness_cache.get(key)

    def check_words_async(self, words, on_done=None):
        """Kicks off a background dictionary lookup for any of `words`
        not already cached or already in flight. `on_done` fires once
        (on the GUI thread) after this batch's results are cached, so the
        caller (the highlighter) can re-trigger formatting for the block
        it came from now that the answers are ready.

        Only one lookup batch runs at a time (any more get queued) and
        that thread runs at LowPriority: a background QThread still
        shares the same Python interpreter/GIL as the GUI thread, so
        piling up several CPU-bound lookup threads at once - or letting
        one run at normal priority - can still starve the GUI thread of
        the interpreter time it needs to stay responsive while typing,
        even though the work is technically "off" the GUI thread. Keeping
        exactly one such thread active, at low priority, bounds how much
        of that contention can happen at once."""
        dictionaries = self.current_dictionaries()
        if not dictionaries:
            return
        lang_key = tuple(sorted(self.lang_codes))
        to_check = []
        seen_lower = set()
        for w in words:
            wl = w.lower()
            if wl in seen_lower:
                continue
            seen_lower.add(wl)
            key = (lang_key, wl)
            if key in self._correctness_cache or key in self._correctness_inflight:
                continue
            self._correctness_inflight.add(key)
            to_check.append(w)
        if not to_check:
            return
        self._correctness_threads = [t for t in self._correctness_threads if t.isRunning()]
        # A single call here can carry way more than a typical few-word
        # edit's worth of lookups - e.g. the very first check of a large
        # block that has no blank-line paragraph breaks (so the whole
        # document loads as ONE QTextBlock) hands over every word in the
        # entire document at once. Sending that as one lookup batch means
        # on_done - and therefore the highlighter's re-formatting of that
        # block - doesn't fire until every single word has been checked,
        # so nothing updates for however long the full batch takes, and
        # then everything appears at once. Slicing it into smaller pieces
        # queues several smaller batches instead (reusing the existing
        # one-thread-at-a-time queue below), so each piece's completion
        # triggers its own on_done - results, and underlines, start
        # trickling in well before the whole word list is done, and the
        # GUI gets a trip back through the event loop between pieces
        # instead of one long uninterrupted background run.
        chunk_size = self._CORRECTNESS_CHUNK_WORDS
        chunks = [to_check[i:i + chunk_size] for i in range(0, len(to_check), chunk_size)] or [to_check]
        for chunk in chunks:
            if len(self._correctness_threads) >= self._max_concurrent_correctness_threads:
                self._correctness_queue.append((chunk, lang_key, on_done))
                continue
            self._start_correctness_thread(chunk, dictionaries, lang_key, on_done)

    def _start_correctness_thread(self, to_check, dictionaries, lang_key, on_done):
        thread = _CorrectnessCheckThread(to_check, dictionaries, self)
        thread.ready.connect(lambda results, lk=lang_key, cb=on_done: self._on_correctness_ready(results, lk, cb))
        self._correctness_threads.append(thread)
        thread.start(QThread.LowPriority)

    def _on_correctness_ready(self, results, lang_key, on_done):
        for word_lower, correct in results.items():
            self._correctness_inflight.discard((lang_key, word_lower))
            self._correctness_cache[(lang_key, word_lower)] = correct
        if on_done:
            on_done()
        self._correctness_threads = [t for t in self._correctness_threads if t.isRunning()]
        if self._correctness_queue and len(self._correctness_threads) < self._max_concurrent_correctness_threads:
            next_words, next_lang_key, next_on_done = self._correctness_queue.pop(0)
            dictionaries = self.current_dictionaries()
            if dictionaries:
                self._start_correctness_thread(next_words, dictionaries, next_lang_key, next_on_done)

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

    def request_suggestions(self, word, limit=6, prefetch=False):
        """Non-blocking counterpart to suggestions(): returns cached
        suggestions immediately if available, otherwise kicks off a
        background computation (or queues it, see below) and returns
        None. `suggestions_ready` fires with the same word once the
        background thread finishes, so callers (the right-click menu)
        can open instantly with a placeholder instead of freezing while
        phunspell searches its dictionary, then fill in the real list a
        moment later.

        Only `_max_concurrent_suggestion_threads` suggestion searches run
        at once - phunspell's edit-distance search is CPU-heavy, so
        firing off unlimited threads (e.g. when the highlighter prefetches
        suggestions for every misspelled word on screen) would just make
        every one of them slower. Anything beyond that limit is queued;
        `prefetch=True` (used by the highlighter, see below) puts the
        request at the back of the queue, while an explicit ask - e.g. the
        right-click menu - jumps to the front so it isn't stuck waiting
        behind background work.

        Duplicate requests for the same (languages, word) are collapsed:
        if it's already running or queued, this just returns None again
        without spawning another thread; the eventual `suggestions_ready`
        covers every caller."""
        key = self._suggestion_cache_key(word)
        cached = self._suggestion_cache.get(key)
        if cached is not None:
            return cached
        if key in self._suggestion_inflight:
            return None  # already running or queued - suggestions_ready will fire once
        self._suggestion_inflight.add(key)
        self._suggestion_threads = [t for t in self._suggestion_threads if t.isRunning()]
        if len(self._suggestion_threads) >= self._max_concurrent_suggestion_threads:
            entry = (key, word, limit)
            if prefetch:
                self._suggestion_queue.append(entry)
            else:
                self._suggestion_queue.insert(0, entry)
            return None
        self._start_suggestion_thread(key, word, limit)
        return None

    def _start_suggestion_thread(self, key, word, limit):
        thread = _SuggestionLoaderThread(word, self.current_dictionaries(), limit, self)
        thread.ready.connect(lambda w, results, k=key: self._on_suggestions_ready(k, results))
        self._suggestion_threads.append(thread)
        # LowPriority for the same reason _start_correctness_thread() uses
        # it (see check_words_async's docstring): phunspell.suggest() is
        # even more CPU-heavy than a lookup() - it computes edit distances
        # against the whole dictionary - and a background QThread still
        # shares the GIL with the GUI thread. Left at normal priority, a
        # document/paste with many misspelled words at once (e.g. text in
        # a language not in the active dictionary) queues up suggestion
        # computation after suggestion computation, and those threads
        # winning the GIL over the GUI thread is what showed up as
        # freezing even though the work is technically "off" the GUI
        # thread.
        thread.start(QThread.LowPriority)

    def prefetch_suggestions(self, word, limit=6):
        """Warms the suggestion cache for `word` in the background without
        anyone waiting on it. Called by the highlighter as soon as a word
        is flagged misspelled, so that by the time the user actually
        right-clicks it, suggestions are often already sitting in the
        cache and the context menu can show them immediately instead of
        displaying "Loading suggestions..." while phunspell searches."""
        self.request_suggestions(word, limit, prefetch=True)

    def _on_suggestions_ready(self, key, results):
        self._suggestion_cache[key] = results
        self._suggestion_inflight.discard(key)
        self.suggestions_ready.emit(key[1], results)
        # A thread slot just freed up - start the next queued request, if any.
        self._suggestion_threads = [t for t in self._suggestion_threads if t.isRunning()]
        if self._suggestion_queue and len(self._suggestion_threads) < self._max_concurrent_suggestion_threads:
            next_key, next_word, next_limit = self._suggestion_queue.pop(0)
            self._start_suggestion_thread(next_key, next_word, next_limit)

    def shutdown(self):
        """Stop cleanly on app exit so no background QThread outlives
        the SpellCheckManager (which would print a Qt warning / risk a
        crash on interpreter shutdown)."""
        for thread in self._threads:
            thread.wait(2000)
        for thread in self._suggestion_threads:
            thread.wait(2000)
        for thread in self._correctness_threads:
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

        # --- Debounce the word currently being typed ---
        # QSyntaxHighlighter re-runs highlightBlock() synchronously, on the
        # GUI thread, after EVERY edit to that block - there's no supported
        # way to move it to a worker thread, since it has to mutate the live
        # QTextLayout formatting. For phunspell's dictionary lookup (which
        # does real morphological/affix analysis, not just a hash lookup -
        # especially costly for a heavily-inflected language like Polish),
        # that means every single keystroke while typing a word re-checks
        # that word (now one character longer/different) plus every other
        # word already in the block, and on a fast typist that per-keystroke
        # cost is exactly what showed up as visible input lag.
        # Skipping the dictionary lookup specifically for the word the
        # cursor is currently sitting inside - and checking it once, after a
        # short idle pause or as soon as the cursor leaves it - removes
        # nearly all of that redundant work (an in-progress word gets
        # checked once when you're done with it, not once per letter),
        # while every other word on screen keeps getting checked instantly
        # as before.
        self._skip_active_word = True
        self._pending_recheck_block = None
        self._pending_recheck_whole_block = False   # True = large-block deferral, not just one word
        self._debounce = QTimer(editor)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(300)
        self._debounce.timeout.connect(self._recheck_active_word)
        editor.cursorPositionChanged.connect(self._on_cursor_moved)

        # --- Bulk-load mode (whole-document freeze avoidance) ---
        # QSyntaxHighlighter has no supported way to move highlightBlock()
        # off the GUI thread - it mutates the live QTextLayout formatting
        # directly, so Qt always calls it synchronously, on the GUI thread,
        # one block at a time. Everything above already keeps each
        # individual highlightBlock() call cheap while *typing* (dictionary
        # lookups run on a background QThread; only a plain dict-cache read
        # happens synchronously). But a whole-document replace - opening a
        # large file, or the Formatted<->Plain Text view toggle re-parsing
        # the whole document via setMarkdown()/setPlainText() - makes Qt
        # call highlightBlock() for EVERY block in the document, back to
        # back, in one synchronous pass, before control ever returns to the
        # event loop. On a long document that pass itself - thousands of
        # regex scans plus per-word cache lookups, one block after another
        # with no chance to paint or process input in between - is what
        # shows up as the app freezing/stuttering ("zacina") specifically
        # on large text, even though nothing in it is individually slow.
        #
        # begin_bulk_load()/end_bulk_load() bracket those whole-document
        # replaces (see callers below). While bulk mode is on,
        # highlightBlock() does nothing at all (see the top of that method)
        # so Qt's forced synchronous pass over every block is reduced to a
        # no-op and returns instantly. end_bulk_load() then does the real
        # work itself, but spread out: a queue of every block number in the
        # document, drained a small chunk at a time via chained
        # QTimer.singleShot(0, ...) calls. Each chunk still runs on the GUI
        # thread (it has to), but returning to the event loop between
        # chunks lets Qt paint and handle input in between, so the document
        # visibly appears instantly and spelling underlines fill in over
        # the next moment instead of the whole app locking up.
        self._bulk_loading = False
        self._bulk_queue = deque()
        self._bulk_chunk_size = 40
        # True for the duration of each chunk drained by _process_bulk_chunk
        # (i.e. while highlightBlock() is running as part of the initial,
        # automatic pass over a freshly-opened/pasted document - not while
        # the user is actually looking at/editing a block). See
        # highlightBlock()'s use of this below: a document can easily
        # contain far more distinct misspelled words at once than a user
        # editing normally ever would (e.g. text in a language other than
        # the active dictionary, like this file's Lorem Ipsum test case),
        # and eagerly prefetching suggestions - a CPU-heavy edit-distance
        # search per word - for every single one of them during that
        # automatic pass is wasted work for words nobody has clicked on
        # yet, and was still enough queued background work (even at
        # LowPriority, even bounded to 2-at-a-time) to make the GUI thread
        # stutter. Suggestions are still computed on demand the moment the
        # user actually right-clicks a misspelled word (see
        # Editor._replace_spelling's caller), just not proactively for
        # words still off-screen or never interacted with.
        self._bulk_chunk_active = False
        self._bulk_generation = 0   # bumped on each begin/end so a stale
                                     # chained singleShot from a previous
                                     # bulk pass (e.g. tab closed/reopened
                                     # mid-pass) recognizes itself as stale
                                     # and stops instead of processing a
                                     # document it no longer applies to.

    def begin_bulk_load(self):
        """Call right before replacing the whole document (setMarkdown(),
        setPlainText()) so the forced synchronous highlightBlock() pass
        Qt is about to run over every block is a no-op instead of a
        freeze. Always pair with end_bulk_load() once the replace is
        done - use try/finally if anything between them could raise."""
        self._bulk_loading = True
        self._bulk_generation += 1
        self._bulk_queue.clear()
        self._pending_recheck_block = None
        self._pending_recheck_whole_block = False
        self._debounce.stop()

    def end_bulk_load(self):
        """Call right after the whole-document replace finishes. Queues
        every block in the new document and starts draining it in small
        chunks, off the immediate call stack, so real highlighting/spell
        checking fills in progressively without blocking the GUI thread
        for the whole document at once."""
        self._bulk_loading = False
        window = self.editor.window()
        manager = getattr(window, "spell_manager", None)
        if manager is None or not manager.enabled:
            return  # nothing to highlight - skip scheduling entirely
        doc = self.document()
        self._bulk_queue = deque(range(doc.blockCount()))
        generation = self._bulk_generation
        QTimer.singleShot(0, lambda g=generation: self._process_bulk_chunk(g))

    def _process_bulk_chunk(self, generation):
        # A newer begin_bulk_load()/end_bulk_load() pair (or the editor/
        # highlighter being torn down) has superseded this chain - drop it
        # rather than process a queue that's no longer current.
        if generation != self._bulk_generation or self._bulk_loading:
            return
        doc = self.document()
        processed = 0
        self._bulk_chunk_active = True
        try:
            while self._bulk_queue and processed < self._bulk_chunk_size:
                block_num = self._bulk_queue.popleft()
                block = doc.findBlockByNumber(block_num)
                if block.isValid():
                    self.rehighlightBlock(block)
                processed += 1
        finally:
            self._bulk_chunk_active = False
        if self._bulk_queue:
            QTimer.singleShot(0, lambda g=generation: self._process_bulk_chunk(g))

    def _on_cursor_moved(self):
        # This fires on EVERY cursor-position change - including the one
        # caused by simply typing the next letter of the same word, since
        # inserting a character moves the cursor too. It also fires once
        # per character on punctuation-dense text (many short word
        # fragments separated by commas/semicolons/etc., as reported) -
        # each fragment boundary counts as "leaving a word". Firing an
        # IMMEDIATE, synchronous rehighlightBlock() (a full re-scan of the
        # whole line) on every one of those crossings is what produced
        # visible lag specifically on that kind of text, even though plain
        # prose - far fewer, sparser boundaries - felt fine.
        #
        # Only ever restarting the SAME short idle timer here - never
        # firing immediately - means a rapid burst of boundary crossings
        # (typing "a,b,c,d,e,f,") collapses into exactly one
        # rehighlightBlock() call once things go quiet, instead of one per
        # comma. The cost is underlines appearing up to ~300ms after
        # finishing a word instead of instantly, which isn't perceptible.
        if self._pending_recheck_block is None:
            return
        cursor = self.editor.textCursor()
        block = cursor.block()
        if block != self._pending_recheck_block:
            self._debounce.start()
            return
        if self._pending_recheck_whole_block:
            # Deferred because the whole paragraph is large, not because of
            # one specific word - spaces/punctuation between words inside
            # it are still "actively editing this block", so only leaving
            # the block entirely (handled above) or the idle timer below
            # should trigger a recheck here; otherwise every space in a
            # long paragraph would force a full re-scan again, right back
            # to the original problem.
            return
        local_pos = cursor.position() - block.position()
        text = block.text()
        still_touching_word = local_pos > 0 and SPELLCHECK_WORD_CHAR_RE.match(text[local_pos - 1])
        if still_touching_word:
            return
        self._debounce.start()

    def _recheck_active_word(self):
        block = self._pending_recheck_block
        self._pending_recheck_block = None
        self._pending_recheck_whole_block = False
        if block is not None and block.isValid():
            self._skip_active_word = False
            try:
                self.rehighlightBlock(block)
            finally:
                self._skip_active_word = True

    def highlightBlock(self, text):
        if self._bulk_loading:
            # See begin_bulk_load(): a whole-document replace is in
            # progress and Qt is about to force a synchronous call here
            # for every block. Doing nothing keeps that forced pass
            # effectively free; end_bulk_load() re-processes every block
            # for real afterwards, spread across chunks.
            return

        window = self.editor.window()
        manager = getattr(window, "spell_manager", None)
        if manager is None or not manager.enabled:
            return

        block = self.currentBlock()
        block_fmt = block.blockFormat()
        if block_fmt.hasProperty(BLOCK_CODE_PROP) and block_fmt.property(BLOCK_CODE_PROP) == True:
            return  # skip code blocks entirely

        # This block is being (re)processed now, so any earlier "pending"
        # skip recorded for it is about to be superseded below (either
        # re-armed for whatever word the cursor is still touching, or not,
        # if the cursor has moved on) - clear it up front so a stale
        # leftover from a previous pass can't trigger a redundant duplicate
        # check later via _on_cursor_moved/the debounce timer.
        if self._pending_recheck_block == block:
            self._pending_recheck_block = None
            self._debounce.stop()

        cursor = self.editor.textCursor()
        # The "cursor is sitting in this block, so treat it as actively
        # being typed in and defer" heuristic below only makes sense for
        # real, live editing. During an automatic bulk pass over a
        # freshly-opened/pasted document (_bulk_chunk_active - see its
        # docstring), the cursor is just wherever it defaults to (usually
        # position 0) - not evidence of typing - and if that position
        # happens to land in a large block (e.g. a document with no
        # blank-line paragraph breaks loads as ONE giant block, so the
        # cursor is *always* "inside" it), every one of this pass's
        # highlightBlock() calls, including the ones triggered later by
        # each background correctness batch finishing (see
        # _on_words_checked(), which re-enables this same flag for that
        # reason), would otherwise get deferred behind the 300ms debounce
        # below instead of running right away. With many batches that
        # adds up to several seconds of the load looking "stuck" before
        # anything reflects on screen, well after the actual dictionary
        # lookups themselves are done.
        cursor_in_this_block = (
            not self._bulk_chunk_active
            and self._skip_active_word
            and cursor.block().blockNumber() == block.blockNumber()
        )
        cursor_pos_in_block = cursor.position() - block.position() if cursor_in_this_block else -1

        if cursor_in_this_block and len(text) > SPELLCHECK_LARGE_BLOCK_CHARS:
            # This whole paragraph is being actively typed in AND is large
            # enough that re-scanning it in full on every keystroke is
            # itself the bottleneck (independent of any single word's
            # length) - defer the ENTIRE block the same way a single
            # active word is deferred below: skip it while typing, run it
            # once idle or as soon as the cursor leaves this block.
            self._pending_recheck_block = block
            self._debounce.start()
            return

        doc = self.document()
        probe = QTextCursor(doc)
        pending_words = []
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

            if cursor_in_this_block and match.start() <= cursor_pos_in_block <= match.end():
                self._pending_recheck_block = block
                self._debounce.start()
                continue

            cached = manager.is_correct_cached(word)
            if cached is None:
                # Not known yet - don't block the GUI thread waiting for
                # phunspell here. Collect it and hand the whole batch off
                # to a background thread below; this word just isn't
                # underlined (or not) until that comes back, a moment
                # later, and triggers a cheap re-highlight of this block.
                pending_words.append(word)
                continue

            if not cached:
                self.setFormat(match.start(), len(word), self._format)
                # Warm the suggestion cache now, while the word is being
                # underlined, instead of waiting for a right-click - see
                # SpellCheckManager.prefetch_suggestions(). Skipped during
                # the automatic bulk pass over a freshly-opened/pasted
                # document (see self._bulk_chunk_active's docstring) - a
                # document can have far more misspelled words at once than
                # a user ever has on screen while actually editing, and
                # eagerly computing suggestions for all of them at once is
                # exactly the queued-up CPU work that was still enough to
                # stutter the GUI thread even off it. Right-clicking a
                # misspelled word still computes its suggestions on demand
                # regardless of whether this ran for it.
                if not self._bulk_chunk_active:
                    manager.prefetch_suggestions(word)

        if pending_words:
            # Remember whether THIS pass (the one collecting pending_words
            # right now) is part of the automatic bulk pass over a
            # freshly-opened/pasted document (_bulk_chunk_active - see its
            # docstring above _process_bulk_chunk()). check_words_async()
            # answers on a background thread, so its on_done callback below
            # always fires LATER, on its own trip through the event loop -
            # by then _process_bulk_chunk() has already returned and
            # _bulk_chunk_active is back to False, even though the word
            # being flagged only exists because of that bulk pass. Without
            # capturing the flag here and passing it through, every
            # misspelled word discovered this way would still (correctly)
            # skip prefetching suggestions on THIS call, but then trigger a
            # SECOND highlightBlock() pass via _on_words_checked() below
            # that no longer looks like bulk loading - so it prefetches
            # suggestions after all. On a document with many misspelled
            # words at once (e.g. text in a language outside the active
            # dictionary, like the Lorem Ipsum test file), that reintroduces
            # the exact same flood of CPU-heavy edit-distance searches this
            # whole mechanism was built to avoid, just one event-loop tick
            # later - which is why the freeze only showed up AFTER the
            # underlines had already started appearing.
            bulk = self._bulk_chunk_active
            manager.check_words_async(pending_words, on_done=lambda b=block, bulk=bulk: self._on_words_checked(b, bulk))

    def _on_words_checked(self, block, suppress_prefetch=False):
        if not block.isValid():
            return
        if suppress_prefetch:
            # Re-enter with the same flag highlightBlock() uses to skip
            # prefetch_suggestions() (see above) so this deferred,
            # bulk-originated pass stays exempt too, instead of only the
            # first, immediate pass being exempt.
            self._bulk_chunk_active = True
            try:
                self.rehighlightBlock(block)
            finally:
                self._bulk_chunk_active = False
        else:
            self.rehighlightBlock(block)


def _is_local_file_href(href):
    """True if a hyperlink target should be treated as a local file rather
    than a web address: an explicit file:// URI, or any plain path that
    doesn't look like some other URL scheme (http://, mailto:, ftp://, ...).
    This deliberately also covers *relative* paths (".\\plik.pdf",
    "plik.pdf", "..\\folder\\plik.pdf") - not just absolute ones - since
    those are resolved later, at open time, against the folder of the
    currently saved .md document (see open_hyperlink/resolve_media_path)."""
    if not href:
        return False
    if href.startswith("file://"):
        return True  # checked first: also matches the generic scheme:// test below
    if href.startswith("mailto:"):
        return False
    if _is_url(href):
        return False  # some other URL scheme (http, https, ftp, ...)
    return True


def open_hyperlink(href, base_dir=None):
    """Open a hyperlink's target: local files are launched the way the
    system file explorer would (using the file's default association),
    everything else opens in the default web browser. A local target can
    be absolute (C:\\..., /..., ~/..., a file:// URI) or relative - such
    as ".\\plik.pdf" or "..\\docs\\readme.pdf" - in which case it's
    resolved against `base_dir` (normally the folder the current .md
    document is saved in; see Editor.get_media_base_dir)."""
    if _is_local_file_href(href):
        local_path, _is_remote = resolve_media_path(href, base_dir)
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(local_path)):
            QMessageBox.warning(None, "MPad++", f"Could not open file:\n{local_path}")
    else:
        webbrowser.open(href, new=2)


# --- Table column alignment ---
#
# Markdown only supports aligning a table by whole COLUMN - the
# ":---"/"---:"/":---:" marker in a column's separator cell applies to
# every row of that column alike, there's no such thing as "just the
# header row" or "just the data rows" in the format itself. So alignment
# here is read from and written straight to the document's actual cell
# formatting (the same thing get_inline_md()/export_table_to_md() already
# read everything else from) instead of being kept as a separate
# app-only setting (globally in Preferences, or per-table on the
# QTextTableFormat) that only this program would ever know how to read
# back - that state doesn't exist anywhere once the file leaves this app,
# so it doesn't belong outside the Markdown text itself.
_TABLE_ALIGN_QT = {"left": Qt.AlignLeft, "center": Qt.AlignHCenter, "right": Qt.AlignRight}


def get_table_column_alignment(table, col):
    """Read a table column's current alignment ("left"/"center"/"right") from
    its header cell's paragraph alignment."""
    cell = table.cellAt(0, col)
    it = cell.begin()
    while not it.atEnd():
        blk = it.currentBlock()
        if blk.isValid():
            align = blk.blockFormat().alignment()
            if align & Qt.AlignHCenter:
                return "center"
            if align & Qt.AlignRight:
                return "right"
            return "left"
        it += 1
    return "left"


def set_table_column_alignment(table, col, align_key):
    """Apply an alignment to every cell in one table column (all rows alike),
    which is the only granularity real Markdown table alignment has."""
    align = _TABLE_ALIGN_QT.get(align_key, Qt.AlignLeft)
    for r in range(table.rows()):
        cell = table.cellAt(r, col)
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


def sync_table_column_alignments(table):
    """Re-apply every column's current (header-row) alignment across all of
    its rows. Needed after inserting a row: the new row's cells start out
    with no explicit alignment, which would otherwise leave that one row
    out of step with the rest of its column."""
    for c in range(table.columns()):
        set_table_column_alignment(table, c, get_table_column_alignment(table, c))


_TABLE_SEP_CELL_RE = re.compile(r'^:?-+:?$')


def parse_markdown_table_alignments(source_text):
    """Scan raw Markdown text for GFM table separator rows and return a list
    of per-table column-alignment lists (one entry per table, in the order
    the tables appear), e.g. [["left", "center", "right"], ...].

    This exists because Qt's own Markdown importer (QTextDocument.setMarkdown)
    parses the table itself but silently discards the alignment markers in
    the process - so the only way to recover them is to read the source text
    directly, then reapply them to the resulting QTextTable afterward.
    """
    lines = source_text.splitlines()

    def split_row(line):
        line = line.strip()
        if line.startswith('|'):
            line = line[1:]
        if line.endswith('|'):
            line = line[:-1]
        return [c.strip() for c in line.split('|')]

    tables_align = []
    for i in range(1, len(lines)):
        line = lines[i]
        if '|' not in line:
            continue
        prev = lines[i - 1]
        if '|' not in prev or not prev.strip():
            continue
        cells = split_row(line)
        if not cells or not all(_TABLE_SEP_CELL_RE.match(c) for c in cells):
            continue
        aligns = []
        for c in cells:
            if c.startswith(':') and c.endswith(':'):
                aligns.append("center")
            elif c.endswith(':'):
                aligns.append("right")
            else:
                aligns.append("left")
        tables_align.append(aligns)
    return tables_align


def apply_markdown_table_alignments(document, tables_align):
    """Reapply the per-table column alignments parse_markdown_table_alignments()
    recovered from source text onto the QTextTables setMarkdown() just built,
    matching them up in document order."""
    if not tables_align:
        return
    cursor = QTextCursor(document)
    cursor.movePosition(QTextCursor.Start)
    idx = 0
    while idx < len(tables_align):
        table = cursor.currentTable()
        if table:
            aligns = tables_align[idx]
            idx += 1
            for c in range(min(table.columns(), len(aligns))):
                set_table_column_alignment(table, c, aligns[c])
            cursor.setPosition(table.lastPosition() + 1, QTextCursor.MoveAnchor)
        else:
            if not cursor.movePosition(QTextCursor.NextBlock):
                break


class Editor(QTextEdit):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.current_file = None
        self.view_mode = "formatted"
        self.setAcceptDrops(True)
        self.apply_settings()

        # --- Embedded media (image/gif/video/audio) ---
        # One handler per editor/document, registered for MEDIA_OBJECT_TYPE
        # so every ![alt](src) that resolves to a recognized media file
        # gets painted as a real inline picture, animation, or player
        # instead of plain text.
        self._media_object_handler = MediaTextObject(self)
        self.document().documentLayout().registerHandler(MEDIA_OBJECT_TYPE, self._media_object_handler)
        self._media_pixmap_cache = {}      # src -> QPixmap or None (failed/pending)
        self._media_movie_cache = {}       # src -> (QMovie, QBuffer-or-None) or None
        self._media_controllers = {}       # media_id -> MediaPlayerController
        self._media_download_threads = {}  # src -> _MediaDownloadThread (kept alive)
        self._media_download_kind = {}     # src -> "image" | "gif"

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
        self._code_copy_icon_rects = []   # [(QRect, block_start_pos, block_end_pos)], set in paintEvent
        self._code_copy_hover_pos = None
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

        # Even with setCursorWidth(0), QWidgetTextControl still computes and
        # POSTS (queues) its own update for the previous cursor rect on every
        # cursor move / text edit as part of its internal "erase old cursor,
        # draw new one" bookkeeping. That queued update isn't delivered until
        # the next turn of the event loop - i.e. strictly AFTER the
        # synchronous repaint() just above - and since it can carry a
        # narrower clip rect based on the layout as it stood before this
        # edit/relayout, letting it paint unopposed can leave a leftover
        # sliver of our own previously-drawn caret on screen (wrong
        # position/height) that nothing then cleans up until the next blink.
        # Visually this reads as a second, non-blinking caret next to the
        # real one. Scheduling one more full-viewport repaint for the next
        # event-loop turn - after that queued update has already been
        # delivered - guarantees we paint over and erase it every time. A
        # second, further-delayed repaint is chained after the first as
        # extra insurance for slower/rarer timings where one event-loop
        # turn isn't enough for Qt's queued update to have landed yet.
        def _cleanup_repaint():
            self.viewport().repaint()
            QTimer.singleShot(0, lambda: self.viewport().repaint())
        QTimer.singleShot(0, _cleanup_repaint)

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
        # QTextDocumentLayout caches each block's bounding rect/height and
        # only recomputes it lazily, on its own schedule (same issue
        # documented in line_number_area_paint_event below). Right after a
        # font/font-size change, everything this method reads below -
        # blockBoundingRect() for the current-line highlight, cursorRect()
        # for our custom-drawn caret, and the quote/HR block rects - could
        # otherwise be read before that recompute has happened, producing a
        # highlight rect and caret that still reflect the OLD font size (and,
        # since our caret blinks on its own out-of-phase timer, an
        # inconsistent size from one blink to the next depending on whether
        # the layout pass had completed yet). Touching documentSize() forces
        # any pending layout pass to finish before we read a single rect
        # below, so every position/size here is current.
        self.document().documentLayout().documentSize()

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

        # Draw a small "copy" button in the top-right corner of every code
        # block, one per contiguous run of code-formatted blocks (a fenced
        # multi-line code block gets exactly one button, not one per line).
        self._code_copy_icon_rects = []   # [(QRect, start_block_pos, end_block_pos_end)]
        icon_painter = QPainter(self.viewport())
        icon_painter.setRenderHint(QPainter.Antialiasing, True)
        icon_size = 16
        icon_margin = 6

        def is_code_block(b):
            return (b.isValid() and b.isVisible()
                    and b.blockFormat().hasProperty(BLOCK_CODE_PROP)
                    and b.blockFormat().property(BLOCK_CODE_PROP) == True)

        code_block = self.document().firstBlock()
        while code_block.isValid():
            if not is_code_block(code_block):
                code_block = code_block.next()
                continue
            region_start = code_block
            region_end = code_block
            nxt = code_block.next()
            while is_code_block(nxt):
                region_end = nxt
                nxt = nxt.next()

            start_rect = self.document().documentLayout().blockBoundingRect(region_start)
            top = int(start_rect.top() - self.verticalScrollBar().value())
            if -icon_size <= top <= viewport_height:
                btn_x = self.viewport().width() - icon_size - icon_margin - 2
                btn_y = top + icon_margin
                btn_rect = QRect(btn_x, btn_y, icon_size, icon_size)
                hovered = btn_rect.contains(self._code_copy_hover_pos) if self._code_copy_hover_pos else False
                bg = QColor(self.settings.get('editor_text', '#e6e6e6'))
                bg.setAlpha(60 if hovered else 30)
                icon_painter.setPen(Qt.NoPen)
                icon_painter.setBrush(bg)
                icon_painter.drawRoundedRect(btn_rect, 4, 4)
                pen_color = QColor(self.settings.get('editor_text', '#e6e6e6'))
                icon_painter.setPen(QPen(pen_color, 1.3))
                icon_painter.setBrush(Qt.NoBrush)
                # Two overlapping rounded rectangles - the universal "copy" glyph.
                back = QRectF(btn_x + 3, btn_y + 5, 8, 8)
                front = QRectF(btn_x + 5, btn_y + 3, 8, 8)
                icon_painter.drawRoundedRect(back, 1.5, 1.5)
                icon_painter.fillRect(front, QColor(self.settings.get('editor_bg', '#1e1e1e')))
                icon_painter.drawRoundedRect(front, 1.5, 1.5)
                self._code_copy_icon_rects.append((btn_rect, region_start.position(),
                                                    region_end.position() + region_end.length() - 1))
            code_block = nxt
        icon_painter.end()

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
        self._code_copy_hover_pos = pos
        hovered_icon = any(rect.contains(pos) for rect, _, _ in self._code_copy_icon_rects)
        media_hit = self._media_object_at(pos)
        if hovered_icon:
            self.viewport().setCursor(Qt.PointingHandCursor)
            self.viewport().update()
        elif media_hit is not None and media_hit[0].property(MEDIA_TYPE_PROP) in ("video", "audio"):
            self.viewport().setCursor(Qt.PointingHandCursor)
        elif self.anchorAt(pos):
            self.viewport().setCursor(Qt.PointingHandCursor)
        else:
            self.viewport().setCursor(Qt.IBeamCursor)
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            pos = event.position().toPoint()
            for rect, start_pos, end_pos in self._code_copy_icon_rects:
                if rect.contains(pos):
                    copy_cursor = QTextCursor(self.document())
                    copy_cursor.setPosition(start_pos)
                    copy_cursor.setPosition(end_pos, QTextCursor.KeepAnchor)
                    QApplication.clipboard().setText(copy_cursor.selectedText().replace('\u2029', '\n'))
                    QToolTip.showText(event.globalPosition().toPoint(), "Skopiowano!", self, rect, 1200)
                    return  # don't let this click also move the text cursor/selection
            media_hit = self._media_object_at(pos)
            if media_hit is not None:
                fmt, rect, _obj_pos = media_hit
                if self._handle_media_click(fmt, rect, pos):
                    return  # click was consumed by the play/pause control
            anchor = self.anchorAt(pos)
            if anchor:
                open_hyperlink(anchor, self.get_media_base_dir())
        super().mousePressEvent(event)

    def _media_object_at(self, pos):
        """Hit-test a viewport point against embedded media objects. Returns
        (charFormat, rect_in_viewport, doc_position) for the object under
        `pos`, or None.

        This used to derive a single "clicked" document position from
        cursorForPosition() and only test the one or two character slots
        immediately around it. That works fine for a media object sitting
        alone on its line, but breaks as soon as the same paragraph
        continues with more text after the object: cursorForPosition()'s
        x/y snapping can then land a pixel-perfect click on the object
        several character slots away from where the object itself lives
        (inside the following text run), so the old two-candidate probe
        never found it and the click fell straight through to the editor's
        own text-cursor placement instead of the video/audio/image object.

        Fixed by not guessing a document position from the click at all:
        instead, walk every fragment of the block(s) near the click (plus
        one block of margin on each side, in case the object's own line
        wrapped) and test the click point directly against each media
        object's real on-screen rect. That rect is still derived from the
        cursor boundary rects immediately before/after the object (its
        width in the line) combined with its intrinsic height, since Qt
        doesn't expose inline-object geometry any more directly than that."""
        doc = self.document()
        last = doc.characterCount() - 1
        hit_block = self.cursorForPosition(pos).block()
        blocks = [hit_block]
        if hit_block.previous().isValid():
            blocks.append(hit_block.previous())
        if hit_block.next().isValid():
            blocks.append(hit_block.next())

        seen = set()
        for block in blocks:
            it = block.begin()
            while not it.atEnd():
                frag = it.fragment()
                it += 1
                if not frag.isValid():
                    continue
                fmt = frag.charFormat()
                if fmt.objectType() != MEDIA_OBJECT_TYPE:
                    continue
                obj_pos = frag.position()
                if obj_pos in seen or obj_pos <= 0 or obj_pos > last:
                    continue
                seen.add(obj_pos)
                before = QTextCursor(doc)
                before.setPosition(obj_pos)
                after = QTextCursor(doc)
                after.setPosition(min(obj_pos + 1, last))
                left_rect = self.cursorRect(before)
                right_rect = self.cursorRect(after)
                height = self.media_intrinsic_size(fmt).height()
                rect = QRect(left_rect.left(), left_rect.top(),
                             max(1, right_rect.left() - left_rect.left()), int(height))
                if rect.contains(pos):
                    return fmt, rect, obj_pos
        return None

    def _handle_media_click(self, fmt, rect, pos):
        media_type = fmt.property(MEDIA_TYPE_PROP)
        if media_type not in ("video", "audio"):
            return False
        if not HAVE_MULTIMEDIA:
            return True  # still swallow the click - nothing to play
        media_id = fmt.property(MEDIA_ID_PROP) or ""
        src = fmt.property(MEDIA_SRC_PROP) or ""
        resolved, is_remote = resolve_media_path(src, self.get_media_base_dir())
        ctrl = self.get_media_controller(media_id, media_type, resolved, is_remote)
        if ctrl is None:
            return True
        # Clicking the bottom-most strip of a video (its control bar), or
        # anywhere on the (thin) audio bar, either toggles play/pause or
        # seeks depending on exactly where within the bar the click lands;
        # clicking the rest of a video toggles play/pause - matching a
        # typical inline player. The x-ranges below must mirror the ones
        # the bar is actually painted with in _draw_media_video /
        # _draw_media_audio (icon column, progress track, time label) -
        # previously this used the *whole* bar width for seeking, which
        # both made seeking imprecise (it didn't line up with the visibly
        # narrower progress track) and made the play/pause icon itself
        # unclickable (a click on it was always misread as a seek).
        if media_type == "video":
            bar_top = rect.bottom() - 26
            if pos.y() >= bar_top and rect.width() > 0:
                progress_left = rect.left() + 32
                progress_width = max(0, rect.width() - 140)
                if pos.x() < progress_left:
                    ctrl.toggle_play()
                elif progress_width > 0 and pos.x() < progress_left + progress_width:
                    frac = (pos.x() - progress_left) / progress_width
                    ctrl.seek_fraction(frac)
                # else: click landed on the time label - swallow, no action
                return True
            ctrl.toggle_play()
            return True
        if media_type == "audio":
            progress_left = rect.left() + 46
            progress_width = max(0, rect.width() - 132)
            if pos.x() < progress_left:
                ctrl.toggle_play()
            elif progress_width > 0 and pos.x() < progress_left + progress_width:
                frac = (pos.x() - progress_left) / progress_width
                ctrl.seek_fraction(frac)
            else:
                ctrl.toggle_play()
            return True
        ctrl.toggle_play()
        return True

    # --- Embedded media: loading, sizing, painting ---

    def get_media_base_dir(self):
        """Folder relative paths (".\\pic.png", "sub\\clip.mp4", ...) are
        resolved against - the folder the current .md document lives in,
        or the working directory for a not-yet-saved document."""
        if self.current_file:
            return os.path.dirname(os.path.abspath(self.current_file))
        return os.getcwd()

    def media_intrinsic_size(self, fmt):
        media_type = fmt.property(MEDIA_TYPE_PROP)
        src = fmt.property(MEDIA_SRC_PROP) or ""
        resolved, is_remote = resolve_media_path(src, self.get_media_base_dir())

        if media_type in ("image", "gif"):
            pix = (self.get_media_movie(src, resolved, is_remote).currentPixmap()
                   if media_type == "gif" and self.get_media_movie(src, resolved, is_remote)
                   else self.get_media_pixmap(src, resolved, is_remote))
            if pix and not pix.isNull() and pix.width() > 0:
                w = min(pix.width(), MEDIA_MAX_WIDTH)
                h = pix.height() * (w / pix.width())
                base = QSizeF(w, h)
            else:
                base = QSizeF(220, 140)
        elif media_type == "video":
            base = QSizeF(MEDIA_MAX_WIDTH, 290)
        elif media_type == "audio":
            base = QSizeF(min(MEDIA_MAX_WIDTH, 420), 56)
        else:
            base = QSizeF(160, 40)

        # A display-size multiplier, applied uniformly to both dimensions so
        # aspect ratio is always preserved. Only ever set on documents
        # created by older versions of the app (the context-menu action that
        # used to set this has been removed); still honored here so those
        # documents keep rendering the way they were saved.
        scale = fmt.property(MEDIA_SCALE_PROP)
        if scale and scale != 1.0:
            scale = max(MEDIA_SCALE_MIN, min(MEDIA_SCALE_MAX, float(scale)))
            base = QSizeF(base.width() * scale, base.height() * scale)

        # Settings > Preferences > General lets the user set a minimum
        # display width (in px) per media type, so small images/gifs/videos
        # never render illegibly tiny. Aspect ratio is preserved.
        min_width = self._min_media_width_for(media_type)
        if min_width and base.width() > 0 and base.width() < min_width:
            ratio = min_width / base.width()
            base = QSizeF(min_width, base.height() * ratio)

        return base

    def _min_media_width_for(self, media_type):
        key = {
            "image": "media_min_width_image",
            "gif": "media_min_width_gif",
            "video": "media_min_width_video",
        }.get(media_type)
        if key is None:
            return 0
        try:
            return max(0, int(self.settings.get(key, 0)))
        except (TypeError, ValueError):
            return 0

    def get_media_pixmap(self, src, resolved, is_remote):
        cache = self._media_pixmap_cache
        if src in cache:
            return cache[src]
        if is_remote:
            cache[src] = None
            self._start_media_download(src, "image")
            return None
        pix = QPixmap(resolved)
        cache[src] = pix if not pix.isNull() else None
        return cache[src]

    def get_media_movie(self, src, resolved, is_remote):
        cache = self._media_movie_cache
        if src in cache:
            return cache[src][0] if cache[src] else None
        if is_remote:
            cache[src] = None
            self._start_media_download(src, "gif")
            return None
        movie = QMovie(resolved)
        if not movie.isValid():
            cache[src] = None
            return None
        movie.setCacheMode(QMovie.CacheAll)
        movie.frameChanged.connect(lambda _f: self.viewport().update())
        movie.start()
        cache[src] = (movie, None)
        return movie

    def _start_media_download(self, src, kind):
        if src in self._media_download_threads:
            return
        thread = _MediaDownloadThread(src, self)
        self._media_download_kind[src] = kind
        thread.finished_download.connect(self._on_media_downloaded)
        self._media_download_threads[src] = thread
        thread.start()

    def _on_media_downloaded(self, src, data):
        kind = self._media_download_kind.pop(src, "image")
        self._media_download_threads.pop(src, None)
        if kind == "gif":
            movie = None
            if data:
                buf = QBuffer(self)
                buf.setData(QByteArray(data))
                buf.open(QIODevice.ReadOnly)
                candidate = QMovie()
                candidate.setDevice(buf)
                if candidate.isValid():
                    candidate.setCacheMode(QMovie.CacheAll)
                    candidate.frameChanged.connect(lambda _f: self.viewport().update())
                    candidate.start()
                    movie = (candidate, buf)
            self._media_movie_cache[src] = movie
        else:
            pix = None
            if data:
                candidate = QPixmap()
                if candidate.loadFromData(data):
                    pix = candidate
            self._media_pixmap_cache[src] = pix
        # The real size is only known now - force the document to relayout
        # so the object stops using its placeholder size.
        self.document().markContentsDirty(0, self.document().characterCount())
        self.viewport().update()

    def get_media_controller(self, media_id, media_type, resolved, is_remote):
        if not HAVE_MULTIMEDIA:
            return None
        ctrl = self._media_controllers.get(media_id)
        if ctrl is None:
            ctrl = MediaPlayerController(media_type, resolved, is_remote, self)
            ctrl.changed.connect(self.viewport().update)
            self._media_controllers[media_id] = ctrl
        return ctrl

    def draw_media_object(self, painter, rect, fmt):
        media_type = fmt.property(MEDIA_TYPE_PROP)
        src = fmt.property(MEDIA_SRC_PROP) or ""
        alt = fmt.property(MEDIA_ALT_PROP) or ""
        media_id = fmt.property(MEDIA_ID_PROP) or ""
        resolved, is_remote = resolve_media_path(src, self.get_media_base_dir())

        painter.save()
        try:
            if media_type in ("image", "gif"):
                self._draw_media_image(painter, rect, src, resolved, is_remote, media_type, alt)
            elif media_type == "video":
                self._draw_media_video(painter, rect, media_id, resolved, is_remote, alt)
            elif media_type == "audio":
                self._draw_media_audio(painter, rect, media_id, resolved, is_remote, alt)
        finally:
            painter.restore()

    def _draw_media_image(self, painter, rect, src, resolved, is_remote, media_type, alt):
        if media_type == "gif":
            movie = self.get_media_movie(src, resolved, is_remote)
            pix = movie.currentPixmap() if movie else None
        else:
            pix = self.get_media_pixmap(src, resolved, is_remote)
        if pix and not pix.isNull():
            target = pix.scaled(rect.size().toSize(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            x = rect.left() + (rect.width() - target.width()) / 2
            y = rect.top() + (rect.height() - target.height()) / 2
            painter.drawPixmap(int(x), int(y), target)
        else:
            subtitle = "Loading…" if is_remote else "Could not load image"
            self._draw_media_placeholder(painter, rect, "🖼", alt or os.path.basename(resolved), subtitle)

    def _draw_media_placeholder(self, painter, rect, icon_char, title, subtitle):
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#2a2a2a"))
        painter.drawRoundedRect(rect, 6, 6)
        painter.setPen(QColor("#8a8a8a"))
        f = painter.font()
        f.setPointSize(18)
        painter.setFont(f)
        painter.drawText(QRectF(rect.left(), rect.top(), rect.width(), rect.height() - 20),
                          Qt.AlignCenter, icon_char)
        f2 = painter.font()
        f2.setPointSize(8)
        painter.setFont(f2)
        painter.setPen(QColor("#aaaaaa"))
        label = f"{title} — {subtitle}" if subtitle else title
        elided = QFontMetrics(f2).elidedText(label, Qt.ElideMiddle, max(10, int(rect.width() - 8)))
        painter.drawText(QRectF(rect.left() + 4, rect.bottom() - 18, rect.width() - 8, 16),
                          Qt.AlignLeft | Qt.AlignVCenter, elided)

    def _draw_media_video(self, painter, rect, media_id, resolved, is_remote, alt):
        if not HAVE_MULTIMEDIA:
            self._draw_media_placeholder(painter, rect, "🎬", alt or os.path.basename(resolved),
                                          "Install PySide6-Addons (QtMultimedia)")
            return
        ctrl = self.get_media_controller(media_id, "video", resolved, is_remote)
        bar_h = 26
        video_rect = QRectF(rect.left(), rect.top(), rect.width(), rect.height() - bar_h)
        bar_rect = QRectF(rect.left(), rect.bottom() - bar_h, rect.width(), bar_h)

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#000000"))
        painter.drawRect(video_rect)

        if ctrl.error_text:
            painter.setPen(QColor("#ff8080"))
            f = painter.font(); f.setPointSize(8); painter.setFont(f)
            painter.drawText(video_rect, Qt.AlignCenter, "Playback error:\n" + ctrl.error_text)
        elif ctrl.current_frame is not None:
            scaled = ctrl.current_frame.scaled(video_rect.size().toSize(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            x = video_rect.left() + (video_rect.width() - scaled.width()) / 2
            y = video_rect.top() + (video_rect.height() - scaled.height()) / 2
            painter.drawImage(int(x), int(y), scaled)
        else:
            painter.setPen(QColor("#dddddd"))
            f = painter.font(); f.setPointSize(20); painter.setFont(f)
            painter.drawText(video_rect, Qt.AlignCenter, "▶")
            f2 = painter.font(); f2.setPointSize(8); painter.setFont(f2)
            painter.setFont(f2)
            painter.setPen(QColor("#999999"))
            label = QFontMetrics(f2).elidedText(alt or os.path.basename(resolved), Qt.ElideMiddle, int(video_rect.width() - 8))
            painter.drawText(QRectF(video_rect.left(), video_rect.bottom() - 18, video_rect.width(), 16), Qt.AlignCenter, label)

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#1c1c1c"))
        painter.drawRect(bar_rect)

        painter.setPen(QColor("#ffffff"))
        f = painter.font(); f.setPointSize(10); painter.setFont(f)
        icon = "⏸" if ctrl.is_playing() else "▶"
        painter.drawText(QRectF(bar_rect.left() + 6, bar_rect.top(), 24, bar_rect.height()),
                          Qt.AlignVCenter | Qt.AlignLeft, icon)

        progress_rect = QRectF(bar_rect.left() + 32, bar_rect.top() + bar_rect.height() / 2 - 2,
                                max(0, bar_rect.width() - 140), 4)
        painter.setBrush(QColor("#444444"))
        painter.drawRoundedRect(progress_rect, 2, 2)
        frac = ctrl.position_fraction()
        painter.setBrush(QColor(self.settings.get("link", "#3794ff")))
        painter.drawRoundedRect(QRectF(progress_rect.left(), progress_rect.top(),
                                        progress_rect.width() * frac, progress_rect.height()), 2, 2)

        painter.setPen(QColor("#cccccc"))
        f3 = painter.font(); f3.setPointSize(7); painter.setFont(f3)
        painter.drawText(QRectF(bar_rect.right() - 104, bar_rect.top(), 100, bar_rect.height()),
                          Qt.AlignVCenter | Qt.AlignRight, ctrl.time_text())

    def _draw_media_audio(self, painter, rect, media_id, resolved, is_remote, alt):
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#2a2a2a"))
        painter.drawRoundedRect(rect, 8, 8)

        if not HAVE_MULTIMEDIA:
            self._draw_media_placeholder(painter, rect, "🎵", alt or os.path.basename(resolved),
                                          "Install PySide6-Addons (QtMultimedia)")
            return
        ctrl = self.get_media_controller(media_id, "audio", resolved, is_remote)

        icon_circle = QRectF(rect.left() + 8, rect.top() + rect.height() / 2 - 14, 28, 28)
        painter.setBrush(QColor(self.settings.get("link", "#3794ff")))
        painter.drawEllipse(icon_circle)
        painter.setPen(QColor("#ffffff"))
        f = painter.font(); f.setPointSize(11); painter.setFont(f)
        painter.drawText(icon_circle, Qt.AlignCenter, "⏸" if ctrl.is_playing() else "▶")

        title = alt or os.path.basename(resolved)
        f2 = painter.font(); f2.setPointSize(8); painter.setFont(f2)
        painter.setPen(QColor("#e0e0e0"))
        name_rect = QRectF(rect.left() + 46, rect.top() + 6, rect.width() - 58, 16)
        painter.drawText(name_rect, Qt.AlignLeft | Qt.AlignVCenter,
                          QFontMetrics(f2).elidedText(title, Qt.ElideMiddle, max(10, int(name_rect.width()))))

        if ctrl.error_text:
            painter.setPen(QColor("#ff8080"))
            painter.drawText(QRectF(rect.left() + 46, rect.top() + 24, rect.width() - 58, 16),
                              Qt.AlignLeft | Qt.AlignVCenter, "Error: " + ctrl.error_text)
            return

        progress_rect = QRectF(rect.left() + 46, rect.bottom() - 18, max(0, rect.width() - 132), 4)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#4a4a4a"))
        painter.drawRoundedRect(progress_rect, 2, 2)
        frac = ctrl.position_fraction()
        painter.setBrush(QColor(self.settings.get("link", "#3794ff")))
        painter.drawRoundedRect(QRectF(progress_rect.left(), progress_rect.top(),
                                        progress_rect.width() * frac, progress_rect.height()), 2, 2)

        painter.setPen(QColor("#bbbbbb"))
        f3 = painter.font(); f3.setPointSize(7); painter.setFont(f3)
        painter.drawText(QRectF(rect.right() - 82, rect.bottom() - 20, 78, 16),
                          Qt.AlignRight | Qt.AlignVCenter, ctrl.time_text())

    def insert_media_object(self, media_type, src, alt):
        """Insert a new embedded media object at the cursor. `src` is kept
        exactly as given (so relative paths and URLs round-trip through
        Markdown unchanged); resolution to an actual loadable path/URL
        happens on demand when painting."""
        fmt = QTextCharFormat()
        fmt.setObjectType(MEDIA_OBJECT_TYPE)
        fmt.setProperty(MEDIA_TYPE_PROP, media_type)
        fmt.setProperty(MEDIA_SRC_PROP, src)
        fmt.setProperty(MEDIA_ALT_PROP, alt)
        fmt.setProperty(MEDIA_ID_PROP, str(uuid.uuid4()))
        cursor = self.textCursor()
        cursor.insertText("\ufffc", fmt)
        self.setTextCursor(cursor)

    def replace_media_placeholders(self, media_matches):
        """Called right after document().setMarkdown() replaces the whole
        document: Qt's own Markdown importer already turned every
        ![alt](src) into a plain static QTextImageFormat fragment (and
        silently dropped the alt text - see media_matches, extracted from
        the raw source beforehand). This walks those fragments and, for
        every one whose src is a recognized image/gif/video/audio file,
        swaps it for a real embedded media object (restoring the alt
        text); anything else becomes an ordinary hyperlink instead, since
        it isn't something this app can actually embed.
        """
        doc = self.document()
        queue = list(media_matches)
        replacements = []  # (start, end, media_type_or_None, src, alt)

        block = doc.firstBlock()
        while block.isValid():
            it = block.begin()
            while not it.atEnd():
                frag = it.fragment()
                if frag.isValid() and frag.charFormat().isImageFormat():
                    src = frag.charFormat().toImageFormat().name()
                    alt = queue.pop(0)[0] if queue else ""
                    media_type = classify_media_path(src)
                    replacements.append((frag.position(), frag.position() + frag.length(), media_type, src, alt))
                it += 1
            block = block.next()

        for start, end, media_type, src, alt in reversed(replacements):
            cursor = QTextCursor(doc)
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.KeepAnchor)
            if media_type:
                fmt = QTextCharFormat()
                fmt.setObjectType(MEDIA_OBJECT_TYPE)
                fmt.setProperty(MEDIA_TYPE_PROP, media_type)
                fmt.setProperty(MEDIA_SRC_PROP, src)
                fmt.setProperty(MEDIA_ALT_PROP, alt)
                fmt.setProperty(MEDIA_ID_PROP, str(uuid.uuid4()))
                cursor.insertText("\ufffc", fmt)
            else:
                fmt = QTextCharFormat()
                fmt.setAnchor(True)
                fmt.setAnchorHref(src)
                fmt.setForeground(QColor(self.settings["link"]))
                fmt.setFontUnderline(self.settings.get("link_underline", True))
                cursor.insertText(alt if alt else src, fmt)

    def release_media_players(self):
        """Stop every live QMediaPlayer this editor owns, so closing a tab
        doesn't leave audio/video quietly playing in the background."""
        for ctrl in self._media_controllers.values():
            ctrl.stop_and_release()

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

        media_hit = self._media_object_at(event.pos())
        
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

        if media_hit is not None:
            media_fmt, _media_rect, media_obj_pos = media_hit
            media_type = media_fmt.property(MEDIA_TYPE_PROP)
            if media_type in ("image", "gif", "video"):
                menu.addSeparator()

                edit_link_action = QAction("Edit link…", menu)
                edit_link_action.triggered.connect(
                    lambda checked=False, e=self, p=media_obj_pos, f=QTextCharFormat(media_fmt):
                        self.window().edit_media_from_menu(e, p, f))
                menu.addAction(edit_link_action)

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
        if (event.key() == Qt.Key_Space and self.view_mode == "formatted"
                and not event.modifiers() & (Qt.ControlModifier | Qt.AltModifier)):
            cursor = self.textCursor()
            if not cursor.hasSelection():
                block = cursor.block()
                block_fmt = block.blockFormat()
                # Don't hijack the space if this line already has some other
                # special formatting going on (already a heading, inside a
                # quote/code block, or an HR line) - those have their own
                # typing behavior and "# " isn't meaningful inside them.
                already_special = (
                    block_fmt.headingLevel() > 0
                    or (block_fmt.hasProperty(QUOTE_PROP) and block_fmt.property(QUOTE_PROP) == True)
                    or (block_fmt.hasProperty(BLOCK_CODE_PROP) and block_fmt.property(BLOCK_CODE_PROP) == True)
                    or (block_fmt.hasProperty(HR_PROP) and block_fmt.property(HR_PROP) == True)
                )
                if not already_special:
                    offset = cursor.position() - block.position()
                    text_before_cursor = block.text()[:offset]

                    m_heading = re.match(r'^(#{1,6})$', text_before_cursor)
                    m_bullet = re.match(r'^[-\*\+]$', text_before_cursor)
                    m_numbered = re.match(r'^(\d+)\.$', text_before_cursor)
                    m_quote = re.match(r'^>$', text_before_cursor)

                    if m_heading or m_bullet or m_numbered or m_quote:
                        cursor.beginEditBlock()
                        cursor.setPosition(block.position())
                        cursor.setPosition(block.position() + offset, QTextCursor.KeepAnchor)
                        cursor.removeSelectedText()
                        cursor.endEditBlock()
                        self.setTextCursor(cursor)
                        # Each of these reuses the exact same per-block
                        # formatting code the corresponding toolbar button
                        # uses, so typing the markdown shortcut and clicking
                        # the button produce identical results.
                        if m_heading:
                            self.window().toggle_heading(len(m_heading.group(1)))
                        elif m_bullet:
                            self.window().toggle_list("ul")
                        elif m_numbered:
                            self.window().toggle_list("ol")
                        else:
                            self.window().toggle_quote()
                        return

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

        if (event.key() in (Qt.Key_Tab, Qt.Key_Backtab)
                and not event.modifiers() & (Qt.ControlModifier | Qt.AltModifier)):
            cursor = self.textCursor()
            if not cursor.hasSelection():
                block = cursor.block()
                line_text = block.text()
                parsed = _parse_numbered_list_line(line_text)
                if parsed is not None:
                    depth, numbers, spacing, content = parsed
                    block_start = block.position()
                    orig_offset = cursor.position() - block_start
                    old_prefix_len = len(line_text) - len(content)
                    is_outdent = event.key() == Qt.Key_Backtab or bool(event.modifiers() & Qt.ShiftModifier)
                    new_text = None
                    if is_outdent:
                        if depth == 0:
                            # Nothing shallower than top level - Shift+Tab
                            # here just drops the numbering instead of
                            # doing nothing, the same way it would un-indent
                            # a line with nowhere left to go.
                            new_text = content
                        elif len(numbers) > 1:
                            # Becomes the next sibling of its former parent -
                            # e.g. outdenting "2.1." (numbers=[2,1]) drops
                            # the "1" and bumps the "2" to "3", matching
                            # what continuing the ORIGINAL top-level list
                            # after a nested block looks like.
                            new_numbers = numbers[:-1]
                            new_numbers[-1] += 1
                            new_text = "\t" * (depth - 1) + '.'.join(map(str, new_numbers)) + '.' + spacing + content
                        else:
                            # Only one number component even though the line
                            # is indented (e.g. pasted text, or a hand-edited/
                            # hand-tabbed line) - there's no parent number to
                            # bump, so just drop one indent level instead of
                            # indexing into an empty list (which used to
                            # crash here).
                            new_text = "\t" * (depth - 1) + '.'.join(map(str, numbers)) + '.' + spacing + content
                    else:
                        # Indent: only makes sense relative to the line
                        # right above - you can't nest under nothing, and
                        # (like every outliner) you can only go one level
                        # deeper than what's immediately above, not skip
                        # straight to a deeper level.
                        prev_block = block.previous()
                        prev_parsed = _parse_numbered_list_line(prev_block.text()) if prev_block.isValid() else None
                        if prev_parsed is not None:
                            prev_depth, prev_numbers, _, _ = prev_parsed
                            if prev_depth == depth:
                                # Nest under the item directly above, as its
                                # first child - e.g. "3." right after "2."
                                # becomes "2.1.".
                                new_numbers = prev_numbers + [1]
                            elif prev_depth == depth + 1:
                                # Already at the target depth - become the
                                # next sibling there instead of a child of
                                # it (e.g. after "2.1." already exists,
                                # indenting a new top-level line makes it
                                # "2.2.", not "2.1.1.").
                                new_numbers = prev_numbers[:-1] + [prev_numbers[-1] + 1]
                            else:
                                new_numbers = None
                            if new_numbers is not None:
                                new_depth = depth + 1
                                new_text = "\t" * new_depth + '.'.join(map(str, new_numbers)) + '.' + spacing + content
                    if new_text is not None:
                        cursor.beginEditBlock()
                        cursor.setPosition(block_start)
                        cursor.setPosition(block_start + len(line_text), QTextCursor.KeepAnchor)
                        cursor.removeSelectedText()
                        cursor.insertText(new_text)
                        cursor.endEditBlock()
                        # Keep the caret at the same spot within the actual
                        # text (not the marker) rather than always landing
                        # at the end of the line.
                        new_prefix_len = len(new_text) - len(content)
                        if orig_offset >= old_prefix_len:
                            new_offset = new_prefix_len + (orig_offset - old_prefix_len)
                        else:
                            new_offset = new_prefix_len
                        restore_cursor = QTextCursor(self.document())
                        restore_cursor.setPosition(block_start + new_offset)
                        self.setTextCursor(restore_cursor)
                    # Whether or not anything changed, a Tab/Backtab on a
                    # recognized list line never falls through to inserting
                    # a literal tab character.
                    return

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

            if (self.view_mode == "formatted" and not cursor.hasSelection()
                    and not is_quote and not is_block_code and not is_hr
                    and block_fmt.headingLevel() == 0):
                stripped = block.text().strip()
                if re.match(r'^```(\S*)$', stripped) and block.text() == stripped:
                    cursor.beginEditBlock()
                    cursor.setPosition(block.position())
                    cursor.setPosition(block.position() + len(block.text()), QTextCursor.KeepAnchor)
                    cursor.removeSelectedText()
                    code_block_fmt = QTextBlockFormat()
                    code_block_fmt.setProperty(BLOCK_CODE_PROP, True)
                    code_block_fmt.setBackground(QColor(self.settings['code_bg']))
                    cursor.setBlockFormat(code_block_fmt)
                    code_char_fmt = QTextCharFormat()
                    code_char_fmt.setForeground(QColor(self.settings['code']))
                    code_char_fmt.setFontFamilies(["Consolas"])
                    code_char_fmt.setProperty(CODE_PROP, True)
                    cursor.setCharFormat(code_char_fmt)
                    cursor.endEditBlock()
                    self.setTextCursor(cursor)
                    self.window().update_toolbar_state()
                    return

            if (self.view_mode == "formatted" and not cursor.hasSelection()
                    and not is_quote and not is_block_code and not is_hr
                    and block_fmt.headingLevel() == 0):
                stripped = block.text().strip()
                if re.match(r'^(-{3,}|\*{3,}|_{3,})$', stripped) and block.text() == stripped:
                    cursor.beginEditBlock()
                    cursor.setPosition(block.position())
                    cursor.setPosition(block.position() + len(block.text()), QTextCursor.KeepAnchor)
                    cursor.removeSelectedText()
                    hr_fmt = QTextBlockFormat()
                    hr_fmt.setProperty(HR_PROP, True)
                    cursor.setBlockFormat(hr_fmt)
                    cursor.setCharFormat(QTextCharFormat())
                    # A fresh, normally-formatted line below it to keep
                    # typing on, matching what clicking the "Insert
                    # horizontal line" toolbar button leaves the cursor on.
                    cursor.insertBlock()
                    normal_fmt = QTextBlockFormat()
                    cursor.setBlockFormat(normal_fmt)
                    normal_char = QTextCharFormat()
                    normal_char.setForeground(QColor(self.settings['editor_text']))
                    normal_char.setFontFamilies([self.settings['font_family']])
                    normal_char.setFontPointSize(self.settings['font_size'])
                    cursor.setCharFormat(normal_char)
                    cursor.endEditBlock()
                    self.setTextCursor(cursor)
                    self.window().update_toolbar_state()
                    return

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

            else:
                # Lists here aren't real Qt QTextList objects - toggle_list()
                # and post_process_markdown() both bake the marker ("• ",
                # "■ " or "1. ") directly into the paragraph's plain text
                # instead (see toggle_list()'s docstring-equivalent comment
                # there). That means, unlike quote/code above, there's no
                # block-level property to detect a list item by - it has to
                # be read back out of the block's own text with a regex.
                # Same continue/exit convention as quote and code blocks:
                # Enter on a non-empty item carries the marker (incrementing
                # the number for ordered lists) onto the new line; Enter on
                # an already-empty item (just the marker, nothing typed
                # after it) exits the list instead of adding another one.
                line_text = block.text()
                bullet_match = LIST_BULLET_RE.match(line_text)
                numbered_match = None if bullet_match else LIST_NUMBERED_RE.match(line_text)
                if bullet_match or numbered_match:
                    m = bullet_match or numbered_match
                    indent, marker, spacing, content = m.groups()
                    if content.strip() == '':
                        numbered_depth = len(indent) if numbered_match else 0
                        if numbered_match and numbered_depth > 0:
                            # Empty nested item - rather than dropping all
                            # numbering at once, pop out one level and
                            # continue THAT level's numbering instead (same
                            # arithmetic as Shift+Tab - see its comment
                            # above). Pressing Enter again on the resulting
                            # (still-empty, now-shallower) item repeats
                            # this, so it takes one Enter per nesting level
                            # to fully back out, ending - once depth 0 is
                            # reached - in the plain "drop the marker"
                            # behavior below, same as a never-nested item.
                            numbers = [int(p) for p in marker.split('.')]
                            new_indent = "\t" * (numbered_depth - 1)
                            if len(numbers) > 1:
                                new_numbers = numbers[:-1]
                                new_numbers[-1] += 1
                                new_line = f"{new_indent}{'.'.join(map(str, new_numbers))}.{spacing}"
                            else:
                                # Only one number component even though the
                                # line is indented (e.g. pasted text, or a
                                # hand-edited/hand-tabbed line) - there's no
                                # parent number to bump, so just drop one
                                # indent level instead of indexing into an
                                # empty list (which used to crash here).
                                new_line = f"{new_indent}{'.'.join(map(str, numbers))}.{spacing}"
                            cursor.beginEditBlock()
                            cursor.setPosition(block.position())
                            cursor.setPosition(block.position() + len(line_text), QTextCursor.KeepAnchor)
                            cursor.removeSelectedText()
                            cursor.insertText(new_line)
                            cursor.endEditBlock()
                            self.setTextCursor(cursor)
                            self.window().update_toolbar_state()
                            return
                        # Empty, top-level item - drop the marker and stay
                        # on this (now blank) line instead of starting a
                        # new one.
                        cursor.beginEditBlock()
                        cursor.setPosition(block.position())
                        cursor.setPosition(block.position() + len(line_text), QTextCursor.KeepAnchor)
                        cursor.removeSelectedText()
                        cursor.endEditBlock()
                        self.setTextCursor(cursor)
                        self.window().update_toolbar_state()
                        return
                    else:
                        cursor.beginEditBlock()
                        cursor.insertBlock()
                        if numbered_match:
                            # marker may now be a dotted chain like "2.1"
                            # (see LIST_NUMBERED_RE) - only the last
                            # component advances; a nested item's parent
                            # number doesn't change just because a sibling
                            # was added underneath it.
                            parts = marker.split('.')
                            parts[-1] = str(int(parts[-1]) + 1)
                            new_marker = '.'.join(parts) + '.'
                        else:
                            new_marker = marker
                        cursor.insertText(f"{indent}{new_marker}{spacing}")
                        cursor.endEditBlock()
                        self.setTextCursor(cursor)
                        return

        if (self.view_mode == "formatted" and event.text() in ('*', '_', '`')
                and not event.modifiers() & (Qt.ControlModifier | Qt.AltModifier)):
            cursor = self.textCursor()
            if not cursor.hasSelection():
                block = cursor.block()
                block_fmt = block.blockFormat()
                cur_fmt = cursor.charFormat()
                inside_block_code = (block_fmt.hasProperty(BLOCK_CODE_PROP)
                                      and block_fmt.property(BLOCK_CODE_PROP) == True)
                inside_inline_code = (cur_fmt.hasProperty(CODE_PROP)
                                       and cur_fmt.property(CODE_PROP) == True)
                if not inside_block_code and not inside_inline_code:
                    offset = cursor.position() - block.position()
                    # Simulate the character actually landing at the end of
                    # the text typed so far, without inserting it yet - lets
                    # a plain, non-matching '*'/'_'/'`' fall straight through
                    # to the normal insertion path below instead of needing
                    # a separate "undo the speculative insert" step.
                    candidate = block.text()[:offset] + event.text()
                    m = None
                    action = None
                    if event.text() == '`':
                        m = re.search(r'`([^`\n]+)`$', candidate)
                        action = 'code'
                    elif event.text() == '*':
                        m = re.search(r'\*\*([^\*\n]+)\*\*$', candidate)
                        action = 'bold'
                        if not m:
                            m = re.search(r'(?<!\*)\*([^\*\n]+)\*$', candidate)
                            action = 'italic'
                    elif event.text() == '_':
                        m = re.search(r'__([^_\n]+)__$', candidate)
                        action = 'bold'
                        if not m:
                            m = re.search(r'(?<!_)_([^_\n]+)_$', candidate)
                            action = 'italic'
                    if m:
                        content = m.group(1)
                        start_off = m.start()
                        doc = self.document()
                        cursor.beginEditBlock()
                        cursor.setPosition(block.position() + start_off)
                        cursor.setPosition(block.position() + offset, QTextCursor.KeepAnchor)
                        cursor.removeSelectedText()
                        cursor.insertText(content)
                        cursor.endEditBlock()
                        sel = QTextCursor(doc)
                        sel.setPosition(block.position() + start_off)
                        sel.setPosition(block.position() + start_off + len(content), QTextCursor.KeepAnchor)
                        self.setTextCursor(sel)
                        # Reuses the exact same toggle used by the Bold/
                        # Italic/Code toolbar buttons, so the live shortcut
                        # and the button produce identical formatting.
                        if action == 'bold':
                            self.window().toggle_bold()
                        elif action == 'italic':
                            self.window().toggle_italic()
                        else:
                            self.window().toggle_code()
                        # Land a plain caret right after the transformed
                        # text with NORMAL formatting - otherwise every
                        # character typed next would keep inheriting
                        # bold/italic/code, the way it would after any
                        # ordinary selection-based toggle.
                        end_pos = block.position() + start_off + len(content)
                        normal_fmt = QTextCharFormat()
                        normal_fmt.setForeground(QColor(self.settings['editor_text']))
                        normal_fmt.setFontFamilies([self.settings['font_family']])
                        normal_fmt.setFontPointSize(self.settings['font_size'])
                        normal_fmt.setFontWeight(QFont.Normal)
                        normal_fmt.setFontItalic(False)
                        normal_fmt.setFontUnderline(False)
                        normal_fmt.setProperty(CODE_PROP, False)
                        normal_fmt.setBackground(Qt.transparent)
                        end_cursor = QTextCursor(doc)
                        end_cursor.setPosition(end_pos)
                        end_cursor.setCharFormat(normal_fmt)
                        self.setTextCursor(end_cursor)
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

    def insertFromMimeData(self, source):
        """Handles Ctrl+V paste and drag-and-drop of plain text/rich text
        (file drops are handled separately by dropEvent above).

        For a large paste, Qt inserts the whole thing as one edit, which -
        exactly like setMarkdown()/setPlainText() during File > Open or the
        view-mode toggle - forces QSyntaxHighlighter to synchronously call
        highlightBlock() for every newly-inserted block in one go, before
        control returns to the event loop. That single synchronous pass is
        what shows up as the app freezing/stuttering right after pasting a
        large amount of text, even though spell checking is otherwise kept
        off the GUI thread everywhere else (see begin_bulk_load()'s
        docstring). Wrapping the paste the same way File > Open does -
        bulk mode off during the insert, real highlighting done afterwards
        in small non-blocking chunks - fixes that without touching what
        gets pasted or how.

        Small pastes (typing-speed clipboard use) are wrapped too since the
        cost of doing so is negligible - end_bulk_load() only spreads work
        across ticks when there's actually more than one chunk's worth of
        blocks to process."""
        self.spell_highlighter.begin_bulk_load()
        try:
            super().insertFromMimeData(source)
        finally:
            self.spell_highlighter.end_bulk_load()

    def post_process_markdown(self):
        cursor = QTextCursor(self.document())
        cursor.beginEditBlock()
        
        # Running per-depth counters used to rebuild OUR OWN nested-numbered-
        # list convention ("\t"*depth + "2.1." + " " + content, see
        # LIST_NUMBERED_RE) out of Qt's real QTextList objects below. This
        # can't just read Qt's own text_list.itemNumber(block): items are
        # converted to plain text and removed from their QTextList one at a
        # time in this same loop, and remove() re-indexes every remaining
        # item in that list immediately - so itemNumber() queried *after* an
        # earlier sibling has already been removed comes back wrong (every
        # item ends up reporting position 0, i.e. "1."). Tracking our own
        # depth-keyed counters, incremented/truncated as blocks are walked in
        # document order, sidesteps that entirely and also reconstructs the
        # indentation nested items need but Qt's flat itemNumber() can't
        # express on its own.
        list_counters = []
        
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
                if style == QTextListFormat.Style.ListDecimal:
                    # depth 0 = top level, matching LIST_NUMBERED_RE's one-
                    # tab-per-level convention; Qt reports indent=1 for a
                    # top-level list.
                    depth = max(fmt.indent() - 1, 0)
                    if depth >= len(list_counters):
                        list_counters.extend([0] * (depth - len(list_counters) + 1))
                    else:
                        del list_counters[depth + 1:]
                    list_counters[depth] += 1
                    numbers = list_counters[:depth + 1]
                    prefix = "\t" * depth + '.'.join(map(str, numbers)) + '. '
                else:
                    list_counters = []
                    if style == QTextListFormat.Style.ListSquare:
                        prefix = "■ "
                    else:
                        prefix = "• "
                    
                text_list.remove(block)
                temp_cursor.insertText(prefix)
                is_list = False
            else:
                # A non-list block breaks the run - the next numbered list
                # (if any) starts fresh at "1." rather than continuing this
                # one's counters.
                list_counters = []
                
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

            new_block_fmt = None

            # NOTE: we intentionally do NOT force a fixed line height here.
            # An earlier version of this method pinned every block's line
            # height to a plain reference font's metrics (e.g. Arial) at the
            # same point size, to make row spacing "consistent" regardless
            # of which typeface was active. That backfired badly: decorative
            # faces (e.g. "Gabriola") genuinely need more vertical room per
            # line than their point size suggests - their real ascent/
            # descent is simply bigger, by design - and forcing a smaller,
            # reference-sized row height clipped the tops of their glyphs.
            # What looked like an "inconsistent gap" for such fonts was
            # actually correct: Qt's own default (font-metric-based) line
            # spacing is what keeps every font's glyphs fully visible, so we
            # leave lineHeightType/lineHeight alone and let Qt compute it
            # per-block from each block's own real font.
            #
            # Documents edited under that earlier version may still carry a
            # stale FixedHeight setting on some blocks (from before this was
            # reverted) - clean those back to Qt's natural per-font spacing
            # (SingleHeight, i.e. "let the font decide") so old clipped text
            # recovers as soon as settings are re-applied.
            if block_fmt.lineHeightType() == QTextBlockFormat.FixedHeight.value:
                new_block_fmt = QTextBlockFormat(block_fmt)
                new_block_fmt.setLineHeight(0.0, QTextBlockFormat.SingleHeight.value)

            if is_block_code:
                current_bg = block_fmt.background().color() if block_fmt.hasProperty(QTextFormat.BackgroundBrush) else QColor(Qt.transparent)
                if current_bg != QColor(self.settings['code_bg']):
                    if new_block_fmt is None:
                        new_block_fmt = QTextBlockFormat(block_fmt)
                    new_block_fmt.setBackground(QColor(self.settings['code_bg']))
            else:
                if block_fmt.hasProperty(QTextFormat.BackgroundBrush) and block_fmt.background().color() == QColor(self.settings['code_bg']):
                    if new_block_fmt is None:
                        new_block_fmt = QTextBlockFormat(block_fmt)
                    new_block_fmt.setBackground(Qt.transparent)

            if new_block_fmt is not None:
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
                    # Only treat a monospace-looking font as a sign of "this run
                    # was manually made code" if it's actually DIFFERENT from the
                    # app's own current font_family setting. Otherwise, whenever
                    # font_family itself is a monospace face (e.g. the default,
                    # "Consolas"), this would misfire on completely ordinary text/
                    # headings the moment they carry that same default font -
                    # which they always do, since this very method just set it on
                    # them on the previous pass. That created a feedback loop:
                    # normal text/headings would get flagged as code and start
                    # being wrapped in ``` on export, every time settings were
                    # re-applied (e.g. after adding a heading or changing a color
                    # in Settings/Preferences).
                    if not is_code and fam and fam.lower() != self.settings['font_family'].lower():
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
                        # 0 means "Default" in the Style Configuration dialog's
                        # spinbox. Falling back to the global font_size here
                        # would make every heading level the same size as
                        # body text (only the color would still differ per
                        # level) - not what "Default" is supposed to mean.
                        # The Formatted-view CSS stylesheet (see
                        # get_preview_html/apply_app_theme) already falls
                        # back to this heading level's own classic default
                        # size (24/20/18/16/14/13) instead; match that here
                        # so headings keep a proper cascading scale even when
                        # sized at "Default".
                        if size == 0: size = DEFAULT_SETTINGS.get(f"h{level}_size", self.settings["font_size"])
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
                # Text alignment is left untouched here - it's real
                # per-column Markdown alignment (see set_table_column_alignment()),
                # already applied to each cell directly, not something this
                # styling pass should override.


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

        # Default alignment every column of a newly inserted table starts
        # with (Insert > Table). Purely a starting point for brand-new
        # tables - once a table exists, its alignment is set per-column via
        # Edit Table and lives in the table itself, not in this setting.
        self.table_default_align_combo = QComboBox()
        self.table_default_align_combo.addItem("Left", "left")
        self.table_default_align_combo.addItem("Center", "center")
        self.table_default_align_combo.addItem("Right", "right")
        current_table_align = self.settings.get("table_default_align", "left")
        idx = self.table_default_align_combo.findData(current_table_align)
        self.table_default_align_combo.setCurrentIndex(idx if idx >= 0 else 0)
        layout.addRow("Default new table column alignment:", self.table_default_align_combo)

        # Minimum display width (px) an embedded Image / GIF / Video is
        # never rendered smaller than (height follows proportionally). 0
        # means no minimum. See Editor.media_intrinsic_size /
        # _min_media_width_for.
        min_size_widget = QWidget()
        min_size_layout = QFormLayout(min_size_widget)
        min_size_layout.setContentsMargins(0, 0, 0, 0)

        self.media_min_width_spins = {}
        media_min_size_rows = [
            ("image", "Image:"),
            ("gif", "GIF:"),
            ("video", "Video:"),
        ]
        for media_key, row_label in media_min_size_rows:
            spin = QSpinBox()
            spin.setRange(0, 4000)
            spin.setSuffix(" px")
            spin.setSpecialValueText("No minimum")
            spin.setValue(int(self.settings.get(f"media_min_width_{media_key}", 0)))
            self.media_min_width_spins[media_key] = spin
            min_size_layout.addRow(row_label, spin)

        layout.addRow("Minimum media size:", min_size_widget)

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

        self.settings["table_default_align"] = self.table_default_align_combo.currentData()

        for media_key, spin in self.media_min_width_spins.items():
            self.settings[f"media_min_width_{media_key}"] = spin.value()

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

        # Local files can be picked instead of typing/pasting a URL. The
        # chosen path is stored as a file:// URI, which open_hyperlink()
        # recognizes and launches via the system file explorer's default
        # file association, instead of the web browser.
        browse_btn = QPushButton("Choose local file…")
        browse_btn.clicked.connect(self._browse_local_file)

        url_row = QWidget()
        url_row_layout = QVBoxLayout(url_row)
        url_row_layout.setContentsMargins(0, 0, 0, 0)
        url_row_layout.addWidget(self.url_input)
        url_row_layout.addWidget(browse_btn)

        layout.addRow("Display text:", self.text_input)
        layout.addRow("URL Address:", url_row)

        self._removed = False

        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        if allow_remove:
            remove_btn = btn_box.addButton("Remove Link", QDialogButtonBox.DestructiveRole)
            remove_btn.clicked.connect(self._on_remove)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addRow(btn_box)

    def _browse_local_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose file")
        if not path:
            return
        # Stored as a plain path (no file:// prefix) - this is what
        # Markdown viewers/parsers actually expect for local-file links.
        self.url_input.setPlainText(path)
        # If no display text was entered yet, default it to the file name
        # so the inserted link isn't left blank.
        if not self.text_input.toPlainText().strip():
            self.text_input.setPlainText(os.path.basename(path))

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


class MediaDialog(QDialog):
    """Insert/edit an embedded media object - image, animated gif, video,
    or audio. Deliberately mirrors LinkDialog (same two-field + "browse a
    local file" layout) since the two dialogs do the same conceptual job;
    which one applies is decided later, purely by the file extension of
    whatever path/URL ends up here (see classify_media_path)."""

    MEDIA_FILE_FILTER = (
        "Multimedia (*.png *.jpg *.jpeg *.bmp *.webp *.svg *.ico *.tif *.tiff "
        "*.gif *.mp4 *.avi *.mkv *.mov *.webm *.wmv *.m4v *.mpg *.mpeg "
        "*.mp3 *.wav *.ogg *.flac *.m4a *.aac *.wma *.opus);;All files (*)"
    )

    def __init__(self, alt_text="", src="", parent=None, allow_remove=False):
        super().__init__(parent)
        self.setWindowTitle("Multimedia - MPad++")
        self.setMinimumWidth(640)
        self.setMinimumHeight(360)
        self.resize(680, 400)
        layout = QFormLayout(self)

        info = QLabel(
            "Supported: images, gifs, video and audio - as a local path,\n"
            "a relative path (e.g. .\\image.png, resolved from the saved .md file)\n"
            "or a URL. A player for video/audio is added automatically."
        )
        info.setWordWrap(True)
        layout.addRow(info)

        self.text_input = QPlainTextEdit(alt_text)
        self.text_input.setTabChangesFocus(True)
        self.text_input.setMinimumHeight(70)

        self.url_input = QPlainTextEdit(src)
        self.url_input.setTabChangesFocus(True)
        self.url_input.setMinimumHeight(70)
        url_cursor = self.url_input.textCursor()
        url_cursor.movePosition(QTextCursor.Start)
        self.url_input.setTextCursor(url_cursor)
        self.url_input.selectAll()

        browse_btn = QPushButton("Choose local file…")
        browse_btn.clicked.connect(self._browse_local_file)

        self.type_label = QLabel()
        self._update_type_label()
        self.url_input.textChanged.connect(self._update_type_label)

        url_row = QWidget()
        url_row_layout = QVBoxLayout(url_row)
        url_row_layout.setContentsMargins(0, 0, 0, 0)
        url_row_layout.addWidget(self.url_input)
        url_row_layout.addWidget(browse_btn)
        url_row_layout.addWidget(self.type_label)

        layout.addRow("Alt text:", self.text_input)
        layout.addRow("Path / URL:", url_row)

        self._removed = False

        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        if allow_remove:
            remove_btn = btn_box.addButton("Remove", QDialogButtonBox.DestructiveRole)
            remove_btn.clicked.connect(self._on_remove)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addRow(btn_box)

    def _update_type_label(self):
        src = " ".join(self.url_input.toPlainText().splitlines()).strip()
        media_type = classify_media_path(src)
        names = {"image": "image", "gif": "animated gif", "video": "video", "audio": "audio"}
        if not src:
            self.type_label.setText("")
        elif media_type:
            self.type_label.setText(f"Will be embedded as: {names[media_type]}")
        else:
            self.type_label.setText("Unrecognized extension - will be inserted as a plain link")

    def _browse_local_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose multimedia file", "", self.MEDIA_FILE_FILTER)
        if not path:
            return
        self.url_input.setPlainText(path)
        if not self.text_input.toPlainText().strip():
            self.text_input.setPlainText(os.path.basename(path))

    def _on_remove(self):
        self._removed = True
        self.accept()

    def is_removed(self):
        return self._removed

    def get_data(self):
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
        self.find_input.textChanged.connect(self._update_match_count)
        layout.addRow("Find:", self.find_input)

        self.replace_input = QLineEdit()
        self.replace_input.returnPressed.connect(self.replace_current)
        layout.addRow("Replace with:", self.replace_input)

        self.case_check = QCheckBox("Case sensitive")
        self.case_check.toggled.connect(self._update_match_count)
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

    def _count_matches(self, text):
        editor = self.get_editor()
        if not editor or not text:
            return 0
        doc = editor.document()
        flags = self._flags(backward=False)
        count = 0
        cursor = QTextCursor(doc)
        while True:
            cursor = doc.find(text, cursor, flags)
            if cursor.isNull():
                break
            count += 1
        return count

    def _match_position(self, text):
        """Total match count, plus the 1-based index of whichever match the
        editor's current selection sits on (0 if the selection isn't a
        match - e.g. before Find Next/Previous has been used yet)."""
        editor = self.get_editor()
        if not editor or not text:
            return 0, 0
        doc = editor.document()
        flags = self._flags(backward=False)
        sel_cursor = editor.textCursor()
        sel_start = sel_cursor.selectionStart() if sel_cursor.hasSelection() else None
        total = 0
        current_index = 0
        cursor = QTextCursor(doc)
        while True:
            cursor = doc.find(text, cursor, flags)
            if cursor.isNull():
                break
            total += 1
            if sel_start is not None and cursor.selectionStart() == sel_start:
                current_index = total
        return current_index, total

    def _update_match_count(self):
        text = self.find_input.text()
        if not text:
            self.status_label.setText("")
            return
        current_index, total = self._match_position(text)
        if total == 0:
            self.status_label.setText("Phrase not found")
        elif current_index:
            self.status_label.setText(f"{current_index}/{total}")
        else:
            self.status_label.setText(f"{total} occurrence{'s' if total != 1 else ''} found")

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
        # Report the total match count regardless of whether this
        # particular jump succeeded - "Phrase not found" only makes sense
        # when there really are zero matches in the whole document.
        self._update_match_count()

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
        self._update_match_count()


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

        # Footer/status bar: word & character counts for the active tab
        # plus the cursor's current line/column, refreshed on every edit
        # and every cursor move. QStatusBar was already themed above (see
        # apply_app_theme()) even though nothing had actually created one
        # yet.
        self.status_label = QLabel()
        self.statusBar().addPermanentWidget(self.status_label)
        self.update_status_bar()

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

        self.act_media = QAction("", self)
        self.act_media.setToolTip("Insert media (image / video / gif / audio)")
        self.act_media.triggered.connect(self.insert_media)
        toolbar.addAction(self.act_media)

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
            "media": self.act_media,
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
        editor.textChanged.connect(self.update_status_bar)
        editor.cursorPositionChanged.connect(self.update_status_bar)
        if switch:
            self.tab_widget.setCurrentIndex(index)
        self.update_status_bar()
        return editor

    def update_status_bar(self):
        """Refreshes the footer with the active tab's word/character
        counts and the cursor's current line/column. Hooked up to every
        editor's textChanged/cursorPositionChanged (in new_tab()) and to
        tab switching (in on_tab_changed()) so it always reflects
        whichever tab is currently showing, not just the one it was last
        connected for."""
        editor = self.get_editor()
        if not editor:
            self.status_label.setText("")
            return
        text = editor.toPlainText()
        char_count = len(text)
        word_count = len(text.split())
        cursor = editor.textCursor()
        line = cursor.blockNumber() + 1
        col = cursor.positionInBlock() + 1
        self.status_label.setText(
            f"Words: {word_count}    Characters: {char_count}    Ln {line}, Col {col}"
        )
        self.status_label.setStyleSheet("color: #ccc; padding-right: 6px;")

    def on_modification_changed(self, editor):
        self.update_tab_title(editor)
        if editor == self.tab_widget.currentWidget():
            self.update_window_title()

    def close_tab(self, index):
        editor = self.tab_widget.widget(index)
        if editor and editor.document().isModified():
            reply = QMessageBox.question(self, "Close Tab", "The tab has unsaved changes. Are you sure you want to close it?", QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.No: return
        if editor:
            editor.release_media_players()
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
        self.update_status_bar()

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
            cursor.setPosition(cell.lastCursorPosition().position(), QTextCursor.KeepAnchor)
            header.append(cursor.selectedText().replace('\n', ' '))
        md_lines.append("| " + " | ".join(header) + " |")

        sep_markers = {"left": "---", "center": ":---:", "right": "---:"}
        sep = [sep_markers.get(get_table_column_alignment(table, c), "---") for c in range(cols)]
        md_lines.append("| " + " | ".join(sep) + " |")
        
        for r in range(1, rows):
            row_data = []
            for c in range(cols):
                cell = table.cellAt(r, c)
                cursor = cell.firstCursorPosition()
                cursor.setPosition(cell.lastCursorPosition().position(), QTextCursor.KeepAnchor)
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

                if fmt.objectType() == MEDIA_OBJECT_TYPE:
                    alt = fmt.property(MEDIA_ALT_PROP) or ""
                    src = fmt.property(MEDIA_SRC_PROP) or ""
                    piece = f"![{self.escape_md_text(alt)}]({src})"
                elif is_code:
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
            editor.spell_highlighter.begin_bulk_load()
            try:
                editor.document().setMarkdown(content, QTextDocument.MarkdownDialectGitHub)
                apply_markdown_table_alignments(editor.document(), parse_markdown_table_alignments(content))
                editor.current_file = file_path
                editor.view_mode = "formatted"
                editor.replace_media_placeholders(extract_media_alt_map(content))
                editor.post_process_markdown()
                editor.style_tables()
                editor.apply_settings_to_document(restore_cursor=False)
                editor.document().setModified(False)
            finally:
                editor.spell_highlighter.end_bulk_load()

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
        for i in range(self.tab_widget.count()):
            editor = self.tab_widget.widget(i)
            if editor:
                editor.release_media_players()
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
            # See toggle_heading() for why this is wrapped in begin_bulk_load()/
            # end_bulk_load(), and why it walks real document blocks instead of
            # QTextCursor's visual-line Down.
            editor.spell_highlighter.begin_bulk_load()
            try:
                start = cursor.selectionStart()
                end = cursor.selectionEnd()
                doc = editor.document()

                start_block = doc.findBlock(start)
                end_block = doc.findBlock(end)
                end_block_number = end_block.blockNumber()

                first_block_fmt = start_block.blockFormat()
                toggle_off = (first_block_fmt.hasProperty(BLOCK_CODE_PROP) and first_block_fmt.property(BLOCK_CODE_PROP) == True)

                block = start_block
                while block.isValid():
                    block_cursor = QTextCursor(doc)
                    block_cursor.setPosition(block.position())
                    block_cursor.setPosition(block.position() + max(block.length() - 1, 0), QTextCursor.KeepAnchor)

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

                    block_cursor.setBlockFormat(new_block_fmt)
                    block_cursor.mergeCharFormat(new_char_fmt)

                    if block.blockNumber() >= end_block_number:
                        break
                    block = doc.findBlockByNumber(block.blockNumber() + 1)
            finally:
                cursor.endEditBlock()
                editor.spell_highlighter.end_bulk_load()
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

    def _apply_char_format_to_block(self, doc, block, char_fmt):
        """Apply char_fmt to every character in `block`, per fragment (so
        existing inline formatting - bold/italic spans, links, embedded
        images - is preserved rather than flattened), working around a
        genuine Qt/PySide bug that made toggle_heading()/toggle_quote()
        silently fail to ever repaint at the new size after the first
        toggle of a given line.

        Root cause (confirmed by inspecting the actual QTextCharFormat
        Qt produces): document().setMarkdown() renders headings using a
        *relative* QTextFormat.FontSizeAdjustment property (like HTML's
        h1-h6 cascading off the base font size), not an absolute
        fontPointSize - a block's very first fragment right after import
        has fontPointSize() == 0 and FontSizeAdjustment == 3 (for h1),
        etc. mergeCharFormat() - what this used to call, and what every
        earlier attempt at fixing this still used under the hood - only
        ever ADDS/OVERRIDES properties that are actually present on the
        format you pass it; it can't clear a property it doesn't know
        about, so that leftover FontSizeAdjustment survives every
        mergeCharFormat() call forever, and Qt's font resolution keeps
        applying it, which is what visually pinned the block at
        whatever size the *first* successful change happened to produce
        - explicit fontPointSize() looked correct when queried right
        back, but the adjustment kept overriding it at paint time.
        Forcing documentLayout().documentSize(), markContentsDirty(),
        block.layout().clearLayout(), a synchronous repaint(), or even
        deleting and re-inserting the block's text all failed to fix
        this, because none of them touch FontSizeAdjustment either.

        The fix is two-part, and BOTH parts are required (confirmed by
        testing each alone): explicitly clear FontSizeAdjustment on the
        format being applied, AND apply it with setCharFormat() (which
        replaces a fragment's format outright) rather than
        mergeCharFormat() (which - even passed a format with
        FontSizeAdjustment explicitly zeroed - was still observed to get
        stuck after the first toggle in testing, for reasons that could
        not be fully pinned down but are moot given setCharFormat()
        works reliably instead).

        Two passes, deliberately: the first only *reads* frag.position()/
        length()/charFormat() into a plain list while walking the
        block's fragment iterator; the second does the actual
        setCharFormat() edits afterwards, once that iterator is no
        longer in use. setCharFormat() can merge/split/reallocate the
        block's underlying fragment map (e.g. when a fragment's format
        ends up identical to its neighbour's), which invalidates the
        very iterator that produced it - editing through it in a single
        combined pass crashed the interpreter (a real, reproducible
        segfault, not just wrong results) as soon as a block had more
        than one fragment.
        """
        frag_specs = []
        it = block.begin()
        while not it.atEnd():
            frag = it.fragment()
            if frag.isValid() and frag.length() > 0:
                frag_specs.append((frag.position(), frag.length(), QTextCharFormat(frag.charFormat())))
            it += 1

        touched = False
        for frag_pos, frag_len, frag_fmt in frag_specs:
            frag_fmt.clearProperty(QTextFormat.FontSizeAdjustment)
            frag_fmt.merge(char_fmt)
            frag_cursor = QTextCursor(doc)
            frag_cursor.setPosition(frag_pos)
            frag_cursor.setPosition(frag_pos + frag_len, QTextCursor.KeepAnchor)
            frag_cursor.setCharFormat(frag_fmt)
            touched = True
        return touched

    def toggle_heading(self, level):
        editor = self.get_editor()
        if not editor: return
        cursor = editor.textCursor()
        cursor.beginEditBlock()
        # See toggle_heading() for why this is wrapped in begin_bulk_load()/
        # end_bulk_load() - same per-line formatting loop, same forced
        # synchronous spellcheck pass per line otherwise.
        editor.spell_highlighter.begin_bulk_load()
        try:
            start = cursor.selectionStart()
            end = cursor.selectionEnd()
            doc = editor.document()

            # Walk real document BLOCKS (paragraphs) rather than QTextCursor's
            # EndOfLine/Down, which move by *visual* line - i.e. they also
            # stop at soft line breaks (Shift+Enter, U+2028) and at word-wrap
            # points. A heading applies a much larger font size, which can
            # itself shift where a long/wrapped paragraph's wrap points fall
            # mid-loop; navigating by visual line in that situation is
            # exactly the case (already hit and fixed the same way in
            # toggle_list()) that lets Down snap back to the SAME visual line
            # forever - an infinite loop (the app hanging) instead of a clean
            # per-paragraph pass. Blocks aren't affected by wrapping or soft
            # breaks, so this can't happen here.
            start_block = doc.findBlock(start)
            end_block = doc.findBlock(end)
            end_block_number = end_block.blockNumber()

            toggle_off = (start_block.blockFormat().headingLevel() == level)

            # Same for every block touched by this call (one toggle_off/
            # level per call, not per block) - computed once instead of
            # inside the loop below.
            char_fmt = QTextCharFormat()
            if toggle_off:
                char_fmt.setFontPointSize(self.settings["font_size"])
                char_fmt.setForeground(QColor(self.settings["editor_text"]))
                char_fmt.setFontWeight(QFont.Normal)
            else:
                size = self.settings.get(f"h{level}_size", 0)
                # See apply_settings_to_document() for why this falls
                # back to the heading level's own default size (not the
                # global font_size) when sized at "Default" (0).
                if size == 0: size = DEFAULT_SETTINGS.get(f"h{level}_size", self.settings["font_size"])
                char_fmt.setFontPointSize(size)
                char_fmt.setForeground(QColor(self.settings[f"h{level}"]))
                char_fmt.setFontWeight(QFont.Bold)

            block = start_block
            while block.isValid():
                block_cursor = QTextCursor(doc)
                block_cursor.setPosition(block.position())
                # block.length() includes the trailing paragraph separator;
                # stop one short of it so the format doesn't spill into the
                # next block.
                block_cursor.setPosition(block.position() + max(block.length() - 1, 0), QTextCursor.KeepAnchor)

                block_fmt = block_cursor.blockFormat()
                block_fmt.setHeadingLevel(0 if toggle_off else level)

                block_cursor.setBlockFormat(block_fmt)
                # See _apply_char_format_to_block()'s docstring for why this
                # applies the format per-fragment via setCharFormat() rather
                # than a single mergeCharFormat() call - the latter left a
                # heading permanently stuck at whatever size the *first*
                # toggle happened to produce. touched is False only for an
                # empty block (nothing to apply to) - see the explicit
                # cursor.setCharFormat() fallback below for that case.
                touched = self._apply_char_format_to_block(doc, block, char_fmt)

                if block.blockNumber() >= end_block_number:
                    break
                block = doc.findBlockByNumber(block.blockNumber() + 1)
        finally:
            cursor.endEditBlock()
            editor.spell_highlighter.end_bulk_load()
        editor.setTextCursor(cursor)
        if not cursor.hasSelection():
            # The block(s) just got their character formatting rewritten via
            # separate, throwaway cursors above - the actual editor cursor
            # being restored here never had setCharFormat() called on it.
            # For a normal selection that's harmless (there's existing text
            # already carrying the new format to look at), but for a bare
            # caret - most commonly an empty line, e.g. right after the
            # "# " live-heading shortcut, or clicking a heading button
            # before typing anything - there are no characters yet for
            # _apply_char_format_to_block() to have touched, so without this
            # the next characters typed would silently keep the old
            # formatting instead of picking up the heading's size/color/
            # weight.
            cursor.setCharFormat(char_fmt)
            editor.setTextCursor(cursor)
        self.update_toolbar_state()

    def toggle_quote(self):
        editor = self.get_editor()
        if not editor: return
        cursor = editor.textCursor()
        cursor.beginEditBlock()
        # See toggle_heading() for why this is wrapped in begin_bulk_load()/
        # end_bulk_load(), and why it walks real document blocks instead of
        # QTextCursor's visual-line EndOfLine/Down.
        editor.spell_highlighter.begin_bulk_load()
        try:
            start = cursor.selectionStart()
            end = cursor.selectionEnd()
            doc = editor.document()

            start_block = doc.findBlock(start)
            end_block = doc.findBlock(end)
            end_block_number = end_block.blockNumber()

            block_fmt_check = start_block.blockFormat()
            toggle_off = (block_fmt_check.hasProperty(QUOTE_PROP) and block_fmt_check.property(QUOTE_PROP) == True)

            char_fmt = QTextCharFormat()
            if toggle_off:
                char_fmt.setFontItalic(False)
                char_fmt.setForeground(QColor(self.settings['editor_text']))
            else:
                char_fmt.setFontItalic(True)
                char_fmt.setForeground(QColor(self.settings['quote']))

            block = start_block
            while block.isValid():
                block_cursor = QTextCursor(doc)
                block_cursor.setPosition(block.position())
                block_cursor.setPosition(block.position() + max(block.length() - 1, 0), QTextCursor.KeepAnchor)

                block_fmt = block_cursor.blockFormat()
                if toggle_off:
                    block_fmt.setLeftMargin(0)
                    block_fmt.setProperty(QUOTE_PROP, False)
                else:
                    block_fmt.setLeftMargin(15)
                    block_fmt.setProperty(QUOTE_PROP, True)

                block_cursor.setBlockFormat(block_fmt)
                # See toggle_heading()/_apply_char_format_to_block() for why
                # this applies per-fragment via setCharFormat() instead of
                # mergeCharFormat(), and why an empty block needs the
                # explicit cursor.setCharFormat() fallback below too.
                touched = self._apply_char_format_to_block(doc, block, char_fmt)

                if block.blockNumber() >= end_block_number:
                    break
                block = doc.findBlockByNumber(block.blockNumber() + 1)
        finally:
            cursor.endEditBlock()
            editor.spell_highlighter.end_bulk_load()
        editor.setTextCursor(cursor)
        if not cursor.hasSelection():
            cursor.setCharFormat(char_fmt)
            editor.setTextCursor(cursor)
        self.update_toolbar_state()

    def toggle_list(self, list_type):
        editor = self.get_editor()
        if not editor: return
        cursor = editor.textCursor()
        cursor.beginEditBlock()
        
        start = cursor.selectionStart()
        end = cursor.selectionEnd()
        doc = editor.document()
        
        start_block = doc.findBlock(start)
        end_block = doc.findBlock(end)
        end_block_number = end_block.blockNumber()
        
        line_text = start_block.text().strip()
        toggle_off = False
        
        is_ul = line_text.startswith("• ") or line_text.startswith("- ") or line_text.startswith("* ")
        is_ol = len(line_text) > 2 and line_text[0].isdigit() and line_text[1] == '.' and line_text[2] == ' '
        
        if list_type == "ul":
            if is_ul: toggle_off = True
        else:
            if is_ol: toggle_off = True

        # A marker's own formatting - deliberately plain, so it never
        # inherits whatever character format (link, bold, custom color...)
        # happens to sit at the start of the line's actual content.
        marker_fmt = QTextCharFormat()
        marker_fmt.setForeground(QColor(self.settings['editor_text']))
        marker_fmt.setFontFamilies([self.settings['font_family']])
        marker_fmt.setFontPointSize(self.settings['font_size'])
        marker_fmt.setFontWeight(QFont.Normal)
        marker_fmt.setFontItalic(False)
        marker_fmt.setFontUnderline(False)
        marker_fmt.setAnchor(False)
        marker_fmt.setAnchorHref("")
        marker_fmt.setProperty(CODE_PROP, False)

        # Walk real document BLOCKS (paragraphs) rather than QTextCursor's
        # EndOfLine/Down, which move by *visual* line - i.e. they also stop
        # at soft line breaks (Shift+Enter, U+2028) and at word-wrap points.
        # Growing the text on every step (adding/renumbering markers) while
        # navigating by visual line was exactly the case that let Down snap
        # back to the SAME line start forever once a soft-wrapped block's
        # wrap point shifted mid-loop - an infinite loop (the app hanging)
        # rather than a clean per-item pass. Blocks aren't affected by
        # wrapping or soft breaks, so this can't happen here, and it also
        # matches how every other list-line an item is already treated
        # elsewhere in this class (one block = one list item).
        counter = 1
        block = start_block
        while block.isValid():
            block_text = block.text()

            if block_text.startswith("• ") or block_text.startswith("- ") or block_text.startswith("* "):
                old_marker_len = 2
            elif len(block_text) > 2 and block_text[0].isdigit() and block_text[1] == '.' and block_text[2] == ' ':
                old_marker_len = 3
            else:
                old_marker_len = 0

            if not toggle_off:
                if list_type == "ul":
                    new_marker = "• "
                else:
                    new_marker = f"{counter}. "
                counter += 1
            else:
                new_marker = ""

            old_marker = block_text[:old_marker_len]
            if new_marker != old_marker:
                # Only the marker prefix is ever selected/replaced here -
                # the rest of the line's text (and its formatting, whatever
                # it is) is never touched, so it can't be flattened into one
                # uniform format the way replacing the whole line used to.
                edit_cursor = QTextCursor(doc)
                edit_cursor.setPosition(block.position())
                if old_marker_len:
                    edit_cursor.setPosition(block.position() + old_marker_len, QTextCursor.KeepAnchor)
                    edit_cursor.removeSelectedText()
                if new_marker:
                    edit_cursor.insertText(new_marker, marker_fmt)

            if block.blockNumber() >= end_block_number:
                break
            block = doc.findBlockByNumber(block.blockNumber() + 1)
            
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
            table = cursor.currentTable()
            default_align = self.settings.get("table_default_align", "left")
            if default_align != "left" and table:
                for c in range(cols):
                    set_table_column_alignment(table, c, default_align)
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
        def add_row():
            table.insertRows(row + 1, 1)
            # New row's cells start with no explicit alignment - bring them
            # in line with the rest of their column.
            sync_table_column_alignments(table)
            editor.style_tables()
        btn_add_row.clicked.connect(add_row)
        layout.addWidget(btn_add_row)
        
        btn_del_row = QPushButton("Delete cursor row")
        def del_row():
            if table.rows() > 1: table.removeRows(row, 1)
            editor.style_tables()
        btn_del_row.clicked.connect(del_row)
        layout.addWidget(btn_del_row)
        
        btn_add_col = QPushButton("Add column to the right")
        btn_add_col.clicked.connect(lambda: (table.insertColumns(col + 1, 1), editor.style_tables(), refresh_align_combos()))
        layout.addWidget(btn_add_col)
        
        btn_del_col = QPushButton("Delete cursor column")
        def del_col():
            if table.columns() > 1: table.removeColumns(col, 1)
            editor.style_tables()
            refresh_align_combos()
        btn_del_col.clicked.connect(del_col)
        layout.addWidget(btn_del_col)

        # Markdown only aligns a table by whole COLUMN (the ":---"/"---:"/
        # ":---:" separator marker applies to every row of that column
        # alike), so one alignment control per column - applied straight to
        # that column's cells - is what the format actually supports, unlike
        # the old separate "header row" / "other rows" settings.
        align_row = QWidget()
        align_form = QFormLayout(align_row)
        align_form.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(align_row)

        def refresh_align_combos():
            while align_form.rowCount():
                align_form.removeRow(0)
            for c in range(table.columns()):
                combo = QComboBox()
                combo.addItem("Left", "left")
                combo.addItem("Center", "center")
                combo.addItem("Right", "right")
                current = get_table_column_alignment(table, c)
                idx = combo.findData(current)
                combo.setCurrentIndex(idx if idx >= 0 else 0)
                combo.currentIndexChanged.connect(
                    lambda _, col=c, cmb=combo: (
                        set_table_column_alignment(table, col, cmb.currentData()),
                        editor.style_tables(),
                    )
                )
                align_form.addRow(f"Column {c + 1} alignment:", combo)

        refresh_align_combos()

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

    def insert_media(self):
        editor = self.get_editor()
        if not editor: return
        cursor = editor.textCursor()
        default_alt = cursor.selectedText() if cursor.hasSelection() else ""

        dialog = MediaDialog(default_alt, "", self)
        if dialog.exec() == QDialog.Accepted:
            alt, src = dialog.get_data()
            if not src:
                return
            if not alt:
                alt = os.path.basename(src.split("?", 1)[0].split("#", 1)[0]) or "media"
            media_type = classify_media_path(src)
            if cursor.hasSelection():
                cursor.removeSelectedText()
                editor.setTextCursor(cursor)
            if media_type:
                editor.insert_media_object(media_type, src, alt)
            else:
                # Not a recognized image/gif/video/audio extension - falls
                # back to a plain hyperlink instead of an embedded object.
                fmt = QTextCharFormat()
                fmt.setAnchor(True)
                fmt.setAnchorHref(src)
                fmt.setForeground(QColor(self.settings['link']))
                fmt.setFontUnderline(self.settings.get("link_underline", True))
                cursor = editor.textCursor()
                cursor.insertText(alt, fmt)
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

    # --- Embedded media: "Settings" context-menu options ---

    def _media_object_cursor(self, editor, obj_pos):
        """Select exactly the one ObjectReplacementCharacter of the media
        object at `obj_pos` (as returned by Editor._media_object_at)."""
        last = editor.document().characterCount() - 1
        cursor = QTextCursor(editor.document())
        cursor.setPosition(obj_pos)
        cursor.setPosition(min(obj_pos + 1, last), QTextCursor.KeepAnchor)
        return cursor

    def edit_media_from_menu(self, editor, obj_pos, fmt):
        old_alt = fmt.property(MEDIA_ALT_PROP) or ""
        old_src = fmt.property(MEDIA_SRC_PROP) or ""
        dialog = MediaDialog(old_alt, old_src, self, allow_remove=True)
        if dialog.exec() != QDialog.Accepted:
            return
        cursor = self._media_object_cursor(editor, obj_pos)
        if dialog.is_removed():
            cursor.removeSelectedText()
            editor.setTextCursor(cursor)
            return
        alt, src = dialog.get_data()
        if not src:
            return
        if not alt:
            alt = os.path.basename(src.split("?", 1)[0].split("#", 1)[0]) or "media"
        media_type = classify_media_path(src)
        if media_type:
            new_fmt = QTextCharFormat()
            new_fmt.setObjectType(MEDIA_OBJECT_TYPE)
            new_fmt.setProperty(MEDIA_TYPE_PROP, media_type)
            new_fmt.setProperty(MEDIA_SRC_PROP, src)
            new_fmt.setProperty(MEDIA_ALT_PROP, alt)
            # A changed source needs a fresh player/controller; an
            # unchanged one keeps its id so playback isn't interrupted.
            new_fmt.setProperty(MEDIA_ID_PROP, fmt.property(MEDIA_ID_PROP) if src == old_src else str(uuid.uuid4()))
            new_fmt.setProperty(MEDIA_SCALE_PROP, fmt.property(MEDIA_SCALE_PROP) or 1.0)
            cursor.removeSelectedText()
            cursor.insertText("\ufffc", new_fmt)
        else:
            # Not a recognized image/gif/video/audio extension anymore -
            # falls back to a plain hyperlink, same as insert_media().
            link_fmt = QTextCharFormat()
            link_fmt.setAnchor(True)
            link_fmt.setAnchorHref(src)
            link_fmt.setForeground(QColor(self.settings['link']))
            link_fmt.setFontUnderline(self.settings.get("link_underline", True))
            cursor.removeSelectedText()
            cursor.insertText(alt, link_fmt)
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
        # Don't rely on view_action_group's exclusivity here: a QActionGroup
        # enforces "only one checked" by listening to each member action's
        # own toggled signal and un-checking its siblings when one fires -
        # but blockSignals() above (needed so setChecked() here doesn't
        # re-trigger set_view_mode() through the actions' triggered/toggled
        # connections) also blocks that internal toggled signal. So calling
        # setChecked(True) on just one action never told the group to
        # un-check the other, and both ended up showing as checked at once
        # once the previously-active one had already been checked before.
        # Setting both explicitly avoids depending on that signal at all.
        is_plain = (editor.view_mode == "plain")
        self.act_view_plain.setChecked(is_plain)
        self.act_view_formatted.setChecked(not is_plain)
        self.act_view_formatted.blockSignals(False)
        self.act_view_plain.blockSignals(False)

    def update_formatting_actions_enabled(self):
        editor = self.get_editor()
        is_plain = bool(editor) and editor.view_mode == "plain"
        actions = [self.act_bold, self.act_italic, self.act_underline, self.act_code,
                   self.act_quote, self.act_ul, self.act_ol, self.act_table,
                   self.act_hr, self.act_link, self.act_media] + list(self.h_actions.values())
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

        # Both branches below replace the whole document's content/formatting
        # at once, which would otherwise force QSyntaxHighlighter to
        # synchronously re-scan every block in one go - see
        # SpellCheckHighlighter.begin_bulk_load() for why that freezes the
        # app on a large document. end_bulk_load() (in both the success and
        # error paths below) hands the real highlighting back off to be done
        # in small, non-blocking chunks.
        editor.spell_highlighter.begin_bulk_load()
        try:
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
                apply_markdown_table_alignments(editor.document(), parse_markdown_table_alignments(text))
                editor.replace_media_placeholders(extract_media_alt_map(text))
                editor.post_process_markdown()
                editor.apply_settings_to_document(restore_cursor=False)
                editor.style_tables()
        except Exception as e:
            editor.spell_highlighter.end_bulk_load()
            # A failure partway through must never leave the document stuck
            # with undo/redo disabled, or the View menu's checkmark out of
            # sync with editor.view_mode (which is only updated below, once
            # the switch has actually succeeded) - both of which used to
            # happen here and made the editor look "stuck" mid-switch.
            editor.document().setUndoRedoEnabled(True)
            editor.document().setModified(was_modified)
            self.update_view_menu_state()
            self.update_formatting_actions_enabled()
            if had_focus:
                editor.setFocus(Qt.OtherFocusReason)
            QMessageBox.critical(self, "Error", f"Could not switch view:\n{e}")
            return
        else:
            editor.spell_highlighter.end_bulk_load()

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
            # Minimum media width may have changed - force every open
            # document to relayout its embedded image/gif/video objects so
            # the new minimum takes effect immediately, not just on next
            # edit/reopen.
            for i in range(self.tab_widget.count()):
                editor = self.tab_widget.widget(i)
                editor.settings = self.settings
                editor.document().markContentsDirty(0, editor.document().characterCount())
                editor.viewport().update()

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
