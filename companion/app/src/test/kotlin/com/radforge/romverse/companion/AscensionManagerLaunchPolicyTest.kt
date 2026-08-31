package com.radforge.romverse.companion

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class AscensionManagerLaunchPolicyTest {
    @Test
    fun mapsVerifiedOfficialMagiskToItsExactPackageAndSigner() {
        val target = AscensionManagerLaunchPolicy.target(status())

        assertEquals("Magisk", target?.displayName)
        assertEquals("com.topjohnwu.magisk", target?.packageName)
        assertEquals(
            "b4cb83b4dad99f997dbe872f013aa16c14eec41d167021f371f7e1330f273ee6",
            target?.signerSha256,
        )
    }

    @Test
    fun mapsVerifiedOfficialKernelSuToItsExactPackageAndSigner() {
        val target = AscensionManagerLaunchPolicy.target(
            status(
                method = "kernelsu_lkm",
                repository = "tiann/KernelSU",
                asset = "KernelSU_v3.3.0_32601-release.apk",
            ),
        )

        assertEquals("KernelSU Manager", target?.displayName)
        assertEquals("me.weishu.kernelsu", target?.packageName)
        assertEquals(
            "c371061b19d8c7d7d6133c6a9bafe198fa944e50c1b31c9d8daa8d7f1fc2d2d6",
            target?.signerSha256,
        )
    }

    @Test
    fun refusesUnavailableManagerEvidence() {
        val unavailable = DesktopAscensionStatus(
            state = "preparing",
            project = "My ROM",
            method = "magisk",
            targetPartition = "init_boot",
            blockerCount = 0,
            phoneChanged = false,
            executionAuthority = "none",
        )

        assertNull(AscensionManagerLaunchPolicy.target(unavailable))
    }

    @Test
    fun signerPinsRemainFullLowercaseSha256Values() {
        val targets = listOf(
            AscensionManagerLaunchPolicy.target(status()),
            AscensionManagerLaunchPolicy.target(
                status(
                    method = "kernelsu_lkm",
                    repository = "tiann/KernelSU",
                    asset = "KernelSU_v3.3.0_32601-release.apk",
                ),
            ),
        )

        assertTrue(targets.all { it?.signerSha256?.matches(Regex("[0-9a-f]{64}")) == true })
    }

    @Test
    fun identifiesOnlySignerPinnedInstalledManagerCandidates() {
        val magisk = AscensionManagerLaunchPolicy.installedCandidate { packageName ->
            if (packageName == "com.topjohnwu.magisk") {
                "b4cb83b4dad99f997dbe872f013aa16c14eec41d167021f371f7e1330f273ee6"
            } else null
        }
        val conflict = AscensionManagerLaunchPolicy.installedCandidate { packageName ->
            when (packageName) {
                "com.topjohnwu.magisk" ->
                    "b4cb83b4dad99f997dbe872f013aa16c14eec41d167021f371f7e1330f273ee6"
                "me.weishu.kernelsu" ->
                    "c371061b19d8c7d7d6133c6a9bafe198fa944e50c1b31c9d8daa8d7f1fc2d2d6"
                else -> null
            }
        }
        val altered = AscensionManagerLaunchPolicy.installedCandidate { "0".repeat(64) }

        assertEquals("magisk", magisk)
        assertEquals("conflict", conflict)
        assertEquals("none", altered)
    }

    private fun status(
        method: String = "magisk",
        repository: String = "topjohnwu/Magisk",
        asset: String = "Magisk-v30.7.apk",
    ) = DesktopAscensionStatus(
        state = "preparing",
        project = "My ROM",
        method = method,
        targetPartition = "init_boot",
        blockerCount = 0,
        phoneChanged = false,
        executionAuthority = "none",
        managerState = "verified",
        managerRepository = repository,
        managerTag = "v30.7",
        managerAsset = asset,
        managerSha256Ref = "e0d32d2123532860",
    )
}
