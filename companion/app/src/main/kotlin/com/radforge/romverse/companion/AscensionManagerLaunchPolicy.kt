package com.radforge.romverse.companion

data class AscensionManagerLaunchTarget(
    val displayName: String,
    val packageName: String,
    val signerSha256: String,
)

object AscensionManagerLaunchPolicy {
    private val MAGISK = AscensionManagerLaunchTarget(
        displayName = "Magisk",
        packageName = "com.topjohnwu.magisk",
        signerSha256 = "b4cb83b4dad99f997dbe872f013aa16c14eec41d167021f371f7e1330f273ee6",
    )
    private val KERNELSU = AscensionManagerLaunchTarget(
        displayName = "KernelSU Manager",
        packageName = "me.weishu.kernelsu",
        signerSha256 = "c371061b19d8c7d7d6133c6a9bafe198fa944e50c1b31c9d8daa8d7f1fc2d2d6",
    )

    fun target(status: DesktopAscensionStatus): AscensionManagerLaunchTarget? {
        if (status.managerState != "verified") return null
        return when {
            status.method == "magisk" &&
                status.managerRepository == "topjohnwu/Magisk" &&
                status.managerAsset.matches(Regex("Magisk-v[0-9][A-Za-z0-9._-]*\\.apk")) -> MAGISK
            status.method == "kernelsu_lkm" &&
                status.managerRepository == "tiann/KernelSU" &&
                status.managerAsset.matches(
                    Regex("KernelSU_v[0-9][A-Za-z0-9._-]*-release\\.apk"),
                ) -> KERNELSU
            else -> null
        }
    }

    fun installedCandidate(signerByPackage: (String) -> String?): String {
        val magisk = signerByPackage(MAGISK.packageName) == MAGISK.signerSha256
        val kernelSu = signerByPackage(KERNELSU.packageName) == KERNELSU.signerSha256
        return when {
            magisk && kernelSu -> "conflict"
            magisk -> "magisk"
            kernelSu -> "kernelsu_lkm"
            else -> "none"
        }
    }
}
