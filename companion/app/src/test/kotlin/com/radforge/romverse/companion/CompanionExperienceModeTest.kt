package com.radforge.romverse.companion

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class CompanionExperienceModeTest {
    @Test
    fun unknownOrMissingPreferenceFailsSafelyToGuidedMode() {
        assertEquals(CompanionExperienceMode.GUIDED, CompanionExperienceMode.parse(null))
        assertEquals(CompanionExperienceMode.GUIDED, CompanionExperienceMode.parse("bypass"))
        assertEquals(CompanionExperienceMode.EXPERT, CompanionExperienceMode.parse("expert"))
    }

    @Test
    fun guidedModeFoldsTechnicalCapabilityOverflowButExpertDoesNot() {
        assertEquals(
            4,
            CompanionExperiencePolicy.initialCapabilityCount(
                CompanionExperienceMode.GUIDED,
                12,
            ),
        )
        assertEquals(
            12,
            CompanionExperiencePolicy.initialCapabilityCount(
                CompanionExperienceMode.EXPERT,
                12,
            ),
        )
        assertEquals(
            2,
            CompanionExperiencePolicy.initialCapabilityCount(
                CompanionExperienceMode.GUIDED,
                2,
            ),
        )
    }

    @Test
    fun guidedModeFoldsTechnicalEvidenceButExpertOpensIt() {
        assertFalse(
            CompanionExperiencePolicy.technicalEvidenceVisible(
                CompanionExperienceMode.GUIDED,
            ),
        )
        assertTrue(
            CompanionExperiencePolicy.technicalEvidenceVisible(
                CompanionExperienceMode.EXPERT,
            ),
        )
    }
}
