package com.radforge.romverse.companion

import android.content.Context
import android.graphics.Rect
import android.os.Build
import android.util.AttributeSet
import android.view.HapticFeedbackConstants
import android.view.MotionEvent
import android.view.ViewConfiguration
import androidx.core.view.GravityCompat
import androidx.drawerlayout.widget.DrawerLayout
import kotlin.math.min
import kotlin.math.roundToInt

/** DrawerLayout with a deterministic, scroll-safe ROMVERSE left-edge opening gesture. */
internal class RomverseDrawerLayout @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
) : DrawerLayout(context, attrs) {
    private val density = resources.displayMetrics.density
    private val edgeWidthPx = dp(28).toFloat()
    private val tracker = CompanionEdgeSwipeTracker(
        edgeWidthPx = edgeWidthPx,
        touchSlopPx = ViewConfiguration.get(context).scaledTouchSlop.toFloat(),
        openDistancePx = dp(56).toFloat(),
    )
    private var consumingEdgeGesture = false

    override fun dispatchTouchEvent(event: MotionEvent): Boolean {
        if (consumingEdgeGesture) {
            if (event.actionMasked == MotionEvent.ACTION_UP ||
                event.actionMasked == MotionEvent.ACTION_CANCEL
            ) {
                consumingEdgeGesture = false
                tracker.reset()
            }
            return true
        }
        if (isDrawerVisible(GravityCompat.START)) {
            tracker.reset()
            return super.dispatchTouchEvent(event)
        }
        val decision = when (event.actionMasked) {
            MotionEvent.ACTION_DOWN -> tracker.begin(event.x, event.y, false)
            MotionEvent.ACTION_MOVE -> tracker.move(event.x, event.y, event.pointerCount)
            MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> tracker.end()
            MotionEvent.ACTION_POINTER_DOWN -> tracker.move(event.x, event.y, event.pointerCount)
            else -> EdgeSwipeDecision.IGNORED
        }
        if (decision == EdgeSwipeDecision.OPEN) {
            val cancel = MotionEvent.obtain(event).apply { action = MotionEvent.ACTION_CANCEL }
            try {
                super.dispatchTouchEvent(cancel)
            } finally {
                cancel.recycle()
            }
            consumingEdgeGesture = true
            performHapticFeedback(HapticFeedbackConstants.CONTEXT_CLICK)
            openDrawer(GravityCompat.START, true)
            return true
        }
        return super.dispatchTouchEvent(event)
    }

    override fun onSizeChanged(width: Int, height: Int, oldWidth: Int, oldHeight: Int) {
        super.onSizeChanged(width, height, oldWidth, oldHeight)
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.Q || width <= 0 || height <= 0) return
        // Android limits each edge's exclusion height. A centered 200dp zone keeps the
        // dedicated ROMVERSE gesture reliable without taking over the full system-back edge.
        val zoneHeight = min(height, dp(200))
        val top = ((height - zoneHeight) / 2).coerceAtLeast(0)
        systemGestureExclusionRects = listOf(Rect(0, top, edgeWidthPx.roundToInt(), top + zoneHeight))
    }

    private fun dp(value: Int): Int = (value * density).roundToInt()
}
