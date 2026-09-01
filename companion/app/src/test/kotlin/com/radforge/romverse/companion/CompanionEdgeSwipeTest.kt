package com.radforge.romverse.companion

import org.junit.Assert.assertEquals
import org.junit.Test

class CompanionEdgeSwipeTest {
    private fun tracker() = CompanionEdgeSwipeTracker(
        edgeWidthPx = 28f,
        touchSlopPx = 8f,
        openDistancePx = 56f,
    )

    @Test
    fun `horizontal right swipe from left edge opens navigation`() {
        val gesture = tracker()

        assertEquals(EdgeSwipeDecision.TRACKING, gesture.begin(8f, 400f, false))
        assertEquals(EdgeSwipeDecision.TRACKING, gesture.move(34f, 405f))
        assertEquals(EdgeSwipeDecision.OPEN, gesture.move(72f, 409f))
    }

    @Test
    fun `touch outside edge never becomes a navigation gesture`() {
        val gesture = tracker()

        assertEquals(EdgeSwipeDecision.IGNORED, gesture.begin(29f, 400f, false))
        assertEquals(EdgeSwipeDecision.IGNORED, gesture.move(200f, 405f))
    }

    @Test
    fun `vertical page scroll from edge is cancelled instead of opening`() {
        val gesture = tracker()

        assertEquals(EdgeSwipeDecision.TRACKING, gesture.begin(6f, 400f, false))
        assertEquals(EdgeSwipeDecision.CANCELLED, gesture.move(18f, 460f))
        assertEquals(EdgeSwipeDecision.IGNORED, gesture.move(110f, 468f))
    }

    @Test
    fun `short or diagonal gesture does not open navigation`() {
        val gesture = tracker()

        gesture.begin(10f, 400f, false)
        assertEquals(EdgeSwipeDecision.TRACKING, gesture.move(52f, 430f))
        assertEquals(EdgeSwipeDecision.CANCELLED, gesture.end())
    }

    @Test
    fun `reverse and multi pointer gestures fail closed`() {
        val reverse = tracker()
        reverse.begin(12f, 400f, false)
        assertEquals(EdgeSwipeDecision.CANCELLED, reverse.move(0f, 400f))

        val multi = tracker()
        multi.begin(12f, 400f, false)
        assertEquals(EdgeSwipeDecision.CANCELLED, multi.move(44f, 404f, pointerCount = 2))
    }

    @Test
    fun `open drawer never starts another edge gesture`() {
        val gesture = tracker()

        assertEquals(EdgeSwipeDecision.IGNORED, gesture.begin(4f, 400f, true))
    }
}
