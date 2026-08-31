package com.radforge.romverse.companion

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class VitalisAssessmentTest {
    @Test
    fun completeHealthyEvidenceProducesOptimalBaseline() {
        val assessment = VitalisAssessmentEngine.assess(
            VitalisSnapshot(82, 31.5, 45, 52, true, true),
        )

        assertEquals(100, assessment.score)
        assertEquals(100, assessment.evidencePercent)
        assertEquals("OPTIMAL", assessment.state)
        assertEquals("all-clear", assessment.findings.single().findingId)
    }

    @Test
    fun missingCoreEvidenceRemainsExplicitlyUnconfirmed() {
        val assessment = VitalisAssessmentEngine.assess(
            VitalisSnapshot(null, null, null, 50, true, false),
        )

        assertNull(assessment.score)
        assertEquals("UNCONFIRMED", assessment.state)
        assertTrue(assessment.evidencePercent < 100)
        assertTrue(assessment.findings.any { it.findingId == "evidence-unconfirmed" })
        assertTrue(assessment.findings.none { it.findingId == "all-clear" })
    }

    @Test
    fun missingTemperatureCannotProduceAFalseOptimalScore() {
        val assessment = VitalisAssessmentEngine.assess(
            VitalisSnapshot(82, null, 45, 52, true, true),
        )

        assertNull(assessment.score)
        assertEquals("UNCONFIRMED", assessment.state)
        assertTrue(assessment.findings.any { it.findingId == "evidence-unconfirmed" })
    }

    @Test
    fun knownCriticalEvidenceRemainsProminentWhenAnotherSignalIsMissing() {
        val assessment = VitalisAssessmentEngine.assess(
            VitalisSnapshot(null, 48.0, 45, 52, true, true),
        )

        assertNull(assessment.score)
        assertEquals("ACTION RECOMMENDED", assessment.state)
        assertTrue(assessment.findings.any { it.findingId == "high-temperature" })
    }

    @Test
    fun staleAndFarFutureEvidenceIsNeverScored() {
        val stale = VitalisAssessmentEngine.assess(
            VitalisSnapshot(82, 31.5, 45, 52, true, true, capturedAtEpochMs = 100_000L),
            nowEpochMs = 300_001L,
        )
        val future = VitalisAssessmentEngine.assess(
            VitalisSnapshot(
                82,
                31.5,
                45,
                52,
                true,
                true,
                capturedAtEpochMs = Long.MAX_VALUE,
            ),
            nowEpochMs = 1L,
        )

        listOf(stale, future).forEach { assessment ->
            assertNull(assessment.score)
            assertEquals(0, assessment.evidencePercent)
            assertEquals("UNCONFIRMED", assessment.state)
            assertEquals("stale-evidence", assessment.findings.single().findingId)
        }
    }

    @Test
    fun disconnectedOptionalUsbLinkDoesNotCreateFalseHealthAttention() {
        val assessment = VitalisAssessmentEngine.assess(
            VitalisSnapshot(82, 31.5, 45, 52, true, false),
        )

        assertEquals(100, assessment.score)
        assertEquals("OPTIMAL", assessment.state)
        assertEquals(VitalisSeverity.HEALTHY, assessment.findings.single().severity)
        assertEquals("usb-not-detected", assessment.findings.single().findingId)
    }

    @Test
    fun criticalStorageAndTemperatureProduceActionsWithoutChangingDevice() {
        val assessment = VitalisAssessmentEngine.assess(
            VitalisSnapshot(60, 47.2, 94, 91, false, false),
        )

        assertEquals("ACTION RECOMMENDED", assessment.state)
        assertTrue(assessment.score != null && assessment.score!! < 65)
        assertTrue(assessment.findings.any { it.findingId == "high-temperature" })
        assertTrue(assessment.findings.any { it.findingId == "storage-critical" })
        assertTrue(assessment.findings.all { it.nextAction.isNotBlank() })
    }
}
