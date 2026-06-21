import sys
import json
import os
import webbrowser
from PySide6.QtWidgets import (QApplication, QMainWindow, QTextEdit, QVBoxLayout, 
                               QHBoxLayout, QWidget, QToolBar, QDialog, 
                               QLabel, QLineEdit, QDialogButtonBox, QColorDialog, 
                               QPushButton, QFormLayout, QSpinBox, QFontDialog, 
                               QMessageBox, QFileDialog, QMenu, QToolButton, QCheckBox,
                               QTabWidget, QSizePolicy)
from PySide6.QtGui import (QColor, QTextCharFormat, QKeySequence, QShortcut, QFont, 
                           QAction, QTextCursor, QDragEnterEvent, QDropEvent, 
                           QTextDocument, QBrush, QPainter, QTextFormat, QPen, QIcon)
from PySide6.QtCore import QRegularExpression, Qt, QFileInfo, QPoint, QSize, QRect

# --- Default settings ---
DEFAULT_SETTINGS = {
    "app_bg": "#1e1e1e",
    "app_text": "#d4d4d4",
    "editor_bg": "#1e1e1e",
    "editor_text": "#d4d4d4",
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
    "link": "#3794ff", "link_size": 0,
    "link_underline": True,
    
    "table_header_bg": "#673AB7",
    "table_header_text": "#FFFFFF",
    "table_row1_bg": "#252526",
    "table_row2_bg": "#2d2d2d",
    
    "tab_active_bg": "#1e1e1e",
    "tab_inactive_bg": "#2d2d2d",
    "tab_active_bar_color": "#007acc"
}

CODE_PROP = QTextFormat.UserProperty + 1
QUOTE_PROP = QTextFormat.UserProperty + 2

class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self):
        return QSize(self.editor.line_number_area_width(), 0)

    def paintEvent(self, event):
        self.editor.line_number_area_paint_event(event)


class Editor(QTextEdit):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.current_file = None
        self.setAcceptDrops(True)
        self.apply_settings()

        self.line_number_area = LineNumberArea(self)
        self.textChanged.connect(self.update_line_number_area_width)
        self.verticalScrollBar().valueChanged.connect(self.line_number_area.update)
        self.cursorPositionChanged.connect(self.highlight_current_line)
        self.cursorPositionChanged.connect(self.line_number_area.update)
        
        # Gear button for tables
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

    def apply_settings(self):
        self.setStyleSheet(f"QTextEdit {{ background-color: {self.settings['editor_bg']}; color: {self.settings['editor_text']}; border: none; }}")
        font = QFont(self.settings["font_family"], self.settings["font_size"])
        self.setFont(font)
        
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

    def paintEvent(self, event):
        super().paintEvent(event)
        
        painter = QPainter(self.viewport())
        line_width = self.settings.get('quote_line_width', 3)
        line_color = QColor(self.settings.get('quote_line_color', '#5c5c5c'))
        painter.setPen(QPen(line_color, line_width))
        
        block = self.document().firstBlock()
        viewport_height = self.viewport().height()
        
        while block.isValid():
            rect = self.document().documentLayout().blockBoundingRect(block)
            top = int(rect.top() - self.verticalScrollBar().value())
            bottom = int(rect.bottom() - self.verticalScrollBar().value())
            
            if top > viewport_height:
                break
                
            if block.isVisible() and block.blockFormat().property(QUOTE_PROP) is True:
                if bottom > 0:
                    x = max(2, line_width // 2)
                    painter.drawLine(x, top, x, bottom)
                    
            block = block.next()

    def highlight_current_line(self):
        extra_selections = []
        selection = QTextEdit.ExtraSelection()
        line_color = QColor(self.settings['editor_bg']).lighter(115)
        selection.format.setBackground(line_color)
        selection.format.setProperty(QTextFormat.FullWidthSelection, True)
        selection.cursor = self.textCursor()
        selection.cursor.clearSelection()
        extra_selections.append(selection)
        self.setExtraSelections(extra_selections)

    def line_number_area_paint_event(self, event):
        painter = QPainter(self.line_number_area)
        painter.fillRect(event.rect(), QColor(self.settings['editor_bg']).darker(110))
        
        block = self.document().firstBlock()
        block_number = 0
        viewport_height = self.viewport().height()
        line_height = self.fontMetrics().height()
        prev_top = -9999
        
        while block.isValid():
            rect = self.document().documentLayout().blockBoundingRect(block)
            top = int(rect.top() - self.verticalScrollBar().value())
            bottom = int(rect.bottom() - self.verticalScrollBar().value())
            
            if top > viewport_height:
                break
                
            if block.isVisible() and bottom > 0:
                # If the block is lower than the previous one (difference greater than half the line height),
                # it means it is a new visual line (works for regular text and tables!)
                if top - prev_top > line_height / 2:
                    # Calculate how many lines this block occupies (e.g., wrapped text)
                    num_lines = max(1, round(rect.height() / line_height))
                    block_number += num_lines
                    prev_top = top
                    
                    for i in range(num_lines):
                        y_pos = top + i * line_height
                        painter.setPen(QColor("#858585"))
                        painter.drawText(0, y_pos, self.line_number_area.width() - 5, line_height,
                                         Qt.AlignRight | Qt.AlignVCenter, str(block_number - num_lines + 1 + i))
                # If the block is at the same level as the previous one (e.g., another table cell in the same row),
                # we ignore it (do not increase the numbering and do not draw).
                
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

    def contextMenuEvent(self, event):
        cursor = self.cursorForPosition(event.pos())
        fmt = cursor.charFormat()
        
        if not fmt.isAnchor():
            temp = QTextCursor(cursor)
            if temp.position() < self.document().characterCount() - 1:
                temp.setPosition(temp.position() + 1)
                if temp.charFormat().isAnchor():
                    cursor = temp
                    fmt = temp.charFormat()

        menu = self.createStandardContextMenu()
        
        if fmt.isAnchor():
            href = fmt.anchorHref()
            start_pos = cursor.position()
            end_pos = cursor.position()
            
            while start_pos > 0:
                temp = QTextCursor(self.document())
                temp.setPosition(start_pos - 1)
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
            
            edit_action = QAction("Edit Hyperlink", menu)
            edit_action.triggered.connect(lambda: self.window().edit_link_from_menu(self, anchor_cursor, text, href))
            menu.addAction(edit_action)
            
        menu.exec(event.globalPos())

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event: QDropEvent):
        if event.mimeData().hasUrls():
            url = event.mimeData().urls()[0]
            if url.isLocalFile():
                file_path = url.toLocalFile()
                if file_path.endswith('.md') or file_path.endswith('.txt'):
                    self.window().open_file_path(file_path, target_editor=self)
                    return
        super().dropEvent(event)
        
    def apply_settings_to_document(self):
        updates = []
        block = self.document().firstBlock()
        while block.isValid():
            cursor = QTextCursor(block)
            if cursor.currentTable():
                block = block.next()
                continue
                
            block_fmt = block.blockFormat()
            level = block_fmt.headingLevel()
            is_quote = (block_fmt.property(QUOTE_PROP) is True)
            
            it = block.begin()
            while not it.atEnd():
                frag = it.fragment()
                if frag.isValid() and frag.length() > 0:
                    fmt = QTextCharFormat(frag.charFormat())
                    changed = False
                    
                    is_code = (fmt.property(CODE_PROP) is True)
                    fam = ""
                    if fmt.fontFamilies():
                        fam = fmt.fontFamilies()[0]
                    if not is_code and fam:
                        if "mono" in fam.lower() or "consolas" in fam.lower():
                            is_code = True
                            fmt.setProperty(CODE_PROP, True)
                            
                    is_anchor = fmt.isAnchor()
                    is_bold = (fmt.fontWeight() == QFont.Bold)
                    is_italic = fmt.fontItalic()
                    is_underline = fmt.fontUnderline()
                    
                    if is_code:
                        fmt.setBackground(QColor(self.settings['code_bg']))
                        fmt.setForeground(QColor(self.settings['code']))
                        fmt.setFontFamilies(["Consolas"])
                        changed = True
                    elif is_anchor:
                        fmt.setForeground(QColor(self.settings['link']))
                        fmt.setFontUnderline(self.settings.get("link_underline", True))
                        changed = True
                    elif level > 0:
                        fmt.setForeground(QColor(self.settings[f"h{level}"]))
                        size = self.settings.get(f"h{level}_size", 0)
                        if size == 0: size = self.settings["font_size"]
                        fmt.setFontPointSize(size)
                        fmt.setFontWeight(QFont.Bold)
                        changed = True
                    elif is_quote:
                        fmt.setForeground(QColor(self.settings['quote']))
                        fmt.setFontItalic(True)
                        changed = True
                    else:
                        fmt.setForeground(QColor(self.settings['editor_text']))
                        changed = True
                        if is_bold:
                            fmt.setForeground(QColor(self.settings['bold']))
                        if is_italic:
                            fmt.setForeground(QColor(self.settings['italic']))
                        if is_underline:
                            fmt.setForeground(QColor(self.settings['underline']))
                            
                    if changed:
                        updates.append((frag.position(), frag.length(), fmt))
                it += 1
            block = block.next()
            
        cur = QTextCursor(self.document())
        cur.beginEditBlock()
        for pos, length, fmt in updates:
            cur.setPosition(pos)
            cur.setPosition(pos + length, QTextCursor.KeepAnchor)
            cur.setCharFormat(fmt)
        cur.endEditBlock()

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


class EditorTabs(QTabWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTabsClosable(True)
        self.setMovable(True)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)
        
        self.plus_btn = QToolButton(self)
        self.plus_btn.setText("+")
        self.plus_btn.setToolTip("New Tab")
        self.plus_btn.setAutoRaise(True)
        self.setCornerWidget(self.plus_btn, Qt.TopRightCorner)

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
        
        layout = QFormLayout(self)
        self.color_buttons = {}
        self.size_spins = {}

        self.add_color_picker(layout, "App Background", "app_bg")
        self.add_color_picker(layout, "Editor Background", "editor_bg")
        self.add_color_picker(layout, "Normal Text", "editor_text")

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

        layout.addRow(QLabel("--- Table Colors ---"))
        self.add_color_picker(layout, "Header (background)", "table_header_bg")
        self.add_color_picker(layout, "Header (text)", "table_header_text")
        self.add_color_picker(layout, "Row 1 (background)", "table_row1_bg")
        self.add_color_picker(layout, "Row 2 (background)", "table_row2_bg")

        layout.addRow(QLabel("--- Tab Colors ---"))
        self.add_color_picker(layout, "Active tab (background)", "tab_active_bg")
        self.add_color_picker(layout, "Inactive tab (background)", "tab_inactive_bg")
        self.add_color_picker(layout, "Active tab bar", "tab_active_bar_color")

        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addRow(btn_box)

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
        super().accept()

    def get_settings(self):
        return self.settings


class LinkDialog(QDialog):
    def __init__(self, selected_text, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Hyperlink - MPad++")
        layout = QFormLayout(self)

        self.text_input = QLineEdit(selected_text)
        self.url_input = QLineEdit("https://")

        layout.addRow("Display text:", self.text_input)
        layout.addRow("URL Address:", self.url_input)

        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addRow(btn_box)

    def get_data(self):
        return self.text_input.text(), self.url_input.text()


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


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MPad++")
        self.resize(800, 600)
        
        # Setting application icon
        icon_path = os.path.join("icons", "notepad.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.settings_file = "mpad_settings.json"
        self.settings = self.load_settings()
        
        self.apply_app_theme()

        self.tab_widget = EditorTabs(self)
        self.tab_widget.tabCloseRequested.connect(self.close_tab)
        self.tab_widget.currentChanged.connect(self.on_tab_changed)
        self.tab_widget.plus_btn.clicked.connect(lambda: self.new_tab())
        
        # Container with 3px top margin to separate tabs from toolbar
        container = QWidget()
        container.setObjectName("TopGapContainer")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 3, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.tab_widget)
        self.setCentralWidget(container)
        
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
            #TopGapContainer {{ background-color: #2d2d2d; }}
            QTabWidget::pane {{ border: none; background: {self.settings['editor_bg']}; }}
            QTabBar::tab {{ background: {self.settings['tab_inactive_bg']}; color: #888; padding: 5px 12px 8px 12px; border: 1px solid #1e1e1e; border-top: 3px solid transparent; }}
            QTabBar::tab:selected {{ background: {self.settings['tab_active_bg']}; color: {self.settings['app_text']}; border-bottom: none; border-top: 3px solid {self.settings['tab_active_bar_color']}; }}
            QTabBar::tab:hover:!selected {{ background: #383838; }}
            QTabBar::close-button {{ image: none; subcontrol-position: right; margin: 2px; border-radius: 2px; }}
            QTabBar::close-button:hover {{ background: #ff4d4d; }}
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
        
        settings_menu = menubar.addMenu("Settings")
        config_action = QAction("Configure Styles", self)
        config_action.triggered.connect(self.open_settings)
        settings_menu.addAction(config_action)

    def create_toolbar(self):
        toolbar = QToolBar("Formatting")
        toolbar.setMovable(False)
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

        self.act_bold = QAction("B", self); self.act_bold.setCheckable(True)
        self.act_bold.triggered.connect(self.toggle_bold)
        toolbar.addAction(self.act_bold)

        self.act_italic = QAction("I", self); self.act_italic.setCheckable(True)
        self.act_italic.triggered.connect(self.toggle_italic)
        toolbar.addAction(self.act_italic)

        self.act_underline = QAction("U", self); self.act_underline.setCheckable(True)
        self.act_underline.triggered.connect(self.toggle_underline)
        toolbar.addAction(self.act_underline)

        self.act_code = QAction("Code", self); self.act_code.setCheckable(True)
        self.act_code.triggered.connect(self.toggle_code)
        toolbar.addAction(self.act_code)

        self.act_quote = QAction("Quote", self); self.act_quote.setCheckable(True)
        self.act_quote.triggered.connect(self.toggle_quote)
        toolbar.addAction(self.act_quote)

        toolbar.addSeparator()

        self.act_ul = QAction("UL", self); self.act_ul.setCheckable(True)
        self.act_ul.triggered.connect(lambda: self.toggle_list("ul"))
        toolbar.addAction(self.act_ul)

        self.act_ol = QAction("OL", self); self.act_ol.setCheckable(True)
        self.act_ol.triggered.connect(lambda: self.toggle_list("ol"))
        toolbar.addAction(self.act_ol)

        self.act_table = QAction("Table", self)
        self.act_table.triggered.connect(self.insert_table)
        toolbar.addAction(self.act_table)

        toolbar.addSeparator()

        self.act_link = QAction("Link", self); self.act_link.setCheckable(True)
        self.act_link.triggered.connect(self.insert_link)
        toolbar.addAction(self.act_link)

    def update_toolbar_margin(self):
        editor = self.tab_widget.currentWidget()
        if editor:
            self.toolbar_spacer.setFixedWidth(editor.line_number_area_width())

    def create_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+D"), self, activated=self.duplicate_line)
        QShortcut(QKeySequence("Alt+Up"), self, activated=lambda: self.move_line(-1))
        QShortcut(QKeySequence("Alt+Down"), self, activated=lambda: self.move_line(1))

    # --- Tab Management ---
    def new_tab(self, switch=True):
        editor = Editor(self.settings, self)
        index = self.tab_widget.addTab(editor, "New")
        if switch:
            self.tab_widget.setCurrentIndex(index)
        return editor

    def close_tab(self, index):
        editor = self.tab_widget.widget(index)
        if editor and not editor.document().isEmpty():
            reply = QMessageBox.question(self, "Close Tab", "The tab is not empty. Are you sure you want to close it?", QMessageBox.Yes | QMessageBox.No)
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

    def update_tab_title(self, editor):
        idx = self.tab_widget.indexOf(editor)
        if editor.current_file:
            self.tab_widget.setTabText(idx, os.path.basename(editor.current_file))
            self.tab_widget.setTabToolTip(idx, editor.current_file)
        else:
            self.tab_widget.setTabText(idx, "New")
            self.tab_widget.setTabToolTip(idx, "")

    def update_window_title(self):
        editor = self.tab_widget.currentWidget()
        if editor and editor.current_file:
            self.setWindowTitle(f"MPad++ - {os.path.basename(editor.current_file)}")
        else:
            self.setWindowTitle("MPad++")

    # --- File Operations ---
    def open_file_dialog(self, in_new_tab=False):
        file_path, _ = QFileDialog.getOpenFileName(self, "Open File", "", "Markdown (*.md);;Text files (*.txt)")
        if file_path:
            self.open_file_path(file_path, in_new_tab=in_new_tab)

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
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            editor.document().setMarkdown(content, QTextDocument.MarkdownDialectGitHub)
            editor.current_file = file_path
            editor.style_tables()
            editor.apply_settings_to_document()
            self.update_tab_title(editor)
            self.update_window_title()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Cannot open file:\n{str(e)}")

    def save_file(self):
        editor = self.tab_widget.currentWidget()
        if not editor: return
        if not editor.current_file:
            self.save_as_file()
            return
        try:
            markdown_content = editor.document().toMarkdown(QTextDocument.MarkdownDialectGitHub)
            with open(editor.current_file, 'w', encoding='utf-8') as f:
                f.write(markdown_content)
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
            if editor and not editor.document().isEmpty():
                reply = QMessageBox.question(self, "Exit", "Some tabs are not empty. Are you sure you want to close the program?", QMessageBox.Yes | QMessageBox.No)
                if reply == QMessageBox.No:
                    event.ignore()
                    return
                break
        event.accept()

    # --- WYSIWYG Formatting ---
    def get_editor(self):
        return self.tab_widget.currentWidget()

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
        if not cursor.hasSelection():
            fmt = cursor.charFormat()
            is_code = (fmt.property(CODE_PROP) is True)
            if is_code:
                fmt.setBackground(Qt.transparent)
                fmt.setForeground(QColor(self.settings['editor_text']))
                fmt.setFontFamilies([self.settings['font_family']])
                fmt.setProperty(CODE_PROP, False)
            else:
                fmt.setBackground(QColor(self.settings['code_bg']))
                fmt.setForeground(QColor(self.settings['code']))
                fmt.setFontFamilies(["Consolas"])
                fmt.setProperty(CODE_PROP, True)
            cursor.setCharFormat(fmt)
            editor.setTextCursor(cursor)
            return
            
        fmt = cursor.charFormat()
        is_code = (fmt.property(CODE_PROP) is True)
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
        toggle_off = (block_fmt_check.property(QUOTE_PROP) is True)
        
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

    def insert_table(self):
        editor = self.get_editor()
        if not editor: return
        dialog = TableDialog(self)
        if dialog.exec() == QDialog.Accepted:
            rows, cols = dialog.get_data()
            cursor = editor.textCursor()
            cursor.insertTable(rows, cols)
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
        btn_add_row.clicked.connect(lambda: table.insertRows(row + 1, 1))
        layout.addWidget(btn_add_row)
        
        btn_del_row = QPushButton("Delete cursor row")
        def del_row():
            if table.rows() > 1: table.removeRows(row, 1)
        btn_del_row.clicked.connect(del_row)
        layout.addWidget(btn_del_row)
        
        btn_add_col = QPushButton("Add column to the right")
        btn_add_col.clicked.connect(lambda: table.insertColumns(col + 1, 1))
        layout.addWidget(btn_add_col)
        
        btn_del_col = QPushButton("Delete cursor column")
        def del_col():
            if table.columns() > 1: table.removeColumns(col, 1)
        btn_del_col.clicked.connect(del_col)
        layout.addWidget(btn_del_col)
        
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

        dialog = LinkDialog(selected_text, self)
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
        dialog = LinkDialog(old_text, self)
        if dialog.exec() == QDialog.Accepted:
            new_text, new_url = dialog.get_data()
            if new_text and new_url:
                fmt = QTextCharFormat()
                fmt.setAnchor(True)
                fmt.setAnchorHref(new_url)
                fmt.setForeground(QColor(self.settings['link']))
                fmt.setFontUnderline(self.settings.get("link_underline", True))
                cursor.insertText(new_text, fmt)
                editor.setTextCursor(cursor)

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
        self.act_code.setChecked(char_fmt.property(CODE_PROP) is True)
        self.act_quote.setChecked(block_fmt.property(QUOTE_PROP) is True)
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

    def open_settings(self):
        dialog = SettingsDialog(self.settings, self)
        if dialog.exec() == QDialog.Accepted:
            self.settings.update(dialog.get_settings())
            self.save_settings()
            self.apply_app_theme()
            
            for i in range(self.tab_widget.count()):
                editor = self.tab_widget.widget(i)
                editor.settings = self.settings
                editor.apply_settings()
                editor.apply_settings_to_document()
                editor.style_tables()
                editor.viewport().update()
            
            self.update_toolbar_margin()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Setting icon for the whole app (taskbar, dialogs)
    icon_path = os.path.join("icons", "notepad.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
        
    window = MainWindow()
    window.show()
    sys.exit(app.exec())