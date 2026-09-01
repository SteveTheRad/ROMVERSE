package com.radforge.romverse.companion

internal enum class CompanionHomeHeroKind {
    GUARDIAN,
    MISSION,
    VITALIS,
    ROM_HEALTH,
}

/** Deterministic priority for the Companion three-second rule. */
internal object CompanionHomeHeroPolicy {
    fun choose(
        guardianBlocked: Boolean,
        missionRunning: Boolean,
        healthAttention: Boolean,
    ): CompanionHomeHeroKind = when {
        guardianBlocked -> CompanionHomeHeroKind.GUARDIAN
        missionRunning -> CompanionHomeHeroKind.MISSION
        healthAttention -> CompanionHomeHeroKind.VITALIS
        else -> CompanionHomeHeroKind.ROM_HEALTH
    }
}
