package com.radforge.romverse.companion

/** Shared density-independent layout contract for the programmatic Companion UI. */
object CompanionLayoutSpec {
    const val CONTENT_HORIZONTAL_DP = 20
    const val CONTENT_TOP_DP = 18
    const val CONTENT_BOTTOM_DP = 28
    const val CARD_HORIZONTAL_PADDING_DP = 16
    const val CARD_VERTICAL_PADDING_DP = 15
    const val CARD_GAP_DP = 12
    const val CONTROL_MIN_HEIGHT_DP = 52
    const val SOCIAL_ACTION_MIN_HEIGHT_DP = 64
    const val ABOUT_MARK_SIZE_DP = 176
    const val ABOUT_COMPANY_LOGO_HEIGHT_DP = 160

    fun usableContentWidth(screenWidthDp: Int): Int =
        (screenWidthDp - CONTENT_HORIZONTAL_DP * 2).coerceAtLeast(0)
}
