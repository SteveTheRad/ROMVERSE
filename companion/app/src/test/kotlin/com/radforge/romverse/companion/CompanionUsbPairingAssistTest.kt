package com.radforge.romverse.companion

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class CompanionUsbPairingAssistTest {
    private val fingerprint = "ab".repeat(32)

    @Test
    fun `exact loopback handoff is accepted and normalized`() {
        val result = CompanionUsbPairingAssistPolicy.parse(
            CompanionUsbPairingAssistPolicy.ACTION,
            " 127.0.0.1:8765 ",
            fingerprint.chunked(2).joinToString(":"),
            "123 456",
        )

        requireNotNull(result)
        assertEquals("127.0.0.1:8765", result.host)
        assertEquals(fingerprint, result.certificateSha256)
        assertEquals("123456", result.pairingCode)
    }

    @Test
    fun `untrusted or malformed handoffs fail closed`() {
        val rejected = listOf(
            CompanionUsbPairingAssistPolicy.parse("wrong.action", "127.0.0.1:8765", fingerprint, "123456"),
            CompanionUsbPairingAssistPolicy.parse(CompanionUsbPairingAssistPolicy.ACTION, "192.168.1.2:8765", fingerprint, "123456"),
            CompanionUsbPairingAssistPolicy.parse(CompanionUsbPairingAssistPolicy.ACTION, "127.0.0.1:0", fingerprint, "123456"),
            CompanionUsbPairingAssistPolicy.parse(CompanionUsbPairingAssistPolicy.ACTION, "127.0.0.1:8765", "00", "123456"),
            CompanionUsbPairingAssistPolicy.parse(CompanionUsbPairingAssistPolicy.ACTION, "127.0.0.1:8765", fingerprint, "12345x"),
        )

        assertTrue(rejected.all { it == null })
        assertNull(CompanionUsbPairingAssistPolicy.parse(null, null, null, null))
    }
}
