package com.radforge.romverse.companion

internal enum class CompanionDisplayMode(val persistedValue: String) {
    COSMIC("cosmic"),
    OLED("oled"),
    ;

    companion object {
        fun parse(value: String?): CompanionDisplayMode =
            entries.firstOrNull { it.persistedValue == value } ?: COSMIC
    }
}

internal data class CompanionDisplayPalette(
    val panel: String,
    val sectionSurface: String,
    val cosmicGradient: List<String>,
    val cardGradient: List<String>,
    val sidebarGradient: List<String>,
    val barGradient: List<String>,
    val navigationIdle: String,
    val navigationPressed: String,
    val ambientNebula: Boolean,
)

internal object CompanionDisplayPolicy {
    fun palette(mode: CompanionDisplayMode): CompanionDisplayPalette = when (mode) {
        CompanionDisplayMode.COSMIC -> CompanionDisplayPalette(
            panel = "#05090F",
            sectionSurface = "#010307",
            cosmicGradient = listOf("#010307", "#040812", "#060712"),
            cardGradient = listOf("#E00A0E18", "#D40B1222", "#D0060C16"),
            sidebarGradient = listOf("#E602050A", "#DA080E20", "#CE140D2B", "#DC061725"),
            barGradient = listOf("#F2050A12", "#E8121125", "#E0061B2A"),
            navigationIdle = "#030811",
            navigationPressed = "#101A2C",
            ambientNebula = true,
        )
        CompanionDisplayMode.OLED -> CompanionDisplayPalette(
            panel = "#000000",
            sectionSurface = "#000000",
            cosmicGradient = listOf("#000000", "#000000", "#000000"),
            cardGradient = listOf("#FA000000", "#F5000000", "#F0000000"),
            sidebarGradient = listOf("#FF000000", "#FA000000", "#F5000000", "#FF000000"),
            barGradient = listOf("#FF000000", "#FA000000", "#F5000000"),
            navigationIdle = "#000000",
            navigationPressed = "#0A1020",
            ambientNebula = false,
        )
    }
}
