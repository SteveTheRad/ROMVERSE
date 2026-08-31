package com.radforge.romverse.companion

data class RecoveryEvidence(val score: Int?, val findings: Set<String>) {
    init {
        require(score == null || score in 0..100) { "Recovery health score must be 0..100" }
        require(findings.size <= 30) { "Recovery evidence has too many findings" }
        require(findings.all { it.isNotBlank() && it.length <= 120 }) {
            "Recovery finding is invalid"
        }
        require(findings.all { it.none(Char::isISOControl) }) {
            "Recovery finding contains control characters"
        }
    }
}

enum class RecoveryDirection(val display: String) {
    IMPROVED("IMPROVED"),
    UNCHANGED("UNCHANGED"),
    NEEDS_ATTENTION("NEEDS MORE ATTENTION"),
    UNCONFIRMED("UNCONFIRMED"),
}

data class RecoveryComparison(
    val direction: RecoveryDirection,
    val scoreDelta: Int?,
    val resolved: Set<String>,
    val added: Set<String>,
) {
    fun summary(): String =
        "Fresh local evidence: ${direction.display} • score ${scoreDelta?.let { "${if (it >= 0) "+" else ""}$it" } ?: "unconfirmed"} • ${resolved.size} resolved • ${added.size} new"
}

object RecoveryEvidenceComparator {
    fun compare(baseline: RecoveryEvidence, current: RecoveryEvidence): RecoveryComparison {
        val resolved = baseline.findings - current.findings
        val added = current.findings - baseline.findings
        val delta = if (baseline.score != null && current.score != null) {
            current.score - baseline.score
        } else null
        val direction = when {
            added.isNotEmpty() || (delta != null && delta < 0) -> RecoveryDirection.NEEDS_ATTENTION
            delta == null -> RecoveryDirection.UNCONFIRMED
            delta > 0 || (resolved.isNotEmpty() && added.isEmpty()) -> RecoveryDirection.IMPROVED
            else -> RecoveryDirection.UNCHANGED
        }
        return RecoveryComparison(direction, delta, resolved, added)
    }
}
