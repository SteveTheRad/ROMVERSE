package com.radforge.romverse.companion

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class CompanionPrivacyCurtainTest {
    @Test
    fun disabledCurtainNeitherObscuresContentNorBlocksCapture() {
        val state = CompanionPrivacyCurtainState(enabled = false)

        assertFalse(state.obscuresContent)
        assertFalse(state.blocksScreenCapture)
        assertFalse(state.revealForSession().temporarilyRevealed)
    }

    @Test
    fun enabledCurtainObscuresContentAndBlocksCapture() {
        val state = CompanionPrivacyCurtainState(enabled = true)

        assertTrue(state.obscuresContent)
        assertTrue(state.blocksScreenCapture)
    }

    @Test
    fun temporaryRevealKeepsCaptureBlockedAndBackgroundClosesReveal() {
        val revealed = CompanionPrivacyCurtainState(enabled = true).revealForSession()

        assertFalse(revealed.obscuresContent)
        assertTrue(revealed.blocksScreenCapture)
        assertTrue(revealed.temporarilyRevealed)

        val returned = revealed.onBackgrounded()
        assertTrue(returned.obscuresContent)
        assertTrue(returned.blocksScreenCapture)
        assertFalse(returned.temporarilyRevealed)
    }
}
