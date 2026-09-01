package com.radforge.romverse.companion

import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test

class CompanionPersonalizationTest {
    @Test
    fun `display name is trimmed and whitespace is bounded`() {
        assertEquals("Nova Builder", CompanionPersonalization.validateDisplayName("  Nova\n Builder  "))
    }

    @Test
    fun `missing or unsafe persisted names use the public default`() {
        assertEquals("Explorer", CompanionPersonalization.displayNameOrDefault(null))
        assertEquals("Explorer", CompanionPersonalization.displayNameOrDefault("bad\u0000name"))
    }

    @Test
    fun `overlong names are rejected before settings are saved`() {
        assertThrows(IllegalArgumentException::class.java) {
            CompanionPersonalization.validateDisplayName("x".repeat(41))
        }
    }
}
