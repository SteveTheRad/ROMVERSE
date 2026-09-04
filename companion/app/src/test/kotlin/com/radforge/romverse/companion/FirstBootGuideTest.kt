package com.radforge.romverse.companion

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class FirstBootGuideTest {
    private val now = 1_800_000_000_000L

    @Test
    fun recordsReviewedStepsWithoutClaimingSubsystemSuccess() {
        val reviewed = FirstBootGuide.toggle(
            FirstBootGuideState(),
            "stable_boot",
            true,
            now,
        )

        assertEquals(setOf("stable_boot"), reviewed.reviewedStepIds)
        assertEquals(12, reviewed.progressPercent)
        assertFalse(reviewed.complete)
        val encoded = FirstBootGuide.encode(reviewed)
        assertFalse(encoded.contains("passed", ignoreCase = true))
        assertEquals(reviewed, FirstBootGuide.decode(encoded, now + 1L))
    }

    @Test
    fun completesOnlyAfterEveryOfflineStepWasReviewed() {
        val state = FirstBootGuide.steps.fold(FirstBootGuideState()) { current, step ->
            FirstBootGuide.toggle(current, step.id, true, now)
        }

        assertEquals(100, state.progressPercent)
        assertTrue(state.complete)
    }

    @Test
    fun rejectsTamperingUnknownStepsAndFutureState() {
        val reviewed = FirstBootGuide.toggle(FirstBootGuideState(), "stable_boot", true, now)
        val encoded = FirstBootGuide.encode(reviewed)
        val tampered = JSONObject(encoded).apply {
            getJSONArray("reviewed_step_ids").put("flash_succeeded")
        }.toString()

        assertEquals(FirstBootGuideState(), FirstBootGuide.decode(tampered, now + 1L))
        assertEquals(FirstBootGuideState(), FirstBootGuide.decode(encoded, now - 300_001L))
        assertEquals(
            FirstBootGuideState(),
            FirstBootGuide.decode(JSONObject(encoded).put("schema_version", "1").toString(), now),
        )
    }
}
