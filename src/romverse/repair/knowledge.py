from __future__ import annotations

from dataclasses import dataclass

from romverse.repair.templates import RepairConcern


@dataclass(frozen=True, slots=True)
class RepairKnowledge:
    """Offline repair guidance; deliberately conservative and model-agnostic."""

    concern: RepairConcern
    overview: str
    likely_causes: tuple[str, ...]
    evidence_to_collect: tuple[str, ...]
    recommended_steps: tuple[str, ...]
    risk_note: str
    safe_automation: str


_ENTRIES = (
    RepairKnowledge(
        RepairConcern.BATTERY_HEAT,
        "Battery drain or heat usually comes from workload, radio activity, a charging fault, or an aging cell. Temperature and charge trends matter more than a single reading.",
        (
            "High-background app or sync activity",
            "Poor signal causing repeated modem work",
            "Cable/charger or battery wear",
            "Thermal load from gaming, navigation, or direct sunlight",
        ),
        (
            "Battery percentage and temperature",
            "Whether heat occurs while idle, charging, or under load",
            "Charger, cable, and recent app/update changes",
        ),
        (
            "Stop heavy use and let the phone cool in ventilation",
            "Test with a known-good charger and cable",
            "Review battery usage and remove recently installed problem apps",
            "If swelling, smell, smoke, or extreme heat is present, power off and seek qualified service",
        ),
        "Battery swelling or runaway heat is a physical safety issue; do not open or puncture the device.",
        "ROMVERSE can refresh read-only telemetry and produce a comparison report; it will not alter battery or charging settings automatically.",
    ),
    RepairKnowledge(
        RepairConcern.STORAGE,
        "Low storage can make Android services, updates, cameras, and apps fail even when the phone still appears usable.",
        (
            "Large videos/downloads",
            "App cache or offline media",
            "A failed update leaving temporary files",
            "A damaged filesystem or inaccurate storage report",
        ),
        (
            "Free/used space and affected mount",
            "Largest user and app data categories",
            "Whether failure began after an update or restore",
        ),
        (
            "Back up important data first",
            "Remove or move large files and clear cache for affected apps",
            "Keep a safety margin before updates or ROM transfers",
            "If storage totals look inconsistent, reboot and re-scan before deleting anything",
        ),
        "Never delete system partitions or unknown files as a first response; destructive cleanup requires explicit review.",
        "ROMVERSE can re-scan usage and prepare a cleanup plan; file deletion remains user-approved.",
    ),
    RepairKnowledge(
        RepairConcern.USB_ADB,
        "USB and ADB failures are commonly authorization, cable/port, driver, mode, or host-tool problems—not proof that the phone is damaged.",
        (
            "USB debugging disabled or authorization prompt missed",
            "Charge-only cable, hub, or faulty port",
            "ADB server/driver mismatch",
            "Device is in recovery, bootloader, or unauthorized state",
        ),
        (
            "ADB state and connection note",
            "Whether another cable/port/host works",
            "On-device USB debugging and RSA prompt",
            "Recovery/bootloader screen if present",
        ),
        (
            "Unlock the phone and accept the RSA prompt",
            "Try a data-rated cable and a direct host port",
            "Restart the ADB server and refresh Device Portal",
            "Install the platform tools/driver for the host OS, then re-scan",
        ),
        "Do not use random drivers or unlock commands from untrusted sources.",
        "ROMVERSE can verify tools and, when ADB is offline or failing, offer an exact Guardian-approved host-daemon restart followed by a read-only re-scan. It cannot accept the phone's RSA prompt or run a device command through that repair.",
    ),
    RepairKnowledge(
        RepairConcern.APP_CRASH,
        "App crashes may be isolated to one package or caused by shared Android services, permissions, storage, or a recent update.",
        (
            "Corrupt app cache/data",
            "Incompatible update or WebView/service",
            "Missing permission or account state",
            "Low storage or OS instability",
        ),
        (
            "Package name, crash time, and repeatability",
            "Android version and security patch",
            "Available storage and recent changes",
            "Relevant logcat excerpt when authorized",
        ),
        (
            "Update the app and core system components",
            "Force stop and clear cache first",
            "Check permissions and account sign-in",
            "Back up data before clearing app storage or uninstalling",
        ),
        "Clearing data or uninstalling can remove local content; confirm backups first.",
        "ROMVERSE can capture a read-only incident checklist; clearing data, uninstalling, or package changes stay approval-gated.",
    ),
    RepairKnowledge(
        RepairConcern.BOOT_UPDATE,
        "Boot loops and update failures need a careful distinction between a transient failed boot, incompatible software, and a hardware fault.",
        (
            "Interrupted or incompatible update",
            "Modified boot image or verified-boot mismatch",
            "Damaged cache/data",
            "Battery, storage, or board failure",
        ),
        (
            "Exact boot screen and loop timing",
            "Current build, bootloader, and Verified Boot state",
            "Recent update, root, or modification",
            "Recovery/fastboot visibility and backup status",
        ),
        (
            "Charge above the safe threshold and record the current state",
            "Try one normal reboot only; avoid repeated power cycling",
            "Use the OEM recovery path and official firmware documentation",
            "Create a Guardian-reviewed plan before any wipe, unlock, flash, or rollback",
        ),
        "Unlocking, wiping, flashing, and rollback can erase data or permanently affect the device; no such action is automatic in v0.1.",
        "ROMVERSE can document evidence and build a dry-run plan; privileged execution remains locked behind Guardian.",
    ),
    RepairKnowledge(
        RepairConcern.DISPLAY_TOUCH,
        "Display and touch faults can be software, connector, accessory, or panel failures. Separate intermittent behavior from physical damage before attempting repair.",
        (
            "Cracked or liquid-damaged panel",
            "Screen protector/case interference",
            "Display driver or accessibility setting",
            "Loose connector or failing digitizer",
        ),
        (
            "Whether the image, touch, or both are affected",
            "Behavior in recovery/bootloader versus Android",
            "Recent drop, liquid exposure, update, or replacement part",
        ),
        (
            "Remove accessories and clean/dry the surface",
            "Capture evidence before a factory reset",
            "Test safe mode or recovery only when documented for the model",
            "Use qualified hardware service for panel or connector work",
        ),
        "Opening a phone can damage seals and expose batteries; hardware repair should be performed by a qualified technician.",
        "ROMVERSE can record symptoms and compare software-state evidence; it cannot safely validate panel electronics remotely.",
    ),
    RepairKnowledge(
        RepairConcern.NETWORK,
        "Connectivity failures may be caused by coverage, airplane mode, saved-network state, radio firmware, or carrier configuration.",
        (
            "Coverage or carrier outage",
            "Incorrect time, APN, or network settings",
            "Corrupt saved network profile",
            "Radio firmware or hardware fault",
        ),
        (
            "Which radios fail and in which locations",
            "SIM/eSIM and carrier state",
            "Airplane mode, signal, and IP details",
            "Whether Bluetooth/Wi-Fi fail independently",
        ),
        (
            "Toggle the affected radio and restart once",
            "Forget and rejoin a trusted network",
            "Verify carrier/APN settings from official documentation",
            "Reset network settings only after recording saved credentials",
        ),
        "Network resets remove saved connections; never expose passwords or SIM identifiers in shared logs.",
        "ROMVERSE can collect read-only radio state and produce a privacy-safe checklist; network resets require confirmation.",
    ),
    RepairKnowledge(
        RepairConcern.CAMERA_AUDIO,
        "Camera, microphone, and speaker issues should be isolated by component, app, and direction of audio before changing system software.",
        (
            "Permission or privacy toggle",
            "Blocked speaker/microphone opening",
            "App-specific failure",
            "Water, impact, or component failure",
        ),
        (
            "Which sensor or audio direction fails",
            "Whether the stock app and a second trusted app behave the same",
            "Permission state and recent physical exposure",
        ),
        (
            "Check permissions and privacy controls",
            "Remove cases or debris from openings",
            "Restart and test with a known-good headset",
            "Back up data before any reset or repair appointment",
        ),
        "Do not probe openings with sharp tools or use compressed air against microphones.",
        "ROMVERSE can guide controlled read-only checks; permission changes and resets remain user-approved.",
    ),
    RepairKnowledge(
        RepairConcern.PERFORMANCE,
        "Slowness and freezing are usually measurable through storage pressure, thermal throttling, background workload, or a single misbehaving service.",
        (
            "Low free storage or memory pressure",
            "Thermal throttling",
            "Background sync or runaway app",
            "Aging battery or hardware fault",
        ),
        (
            "When the slowdown occurs and whether it is repeatable",
            "Battery temperature, storage use, and recent app changes",
            "Whether safe mode changes the behavior",
        ),
        (
            "Restart once and allow services to settle",
            "Free storage and review battery/app usage",
            "Update or remove one recently changed app at a time",
            "Back up before considering a reset",
        ),
        "A factory reset is not a first-line fix and can erase data; preserve evidence before taking it.",
        "ROMVERSE can trend available telemetry and build an evidence report; it will not kill processes or reset the phone automatically.",
    ),
)

_BY_CONCERN = {entry.concern: entry for entry in _ENTRIES}


def knowledge_for(concern: RepairConcern) -> RepairKnowledge:
    return _BY_CONCERN[concern]


def search_knowledge(query: str) -> tuple[RepairKnowledge, ...]:
    needle = query.strip().casefold()
    if not needle:
        return _ENTRIES
    return tuple(
        entry
        for entry in _ENTRIES
        if needle in entry.overview.casefold()
        or needle in entry.concern.value.casefold()
        or any(needle in item.casefold() for item in entry.likely_causes)
    )
