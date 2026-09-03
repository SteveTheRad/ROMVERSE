package com.radforge.romverse.companion

internal enum class CompanionLinkJourneyState {
    LIVE,
    SYNCING,
    STALE,
    REAUTHORIZE,
    ENTER_CODE,
    CONFIRM_IDENTITY,
    DISCOVERING,
    DISCOVER,
    USB_ONLY,
    NETWORK_NEEDED,
}

internal enum class CompanionLinkStepState {
    COMPLETE,
    ACTIVE,
    WAITING,
    ATTENTION,
}

internal data class CompanionLinkStep(
    val label: String,
    val status: String,
    val state: CompanionLinkStepState,
)

internal data class CompanionLinkReadiness(
    val state: CompanionLinkJourneyState,
    val headline: String,
    val detail: String,
    val nextAction: String,
    val progressPercent: Int,
    val lastSyncLabel: String,
    val steps: List<CompanionLinkStep>,
) {
    init {
        require(progressPercent in 0..100) { "Link progress must be 0..100" }
        require(steps.size == 5) { "Link Flight Path requires exactly five stages" }
    }
}

/** Truthful UI policy for the local Companion-to-Desktop Link journey. */
internal object CompanionLinkReadinessPolicy {
    const val FRESH_SYNC_AGE_MILLIS = 30_000L

    fun assess(
        localNetworkAvailable: Boolean,
        usbConnected: Boolean,
        endpointPresent: Boolean,
        certificateValid: Boolean,
        safetyConfirmed: Boolean,
        desktopRemembered: Boolean,
        secureSession: Boolean,
        discoveryInFlight: Boolean,
        syncInFlight: Boolean,
        lastSuccessfulSyncEpochMs: Long,
        nowEpochMs: Long,
    ): CompanionLinkReadiness {
        require(nowEpochMs >= 0L) { "Link readiness clock is invalid" }
        require(lastSuccessfulSyncEpochMs >= 0L) { "Link sync timestamp is invalid" }

        val desktopFound = endpointPresent && certificateValid
        val identityConfirmed = desktopFound && (desktopRemembered || safetyConfirmed)
        val sessionVerified = identityConfirmed && secureSession
        val syncAge = lastSuccessfulSyncEpochMs
            .takeIf { it in 1..nowEpochMs }
            ?.let { nowEpochMs - it }
        val syncFresh = sessionVerified && syncAge != null && syncAge <= FRESH_SYNC_AGE_MILLIS

        val state = when {
            sessionVerified && syncInFlight -> CompanionLinkJourneyState.SYNCING
            syncFresh -> CompanionLinkJourneyState.LIVE
            sessionVerified -> CompanionLinkJourneyState.STALE
            desktopRemembered -> CompanionLinkJourneyState.REAUTHORIZE
            !localNetworkAvailable && usbConnected -> CompanionLinkJourneyState.USB_ONLY
            !localNetworkAvailable -> CompanionLinkJourneyState.NETWORK_NEEDED
            !desktopFound && discoveryInFlight -> CompanionLinkJourneyState.DISCOVERING
            !desktopFound -> CompanionLinkJourneyState.DISCOVER
            !identityConfirmed -> CompanionLinkJourneyState.CONFIRM_IDENTITY
            else -> CompanionLinkJourneyState.ENTER_CODE
        }
        val complete = listOf(true, desktopFound, identityConfirmed, sessionVerified, syncFresh)
        val firstIncomplete = complete.indexOfFirst { !it }
        val stepLabels = listOf("PHONE", "DESKTOP", "IDENTITY", "SESSION", "SYNC")
        val completeLabels = listOf("READY", "FOUND", "VERIFIED", "SECURE", "LIVE")
        val waitingLabels = listOf("READY", "WAITING", "WAITING", "WAITING", "WAITING")
        val steps = stepLabels.indices.map { index ->
            val stepState = when {
                complete[index] -> CompanionLinkStepState.COMPLETE
                index != firstIncomplete -> CompanionLinkStepState.WAITING
                index == 1 && !localNetworkAvailable -> CompanionLinkStepState.ATTENTION
                else -> CompanionLinkStepState.ACTIVE
            }
            val status = when {
                complete[index] -> completeLabels[index]
                index != firstIncomplete -> waitingLabels[index]
                index == 1 && !localNetworkAvailable -> "NEEDS WI-FI"
                index == 1 && discoveryInFlight -> "FINDING"
                index == 1 -> "FIND PC"
                index == 2 -> "CONFIRM"
                index == 3 -> "AUTHORIZE"
                index == 4 && syncInFlight -> "SYNCING"
                index == 4 -> "REFRESH"
                else -> waitingLabels[index]
            }
            CompanionLinkStep(stepLabels[index], status, stepState)
        }
        val lastSyncLabel = syncAge?.let(::ageLabel) ?: "No verified two-way sync yet"
        val (headline, detail, action) = copyFor(state, lastSyncLabel)
        return CompanionLinkReadiness(
            state = state,
            headline = headline,
            detail = detail,
            nextAction = action,
            progressPercent = complete.count { it } * 20,
            lastSyncLabel = lastSyncLabel,
            steps = steps,
        )
    }

    private fun copyFor(
        state: CompanionLinkJourneyState,
        lastSyncLabel: String,
    ): Triple<String, String, String> = when (state) {
        CompanionLinkJourneyState.LIVE -> Triple(
            "Desktop and phone are in sync",
            "Pinned TLS identity, active approval, Desktop evidence, and phone health all verified.",
            "SYNC NOW",
        )
        CompanionLinkJourneyState.SYNCING -> Triple(
            "Synchronizing verified evidence",
            "ROMVERSE is refreshing Desktop status and returning a fresh phone health snapshot.",
            "SYNCING…",
        )
        CompanionLinkJourneyState.STALE -> Triple(
            "Secure Link needs a refresh",
            "$lastSyncLabel. The approval is active, but current two-way evidence is not yet fresh.",
            "REFRESH SECURE LINK",
        )
        CompanionLinkJourneyState.REAUTHORIZE -> Triple(
            "Trusted Desktop remembered",
            "Its pinned identity is preserved, but the time-limited approval has ended.",
            "ENTER NEW LINK CODE",
        )
        CompanionLinkJourneyState.ENTER_CODE -> Triple(
            "Desktop identity confirmed",
            "Enter the six-digit code from Desktop, then approve the request on the PC.",
            "ENTER LINK CODE",
        )
        CompanionLinkJourneyState.CONFIRM_IDENTITY -> Triple(
            "Compare the Link safety code",
            "Confirm the same code is visible on Desktop before requesting approval.",
            "REVIEW SAFETY CODE",
        )
        CompanionLinkJourneyState.DISCOVERING -> Triple(
            "Searching the local galaxy",
            "Listening only for a compatible ROMVERSE Desktop advertisement on this network.",
            "SEARCHING…",
        )
        CompanionLinkJourneyState.DISCOVER -> Triple(
            "Find ROMVERSE Desktop",
            "Open ROMVERSE Link on the PC. Discovery fills the local address and certificate identity.",
            "FIND DESKTOP",
        )
        CompanionLinkJourneyState.USB_ONLY -> Triple(
            "USB detected • Link not paired",
            "Link not paired. USB helps Desktop identify this phone, but Companion's encrypted live view pairs over trusted Wi-Fi.",
            "OPEN WI-FI SETTINGS",
        )
        CompanionLinkJourneyState.NETWORK_NEEDED -> Triple(
            "Connect to the trusted local network",
            "Phone and PC need a shared local network for encrypted ROMVERSE Link discovery.",
            "OPEN WI-FI SETTINGS",
        )
    }

    private fun ageLabel(ageMillis: Long): String = when {
        ageMillis < 1_000L -> "Last verified sync just now"
        ageMillis < 60_000L -> "Last verified sync ${ageMillis / 1_000L}s ago"
        ageMillis < 3_600_000L -> "Last verified sync ${ageMillis / 60_000L}m ago"
        else -> "Last verified sync ${ageMillis / 3_600_000L}h ago"
    }
}
