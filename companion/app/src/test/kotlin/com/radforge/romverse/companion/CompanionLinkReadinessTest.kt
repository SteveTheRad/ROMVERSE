package com.radforge.romverse.companion

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class CompanionLinkReadinessTest {
    private val now = 1_000_000L

    private fun readiness(
        localNetwork: Boolean = true,
        usb: Boolean = false,
        endpoint: Boolean = false,
        certificate: Boolean = false,
        safety: Boolean = false,
        remembered: Boolean = false,
        secure: Boolean = false,
        discovering: Boolean = false,
        syncing: Boolean = false,
        lastSync: Long = 0L,
    ) = CompanionLinkReadinessPolicy.assess(
        localNetworkAvailable = localNetwork,
        usbConnected = usb,
        endpointPresent = endpoint,
        certificateValid = certificate,
        safetyConfirmed = safety,
        desktopRemembered = remembered,
        secureSession = secure,
        discoveryInFlight = discovering,
        syncInFlight = syncing,
        lastSuccessfulSyncEpochMs = lastSync,
        nowEpochMs = now,
    )

    @Test
    fun `fresh exact session is fully live`() {
        val result = readiness(
            endpoint = true,
            certificate = true,
            remembered = true,
            secure = true,
            lastSync = now - 4_000L,
        )

        assertEquals(CompanionLinkJourneyState.LIVE, result.state)
        assertEquals(100, result.progressPercent)
        assertEquals("Last verified sync 4s ago", result.lastSyncLabel)
        assertTrue(result.steps.all { it.state == CompanionLinkStepState.COMPLETE })
    }

    @Test
    fun `secure session never claims live sync without fresh two way evidence`() {
        val result = readiness(
            endpoint = true,
            certificate = true,
            remembered = true,
            secure = true,
            lastSync = now - CompanionLinkReadinessPolicy.FRESH_SYNC_AGE_MILLIS - 1L,
        )

        assertEquals(CompanionLinkJourneyState.STALE, result.state)
        assertEquals(80, result.progressPercent)
        assertEquals(CompanionLinkStepState.ACTIVE, result.steps.last().state)
        assertEquals("REFRESH", result.steps.last().status)
    }

    @Test
    fun `remembered desktop requires a new approval`() {
        val result = readiness(
            endpoint = true,
            certificate = true,
            remembered = true,
        )

        assertEquals(CompanionLinkJourneyState.REAUTHORIZE, result.state)
        assertEquals(60, result.progressPercent)
        assertEquals("ENTER NEW LINK CODE", result.nextAction)
        assertEquals(CompanionLinkStepState.ACTIVE, result.steps[3].state)
    }

    @Test
    fun `new desktop identity must be confirmed before approval`() {
        val result = readiness(endpoint = true, certificate = true)

        assertEquals(CompanionLinkJourneyState.CONFIRM_IDENTITY, result.state)
        assertEquals(40, result.progressPercent)
        assertEquals("REVIEW SAFETY CODE", result.nextAction)
        assertEquals(CompanionLinkStepState.ACTIVE, result.steps[2].state)
        assertFalse(result.steps[3].state == CompanionLinkStepState.COMPLETE)
    }

    @Test
    fun `confirmed identity advances to code entry`() {
        val result = readiness(endpoint = true, certificate = true, safety = true)

        assertEquals(CompanionLinkJourneyState.ENTER_CODE, result.state)
        assertEquals(60, result.progressPercent)
        assertEquals("ENTER LINK CODE", result.nextAction)
    }

    @Test
    fun `usb does not masquerade as encrypted Companion Link`() {
        val result = readiness(localNetwork = false, usb = true)

        assertEquals(CompanionLinkJourneyState.USB_ONLY, result.state)
        assertEquals(20, result.progressPercent)
        assertEquals("NEEDS WI-FI", result.steps[1].status)
        assertTrue(result.detail.contains("Link not paired", ignoreCase = true))
    }

    @Test
    fun `discovery and sync in flight are explicit`() {
        assertEquals(
            CompanionLinkJourneyState.DISCOVERING,
            readiness(discovering = true).state,
        )
        assertEquals(
            CompanionLinkJourneyState.SYNCING,
            readiness(
                endpoint = true,
                certificate = true,
                remembered = true,
                secure = true,
                syncing = true,
            ).state,
        )
    }

    @Test
    fun `future timestamp cannot create fresh sync`() {
        val result = readiness(
            endpoint = true,
            certificate = true,
            remembered = true,
            secure = true,
            lastSync = now + 1L,
        )

        assertEquals(CompanionLinkJourneyState.STALE, result.state)
        assertEquals("No verified two-way sync yet", result.lastSyncLabel)
    }
}
