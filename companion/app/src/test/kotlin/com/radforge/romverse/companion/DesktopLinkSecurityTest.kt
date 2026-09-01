package com.radforge.romverse.companion

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class DesktopLinkSecurityTest {
    @Test
    fun `fingerprints normalize without weakening validation`() {
        val compact = "0123456789abcdef".repeat(4)
        val readable = compact.chunked(4).joinToString(":").uppercase()

        assertEquals(compact, DesktopLinkSecurity.normalizeFingerprint(readable))
        assertNull(DesktopLinkSecurity.normalizeFingerprint("a".repeat(63)))
        assertNull(DesktopLinkSecurity.normalizeFingerprint("g".repeat(64)))
        assertNull(DesktopLinkSecurity.normalizeFingerprint("https://example.test"))
    }

    @Test
    fun `safety code is a stable readable prefix of the full pin`() {
        val fingerprint = "0123456789abcdef".repeat(4)

        assertEquals(
            "0123-4567-89AB-CDEF-0123-4567",
            DesktopLinkSecurity.safetyCode(fingerprint),
        )
        assertNull(DesktopLinkSecurity.safetyCode("invalid"))
    }

    @Test
    fun `legacy cleartext and expired sessions must pair again`() {
        val fingerprint = "0123456789abcdef".repeat(4)

        assertEquals(
            true,
            DesktopLinkSecurity.isCurrentSession(3, fingerprint, 20_000L, 10_000L),
        )
        assertEquals(
            false,
            DesktopLinkSecurity.isCurrentSession(2, fingerprint, 20_000L, 10_000L),
        )
        assertEquals(
            false,
            DesktopLinkSecurity.isCurrentSession(3, fingerprint, 10_000L, 10_000L),
        )
    }

    @Test
    fun `remembered desktop requires current protocol valid pin and bounded host`() {
        val fingerprint = "0123456789abcdef".repeat(4)

        assertEquals(true, DesktopLinkSecurity.isRememberedDesktop(3, fingerprint, "192.168.1.5:8765"))
        assertEquals(false, DesktopLinkSecurity.isRememberedDesktop(2, fingerprint, "192.168.1.5:8765"))
        assertEquals(false, DesktopLinkSecurity.isRememberedDesktop(3, "invalid", "192.168.1.5:8765"))
        assertEquals(false, DesktopLinkSecurity.isRememberedDesktop(3, fingerprint, "host/path:8765"))
        assertEquals(false, DesktopLinkSecurity.isRememberedDesktop(3, fingerprint, "192.168.1.5"))
        assertEquals(false, DesktopLinkSecurity.isRememberedDesktop(3, fingerprint, "192.168.1.5:0"))
        assertEquals(false, DesktopLinkSecurity.isRememberedDesktop(3, fingerprint, "192.168.1.5:65536"))
        assertEquals(true, DesktopLinkSecurity.isRememberedDesktop(3, fingerprint, "[fd00::17]:8765"))
    }

    @Test
    fun `rediscovery cannot replace a remembered desktop identity`() {
        val remembered = "0123456789abcdef".repeat(4)
        val different = "fedcba9876543210".repeat(4)

        assertEquals(true, DesktopLinkSecurity.acceptsDiscoveredIdentity(null, different))
        assertEquals(true, DesktopLinkSecurity.acceptsDiscoveredIdentity(remembered, remembered))
        assertEquals(false, DesktopLinkSecurity.acceptsDiscoveredIdentity(remembered, different))
        assertEquals(false, DesktopLinkSecurity.acceptsDiscoveredIdentity(remembered, "invalid"))
    }

    @Test
    fun `reconnect retry delay is bounded`() {
        assertEquals(2_000L, DesktopLinkSecurity.retryDelayMillis(0))
        assertEquals(10_000L, DesktopLinkSecurity.retryDelayMillis(2))
        assertEquals(60_000L, DesktopLinkSecurity.retryDelayMillis(50))
    }

    @Test
    fun `trusted rediscovery requires the saved pin valid endpoint and live session proof`() {
        val remembered = "0123456789abcdef".repeat(4)
        val different = "fedcba9876543210".repeat(4)

        assertEquals(
            "192.168.1.17:8765",
            DesktopLinkSecurity.trustedRediscoveredEndpoint(
                3,
                remembered,
                remembered,
                "192.168.1.17:8765",
                authenticatedSessionProof = true,
            ),
        )
        assertNull(
            DesktopLinkSecurity.trustedRediscoveredEndpoint(
                3,
                remembered,
                different,
                "192.168.1.17:8765",
                authenticatedSessionProof = true,
            ),
        )
        assertNull(
            DesktopLinkSecurity.trustedRediscoveredEndpoint(
                3,
                remembered,
                remembered,
                "192.168.1.17:8765",
                authenticatedSessionProof = false,
            ),
        )
        assertNull(
            DesktopLinkSecurity.trustedRediscoveredEndpoint(
                3,
                remembered,
                remembered,
                "attacker.test/path:8765",
                authenticatedSessionProof = true,
            ),
        )
    }
}
