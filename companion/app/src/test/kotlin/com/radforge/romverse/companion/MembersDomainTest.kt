package com.radforge.romverse.companion

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test

class MembersDomainTest {
    @Test
    fun `configuration rejects insecure and local issuers`() {
        listOf(
            "http://members.example.test",
            "https://localhost:8443",
            "https://127.0.0.1",
            "https://192.168.1.2",
            "https://user:password@members.example.test",
        ).forEach { issuer ->
            assertThrows(IllegalArgumentException::class.java) {
                CompanionMembersConfig(issuer, "companion-client").validated()
            }
        }
    }

    @Test
    fun `server profile remains sole membership authority`() {
        val profile = CompanionMemberProfile.parse(
            JSONObject()
                .put("sub", "member-42")
                .put("name", "Nova Builder")
                .put("email", "nova@example.test")
                .put(
                    "romverse_membership",
                    JSONObject()
                        .put("plan", "ROMVERSE One")
                        .put("status", "trial")
                        .put("trial_ends_at", "2026-09-05T00:00:00Z"),
                ),
        )

        assertEquals("Nova Builder", profile.displayName)
        assertEquals("ROMVERSE One", profile.plan)
        assertEquals("trial", profile.status)
    }

    @Test
    fun `device authorization enforces bounded expiry and https verification`() {
        val authorization = CompanionDeviceAuthorization.parse(
            JSONObject()
                .put("device_code", "secret-device-code")
                .put("user_code", "ROM-VERSE")
                .put("verification_uri", "https://members.example.test/activate")
                .put("expires_in", 600)
                .put("interval", 5),
            1_000L,
        )

        assertEquals("ROM-VERSE", authorization.userCode)
        assertEquals(601_000L, authorization.expiresAtEpochMs)
        assertEquals(5, authorization.intervalSeconds)
    }
}
