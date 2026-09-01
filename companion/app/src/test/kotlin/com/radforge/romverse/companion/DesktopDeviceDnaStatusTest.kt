package com.radforge.romverse.companion

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class DesktopDeviceDnaStatusTest {
    private fun payload(): JSONObject = JSONObject()
        .put("device_dna_state", "needs-attention")
        .put("device_dna_project", "My ROM")
        .put("device_dna_profile_ref", "a".repeat(16))
        .put("device_dna_warning_count", 2)
        .put("device_dna_execution_authority", "none")
        .put("device_dna_bootloader_relock", "never")
        .put(
            "device_dna_capabilities",
            JSONArray()
                .put(
                    JSONObject()
                        .put("capability_id", "source_adapter")
                        .put("label", "Automatic source adapter")
                        .put("state", "SUPPORTED")
                        .put("detail", "Payload Atlas selected from bounded evidence."),
                )
                .put(
                    JSONObject()
                        .put("capability_id", "guardian_flash")
                        .put("label", "Guardian flash")
                        .put("state", "UNCONFIRMED")
                        .put("detail", "More exact recovery evidence is required."),
                )
                .put(
                    JSONObject()
                        .put("capability_id", "bootloader_relock")
                        .put("label", "Bootloader relocking")
                        .put("state", "UNSUPPORTED")
                        .put("detail", "ROMVERSE never permits bootloader relocking."),
                ),
        )

    @Test
    fun parsesBoundedReadOnlyCapabilityMap() {
        val status = DesktopDeviceDnaStatus.parse(6, payload())

        requireNotNull(status)
        assertEquals("My ROM", status.project)
        assertEquals(3, status.capabilities.size)
        assertEquals(1, status.attentionCount)
        assertEquals("EVIDENCE NEEDS ATTENTION", status.headline)
        assertEquals("none", status.executionAuthority)
        assertEquals("never", status.bootloaderRelock)
        val report = status.privacySafeReport()
        assertTrue(report.contains("Profile reference: ${"a".repeat(16)}"))
        assertTrue(report.contains("UNCONFIRMED • Guardian flash"))
        assertTrue(report.contains("Execution authority: NONE"))
        assertTrue(report.contains("Bootloader relock: NEVER"))
        assertTrue(report.contains("no source paths, full hashes, commands, approvals"))
    }

    @Test
    fun rejectsWrongSchemaAuthorityRelockAndMalformedCapabilities() {
        assertNull(DesktopDeviceDnaStatus.parse(5, payload()))
        assertNull(
            DesktopDeviceDnaStatus.parse(
                6,
                JSONObject(payload().toString()).put("device_dna_execution_authority", "flash"),
            ),
        )
        assertNull(
            DesktopDeviceDnaStatus.parse(
                6,
                JSONObject(payload().toString()).put("device_dna_bootloader_relock", "allowed"),
            ),
        )
        val malformed = JSONObject(payload().toString())
        malformed.getJSONArray("device_dna_capabilities")
            .getJSONObject(0)
            .put("state", "READY")
        assertNull(DesktopDeviceDnaStatus.parse(6, malformed))
    }

    @Test
    fun unavailableProfileIsNullOnlyWhenItCarriesNoEvidence() {
        val empty = JSONObject()
            .put("device_dna_state", "unavailable")
            .put("device_dna_project", "")
            .put("device_dna_profile_ref", "")
            .put("device_dna_warning_count", 0)
            .put("device_dna_execution_authority", "none")
            .put("device_dna_bootloader_relock", "never")
            .put("device_dna_capabilities", JSONArray())
        assertNull(DesktopDeviceDnaStatus.parse(6, empty))
        assertNull(
            DesktopDeviceDnaStatus.parse(
                6,
                JSONObject(empty.toString()).put("device_dna_project", "Invented"),
            ),
        )
        assertTrue(DesktopDeviceDnaCapability.STATES.contains("UNCONFIRMED"))
    }
}
