package com.radforge.romverse.companion

internal object LifelinePlanBuilder {
    private const val MAX_CHECKPOINTS = 12

    fun checkpoints(findingTitles: Collection<String>): List<String> {
        val normalized = findingTitles.map { it.trim().uppercase() }.filter(String::isNotBlank)
        val checkpoints = mutableListOf(
            "Back up important data before any risky manual action.",
        )
        if (normalized.any { "LOW BATTERY" in it }) {
            checkpoints += "Charge the phone above 40%, then confirm it is no longer reporting a low-battery warning."
        }
        if (normalized.any { "HIGH TEMPERATURE" in it }) {
            checkpoints += "Disconnect charging, let the phone cool, and confirm the temperature has returned to a safe range."
        }
        if (normalized.any { "STORAGE" in it }) {
            checkpoints += "Open Android storage settings, review large files, and preserve at least 10% free space."
        }
        if (normalized.any { "MEMORY" in it }) {
            checkpoints += "Close heavy apps, wait for memory pressure to settle, and reproduce the issue once."
        }
        if (normalized.any { "NETWORK" in it }) {
            checkpoints += "Reconnect Wi-Fi or mobile data and confirm Android reports a validated internet connection."
        }
        if (normalized.any { "USB" in it }) {
            checkpoints += "If Desktop is required, use a data-capable cable and confirm ROMVERSE Link detects the phone."
        }
        if (normalized.any { "UNCONFIRMED" in it }) {
            checkpoints += "Refresh Vitalis after Android can expose the missing evidence; do not treat unknown values as healthy."
        }
        if (checkpoints.size == 1) {
            checkpoints += "Review the diagnostic evidence and keep the current healthy baseline."
        }
        checkpoints += "Change one thing at a time and record what was tried."
        checkpoints += "Return to ROMVERSE Companion and compare the result with a fresh read-only scan."
        return checkpoints.distinct().take(MAX_CHECKPOINTS)
    }
}
