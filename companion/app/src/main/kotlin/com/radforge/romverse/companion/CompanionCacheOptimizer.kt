package com.radforge.romverse.companion

import java.io.File
import java.io.FileOutputStream
import java.io.ByteArrayOutputStream
import java.nio.file.Files
import java.nio.file.LinkOption
import java.nio.file.StandardCopyOption
import java.security.MessageDigest
import java.util.UUID

internal data class CacheCandidate(
    val relativePath: String,
    val sizeBytes: Long,
    val modifiedAtEpochMs: Long,
    val sha256: String,
)

internal data class CacheCleanupPlan(
    val root: File,
    val createdAtEpochMs: Long,
    val minimumAgeMs: Long,
    val candidates: List<CacheCandidate>,
    val skippedRecent: Int,
    val skippedUnsafe: Int,
    val planDigest: String,
) {
    val totalBytes: Long get() = candidates.sumOf { it.sizeBytes }
}

internal data class CacheCleanupResult(
    val filesRemoved: Int,
    val bytesRecovered: Long,
    val changedOrMissing: Int,
    val unsafePreserved: Int,
    val receiptId: String,
    val receiptSaved: Boolean,
    val receiptError: String = "",
)

internal data class CacheReceiptRead(
    val valid: Boolean,
    val integrityVerified: Boolean,
    val reason: String,
    val fields: Map<String, String> = emptyMap(),
)

internal class CompanionCacheOptimizer(
    private val receiptRoot: File,
    private val minimumAgeMs: Long = 24L * 60L * 60L * 1_000L,
) {
    companion object {
        const val MAX_SCANNED_FILES = 10_000
        const val MAX_CANDIDATES = 5_000
        const val MAX_CANDIDATE_BYTES = 512L * 1024L * 1024L
        const val MAX_FILE_BYTES = 128L * 1024L * 1024L
        private const val RECEIPT_FORMAT = "romverse.companion-cache-cleanup"
        private const val RECEIPT_VERSION = "1"
    }

    init {
        require(minimumAgeMs >= 60_000L) { "Cache safety window is too short" }
    }

    fun preview(cacheRoot: File, nowEpochMs: Long = System.currentTimeMillis()): CacheCleanupPlan {
        require(nowEpochMs > 0L) { "Preview time must be positive" }
        if (!cacheRoot.exists()) cacheRoot.mkdirs()
        require(cacheRoot.isDirectory && !Files.isSymbolicLink(cacheRoot.toPath())) {
            "Companion cache root is not a safe directory"
        }
        val root = cacheRoot.canonicalFile
        val rootPath = root.toPath()
        val candidates = mutableListOf<CacheCandidate>()
        var scanned = 0
        var skippedRecent = 0
        var skippedUnsafe = 0
        var candidateBytes = 0L
        Files.walk(rootPath).use { stream ->
            stream.sorted().forEach { path ->
                if (path == rootPath) return@forEach
                if (Files.isSymbolicLink(path)) {
                    skippedUnsafe++
                    return@forEach
                }
                if (!Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS)) {
                    if (!Files.isDirectory(path, LinkOption.NOFOLLOW_LINKS)) skippedUnsafe++
                    return@forEach
                }
                scanned++
                require(scanned <= MAX_SCANNED_FILES) { "Companion cache contains too many files" }
                val attributes = Files.readAttributes(
                    path,
                    java.nio.file.attribute.BasicFileAttributes::class.java,
                    LinkOption.NOFOLLOW_LINKS,
                )
                val age = nowEpochMs - attributes.lastModifiedTime().toMillis()
                if (age < minimumAgeMs) {
                    skippedRecent++
                    return@forEach
                }
                if (attributes.size() > MAX_FILE_BYTES) {
                    skippedUnsafe++
                    return@forEach
                }
                val relative = rootPath.relativize(path.normalize()).toString()
                    .replace(File.separatorChar, '/')
                require(isSafeRelative(relative)) { "Cache candidate escaped its root" }
                candidateBytes += attributes.size()
                require(candidateBytes <= MAX_CANDIDATE_BYTES) {
                    "Companion cache preview exceeds the safe byte limit"
                }
                require(candidates.size < MAX_CANDIDATES) {
                    "Companion cache preview contains too many candidates"
                }
                candidates += CacheCandidate(
                    relative,
                    attributes.size(),
                    attributes.lastModifiedTime().toMillis(),
                    fileSha256(path.toFile()),
                )
            }
        }
        val sorted = candidates.sortedBy { it.relativePath }
        val plan = CacheCleanupPlan(
            root,
            nowEpochMs,
            minimumAgeMs,
            sorted,
            skippedRecent,
            skippedUnsafe,
            "",
        )
        return plan.copy(planDigest = planDigest(plan))
    }

    fun clean(plan: CacheCleanupPlan, nowEpochMs: Long = System.currentTimeMillis()): CacheCleanupResult {
        require(nowEpochMs >= plan.createdAtEpochMs) { "Cleanup time predates its preview" }
        require(plan.planDigest == planDigest(plan)) { "Cache cleanup plan integrity mismatch" }
        require(plan.candidates.size <= MAX_CANDIDATES && plan.totalBytes <= MAX_CANDIDATE_BYTES) {
            "Cache cleanup plan exceeds the safe boundary"
        }
        val root = plan.root.canonicalFile
        require(root == plan.root && root.isDirectory && !Files.isSymbolicLink(root.toPath())) {
            "Companion cache root changed after preview"
        }
        var filesRemoved = 0
        var bytesRecovered = 0L
        var changedOrMissing = 0
        var unsafePreserved = 0
        for (candidate in plan.candidates) {
            if (!isSafeRelative(candidate.relativePath)) {
                unsafePreserved++
                continue
            }
            val target = File(root, candidate.relativePath).normalize()
            if (!target.toPath().startsWith(root.toPath()) || hasSymlinkAncestor(root, target)) {
                unsafePreserved++
                continue
            }
            val attributes = runCatching {
                Files.readAttributes(
                    target.toPath(),
                    java.nio.file.attribute.BasicFileAttributes::class.java,
                    LinkOption.NOFOLLOW_LINKS,
                )
            }.getOrNull()
            if (attributes == null || !attributes.isRegularFile) {
                changedOrMissing++
                continue
            }
            val unchanged = attributes.size() == candidate.sizeBytes &&
                attributes.lastModifiedTime().toMillis() == candidate.modifiedAtEpochMs &&
                runCatching { fileSha256(target) }.getOrNull() == candidate.sha256
            if (!unchanged) {
                changedOrMissing++
                continue
            }
            if (runCatching { Files.delete(target.toPath()) }.isSuccess) {
                filesRemoved++
                bytesRecovered += candidate.sizeBytes
            } else {
                changedOrMissing++
            }
        }
        val receiptId = sha256("${plan.planDigest}:$nowEpochMs").take(24)
        val receipt = linkedMapOf(
            "format" to RECEIPT_FORMAT,
            "schema_version" to RECEIPT_VERSION,
            "receipt_id" to receiptId,
            "created_at_epoch_ms" to nowEpochMs.toString(),
            "plan_digest" to plan.planDigest,
            "files_removed" to filesRemoved.toString(),
            "bytes_recovered" to bytesRecovered.toString(),
            "changed_or_missing_preserved" to changedOrMissing.toString(),
            "unsafe_preserved" to unsafePreserved.toString(),
            "scope" to "companion-cache-only",
            "other_apps_modified" to "false",
            "device_command_executed" to "false",
        )
        return runCatching {
            writeReceipt(receipt)
            val verified = loadLatestReceipt()
            require(verified.valid && verified.fields["receipt_id"] == receiptId) {
                "Cleanup receipt failed post-write verification"
            }
            CacheCleanupResult(
                filesRemoved,
                bytesRecovered,
                changedOrMissing,
                unsafePreserved,
                receiptId,
                true,
            )
        }.getOrElse {
            CacheCleanupResult(
                filesRemoved,
                bytesRecovered,
                changedOrMissing,
                unsafePreserved,
                receiptId,
                false,
                it.message ?: "Receipt could not be saved",
            )
        }
    }

    fun loadLatestReceipt(): CacheReceiptRead {
        val path = File(receiptRoot, "latest-cleanup.romverse")
        if (!path.isFile || Files.isSymbolicLink(path.toPath())) {
            return CacheReceiptRead(false, false, "Cleanup receipt is missing or unsafe")
        }
        return runCatching {
            require(path.length() in 1..65_536) { "Cleanup receipt size is invalid" }
            val encoded = readBounded(path, 65_536)
            require(encoded.size in 1..65_536) { "Cleanup receipt size is invalid" }
            val content = encoded.toString(Charsets.UTF_8)
            require(content.endsWith('\n')) { "Cleanup receipt terminator is invalid" }
            val lines = content.dropLast(1).split('\n')
            val fields = lines.associate { line ->
                val split = line.indexOf('=')
                require(split > 0) { "Cleanup receipt line is malformed" }
                line.substring(0, split) to line.substring(split + 1)
            }
            val requiredFields = setOf(
                "format",
                "schema_version",
                "receipt_id",
                "created_at_epoch_ms",
                "plan_digest",
                "files_removed",
                "bytes_recovered",
                "changed_or_missing_preserved",
                "unsafe_preserved",
                "scope",
                "other_apps_modified",
                "device_command_executed",
                "receipt_digest",
            )
            require(lines.size == requiredFields.size && fields.keys == requiredFields) {
                "Cleanup receipt fields are invalid"
            }
            require(fields["format"] == RECEIPT_FORMAT && fields["schema_version"] == RECEIPT_VERSION) {
                "Cleanup receipt format is unsupported"
            }
            require(fields["scope"] == "companion-cache-only") { "Cleanup receipt scope is invalid" }
            require(fields["other_apps_modified"] == "false") { "Cleanup receipt scope claim is invalid" }
            require(fields["device_command_executed"] == "false") { "Cleanup receipt execution claim is invalid" }
            require(fields.getValue("receipt_id").isLowerHex(24)) {
                "Cleanup receipt identifier is invalid"
            }
            require(fields.getValue("plan_digest").isLowerHex(64)) {
                "Cleanup receipt plan fingerprint is invalid"
            }
            require(fields.getValue("created_at_epoch_ms").toLong() > 0L) {
                "Cleanup receipt timestamp is invalid"
            }
            require(fields.getValue("files_removed").toInt() in 0..MAX_CANDIDATES) {
                "Cleanup receipt file count is invalid"
            }
            require(fields.getValue("bytes_recovered").toLong() in 0..MAX_CANDIDATE_BYTES) {
                "Cleanup receipt byte count is invalid"
            }
            require(fields.getValue("changed_or_missing_preserved").toInt() in 0..MAX_CANDIDATES) {
                "Cleanup receipt changed-file count is invalid"
            }
            require(fields.getValue("unsafe_preserved").toInt() in 0..MAX_CANDIDATES) {
                "Cleanup receipt unsafe-file count is invalid"
            }
            val removed = fields.getValue("files_removed").toInt()
            val changed = fields.getValue("changed_or_missing_preserved").toInt()
            val unsafe = fields.getValue("unsafe_preserved").toInt()
            require(removed + changed + unsafe <= MAX_CANDIDATES) {
                "Cleanup receipt result counts are inconsistent"
            }
            val recovered = fields.getValue("bytes_recovered").toLong()
            require(removed != 0 || recovered == 0L) {
                "Cleanup receipt recovered-byte claim is inconsistent"
            }
            val expectedReceiptId = sha256(
                "${fields.getValue("plan_digest")}:${fields.getValue("created_at_epoch_ms")}"
            ).take(24)
            require(fields.getValue("receipt_id") == expectedReceiptId) {
                "Cleanup receipt identifier does not match its evidence"
            }
            val expected = fields["receipt_digest"].orEmpty()
            require(expected.isLowerHex(64)) {
                "Cleanup receipt fingerprint is invalid"
            }
            val unsigned = fields.filterKeys { it != "receipt_digest" }
            val actual = sha256(canonicalFields(unsigned))
            require(MessageDigest.isEqual(expected.toByteArray(), actual.toByteArray())) {
                "Cleanup receipt integrity mismatch"
            }
            CacheReceiptRead(true, true, "Cleanup receipt integrity verified", fields)
        }.getOrElse {
            CacheReceiptRead(false, false, it.message ?: "Cleanup receipt is invalid")
        }
    }

    private fun writeReceipt(fields: LinkedHashMap<String, String>) {
        receiptRoot.mkdirs()
        require(receiptRoot.isDirectory && !Files.isSymbolicLink(receiptRoot.toPath())) {
            "Cleanup receipt directory is unsafe"
        }
        val contentFields = LinkedHashMap(fields)
        contentFields["receipt_digest"] = sha256(canonicalFields(fields))
        val content = canonicalFields(contentFields)
        val latest = File(receiptRoot, "latest-cleanup.romverse")
        val history = File(receiptRoot, "cleanup-${fields.getValue("receipt_id")}.romverse")
        atomicWrite(history, content)
        atomicWrite(latest, content)
    }

    private fun atomicWrite(path: File, content: String) {
        val temporary = File(path.parentFile, ".${path.name}.${UUID.randomUUID()}.tmp")
        try {
            FileOutputStream(temporary).use { stream ->
                stream.write(content.toByteArray(Charsets.UTF_8))
                stream.fd.sync()
            }
            runCatching {
                Files.move(
                    temporary.toPath(),
                    path.toPath(),
                    StandardCopyOption.ATOMIC_MOVE,
                    StandardCopyOption.REPLACE_EXISTING,
                )
            }.getOrElse {
                Files.move(
                    temporary.toPath(),
                    path.toPath(),
                    StandardCopyOption.REPLACE_EXISTING,
                )
            }
        } finally {
            temporary.delete()
        }
    }

    private fun planDigest(plan: CacheCleanupPlan): String {
        val candidates = plan.candidates.joinToString(";") {
            "${it.relativePath.length}:${it.relativePath},${it.sizeBytes},${it.modifiedAtEpochMs},${it.sha256}"
        }
        return sha256(
            "romverse.companion-cache-plan|1|${sha256(plan.root.canonicalPath)}|" +
                "${plan.createdAtEpochMs}|${plan.minimumAgeMs}|" +
                "${plan.skippedRecent}|${plan.skippedUnsafe}|$candidates"
        )
    }

    private fun hasSymlinkAncestor(root: File, target: File): Boolean {
        var cursor = root.toPath()
        for (part in root.toPath().relativize(target.toPath())) {
            cursor = cursor.resolve(part)
            if (Files.isSymbolicLink(cursor)) return true
        }
        return false
    }

    private fun isSafeRelative(value: String): Boolean {
        if (value.isBlank() || value.startsWith('/') || value.startsWith('\\')) return false
        val segments = value.replace('\\', '/').split('/')
        return segments.none { it.isBlank() || it == "." || it == ".." || it.any(Char::isISOControl) }
    }

    private fun fileSha256(file: File): String {
        val digest = MessageDigest.getInstance("SHA-256")
        file.inputStream().buffered().use { input ->
            val buffer = ByteArray(64 * 1024)
            while (true) {
                val count = input.read(buffer)
                if (count < 0) break
                digest.update(buffer, 0, count)
            }
        }
        return digest.digest().joinToString("") { "%02x".format(it) }
    }

    private fun readBounded(file: File, maximumBytes: Int): ByteArray {
        val output = ByteArrayOutputStream()
        file.inputStream().buffered().use { input ->
            val buffer = ByteArray(8 * 1024)
            while (true) {
                val count = input.read(buffer)
                if (count < 0) break
                require(output.size() + count <= maximumBytes) {
                    "Cleanup receipt size is invalid"
                }
                output.write(buffer, 0, count)
            }
        }
        return output.toByteArray()
    }

    private fun canonicalFields(fields: Map<String, String>): String = fields.toSortedMap()
        .entries.joinToString("\n", postfix = "\n") { "${it.key}=${it.value}" }

    private fun String.isLowerHex(length: Int): Boolean =
        this.length == length && all { it in "0123456789abcdef" }

    private fun sha256(value: String): String = MessageDigest.getInstance("SHA-256")
        .digest(value.toByteArray(Charsets.UTF_8))
        .joinToString("") { "%02x".format(it) }
}
