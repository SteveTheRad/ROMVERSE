package com.radforge.romverse.companion

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class DesktopLiveConsoleStatusTest {
    private fun payload(): JSONObject = JSONObject()
        .put("live_console_integrity", "trusted")
        .put("nexus_status", "needs-evidence")
        .put("nexus_objective", "flash-device")
        .put("nexus_current_stage", "Research")
        .put("nexus_research_count", 2)
        .put("guardian_review_state", "blocked")
        .put("live_console_execution_authority", "none")
        .put("raw_terminal_included", false)
        .put(
            "live_console_events",
            JSONArray().put(
                JSONObject()
                    .put("event_id", "a".repeat(32))
                    .put("updated_at", "2026-08-30T01:00:00+00:00")
                    .put("source", "ROMVERSE Nexus")
                    .put("stage", "pathfinder-route")
                    .put("title", "Nexus Plan updated")
                    .put("summary", "A real route was generated.")
                    .put("explanation", "Current evidence was used.")
                    .put("next_action", "Resolve research requirements.")
                    .put("state", "attention")
                    .put("progress_percent", 100)
                    .put("confidence", "unconfirmed")
                    .put("guardian_protected", true),
            ),
        )

    @Test
    fun parsesBoundedGenuineLiveConsoleStatus() {
        val status = DesktopLiveConsoleStatus.parse(5, payload())

        requireNotNull(status)
        assertEquals("Research", status.nexusCurrentStage)
        assertEquals(2, status.nexusResearchCount)
        assertEquals(1, status.events.size)
        assertEquals("Nexus Plan updated", status.events.first().title)
        assertEquals("ATTENTION", status.events.first().stateLabel)
        assertFalse(status.rawTerminalIncluded)
    }

    @Test
    fun rejectsOlderSchemaExecutionAuthorityAndRawTerminalClaims() {
        assertNull(DesktopLiveConsoleStatus.parse(4, payload()))
        assertNull(
            DesktopLiveConsoleStatus.parse(
                5,
                JSONObject(payload().toString()).put("live_console_execution_authority", "flash"),
            ),
        )
        assertNull(
            DesktopLiveConsoleStatus.parse(
                5,
                JSONObject(payload().toString()).put("raw_terminal_included", true),
            ),
        )
        assertTrue(DesktopLiveConsoleStatus.parse(5, payload())?.events?.first()?.guardianProtected == true)
    }

    @Test
    fun parsesLinkV6PrivacyFilteredRawTerminalRecords() {
        val v6 = JSONObject(payload().toString())
            .put("raw_terminal_included", true)
            .put("raw_terminal_integrity", "verified-local-feed")
            .put(
                "raw_terminal_records",
                JSONArray().put(
                    JSONObject()
                        .put("record_id", "c".repeat(32))
                        .put("captured_at", "2026-08-30T02:00:00+00:00")
                        .put("probe_id", "verified-boot-state")
                        .put("title", "Verified Boot state")
                        .put("lines", JSONArray().put("green"))
                        .put("success", true)
                        .put("record_digest", "d".repeat(64)),
                ),
            )

        val status = DesktopLiveConsoleStatus.parse(6, v6)

        requireNotNull(status)
        assertTrue(status.rawTerminalIncluded)
        assertEquals("verified-local-feed", status.rawTerminalIntegrity)
        assertEquals("verified-boot-state", status.rawTerminalRecords.first().probeId)
        assertEquals(listOf("green"), status.rawTerminalRecords.first().lines)
        assertEquals("none", status.executionAuthority)
    }

    @Test
    fun rejectsLinkV6UnapprovedOrUnmarkedRawTerminalRecords() {
        val unmarked = JSONObject(payload().toString())
            .put("raw_terminal_integrity", "verified-local-feed")
            .put(
                "raw_terminal_records",
                JSONArray().put(
                    JSONObject()
                        .put("record_id", "e".repeat(32))
                        .put("captured_at", "2026-08-30T02:00:00+00:00")
                        .put("probe_id", "adb-devices")
                        .put("title", "ADB devices")
                        .put("lines", JSONArray().put("private serial"))
                        .put("success", true)
                        .put("record_digest", "f".repeat(64)),
                ),
            )
        assertNull(DesktopLiveConsoleStatus.parse(6, unmarked))
    }
}
