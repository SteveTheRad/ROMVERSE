package com.radforge.romverse.companion

internal data class VitalisSnapshot(
    val batteryPercent: Int?,
    val temperatureCelsius: Double?,
    val storageUsedPercent: Int?,
    val ramUsedPercent: Int?,
    val networkValidated: Boolean?,
    val usbConnected: Boolean?,
    val capturedAtEpochMs: Long = System.currentTimeMillis(),
) {
    init {
        require(capturedAtEpochMs > 0L)
        require(batteryPercent == null || batteryPercent in 0..100)
        require(temperatureCelsius == null || temperatureCelsius in -20.0..100.0)
        require(storageUsedPercent == null || storageUsedPercent in 0..100)
        require(ramUsedPercent == null || ramUsedPercent in 0..100)
    }
}

internal enum class VitalisSeverity {
    HEALTHY,
    CAUTION,
    CRITICAL,
    UNCONFIRMED,
}

internal data class VitalisFinding(
    val findingId: String,
    val severity: VitalisSeverity,
    val title: String,
    val detail: String,
    val nextAction: String,
) {
    val reportLine: String
        get() = "• $title — $detail"
}

internal data class VitalisAssessment(
    val score: Int?,
    val evidencePercent: Int,
    val state: String,
    val findings: List<VitalisFinding>,
) {
    init {
        require(score == null || score in 0..100)
        require(evidencePercent in 0..100)
        require(state in setOf("OPTIMAL", "ATTENTION", "ACTION RECOMMENDED", "UNCONFIRMED"))
        require(findings.isNotEmpty() && findings.size <= 12)
    }
}

internal object VitalisAssessmentEngine {
    private const val EVIDENCE_COUNT = 6
    private const val MAX_EVIDENCE_AGE_MS = 120_000L
    private const val MAX_FUTURE_SKEW_MS = 300_000L

    fun assess(
        snapshot: VitalisSnapshot,
        nowEpochMs: Long = System.currentTimeMillis(),
    ): VitalisAssessment {
        require(nowEpochMs > 0L)
        val isTooFarInFuture = snapshot.capturedAtEpochMs > nowEpochMs &&
            snapshot.capturedAtEpochMs - nowEpochMs > MAX_FUTURE_SKEW_MS
        val isTooOld = snapshot.capturedAtEpochMs <= nowEpochMs &&
            nowEpochMs - snapshot.capturedAtEpochMs > MAX_EVIDENCE_AGE_MS
        if (isTooFarInFuture || isTooOld) {
            return VitalisAssessment(
                score = null,
                evidencePercent = 0,
                state = "UNCONFIRMED",
                findings = listOf(
                    finding(
                        "stale-evidence",
                        VitalisSeverity.UNCONFIRMED,
                        "FRESH EVIDENCE REQUIRED",
                        "The saved health reading is outside Vitalis' two-minute freshness boundary.",
                        "Refresh Vitalis to capture a new read-only health baseline.",
                    ),
                ),
            )
        }
        val findings = mutableListOf<VitalisFinding>()
        var penalty = 0
        if (snapshot.batteryPercent != null && snapshot.batteryPercent < 20) {
            penalty += 18
            findings += finding(
                "low-battery",
                VitalisSeverity.CAUTION,
                "LOW BATTERY",
                "Battery is ${snapshot.batteryPercent}%; risky repair or installation work should wait.",
                "Charge above 40%, then run a fresh Vitalis scan.",
            )
        }
        if (snapshot.temperatureCelsius != null && snapshot.temperatureCelsius >= 45.0) {
            penalty += 25
            findings += finding(
                "high-temperature",
                VitalisSeverity.CRITICAL,
                "HIGH TEMPERATURE",
                "Battery temperature is %.1f °C.".format(snapshot.temperatureCelsius),
                "Disconnect charging, let the phone cool, and verify the temperature again.",
            )
        }
        when {
            snapshot.storageUsedPercent != null && snapshot.storageUsedPercent >= 90 -> {
                penalty += 25
                findings += finding(
                    "storage-critical",
                    VitalisSeverity.CRITICAL,
                    "STORAGE CRITICAL",
                    "Storage is ${snapshot.storageUsedPercent}% used; recovery headroom is too low.",
                    "Review large files in Android storage settings and keep at least 10% free.",
                )
            }
            snapshot.storageUsedPercent != null && snapshot.storageUsedPercent >= 80 -> {
                penalty += 10
                findings += finding(
                    "storage-pressure",
                    VitalisSeverity.CAUTION,
                    "STORAGE PRESSURE",
                    "Storage is ${snapshot.storageUsedPercent}% used.",
                    "Review large files and preserve enough space for downloads and rollback material.",
                )
            }
        }
        if (snapshot.ramUsedPercent != null && snapshot.ramUsedPercent >= 90) {
            penalty += 12
            findings += finding(
                "memory-pressure",
                VitalisSeverity.CAUTION,
                "MEMORY PRESSURE",
                "RAM is ${snapshot.ramUsedPercent}% used.",
                "Close heavy apps, restart if appropriate, and reproduce the issue once more.",
            )
        }
        if (snapshot.networkValidated == false) {
            penalty += 8
            findings += finding(
                "network-not-validated",
                VitalisSeverity.CAUTION,
                "NETWORK NOT VALIDATED",
                "Android has not validated the active internet connection.",
                "Reconnect Wi-Fi or mobile data before an online recovery step.",
            )
        }
        if (snapshot.usbConnected == false) {
            findings += finding(
                "usb-not-detected",
                VitalisSeverity.HEALTHY,
                "USB LINK OPTIONAL",
                "No USB connection is currently visible; normal Companion health remains available.",
                "Connect a data-capable cable only when a Link or Lifeline step asks for Desktop.",
            )
        }
        val unknown = buildList {
            if (snapshot.batteryPercent == null) add("battery level")
            if (snapshot.temperatureCelsius == null) add("battery temperature")
            if (snapshot.storageUsedPercent == null) add("storage use")
            if (snapshot.ramUsedPercent == null) add("memory use")
            if (snapshot.networkValidated == null) add("network validation")
            if (snapshot.usbConnected == null) add("USB state")
        }
        if (unknown.isNotEmpty()) {
            findings += finding(
                "evidence-unconfirmed",
                VitalisSeverity.UNCONFIRMED,
                "EVIDENCE UNCONFIRMED",
                "Unavailable: ${unknown.joinToString()}.",
                "Refresh Vitalis after Android can provide the missing evidence.",
            )
        }
        val observed = EVIDENCE_COUNT - unknown.size
        val scoringEvidenceObserved = snapshot.batteryPercent != null &&
            snapshot.temperatureCelsius != null && snapshot.storageUsedPercent != null &&
            snapshot.ramUsedPercent != null && snapshot.networkValidated != null
        val score = if (scoringEvidenceObserved) (100 - penalty).coerceIn(0, 100) else null
        if (findings.isEmpty()) {
            findings += finding(
                "all-clear",
                VitalisSeverity.HEALTHY,
                "ALL CLEAR",
                "No immediate resource, temperature, network, or Link risk was detected.",
                "Keep the current baseline and scan again after any meaningful change.",
            )
        }
        val state = when {
            findings.any { it.severity == VitalisSeverity.CRITICAL } ||
                (score != null && score < 65) ->
                "ACTION RECOMMENDED"
            findings.any { it.severity == VitalisSeverity.CAUTION } ||
                (score != null && score < 85) -> "ATTENTION"
            score == null || findings.any { it.severity == VitalisSeverity.UNCONFIRMED } ->
                "UNCONFIRMED"
            else -> "OPTIMAL"
        }
        return VitalisAssessment(
            score,
            (observed * 100) / EVIDENCE_COUNT,
            state,
            findings,
        )
    }

    private fun finding(
        id: String,
        severity: VitalisSeverity,
        title: String,
        detail: String,
        action: String,
    ) = VitalisFinding(id, severity, title, detail, action)
}
