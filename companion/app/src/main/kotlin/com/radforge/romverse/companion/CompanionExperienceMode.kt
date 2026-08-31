package com.radforge.romverse.companion

/** Local presentation density. Neither choice grants device-write authority. */
internal enum class CompanionExperienceMode(val persistedValue: String) {
    GUIDED("guided"),
    EXPERT("expert"),
    ;

    companion object {
        fun parse(value: String?): CompanionExperienceMode =
            entries.firstOrNull { it.persistedValue == value } ?: GUIDED
    }
}

internal object CompanionExperiencePolicy {
    const val GUIDED_CAPABILITY_PREVIEW_COUNT = 4

    fun initialCapabilityCount(
        mode: CompanionExperienceMode,
        available: Int,
    ): Int = when (mode) {
        CompanionExperienceMode.GUIDED ->
            available.coerceAtMost(GUIDED_CAPABILITY_PREVIEW_COUNT).coerceAtLeast(0)
        CompanionExperienceMode.EXPERT -> available.coerceAtLeast(0)
    }

    /**
     * Technical evidence is presentation-only. Guided mode folds it behind an explicit action;
     * Expert mode opens it immediately. Safety findings, blockers, and next actions must never be
     * placed inside a technical-only container.
     */
    fun technicalEvidenceVisible(mode: CompanionExperienceMode): Boolean =
        mode == CompanionExperienceMode.EXPERT
}
