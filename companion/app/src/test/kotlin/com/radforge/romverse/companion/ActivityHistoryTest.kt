package com.radforge.romverse.companion

import org.junit.Assert.assertEquals
import org.junit.Assert.assertSame
import org.junit.Test

class ActivityHistoryTest {
    private fun event(id: String, time: Long, key: String = "") = CompanionActivityEvent(
        id,
        time,
        "Health snapshot refreshed",
        dedupeKey = key,
    )

    @Test
    fun duplicateInsideWindowIsNotAdded() {
        val existing = listOf(event("one", 1_000, "health"))
        val result = CompanionActivityHistory.append(existing, event("two", 2_000, "health"), 5_000)
        assertSame(existing, result)
    }

    @Test
    fun eventOutsideWindowIsAddedNewestFirst() {
        val result = CompanionActivityHistory.append(
            listOf(event("one", 1_000, "health")),
            event("two", 8_000, "health"),
            5_000,
        )
        assertEquals(listOf("two", "one"), result.map { it.eventId })
    }

    @Test
    fun titleCleaningRemovesNullAndBoundsLength() {
        val cleaned = CompanionActivityHistory.cleanTitle("  hello\u0000world ${"x".repeat(200)}  ")
        assertEquals(160, cleaned.length)
        assertEquals(false, cleaned.contains('\u0000'))
    }
}
