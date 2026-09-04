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
        assertEquals(5, payload["schema_version"])
        assertEquals(true, payload["guardian_active"])
        assertEquals(100, payload["health_score"])
        assertEquals("OPTIMAL", payload["vitalis_state"])
        assertEquals(100, payload["vitalis_evidence_percent"])
        assertEquals("6.12.23-popsicle", payload["kernel_release"])
        assertEquals("magisk", payload["root_manager_candidate"])
        assertEquals("unconfirmed", payload["user_data_backup_state"])
        assertEquals("user_attestation_only", payload["backup_confirmation_scope"])
        assertEquals("none", payload["backup_execution_authority"])
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

    @Test
    fun `backup confirmation is explicit user evidence and never authority`() {
        val confirmed = snapshot().copy(
            userDataBackupState = "confirmed_by_user",
            userDataBackupConfirmedAtEpochMs = 1_787_999_000_000,
        )

        assertEquals("confirmed_by_user", confirmed.asWireMap()["user_data_backup_state"])
        assertEquals(1_787_999_000_000, confirmed.asWireMap()["user_data_backup_confirmed_at_epoch_ms"])
        assertEquals("none", confirmed.asWireMap()["backup_execution_authority"])
        assertTrue(
            runCatching {
                snapshot().copy(
                    userDataBackupState = "confirmed_by_user",
                    userDataBackupConfirmedAtEpochMs = null,
                )
            }.isFailure,
        )
    }
}
