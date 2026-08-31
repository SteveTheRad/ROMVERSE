package com.radforge.romverse.companion

import java.nio.file.Files
import java.nio.file.attribute.FileTime
import java.security.MessageDigest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class CompanionCacheOptimizerTest {
    private val day = 24L * 60L * 60L * 1_000L

    @Test
    fun `preview selects only stale regular files and records skipped evidence`() {
        val workspace = Files.createTempDirectory("romverse-cache-test").toFile()
        try {
            val cache = workspace.resolve("cache").apply { mkdirs() }
            val receipt = workspace.resolve("receipts")
            val now = 10L * day
            val stale = cache.resolve("stale.tmp").apply { writeText("stale") }
            val recent = cache.resolve("recent.tmp").apply { writeText("recent") }
            Files.setLastModifiedTime(stale.toPath(), FileTime.fromMillis(now - 2L * day))
            Files.setLastModifiedTime(recent.toPath(), FileTime.fromMillis(now - 1_000L))
            val outside = workspace.resolve("outside.tmp").apply { writeText("outside") }
            val symlink = cache.resolve("unsafe-link")
            Files.createSymbolicLink(symlink.toPath(), outside.toPath())

            val plan = CompanionCacheOptimizer(receipt).preview(cache, now)

            assertEquals(listOf("stale.tmp"), plan.candidates.map { it.relativePath })
            assertEquals(stale.length(), plan.totalBytes)
            assertEquals(1, plan.skippedRecent)
            assertEquals(1, plan.skippedUnsafe)
            assertTrue(recent.exists())
            assertTrue(outside.exists())
        } finally {
            workspace.deleteRecursively()
        }
    }

    @Test
    fun `cleanup deletes exact previewed file and writes verified privacy safe receipt`() {
        val workspace = Files.createTempDirectory("romverse-cache-clean").toFile()
        try {
            val cache = workspace.resolve("cache").apply { mkdirs() }
            val receipts = workspace.resolve("receipts")
            val now = 10L * day
            val stale = cache.resolve("stale.tmp").apply { writeText("verified stale bytes") }
            Files.setLastModifiedTime(stale.toPath(), FileTime.fromMillis(now - 2L * day))
            val optimizer = CompanionCacheOptimizer(receipts)
            val plan = optimizer.preview(cache, now)

            val result = optimizer.clean(plan, now + 1_000L)

            assertEquals(1, result.filesRemoved)
            assertFalse(stale.exists())
            assertTrue(result.receiptSaved)
            val receipt = optimizer.loadLatestReceipt()
            assertTrue(receipt.valid)
            assertTrue(receipt.integrityVerified)
            assertEquals("companion-cache-only", receipt.fields["scope"])
            assertEquals("false", receipt.fields["other_apps_modified"])
            assertEquals("false", receipt.fields["device_command_executed"])
            val serialized = receipts.resolve("latest-cleanup.romverse").readText()
            assertFalse(serialized.contains(cache.absolutePath))
            assertFalse(serialized.contains("stale.tmp"))
            assertFalse(receipts.listFiles().orEmpty().any { it.name.endsWith(".tmp") })
        } finally {
            workspace.deleteRecursively()
        }
    }

    @Test
    fun `file changed after preview is preserved`() {
        val workspace = Files.createTempDirectory("romverse-cache-change").toFile()
        try {
            val cache = workspace.resolve("cache").apply { mkdirs() }
            val now = 10L * day
            val stale = cache.resolve("stale.tmp").apply { writeText("before") }
            Files.setLastModifiedTime(stale.toPath(), FileTime.fromMillis(now - 2L * day))
            val optimizer = CompanionCacheOptimizer(workspace.resolve("receipts"))
            val plan = optimizer.preview(cache, now)
            stale.writeText("changed after preview")

            val result = optimizer.clean(plan, now + 1_000L)

            assertTrue(stale.exists())
            assertEquals(0, result.filesRemoved)
            assertEquals(1, result.changedOrMissing)
            assertTrue(result.receiptSaved)
        } finally {
            workspace.deleteRecursively()
        }
    }

    @Test
    fun `forged traversal plan is rejected and outside file survives`() {
        val workspace = Files.createTempDirectory("romverse-cache-traversal").toFile()
        try {
            val cache = workspace.resolve("cache").apply { mkdirs() }
            val now = 10L * day
            val inside = cache.resolve("inside.tmp").apply { writeText("inside") }
            Files.setLastModifiedTime(inside.toPath(), FileTime.fromMillis(now - 2L * day))
            val outside = workspace.resolve("outside.tmp").apply { writeText("outside") }
            val optimizer = CompanionCacheOptimizer(workspace.resolve("receipts"))
            val plan = optimizer.preview(cache, now)
            val forged = plan.copy(
                candidates = listOf(
                    plan.candidates.single().copy(relativePath = "../outside.tmp")
                )
            )

            val failure = runCatching { optimizer.clean(forged, now + 1_000L) }
            assertTrue(failure.isFailure)
            assertTrue(outside.exists())
            assertTrue(inside.exists())
        } finally {
            workspace.deleteRecursively()
        }
    }

    @Test
    fun `plan cannot be replayed against a different cache root`() {
        val workspace = Files.createTempDirectory("romverse-cache-root-bind").toFile()
        try {
            val firstRoot = workspace.resolve("first-cache").apply { mkdirs() }
            val secondRoot = workspace.resolve("second-cache").apply { mkdirs() }
            val now = 10L * day
            val first = firstRoot.resolve("same.tmp").apply { writeText("same bytes") }
            val second = secondRoot.resolve("same.tmp").apply { writeText("same bytes") }
            val modified = FileTime.fromMillis(now - 2L * day)
            Files.setLastModifiedTime(first.toPath(), modified)
            Files.setLastModifiedTime(second.toPath(), modified)
            val optimizer = CompanionCacheOptimizer(workspace.resolve("receipts"))
            val plan = optimizer.preview(firstRoot, now)

            val failure = runCatching {
                optimizer.clean(plan.copy(root = secondRoot.canonicalFile), now + 1_000L)
            }
            assertTrue(failure.isFailure)
            assertTrue(first.exists())
            assertTrue(second.exists())
        } finally {
            workspace.deleteRecursively()
        }
    }

    @Test
    fun `tampered cleanup receipt is rejected`() {
        val workspace = Files.createTempDirectory("romverse-cache-receipt").toFile()
        try {
            val cache = workspace.resolve("cache").apply { mkdirs() }
            val receipts = workspace.resolve("receipts")
            val now = 10L * day
            val stale = cache.resolve("stale.tmp").apply { writeText("stale") }
            Files.setLastModifiedTime(stale.toPath(), FileTime.fromMillis(now - 2L * day))
            val optimizer = CompanionCacheOptimizer(receipts)
            optimizer.clean(optimizer.preview(cache, now), now + 1_000L)
            val latest = receipts.resolve("latest-cleanup.romverse")
            latest.writeText(latest.readText().replace("files_removed=1", "files_removed=9"))

            val loaded = optimizer.loadLatestReceipt()
            assertFalse(loaded.valid)
            assertTrue(loaded.reason.contains("integrity mismatch"))
        } finally {
            workspace.deleteRecursively()
        }
    }

    @Test
    fun `same size and timestamp content change is preserved`() {
        val workspace = Files.createTempDirectory("romverse-cache-digest").toFile()
        try {
            val cache = workspace.resolve("cache").apply { mkdirs() }
            val now = 10L * day
            val stale = cache.resolve("stale.tmp").apply { writeText("before") }
            val oldTime = FileTime.fromMillis(now - 2L * day)
            Files.setLastModifiedTime(stale.toPath(), oldTime)
            val optimizer = CompanionCacheOptimizer(workspace.resolve("receipts"))
            val plan = optimizer.preview(cache, now)
            stale.writeText("after!")
            Files.setLastModifiedTime(stale.toPath(), oldTime)

            val result = optimizer.clean(plan, now + 1_000L)

            assertTrue(stale.exists())
            assertEquals(0, result.filesRemoved)
            assertEquals(1, result.changedOrMissing)
        } finally {
            workspace.deleteRecursively()
        }
    }

    @Test
    fun `candidate replaced by link is preserved with its outside target`() {
        val workspace = Files.createTempDirectory("romverse-cache-link-swap").toFile()
        try {
            val cache = workspace.resolve("cache").apply { mkdirs() }
            val now = 10L * day
            val stale = cache.resolve("stale.tmp").apply { writeText("stale") }
            Files.setLastModifiedTime(stale.toPath(), FileTime.fromMillis(now - 2L * day))
            val outside = workspace.resolve("outside.tmp").apply { writeText("outside") }
            val optimizer = CompanionCacheOptimizer(workspace.resolve("receipts"))
            val plan = optimizer.preview(cache, now)
            stale.delete()
            Files.createSymbolicLink(stale.toPath(), outside.toPath())

            val result = optimizer.clean(plan, now + 1_000L)

            assertTrue(Files.isSymbolicLink(stale.toPath()))
            assertTrue(outside.exists())
            assertEquals(0, result.filesRemoved)
            assertEquals(1, result.unsafePreserved)
        } finally {
            workspace.deleteRecursively()
        }
    }

    @Test
    fun `oversized stale file and linked cache root are rejected safely`() {
        val workspace = Files.createTempDirectory("romverse-cache-boundaries").toFile()
        try {
            val cache = workspace.resolve("cache").apply { mkdirs() }
            val now = 10L * day
            val oversized = cache.resolve("oversized.tmp")
            java.io.RandomAccessFile(oversized, "rw").use {
                it.setLength(CompanionCacheOptimizer.MAX_FILE_BYTES + 1L)
            }
            Files.setLastModifiedTime(oversized.toPath(), FileTime.fromMillis(now - 2L * day))
            val optimizer = CompanionCacheOptimizer(workspace.resolve("receipts"))

            val plan = optimizer.preview(cache, now)

            assertTrue(plan.candidates.isEmpty())
            assertEquals(1, plan.skippedUnsafe)
            assertTrue(oversized.exists())
            val linkedRoot = workspace.resolve("linked-cache")
            Files.createSymbolicLink(linkedRoot.toPath(), cache.toPath())
            assertTrue(runCatching { optimizer.preview(linkedRoot, now) }.isFailure)
        } finally {
            workspace.deleteRecursively()
        }
    }

    @Test
    fun `deletion result remains unverified when receipt storage fails`() {
        val workspace = Files.createTempDirectory("romverse-cache-storage-failure").toFile()
        try {
            val cache = workspace.resolve("cache").apply { mkdirs() }
            val receiptBlocker = workspace.resolve("receipt-blocker").apply {
                writeText("not a directory")
            }
            val now = 10L * day
            val stale = cache.resolve("stale.tmp").apply { writeText("stale") }
            Files.setLastModifiedTime(stale.toPath(), FileTime.fromMillis(now - 2L * day))
            val optimizer = CompanionCacheOptimizer(receiptBlocker)

            val result = optimizer.clean(optimizer.preview(cache, now), now + 1_000L)

            assertFalse(stale.exists())
            assertEquals(1, result.filesRemoved)
            assertFalse(result.receiptSaved)
            assertTrue(result.receiptError.isNotBlank())
        } finally {
            workspace.deleteRecursively()
        }
    }

    @Test
    fun `correctly redigested receipt cannot change its evidence identifier`() {
        val workspace = Files.createTempDirectory("romverse-cache-resealed-receipt").toFile()
        try {
            val cache = workspace.resolve("cache").apply { mkdirs() }
            val receipts = workspace.resolve("receipts")
            val now = 10L * day
            val stale = cache.resolve("stale.tmp").apply { writeText("stale") }
            Files.setLastModifiedTime(stale.toPath(), FileTime.fromMillis(now - 2L * day))
            val optimizer = CompanionCacheOptimizer(receipts)
            optimizer.clean(optimizer.preview(cache, now), now + 1_000L)
            val latest = receipts.resolve("latest-cleanup.romverse")
            val fields = latest.readLines().associate { line ->
                line.substringBefore('=') to line.substringAfter('=')
            }.toMutableMap()
            fields["receipt_id"] = "b".repeat(24)
            val unsigned = fields.filterKeys { it != "receipt_digest" }
            val canonical = unsigned.toSortedMap().entries.joinToString("\n", postfix = "\n") {
                "${it.key}=${it.value}"
            }
            fields["receipt_digest"] = MessageDigest.getInstance("SHA-256")
                .digest(canonical.toByteArray())
                .joinToString("") { "%02x".format(it) }
            latest.writeText(
                fields.toSortedMap().entries.joinToString("\n", postfix = "\n") {
                    "${it.key}=${it.value}"
                }
            )

            val loaded = optimizer.loadLatestReceipt()

            assertFalse(loaded.valid)
            assertTrue(loaded.reason.contains("identifier does not match"))
        } finally {
            workspace.deleteRecursively()
        }
    }
}
