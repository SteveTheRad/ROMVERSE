package com.radforge.romverse.companion

/**
 * Health-only payload shared with an already authenticated ROMVERSE Desktop.
 *
 * The contract intentionally excludes identifiers such as serial/IMEI, account
 * details, package inventories, user files, and every kind of command or
 * approval. It is evidence for display and diagnosis, never execution authority.
 */
internal data class CompanionHealthSnapshot(
    val capturedAtEpochMs: Long,
    val manufacturer: String,
    val model: String,
    val deviceCodename: String,
    val androidVersion: String,
    val sdkInt: Int,
    val companionVersion: String,
    val batteryPercent: Int?,
    val batteryTemperatureCelsius: Double?,
    val storageUsedBytes: Long?,
    val storageTotalBytes: Long?,
    val memoryAvailableBytes: Long?,
    val memoryTotalBytes: Long?,
    val networkValidated: Boolean?,
    val usbConnected: Boolean?,
    val healthScore: Int?,
    val vitalisState: String,
    val vitalisEvidencePercent: Int,
    val kernelRelease: String,
    val rootSignal: String,
    val rootManagerCandidate: String,
    val bootloaderState: String,
    val kernelSuSupport: String,
) {
    init {
        require(capturedAtEpochMs > 0) { "capture time must be positive" }
        listOf(manufacturer, model, deviceCodename, androidVersion, companionVersion).forEach {
            require(it.isNotBlank() && it.length <= 80 && it.none(Char::isISOControl)) {
                "identity text is invalid"
            }
        }
        require(sdkInt in 1..10_000) { "SDK is outside the supported range" }
        require(batteryPercent == null || batteryPercent in 0..100) { "battery is invalid" }
        require(
            batteryTemperatureCelsius == null ||
                batteryTemperatureCelsius.isFinite() && batteryTemperatureCelsius in -20.0..100.0
        ) { "battery temperature is invalid" }
        require(healthScore == null || healthScore in 0..100) { "health score is invalid" }
        require(vitalisState in setOf("OPTIMAL", "ATTENTION", "ACTION RECOMMENDED", "UNCONFIRMED")) {
            "Vitalis state is invalid"
        }
        require(vitalisEvidencePercent in 0..100) { "Vitalis evidence is invalid" }
        require(kernelRelease.isNotBlank() && kernelRelease.length <= 160 && kernelRelease.none(Char::isISOControl)) {
            "kernel release is invalid"
        }
        require(rootSignal in setOf("observed", "not_observed", "unknown")) {
            "root signal is invalid"
        }
        require(rootManagerCandidate in setOf("magisk", "kernelsu_lkm", "conflict", "none", "unknown")) {
            "root Manager candidate is invalid"
        }
        require(bootloaderState in setOf("locked", "unlocked", "unknown")) {
            "bootloader state is invalid"
        }
        require(kernelSuSupport in setOf("supported", "unsupported", "unknown")) {
            "KernelSU support is invalid"
        }
        listOf(
            storageUsedBytes,
            storageTotalBytes,
            memoryAvailableBytes,
            memoryTotalBytes,
        ).forEach {
            require(it == null || it in 0..Long.MAX_VALUE / 100L) {
                "resource size is invalid"
            }
        }
        require(
            storageUsedBytes == null || storageTotalBytes == null ||
                storageUsedBytes <= storageTotalBytes
        ) { "storage use exceeds total" }
        require(
            memoryAvailableBytes == null || memoryTotalBytes == null ||
                memoryAvailableBytes <= memoryTotalBytes
        ) { "available memory exceeds total" }
        require((storageUsedBytes == null) == (storageTotalBytes == null)) {
            "storage evidence must be a complete pair"
        }
        require((memoryAvailableBytes == null) == (memoryTotalBytes == null)) {
            "memory evidence must be a complete pair"
        }
        require(storageTotalBytes == null || storageTotalBytes > 0L) {
            "storage total must be positive"
        }
        require(memoryTotalBytes == null || memoryTotalBytes > 0L) {
            "memory total must be positive"
        }
        val storagePercent = if (storageUsedBytes != null && storageTotalBytes != null) {
            ((storageUsedBytes * 100L) / storageTotalBytes).toInt()
        } else null
        val ramPercent = if (memoryAvailableBytes != null && memoryTotalBytes != null) {
            (((memoryTotalBytes - memoryAvailableBytes) * 100L) / memoryTotalBytes).toInt()
        } else null
        val assessment = VitalisAssessmentEngine.assess(
            VitalisSnapshot(
                batteryPercent = batteryPercent,
                temperatureCelsius = batteryTemperatureCelsius,
                storageUsedPercent = storagePercent,
                ramUsedPercent = ramPercent,
                networkValidated = networkValidated,
                usbConnected = usbConnected,
                capturedAtEpochMs = capturedAtEpochMs,
            ),
            nowEpochMs = capturedAtEpochMs,
        )
        require(healthScore == assessment.score) { "health score does not match Vitalis evidence" }
        require(vitalisState == assessment.state) { "Vitalis state does not match its evidence" }
        require(vitalisEvidencePercent == assessment.evidencePercent) {
            "Vitalis evidence coverage does not match its fields"
        }
    }

    fun asWireMap(): Map<String, Any?> = mapOf(
        "schema_version" to 4,
        "captured_at_epoch_ms" to capturedAtEpochMs,
        "manufacturer" to manufacturer,
        "model" to model,
        "device_codename" to deviceCodename,
        "android_version" to androidVersion,
        "sdk_int" to sdkInt,
        "companion_version" to companionVersion,
        "battery_percent" to batteryPercent,
        "battery_temperature_celsius" to batteryTemperatureCelsius,
        "storage_used_bytes" to storageUsedBytes,
        "storage_total_bytes" to storageTotalBytes,
        "memory_available_bytes" to memoryAvailableBytes,
        "memory_total_bytes" to memoryTotalBytes,
        "network_validated" to networkValidated,
        "usb_connected" to usbConnected,
        "health_score" to healthScore,
        "vitalis_state" to vitalisState,
        "vitalis_evidence_percent" to vitalisEvidencePercent,
        "kernel_release" to kernelRelease,
        "root_signal" to rootSignal,
        "root_manager_candidate" to rootManagerCandidate,
        "bootloader_state" to bootloaderState,
        "kernelsu_support" to kernelSuSupport,
        "guardian_active" to true,
        "privacy_scope" to "health_and_device_safety",
    )
}
