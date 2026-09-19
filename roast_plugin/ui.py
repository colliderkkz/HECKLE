from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QColor,
    QCursor,
    QFont,
    QFontMetrics,
    QGuiApplication,
    QIcon,
    QMouseEvent,
    QPainter,
    QPixmap,
)
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from .config import AppConfig, ConfigStore


class ApiSettingsDialog(QDialog):
    def __init__(self, config: AppConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("roast_plugin API 设置")
        self.setMinimumWidth(440)
        self.key_edit = QLineEdit(config.api_key)
        self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_edit.setPlaceholderText("填写你自己的 API Key")
        self.base_edit = QLineEdit(config.api_base)
        self.base_edit.setPlaceholderText("例如 https://api.openai.com/v1")
        self.model_edit = QLineEdit(config.model)
        form = QFormLayout()
        form.addRow("你的 API Key", self.key_edit)
        form.addRow("接口地址", self.base_edit)
        form.addRow("模型", self.model_edit)
        note = QLabel(
            "roast_plugin 不提供或代填密钥，请使用你自己的服务商 API Key。"
            "请求将直接发送到上方接口；密钥保存在本机用户配置目录。"
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #777;")
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(note)
        layout.addWidget(buttons)

    def apply(self, config: AppConfig) -> None:
        config.api_key = self.key_edit.text().strip()
        config.api_base = self.base_edit.text().strip() or "https://api.openai.com/v1"
        config.model = self.model_edit.text().strip() or "gpt-4o-mini"
        config.normalize_api_settings()


class RoastBubble(QWidget):
    pause_changed = Signal(bool)
    frequency_changed = Signal(str)
    api_settings_changed = Signal()
    roast_now_requested = Signal()

    def __init__(self, config: AppConfig, store: ConfigStore) -> None:
        flags = (
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        super().__init__(None, flags)
        self.config = config
        self.store = store
        self.latest_text = "roast_plugin 已启动，正在观察你。"
        self.drag_offset: QPoint | None = None
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.label = QLabel(self.latest_text, self)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setWordWrap(True)
        label_font = QFont("Microsoft YaHei UI")
        label_font.setPixelSize(15)
        self.label.setFont(label_font)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.addWidget(self.label)
        self._apply_transparent_style()
        self._resize_for_text(self.latest_text, keep_on_screen=False)
        self._restore_position()
        self._create_menu()
        self._create_tray_icon()

    def show_roast(self, text: str) -> None:
        self.latest_text = text
        self.label.setText(text)
        self._apply_transparent_style()
        self._resize_for_text(text)
        self.show()
        self.raise_()

    def _resize_for_text(self, text: str, keep_on_screen: bool = True) -> None:
        screen = QGuiApplication.screenAt(self.frameGeometry().center())
        screen = screen or QGuiApplication.primaryScreen()
        available = screen.availableGeometry()
        metrics = QFontMetrics(self.label.font())
        max_width = max(220, min(520, int(available.width() * 0.45)))
        label_width = max(140, min(metrics.horizontalAdvance(text) + 32, max_width))
        text_rect = metrics.boundingRect(
            QRect(0, 0, max(1, label_width - 24), 10_000),
            Qt.AlignmentFlag.AlignCenter
            | Qt.TextFlag.TextWordWrap
            | Qt.TextFlag.TextWrapAnywhere,
            text,
        )
        label_height = max(48, text_rect.height() + 24)
        self.label.setFixedSize(label_width, label_height)
        self.adjustSize()
        if keep_on_screen:
            self._keep_on_screen(available)

    def _keep_on_screen(self, available: QRect) -> None:
        margin = 8
        min_x = available.left() + margin
        min_y = available.top() + margin
        max_x = max(min_x, available.right() - self.width() - margin + 1)
        max_y = max(min_y, available.bottom() - self.height() - margin + 1)
        self.move(
            min(max(self.x(), min_x), max_x),
            min(max(self.y(), min_y), max_y),
        )

    def _apply_transparent_style(self) -> None:
        self.setStyleSheet(
            "QWidget {background:transparent;}"
            "QLabel {"
            "background:rgba(24,26,31,150);"
            "border:1px solid rgba(255,255,255,34);"
            "border-radius:14px;"
            "color:rgba(255,255,255,245);"
            "padding:4px;"
            "}"
        )

    def _create_menu(self) -> None:
        self.menu = QMenu()
        roast_now = self.menu.addAction("立即吐槽")
        roast_now.triggered.connect(lambda: self.roast_now_requested.emit())
        self.menu.addSeparator()
        self.pause_action = self.menu.addAction("")
        self.pause_action.triggered.connect(self._toggle_pause)
        frequency = self.menu.addMenu("吐槽频率")
        self.frequency_group = QActionGroup(frequency)
        self.frequency_group.setExclusive(True)
        for value, label in (("low", "低"), ("normal", "正常"), ("high", "高")):
            action = QAction(label, frequency, checkable=True)
            action.setData(value)
            action.setChecked(self.config.frequency == value)
            action.triggered.connect(lambda _checked=False, v=value: self._set_frequency(v))
            self.frequency_group.addAction(action)
            frequency.addAction(action)
        self.menu.addAction("API 设置", self._open_api_dialog)
        self.menu.addSeparator()
        self.menu.addAction("退出", QGuiApplication.quit)
        self.menu.aboutToShow.connect(self._refresh_menu)

    def _create_tray_icon(self) -> None:
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(36, 38, 45))
        painter.setPen(QColor(110, 116, 130))
        painter.drawRoundedRect(5, 5, 54, 54, 15, 15)
        painter.setPen(QColor(245, 246, 248))
        painter.setFont(QFont("Segoe UI", 25, QFont.Weight.Bold))
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "R")
        painter.end()
        self.tray_icon = QSystemTrayIcon(QIcon(pixmap), self)
        self.tray_icon.setToolTip("roast_plugin 吐槽器")
        self.tray_icon.setContextMenu(self.menu)
        self.tray_icon.activated.connect(self._tray_activated)
        self.tray_icon.show()

    def _refresh_menu(self) -> None:
        self.pause_action.setText("继续吐槽" if self.config.paused else "暂停吐槽")

    def _toggle_pause(self) -> None:
        self.config.paused = not self.config.paused
        self.store.save(self.config)
        self.pause_changed.emit(self.config.paused)
        self.show_roast("暂停了，终于嫌我烦了。" if self.config.paused else "又想听了？那我继续。")

    def _set_frequency(self, value: str) -> None:
        self.config.frequency = value
        self.store.save(self.config)
        self.frequency_changed.emit(value)

    def _tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.show_roast(self.latest_text)

    def _restore_position(self) -> None:
        primary = QGuiApplication.primaryScreen().availableGeometry()
        if self.config.bubble_x is None or self.config.bubble_y is None:
            self.move(
                primary.right() - self.width() - 30,
                primary.bottom() - self.height() - 50,
            )
        else:
            point = QPoint(self.config.bubble_x, self.config.bubble_y)
            saved_screen = QGuiApplication.screenAt(point)
            if saved_screen is not None:
                self.move(point)
                self._keep_on_screen(saved_screen.availableGeometry())
            else:
                self.move(
                    primary.right() - self.width() - 30,
                    primary.bottom() - self.height() - 50,
                )

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            global_pos = event.globalPosition().toPoint()
            self.drag_offset = global_pos - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self.drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_offset)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_offset = None
            self.config.bubble_x, self.config.bubble_y = self.x(), self.y()
            self.store.save(self.config)
            event.accept()

    def contextMenuEvent(self, event) -> None:
        self.menu.exec(QCursor.pos())

    def _open_api_dialog(self) -> None:
        dialog = ApiSettingsDialog(self.config)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            dialog.apply(self.config)
            self.store.save(self.config)
            self.api_settings_changed.emit()
            QMessageBox.information(dialog, "roast_plugin", "API 设置已保存。")
