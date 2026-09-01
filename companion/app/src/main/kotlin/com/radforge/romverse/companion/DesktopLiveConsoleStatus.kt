package com.radforge.romverse.companion

import org.json.JSONArray
import org.json.JSONObject
import java.time.OffsetDateTime

data class DesktopLiveConsoleEvent(
    val eventId: String,
    val updatedAt: String,
    val source: String,
    val stage: String,
    val title: String,
    val summary: String,
    val explanation: String,
    val nextAction: String,
    val state: String,
    val progressPercent: Int,
    val confidence: String,
    val guardianProtected: Boolean,
) {
    init {
        require(eventId.isNotBlank() && eventId.length <= 100 && eventId.all { it.isLetterOrDigit() || it == '-' })
        require(updatedAt.length <= 80 && runCatching { OffsetDateTime.parse(updatedAt) }.isSuccess) {
            "Live Console timestamp is invalid"
        }
        requireText(source, 80, "source")
        requireText(stage, 100, "stage")
        requireText(title, 180, "title")
        requireText(summary, 500, "summary")
        requireText(explanation, 1000, "explanation")
        requireText(nextAction, 500, "next action")
        require(state in STATES) { "Live Console state is invalid" }
        require(progressPercent in 0..100) { "Live Console progress is invalid" }
        require(confidence in CONFIDENCE) { "Live Console confidence is invalid" }
        require(guardianProtected) { "Live Console event is not Guardian protected" }
    }

    val stateLabel: String
        get() = state.replace('-', ' ').uppercase()

    companion object {
        private val STATES = setOf(
            "running",
            "succeeded",
            "failed",
            "blocked",
            "attention",
            "information",
        )
        private val CONFIDENCE = setOf(
            "verified",
            "high",
            "medium",
            "low",
            "unconfirmed",
            "not-applicable",
        )

        private fun requireText(value: String, maximum: Int, label: String) {
            require(value.isNotBlank() && value.length <= maximum && value.none(Char::isISOControl)) {
                "Live Console $label is invalid"
            }
        }
    }
}

data class DesktopRawTerminalRecord(
    val recordId: String,
    val capturedAt: String,
    val probeId: String,
    val title: String,
    val lines: List<String>,
    val success: Boolean,
    val recordDigest: String,
) {
    init {
        require(recordId.isNotBlank() && recordId.length <= 100 && recordId.all { it.isLetterOrDigit() || it == '-' })
        require(capturedAt.length <= 80 && runCatching { OffsetDateTime.parse(capturedAt) }.isSuccess)
        require(probeId in PROBES) { "Raw Terminal probe is not Link-approved" }
        require(title.isNotBlank() && title.length <= 80 && title.none(Char::isISOControl))
        require(lines.size in 1..32) { "Raw Terminal line count is invalid" }
        require(lines.all { it.isNotBlank() && it.length <= 240 && it.none(Char::isISOControl) })
        require(recordDigest.length == 64 && recordDigest.all { it in '0'..'9' || it in 'a'..'f' })
    }

    companion object {
        private val PROBES = setOf(
            "adb-version",
            "device-model",
            "android-version",
            "battery-details",
            "storage-details",
            "verified-boot-state",
        )
    }
}

data class DesktopLiveConsoleStatus(
    val integrity: String,
    val nexusStatus: String,
    val nexusObjective: String,
    val nexusCurrentStage: String,
    val nexusResearchCount: Int,
    val guardianReviewState: String,
    val executionAuthority: String,
    val rawTerminalIncluded: Boolean,
    val rawTerminalIntegrity: String,
    val rawTerminalRecords: List<DesktopRawTerminalRecord>,
    val events: List<DesktopLiveConsoleEvent>,
) {
    init {
        require(integrity in INTEGRITY) { "Live Console integrity is invalid" }
        require(nexusStatus in NEXUS_STATES) { "Nexus status is invalid" }
        require(nexusObjective in OBJECTIVES) { "Nexus objective is invalid" }
        require(nexusCurrentStage.length <= 120 && nexusCurrentStage.none(Char::isISOControl))
        require(nexusResearchCount in 0..100) { "Nexus research count is invalid" }
        require(guardianReviewState in GUARDIAN_STATES) { "Guardian review state is invalid" }
        require(executionAuthority == "none") { "Live Console cannot carry execution authority" }
        require(rawTerminalIntegrity in RAW_TERMINAL_INTEGRITY) { "Raw Terminal integrity is invalid" }
        require(rawTerminalRecords.size <= 4) { "Raw Terminal record list is too large" }
        require(rawTerminalIncluded == rawTerminalRecords.isNotEmpty()) {
            "Raw Terminal inclusion marker is invalid"
        }
        require(events.size <= 8) { "Live Console event list is too large" }
    }

    companion object {
        private val INTEGRITY = setOf("trusted", "needs-attention", "unavailable")
        private val NEXUS_STATES = setOf("no-plan", "needs-evidence", "ready-for-guardian")
        private val OBJECTIVES = setOf("none", "build-rom", "root-rom", "flash-device")
        private val GUARDIAN_STATES = setOf("unavailable", "blocked", "ready")
        private val RAW_TERMINAL_INTEGRITY = setOf(
            "verified-local-feed",
            "needs-attention",
            "unavailable",
        )

        fun parse(schemaVersion: Int, payload: JSONObject): DesktopLiveConsoleStatus? = runCatching {
            require(schemaVersion in 5..6) { "Live Console requires Link schema 5 or 6" }
            val rawEvents = payload.optJSONArray("live_console_events") ?: error("Missing events")
            require(rawEvents.length() <= 8) { "Live Console event list is too large" }
            val events = buildList {
                for (index in 0 until rawEvents.length()) {
                    val item = rawEvents.getJSONObject(index)
                    add(
                        DesktopLiveConsoleEvent(
                            eventId = item.getString("event_id"),
                            updatedAt = item.getString("updated_at"),
                            source = item.getString("source"),
                            stage = item.getString("stage"),
                            title = item.getString("title"),
                            summary = item.getString("summary"),
                            explanation = item.getString("explanation"),
                            nextAction = item.getString("next_action"),
                            state = item.getString("state"),
                            progressPercent = item.getInt("progress_percent"),
                            confidence = item.getString("confidence"),
                            guardianProtected = item.getBoolean("guardian_protected"),
                        ),
                    )
                }
            }
            val rawTerminal = if (schemaVersion >= 6) {
                payload.optJSONArray("raw_terminal_records") ?: error("Missing Raw Terminal records")
            } else JSONArray()
            require(rawTerminal.length() <= 4) { "Raw Terminal record list is too large" }
            val terminalRecords = buildList {
                for (index in 0 until rawTerminal.length()) {
                    val item = rawTerminal.getJSONObject(index)
                    val rawLines = item.getJSONArray("lines")
                    val lines = buildList {
                        for (lineIndex in 0 until rawLines.length()) {
                            add(rawLines.getString(lineIndex))
                        }
                    }
                    add(
                        DesktopRawTerminalRecord(
                            recordId = item.getString("record_id"),
                            capturedAt = item.getString("captured_at"),
                            probeId = item.getString("probe_id"),
                            title = item.getString("title"),
                            lines = lines,
                            success = item.getBoolean("success"),
                            recordDigest = item.getString("record_digest"),
                        ),
                    )
                }
            }
            DesktopLiveConsoleStatus(
                integrity = payload.getString("live_console_integrity"),
                nexusStatus = payload.getString("nexus_status"),
                nexusObjective = payload.getString("nexus_objective"),
                nexusCurrentStage = payload.getString("nexus_current_stage"),
                nexusResearchCount = payload.getInt("nexus_research_count"),
                guardianReviewState = payload.getString("guardian_review_state"),
                executionAuthority = payload.getString("live_console_execution_authority"),
                rawTerminalIncluded = payload.getBoolean("raw_terminal_included"),
                rawTerminalIntegrity = if (schemaVersion >= 6) {
                    payload.getString("raw_terminal_integrity")
                } else "unavailable",
                rawTerminalRecords = terminalRecords,
                events = events,
            )
        }.getOrNull()
    }
}
