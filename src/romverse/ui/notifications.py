from __future__ import annotations

import re
import time
from dataclasses import dataclass
from enum import StrEnum

from PySide6.QtCore import QEasingCurve, QEvent, QObject, QPropertyAnimation, QTimer, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)


class NotificationKind(StrEnum):
    INFORMATION = "information"
    SUCCESS = "success"
    ATTENTION = "attention"


@dataclass(frozen=True, slots=True)
class DesktopNotification:
    key: str
    title: str
    message: str
    kind: NotificationKind


class NotificationToast(QFrame):
    """Non-blocking in-app fallback for systems without notification-area support."""

    DISPLAY_MS = 6_500

    def __init__(self, surface: QWidget, *, reduced_motion: bool = False) -> None:
        super().__init__(surface)
        self.setObjectName("DesktopNotificationToast")
        self.setAccessibleName("ROMVERSE notification")
        self.setMinimumWidth(320)
        self.setMaximumWidth(440)
        self._reduced_motion = bool(reduced_motion)
        self._hiding = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 13, 12, 13)
        layout.setSpacing(12)
        self.indicator = QLabel("●")
        self.indicator.setObjectName("NotificationIndicator")
        self.indicator.setAccessibleName("Notification status")
        layout.addWidget(self.indicator, 0)
        copy = QVBoxLayout()
        copy.setContentsMargins(0, 0, 0, 0)
        copy.setSpacing(3)
        self.title = QLabel()
        self.title.setObjectName("NotificationTitle")
        self.title.setWordWrap(True)
        self.message = QLabel()
        self.message.setObjectName("NotificationMessage")
        self.message.setWordWrap(True)
        copy.addWidget(self.title)
        copy.addWidget(self.message)
        layout.addLayout(copy, 1)
        self.close_button = QPushButton("×")
        self.close_button.setObjectName("NotificationClose")
        self.close_button.setAccessibleName("Dismiss ROMVERSE notification")
        self.close_button.setFixedSize(28, 28)
        self.close_button.clicked.connect(self.dismiss)
        layout.addWidget(self.close_button, 0)

        self._opacity = QGraphicsOpacityEffect(self)
        self._opacity.setOpacity(0.0)
        self.setGraphicsEffect(self._opacity)
        self._fade = QPropertyAnimation(self._opacity, b"opacity", self)
        self._fade.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._fade.finished.connect(self._fade_finished)
        self._expiry = QTimer(self)
        self._expiry.setSingleShot(True)
        self._expiry.timeout.connect(self.dismiss)
        self.hide()

    def set_reduced_motion(self, enabled: bool) -> None:
        self._reduced_motion = bool(enabled)
        if self._reduced_motion:
            self._fade.stop()
            self._opacity.setOpacity(1.0 if self.isVisible() else 0.0)

    def present(self, notification: DesktopNotification) -> None:
        self._fade.stop()
        self._hiding = False
        self.title.setText(notification.title)
        self.message.setText(notification.message)
        accent = {
            NotificationKind.INFORMATION: "#63ECF8",
            NotificationKind.SUCCESS: "#72FFB2",
            NotificationKind.ATTENTION: "#FFB34D",
        }[notification.kind]
        self.setStyleSheet(
            "QFrame#DesktopNotificationToast { background: rgba(5, 10, 25, 244); "
            "border: 1px solid rgba(84, 115, 188, 180); "
            f"border-left: 3px solid {accent}; border-radius: 13px; }}"
            f"QLabel#NotificationIndicator {{ color: {accent}; font-size: 13px; }}"
            "QLabel#NotificationTitle { color: #F4F7FF; font-size: 13px; font-weight: 800; }"
            "QLabel#NotificationMessage { color: #AFC0DF; font-size: 11px; }"
            "QPushButton#NotificationClose { color: #91A3C4; background: transparent; "
            "border: 1px solid transparent; border-radius: 8px; font-size: 18px; }"
            "QPushButton#NotificationClose:hover { color: white; "
            "border-color: rgba(99, 236, 248, 130); }"
        )
        width = min(440, max(320, self.parentWidget().width() - 48))
        self.setFixedWidth(width)
        self.adjustSize()
        self.show()
        self.raise_()
        self.reposition()
        if self._reduced_motion:
            self._opacity.setOpacity(1.0)
        else:
            self._opacity.setOpacity(0.0)
            self._fade.setDuration(180)
            self._fade.setStartValue(0.0)
            self._fade.setEndValue(1.0)
            self._fade.start()
        self._expiry.start(self.DISPLAY_MS)

    def dismiss(self) -> None:
        self._expiry.stop()
        if not self.isVisible():
            return
        if self._reduced_motion:
            self.hide()
            self._opacity.setOpacity(0.0)
            return
        self._hiding = True
        self._fade.stop()
        self._fade.setDuration(260)
        self._fade.setStartValue(self._opacity.opacity())
        self._fade.setEndValue(0.0)
        self._fade.start()

    def reposition(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        margin = 22
        bottom_reserve = 66
        self.move(
            max(margin, parent.width() - self.width() - margin),
            max(margin, parent.height() - self.height() - bottom_reserve),
        )

    def _fade_finished(self) -> None:
        if self._hiding:
            self._hiding = False
            self.hide()
            self._opacity.setOpacity(0.0)


class DesktopNotificationCenter(QObject):
    """Dedupe and deliver meaningful Desktop milestones without blocking workflow."""

    delivered = Signal(object)
    DEDUPE_SECONDS = 45
    MAX_TEXT = 320
    _KEY = re.compile(r"[a-z0-9][a-z0-9._-]{0,79}")

    def __init__(
        self,
        surface: QWidget,
        icon: QIcon,
        *,
        enabled: bool = True,
        reduced_motion: bool = False,
    ) -> None:
        super().__init__(surface)
        self.surface = surface
        self.enabled = bool(enabled)
        self.toast = NotificationToast(surface, reduced_motion=reduced_motion)
        self.last_notification: DesktopNotification | None = None
        self.delivery_count = 0
        self._recent: dict[str, tuple[str, str, float]] = {}
        self._tray: QSystemTrayIcon | None = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self._tray = QSystemTrayIcon(icon, surface)
            self._tray.setToolTip("ROMVERSE Desktop")
            self._tray.activated.connect(self._activate_window)
            self._tray.setVisible(self.enabled)
        self.surface.installEventFilter(self)

    @property
    def native_available(self) -> bool:
        return self._tray is not None and QSystemTrayIcon.supportsMessages()

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = bool(enabled)
        if self._tray is not None:
            self._tray.setVisible(self.enabled)
        if not self.enabled:
            self.toast.dismiss()

    def set_reduced_motion(self, enabled: bool) -> None:
        self.toast.set_reduced_motion(enabled)

    def notify(
        self,
        key: str,
        title: str,
        message: str,
        kind: NotificationKind = NotificationKind.INFORMATION,
    ) -> bool:
        if not self.enabled or not self._KEY.fullmatch(key):
            return False
        clean_title = " ".join(str(title).replace("\x00", " ").split())[:100]
        clean_message = " ".join(str(message).replace("\x00", " ").split())[: self.MAX_TEXT]
        if not clean_title or not clean_message:
            return False
        now = time.monotonic()
        previous = self._recent.get(key)
        if (
            previous is not None
            and previous[:2] == (clean_title, clean_message)
            and now - previous[2] < self.DEDUPE_SECONDS
        ):
            return False
        self._recent[key] = (clean_title, clean_message, now)
        if len(self._recent) > 128:
            self._recent = dict(
                sorted(self._recent.items(), key=lambda item: item[1][2], reverse=True)[:64]
            )
        notification = DesktopNotification(key, clean_title, clean_message, kind)
        self.last_notification = notification
        self.delivery_count += 1
        window_active = self.surface.window().isActiveWindow()
        deliver_native = self.native_available and not window_active
        if deliver_native and self._tray is not None:
            native_kind = (
                QSystemTrayIcon.MessageIcon.Warning
                if kind is NotificationKind.ATTENTION
                else QSystemTrayIcon.MessageIcon.Information
            )
            self._tray.showMessage(clean_title, clean_message, native_kind, 6_500)
        else:
            # Keep foreground feedback inside ROMVERSE. This avoids showing the
            # same alert twice while still giving background work a native notice.
            self.toast.present(notification)
        self.delivered.emit(notification)
        return True

    def shutdown(self) -> None:
        self.toast.hide()
        if self._tray is not None:
            self._tray.hide()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self.surface and event.type() in {
            QEvent.Type.Resize,
            QEvent.Type.Show,
        }:
            QTimer.singleShot(0, self.toast.reposition)
        return super().eventFilter(watched, event)

    def _activate_window(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason not in {
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        }:
            return
        window = self.surface.window()
        window.showNormal()
        window.raise_()
        window.activateWindow()
