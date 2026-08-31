package com.radforge.romverse.companion

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class DesktopAscensionStatusTest {
    @Test
    fun parsesReviewReadyReadOnlyStatus() {
        val status = DesktopAscensionStatus.parse(
            schemaVersion = 2,
            state = "review_ready",
            project = "My ROM",
            method = "magisk",
            targetPartition = "init_boot",
            blockerCount = 0,
            phoneChanged = false,
            executionAuthority = "none",
        )

        assertEquals(100, status?.stagePercent)
        assertEquals("READY FOR GUARDIAN REVIEW", status?.stateLabel)
        assertEquals("My ROM", status?.project)
        assertTrue(status?.nextStep?.contains("explicit consent") == true)
    }

    @Test
    fun parsesBlockedStatusAsAttentionStage() {
        val status = DesktopAscensionStatus.parse(
            2,
            "blocked",
            "My ROM",
            "kernelsu_lkm",
            "boot",
            2,
            false,
            "none",
        )

        assertEquals(82, status?.stagePercent)
        assertTrue(status?.stateLabel?.contains("ATTENTION") == true)
        assertTrue(status?.nextStep?.contains("Guardian card") == true)
    }

    @Test
    fun parsesExactDesktopJourneyGuidance() {
        val status = DesktopAscensionStatus.parse(
            schemaVersion = 3,
            state = "preparing",
            project = "My ROM",
            method = "magisk",
            targetPartition = "init_boot",
            blockerCount = 0,
            phoneChanged = false,
            executionAuthority = "none",
            stageNumber = 4,
            stageTitle = "Prepare the guided phone handoff",
            guidedNextAction = "Review the exact phone on Desktop.",
            whyItMatters = "Installing an app changes phone storage.",
            romverseAction = "ROMVERSE will verify the phone and prepare two bounded actions.",
        )

        assertEquals(44, status?.stagePercent)
        assertEquals("Review the exact phone on Desktop.", status?.nextStep)
        assertTrue(status?.whyItMatters?.contains("phone storage") == true)
        assertTrue(status?.romverseAction?.contains("two bounded actions") == true)
    }

    @Test
    fun acceptsFinalNineStageBuildSealJourney() {
        val status = DesktopAscensionStatus.parse(
            schemaVersion = 4,
            state = "review_ready",
            project = "My Rooted ROM",
            method = "magisk",
            targetPartition = "init_boot",
            blockerCount = 0,
            phoneChanged = false,
            executionAuthority = "none",
            stageNumber = 9,
            stageTitle = "Ready for final Guardian review",
        )

        assertEquals(100, status?.stagePercent)
    }

    @Test
    fun parsesSchemaSixVerifiedOfficialManagerProvenance() {
        val status = DesktopAscensionStatus.parse(
            schemaVersion = 6,
            state = "preparing",
            project = "My Rooted ROM",
            method = "magisk",
            targetPartition = "init_boot",
            blockerCount = 0,
            phoneChanged = false,
            executionAuthority = "none",
            stageNumber = 3,
            stageTitle = "Prepare a source-bound patch capsule",
            managerState = "verified",
            managerRepository = "topjohnwu/Magisk",
            managerTag = "v30.7",
            managerAsset = "Magisk-v30.7.apk",
            managerSha256Ref = "e0d32d2123532860",
        )

        assertEquals("verified", status?.managerState)
        assertEquals("topjohnwu/Magisk", status?.managerRepository)
        assertEquals("Magisk-v30.7.apk", status?.managerAsset)
        assertEquals("e0d32d2123532860", status?.managerSha256Ref)
    }

    @Test
    fun rejectsManagerProvenanceThatIsOldMismatchedOrNotBounded() {
        fun parse(
            schema: Int = 6,
            repository: String = "topjohnwu/Magisk",
            asset: String = "Magisk-v30.7.apk",
            fingerprint: String = "e0d32d2123532860",
        ) = DesktopAscensionStatus.parse(
            schemaVersion = schema,
            state = "preparing",
            project = "My ROM",
            method = "magisk",
            targetPartition = "init_boot",
            blockerCount = 0,
            phoneChanged = false,
            executionAuthority = "none",
            managerState = "verified",
            managerRepository = repository,
            managerTag = "v30.7",
            managerAsset = asset,
            managerSha256Ref = fingerprint,
        )

        assertNull(parse(schema = 5))
        assertNull(parse(repository = "example/Magisk"))
        assertNull(parse(asset = "Magisk-debug.apk"))
        assertNull(parse(fingerprint = "a".repeat(64)))
    }

    @Test
    fun displaysExplicitUnrootedGenesisChoice() {
        val status = DesktopAscensionStatus.parse(
            schemaVersion = 4,
            state = "skipped",
            project = "Clean ROM",
            method = "none",
            targetPartition = "",
            blockerCount = 0,
            phoneChanged = false,
            executionAuthority = "none",
            stageTitle = "Unrooted ROM selected",
        )

        assertEquals(100, status?.stagePercent)
        assertEquals("UNROOTED ROM SELECTED", status?.stateLabel)
        assertTrue(status?.nextStep?.contains("unrooted build route") == true)
    }

    @Test
    fun rejectsAuthorityPhoneChangesAndOldSchemas() {
        assertNull(DesktopAscensionStatus.parse(1, "review_ready", "", "magisk", "boot", 0, false, "none"))
        assertEquals(
            "READY FOR GUARDIAN REVIEW",
            DesktopAscensionStatus.parse(6, "review_ready", "", "magisk", "boot", 0, false, "none")?.stateLabel,
        )
        assertNull(DesktopAscensionStatus.parse(7, "review_ready", "", "magisk", "boot", 0, false, "none"))
        assertEquals(
            "READY FOR GUARDIAN REVIEW",
            DesktopAscensionStatus.parse(5, "review_ready", "", "magisk", "boot", 0, false, "none")?.stateLabel,
        )
        assertNull(DesktopAscensionStatus.parse(2, "review_ready", "", "magisk", "boot", 0, true, "none"))
        assertNull(DesktopAscensionStatus.parse(2, "review_ready", "", "magisk", "boot", 0, false, "flash"))
    }

    @Test
    fun rejectsUnknownMethodOrPartition() {
        assertNull(DesktopAscensionStatus.parse(2, "preparing", "", "unknown", "boot", 0, false, "none"))
        assertNull(DesktopAscensionStatus.parse(2, "preparing", "", "magisk", "system", 0, false, "none"))
    }

    @Test
    fun rejectsUnboundedOrControlBearingAutomaticExplanation() {
        fun parse(action: String) = DesktopAscensionStatus.parse(
            schemaVersion = 6,
            state = "preparing",
            project = "My ROM",
            method = "magisk",
            targetPartition = "init_boot",
            blockerCount = 0,
            phoneChanged = false,
            executionAuthority = "none",
            romverseAction = action,
        )

        assertNull(parse("a".repeat(501)))
        assertNull(parse("Hidden\noperation"))
    }
}
