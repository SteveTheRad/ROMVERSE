package com.radforge.romverse.companion

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class LifelinePlanTest {
    @Test
    fun findingsProduceSpecificBeginnerCheckpoints() {
        val checkpoints = LifelinePlanBuilder.checkpoints(
            listOf("LOW BATTERY", "STORAGE CRITICAL", "NETWORK NOT VALIDATED"),
        )

        assertTrue(checkpoints.any { "above 40%" in it })
        assertTrue(checkpoints.any { "10% free" in it })
        assertTrue(checkpoints.any { "validated internet" in it })
        assertTrue(checkpoints.last().contains("fresh read-only scan"))
    }

    @Test
    fun healthyBaselineStillHasSafeBoundedPlan() {
        val checkpoints = LifelinePlanBuilder.checkpoints(listOf("ALL CLEAR"))

        assertEquals(4, checkpoints.size)
        assertTrue(checkpoints.first().startsWith("Back up"))
        assertTrue(checkpoints.any { "healthy baseline" in it })
        assertTrue(checkpoints.size <= 12)
    }

    @Test
    fun repeatedFindingsDoNotDuplicateSteps() {
        val checkpoints = LifelinePlanBuilder.checkpoints(
            listOf("STORAGE CRITICAL", "STORAGE PRESSURE", "STORAGE CRITICAL"),
        )

        assertEquals(1, checkpoints.count { "10% free" in it })
    }
}
