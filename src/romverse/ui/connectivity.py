from __future__ import annotations

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QWidget


class OnlineStatusBadge(QFrame):
    """Compact, real network-reachability indicator for ROMVERSE online services."""

    CHECK_URL = QUrl("https://connectivitycheck.gstatic.com/generate_204")
    CHECK_INTERVAL_MS = 30_000
    TIMEOUT_MS = 6_000

    def __init__(self, parent: QWidget | None = None) -> None:
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
        self.timeout = QTimer(self)
        self.timeout.setSingleShot(True)
        self.timeout.timeout.connect(self._timed_out)
        self.timer = QTimer(self)
        self.timer.setInterval(self.CHECK_INTERVAL_MS)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        self._set_state(False, "Checking verified internet access …")
        QTimer.singleShot(0, self.refresh)

    def refresh(self) -> None:
        if self.reply is not None:
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
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        online = (
            reply.error() is QNetworkReply.NetworkError.NoError
            and isinstance(status, int)
            and 200 <= status < 400
        )
        detail = (
            "Verified internet access • online intelligence and tool services available"
            if online
            else f"Internet check failed • {reply.errorString()}"
        )
        reply.deleteLater()
        self._set_state(online, detail)

    def _timed_out(self) -> None:
        if self.reply is not None:
            self.reply.abort()

    def _set_state(self, online: bool, detail: str) -> None:
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
