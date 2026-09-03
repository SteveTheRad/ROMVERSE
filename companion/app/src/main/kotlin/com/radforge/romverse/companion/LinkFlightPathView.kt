package com.radforge.romverse.companion

import android.animation.ValueAnimator
import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.util.AttributeSet
import android.util.TypedValue
import android.view.View
import androidx.core.graphics.toColorInt
import kotlin.math.sin

/** Compact evidence visualization; every node is derived from real Link state. */
internal class LinkFlightPathView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
) : View(context, attrs) {
    private val density = resources.displayMetrics.density
    private val linePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeCap = Paint.Cap.ROUND
        strokeWidth = 2f * density
    }
    private val nodePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.FILL
    }
    private val labelPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.WHITE
        textAlign = Paint.Align.CENTER
        textSize = TypedValue.applyDimension(
            TypedValue.COMPLEX_UNIT_SP,
            9f,
            resources.displayMetrics,
        )
        typeface = android.graphics.Typeface.DEFAULT_BOLD
    }
    private val statusPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = "#8FA6C9".toColorInt()
        textAlign = Paint.Align.CENTER
        textSize = TypedValue.applyDimension(
            TypedValue.COMPLEX_UNIT_SP,
            8f,
            resources.displayMetrics,
        )
    }
    private var steps = emptyList<CompanionLinkStep>()
    private var motionEnabled = true
    private var active = false

    fun render(readiness: CompanionLinkReadiness, allowMotion: Boolean) {
        steps = readiness.steps
        motionEnabled = allowMotion
        contentDescription = buildString {
            append("ROMVERSE Link Flight Path. ")
            append(readiness.headline)
            append(". ")
            append(steps.joinToString(". ") { "${it.label}: ${it.status}" })
        }
        invalidate()
    }

    override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
        val preferredHeight = (104f * density).toInt()
        setMeasuredDimension(
            resolveSize(suggestedMinimumWidth, widthMeasureSpec),
            resolveSize(preferredHeight, heightMeasureSpec),
        )
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        if (steps.size != 5 || width <= 0 || height <= 0) return
        val inset = 18f * density
        val centerY = 34f * density
        val spacing = (width - inset * 2f) / (steps.size - 1)
        val now = android.os.SystemClock.uptimeMillis()
        for (index in 0 until steps.lastIndex) {
            val startX = inset + spacing * index
            val endX = inset + spacing * (index + 1)
            linePaint.color = if (steps[index + 1].state == CompanionLinkStepState.COMPLETE) {
                "#53E6A2".toColorInt()
            } else {
                "#2B3958".toColorInt()
            }
            canvas.drawLine(startX, centerY, endX, centerY, linePaint)
        }
        steps.forEachIndexed { index, step ->
            val x = inset + spacing * index
            val color = when (step.state) {
                CompanionLinkStepState.COMPLETE -> "#53E6A2".toColorInt()
                CompanionLinkStepState.ACTIVE -> "#55DFF4".toColorInt()
                CompanionLinkStepState.ATTENTION -> "#FFB454".toColorInt()
                CompanionLinkStepState.WAITING -> "#52617E".toColorInt()
            }
            if (step.state == CompanionLinkStepState.ACTIVE) {
                val pulse = if (motionEnabled && ValueAnimator.areAnimatorsEnabled()) {
                    1f + 0.18f * sin(now / 280f)
                } else {
                    1f
                }
                nodePaint.color = color
                nodePaint.alpha = 45
                canvas.drawCircle(x, centerY, 15f * density * pulse, nodePaint)
                nodePaint.alpha = 255
            }
            nodePaint.color = color
            canvas.drawCircle(x, centerY, 7f * density, nodePaint)
            if (step.state == CompanionLinkStepState.COMPLETE) {
                nodePaint.color = "#07161A".toColorInt()
                canvas.drawCircle(x, centerY, 2.5f * density, nodePaint)
            }
            canvas.drawText(step.label, x, centerY + 27f * density, labelPaint)
            canvas.drawText(step.status, x, centerY + 42f * density, statusPaint)
        }
        if (active && motionEnabled && steps.any { it.state == CompanionLinkStepState.ACTIVE }) {
            postInvalidateDelayed(50L)
        }
    }

    override fun onAttachedToWindow() {
        super.onAttachedToWindow()
        active = true
        invalidate()
    }

    override fun onDetachedFromWindow() {
        active = false
        super.onDetachedFromWindow()
    }

    override fun onWindowVisibilityChanged(visibility: Int) {
        super.onWindowVisibilityChanged(visibility)
        active = visibility == VISIBLE
        if (active) invalidate()
    }
}
