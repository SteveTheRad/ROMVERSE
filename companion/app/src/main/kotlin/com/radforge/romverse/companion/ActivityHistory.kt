package com.radforge.romverse.companion

data class CompanionActivityEvent(
    val eventId: String,
    val recordedAtEpochMs: Long,
    val title: String,
    val source: String = "ROMVERSE Companion",
    val outcome: String = "information",
    val dedupeKey: String = "",
) {
    init {
        require(eventId.isNotBlank() && eventId.length <= 80) { "Invalid activity identifier" }
        require(recordedAtEpochMs > 0L) { "Invalid activity timestamp" }
        require(title.isNotBlank() && title.length <= 160) { "Invalid activity title" }
        require(source == "ROMVERSE Companion") { "Invalid activity source" }
        require(outcome in setOf("information", "success", "attention")) { "Invalid activity outcome" }
        require(dedupeKey.length <= 100) { "Invalid activity dedupe key" }
    }
}

object CompanionActivityHistory {
    const val MAX_EVENTS = 100

    fun cleanTitle(value: String): String = value.replace('\u0000', ' ').trim().take(160)

    fun append(
        existing: List<CompanionActivityEvent>,
        event: CompanionActivityEvent,
        dedupeWindowMs: Long = 0L,
    ): List<CompanionActivityEvent> {
        require(existing.size <= MAX_EVENTS) { "Activity history is too large" }
        if (event.dedupeKey.isNotBlank() && dedupeWindowMs > 0L) {
            val previous = existing.firstOrNull { it.dedupeKey == event.dedupeKey }
            if (previous != null && event.recordedAtEpochMs - previous.recordedAtEpochMs < dedupeWindowMs) {
                return existing
            }
        }
        return (listOf(event) + existing).take(MAX_EVENTS)
    }
}
