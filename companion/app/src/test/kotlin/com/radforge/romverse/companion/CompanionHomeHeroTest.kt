package com.radforge.romverse.companion

import org.junit.Assert.assertEquals
import org.junit.Test

class CompanionHomeHeroTest {
    @Test
    fun guardianAttentionOutranksEveryOtherHomeState() {
        assertEquals(
            CompanionHomeHeroKind.GUARDIAN,
            CompanionHomeHeroPolicy.choose(
                guardianBlocked = true,
                missionRunning = true,
                healthAttention = true,
            ),
        )
    }

    @Test
    fun missionOutranksRoutineVitalisAttention() {
        assertEquals(
            CompanionHomeHeroKind.MISSION,
            CompanionHomeHeroPolicy.choose(
                guardianBlocked = false,
                missionRunning = true,
                healthAttention = true,
            ),
        )
    }

    @Test
    fun attentionAndHealthyStatesRemainDistinct() {
        assertEquals(
            CompanionHomeHeroKind.VITALIS,
            CompanionHomeHeroPolicy.choose(false, false, true),
        )
        assertEquals(
            CompanionHomeHeroKind.ROM_HEALTH,
            CompanionHomeHeroPolicy.choose(false, false, false),
        )
    }
}
