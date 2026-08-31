from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from romverse.ascension.models import AscensionMethod
from romverse.ascension.route import AscensionRouteRecord


class AscensionEntryState(StrEnum):
    """Beginner-facing certainty for the optional Genesis root decision."""

    SUPPORTED = "supported"
    CAUTION = "caution"
    BLOCKED = "blocked"
    UNCONFIRMED = "unconfirmed"


@dataclass(frozen=True, slots=True)
class AscensionEntryBrief:
    """Read-only explanation of the route Genesis may offer to a user.

    This object is intentionally incapable of carrying commands or execution authority.
    It teaches what ROMVERSE knows, what it can automate next, and what still belongs to
    the user and Guardian.
    """

    state: AscensionEntryState
    title: str
    summary: str
    method: AscensionMethod | None
    patch_target: str
    confidence: str
    evidence: tuple[str, ...]
    route_digest: str
    execution_authority: str = "none"
    phone_changed: bool = False
    bootloader_relock_allowed: bool = False

    @property
    def method_label(self) -> str:
        return self.method.display_name if self.method is not None else "Not selected"

    @property
    def status_label(self) -> str:
        return self.state.value.upper()

    @property
    def rooted_button_label(self) -> str:
        if self.state is AscensionEntryState.SUPPORTED and self.method is not None:
            return f"Yes • Use {self.method.display_name} in Ascension"
        if self.state is AscensionEntryState.CAUTION:
            return "Yes • Review candidate in Ascension"
        if self.state is AscensionEntryState.BLOCKED:
            return "Review blockers in Ascension Protocol"
        return "Yes • Let Ascension scan and recommend"

    def guidance(self, *, scanning: bool = False) -> str:
        status = "SCANNING" if scanning else self.status_label
        target = self.patch_target or "Unconfirmed until the evidence scan completes"
        evidence = (
            "\n".join(f"• {item}" for item in self.evidence[:4])
            if self.evidence
            else "• No authoritative route evidence has been recorded yet"
        )
        return (
            f"ROOT ROUTE  •  {status}\n"
            f"{self.title}\n\n"
            f"Recommended method: {self.method_label}\n"
            f"Source image target: {target}\n"
            f"Confidence: {self.confidence.upper()}\n\n"
            f"Why ROMVERSE says this:\n{evidence}\n\n"
            "If you choose root, Ascension Protocol will verify the protected source and Device "
            "DNA, acquire a supported manager only from its official release channel, guide the "
            "source-bound patch, verify the returned image, and integrate it into the ROM build.\n\n"
            "You still decide whether to root and approve any later Guardian device-write review.\n"
            "Phone changed now: NO  •  Execution authority: NONE  •  Bootloader relock: NEVER"
        )


def build_ascension_entry_brief(
    record: AscensionRouteRecord | None,
    *,
    device_matches: bool = False,
    error: str = "",
) -> AscensionEntryBrief:
    """Translate an authenticated route record into conservative beginner guidance."""

    if record is None:
        summary = (
            "The route scan stopped safely. Ascension Protocol can show the exact missing "
            "evidence and retry without changing the phone."
            if error
            else "ROMVERSE has not completed the current source-and-device route scan yet. "
            "No root method is being guessed."
        )
        return AscensionEntryBrief(
            AscensionEntryState.UNCONFIRMED,
            "Root recommendation is not confirmed yet",
            summary,
            None,
            "",
            "unconfirmed",
            (error,) if error else (),
            "",
        )

    invariants_hold = (
        record.execution_authority == "none"
        and not record.command_manifest
        and not record.phone_changed
        and not record.bootloader_relock_allowed
    )
    if not invariants_hold:
        return AscensionEntryBrief(
            AscensionEntryState.BLOCKED,
            "Route record failed the Guardian boundary check",
            "ROMVERSE rejected a route record that carried unsafe authority or state.",
            None,
            "",
            "unconfirmed",
            (),
            "",
        )

    evidence = tuple(dict.fromkeys(item for item in record.evidence if item.strip()))
    route_digest = record.record_digest[:16]
    if not device_matches:
        return AscensionEntryBrief(
            AscensionEntryState.UNCONFIRMED,
            "Current phone does not match the saved root route",
            "ROMVERSE will rescan rather than reuse evidence from another device or kernel.",
            None,
            "",
            "unconfirmed",
            evidence,
            route_digest,
        )

    if record.state == "blocked" or record.blocker_count:
        return AscensionEntryBrief(
            AscensionEntryState.BLOCKED,
            record.title,
            record.reason,
            None,
            record.patch_target,
            record.confidence,
            evidence,
            route_digest,
        )

    method = record.recommended_method
    if (
        record.state == "ready-local-only"
        and record.ready_for_local_preparation
        and method is not None
    ):
        state = (
            AscensionEntryState.SUPPORTED
            if record.confidence == "verified"
            else AscensionEntryState.CAUTION
        )
        return AscensionEntryBrief(
            state,
            record.title,
            record.reason,
            method,
            record.patch_target,
            record.confidence,
            evidence,
            route_digest,
        )

    return AscensionEntryBrief(
        AscensionEntryState.UNCONFIRMED,
        record.title,
        record.reason,
        None,
        record.patch_target,
        record.confidence,
        evidence,
        route_digest,
    )
