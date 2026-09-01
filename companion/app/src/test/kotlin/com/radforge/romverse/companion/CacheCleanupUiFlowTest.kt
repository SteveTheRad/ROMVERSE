package com.radforge.romverse.companion

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class CacheCleanupUiFlowTest {
    @Test
    fun `preview confirmation and cleanup expose only genuine busy phases`() {
        val flow = CacheCleanupUiFlow()

        assertFalse(flow.isActive)
        flow.beginPreview()
        assertEquals(CacheCleanupUiPhase.PREVIEWING, flow.phase)
        assertTrue(flow.isActive)
        assertTrue(flow.showProgress)

        flow.previewCompleted(hasCandidates = true)
        assertEquals(CacheCleanupUiPhase.AWAITING_CONFIRMATION, flow.phase)
        assertTrue(flow.isActive)
        assertFalse(flow.showProgress)

        flow.beginCleaning()
        assertTrue(flow.showProgress)
        flow.complete()
        assertEquals(CacheCleanupUiPhase.COMPLETE, flow.phase)
        assertFalse(flow.isActive)
        assertFalse(flow.showProgress)
    }

    @Test
    fun `empty preview and cancellation release the operation lock`() {
        val empty = CacheCleanupUiFlow().apply {
            beginPreview()
            previewCompleted(hasCandidates = false)
        }
        assertEquals(CacheCleanupUiPhase.COMPLETE, empty.phase)
        assertFalse(empty.isActive)

        val cancelled = CacheCleanupUiFlow().apply {
            beginPreview()
            previewCompleted(hasCandidates = true)
            cancel()
        }
        assertEquals(CacheCleanupUiPhase.CANCELLED, cancelled.phase)
        assertFalse(cancelled.isActive)
    }

    @Test
    fun `invalid transitions are rejected instead of inventing progress`() {
        val flow = CacheCleanupUiFlow()

        assertTrue(runCatching { flow.beginCleaning() }.isFailure)
        flow.beginPreview()
        assertTrue(runCatching { flow.beginPreview() }.isFailure)
        assertTrue(runCatching { flow.complete() }.isFailure)
    }

    @Test
    fun `cleanup without verified evidence ends as failed rather than complete`() {
        val flow = CacheCleanupUiFlow().apply {
            beginPreview()
            previewCompleted(hasCandidates = true)
            beginCleaning()
            finishCleaning(evidenceVerified = false)
        }

        assertEquals(CacheCleanupUiPhase.FAILED, flow.phase)
        assertFalse(flow.isActive)
        assertFalse(flow.showProgress)
    }
}
