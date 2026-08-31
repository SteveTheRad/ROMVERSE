package com.radforge.romverse.companion

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class CompanionLayoutSpecTest {
    @Test
    fun homeAndFocusedSectionsShareOneReadableContentGrid() {
        assertEquals(20, CompanionLayoutSpec.CONTENT_HORIZONTAL_DP)
        assertEquals(320, CompanionLayoutSpec.usableContentWidth(360))
        assertEquals(560, CompanionLayoutSpec.usableContentWidth(600))
        assertEquals(12, CompanionLayoutSpec.CARD_GAP_DP)
    }

    @Test
    fun controlsAndAboutBrandingKeepTouchFriendlyBounds() {
        assertTrue(CompanionLayoutSpec.CONTROL_MIN_HEIGHT_DP >= 48)
        assertTrue(CompanionLayoutSpec.SOCIAL_ACTION_MIN_HEIGHT_DP >= 56)
        assertTrue(CompanionLayoutSpec.ABOUT_MARK_SIZE_DP in 144..200)
        assertEquals(0, CompanionLayoutSpec.usableContentWidth(20))
    }
}
