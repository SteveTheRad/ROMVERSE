package com.radforge.romverse.companion

import java.security.MessageDigest

internal data class LifelineSessionSnapshot(
    val sessionId: String,
    val createdAtEpochMs: Long,
    val updatedAtEpochMs: Long,
    val status: String,
    val baselineScore: Int?,
    val baselineFindings: List<String>,
    val checkpoints: List<String>,
    val reviewed: List<Boolean>,
    val verificationScore: Int? = null,
    val verificationFindings: List<String> = emptyList(),
    val verificationSummary: String = "",
) {
    init {
        require(sessionId.length in 1..80 && sessionId.none(Char::isISOControl))
        require(createdAtEpochMs > 0L && updatedAtEpochMs >= createdAtEpochMs)
        require(
            status in setOf(
                "active",
                "ready_for_verification",
                "ready_for_comparison",
                "comparison_complete",
            ),
        )
        require(baselineScore == null || baselineScore in 0..100)
        require(verificationScore == null || verificationScore in 0..100)
        require(baselineFindings.size <= 30 && verificationFindings.size <= 30)
        require((baselineFindings + verificationFindings).all(::validFinding))
        require(baselineFindings.distinct().size == baselineFindings.size)
        require(verificationFindings.distinct().size == verificationFindings.size)
        require(checkpoints.size in 2..12 && checkpoints.all(::validCheckpoint))
        require(reviewed.size == checkpoints.size)
        require(verificationSummary.length <= 2_000 && verificationSummary.none(Char::isISOControl))
        val allReviewed = reviewed.all { it }
        when (status) {
            "active" -> {
                require(!allReviewed) { "Active Lifeline session cannot claim all checkpoints" }
                requireNoVerificationEvidence()
            }
            "ready_for_verification", "ready_for_comparison" -> {
                require(allReviewed) { "Ready Lifeline session requires every checkpoint review" }
                requireNoVerificationEvidence()
            }
            "comparison_complete" -> {
                require(allReviewed) { "Completed Lifeline comparison requires checkpoint review" }
                val expected = RecoveryEvidenceComparator.compare(
                    RecoveryEvidence(baselineScore, baselineFindings.toSet()),
                    RecoveryEvidence(verificationScore, verificationFindings.toSet()),
                ).summary()
                require(verificationSummary == expected) {
                    "Lifeline comparison summary does not match its evidence"
                }
            }
        }
    }

    private fun requireNoVerificationEvidence() {
        require(
            verificationScore == null &&
                verificationFindings.isEmpty() &&
                verificationSummary.isEmpty()
        ) { "Incomplete Lifeline session cannot contain comparison evidence" }
    }

    private companion object {
        fun validFinding(value: String) = value.length in 1..120 && value.none(Char::isISOControl)

        fun validCheckpoint(value: String) = value.length in 1..240 && value.none(Char::isISOControl)
    }
}

internal data class LifelineLegacySessionSnapshot(
    val sessionId: String,
    val createdAtEpochMs: Long,
    val updatedAtEpochMs: Long,
    val status: String,
    val baselineScore: Int?,
    val baselineFindings: List<String>,
    val checkpoints: List<String>,
    val reviewed: List<Boolean>,
    val verificationScore: Int? = null,
    val verificationFindings: List<String> = emptyList(),
    val verificationSummary: String = "",
) {
    init {
        require(sessionId.length in 1..80 && sessionId.none(Char::isISOControl))
        require(createdAtEpochMs > 0L && updatedAtEpochMs >= createdAtEpochMs)
        require(
            status in setOf(
                "active",
                "ready_for_verification",
                "ready_for_comparison",
                "comparison_complete",
            ),
        )
        require(baselineScore == null || baselineScore in 0..100)
        require(verificationScore == null || verificationScore in 0..100)
        require(baselineFindings.size <= 30 && verificationFindings.size <= 30)
        require((baselineFindings + verificationFindings).all(::validText))
        require(checkpoints.size in 2..12 && checkpoints.all(::validCheckpoint))
        require(reviewed.size == checkpoints.size)
        require(verificationSummary.length <= 2_000 && verificationSummary.none(Char::isISOControl))
    }

    private companion object {
        fun validText(value: String) = value.length in 1..120 && value.none(Char::isISOControl)

        fun validCheckpoint(value: String) = value.length in 1..240 && value.none(Char::isISOControl)
    }
}

internal object LifelineSessionMigration {
    fun fromV2(legacy: LifelineLegacySessionSnapshot): LifelineSessionSnapshot {
        val allReviewed = legacy.reviewed.all { it }
        val preserveComparison = legacy.status == "comparison_complete" && allReviewed
        val migratedStatus = when {
            preserveComparison -> "comparison_complete"
            allReviewed -> "ready_for_comparison"
            else -> "active"
        }
        return LifelineSessionSnapshot(
            sessionId = legacy.sessionId,
            createdAtEpochMs = legacy.createdAtEpochMs,
            updatedAtEpochMs = legacy.updatedAtEpochMs,
            status = migratedStatus,
            baselineScore = legacy.baselineScore,
            baselineFindings = legacy.baselineFindings.distinct(),
            checkpoints = legacy.checkpoints,
            reviewed = legacy.reviewed,
            verificationScore = legacy.verificationScore.takeIf { preserveComparison },
            verificationFindings = if (preserveComparison) {
                legacy.verificationFindings.distinct()
            } else emptyList(),
            verificationSummary = legacy.verificationSummary.takeIf { preserveComparison }.orEmpty(),
        )
    }
}

internal object LifelineSessionIntegrity {
    private const val PREFIX = "romverse.lifeline-session|3"
    private const val LEGACY_PREFIX = "romverse.lifeline-session|2"

    fun digest(snapshot: LifelineSessionSnapshot): String = sha256(canonical(snapshot))

    fun verifies(snapshot: LifelineSessionSnapshot, expectedDigest: String): Boolean {
        if (expectedDigest.length != 64 || expectedDigest.any { it !in "0123456789abcdef" }) {
            return false
        }
        return MessageDigest.isEqual(
            expectedDigest.toByteArray(Charsets.UTF_8),
            digest(snapshot).toByteArray(Charsets.UTF_8),
        )
    }

    fun verifiesLegacyV2(
        snapshot: LifelineLegacySessionSnapshot,
        expectedDigest: String,
    ): Boolean {
        if (expectedDigest.length != 64 || expectedDigest.any { it !in "0123456789abcdef" }) {
            return false
        }
        return MessageDigest.isEqual(
            expectedDigest.toByteArray(Charsets.UTF_8),
            digestLegacyV2(snapshot).toByteArray(Charsets.UTF_8),
        )
    }

    fun digestLegacyV2(snapshot: LifelineLegacySessionSnapshot): String =
        sha256(canonicalLegacy(snapshot))

    private fun canonical(snapshot: LifelineSessionSnapshot): String = buildString {
        append(PREFIX)
        field("session_id", snapshot.sessionId)
        field("created_at", snapshot.createdAtEpochMs.toString())
        field("updated_at", snapshot.updatedAtEpochMs.toString())
        field("status", snapshot.status)
        field("baseline_score", snapshot.baselineScore?.toString() ?: "unconfirmed")
        listField("baseline_findings", snapshot.baselineFindings)
        listField("checkpoints", snapshot.checkpoints)
        listField("reviewed", snapshot.reviewed.map(Boolean::toString))
        field("verification_score", snapshot.verificationScore?.toString() ?: "unconfirmed")
        listField("verification_findings", snapshot.verificationFindings)
        field("verification_summary", snapshot.verificationSummary)
    }

    private fun canonicalLegacy(snapshot: LifelineLegacySessionSnapshot): String = buildString {
        append(LEGACY_PREFIX)
        field("session_id", snapshot.sessionId)
        field("created_at", snapshot.createdAtEpochMs.toString())
        field("updated_at", snapshot.updatedAtEpochMs.toString())
        field("status", snapshot.status)
        field("baseline_score", snapshot.baselineScore?.toString() ?: "unconfirmed")
        listField("baseline_findings", snapshot.baselineFindings)
        listField("checkpoints", snapshot.checkpoints)
        listField("reviewed", snapshot.reviewed.map(Boolean::toString))
        field("verification_score", snapshot.verificationScore?.toString() ?: "unconfirmed")
        listField("verification_findings", snapshot.verificationFindings)
        field("verification_summary", snapshot.verificationSummary)
    }

    private fun StringBuilder.field(name: String, value: String) {
        append('\n').append(name).append('=').append(value.length).append(':').append(value)
    }

    private fun StringBuilder.listField(name: String, values: List<String>) {
        append('\n').append(name).append('#').append(values.size)
        values.forEachIndexed { index, value -> field("$name[$index]", value) }
    }

    private fun sha256(value: String): String = MessageDigest.getInstance("SHA-256")
        .digest(value.toByteArray(Charsets.UTF_8))
        .joinToString("") { "%02x".format(it) }
}
