package com.radforge.romverse.companion

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class RecoveryComparisonTest {
    @Test
    fun resolvedFindingAndHigherScoreIsImproved() {
        val result = RecoveryEvidenceComparator.compare(
            RecoveryEvidence(55, setOf("LOW BATTERY", "STORAGE PRESSURE")),
            RecoveryEvidence(85, setOf("STORAGE PRESSURE")),
        )

        assertEquals(RecoveryDirection.IMPROVED, result.direction)
        assertEquals(30, result.scoreDelta)
        assertEquals(setOf("LOW BATTERY"), result.resolved)
        assertTrue(result.summary().contains("1 resolved"))
    }

    @Test
    fun newFindingNeverClaimsImprovementWhenScoreIsUnchanged() {
        val result = RecoveryEvidenceComparator.compare(
            RecoveryEvidence(80, emptySet()),
            RecoveryEvidence(80, setOf("HIGH TEMPERATURE")),
        )

        assertEquals(RecoveryDirection.NEEDS_ATTENTION, result.direction)
        assertEquals(setOf("HIGH TEMPERATURE"), result.added)
    }

    @Test
    fun newFindingNeverClaimsImprovementEvenWhenScoreRises() {
        val result = RecoveryEvidenceComparator.compare(
            RecoveryEvidence(60, setOf("LOW BATTERY")),
            RecoveryEvidence(80, setOf("HIGH TEMPERATURE")),
        )

        assertEquals(RecoveryDirection.NEEDS_ATTENTION, result.direction)
        assertEquals(20, result.scoreDelta)
        assertEquals(setOf("HIGH TEMPERATURE"), result.added)
    }

    @Test
    fun missingScoreNeverManufacturesComparisonCertainty() {
        val result = RecoveryEvidenceComparator.compare(
            RecoveryEvidence(null, setOf("EVIDENCE UNCONFIRMED")),
            RecoveryEvidence(90, emptySet()),
        )

        assertEquals(RecoveryDirection.UNCONFIRMED, result.direction)
        assertEquals(null, result.scoreDelta)
        assertTrue(result.summary().contains("score unconfirmed"))
    }

    @Test
    fun identicalEvidenceIsUnchanged() {
        val evidence = RecoveryEvidence(92, setOf("NETWORK NOT VALIDATED"))

        val result = RecoveryEvidenceComparator.compare(evidence, evidence)

        assertEquals(RecoveryDirection.UNCHANGED, result.direction)
        assertEquals(0, result.scoreDelta)
    }

    @Test(expected = IllegalArgumentException::class)
    fun invalidScoreIsRejected() {
        RecoveryEvidence(101, emptySet())
    }

    @Test(expected = IllegalArgumentException::class)
    fun controlCharactersInFindingsAreRejected() {
        RecoveryEvidence(80, setOf("NETWORK\u0000STATE"))
    }
}
