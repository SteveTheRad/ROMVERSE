package com.radforge.romverse.companion

/**
 * Local presentation privacy only. It never changes ROMVERSE Link, Guardian, or device authority.
 * A temporary reveal exposes the UI for the current foreground session while capture protection
 * remains active. Leaving the app closes that reveal.
 */
internal data class CompanionPrivacyCurtainState(
    val enabled: Boolean,
    val temporarilyRevealed: Boolean = false,
) {
    val obscuresContent: Boolean
        get() = enabled && !temporarilyRevealed

    val blocksScreenCapture: Boolean
        get() = enabled

    fun revealForSession(): CompanionPrivacyCurtainState =
        if (enabled) copy(temporarilyRevealed = true) else this

    fun onBackgrounded(): CompanionPrivacyCurtainState =
        copy(temporarilyRevealed = false)
}
