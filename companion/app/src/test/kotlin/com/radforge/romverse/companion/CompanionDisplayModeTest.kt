package com.radforge.romverse.companion

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class CompanionDisplayModeTest {
    @Test
    fun missingOrUnknownPreferenceFailsBackToCosmicMode() {
        assertEquals(CompanionDisplayMode.COSMIC, CompanionDisplayMode.parse(null))
        assertEquals(CompanionDisplayMode.COSMIC, CompanionDisplayMode.parse("unsupported"))
        assertEquals(CompanionDisplayMode.OLED, CompanionDisplayMode.parse("oled"))
    }

    @Test
    fun oledPaletteUsesTrueBlackPrimarySurfacesAndNoNebula() {
        val palette = CompanionDisplayPolicy.palette(CompanionDisplayMode.OLED)

        assertEquals("#000000", palette.panel)
        assertEquals("#000000", palette.sectionSurface)
        assertTrue(palette.cosmicGradient.all { it == "#000000" })
        assertEquals("#000000", palette.navigationIdle)
        assertFalse(palette.ambientNebula)
    }

    @Test
    fun cosmicPaletteRetainsBrandedDepth() {
        val palette = CompanionDisplayPolicy.palette(CompanionDisplayMode.COSMIC)

        assertTrue(palette.cosmicGradient.distinct().size > 1)
        assertTrue(palette.ambientNebula)
    }
}
