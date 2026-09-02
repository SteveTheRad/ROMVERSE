from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from romverse.members.client import (
    DeviceAuthorization,
    MembersClient,
    MembersConfiguration,
    MembersError,
    MemberSession,
    PollResult,
)
from romverse.ui.background import ManagedRunnable, start_background
from romverse.ui.process_progress import ProcessProgressBar


class _MemberSignals(QObject):
    completed = Signal(object)
    failed = Signal(str)


class _MemberWorker(ManagedRunnable):
    def __init__(self, operation) -> None:
        super().__init__()
        self.operation = operation
        self.signals = _MemberSignals()

    @Slot()
    def execute(self) -> None:
        try:
            self.signals.completed.emit(self.operation())
        except Exception as exc:  # service boundary is converted to visible, bounded UI state
            self.signals.failed.emit(str(exc))


class MembersCenter(QWidget):
    """Passwordless ROMVERSE Members sign-in with honest server-issued status."""

    settings_requested = Signal()
    knowledge_article_requested = Signal(str)

    def __init__(self, issuer: str = "", client_id: str = "") -> None:
        super().__init__()
        self._issuer = issuer
        self._client_id = client_id
        self._client: MembersClient | None = None
        self._authorization: DeviceAuthorization | None = None
        self._session: MemberSession | None = None
        self._busy = False
        self._poll_delay = 5
        self._poll_timer = QTimer(self)
        self._poll_timer.setSingleShot(True)
        self._poll_timer.timeout.connect(self._poll)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(38, 34, 38, 34)
        layout.setSpacing(14)
        eyebrow = QLabel("ROMVERSE  /  MEMBERS")
        eyebrow.setObjectName("Eyebrow")
        title = QLabel("One identity across Studio, Companion, and Galaxy")
        title.setObjectName("Title")
        detail = QLabel(
            "Sign in through your browser. ROMVERSE never asks for or stores your password, "
            "and membership access is accepted only from the configured HTTPS identity service."
        )
        detail.setObjectName("Muted")
        detail.setWordWrap(True)
        layout.addWidget(eyebrow)
        layout.addWidget(title)
        layout.addWidget(detail)

        self.card = QFrame()
        self.card.setObjectName("DashboardCard")
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(24, 22, 24, 22)
        card_layout.setSpacing(12)
        self.heading = QLabel("MEMBERS SERVICE")
        self.heading.setObjectName("DashboardHeading")
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setTextInteractionFlags(
            self.status.textInteractionFlags()
            | self.status.textInteractionFlags().TextSelectableByMouse
        )
        self.code = QLabel("")
        self.code.setObjectName("Title")
        self.code.setVisible(False)
        self.explanation = QLabel("")
        self.explanation.setObjectName("Muted")
        self.explanation.setWordWrap(True)
        card_layout.addWidget(self.heading)
        card_layout.addWidget(self.status)
        self.progress = ProcessProgressBar()
        self.progress.setAccessibleName("ROMVERSE Members operation progress")
        card_layout.addWidget(self.progress)
        card_layout.addWidget(self.code)
        card_layout.addWidget(self.explanation)
        controls = QHBoxLayout()
        self.primary = QPushButton("Sign in with ROMVERSE")
        self.primary.setObjectName("Primary")
        self.primary.clicked.connect(self._primary_action)
        self.copy_button = QPushButton("Copy code")
        self.copy_button.clicked.connect(self._copy_code)
        self.copy_button.setVisible(False)
        self.settings_button = QPushButton("Open Settings")
        self.settings_button.clicked.connect(self.settings_requested)
        self.sign_out = QPushButton("Sign out")
        self.sign_out.clicked.connect(self._sign_out)
        self.sign_out.setVisible(False)
        controls.addWidget(self.primary)
        controls.addWidget(self.copy_button)
        controls.addWidget(self.settings_button)
        controls.addStretch()
        controls.addWidget(self.sign_out)
        card_layout.addLayout(controls)
        layout.addWidget(self.card)

        membership = QFrame()
        membership.setObjectName("DashboardCard")
        membership_layout = QVBoxLayout(membership)
        membership_layout.setContentsMargins(24, 20, 24, 20)
        plan = QLabel("ROMVERSE ONE  •  A$14.99 AUD / MONTH")
        plan.setObjectName("DashboardHeading")
        membership_layout.addWidget(plan)
        trial = QLabel("7-day full-access trial  •  Month-to-month  •  Cancel anytime")
        trial.setObjectName("Good")
        membership_layout.addWidget(trial)
        included = QLabel(
            "One membership includes Studio, Companion, Nexus online intelligence, Guardian, "
            "community access, updates, and normal current or future features. No launch tiers, "
            "paid add-ons, advertising, or sponsored placements."
        )
        included.setObjectName("Muted")
        included.setWordWrap(True)
        membership_layout.addWidget(included)
        self.entitlements = QLabel(
            "Access remains unverified until the official Members service issues a signed profile."
        )
        self.entitlements.setObjectName("Muted")
        self.entitlements.setWordWrap(True)
        membership_layout.addWidget(self.entitlements)
        layout.addWidget(membership)

        privacy = QFrame()
        privacy.setObjectName("DashboardCard")
        privacy_layout = QVBoxLayout(privacy)
        privacy_layout.addWidget(QLabel("SECURITY & PRIVACY"))
        privacy_copy = QLabel(
            "• Password entry happens only at the trusted identity provider in your browser.\n"
            "• Access tokens stay in memory for this Studio session; settings.json never contains them.\n"
            "• A local checkbox can never create a subscription or bypass a server entitlement.\n"
            "• Signing out immediately discards the in-memory session."
        )
        privacy_copy.setObjectName("Muted")
        privacy_copy.setWordWrap(True)
        privacy_layout.addWidget(privacy_copy)
        self.guide_button = QPushButton("Review Members service guide")
        self.guide_button.setToolTip(
            "Open the exact local Archives guide for Members configuration and sign-in "
            "failures. This starts no browser, account, or network action."
        )
        self.guide_button.clicked.connect(
            lambda: self.knowledge_article_requested.emit(
                "members-service-unavailable-or-unconfigured"
            )
        )
        privacy_layout.addWidget(self.guide_button, 0)
        layout.addWidget(privacy)
        layout.addStretch()
        self._render()

    def configure(self, issuer: str, client_id: str) -> None:
        changed = (issuer.strip(), client_id.strip()) != (
            self._issuer.strip(),
            self._client_id.strip(),
        )
        self._issuer = issuer
        self._client_id = client_id
        if changed:
            self._sign_out()
        self._render()

    @property
    def session(self) -> MemberSession | None:
        return self._session

    def _configured(self) -> bool:
        return bool(self._issuer.strip() and self._client_id.strip())

    def _primary_action(self) -> None:
        if self._authorization is not None:
            url = (
                self._authorization.verification_uri_complete
                or self._authorization.verification_uri
            )
            QDesktopServices.openUrl(QUrl(url))
            return
        if not self._configured():
            self.settings_requested.emit()
            return
        try:
            self._client = MembersClient(MembersConfiguration(self._issuer, self._client_id))
        except MembersError as exc:
            self._show_failure(str(exc))
            return
        self._set_busy(True, "Contacting the trusted Members service …")
        self._run(self._client.begin_sign_in, self._authorization_ready)

    def _authorization_ready(self, value: object) -> None:
        if not isinstance(value, DeviceAuthorization):
            self._show_failure("The Members service returned an invalid authorization.")
            return
        self._authorization = value
        self._poll_delay = value.interval_seconds
        self._set_busy(False)
        self._render()
        QDesktopServices.openUrl(QUrl(value.verification_uri_complete or value.verification_uri))
        self._poll_timer.start(self._poll_delay * 1000)

    def _poll(self) -> None:
        if self._busy or self._client is None or self._authorization is None:
            return
        self._set_busy(True, "Waiting for secure browser authorization …")
        self._run(lambda: self._client.poll(self._authorization), self._poll_complete)

    def _poll_complete(self, value: object) -> None:
        self._set_busy(False)
        if not isinstance(value, tuple) or len(value) != 2:
            self._show_failure("The Members service returned an invalid sign-in result.")
            return
        result, session = value
        if result is PollResult.AUTHORIZED and isinstance(session, MemberSession):
            self._session = session
            self._authorization = None
            self._render()
            return
        if result is PollResult.SLOW_DOWN:
            self._poll_delay = min(30, self._poll_delay + 5)
        if result in {PollResult.PENDING, PollResult.SLOW_DOWN}:
            self._render()
            self._poll_timer.start(self._poll_delay * 1000)
            return
        self._authorization = None
        self._show_failure(
            "The sign-in request expired or was declined. Nothing was saved; start again when ready."
        )

    def _run(self, operation, completed) -> None:
        worker = _MemberWorker(operation)
        worker.signals.completed.connect(completed)
        worker.signals.failed.connect(self._show_failure)
        start_background(worker)

    def _set_busy(self, busy: bool, message: str = "") -> None:
        self._busy = busy
        self.primary.setEnabled(not busy)
        self.settings_button.setEnabled(not busy)
        if busy:
            self.progress.begin()
        else:
            self.progress.stop()
        if message:
            self.status.setText(message)

    def _copy_code(self) -> None:
        if self._authorization is not None:
            QGuiApplication.clipboard().setText(self._authorization.user_code)
            self.explanation.setText(
                "Verification code copied. Paste it only into the trusted browser page."
            )

    def _sign_out(self) -> None:
        self._poll_timer.stop()
        self._authorization = None
        self._session = None
        self._client = None
        self._busy = False
        self.progress.stop()
        self._render()

    @Slot(str)
    def _show_failure(self, message: str) -> None:
        self._set_busy(False)
        self._poll_timer.stop()
        self.status.setText("Sign-in needs attention")
        self.status.setObjectName("Danger")
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)
        self.explanation.setText(message)
        QMessageBox.warning(self, "ROMVERSE Members", message)

    def _render(self) -> None:
        self.status.setObjectName("Good" if self._session else "Muted")
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)
        if self._session is not None:
            profile = self._session.profile
            self.status.setText(f"Signed in as {profile.display_name}")
            self.code.setText(
                f"{profile.plan_name}  •  {profile.membership_status.replace('_', ' ').title()}"
            )
            self.code.setVisible(True)
            details = [profile.email] if profile.email else []
            if profile.trial_ends_at:
                details.append(f"Trial ends {profile.trial_ends_at}")
            if profile.renews_at:
                details.append(f"Renews {profile.renews_at}")
            self.explanation.setText("  •  ".join(details) or "Server-verified member profile")
            access = "Access active" if profile.access_active else "Access needs attention"
            issued = (
                ", ".join(profile.entitlements)
                if profile.entitlements
                else "No feature claims issued"
            )
            self.entitlements.setText(f"{access}  •  Server-issued entitlements: {issued}")
            self.primary.setVisible(False)
            self.copy_button.setVisible(False)
            self.settings_button.setVisible(False)
            self.sign_out.setVisible(True)
            return
        self.primary.setVisible(True)
        self.settings_button.setVisible(True)
        self.sign_out.setVisible(False)
        if self._authorization is not None:
            self.status.setText("Finish sign-in in your browser")
            self.code.setText(self._authorization.user_code)
            self.code.setVisible(True)
            self.explanation.setText(
                "ROMVERSE is waiting for the identity service. The code expires automatically, and no password is entered in Studio."
            )
            self.primary.setText("Open secure sign-in page")
            self.copy_button.setVisible(True)
        elif self._configured():
            self.status.setText("Ready for secure browser sign-in")
            self.code.setVisible(False)
            self.explanation.setText(
                f"Identity service: {self._issuer}\nNo access token is stored on disk."
            )
            self.primary.setText("Sign in with ROMVERSE")
            self.copy_button.setVisible(False)
        else:
            self.status.setText("Members service is not configured in this build")
            self.code.setVisible(False)
            self.explanation.setText(
                "Configure the official HTTPS issuer and public client ID in Settings. ROMVERSE will not invent an account, trial, or subscription while the service is unavailable."
            )
            self.primary.setText("Configure Members service")
            self.copy_button.setVisible(False)
        self.entitlements.setText(
            "Access remains unverified until the official Members service issues a signed profile."
        )
