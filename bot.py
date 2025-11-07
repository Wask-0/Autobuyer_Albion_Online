import sys
import json
import os
import time
import re
import keyboard
import psycopg2
from psycopg2.extras import RealDictCursor

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QPushButton, QLabel, QFrame, QHBoxLayout,
    QListWidget, QListWidgetItem, QCheckBox, QDialog
)
from PyQt6.QtCore import Qt, QRect, QPoint, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QPainter, QColor, QPen

# ======================
# Импорты
# ======================
try:
    import pyautogui
    import pydirectinput
    import pytesseract
    from PIL import Image
except ImportError as e:
    print(f"❌ Отсутствует зависимость: {e}. Установите: pip install PyQt6 pyautogui pydirectinput pytesseract pillow keyboard psycopg2-binary")
    sys.exit(1)

# Укажите путь к tesseract, если он не в PATH (только для Windows)
# pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# ======================
# Константы
# ======================
CONFIG_FILE = "config.json"
DB_CONFIG = {
    'host': 'localhost',
    'database': 'your_db_name',
    'user': 'your_user',
    'password': 'your_password',
    'port': 5432
}

# ======================
# PostgreSQL: чтение и запись
# ======================

def get_db_connection():
    return psycopg2.connect(**DB_CONFIG)

def read_items_from_db():
    """Возвращает список: [(id, name, namebot)]"""
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT id, name, namebot FROM items ORDER BY id")
            return [(row['id'], row['name'], row['namebot']) for row in cur.fetchall()]

def write_itemmoney(item_id, buy=None, sale=None, lastday=None, last2day=None):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM itemmoney WHERE item_id = %s", (item_id,))
            exists = cur.fetchone()
            if exists:
                fields = []
                values = []
                if buy is not None:
                    fields.append("buy = %s")
                    values.append(buy)
                if sale is not None:
                    fields.append("sale = %s")
                    values.append(sale)
                if lastday is not None:
                    fields.append("lastday = %s")
                    values.append(lastday)
                if last2day is not None:
                    fields.append("last2day = %s")
                    values.append(last2day)
                if fields:
                    values.append(item_id)
                    query = f"UPDATE itemmoney SET {', '.join(fields)} WHERE item_id = %s"
                    cur.execute(query, values)
            else:
                cur.execute(
                    "INSERT INTO itemmoney (item_id, buy, sale, lastday, last2day) VALUES (%s, %s, %s, %s, %s)",
                    (item_id, buy, sale, lastday, last2day)
                )
            conn.commit()

# ======================
# Вспомогательные функции (OCR и UI)
# ======================
def get_region_rect(region_name):
    if not os.path.exists(CONFIG_FILE):
        raise FileNotFoundError(f"Файл конфигурации {CONFIG_FILE} не найден.")
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        config = json.load(f)
    if region_name not in config:
        raise ValueError(f"Область '{region_name}' не найдена.")
    r = config[region_name]
    return (r['x'], r['y'], r['width'], r['height'])

def get_center_of_region(region_name):
    x, y, w, h = get_region_rect(region_name)
    return x + w // 2, y + h // 2

def click_and_type(region_name, text):
    x, y = get_center_of_region(region_name)
    pyautogui.click(x, y)
    time.sleep(0.02)
    pyautogui.hotkey('ctrl', 'a')
    time.sleep(0.02)
    pyautogui.press('backspace')
    time.sleep(0.02)
    for char in text:
        pydirectinput.press(char)
    time.sleep(0.02)

def click_center(region_name):
    x, y = get_center_of_region(region_name)
    pyautogui.click(x, y)
    time.sleep(0.05)

def move_to_bottom_right_of(region_name):
    x, y, w, h = get_region_rect(region_name)
    pyautogui.moveTo(x + w - 1, y + h - 1)
    time.sleep(0.05)

def ocr_d_or_d1(region_name):
    x, y, w, h = get_region_rect(region_name)
    screenshot = pyautogui.screenshot(region=(x, y, w, h))
    img = screenshot.convert('L')
    img = img.resize((img.width * 2, img.height * 2), Image.Resampling.LANCZOS)
    img = img.point(lambda p: p > 128 and 255)
    text = pytesseract.image_to_string(
        img,
        config='--psm 7 -c tessedit_char_whitelist=0123456789'
    )
    cleaned = re.sub(r'[^0-9]', '', text.strip())
    if not cleaned:
        raise ValueError(f"Не удалось распознать число в области {region_name}: '{text}'")
    return int(cleaned)

def ocr_e(region_name):
    x, y, w, h = get_region_rect(region_name)
    screenshot = pyautogui.screenshot(region=(x, y, w, h))
    img = screenshot.convert('L')
    img = Image.eval(img, lambda x: 255 - x)
    img = img.resize((img.width * 4, img.height * 4), Image.Resampling.LANCZOS)
    img = img.point(lambda p: p > 180 and 255)
    text = pytesseract.image_to_string(
        img,
        config='--psm 7 -c tessedit_char_whitelist=0123456789'
    )
    numbers = re.findall(r'\d+', text)
    if not numbers:
        raise ValueError(f"Не удалось распознать число в области {region_name}: '{text}'")
    return int(numbers[0])

def ocr_c(region_name):
    x, y, w, h = get_region_rect(region_name)
    screenshot = pyautogui.screenshot(region=(x, y, w, h))
    img = screenshot.convert('L')
    img = Image.eval(img, lambda x: 255 - x)          # инверсия
    img = img.resize((img.width * 4, img.height * 4), Image.Resampling.LANCZOS)
    img = img.point(lambda p: p > 180 and 255)        # бинаризация
    text = pytesseract.image_to_string(
        img,
        config='--psm 7 -c tessedit_char_whitelist=0123456789'
    )
    numbers = re.findall(r'\d+', text)
    if not numbers:
        raise ValueError(f"Не удалось распознать число в области {region_name}: '{text}'")
    return int(numbers[0])

# ======================
# Status Overlay
# ======================
class StatusOverlay(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(300, 80)

        self.label = QLabel("Работает...", self)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        self.label.setStyleSheet("color: white; background-color: rgba(0,0,0,160); border-radius: 10px; padding: 10px;")
        self.label.setGeometry(0, 0, 300, 80)

        screen = QApplication.primaryScreen().geometry()
        self.move(screen.right() - 320, 40)
        self.hide()

    def show_running(self):
        self.label.setText("Работает...")
        self.show()

    def show_paused(self):
        self.label.setText("На паузе")
        self.show()

    def hide_overlay(self):
        self.hide()

# ======================
# Анализ в потоке
# ======================


# ======================
# Стиль чекбокса
# ======================
CHECKBOX_STYLE = """
    QCheckBox::indicator {
        width: 20px;
        height: 20px;
        border: 2px solid #555;
        background-color: black;  
    }
    QCheckBox::indicator:checked {
        background-color: white;  
    }
    QCheckBox::indicator:hover {
        border: 2px solid #000;
    }
"""

# ======================
# Окно выбора предметов
# ======================
class SelectionWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Выберите предметы для обработки")
        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Dialog)
        self.setModal(True)
        self.resize(500, 600)

        main_layout = QVBoxLayout()

        header_layout = QHBoxLayout()
        header_label = QLabel("Предметы (белый = включён, чёрный = исключён)")
        header_label.setStyleSheet("color: white; font-weight: bold;")
        self.master_checkbox = QCheckBox()
        self.master_checkbox.setChecked(True)
        self.master_checkbox.setStyleSheet(CHECKBOX_STYLE)
        self.master_checkbox.stateChanged.connect(self.toggle_all)

        header_layout.addWidget(header_label)
        header_layout.addStretch()
        header_layout.addWidget(self.master_checkbox)
        main_layout.addLayout(header_layout)
        main_layout.addSpacing(10)

        self.list_widget = QListWidget()
        main_layout.addWidget(self.list_widget)

        button_layout = QHBoxLayout()
        self.back_btn = QPushButton("← Назад")
        self.ok_btn = QPushButton("OK")
        self.back_btn.setStyleSheet("""
            QPushButton {
                background-color: #5a3a3a;
                color: white;
                border-radius: 8px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #6a4a4a;
            }
        """)
        self.ok_btn.setStyleSheet("""
            QPushButton {
                background-color: #3a5a3a;
                color: white;
                border-radius: 8px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #4a6a4a;
            }
        """)
        self.back_btn.clicked.connect(self.reject)
        self.ok_btn.clicked.connect(self.accept)
        button_layout.addWidget(self.back_btn)
        button_layout.addStretch()
        button_layout.addWidget(self.ok_btn)
        main_layout.addLayout(button_layout)

        self.setLayout(main_layout)
        self.load_items()

    def load_items(self):
        try:
            items = read_items_from_db()
            for item_id, name, namebot in items:
                item_widget = QWidget()
                item_layout = QHBoxLayout(item_widget)
                label = QLabel(name)
                label.setStyleSheet("color: white; font-size: 12px;")
                checkbox = QCheckBox()
                checkbox.setChecked(True)
                checkbox.setProperty("item_id", item_id)
                checkbox.setProperty("namebot", namebot)
                checkbox.setStyleSheet(CHECKBOX_STYLE)

                item_layout.addWidget(label)
                item_layout.addStretch()
                item_layout.addWidget(checkbox)
                item_layout.setContentsMargins(10, 8, 10, 8)

                list_item = QListWidgetItem()
                list_item.setSizeHint(item_widget.sizeHint())
                self.list_widget.addItem(list_item)
                self.list_widget.setItemWidget(list_item, item_widget)
        except Exception as e:
            print(f"❌ Ошибка загрузки списка: {e}")

    def toggle_all(self, state):
        checked = state == Qt.CheckState.Checked.value
        for i in range(self.list_widget.count()):
            widget = self.list_widget.itemWidget(self.list_widget.item(i))
            if widget:
                cb = widget.findChild(QCheckBox)
                if cb:
                    cb.setChecked(checked)

    def get_selected_items(self):
        selected = []
        for i in range(self.list_widget.count()):
            widget = self.list_widget.itemWidget(self.list_widget.item(i))
            if widget:
                checkbox = widget.findChild(QCheckBox)
                if checkbox and checkbox.isChecked():
                    item_id = checkbox.property("item_id")
                    namebot = checkbox.property("namebot")
                    selected.append((item_id, namebot))
        return selected

# ======================
# TooltipWindow, ResizableOverlay, SetupWindow — без изменений
# (оставлены как в оригинале, так как не зависят от источника данных)
# ======================

class TooltipWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(480, 320)

        self.container = QFrame(self)
        self.container.setGeometry(0, 0, 480, 320)
        self.container.setStyleSheet("""
            QFrame {
                background-color: #2a2a3f;
                border-radius: 12px;
                border: 1px solid #5a5a7a;
            }
        """)

        self.close_btn = QPushButton("×")
        self.close_btn.setFixedSize(36, 36)
        self.close_btn.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        self.close_btn.setStyleSheet("""
            QPushButton {
                background-color: #5a3a3a;
                color: white;
                border-radius: 18px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #6a4a4a;
            }
        """)
        self.close_btn.setParent(self.container)
        self.close_btn.move(480 - 46, 10)
        self.close_btn.raise_()
        self.close_btn.clicked.connect(self.close)

        self.content_frame = QFrame(self.container)
        self.content_frame.setGeometry(30, 25, 420, 270)
        layout = QVBoxLayout(self.content_frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        title = QLabel("Памятка по полям разметки")
        title.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        title.setStyleSheet("color: #ffffff;")
        layout.addWidget(title)

        explanations = [
            "<b>Центр A</b> — поле поисковой строки",
            "<b>B</b> — от центра картинки до центра кнопки заказ на продажу",
            "<b>C</b> — правый нижний угол: количество проданных 2 дня назад",
            "<b>D</b> — полоска с ценой закупа",
            "<b>D1</b> — полоска с ценой продажи",
            "<b>E</b> — правый нижний угол: количество проданных день назад",
            "<b>Центр F</b> — ползунок количества товара",
            "<b>Центр G</b> — поле с ценой товара",
            "<b>Центр H</b> — кнопка «Заказ на покупку»"
        ]

        explanation_label = QLabel("<br>".join(explanations))
        explanation_label.setFont(QFont("Segoe UI", 11))
        explanation_label.setStyleSheet("color: #d0d0ff;")
        explanation_label.setWordWrap(True)
        layout.addWidget(explanation_label)

        screen = QApplication.primaryScreen().geometry()
        self.move(screen.center().x() - self.width() // 2, screen.center().y() - self.height() // 2)


class ResizableOverlay(QWidget):
    def __init__(self, name, geometry=None, parent=None):
        super().__init__(parent)
        self.name = name
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.edge_margin = 6
        self.min_size = (50, 30)

        if geometry:
            self.setGeometry(geometry)
        else:
            screen = QApplication.primaryScreen().availableGeometry()
            x = screen.center().x() - 100
            y = screen.center().y() - 50
            self.setGeometry(QRect(x, y, 200, 100))

        self.label = QLabel(self.name, self)
        self.label.setStyleSheet("color: white; font-weight: bold; background-color: rgba(255,0,0,120);")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setGeometry(0, 0, 30, 20)

        self.dragging = False
        self.resizing = False
        self.resize_direction = None
        self.mouse_start_pos = QPoint()
        self.rect_start = QRect()

    def get_cursor_for_position(self, pos):
        x, y = pos.x(), pos.y()
        w, h = self.width(), self.height()
        m = self.edge_margin
        on_left = x < m
        on_right = x > w - m
        on_top = y < m
        on_bottom = y > h - m

        if on_top and on_left: return Qt.CursorShape.SizeFDiagCursor, 'topleft'
        elif on_top and on_right: return Qt.CursorShape.SizeBDiagCursor, 'topright'
        elif on_bottom and on_left: return Qt.CursorShape.SizeBDiagCursor, 'bottomleft'
        elif on_bottom and on_right: return Qt.CursorShape.SizeFDiagCursor, 'bottomright'
        elif on_left: return Qt.CursorShape.SizeHorCursor, 'left'
        elif on_right: return Qt.CursorShape.SizeHorCursor, 'right'
        elif on_top: return Qt.CursorShape.SizeVerCursor, 'top'
        elif on_bottom: return Qt.CursorShape.SizeVerCursor, 'bottom'
        else: return Qt.CursorShape.SizeAllCursor, 'move'

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            cursor_shape, direction = self.get_cursor_for_position(event.pos())
            if direction == 'move':
                self.dragging = True
            else:
                self.resizing = True
                self.resize_direction = direction
            self.mouse_start_pos = event.globalPosition().toPoint()
            self.rect_start = self.geometry()
        event.accept()

    def mouseMoveEvent(self, event):
        if self.dragging:
            delta = event.globalPosition().toPoint() - self.mouse_start_pos
            self.move(self.rect_start.topLeft() + delta)
        elif self.resizing:
            global_pos = event.globalPosition().toPoint()
            delta = global_pos - self.mouse_start_pos
            new_rect = QRect(self.rect_start)
            min_w, min_h = self.min_size

            if 'left' in self.resize_direction: new_rect.setLeft(new_rect.left() + delta.x())
            if 'right' in self.resize_direction: new_rect.setRight(new_rect.right() + delta.x())
            if 'top' in self.resize_direction: new_rect.setTop(new_rect.top() + delta.y())
            if 'bottom' in self.resize_direction: new_rect.setBottom(new_rect.bottom() + delta.y())

            if new_rect.width() < min_w:
                if 'left' in self.resize_direction:
                    new_rect.setLeft(new_rect.right() - min_w)
                else:
                    new_rect.setRight(new_rect.left() + min_w)
            if new_rect.height() < min_h:
                if 'top' in self.resize_direction:
                    new_rect.setTop(new_rect.bottom() - min_h)
                else:
                    new_rect.setBottom(new_rect.top() + min_h)

            self.setGeometry(new_rect)
        else:
            cursor_shape, _ = self.get_cursor_for_position(event.pos())
            self.setCursor(cursor_shape)
        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragging = False
            self.resizing = False
            self.resize_direction = None
        event.accept()

    def paintEvent(self, event):
        painter = QPainter(self)
        pen = QPen(QColor(255, 0, 0), 2)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(0, 0, self.width() - 1, self.height() - 1)

    def get_config(self):
        geo = self.geometry()
        return {"x": geo.x(), "y": geo.y(), "width": geo.width(), "height": geo.height()}


class SetupWindow:
    def __init__(self, main_window):
        self.main_window = main_window
        self.overlays = []
        self.load_config()
        self.show_overlays()
        self.create_buttons()

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
        else:
            self.config = {}

    def show_overlays(self):
        names = ['A', 'B', 'C', 'D', 'D1', 'E', 'F', 'G', 'H', 'J']
        for name in names:
            geo_dict = self.config.get(name)
            geo = QRect(
                geo_dict['x'], geo_dict['y'],
                geo_dict['width'], geo_dict['height']
            ) if geo_dict else None
            overlay = ResizableOverlay(name, geo)
            overlay.show()
            self.overlays.append(overlay)

    def create_buttons(self):
        screen = QApplication.primaryScreen().availableGeometry()
        self.button_container = QWidget()
        self.button_container.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool |
            Qt.WindowType.FramelessWindowHint
        )
        self.button_container.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        h_layout = QHBoxLayout()
        h_layout.setSpacing(20)
        h_layout.setContentsMargins(0, 0, 0, 0)

        self.back_btn = QPushButton("← Назад")
        self.back_btn.setFixedSize(130, 40)
        self.back_btn.setFont(QFont("Segoe UI", 11))
        self.back_btn.clicked.connect(self.on_back)
        self.back_btn.setStyleSheet("""
            QPushButton {
                background-color: #5a3a3a;
                color: white;
                border-radius: 8px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #6a4a4a;
            }
        """)

        self.save_btn = QPushButton("Сохранить разметку")
        self.save_btn.setFixedSize(180, 40)
        self.save_btn.setFont(QFont("Segoe UI", 11))
        self.save_btn.clicked.connect(self.save_config)
        self.save_btn.setStyleSheet("""
            QPushButton {
                background-color: #3a5a3a;
                color: white;
                border-radius: 8px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #4a6a4a;
            }
        """)

        h_layout.addWidget(self.back_btn)
        h_layout.addWidget(self.save_btn)
        h_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout = QVBoxLayout()
        layout.addLayout(h_layout)
        layout.setContentsMargins(0, 0, 0, 0)
        self.button_container.setLayout(layout)

        container_width = 130 + 180 + 20
        container_height = 50
        x = screen.center().x() - container_width // 2
        y = screen.bottom() - container_height - 20
        self.button_container.setGeometry(x, y, container_width, container_height)
        self.button_container.show()

    def save_config(self):
        config = {}
        for overlay in self.overlays:
            config[overlay.name] = overlay.get_config()
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=4)
        print("✅ Конфигурация сохранена в", CONFIG_FILE)
        self.cleanup()

    def on_back(self):
        print("↩️ Возврат без сохранения")
        self.cleanup()

    def cleanup(self):
        for overlay in self.overlays:
            overlay.close()
        self.button_container.close()
        self.main_window.show()

# ======================
# Окно отчёта по прибыльным предметам
# ======================
class ProfitReportWindow(QDialog):
    def __init__(self, profitable_items, parent=None):
        super().__init__(parent)
        self.setWindowTitle("💰 Высокоприбыльные предметы (>200%)")
        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Dialog)
        self.setModal(True)
        self.resize(500, 400)

        layout = QVBoxLayout()

        if not profitable_items:
            label = QLabel("📉 Нет предметов с прибылью >200%.")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setStyleSheet("font-size: 14px; color: #ffcccc;")
            layout.addWidget(label)
        else:
            title = QLabel("💰 ВЫСОКОПРИБЫЛЬНЫЕ ПРЕДМЕТЫ (>200% прибыли)")
            title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            title.setStyleSheet("font-size: 16px; font-weight: bold; color: #aaffaa; margin-bottom: 10px;")
            layout.addWidget(title)

            self.list_widget = QListWidget()
            self.list_widget.setStyleSheet("""
                QListWidget {
                    background-color: #2a2a3a;
                    color: #e0e0ff;
                    border: 1px solid #555;
                    border-radius: 6px;
                }
                QListWidget::item {
                    padding: 8px;
                    border-bottom: 1px solid #3a3a4a;
                }
            """)
            for name, buy, sale, ratio in profitable_items:
                item_text = f"{name}\n  Закуп: {buy} | Продажа: {sale} | x{ratio:.2f}"
                item = QListWidgetItem(item_text)
                item.setFont(QFont("Segoe UI", 10))
                self.list_widget.addItem(item)

            layout.addWidget(self.list_widget)

        # Кнопка закрытия
        close_btn = QPushButton("Закрыть")
        close_btn.setFixedSize(120, 36)
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: #3a5a3a;
                color: white;
                border-radius: 8px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #4a6a4a;
            }
        """)
        close_btn.clicked.connect(self.accept)
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(close_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        self.setLayout(layout)

# ======================
# MainWindow
# ======================
class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Торговый Ассистент")
        self.setFixedSize(480, 320)
        self.setup_ui()
        self.apply_styles()
        self.status_overlay = StatusOverlay()
        self.is_running = False
        self.current_item_index = 0
        self.selected_items = []
        self._pause = False
        self._stop = False

        # Регистрируем хоткеи ОДИН РАЗ при запуске
        keyboard.add_hotkey('ctrl + x', self.toggle_pause_safe)
        keyboard.add_hotkey('ctrl + z', self.request_stop_safe)

        # Таймер для пошагового выполнения
        self.timer = QTimer()
        self.timer.timeout.connect(self.process_next_item)

    def setup_ui(self):
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(20)

        self.btn_setup = QPushButton("Настройка разметки экрана")
        self.btn_setup.setFixedSize(400, 55)
        self.btn_setup.setFont(QFont("Segoe UI", 12))
        self.btn_setup.clicked.connect(self.open_setup)

        self.btn_analyze = QPushButton("Анализ и выставление ордеров на покупку")
        self.btn_analyze.setFixedSize(400, 55)
        self.btn_analyze.setFont(QFont("Segoe UI", 12))
        self.btn_analyze.clicked.connect(self.on_analyze_click)

        self.btn_repost = QPushButton("Перевыставление ордеров")
        self.btn_repost.setFixedSize(400, 55)
        self.btn_repost.setFont(QFont("Segoe UI", 12))

        layout.addWidget(self.btn_setup, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.btn_analyze, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.btn_repost, alignment=Qt.AlignmentFlag.AlignCenter)

        self.setLayout(layout)

        self.tooltip_btn = QPushButton("❗")
        self.tooltip_btn.setFixedSize(36, 36)
        self.tooltip_btn.setFont(QFont("Segoe UI", 14))
        self.tooltip_btn.setStyleSheet("""
            QPushButton {
                background-color: #3a3a5a;
                color: white;
                border-radius: 18px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #4a4a7a;
            }
        """)
        self.tooltip_btn.clicked.connect(self.show_tooltip_window)
        self.tooltip_btn.setParent(self)
        self.tooltip_btn.move(480 - 40, 10)

    def apply_styles(self):
        self.setStyleSheet("""
            QWidget {
                background-color: #1e1e2e;
                color: #e0e0ff;
            }
            QPushButton {
                background-color: #3a3a5a;
                color: #ffffff;
                border: none;
                border-radius: 12px;
                padding: 10px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #4a4a7a;
            }
            QPushButton:pressed {
                background-color: #5a5a8a;
            }
        """)

    def open_setup(self):
        self.hide()
        self.setup_mode = SetupWindow(self)

    def show_tooltip_window(self):
        self.tooltip = TooltipWindow()
        self.tooltip.show()

    def on_analyze_click(self):
        if self.is_running:
            return

        selection_window = SelectionWindow(self)
        if selection_window.exec() == QDialog.DialogCode.Accepted:
            selected_items = selection_window.get_selected_items()
            if not selected_items:
                print("⚠️ Нет выбранных предметов.")
                return

            self.hide()
            self.is_running = True
            self._pause = False
            self._stop = False
            self.selected_items = selected_items
            self.current_item_index = 0
            self.results = []
            self.status_overlay.show_running()
            print("⏳ Начало анализа через 3 секунды...")
            QTimer.singleShot(3000, self.start_timer)

    def start_timer(self):
        if self.is_running:
            self.timer.start(100)  # каждые 100 мс — проверка состояния и шаг

    def toggle_pause_safe(self):
        if self.is_running:
            self.toggle_pause()

    def request_stop_safe(self):
        if self.is_running:
            self.request_stop()

    def toggle_pause(self):
        self._pause = not self._pause
        if self._pause:
            self.status_overlay.show_paused()
            print("⏸ Пауза")
        else:
            self.status_overlay.show_running()
            print("▶ Возобновлено")

    def request_stop(self):
        print("⏹ Запрошена остановка...")
        self._stop = True

    def process_next_item(self):
        if self._stop:
            self.finish_analysis()
            return

        if self._pause:
            return  # просто ждём

        if self.current_item_index >= len(self.selected_items):
            self.finish_analysis()
            return

        item_id, namebot = self.selected_items[self.current_item_index]
        try:
            print(f"📋 Обработка: ID={item_id}, '{namebot}'")

            # === Ввод поиска ===
            click_and_type('A', namebot)

            # === Поиск изображения pic/{name}.png ===
            # Получаем имя из БД (нужно для имени файла)
            with get_db_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("SELECT name FROM items WHERE id = %s", (item_id,))
                    row = cur.fetchone()
                    name = row['name'] if row else str(item_id)

            image_path = os.path.join("pic", f"{name}.png")
            if not os.path.exists(image_path):
                print(f"⚠️ Файл изображения не найден: {image_path}")
                click_center('J')
                time.sleep(0.25)
                self.current_item_index += 1
                return

            # 🔍 Без confidence! Без OpenCV!
            location = pyautogui.locateOnScreen(image_path, confidence=0.85)
            if location is None:
                print(f"❌ Изображение не найдено на экране: {name}")
                click_center('J')
                time.sleep(0.25)
                self.current_item_index += 1
                return

            center_x = location.left + location.width // 2
            center_y = location.top + location.height // 2

            # Получаем смещение — ширина области B из конфига
            _, _, w_B, _ = get_region_rect('B')
            target_x = center_x + w_B
            target_y = center_y

            print(f"🎯 Найдено изображение: ({center_x}, {center_y}) → клик в ({target_x}, {target_y})")
            pyautogui.click(target_x, target_y)
            time.sleep(0.25)

            # === Продажа (D → sale) ===
            sale_raw = 0
            try:
                sale_raw = ocr_d_or_d1('D')
                print(f"📈 Продажа (D): {sale_raw}")
            except Exception as e:
                print(f"⚠️ Ошибка D: {e} → будет записано 0")
                sale_raw = 0

            # === Закупка (D1 → buy) ===
            buy_raw = 0
            try:
                buy_raw = ocr_d_or_d1('D1')
                print(f"📈 Закуп (D1): {buy_raw}")
            except Exception as e:
                print(f"⚠️ Ошибка D1: {e} → будет записано 0")
                buy_raw = 0

            # === Продано (E → lastday) ===
            lastday_raw = 0
            try:
                move_to_bottom_right_of('E')
                time.sleep(0.5)
                lastday_raw = ocr_e('E')
                print(f"📦 Продано (E): {lastday_raw}")
            except Exception as e:
                print(f"⚠️ Ошибка E: {e} → будет записано 0")
                lastday_raw = 0

            # === Продано вчера (C → last2day) ===
            last2day_raw = 0
            try:
                move_to_bottom_right_of('C')
                time.sleep(0.5)
                last2day_raw = ocr_c('C')
                print(f"📦 Продано вчера (C): {last2day_raw}")
            except Exception as e:
                print(f"⚠️ Ошибка C: {e} → будет записано 0")
                last2day_raw = 0

            # === Расчёт прибыли и условие для выставления ордера ===
            total_sold = lastday_raw + last2day_raw
            buy = buy_raw
            sale = sale_raw

            # Проверяем, что buy > 0, иначе деление на ноль 
            should_place_order = False
            if buy > 0 and total_sold > 10:
                ratio = sale / buy if sale > 0 else 0
                if 1.4 <= ratio <= 3.0:  # 40% <= прибыль <= 200%
                    should_place_order = True

            if should_place_order:
                print(f"🛒 Условие выполнено: прибыль x{ratio:.2f}, продано за 2 дня: {total_sold}")

                # 1) Определяем количество для заказа
                if total_sold <= 50:
                    qty = 1
                elif total_sold <= 150:
                    qty = 2
                elif total_sold <= 500:
                    qty = 5
                elif total_sold <= 3000:
                    qty = 7
                elif total_sold <= 10000:
                    qty = 10
                else:
                    qty = 25

                # Клик в центр F и ввод количества
                click_and_type('F', str(qty))
                time.sleep(0.1)

                # 2) Клик в центр G и ввод цены (D1 + 1)
                price = sale_raw + 1
                click_and_type('G', str(price))
                time.sleep(0.1)

                # 3) Нажатие на кнопку "Заказ на покупку" (H)
                click_center('H')
                time.sleep(0.3)

                print(f"✅ Выставлен ордер: кол-во={qty}, цена={price}")
            else:
                print("⏭️ Условие не выполнено — пропуск выставления ордера")

            # === Запись в БД ===
            write_itemmoney(
                item_id=item_id,
                buy=int(buy_raw * 1.025),
                sale=int(sale_raw * 0.935),
                lastday=lastday_raw,
                last2day=last2day_raw
            )
            print(f"✅ Записано в БД: buy={buy_raw}, sale={sale_raw}, lastday={lastday_raw}")

            self.results.append((item_id, buy_raw, sale_raw))

            click_center('J')
            time.sleep(0.25)

        except Exception as e:
            print(f"❌ Ошибка при обработке {item_id}: {e}")

        self.current_item_index += 1

    def finish_analysis(self):
        self.timer.stop()
        keyboard.unhook_all_hotkeys()
        self.status_overlay.hide_overlay()
        self.is_running = False
        self.show()
        print("✅ Анализ завершён.")
        self.show_profit_report(self.results)

    def show_profit_report(self, results):
        if not results:
            profitable_items = []
        else:
            profitable_items = []
            with get_db_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    for item_id, buy, sale in results:
                        if buy and buy > 0:
                            ratio = sale / buy if sale else 0
                            if ratio > 3.0:
                                cur.execute("SELECT name FROM items WHERE id = %s", (item_id,))
                                row = cur.fetchone()
                                name = row['name'] if row else f"ID={item_id}"
                                profitable_items.append((name, buy, sale, ratio))

        report_window = ProfitReportWindow(profitable_items, self)
        report_window.exec()

        if profitable_items:
            print("\n" + "="*60)
            print("💰 ВЫСОКОПРИБЫЛЬНЫЕ ПРЕДМЕТЫ (>200% прибыли):")
            print("="*60)
            for name, buy, sale, ratio in profitable_items:
                print(f"  • {name}")
                print(f"    Закуп: {buy}, Продажа: {sale}, Множитель: {ratio:.2f}x")
            print("="*60)
        else:
            print("\n📉 Нет предметов с прибылью >200%.")


# ======================
# Запуск
# ======================
if __name__ == "__main__":
    # ⚠️ Настройте подключение к вашей БД здесь или через .env
    DB_CONFIG.update({
        'host': 'localhost',
        'database': 'postgres',
        'user': 'postgres',
        'password': '1111',
        'port': 5432
    })

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())