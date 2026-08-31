package com.radforge.romverse.companion

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class LifelineSessionIntegrityTest {
    private val snapshot = LifelineSessionSnapshot(
        sessionId = "8e892584-b96d-430d-99d8-67d20a9ddfd6",
        createdAtEpochMs = 100L,
        updatedAtEpochMs = 200L,
        status = "ready_for_comparison",
        baselineScore = 70,
        baselineFindings = listOf("LOW BATTERY"),
        checkpoints = listOf("Back up important data.", "Run a fresh local scan."),
        reviewed = listOf(true, true),
    )

    @Test
    fun unchangedSessionVerifies() {
        val digest = LifelineSessionIntegrity.digest(snapshot)

        assertTrue(LifelineSessionIntegrity.verifies(snapshot, digest))
    }

    @Test
    fun changedCheckpointEvidenceIsRejected() {
        val digest = LifelineSessionIntegrity.digest(snapshot)

        assertFalse(
            LifelineSessionIntegrity.verifies(
                snapshot.copy(
                    checkpoints = listOf("Different checkpoint.", "Run a fresh local scan."),
                ),
                digest,
            ),
        )
    }

    @Test
    fun malformedDigestIsRejected() {
        assertFalse(LifelineSessionIntegrity.verifies(snapshot, "not-a-digest"))
    }

    @Test
    fun statusCannotClaimProgressWithoutItsRequiredEvidence() {
        assertTrue(
            runCatching {
                snapshot.copy(status = "active", reviewed = listOf(true, true))
            }.isFailure,
        )
        assertTrue(
            runCatching {
                snapshot.copy(status = "ready_for_comparison", reviewed = listOf(true, false))
            }.isFailure,
        )
        assertTrue(
            runCatching {
                snapshot.copy(status = "comparison_complete")
            }.isFailure,
        )
    }

    @Test
    fun completedComparisonSummaryIsDerivedFromTheSavedEvidence() {
        val comparison = RecoveryEvidenceComparator.compare(
            RecoveryEvidence(70, setOf("LOW BATTERY")),
            RecoveryEvidence(90, emptySet()),
        )
        val complete = snapshot.copy(
            status = "comparison_complete",
            verificationScore = 90,
            verificationFindings = emptyList(),
            verificationSummary = comparison.summary(),
        )

        assertTrue(
            LifelineSessionIntegrity.verifies(
                complete,
                LifelineSessionIntegrity.digest(complete),
            ),
        )
        assertTrue(
            runCatching {
                complete.copy(verificationSummary = "Fresh local evidence: IMPROVED")
            }.isFailure,
        )
    }

    @Test
    fun legacySchemaTwoEvidenceRemainsVerifiableForMigration() {
        val legacy = LifelineLegacySessionSnapshot(
            sessionId = snapshot.sessionId,
            createdAtEpochMs = snapshot.createdAtEpochMs,
            updatedAtEpochMs = snapshot.updatedAtEpochMs,
            status = "comparison_complete",
            baselineScore = snapshot.baselineScore,
            baselineFindings = snapshot.baselineFindings,
            checkpoints = snapshot.checkpoints,
            reviewed = listOf(true, false),
            verificationScore = 90,
            verificationFindings = emptyList(),
            verificationSummary = "Fresh local evidence: IMPROVED • score +20 • 1 resolved • 0 new",
        )
        val digest = LifelineSessionIntegrity.digestLegacyV2(legacy)

        assertTrue(LifelineSessionIntegrity.verifiesLegacyV2(legacy, digest))
        assertFalse(LifelineSessionIntegrity.verifiesLegacyV2(legacy, "0".repeat(64)))
        val migrated = LifelineSessionMigration.fromV2(legacy)
        assertTrue(migrated.status == "active")
        assertTrue(migrated.verificationSummary.isEmpty())
        assertTrue(migrated.verificationScore == null)
    }

    @Test
    fun genuineLegacyComparisonMigratesWithoutInventingOrLosingItsEvidence() {
        val comparison = RecoveryEvidenceComparator.compare(
            RecoveryEvidence(70, setOf("LOW BATTERY")),
            RecoveryEvidence(90, emptySet()),
        )
        val legacy = LifelineLegacySessionSnapshot(
            sessionId = snapshot.sessionId,
            createdAtEpochMs = snapshot.createdAtEpochMs,
            updatedAtEpochMs = snapshot.updatedAtEpochMs,
            status = "comparison_complete",
            baselineScore = 70,
            baselineFindings = listOf("LOW BATTERY"),
            checkpoints = snapshot.checkpoints,
            reviewed = listOf(true, true),
            verificationScore = 90,
            verificationFindings = emptyList(),
            verificationSummary = comparison.summary(),
        )

        val migrated = LifelineSessionMigration.fromV2(legacy)

        assertTrue(migrated.status == "comparison_complete")
        assertTrue(migrated.verificationSummary == comparison.summary())
        assertTrue(
            LifelineSessionIntegrity.verifies(
                migrated,
                LifelineSessionIntegrity.digest(migrated),
            ),
        )
    }
}
