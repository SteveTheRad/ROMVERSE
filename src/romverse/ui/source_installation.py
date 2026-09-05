"""Execute a supported source-declared installation with one exact-plan confirmation."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QDialog, QLabel, QMessageBox, QPushButton, QTableWidgetItem

from romverse.core.settings import ExperienceMode
from romverse.guardian.source_installation import SourceInstallationPlan
from romverse.rom.candidate_installation import CandidateInstallationRecipe
from romverse.ui.local_flash import LocalFlashDialog, LocalTransitionWorker
from romverse.ui.source_operation_session import (
    SourceOperationPhase,
    SourceOperationSession,
    SourceOperationSnapshot,
    SourceTransitionReview,
)


class SourceInstallationDialog(LocalFlashDialog):
    """Reuse exact-phone transitions/boot monitoring without pretending this is a subset."""

    experience_mode_requested = Signal(object)

    def __init__(
        self,
        service,
        devices,
        parent=None,
        *,
        recipe,
        session: SourceOperationSession | None = None,
        experience_mode: ExperienceMode = ExperienceMode.GUIDED,
        **kwargs,
    ):
        self.recipe = recipe
        self.preparation = recipe  # Exact source attribution for the recovery handoff.
        self._owns_session = session is None
        operation_session = session or SourceOperationSession(
            service,
            devices,
            recipe=recipe,
            discover=kwargs.get("discover"),
            transition_service=kwargs.get("transition_service"),
            boot_service=kwargs.get("boot_service"),
        )
        super().__init__(service, devices, parent, **kwargs)
        if self._owns_session:
            operation_session.setParent(self)
        self.boot_timer.stop()
        self.boot_timer.deleteLater()
        self.session = operation_session
        self.boot_timer = operation_session.boot_timer
        self._experience_mode = experience_mode
        self._details_expanded = experience_mode is ExperienceMode.EXPERT
        self.setWindowTitle("ROMVERSE · Source-declared installation")
        self.eyebrow.setText("GUIDED INSTALLATION  •  PACKAGE PROCEDURE")
        self.title.setText("Review the complete declared installation")
        candidate = isinstance(recipe, CandidateInstallationRecipe)
        self._candidate_installation = candidate
        if candidate:
            self.setWindowTitle("ROMVERSE · Rebuilt ROM installation")
            self.eyebrow.setText("GUIDED INSTALLATION  •  YOUR REBUILT ROM")
            self.title.setText("Review your complete ROM installation")
        self.introduction.setText(recipe.label)
        self.introduction.setTextFormat(Qt.TextFormat.PlainText)
        self.mapping_hint.setText(
            "This sequence comes from a supported package procedure, not guessed filenames. "
            "It can replace boot-critical firmware and the full super container. Read every action."
        )
        self.add_button.hide()
        self.remove_button.hide()
        self.images.setHorizontalHeaderLabels(("Declared action", "Destination / source member"))
        self.images.setRowCount(len(recipe.steps))
        rebuilt_members = (
            {item.member for item in recipe.origins if item.source_kind == "rebuilt"}
            if candidate
            else set()
        )
        for index, step in enumerate(recipe.steps):
            target = (
                f"{step.partition} ← {step.image_member}"
                if step.action == "flash"
                else step.slot
                if step.action == "set_active"
                else step.partition
                if step.action == "erase"
                else "Android"
            )
            if step.image_member in rebuilt_members:
                target = f"{step.partition} ← YOUR REBUILT IMAGE"
            for column, text in enumerate((step.action.replace("_", " "), target)):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.images.setItem(index, column, item)
        self.review_button.setText("Review installation and phone")
        self.flash_button.setText("Run reviewed installation…")
        self.boundary.setText(
            (
                "DATA WILL BE ERASED. "
                if recipe.wipe
                else "No data erase requested; data preservation and compatibility are unproven. "
            )
            + "Keep an independent backup and recovery route. Boot, readback and subsystem health "
            "are measured separately; procedure recognition is not a safety certificate."
        )
        self.status.setText(
            f"{len(recipe.steps)} declared actions · target slot {recipe.target_slot.upper()}. "
            "Review sends only read-only checks; no installation begins without final confirmation."
        )
        self.experience_button = QPushButton()
        self.experience_button.setAccessibleName("Switch Guided or Expert installation view")
        self.experience_button.clicked.connect(self._request_experience_mode)
        self.layout().insertWidget(2, self.experience_button)
        self.guided_summary = QLabel()
        self.guided_summary.setObjectName("GuidedOperationCard")
        self.guided_summary.setWordWrap(True)
        self.guided_summary.setTextFormat(Qt.TextFormat.PlainText)
        self.guided_summary.setAccessibleName("Guided installation status and exact phone")
        self.layout().insertWidget(3, self.guided_summary)
        self.details_button = QPushButton("View technical details")
        self.details_button.setCheckable(True)
        self.details_button.setChecked(self._details_expanded)
        self.details_button.clicked.connect(self._toggle_details)
        self.layout().insertWidget(self.layout().indexOf(self.images), self.details_button)
        self.guided_primary = QPushButton()
        self.guided_primary.setObjectName("Primary")
        self.guided_primary.setMinimumHeight(46)
        self.guided_primary.clicked.connect(self._guided_primary_action)
        self.layout().insertWidget(self.layout().indexOf(self.status), self.guided_primary)
        operation_session.changed.connect(self._render_session)
        operation_session.transition_review_ready.connect(self._confirm_transition_review)
        operation_session.operation_finished.connect(self.operation_finished.emit)
        operation_session.transition_finished.connect(self.transition_finished.emit)
        operation_session.boot_finished.connect(self.boot_finished.emit)
        operation_session.recovery_required.connect(self._session_recovery_required)
        self.set_experience_mode(experience_mode)
        self._render_session(operation_session.snapshot())

    def _inspect(self):
        if hasattr(self, "session"):
            self.session.review_installation()

    def _refresh_devices(self):
        if hasattr(self, "session"):
            self.session.refresh_devices()

    def _selected_device(self):
        if hasattr(self, "session"):
            return self.session.selected_device()
        return super()._selected_device()

    def _invalidate(self, *_args):
        if not hasattr(self, "session"):
            return super()._invalidate(*_args)
        index = self.target.currentIndex()
        serial = self.session.devices[index].serial if 0 <= index < len(self.session.devices) else ""
        self.session.select_device(serial)

    def _change_mode(self):
        if not hasattr(self, "session"):
            return
        review = self.session.transition_review
        if review is not None:
            self._confirm_transition_review(review)
            return
        self.session.review_transition(self.mode_target.currentData())

    def _confirm_flash(self):
        plan = self.session.plan
        snapshot = self.session.snapshot()
        if (
            not isinstance(plan, SourceInstallationPlan)
            or snapshot.busy
        ):
            return
        question = QMessageBox(self)
        question.setIcon(QMessageBox.Icon.Warning)
        question.setTextFormat(Qt.TextFormat.PlainText)
        question.setWindowTitle("Confirm source-declared installation")
        question.setText(
            f"Run {len(plan.recipe.steps)} declared actions on {plan.device_name} {plan.masked_serial}?"
        )
        question.setInformativeText(
            (
                "ALL PHONE USER DATA WILL BE ERASED.\n\n"
                if plan.recipe.wipe
                else "No data erase requested; data preservation and boot/data compatibility are unproven.\n\n"
            )
            + "This changes the active slot and writes boot-critical firmware and the full super container. "
            + (
                "It will restart Android at the end. "
                if plan.recipe.reboot
                else "It will stay in bootloader afterward. "
            )
            + "Keep USB connected. Stop requests take effect between actions, not in the middle of a write. "
            "Proceed only with your own backup and recovery route and after accepting these risks."
        )
        question.setDetailedText(self.review.toPlainText())
        confirm = question.addButton(
            "Erase data and install" if plan.recipe.wipe else "Install reviewed package",
            QMessageBox.ButtonRole.AcceptRole,
        )
        cancel = question.addButton(QMessageBox.StandardButton.Cancel)
        question.setDefaultButton(cancel)
        question.exec()
        if question.clickedButton() is not confirm:
            self.status.setText("Installation cancelled. No installation command was sent.")
            return
        self.session.accept_installation(snapshot.revision, plan.plan_digest)

    def _set_busy(self, busy, *, writing=False):
        if not hasattr(self, "session"):
            return super()._set_busy(busy, writing=writing)
        snapshot = self.session.snapshot()
        target_change_open = (
            snapshot.can_review or snapshot.phase is SourceOperationPhase.REVIEW_READY
        )
        self.target.setEnabled(not snapshot.busy and target_change_open)
        for widget in (self.images, self.add_button, self.remove_button):
            widget.setEnabled(not snapshot.busy)
        self.close_button.setEnabled(True)
        self.close_button.setText("Hide operation" if snapshot.busy else "Close")
        self.review_button.setEnabled(snapshot.can_review)
        self.refresh_button.setEnabled(snapshot.can_refresh)
        self.flash_button.setEnabled(snapshot.can_install)
        self.mode_target.setEnabled(snapshot.can_change_mode)
        self.mode_button.setEnabled(
            snapshot.can_change_mode or self.session.transition_review is not None
        )
        self.mode_button.setText(
            "Confirm mode change…"
            if self.session.transition_review is not None
            else "Change mode…"
        )
        self.boot_button.setEnabled(snapshot.can_check_boot)
        transitioning = (
            isinstance(self.session.worker, LocalTransitionWorker)
            and self.session.worker.plan is not None
        )
        cancellable = snapshot.writing or transitioning or snapshot.monitoring
        self.cancel_button.setText(
            "Stop boot check"
            if snapshot.monitoring
            else "Stop waiting"
            if transitioning
            else "Stop after current action"
        )
        self.cancel_button.setVisible(snapshot.busy and cancellable)
        self.cancel_button.setEnabled(
            snapshot.busy and cancellable and not snapshot.stop_requested
        )
        self.recovery_button.setVisible(snapshot.recovery_available)
        self.recovery_button.setEnabled(snapshot.recovery_available)

    def _cancel(self):
        self.session.request_stop()

    def _check_boot(self):
        self.session.check_boot()

    def _poll_boot(self):
        if hasattr(self, "session"):
            self.session._poll_boot()

    def _session_recovery_required(self):
        if self.isVisible() and not self.session.busy:
            QDialog.accept(self)

    def _open_recovery(self):
        if self.session.request_recovery():
            QDialog.accept(self)

    def _confirm_transition_review(self, review):
        if not isinstance(review, SourceTransitionReview) or not self.isVisible():
            return
        question = QMessageBox(self)
        question.setIcon(QMessageBox.Icon.Warning)
        question.setTextFormat(Qt.TextFormat.PlainText)
        question.setWindowTitle("Confirm phone mode change")
        question.setText(
            f"Restart {review.plan.device_name} {review.plan.masked_serial} into "
            f"{review.target.value}?"
        )
        question.setInformativeText(
            "The phone will disconnect briefly. Save your work on it first. This action does not "
            "flash images, erase data or change the active slot. Android boot will be checked "
            "separately after reconnection."
        )
        question.setDetailedText(
            "\n".join(
                (
                    f"From: {review.plan.source_mode}",
                    f"Plan: {review.plan.plan_digest}",
                    *review.plan.warnings,
                )
            )
        )
        confirm = question.addButton("Restart phone", QMessageBox.ButtonRole.AcceptRole)
        cancel = question.addButton(QMessageBox.StandardButton.Cancel)
        question.setDefaultButton(cancel)
        question.exec()
        if question.clickedButton() is confirm:
            self.session.accept_transition(review)
        else:
            self.status.setText("Mode change cancelled. No reboot command was sent.")

    def _render_session(self, snapshot):
        if not isinstance(snapshot, SourceOperationSnapshot):
            return
        session = self.session
        self.worker = session.worker
        self.plan = session.plan
        self.result = session.result
        self.execution_error = session.execution_error
        self.last_attempt_device = session.last_attempt_device
        self.last_flash_device = session.last_flash_device
        self.transition_result = session.transition_result
        self.transition_error = session.transition_error
        self.transition_attempt_device = session.transition_attempt_device
        self.boot_session = session.boot_session
        self.boot_report = session.boot_report
        self.boot_device = session.boot_device
        self.boot_error = session.boot_error
        self.monitoring = session.monitoring
        self.recovery_requested = session.recovery_requested
        self.devices = session.devices
        labels = [
            f"{item.display_name} · {item.masked_serial()} · {item.state.value}"
            for item in session.devices
        ]
        current_labels = [self.target.itemText(index) for index in range(self.target.count())]
        if labels != current_labels:
            self.target.blockSignals(True)
            self.target.clear()
            self.target.addItems(labels)
            self.target.blockSignals(False)
        selected_index = next(
            (
                index
                for index, item in enumerate(session.devices)
                if item.serial == snapshot.selected_serial
            ),
            -1,
        )
        if self.target.currentIndex() != selected_index:
            self.target.blockSignals(True)
            self.target.setCurrentIndex(selected_index)
            self.target.blockSignals(False)
        self.status.setText(snapshot.status)
        if self.review.toPlainText() != snapshot.details:
            self.review.setPlainText(snapshot.details)
        if snapshot.progress_indeterminate:
            self.progress.setRange(0, 0)
        else:
            self.progress.setRange(0, max(1, snapshot.progress_total))
            self.progress.setValue(snapshot.progress_value)
        self.progress.setFormat(snapshot.progress_format)
        self._set_busy(snapshot.busy, writing=snapshot.writing)
        self._render_guided_summary(snapshot)
        self._apply_details_visibility()
        if snapshot.phase in {SourceOperationPhase.REVIEW_READY, SourceOperationPhase.COMPLETED}:
            self.progress.setAccessibleName("Verified installation journey progress")

    def _render_guided_summary(self, snapshot):
        device = self.session.selected_device()
        device_name = device.display_name if device is not None else "Connect your Android phone"
        stage = {
            SourceOperationPhase.READY: "Ready to prepare",
            SourceOperationPhase.REFRESHING: "Finding your phone",
            SourceOperationPhase.REVIEWING: "Checking everything is ready",
            SourceOperationPhase.REVIEW_READY: "Ready to install",
            SourceOperationPhase.INSTALLING: "Installing your ROM",
            SourceOperationPhase.TRANSITION_REVIEWING: "Checking the requested phone mode",
            SourceOperationPhase.TRANSITION_READY: "One decision is needed",
            SourceOperationPhase.TRANSITIONING: "Changing phone mode",
            SourceOperationPhase.BOOT_CHECKING: "Starting Android and checking stability",
            SourceOperationPhase.COMPLETED: "Your installation journey is complete",
            SourceOperationPhase.ATTENTION: "ROMVERSE has prepared recovery",
        }[snapshot.phase]
        data = (
            "Data erase is included in this reviewed procedure"
            if self.recipe.wipe
            else "No data erase requested; preservation is not guaranteed"
        )
        self.guided_summary.setProperty("operationState", snapshot.phase.value)
        self.guided_summary.setText(
            f"{stage}\n\n{device_name}\n{len(self.recipe.steps)} verified package actions · {data}"
        )
        self.guided_summary.style().unpolish(self.guided_summary)
        self.guided_summary.style().polish(self.guided_summary)
        if snapshot.phase is SourceOperationPhase.REVIEW_READY:
            text, enabled = "Install ROM…", snapshot.can_install
        elif snapshot.phase is SourceOperationPhase.READY:
            text, enabled = "Prepare installation", snapshot.can_review
        elif (
            snapshot.phase is SourceOperationPhase.COMPLETED
            and self.session.boot_report is None
            and self.session.boot_service is not None
        ):
            text, enabled = "Check Android boot", snapshot.can_check_boot
        elif snapshot.phase is SourceOperationPhase.ATTENTION and snapshot.recovery_available:
            text, enabled = "Open diagnosis and recovery", snapshot.recovery_available
        elif snapshot.phase is SourceOperationPhase.ATTENTION:
            text, enabled = "Check readiness again", snapshot.can_review
        elif snapshot.phase is SourceOperationPhase.COMPLETED:
            text, enabled = "Finish", True
        else:
            text, enabled = stage, False
        self.guided_primary.setText(text)
        self.guided_primary.setEnabled(enabled)

    def _guided_primary_action(self):
        snapshot = self.session.snapshot()
        if snapshot.phase is SourceOperationPhase.REVIEW_READY:
            self._confirm_flash()
        elif snapshot.phase is SourceOperationPhase.READY:
            self.session.review_installation()
        elif (
            snapshot.phase is SourceOperationPhase.COMPLETED
            and self.session.boot_report is None
            and self.session.boot_service is not None
        ):
            self.session.check_boot()
        elif snapshot.phase is SourceOperationPhase.ATTENTION and snapshot.recovery_available:
            self._open_recovery()
        elif snapshot.phase is SourceOperationPhase.ATTENTION and snapshot.can_review:
            self.session.review_installation()
        elif snapshot.phase is SourceOperationPhase.COMPLETED:
            self.accept()

    def _toggle_details(self, checked):
        self._details_expanded = bool(checked)
        self._apply_details_visibility()

    def _apply_details_visibility(self):
        expanded = self._experience_mode is ExperienceMode.EXPERT or self._details_expanded
        guided = self._experience_mode is ExperienceMode.GUIDED
        self.guided_summary.setVisible(guided)
        self.guided_primary.setVisible(guided)
        self.details_button.setVisible(guided)
        self.details_button.setText(
            "Hide technical details" if expanded else "View technical details"
        )
        for widget in (self.mapping_hint, self.images, self.review):
            widget.setVisible(expanded)
        self.mode_target.setVisible(not guided)
        self.mode_button.setVisible(not guided)
        self.boot_button.setVisible(not guided)
        self.review_button.setVisible(not guided)
        self.flash_button.setVisible(not guided)
        self.recovery_button.setVisible(
            not guided and self.session.snapshot().recovery_available
        )
        choose_target = not guided or len(self.session.devices) != 1
        self.target_label.setVisible(choose_target)
        self.target.setVisible(choose_target)
        self.refresh_button.setVisible(choose_target)

    def set_experience_mode(self, mode):
        self._experience_mode = ExperienceMode(mode)
        expert = self._experience_mode is ExperienceMode.EXPERT
        self.experience_button.setText(
            "Switch to Guided view" if expert else "Switch to Expert view"
        )
        self.eyebrow.setText(
            "EXPERT INSTALLATION  •  COMPLETE TECHNICAL EVIDENCE"
            if expert
            else "GUIDED INSTALLATION  •  ROMVERSE HANDLES THE JOURNEY"
        )
        self.title.setText(
            (
                "Review your complete ROM installation"
                if self._candidate_installation
                else "Review the complete declared installation"
            )
            if expert
            else "Install your rebuilt ROM"
            if self._candidate_installation
            else "Install this firmware package"
        )
        self._apply_details_visibility()

    def _request_experience_mode(self):
        selected = (
            ExperienceMode.GUIDED
            if self._experience_mode is ExperienceMode.EXPERT
            else ExperienceMode.EXPERT
        )
        if selected is ExperienceMode.EXPERT:
            from romverse.ui.rom_studio import confirm_expert_mode

            if not confirm_expert_mode(self):
                return
        self.set_experience_mode(selected)
        self.experience_mode_requested.emit(selected)

    def done(self, result):
        if self._owns_session and self.session.busy:
            self.status.setText(
                "This standalone operation must finish or be explicitly stopped before closing."
            )
            return
        QDialog.done(self, result)

    def reject(self):
        self.done(QDialog.DialogCode.Rejected)

    def closeEvent(self, event):  # noqa: N802
        if self._owns_session and self.session.busy:
            event.ignore()
            self.status.setText(
                "This standalone operation must finish or be explicitly stopped before closing."
            )
            return
        QDialog.closeEvent(self, event)
