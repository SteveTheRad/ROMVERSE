package com.radforge.romverse.companion

import java.time.LocalDate
import java.time.temporal.ChronoUnit

data class AtlasSource(
    val sourceId: String,
    val label: String,
    val authority: String,
    val scope: String,
    val verifiedOn: String,
    val url: String,
) {
    fun isStale(asOf: LocalDate = LocalDate.now(), maximumAgeDays: Long = 180): Boolean =
        ChronoUnit.DAYS.between(LocalDate.parse(verifiedOn), asOf) > maximumAgeDays
}

data class CompanionDevicePack(
    val packId: String,
    val version: String,
    val packSha256: String,
    val priority: Int,
    val displayName: String,
    val manufacturers: Set<String>,
    val modelPatterns: Set<String>,
    val productPatterns: Set<String>,
    val sources: List<AtlasSource>,
    val boundary: String,
) {
    fun reportText(): String = buildString {
        appendLine("$displayName  •  $packId v$version")
        appendLine("Pack SHA-256: ${packSha256.take(16)}…")
        appendLine(boundary)
        appendLine()
        appendLine("AUTHORITATIVE REFERENCES")
        sources.forEach { source ->
            appendLine("• ${source.label} — ${source.authority}")
            appendLine(
                "  ${source.scope} • checked ${source.verifiedOn} • " +
                    if (source.isStale()) "REVIEW DUE" else "SOURCE CURRENT"
            )
            appendLine("  ${source.url}")
        }
        appendLine()
        append("Execution authority: NONE. Exact model/build/recovery evidence is still required by ROMVERSE Desktop and Guardian.")
    }
}

data class CompanionAtlasResolution(
    val pack: CompanionDevicePack,
    val reason: String,
    val matched: Boolean,
    val ambiguous: Boolean,
) {
    fun reportText(): String = buildString {
        appendLine(if (ambiguous) "RESOLUTION BLOCKED" else "RESOLUTION")
        appendLine(reason)
        appendLine()
        append(pack.reportText())
    }
}

data class CompanionExactIdentity(
    val packId: String,
    val packSha256: String,
    val priority: Int,
    val marketingName: String,
    val manufacturers: Set<String>,
    val modelPatterns: Set<String>,
    val productPatterns: Set<String>,
)

data class CompanionDeviceIdentity(
    val displayName: String,
    val rawModel: String,
    val codename: String,
    val evidence: String,
    val verifiedExact: Boolean,
)

object CompanionDeviceAtlas {
    fun catalogStatus(): String =
        "${GeneratedDeviceAtlasPacks.catalogPackCount} integrity-checked Packs • " +
            "${GeneratedDeviceAtlasPacks.catalogSourceCount} authoritative references • " +
            "${GeneratedDeviceAtlasPacks.exactIdentityCount} exact identity record(s) • " +
            if (GeneratedDeviceAtlasPacks.catalogReviewDueCount == 0) {
                "sources current"
            } else {
                "${GeneratedDeviceAtlasPacks.catalogReviewDueCount} source review(s) due"
            }

    fun resolve(
        manufacturer: String,
        model: String = "",
        product: String = "",
    ): CompanionDevicePack = resolveDetailed(manufacturer, model, product).pack

    fun identify(
        manufacturer: String,
        model: String,
        product: String,
    ): CompanionDeviceIdentity {
        val normalizedManufacturer = manufacturer.trim().lowercase()
        val normalizedModel = model.trim().lowercase()
        val normalizedProduct = product.trim().lowercase()
        if (isEmulatorIdentity(normalizedModel, normalizedProduct)) {
            return CompanionDeviceIdentity(
                displayName = "Android Emulator",
                rawModel = model.trim().ifBlank { "Android SDK emulator" },
                codename = product.trim(),
                evidence = "Android SDK emulator markers detected; physical device identity is not applicable.",
                verifiedExact = false,
            )
        }
        val candidates = GeneratedDeviceAtlasPacks.exactIdentities.filter { identity ->
            normalizedManufacturer in identity.manufacturers &&
                identity.modelPatterns.any { globMatches(normalizedModel, it) } &&
                identity.productPatterns.any { globMatches(normalizedProduct, it) }
        }
        val highestPriority = candidates.maxOfOrNull { it.priority }
        val leaders = candidates.filter { it.priority == highestPriority }
        if (leaders.size == 1) {
            val identity = leaders.single()
            return CompanionDeviceIdentity(
                identity.marketingName,
                model.trim(),
                product.trim(),
                "Exact Device Pack ${identity.packId} • ${identity.packSha256.take(16)}…",
                verifiedExact = true,
            )
        }
        val rawModel = model.trim().ifBlank { "Unknown Android model" }
        val maker = manufacturer.trim()
        val display = if (
            maker.isBlank() || rawModel.startsWith(maker, ignoreCase = true)
        ) rawModel else "$maker $rawModel"
        val reason = if (leaders.size > 1) {
            "Exact identity is ambiguous; ROMVERSE kept the reported model unconfirmed."
        } else {
            "No exact identity record matched; ROMVERSE kept the Android-reported model unconfirmed."
        }
        return CompanionDeviceIdentity(
            display,
            rawModel,
            product.trim(),
            reason,
            verifiedExact = false,
        )
    }

    fun search(query: String, limit: Int = 25): List<CompanionDevicePack> {
        require(limit in 1..50) { "Device Atlas result limit is outside the safe boundary." }
        val normalized = query.trim().lowercase()
        return (GeneratedDeviceAtlasPacks.oemPacks + GeneratedDeviceAtlasPacks.generic)
            .asSequence()
            .filter { pack ->
                normalized.isBlank() || sequenceOf(
                    pack.packId,
                    pack.displayName,
                    pack.manufacturers.joinToString(" "),
                    pack.modelPatterns.joinToString(" "),
                    pack.productPatterns.joinToString(" "),
                    pack.sources.joinToString(" ") { "${it.label} ${it.authority} ${it.scope}" },
                ).any { normalized in it.lowercase() }
            }
            .sortedWith(compareByDescending<CompanionDevicePack> { it.priority }
                .thenBy { it.displayName })
            .take(limit)
            .toList()
    }

    fun resolveDetailed(
        manufacturer: String,
        model: String = "",
        product: String = "",
    ): CompanionAtlasResolution = resolveFromCatalog(
        manufacturer,
        model,
        product,
        GeneratedDeviceAtlasPacks.oemPacks,
        GeneratedDeviceAtlasPacks.generic,
    )

    internal fun resolveFromCatalog(
        manufacturer: String,
        model: String,
        product: String,
        oemPacks: List<CompanionDevicePack>,
        generic: CompanionDevicePack,
    ): CompanionAtlasResolution {
        val normalized = manufacturer.trim().lowercase()
        val normalizedModel = model.trim().lowercase()
        val normalizedProduct = product.trim().lowercase()
        if (isEmulatorIdentity(normalizedModel, normalizedProduct)) {
            return CompanionAtlasResolution(
                generic,
                "Android SDK emulator markers detected; using generic read-only knowledge without claiming physical-device compatibility.",
                matched = true,
                ambiguous = false,
            )
        }
        val candidates = oemPacks.filter {
            normalized in it.manufacturers &&
                (it.modelPatterns.isEmpty() || it.modelPatterns.any { pattern -> globMatches(normalizedModel, pattern) }) &&
                (it.productPatterns.isEmpty() || it.productPatterns.any { pattern -> globMatches(normalizedProduct, pattern) })
        }
        if (candidates.isEmpty()) {
            return CompanionAtlasResolution(
                generic,
                "No OEM-specific Pack matched; using the integrity-checked Generic Android read-only fallback.",
                matched = true,
                ambiguous = false,
            )
        }
        val priority = candidates.maxOf { it.priority }
        val leaders = candidates.filter { it.priority == priority }
        if (leaders.size != 1) {
            val identities = leaders.map { it.packId }.sorted().joinToString(", ")
            return CompanionAtlasResolution(
                generic,
                "Ambiguous Device Pack match at priority $priority: $identities. OEM-specific context was withheld.",
                matched = false,
                ambiguous = true,
            )
        }
        return CompanionAtlasResolution(
            leaders.single(),
            "Resolved the highest-priority exact or OEM Pack without ambiguity.",
            matched = true,
            ambiguous = false,
        )
    }

    private fun globMatches(value: String, pattern: String): Boolean {
        if (pattern == "*") return true
        val expression = buildString {
            pattern.forEach { character ->
                if (character == '*') append(".*") else append(Regex.escape(character.toString()))
            }
        }
        return Regex("^$expression$").matches(value)
    }

    private fun isEmulatorIdentity(model: String, product: String): Boolean =
        model.startsWith("sdk_gphone") || model == "android sdk built for x86" ||
            product.startsWith("sdk_gphone")
}
