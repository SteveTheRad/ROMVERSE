package com.radforge.romverse.companion

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class CompanionHealthSnapshotTest {
    private fun snapshot() = CompanionHealthSnapshot(
        capturedAtEpochMs = 1_788_000_000_000,
        manufacturer = "Xiaomi",
        model = "2509FPN0BC",
        deviceCodename = "popsicle",
        androidVersion = "17",
        sdkInt = 36,
        companionVersion = "0.1.0",
        batteryPercent = 82,
        batteryTemperatureCelsius = 31.5,
        storageUsedBytes = 100,
        storageTotalBytes = 200,
        memoryAvailableBytes = 80,
        memoryTotalBytes = 160,
        networkValidated = true,
        usbConnected = true,
        healthScore = 100,
        vitalisState = "OPTIMAL",
        vitalisEvidencePercent = 100,
        kernelRelease = "6.12.23-popsicle",
        rootSignal = "not_observed",
        rootManagerCandidate = "magisk",
        bootloaderState = "unknown",
        kernelSuSupport = "unknown",
    )

    @Test
    fun `wire contract contains health evidence but no private identifiers or authority`() {
        val payload = snapshot().asWireMap()

        assertEquals("health_and_device_safety", payload["privacy_scope"])
        assertEquals(4, payload["schema_version"])
        assertEquals(true, payload["guardian_active"])
        assertEquals(100, payload["health_score"])
        assertEquals("OPTIMAL", payload["vitalis_state"])
        assertEquals(100, payload["vitalis_evidence_percent"])
        assertEquals("6.12.23-popsicle", payload["kernel_release"])
        assertEquals("magisk", payload["root_manager_candidate"])
        listOf("serial", "imei", "accounts", "files", "packages", "command", "approval")
            .forEach { assertFalse(payload.containsKey(it)) }
    }

    @Test
    fun `invalid health ranges are rejected`() {
        val failure = runCatching { snapshot().copy(batteryPercent = 101) }
        assertTrue(failure.isFailure)
    }

    @Test
    fun `wire health cannot contradict its Vitalis evidence`() {
        assertTrue(runCatching { snapshot().copy(healthScore = 99) }.isFailure)
        assertTrue(runCatching { snapshot().copy(vitalisState = "ATTENTION") }.isFailure)
        assertTrue(runCatching { snapshot().copy(vitalisEvidencePercent = 83) }.isFailure)
    }

    @Test
    fun `missing temperature forces unconfirmed wire health`() {
        val missingTemperature = snapshot().copy(
            batteryTemperatureCelsius = null,
            healthScore = null,
            vitalisState = "UNCONFIRMED",
            vitalisEvidencePercent = 83,
        )

        assertEquals(null, missingTemperature.healthScore)
        assertEquals("UNCONFIRMED", missingTemperature.vitalisState)
    }
}
