package com.radforge.romverse.companion

internal enum class CacheCleanupUiPhase {
    IDLE,
    PREVIEWING,
    AWAITING_CONFIRMATION,
    CLEANING,
    COMPLETE,
    CANCELLED,
    FAILED,
}

/**
 * Small state contract that keeps the cleanup control locked while a preview, decision, or
 * verified cleanup is active. It deliberately reports only indeterminate progress because the
 * filesystem APIs do not expose honest byte-by-byte progress callbacks.
 */
internal class CacheCleanupUiFlow {
    var phase: CacheCleanupUiPhase = CacheCleanupUiPhase.IDLE
        private set

    val isActive: Boolean
        get() = phase in setOf(
            CacheCleanupUiPhase.PREVIEWING,
            CacheCleanupUiPhase.AWAITING_CONFIRMATION,
            CacheCleanupUiPhase.CLEANING,
        )

    val showProgress: Boolean
        get() = phase == CacheCleanupUiPhase.PREVIEWING || phase == CacheCleanupUiPhase.CLEANING

    fun beginPreview() {
        require(phase == CacheCleanupUiPhase.IDLE) { "Cleanup preview is already active" }
        phase = CacheCleanupUiPhase.PREVIEWING
    }

    fun previewCompleted(hasCandidates: Boolean) {
        require(phase == CacheCleanupUiPhase.PREVIEWING) { "Cleanup preview is not active" }
        phase = if (hasCandidates) {
            CacheCleanupUiPhase.AWAITING_CONFIRMATION
        } else {
            CacheCleanupUiPhase.COMPLETE
        }
    }

    fun beginCleaning() {
        require(phase == CacheCleanupUiPhase.AWAITING_CONFIRMATION) {
            "Cleanup confirmation is not active"
        }
        phase = CacheCleanupUiPhase.CLEANING
    }

    fun complete() {
        finishCleaning(evidenceVerified = true)
    }

    fun finishCleaning(evidenceVerified: Boolean) {
        require(phase == CacheCleanupUiPhase.CLEANING) { "Cleanup is not active" }
        phase = if (evidenceVerified) {
            CacheCleanupUiPhase.COMPLETE
        } else {
            CacheCleanupUiPhase.FAILED
        }
    }

    fun cancel() {
        require(phase == CacheCleanupUiPhase.AWAITING_CONFIRMATION) {
            "Cleanup confirmation is not active"
        }
        phase = CacheCleanupUiPhase.CANCELLED
    }

    fun fail() {
        require(phase == CacheCleanupUiPhase.PREVIEWING || phase == CacheCleanupUiPhase.CLEANING) {
            "No cleanup operation can fail from $phase"
        }
        phase = CacheCleanupUiPhase.FAILED
    }
}
