package com.radforge.romverse.companion

/** Stable navigation contract for the approved Galaxy shell. */
internal enum class CompanionDestination(val label: String) {
    HOME("Home"),
    LINK("Link"),
    LIVE_CONSOLE("Live Console"),
    VITALIS("Vitalis"),
    MORE("More"),
    LIFELINE("Lifeline"),
    DEVICE_DNA("Device DNA"),
    ASCENSION_PROTOCOL("Ascension"),
    APP_LAUNCHPAD("App Launchpad"),
    MEMBERS("Members"),
    GALAXY("Galaxy"),
    SETTINGS("Settings"),
    ABOUT("About"),
}

/** Activity-safe route tokens. They contain no user data and never grant operation authority. */
internal enum class CompanionRoute(
    val sectionTitle: String? = null,
    val restoredDetail: String = "",
) {
    HOME,
    LINK,
    LIVE_CONSOLE(
        "LIVE CONSOLE",
        "Genuine Desktop mission and Guardian evidence received through ROMVERSE Link.",
    ),
    VITALIS("VITALIS", "Live health evidence and Guardian-safe diagnostics."),
    LIFELINE("LIFELINE", "Read-only System Scan and guided repair knowledge."),
    APP_LAUNCHPAD("APP LAUNCHPAD", "Stage, fingerprint, and review APK packages safely."),
    MEMBERS("ROMVERSE MEMBERS", "Secure browser sign-in and server-verified membership status."),
    GALAXY("ROMVERSE GALAXY", "Private local forum for ROM builds, troubleshooting, Recipes, and ideas."),
    SETTINGS(
        "ROMVERSE SETTINGS",
        "Control online intelligence, privacy, accessibility, and account service configuration.",
    ),
    ABOUT(
        "ABOUT ROMVERSE COMPANION",
        "ROMVERSE Companion\nBuild. Optimize. Perfect.\n\nA RadForge Labs Project",
    ),
    DEVICE_PORTAL("HOME", "Device Portal restored from the last visible Companion route."),
    DEVICE_DNA(
        "DEVICE DNA",
        "Evidence-backed Desktop device and firmware capabilities. No phone-control authority is transferred.",
    ),
    DEVICE_ATLAS(
        "DEVICE ATLAS",
        "Search integrity-checked OEM knowledge and authoritative references. Read-only guidance never grants build or flash authority.",
    ),
    FIRST_BOOT_GUIDE(
        "FIRST BOOT GUIDE",
        "Offline, user-reviewed guidance after a ROM starts. Review does not claim a subsystem passed.",
    ),
    ASCENSION_PROTOCOL(
        "ASCENSION PROTOCOL",
        "Follow Desktop root preparation with Guardian proof at every stage.",
    ),
    ;

    companion object {
        fun fromSectionTitle(title: String): CompanionRoute =
            entries.firstOrNull { it.sectionTitle == title } ?: HOME

        fun fromSavedToken(token: String?): CompanionRoute =
            entries.firstOrNull { it.name == token } ?: HOME
    }
}

internal object CompanionNavigation {
    val bottomDestinations = listOf(
        CompanionDestination.HOME,
        CompanionDestination.LINK,
        CompanionDestination.LIVE_CONSOLE,
        CompanionDestination.VITALIS,
        CompanionDestination.MORE,
    )

    val drawerDestinations = listOf(
        CompanionDestination.LIFELINE,
        CompanionDestination.DEVICE_DNA,
        CompanionDestination.ASCENSION_PROTOCOL,
        CompanionDestination.APP_LAUNCHPAD,
        CompanionDestination.MEMBERS,
        CompanionDestination.GALAXY,
        CompanionDestination.SETTINGS,
        CompanionDestination.ABOUT,
    )

    val navigableDestinations = bottomDestinations
        .filterNot { it == CompanionDestination.MORE } + drawerDestinations

    init {
        check(bottomDestinations.first() == CompanionDestination.HOME)
        check((bottomDestinations + drawerDestinations).count { it == CompanionDestination.HOME } == 1)
        check(bottomDestinations.toSet().intersect(drawerDestinations.toSet()).isEmpty())
        check(navigableDestinations.toSet() == CompanionDestination.entries.toSet() - CompanionDestination.MORE)
    }
}

internal fun CompanionRoute.needsTelemetryHydration(
    hasAscension: Boolean,
    hasLiveConsole: Boolean,
    hasDeviceDna: Boolean,
): Boolean = when (this) {
    CompanionRoute.ASCENSION_PROTOCOL -> !hasAscension
    CompanionRoute.LIVE_CONSOLE -> !hasLiveConsole
    CompanionRoute.DEVICE_DNA -> !hasDeviceDna
    else -> false
}
