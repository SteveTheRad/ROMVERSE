from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class RootIdentityState(StrEnum):
    OBSERVED = "observed"
    MANAGER_CANDIDATE = "manager-candidate"
    NOT_CONFIRMED = "not-confirmed"
    UNCONFIRMED = "unconfirmed"


ROOT_MANAGER_CANDIDATES = {"unknown", "none", "magisk", "kernelsu_lkm", "conflict"}


@dataclass(frozen=True, slots=True)
class RootIdentityReview:
    """Read-only root evidence without claiming that Manager presence proves root."""

    state: RootIdentityState
    root_observed: bool | None
    manager_candidate: str
    manager_label: str
    confidence: str
    title: str
    summary: str
    next_action: str
    evidence: tuple[str, ...]
    execution_authority: str = "none"
    phone_changed: bool = False
    bootloader_relock_allowed: bool = False


def review_root_identity(
    root_observed: bool | None,
    manager_candidate: str = "unknown",
    *,
    root_signal_source: str = "",
    manager_evidence: str = "",
) -> RootIdentityReview:
    candidate = manager_candidate if manager_candidate in ROOT_MANAGER_CANDIDATES else "unknown"
    manager_label = {
        "magisk": "Magisk Manager candidate",
        "kernelsu_lkm": "KernelSU Manager candidate",
        "conflict": "Magisk and KernelSU Manager candidates",
        "none": "No allowlisted Manager candidate",
        "unknown": "Manager identity unconfirmed",
    }[candidate]
    source = root_signal_source or "unspecified read-only root signal"
    manager_source = manager_evidence or "manager identity was not inspected"
    evidence = (f"Root signal: {source}", f"Manager evidence: {manager_source}")

    if root_observed is True:
        if candidate in {"magisk", "kernelsu_lkm"}:
            summary = (
                f"ROMVERSE observed a root indicator and found a {manager_label.lower()}. "
                "Manager presence identifies a likely route, but does not prove which backend is active."
            )
            next_action = (
                f"Open the installed {manager_label.removesuffix(' candidate')} and verify its "
                "installed/active status and version. Do not prepare a replacement method until "
                "that review is complete."
            )
        elif candidate == "conflict":
            summary = (
                "ROMVERSE observed a root indicator and found both allowlisted Manager packages. "
                "It cannot safely infer which method owns the active root state."
            )
            next_action = (
                "Review both installed Managers and restore a single understood route before "
                "preparing any replacement."
            )
        else:
            summary = (
                "ROMVERSE observed a root indicator, but could not identify an allowlisted "
                "Magisk or KernelSU Manager with sufficient evidence."
            )
            next_action = (
                "Identify the existing root solution or restore the exact stock image before "
                "starting a different root route."
            )
        return RootIdentityReview(
            RootIdentityState.OBSERVED,
            True,
            candidate,
            manager_label,
            "strong" if root_signal_source == "adb-shell-uid-0" else "caution",
            f"Existing root indicator observed • {manager_label}",
            summary,
            next_action,
            evidence,
        )

    if candidate in {"magisk", "kernelsu_lkm", "conflict"}:
        return RootIdentityReview(
            RootIdentityState.MANAGER_CANDIDATE,
            root_observed,
            candidate,
            manager_label,
            "caution",
            f"{manager_label} found • active root unconfirmed",
            (
                f"ROMVERSE found {manager_label.lower()}, but package presence does not prove an "
                "active rooted system. The available root indicator also did not confirm root."
            ),
            "Open the Manager only if you need to review its status; ROMVERSE will not infer root or layer another method from package presence alone.",
            evidence,
        )

    if root_observed is False:
        return RootIdentityReview(
            RootIdentityState.NOT_CONFIRMED,
            False,
            candidate,
            manager_label,
            "unconfirmed",
            "Active root was not confirmed",
            "The read-only probe did not observe a root indicator. This is not proof that the phone is unrooted.",
            "ROMVERSE may continue source-bound local preparation, but Guardian must reassess root and device evidence before any write.",
            evidence,
        )

    return RootIdentityReview(
        RootIdentityState.UNCONFIRMED,
        None,
        candidate,
        manager_label,
        "unconfirmed",
        "Root identity is unconfirmed",
        "ROMVERSE does not have enough read-only evidence to identify the phone's root state or method.",
        "Reconnect the authorized phone or authenticated Companion and rescan; ROMVERSE will not guess.",
        evidence,
    )
