package com.radforge.romverse.companion

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class LastKnownDeviceDnaTest {
    private val capturedAt = 1_800_000_000_000L
    private val status = DesktopDeviceDnaStatus(
        state = "ready",
        project = "HyperOS 4",
        profileRef = "a".repeat(16),
        warningCount = 0,
        capabilities = listOf(
            DesktopDeviceDnaCapability(
                capabilityId = "source_adapter",
                label = "Automatic source adapter",
                state = "SUPPORTED",
                detail = "Payload Atlas selected from measured evidence.",
            ),
        ),
        executionAuthority = "none",
        bootloaderRelock = "never",
    )

    @Test
    fun preservesPrivacySafeLastKnownDnaOffline() {
        val encoded = LastKnownDeviceDnaArchive.encode(status, capturedAt)
        val restored = LastKnownDeviceDnaArchive.decode(encoded, capturedAt + 1L)

        assertEquals(status, restored?.status)
        assertEquals(capturedAt, restored?.capturedAtEpochMs)
        assertEquals(64, restored?.recordSha256?.length)
        assertEquals("none", restored?.status?.executionAuthority)
    }

    @Test
    fun rejectsTamperingAuthorityAndFutureCapture() {
        val encoded = LastKnownDeviceDnaArchive.encode(status, capturedAt)
        val tampered = JSONObject(encoded).apply {
            getJSONObject("status").put("project", "Changed")
        }.toString()
        assertNull(LastKnownDeviceDnaArchive.decode(tampered, capturedAt + 1L))

        val authority = JSONObject(encoded).apply {
            getJSONObject("status").put("execution_authority", "flash")
        }.toString()
        assertNull(LastKnownDeviceDnaArchive.decode(authority, capturedAt + 1L))
        assertNull(LastKnownDeviceDnaArchive.decode(encoded, capturedAt - 300_001L))
    }

    @Test
    fun rejectsJsonTypeConfusionBeforeTrustingTheDigest() {
        val encoded = LastKnownDeviceDnaArchive.encode(status, capturedAt)
        val stringSchema = JSONObject(encoded).put("schema_version", "1").toString()
        val stringWarnings = JSONObject(encoded).apply {
            getJSONObject("status").put("warning_count", "0")
        }.toString()

        assertNull(LastKnownDeviceDnaArchive.decode(stringSchema, capturedAt + 1L))
        assertNull(LastKnownDeviceDnaArchive.decode(stringWarnings, capturedAt + 1L))
    }
}
