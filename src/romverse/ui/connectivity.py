from __future__ import annotations

from contextlib import suppress

from PySide6.QtCore import QTimer, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QWidget


class OnlineStatusBadge(QFrame):
    """Compact, real network-reachability indicator for ROMVERSE online services."""

    status_changed = Signal(bool, str)

    CHECK_URL = QUrl("https://connectivitycheck.gstatic.com/generate_204")
    CHECK_INTERVAL_MS = 30_000
    TIMEOUT_MS = 6_000

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        auto_start: bool = True,
        monitoring_enabled: bool = True,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("OnlineStatusBadge")
        self.setFixedHeight(30)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(7)
        self.dot = QLabel("●")
        self.label = QLabel("CHECKING")
        layout.addWidget(self.dot)
        layout.addWidget(self.label)
        self.manager = QNetworkAccessManager(self)
        self.reply: QNetworkReply | None = None
        self._online: bool | None = None
        self._monitoring_enabled = bool(monitoring_enabled)
        self.timeout = QTimer(self)
        self.timeout.setSingleShot(True)
        self.timeout.timeout.connect(self._timed_out)
        self.timer = QTimer(self)
        self.timer.setInterval(self.CHECK_INTERVAL_MS)
        self.timer.timeout.connect(self.refresh)
        if self._monitoring_enabled:
            self._set_checking()
        else:
            self._set_disabled()
        if auto_start and self._monitoring_enabled:
            self.timer.start()
            QTimer.singleShot(0, self.refresh)

    @property
    def online(self) -> bool | None:
        """Return True/False after a check, or None while no result exists yet."""

        return self._online

    @property
    def monitoring_enabled(self) -> bool:
        """Report whether Settings permits periodic internet reachability checks."""

        return self._monitoring_enabled

    def set_monitoring_enabled(self, enabled: bool) -> None:
        """Apply the online-sources privacy gate immediately and reversibly."""

        selected = bool(enabled)
        if selected == self._monitoring_enabled:
            return
        self._monitoring_enabled = selected
        self._online = None
        if not selected:
            self.timer.stop()
            self.timeout.stop()
            reply = self.reply
            self.reply = None
            if reply is not None:
                with suppress(RuntimeError, TypeError):
                    reply.finished.disconnect(self._finished)
                reply.abort()
                reply.deleteLater()
            self._set_disabled()
            return
        self._set_checking()
        self.timer.start()
        QTimer.singleShot(0, self.refresh)

    def refresh(self) -> None:
        if not self._monitoring_enabled or self.reply is not None:
            return
        request = QNetworkRequest(self.CHECK_URL)
        request.setRawHeader(b"User-Agent", b"ROMVERSE-Connectivity/1")
        self.reply = self.manager.get(request)
        self.reply.finished.connect(self._finished)
        self.timeout.start(self.TIMEOUT_MS)

    def _finished(self) -> None:
        reply = self.reply
        self.reply = None
        self.timeout.stop()
        if reply is None:
            return
        if not self._monitoring_enabled:
            reply.deleteLater()
            self._set_disabled()
            return
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        online = (
            reply.error() == QNetworkReply.NetworkError.NoError
            and isinstance(status, int)
            and 200 <= status < 400
        )
        detail = (
            "Internet route verified • each ROMVERSE online source is still checked independently"
            if online
            else f"Internet check failed • {reply.errorString()}"
        )
        reply.deleteLater()
        self._set_state(online, detail)

    def _timed_out(self) -> None:
        if self.reply is not None:
            self.reply.abort()

    def _set_checking(self) -> None:
        color = "#FFC857"
        detail = "Checking internet reachability • no online service is assumed available yet"
        self.dot.setStyleSheet(f"color:{color}; font-size:15px; font-weight:900;")
        self.label.setText("CHECKING")
        self.label.setStyleSheet(
            f"color:{color}; font-size:11px; font-weight:800; letter-spacing:1px;"
        )
        self.setToolTip(detail)
        self.dot.setToolTip(detail)
        self.label.setToolTip(detail)
        self.setAccessibleName("ROMVERSE checking internet access")

    def _set_disabled(self) -> None:
        color = "#8C9ABC"
        detail = (
            "Online diagnostics and sources are disabled in Settings • no internet "
            "reachability request is running"
        )
        self.dot.setStyleSheet(f"color:{color}; font-size:15px; font-weight:900;")
        self.label.setText("LOCAL")
        self.label.setStyleSheet(
            f"color:{color}; font-size:11px; font-weight:800; letter-spacing:1px;"
        )
        self.setToolTip(detail)
        self.dot.setToolTip(detail)
        self.label.setToolTip(detail)
        self.setAccessibleName("ROMVERSE online access disabled; local mode")

    def _set_state(self, online: bool, detail: str) -> None:
        changed = self._online is None or self._online != bool(online)
        self._online = bool(online)
        color = "#35F0A2" if online else "#FF526D"
        self.dot.setStyleSheet(f"color:{color}; font-size:15px; font-weight:900;")
        self.label.setText("ONLINE" if online else "OFFLINE")
        self.label.setStyleSheet(
            f"color:{color}; font-size:11px; font-weight:800; letter-spacing:1px;"
        )
        self.setToolTip(detail)
        self.dot.setToolTip(detail)
        self.label.setToolTip(detail)
        self.setAccessibleName("ROMVERSE online" if online else "ROMVERSE offline")
        if changed:
            self.status_changed.emit(bool(online), detail)
