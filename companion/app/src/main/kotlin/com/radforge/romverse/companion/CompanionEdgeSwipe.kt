package com.radforge.romverse.companion

import kotlin.math.abs

internal enum class EdgeSwipeDecision {
    IGNORED,
    TRACKING,
    CANCELLED,
    OPEN,
}

/**
 * Small, Android-independent classifier for the Companion navigation edge gesture.
 *
 * A gesture is eligible only when it begins inside the left-edge zone. Vertical movement,
 * reverse movement, multiple pointers, and short diagonal drags never open navigation. This
 * keeps normal page scrolling and Android's other gestures independent from ROMVERSE.
 */
internal class CompanionEdgeSwipeTracker(
    private val edgeWidthPx: Float,
    private val touchSlopPx: Float,
    private val openDistancePx: Float,
    private val horizontalDominance: Float = 1.25f,
) {
    init {
        require(edgeWidthPx > 0f)
        require(touchSlopPx > 0f)
        require(openDistancePx > touchSlopPx)
        require(horizontalDominance >= 1f)
    }

    private var tracking = false
    private var startX = 0f
    private var startY = 0f

    fun begin(x: Float, y: Float, drawerAlreadyVisible: Boolean): EdgeSwipeDecision {
        reset()
        if (drawerAlreadyVisible || x < 0f || x > edgeWidthPx) return EdgeSwipeDecision.IGNORED
        tracking = true
        startX = x
        startY = y
        return EdgeSwipeDecision.TRACKING
    }

    fun move(x: Float, y: Float, pointerCount: Int = 1): EdgeSwipeDecision {
        if (!tracking) return EdgeSwipeDecision.IGNORED
        if (pointerCount != 1) return cancel()
        val deltaX = x - startX
        val deltaY = abs(y - startY)
        if (deltaX < -touchSlopPx) return cancel()
        if (deltaY > touchSlopPx && deltaY > abs(deltaX) * horizontalDominance) {
            return cancel()
        }
        if (deltaX >= openDistancePx && deltaX >= deltaY * horizontalDominance) {
            tracking = false
            return EdgeSwipeDecision.OPEN
        }
        return EdgeSwipeDecision.TRACKING
    }

    fun end(): EdgeSwipeDecision = if (tracking) cancel() else EdgeSwipeDecision.IGNORED

    fun reset() {
        tracking = false
        startX = 0f
        startY = 0f
    }

    private fun cancel(): EdgeSwipeDecision {
        reset()
        return EdgeSwipeDecision.CANCELLED
    }
}
