package com.radforge.romverse.companion

internal object CompanionPersonalization {
    const val DEFAULT_DISPLAY_NAME = "Explorer"
    const val MAX_DISPLAY_NAME_LENGTH = 40

    fun validateDisplayName(raw: String): String {
        val normalized = raw.trim().replace(Regex("\\s+"), " ")
        require(normalized.isNotEmpty()) { "Enter the name Companion should use." }
        require(normalized.length <= MAX_DISPLAY_NAME_LENGTH) {
            "The Companion display name is too long."
        }
        require(normalized.none(Char::isISOControl)) {
            "The Companion display name contains unsupported control characters."
        }
        return normalized
    }

    fun displayNameOrDefault(raw: String?): String = runCatching {
        validateDisplayName(raw.orEmpty())
    }.getOrDefault(DEFAULT_DISPLAY_NAME)
}
