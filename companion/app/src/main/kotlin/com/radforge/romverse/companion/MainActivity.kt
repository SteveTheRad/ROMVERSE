package com.radforge.romverse.companion

import android.graphics.Color
import android.graphics.Canvas
import android.graphics.BitmapFactory
import android.graphics.LinearGradient
import android.graphics.Paint
import android.graphics.RadialGradient
import android.graphics.RectF
import android.graphics.Shader
import android.graphics.drawable.GradientDrawable
import android.graphics.drawable.ColorDrawable
import android.content.Intent
import android.content.IntentFilter
import android.content.ClipData
import android.content.ClipboardManager
import android.content.pm.PackageManager
import android.app.AlertDialog
import android.net.Uri
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.media.MediaPlayer
import android.provider.OpenableColumns
import android.provider.Settings
import android.hardware.usb.UsbManager
import android.app.ActivityManager
import android.os.BatteryManager
import android.os.Build
import android.os.Bundle
import android.os.Environment
import android.os.StatFs
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.view.Gravity
import android.view.HapticFeedbackConstants
import android.view.View
import android.view.WindowManager
import android.widget.LinearLayout
import android.widget.EditText
import android.widget.Button
import android.widget.CheckBox
import android.widget.ImageView
import android.widget.FrameLayout
import java.net.HttpURLConnection
import java.net.Inet6Address
import java.net.InetAddress
import java.net.SocketTimeoutException
import java.net.URL
import java.net.URLEncoder
import java.net.DatagramPacket
import java.net.DatagramSocket
import org.json.JSONArray
import org.json.JSONObject
import kotlin.math.abs
import kotlin.math.cos
import kotlin.math.roundToInt
import kotlin.math.sin
import android.widget.ScrollView
import android.widget.TextView
import android.widget.ProgressBar
import android.widget.RadioButton
import android.widget.RadioGroup
import android.content.res.ColorStateList
import android.text.InputType
import android.text.InputFilter
import androidx.activity.ComponentActivity
import androidx.activity.OnBackPressedCallback
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.view.GravityCompat
import androidx.core.view.ViewCompat
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.graphics.toColorInt
import androidx.core.widget.doAfterTextChanged
import androidx.drawerlayout.widget.DrawerLayout
import java.io.ByteArrayOutputStream
import java.security.MessageDigest
import java.util.Calendar
import java.util.Date
import java.util.UUID
import java.text.DateFormat
import javax.net.ssl.HttpsURLConnection

private data class PairStatus(
    val state: String,
    val sessionToken: String = "",
    val expiresInSeconds: Long = 0L,
)

private data class TelemetryResult(
    val summary: String? = null,
    val unauthorized: Boolean = false,
    val ascension: DesktopAscensionStatus? = null,
    val liveConsole: DesktopLiveConsoleStatus? = null,
    val deviceDna: DesktopDeviceDnaStatus? = null,
)

private data class SnapshotPostResult(
    val accepted: Boolean = false,
    val unauthorized: Boolean = false,
)

private data class CompanionOriginScene(
    val eyebrow: String,
    val title: String,
    val body: String,
    val constellation: String,
    val durationMs: Long,
)

class MainActivity : ComponentActivity() {
    private companion object {
        const val GALAXY_DRAFT_TITLE = "topic_draft_title_v1"
        const val GALAXY_DRAFT_BODY = "topic_draft_body_v1"
        const val ROMVERSE_WEBSITE_URL = "https://romverse.app/"
        const val RADFORGE_LABS_URL = "https://radforgelabs.com/"
        const val FACEBOOK_URL = "https://www.facebook.com/ROMVERSEOfficial"
        const val REDDIT_URL = "https://www.reddit.com/user/ROMVERSE/"
        const val ACTIVITY_ROUTE_KEY = "romverse_visible_route_v1"
        val ORIGIN_SCENES = listOf(
            CompanionOriginScene(
                "SCENE 01  •  THE BEGINNING",
                "EVERY PROJECT BEGINS WITH AN IDEA",
                "ROMVERSE began with a question.\n\n" +
                    "What if Android ROM development could be powerful without being intimidating?\n\n" +
                    "A distant point of light becomes the first shape of a new Android universe.",
                "IDEA  •  POSSIBILITY  •  BEGIN",
                11_000L,
            ),
            CompanionOriginScene(
                "SCENE 02  •  THE VISION",
                "A BETTER WAY TO BRING IT TOGETHER",
                "Not another collection of tools. A connected experience that helps people build, " +
                    "understand, protect, verify, and learn.\n\nROM Studio, Device DNA, Nexus, " +
                    "Guardian, and Companion share one purpose while the technology that protects " +
                    "their work remains private.",
                "BUILD  •  UNDERSTAND  •  PROTECT  •  VERIFY  •  LEARN",
                13_000L,
            ),
            CompanionOriginScene(
                "SCENE 03  •  THE ROMVERSE PROMISE",
                "REAL PROGRESS. REAL EVIDENCE.",
                "Never pretend something worked when it didn't.\n\n" +
                    "Never hide uncertainty behind a green tick.\n\n" +
                    "Never take control away from the person whose device it is.\n\n" +
                    "Build powerful automation without forgetting responsibility.\n\n" +
                    "Your device. Your decision.",
                "HONESTY  •  EVIDENCE  •  RESPONSIBILITY",
                16_000L,
            ),
            CompanionOriginScene(
                "SCENE 04  •  A MESSAGE FROM STEVETHERAD",
                "WHY ROMVERSE EXISTS",
                "ROMVERSE started as an idea I wanted to see exist.\n\n" +
                    "Something that could take the complicated world of Android ROM development " +
                    "and make it more understandable, more capable, and safer—without taking away " +
                    "the freedom that makes Android special.\n\n" +
                    "What began as an idea became a much bigger vision: a place where someone " +
                    "building their first ROM and someone who has been doing this for years can " +
                    "work with the same powerful tools, at their own level.\n\n" +
                    "ROMVERSE will continue to grow, learn, and improve. But no matter how advanced " +
                    "it becomes, I want it to remain true to the principles it started with.\n\n" +
                    "Respect the user. Respect the device. Be honest about what we know. Never fake " +
                    "success. And most importantly—never stop building.\n\n" +
                    "Thank you for being part of ROMVERSE.\n\n" +
                    "— SteveTheRad\nFounder & Creator of ROMVERSE",
                "RESPECT THE USER  •  RESPECT THE DEVICE",
                25_000L,
            ),
            CompanionOriginScene(
                "SCENE 05  •  THE COMMUNITY",
                "ONE IDEA CAN BECOME SOMETHING GREATER",
                "One point of light becomes several, then many. They are a symbol—not a fabricated " +
                    "user count.\n\nTo everyone who builds, tests, reports, creates, helps, and believes " +
                    "in what ROMVERSE can become: thank you.\n\nPersonal recognition appears only " +
                    "when genuine account evidence says it has been earned. ROMVERSE never invents " +
                    "a badge, membership milestone, or reward.",
                "BUILDERS  •  TESTERS  •  CREATORS  •  COMMUNITY",
                15_000L,
            ),
            CompanionOriginScene(
                "SCENE 06  •  THE FUTURE",
                "WE'RE ONLY GETTING STARTED",
                "Desktop, Companion, and Android device move together through one expanding universe.\n\n" +
                    "Build what wasn't possible yesterday.\n" +
                    "Understand what others leave unexplained.\n" +
                    "Protect what matters.\nPerfect what comes next.",
                "DESKTOP  •  COMPANION  •  ANDROID",
                14_000L,
            ),
            CompanionOriginScene(
                "THE ORIGIN  •  FINALE",
                "ROMVERSE",
                "BUILD. OPTIMIZE. PERFECT.\n\n" +
                    "Created by SteveTheRad\nA RadForge Labs Project\n\n" +
                    "Made for the people who refuse to stop tinkering.\n\n27.08.2026",
                "THE JOURNEY IS ONLY BEGINNING",
                13_000L,
            ),
        )
    }

    private val violet = "#B45CFF".toColorInt()
    private val cyan = "#28E7F5".toColorInt()
    private val muted = "#9AA5BD".toColorInt()
    private val panel: Int
        get() = displayPalette().panel.toColorInt()
    private val pairingPrefs by lazy { getSharedPreferences("pairing", MODE_PRIVATE) }
    private val linkSessionVault by lazy { LinkSessionVault(this, pairingPrefs) }
    private val draftPrefs by lazy { getSharedPreferences("community", MODE_PRIVATE) }
    private val activityPrefs by lazy { getSharedPreferences("activity", MODE_PRIVATE) }
    private val repairPrefs by lazy { getSharedPreferences("repair_session", MODE_PRIVATE) }
    private val optimizerPrefs by lazy { getSharedPreferences("optimizer_history", MODE_PRIVATE) }
    private val userSettingsPrefs by lazy { getSharedPreferences("romverse_settings", MODE_PRIVATE) }
    private val aboutPrefs by lazy { getSharedPreferences("about_romverse", MODE_PRIVATE) }
    private var activeCacheCleanupFlow: CacheCleanupUiFlow? = null
    private var activeCacheCleanupProgress: ProgressBar? = null
    private val localDeviceIdentity by lazy {
        CompanionDeviceAtlas.identify(Build.MANUFACTURER, Build.MODEL, Build.DEVICE)
    }
    private val starfieldLayers = mutableSetOf<StarfieldView>()
    private var batteryMetric: TextView? = null
    private var storageMetric: TextView? = null
    private var activityFeed: TextView? = null
    private val telemetryHandler = Handler(Looper.getMainLooper())
    private var telemetryHost: String? = null
    private var telemetryToken: String? = null
    private var telemetryCertificateSha256: String? = null
    private var desktopTelemetryView: TextView? = null
    @Volatile private var telemetryRefreshInFlight = false
    @Volatile private var linkDiscoveryInFlight = false
    private var linkAddressField: EditText? = null
    private var linkFingerprintField: EditText? = null
    private var linkSafetyLabel: TextView? = null
    private var telemetryRetryAttempt = 0
    private var activityResumed = false
    private var lastNetworkOnline = false
    private var desktopAscensionStatus: DesktopAscensionStatus? = null
    private var desktopLiveConsoleStatus: DesktopLiveConsoleStatus? = null
    private var desktopDeviceDnaStatus: DesktopDeviceDnaStatus? = null
    private var stagedApkUri: String? = null
    private var stagedApkName: String? = null
    private var stagedApkHash: String? = null
    private var apkDetailView: TextView? = null
    private var sectionPage: FrameLayout? = null
    private var sectionHost: FrameLayout? = null
    private var privacyCurtainPage: View? = null
    private var privacyCurtainState = CompanionPrivacyCurtainState(enabled = false)
    private var homeScroll: ScrollView? = null
    private var navigationDrawer: DrawerLayout? = null
    private var navigationTitleView: TextView? = null
    private var currentRoute = CompanionRoute.HOME
    private val navigationButtons = mutableMapOf<NavKind, MutableList<RomverseNavButton>>()
    private var pairSyncCard: View? = null
    private var greetingView: TextView? = null
    private var homeHeroEyebrow: TextView? = null
    private var homeHeroDetail: TextView? = null
    private var homeHeroLink: TextView? = null
    private var homeHeroGuardian: TextView? = null
    private var homeHeroMission: TextView? = null
    private var supporterOverlay: FrameLayout? = null
    private var supporterBackCallback: OnBackPressedCallback? = null
    private val supporterHandler = Handler(Looper.getMainLooper())
    private var supporterTick: Runnable? = null
    private var supporterMediaPlayer: MediaPlayer? = null
    private var nextActionTitle: TextView? = null
    private var nextActionButton: Button? = null
    private var latestRepairReport: String? = null
    private var networkStatusView: TextView? = null
    private val networkStatusHandler = Handler(Looper.getMainLooper())
    private val networkStatusRefresh = object : Runnable {
        override fun run() {
            updateNetworkStatus()
            networkStatusHandler.postDelayed(this, 15_000L)
        }
    }
    private var galaxyIntegrityStatus = "No local Galaxy data saved yet."
    private var galaxyIntegrityVerified = false
    private var galaxyDataExists = false
    private var galaxyDetailView: TextView? = null
    private var memberDetailView: TextView? = null
    private var memberDiscovery: CompanionMembersDiscovery? = null
    private var memberAuthorization: CompanionDeviceAuthorization? = null
    private var memberSession: CompanionMemberSession? = null
    private var memberPollDelaySeconds = 5
    private val memberHandler = Handler(Looper.getMainLooper())
    private val apkPicker = registerForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        uri?.let(::stageApk)
    }
    private val galaxyArchiveExporter = registerForActivityResult(
        ActivityResultContracts.CreateDocument("application/json")
    ) { uri ->
        uri?.let(::exportGalaxyArchive)
    }
    private val galaxyArchiveImporter = registerForActivityResult(
        ActivityResultContracts.OpenDocument()
    ) { uri ->
        uri?.let(::previewGalaxyArchiveImport)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        privacyCurtainState = CompanionPrivacyCurtainState(
            enabled = userSettingsPrefs.getBoolean("privacy_curtain_enabled", false),
        )
        applySystemBarPalette()
        stagedApkName = pairingPrefs.getString("staged_apk_name", null)
        stagedApkHash = pairingPrefs.getString("staged_apk_hash", null)
        stagedApkUri = pairingPrefs.getString("staged_apk_uri", null)
        if (hasSecureWirelessSession()) {
            telemetryHost = pairingPrefs.getString("paired_host", null)
            telemetryToken = linkSessionVault.load()
            telemetryCertificateSha256 = pairingPrefs.getString("certificate_sha256", null)
        } else if (hasRememberedDesktop()) {
            clearWirelessSession(forgetTrustedDesktop = false)
            telemetryHost = pairingPrefs.getString("paired_host", null)
            telemetryCertificateSha256 = pairingPrefs.getString("certificate_sha256", null)
        } else {
            clearWirelessSession(forgetTrustedDesktop = true)
        }
        setContentView(buildScreen())
        restoreRoute(
            CompanionRoute.fromSavedToken(
                savedInstanceState?.getString(ACTIVITY_ROUTE_KEY),
            ),
        )
        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                val drawer = navigationDrawer
                when {
                    drawer?.isDrawerOpen(GravityCompat.START) == true -> {
                        drawer.closeDrawer(GravityCompat.START)
                    }
                    sectionPage != null -> showHome()
                    else -> {
                        isEnabled = false
                        onBackPressedDispatcher.onBackPressed()
                    }
                }
            }
        })
    }

    override fun onSaveInstanceState(outState: Bundle) {
        outState.putString(ACTIVITY_ROUTE_KEY, currentRoute.name)
        super.onSaveInstanceState(outState)
    }

    override fun onResume() {
        super.onResume()
        activityResumed = true
        applyPrivacyCurtain()
        updateHealthMetrics()
        networkStatusHandler.removeCallbacks(networkStatusRefresh)
        networkStatusHandler.post(networkStatusRefresh)
        resumeRememberedLink()
    }

    override fun onPause() {
        activityResumed = false
        networkStatusHandler.removeCallbacks(networkStatusRefresh)
        telemetryHandler.removeCallbacksAndMessages(null)
        super.onPause()
    }

    override fun onStop() {
        privacyCurtainState = privacyCurtainState.onBackgrounded()
        super.onStop()
    }

    private fun stageApk(uri: Uri) {
        stagedApkUri = uri.toString()
        runCatching {
            contentResolver.takePersistableUriPermission(uri, Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }
        stagedApkName = contentResolver
            .query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)
            ?.use { cursor -> if (cursor.moveToFirst()) cursor.getString(0) else null }
            ?: "Selected APK"
        pairingPrefs.edit()
            .putString("staged_apk_name", stagedApkName)
            .putString("staged_apk_uri", stagedApkUri)
            .remove("staged_apk_hash")
            .apply()
        stagedApkHash = null
        apkDetailView?.text = apkStatusText("Reading and fingerprinting the selected APK…")
        logActivity("APK selected for local verification")
        Thread {
            val digest = runCatching {
                contentResolver.openInputStream(uri)?.use { input ->
                    val hash = MessageDigest.getInstance("SHA-256")
                    val buffer = ByteArray(8192)
                    var count: Int
                    while (input.read(buffer).also { count = it } >= 0) {
                        if (count > 0) hash.update(buffer, 0, count)
                    }
                    hash.digest().joinToString("") { byte -> "%02x".format(byte) }
                }
            }.getOrNull()
            runOnUiThread {
                stagedApkHash = digest
                if (digest != null) {
                    pairingPrefs.edit().putString("staged_apk_hash", digest).apply()
                    logActivity("APK fingerprint verified")
                } else {
                    logActivity("APK fingerprint unavailable")
                }
                apkDetailView?.text = apkStatusText(
                    if (digest != null) "Integrity fingerprint ready. Review it before opening Android's installer."
                    else "The APK was staged, but its fingerprint could not be calculated. Choose the file again before proceeding."
                )
            }
        }.start()
    }

    private fun apkStatusText(message: String): String {
        val fingerprint = stagedApkHash?.chunked(16)?.joinToString("\n") ?: "Not calculated"
        return "$message\n\nAPK: ${stagedApkName ?: "None selected"}\nSHA-256:\n$fingerprint\n\nGuardian boundary: ROMVERSE never installs silently. Android's protected installer always presents the final confirmation."
    }

    private fun openStagedApkInstaller(detailView: TextView) {
        val uri = stagedApkUri?.let(Uri::parse)
        if (uri == null || stagedApkHash == null) {
            detailView.text = apkStatusText("Choose an APK and wait for fingerprint verification first.")
            return
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O && !packageManager.canRequestPackageInstalls()) {
            detailView.text = apkStatusText("Android requires permission for ROMVERSE Companion to hand files to the package installer. Enable ‘Allow from this source’, return here, and tap Review & Open Installer again.")
            startActivity(
                Intent(
                    Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                    Uri.parse("package:$packageName")
                )
            )
            return
        }
        AlertDialog.Builder(this)
            .setTitle("Guardian installation review")
            .setMessage(
                "APK: ${stagedApkName ?: "Selected APK"}\n\nSHA-256:\n${stagedApkHash ?: "Unavailable"}\n\nContinue only if you trust the source and recognize this fingerprint. Android will show one more system confirmation."
            )
            .setNegativeButton("Cancel", null)
            .setPositiveButton("Open installer") { _, _ ->
                val installIntent = Intent(Intent.ACTION_VIEW).apply {
                    setDataAndType(uri, "application/vnd.android.package-archive")
                    addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                }
                runCatching { startActivity(installIntent) }
                    .onSuccess {
                        detailView.text = apkStatusText("APK handed to Android's protected installer.")
                        logActivity("APK handed to Android's protected installer")
                    }
                    .onFailure {
                        detailView.text = apkStatusText("Android could not open this APK. Choose the file again or verify that it is a valid package.")
                        logActivity("APK installer handoff failed")
                    }
            }
            .show()
    }

    private fun captureVitalisSnapshot(): VitalisSnapshot {
        val battery = (getSystemService(BATTERY_SERVICE) as BatteryManager)
            .getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY)
            .takeIf { it in 0..100 }
        val batteryIntent = registerReceiver(null, IntentFilter(Intent.ACTION_BATTERY_CHANGED))
        val temperature = batteryIntent
            ?.getIntExtra(BatteryManager.EXTRA_TEMPERATURE, Int.MIN_VALUE)
            ?.takeUnless { it == Int.MIN_VALUE }
            ?.div(10.0)
            ?.takeIf { it in -20.0..100.0 }
        val storage = StatFs(Environment.getDataDirectory().path)
        val storageUsed = if (storage.totalBytes > 0) {
            ((storage.totalBytes - storage.availableBytes) * 100 / storage.totalBytes)
                .toInt()
                .coerceIn(0, 100)
        } else null
        val memory = ActivityManager.MemoryInfo().also {
            (getSystemService(ACTIVITY_SERVICE) as ActivityManager).getMemoryInfo(it)
        }
        val ramUsed = if (memory.totalMem > 0) {
            ((memory.totalMem - memory.availMem) * 100 / memory.totalMem)
                .toInt()
                .coerceIn(0, 100)
        } else null
        val connectivity = getSystemService(CONNECTIVITY_SERVICE) as ConnectivityManager
        val networkCapabilities = connectivity.activeNetwork?.let(connectivity::getNetworkCapabilities)
        val networkValidated = if (networkCapabilities == null) {
            false
        } else {
            networkCapabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED)
        }
        return VitalisSnapshot(
            battery,
            temperature,
            storageUsed,
            ramUsed,
            networkValidated,
            isUsbConnected(),
        )
    }

    private fun buildRepairReport(): String {
        val batteryManager = getSystemService(BATTERY_SERVICE) as BatteryManager
        val battery = batteryManager
            .getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY)
            .takeIf { it in 0..100 }
        val batteryIntent = registerReceiver(null, IntentFilter(Intent.ACTION_BATTERY_CHANGED))
        val temperatureTenths = batteryIntent?.getIntExtra(BatteryManager.EXTRA_TEMPERATURE, Int.MIN_VALUE)
        val temperature = temperatureTenths
            ?.takeUnless { it == Int.MIN_VALUE }
            ?.div(10.0)
            ?.takeIf { it in -20.0..100.0 }
        val charging = when (batteryIntent?.getIntExtra(BatteryManager.EXTRA_STATUS, -1)) {
            BatteryManager.BATTERY_STATUS_CHARGING -> "Charging"
            BatteryManager.BATTERY_STATUS_FULL -> "Full"
            BatteryManager.BATTERY_STATUS_DISCHARGING -> "Discharging"
            BatteryManager.BATTERY_STATUS_NOT_CHARGING -> "Connected, not charging"
            else -> "Unknown"
        }
        val storage = StatFs(Environment.getDataDirectory().path)
        val storageUsedPct = if (storage.totalBytes > 0) {
            ((storage.totalBytes - storage.availableBytes) * 100 / storage.totalBytes).toInt()
        } else null
        val memory = ActivityManager.MemoryInfo().also {
            (getSystemService(ACTIVITY_SERVICE) as ActivityManager).getMemoryInfo(it)
        }
        val ramUsedPct = if (memory.totalMem > 0) {
            ((memory.totalMem - memory.availMem) * 100 / memory.totalMem).toInt().coerceIn(0, 100)
        } else null
        val connectivity = getSystemService(CONNECTIVITY_SERVICE) as ConnectivityManager
        val networkCapabilities = connectivity.activeNetwork?.let(connectivity::getNetworkCapabilities)
        val networkState = when {
            networkCapabilities == null -> "Disconnected"
            networkCapabilities.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) -> "Wi-Fi connected"
            networkCapabilities.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR) -> "Mobile data connected"
            networkCapabilities.hasTransport(NetworkCapabilities.TRANSPORT_ETHERNET) -> "Ethernet connected"
            else -> "Connected"
        }
        val validatedNetwork = if (networkCapabilities == null) {
            false
        } else {
            networkCapabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED)
        }
        val assessment = VitalisAssessmentEngine.assess(
            VitalisSnapshot(
                battery,
                temperature,
                storageUsedPct,
                ramUsedPct,
                validatedNetwork,
                isUsbConnected(),
            ),
        )
        val atlasContext = CompanionDeviceAtlas.resolveDetailed(
            Build.MANUFACTURER,
            Build.MODEL,
            Build.DEVICE,
        ).reportText()
        return """
            ROMVERSE COMPANION • SAFE DIAGNOSTIC
            Guardian health score: ${assessment.score?.let { "$it / 100" } ?: "UNCONFIRMED"}
            Evidence coverage: ${assessment.evidencePercent}% • ${assessment.state}

            DEVICE
            ${localDeviceIdentity.displayName}
            Reported model: ${localDeviceIdentity.rawModel} • Codename: ${localDeviceIdentity.codename}
            Identity: ${if (localDeviceIdentity.verifiedExact) "VERIFIED EXACT" else "UNCONFIRMED"}
            Evidence: ${localDeviceIdentity.evidence}
            Android ${Build.VERSION.RELEASE} • API ${Build.VERSION.SDK_INT}
            Security patch: ${Build.VERSION.SECURITY_PATCH.ifBlank { "Unavailable" }}

            POWER
            Battery: ${battery?.let { "$it%" } ?: "Unavailable"}
            State: $charging
            Temperature: ${temperature?.let { "%.1f °C".format(it) } ?: "Unavailable"}

            RESOURCES & LINK
            Storage: ${storageUsedPct?.let { "$it% used" } ?: "Unavailable"} • ${formatBytes(storage.availableBytes)} free
            RAM: ${ramUsedPct?.let { "$it% used" } ?: "Unavailable"} • ${formatBytes(memory.availMem)} available
            Network: $networkState${if (validatedNetwork == true) " • internet validated" else ""}
            USB: ${if (isUsbConnected()) "Connected" else "Not detected"}

            FINDINGS
            ${assessment.findings.joinToString("\n") { it.reportLine }}

            DEVICE ATLAS CONTEXT
            ${CompanionDeviceAtlas.catalogStatus()}
            $atlasContext

            Guardian boundary: this scan is read-only. It did not delete files, change system settings, reboot, root, unlock, or flash the phone.
        """.trimIndent()
    }

    private fun saveRepairReceipt(report: String) {
        val receiptDir = java.io.File(filesDir, "repair").apply { mkdirs() }
        java.io.File(receiptDir, "latest-diagnostic.json").writeText(
            JSONObject()
                .put("schema_version", 1)
                .put("operation", "companion-safe-diagnostic")
                .put("created_at_epoch_ms", System.currentTimeMillis())
                .put("report", report)
                .put("device_modified", false)
                .toString(2)
        )
    }

    private fun buildScreen(): View {
        navigationButtons.clear()
        val root = RomverseDrawerLayout(this).apply {
            setScrimColor(if (displayMode() == CompanionDisplayMode.OLED) {
                "#E6000000".toColorInt()
            } else {
                "#B8000207".toColorInt()
            })
            drawerElevation = dp(22).toFloat()
            importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_YES
        }
        navigationDrawer = root
        val mainSurface = FrameLayout(this).apply {
            tag = "romverse-display-${displayMode().persistedValue}"
        }
        val stars = starfieldLayer()
        mainSurface.addView(stars, FrameLayout.LayoutParams(-1, -1))
        val appShell = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.TRANSPARENT)
        }
        val appBar = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(12), dp(8), dp(12), dp(8))
            minimumHeight = dp(64)
            background = glassBarBackground()
            elevation = dp(12).toFloat()
        }
        ViewCompat.setOnApplyWindowInsetsListener(appBar) { view, insets ->
            val topInset = insets.getInsets(WindowInsetsCompat.Type.statusBars()).top
            view.setPadding(dp(12), dp(8) + topInset, dp(12), dp(8))
            insets
        }
        appBar.addView(Button(this).apply {
            text = "☰"
            contentDescription = "Open ROMVERSE navigation"
            textSize = 21f
            setTextColor(cyan)
            background = outlinedPanel()
            setPadding(0, 0, 0, 0)
            setOnClickListener { root.openDrawer(GravityCompat.START) }
        }, LinearLayout.LayoutParams(dp(48), dp(48)))
        appBar.addView(ImageView(this).apply {
            setImageResource(R.drawable.romverse_app_icon)
            scaleType = ImageView.ScaleType.CENTER_INSIDE
        }, LinearLayout.LayoutParams(dp(44), dp(44)).apply { marginStart = dp(8) })
        navigationTitleView = text("COMMAND DECK", 14f, Color.WHITE, true).apply {
            letterSpacing = 0.08f
            maxLines = 2
            ellipsize = android.text.TextUtils.TruncateAt.END
            setPadding(dp(8), 0, dp(8), 0)
        }
        appBar.addView(navigationTitleView, LinearLayout.LayoutParams(0, -2, 1f))
        appBar.addView(onlineStatusBadge())
        appShell.addView(appBar, LinearLayout.LayoutParams(-1, -2))

        val content = FrameLayout(this).also { sectionHost = it }
        appShell.addView(content, LinearLayout.LayoutParams(-1, 0, 1f))
        val scroll = ScrollView(this).apply { setBackgroundColor(Color.TRANSPARENT) }
        homeScroll = scroll
        content.addView(scroll, FrameLayout.LayoutParams(-1, -1))
        val page = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(
                dp(CompanionLayoutSpec.CONTENT_HORIZONTAL_DP),
                dp(CompanionLayoutSpec.CONTENT_TOP_DP),
                dp(CompanionLayoutSpec.CONTENT_HORIZONTAL_DP),
                dp(CompanionLayoutSpec.CONTENT_BOTTOM_DP),
            )
        }
        val mark = ImageView(this).apply {
            setImageResource(R.drawable.romverse_app_icon)
            scaleType = ImageView.ScaleType.CENTER_INSIDE
            layoutParams = LinearLayout.LayoutParams(-1, dp(138)).apply {
                gravity = Gravity.CENTER_HORIZONTAL
                bottomMargin = dp(4)
            }
        }
        page.addView(mark)
        val homeIdentity = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER_HORIZONTAL
            layoutParams = LinearLayout.LayoutParams(-1, -2)
        }
        homeIdentity.addView(text("ROMVERSE COMPANION", 13f, cyan, true).apply {
            gravity = Gravity.CENTER
            textAlignment = View.TEXT_ALIGNMENT_CENTER
            letterSpacing = 0.12f
            layoutParams = LinearLayout.LayoutParams(-1, -2)
        })
        homeIdentity.addView(text("YOUR ANDROID SIDEKICK", 10f, Color.WHITE, true).apply {
            gravity = Gravity.CENTER
            textAlignment = View.TEXT_ALIGNMENT_CENTER
            letterSpacing = 0.16f
            layoutParams = LinearLayout.LayoutParams(-1, -2).apply {
                topMargin = dp(2)
            }
        })
        homeIdentity.addView(text("A RADFORGE LABS PROJECT", 10f, muted, true).apply {
            gravity = Gravity.CENTER
            textAlignment = View.TEXT_ALIGNMENT_CENTER
            letterSpacing = 0.04f
            layoutParams = LinearLayout.LayoutParams(-1, -2).apply {
                topMargin = dp(4)
            }
        })
        homeIdentity.addView(text("Monitor. Understand. Stay connected.", 16f, muted, false).apply {
            gravity = Gravity.CENTER
            textAlignment = View.TEXT_ALIGNMENT_CENTER
            layoutParams = LinearLayout.LayoutParams(-1, -2).apply {
                topMargin = dp(3)
            }
        })
        page.addView(homeIdentity)
        page.addView(space(dp(18)))
        greetingView = text(greetingText(), 23f, Color.WHITE, true)
        page.addView(greetingView)
        page.addView(text("Everything important is gathered into one guided workspace.", 13f, muted, false))
        page.addView(space(dp(10)))

        val dashboardSnapshot = captureVitalisSnapshot()
        val dashboardAssessment = VitalisAssessmentEngine.assess(dashboardSnapshot)
        val dashboardStatusColor = when (dashboardAssessment.state) {
            "OPTIMAL" -> "#72FFB2".toColorInt()
            "ACTION RECOMMENDED" -> "#FF6685".toColorInt()
            else -> "#FFB454".toColorInt()
        }
        lateinit var connection: LinearLayout
        val homeHero = card()
        homeHeroEyebrow = text("ROM HEALTH", 12f, violet, true)
        homeHero.addView(homeHeroEyebrow)
        nextActionTitle = text("Assessing current state…", 20f, Color.WHITE, true)
        homeHero.addView(nextActionTitle)
        homeHeroDetail = text("Collecting bounded local evidence.", 13f, muted, false)
        homeHero.addView(homeHeroDetail)
        homeHeroLink = text("?  ROMVERSE LINK  •  CHECKING", 11f, muted, true)
        homeHero.addView(homeHeroLink)
        homeHeroGuardian = text("?  GUARDIAN  •  CHECKING", 11f, muted, true)
        homeHero.addView(homeHeroGuardian)
        homeHeroMission = text("?  DESKTOP MISSION  •  CHECKING", 11f, muted, true)
        homeHero.addView(homeHeroMission)
        nextActionButton = sectionAction("OPEN VITALIS") {
            val running = desktopLiveConsoleStatus?.events?.firstOrNull { it.state == "running" }
            val guardianBlocked = desktopLiveConsoleStatus?.guardianReviewState == "blocked"
            when {
                running != null || guardianBlocked -> showSection(
                    "LIVE CONSOLE",
                    "Genuine Desktop mission and Guardian evidence received through ROMVERSE Link.",
                )
                hasSecureWirelessSession() || isUsbConnected() -> showSection(
                    "VITALIS",
                    "Live health evidence and Guardian-safe diagnostics.",
                )
                else -> homeScroll?.smoothScrollTo(0, connection.top)
            }
        }
        homeHero.addView(nextActionButton)
        page.addView(homeHero)
        refreshHomeHero()

        val galaxyDashboard = card()
        galaxyDashboard.addView(text("GALAXY DEVICE CORE", 12f, violet, true))
        galaxyDashboard.addView(text(
            dashboardAssessment.state,
            20f,
            dashboardStatusColor,
            true,
        ))
        galaxyDashboard.addView(text(
            "Live, read-only evidence • ${dashboardAssessment.evidencePercent}% coverage",
            12f,
            muted,
            false,
        ))
        galaxyDashboard.addView(ResourceGaugeStripView(
            this,
            listOf(
                GaugeMetric("HEALTH", dashboardAssessment.score, dashboardStatusColor),
                GaugeMetric("BATTERY", dashboardSnapshot.batteryPercent, cyan),
                GaugeMetric("STORAGE", dashboardSnapshot.storageUsedPercent, violet),
                GaugeMetric("RAM", dashboardSnapshot.ramUsedPercent, "#72FFB2".toColorInt()),
            ),
        ))
        galaxyDashboard.addView(text(
            "Unknown readings stay unconfirmed. Guardian never presents missing evidence as healthy.",
            11f,
            muted,
            false,
        ))
        page.addView(galaxyDashboard)

        val tabs = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
        }
        fun tab(label: String, icon: String) = Button(this).apply {
            text = "$label\n$icon"
            setTextColor(Color.WHITE)
            background = outlinedPanel()
            isAllCaps = false
            textSize = 13f
            gravity = Gravity.CENTER
            setTypeface(typeface, android.graphics.Typeface.BOLD)
            setPadding(dp(4), dp(4), dp(4), dp(4))
            layoutParams = LinearLayout.LayoutParams(0, dp(72), 1f).apply {
                marginStart = dp(3)
                marginEnd = dp(3)
            }
        }
        fun tabRow(vararg items: Button) = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            items.forEach { addView(it) }
        }
        val homeTab = tab("HOME", "⌂")
        val healthTab = tab("VITALIS", "◈")
        val repairTab = tab("LIFELINE", "✚")
        val apkTab = tab("LAUNCHPAD", "▣")
        val galaxyTab = tab("GALAXY", "✦")
        val aboutTab = tab("ABOUT", "ⓘ")
        tabs.addView(tabRow(homeTab, healthTab, repairTab))
        tabs.addView(tabRow(apkTab, galaxyTab, aboutTab))
        page.addView(tabs)
        tabs.visibility = View.GONE

        connection = card()
        pairSyncCard = connection
        connection.addView(text("PAIR & SYNC", 13f, violet, true))
        val secureWireless = hasSecureWirelessSession()
        val rememberedDesktop = hasRememberedDesktop()
        val pairingState = text(
            when {
                secureWireless -> "Paired • secure read-only telemetry"
                rememberedDesktop -> "Trusted Desktop remembered • approval required"
                else -> "Not paired yet"
            },
            22f,
            Color.WHITE,
            true,
        )
        connection.addView(pairingState)
        val desktopTelemetry = text("Desktop telemetry: waiting for approval", 14f, muted, false)
        desktopTelemetryView = desktopTelemetry
        connection.addView(desktopTelemetry)
        connection.addView(text("Open ROMVERSE Studio on your PC and choose ROMVERSE Link → Pair device.", 14f, muted, false))
        val pcAddress = EditText(this).apply {
            hint = "PC address • 192.168.1.10:8765"
            contentDescription = "ROMVERSE Link PC address"
            setSingleLine(true)
            setTextColor(Color.WHITE)
            setHintTextColor(muted)
            setPadding(dp(14), 0, dp(14), 0)
            background = outlinedPanel()
            setText(pairingPrefs.getString("paired_host", "").orEmpty())
            layoutParams = LinearLayout.LayoutParams(-1, dp(52)).apply {
                topMargin = dp(10)
            }
        }
        connection.addView(pcAddress)
        val pcFingerprint = EditText(this).apply {
            hint = "PC certificate SHA-256 • auto-filled"
            contentDescription = "ROMVERSE Link PC certificate SHA-256"
            setSingleLine(true)
            setTextColor(Color.WHITE)
            setHintTextColor(muted)
            setPadding(dp(14), 0, dp(14), 0)
            background = outlinedPanel()
            setText(pairingPrefs.getString("certificate_sha256", "").orEmpty())
            isEnabled = !rememberedDesktop
            layoutParams = LinearLayout.LayoutParams(-1, dp(52)).apply {
                topMargin = dp(8)
            }
        }
        connection.addView(pcFingerprint)
        val linkSafety = text(
            DesktopLinkSecurity.safetyCode(pcFingerprint.text.toString())?.let {
                "LINK SAFETY CODE  •  $it\nCompare this exact code with ROMVERSE Desktop."
            } ?: "LINK SAFETY CODE  •  waiting for the PC identity",
            13f,
            muted,
            false,
        )
        connection.addView(linkSafety)
        linkAddressField = pcAddress
        linkFingerprintField = pcFingerprint
        linkSafetyLabel = linkSafety
        val safetyConfirm = CheckBox(this).apply {
            text = "I confirmed the Link safety code matches on the PC and phone"
            setTextColor(muted)
            isChecked = rememberedDesktop
            isEnabled = !rememberedDesktop
            setPadding(0, dp(8), 0, dp(8))
        }
        connection.addView(safetyConfirm)
        pcFingerprint.doAfterTextChanged { value ->
            val safetyCode = DesktopLinkSecurity.safetyCode(value?.toString().orEmpty())
            linkSafety.text = safetyCode?.let {
                "LINK SAFETY CODE  •  $it\nCompare this exact code with ROMVERSE Desktop."
            } ?: "LINK SAFETY CODE  •  invalid or incomplete PC identity"
            if (!rememberedDesktop) safetyConfirm.isChecked = false
        }
        discoverPc(pcAddress, pcFingerprint, linkSafety)
        val pairRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            layoutParams = LinearLayout.LayoutParams(-1, -2).apply {
                topMargin = dp(8)
            }
        }
        val code = EditText(this).apply {
            hint = "000000"
            inputType = InputType.TYPE_CLASS_NUMBER
            setSingleLine(true)
            setTextColor(Color.WHITE)
            setHintTextColor(muted)
            setPadding(dp(14), 0, dp(14), 0)
            background = outlinedPanel()
            layoutParams = LinearLayout.LayoutParams(0, dp(56), 1f)
        }
        lateinit var wireless: Button
        val unpair = Button(this).apply {
            text = "RESET PAIRING"
            setTextColor(muted)
            background = outlinedPanel()
            alignPanelAction()
            setOnClickListener {
                clearWirelessSession(forgetTrustedDesktop = true)
                telemetryHandler.removeCallbacksAndMessages(null)
                pairingState.text = "Not paired yet"
                refreshHomeHero()
                val usbConnected = isUsbConnected()
                wireless.text = if (usbConnected) "USB CONNECTED" else "CONNECT WIRELESSLY"
                wireless.background = if (usbConnected) successBackground() else actionBackground()
                wireless.isEnabled = !usbConnected
                code.text?.clear()
                pcFingerprint.text?.clear()
                pcFingerprint.isEnabled = true
                safetyConfirm.isChecked = false
                safetyConfirm.isEnabled = true
                discoverPc(pcAddress, pcFingerprint, linkSafety)
                logActivity("Pairing session cleared")
            }
        }
        pairRow.addView(code)
        connection.addView(pairRow)
        wireless = Button(this).apply {
            text = when {
                isUsbConnected() -> "USB CONNECTED"
                secureWireless -> "PAIRED"
                rememberedDesktop -> "REAUTHORIZE LINK"
                else -> "CONNECT WIRELESSLY"
            }
            setTextColor(cyan)
            background = if (isUsbConnected() || secureWireless) successBackground() else actionBackground()
            alignPanelAction()
            isEnabled = !isUsbConnected() && !secureWireless
            setOnClickListener {
                val host = pcAddress.text.toString().trim()
                val candidate = code.text.toString().replace(" ", "")
                if (host.isBlank()) {
                    text = "DISCOVERING PC…"
                    discoverPc(pcAddress, pcFingerprint, linkSafety)
                    postDelayed({ if (pcAddress.text.isNullOrBlank()) text = "CONNECT WIRELESSLY" }, 3000)
                    return@setOnClickListener
                }
                val certificateSha256 = DesktopLinkSecurity.normalizeFingerprint(
                    pcFingerprint.text.toString(),
                )
                if (certificateSha256 == null) {
                    pcFingerprint.error = "Discover the PC or enter its full certificate SHA-256"
                    return@setOnClickListener
                }
                if (!safetyConfirm.isChecked) {
                    safetyConfirm.error = "Compare and confirm the Link safety code first"
                    return@setOnClickListener
                }
                if (candidate.length != 6 || !candidate.all(Char::isDigit)) {
                    code.error = "Enter the PC address and six-digit code"
                    return@setOnClickListener
                }
                text = "CONNECTING…"
                Thread {
                    val requestId = postPairRequest(host, candidate, certificateSha256)
                    runOnUiThread {
                        text = if (requestId != null) "WAITING FOR PC APPROVAL" else "RETRY WIRELESS PAIRING"
                        if (requestId != null) logActivity("Wireless pairing request sent")
                    }
                    if (requestId != null) {
                        var approved = false
                        repeat(60) {
                            Thread.sleep(1000)
                            val status = getPairStatus(host, requestId, certificateSha256)
                            val telemetry = if (status.state == "approved" && status.sessionToken.isNotBlank()) {
                                getTelemetrySummary(host, status.sessionToken, certificateSha256)
                            } else TelemetryResult()
                            if (status.state == "approved" && telemetry.summary != null) {
                                val phoneSync = postCompanionHealthSnapshot(
                                    host,
                                    status.sessionToken,
                                    certificateSha256,
                                )
                                if (!linkSessionVault.store(status.sessionToken)) {
                                    runOnUiThread {
                                        clearWirelessSession(forgetTrustedDesktop = true)
                                        text = "SECURE STORAGE FAILED • PAIR AGAIN"
                                        pairingState.text =
                                            "Desktop verified • secure session could not be preserved"
                                        logActivity("Wireless pairing stopped because secure storage failed")
                                    }
                                    return@Thread
                                }
                                approved = true
                                runOnUiThread {
                                    text = "PAIRED"
                                    background = successBackground()
                                    setTextColor("#72FFB2".toColorInt())
                                    pairingState.text = if (phoneSync.accepted) {
                                        "Paired • two-way health sync active"
                                    } else {
                                        "Paired • Desktop telemetry active • phone sync retrying"
                                    }
                                    desktopAscensionStatus = telemetry.ascension
                                    desktopLiveConsoleStatus = telemetry.liveConsole
                                    desktopDeviceDnaStatus = telemetry.deviceDna
                                    desktopTelemetry.text = if (phoneSync.accepted) {
                                        "${telemetry.summary}  •  phone health synced"
                                    } else telemetry.summary
                                    telemetryHost = host
                                    telemetryToken = status.sessionToken
                                    telemetryCertificateSha256 = certificateSha256
                                    scheduleTelemetryRefresh(desktopTelemetry)
                                    pairingPrefs.edit()
                                        .putBoolean("paired", true)
                                        .putString("paired_host", host)
                                        .putString("certificate_sha256", certificateSha256)
                                        .putInt(
                                            "link_protocol_version",
                                            DesktopLinkSecurity.PROTOCOL_VERSION,
                                        )
                                        .putLong(
                                            "session_expires_at_epoch_ms",
                                            System.currentTimeMillis() + status.expiresInSeconds * 1000L,
                                        )
                                        .putBoolean("desktop_trusted", true)
                                        .apply()
                                    telemetryRetryAttempt = 0
                                    refreshHomeHero()
                                    logActivity("Wireless pairing approved")
                                }
                                return@Thread
                            }
                        }
                        if (!approved) {
                            runOnUiThread { text = "APPROVAL TIMEOUT • TRY AGAIN" }
                        }
                    }
                }.start()
            }
        }
        connection.addView(wireless)
        connection.addView(unpair)
        if (secureWireless) {
            desktopTelemetry.text = "Desktop telemetry: reconnecting securely…"
        } else if (rememberedDesktop) {
            desktopTelemetry.text =
                "Desktop remembered securely • enter a new Link code when approval expires"
        }
        page.addView(connection)

        val identity = card()
        identity.addView(text("DEVICE PORTAL", 13f, violet, true))
        identity.addView(metric(
            "Model",
            localDeviceIdentity.displayName,
            if (localDeviceIdentity.verifiedExact) {
                "VERIFIED EXACT  •  ${localDeviceIdentity.rawModel}  •  ${localDeviceIdentity.codename}"
            } else {
                "UNCONFIRMED  •  ${localDeviceIdentity.rawModel}  •  ${localDeviceIdentity.codename}"
            },
        ))
        identity.addView(text(localDeviceIdentity.evidence, 11f, muted, false))
        identity.addView(metric("Android", Build.VERSION.RELEASE, "API ${Build.VERSION.SDK_INT}"))
        identity.addView(metric("Security patch", Build.VERSION.SECURITY_PATCH, "Verified locally on this phone"))
        identity.addView(metric("Architecture", Build.SUPPORTED_ABIS.firstOrNull() ?: "Unknown", "Read-only device metadata"))
        page.addView(identity)

        val health = card()
        health.addView(text("PULSE • HEALTH & SAFETY", 13f, violet, true))
        batteryMetric = metric("Battery", "—", "Read locally from this phone")
        storageMetric = metric("Storage", "—", "Read locally from this phone")
        health.addView(batteryMetric)
        health.addView(storageMetric)
        health.addView(metric("Guardian", "ACTIVE", "Read-only protection is enabled"))
        val refreshHealth = Button(this).apply {
            text = "REFRESH HEALTH DATA"
            setTextColor(cyan)
            background = actionBackground()
            alignPanelAction()
            setOnClickListener { updateHealthMetrics() }
        }
        health.addView(refreshHealth)
        val copyHealth = Button(this).apply {
            text = "COPY HEALTH SUMMARY"
            setTextColor(cyan)
            background = outlinedPanel()
            alignPanelAction()
            setOnClickListener {
                val summary = buildHealthSummary()
                val clipboard = getSystemService(CLIPBOARD_SERVICE) as ClipboardManager
                clipboard.setPrimaryClip(ClipData.newPlainText("ROMVERSE health summary", summary))
                logActivity("Health summary copied")
            }
        }
        health.addView(copyHealth)
        val shareHealth = Button(this).apply {
            text = "SHARE HEALTH SUMMARY"
            setTextColor(cyan)
            background = outlinedPanel()
            alignPanelAction()
            setOnClickListener {
                val share = Intent(Intent.ACTION_SEND).apply {
                    type = "text/plain"
                    putExtra(Intent.EXTRA_SUBJECT, "ROMVERSE health summary")
                    putExtra(Intent.EXTRA_TEXT, buildHealthSummary())
                }
                startActivity(Intent.createChooser(share, "Share ROMVERSE health summary"))
                logActivity("Health summary shared")
            }
        }
        health.addView(shareHealth)
        updateHealthMetrics()
        page.addView(health)

        val guardian = card()
        guardian.addView(text("GUARDIAN PROTECTION", 13f, violet, true))
        guardian.addView(text("ACTIVE  •  READ-ONLY MODE", 19f, cyan, true))
        guardian.addView(text("Companion can report health and activity, but it cannot flash, wipe, unlock, or modify your phone.", 14f, muted, false))
        page.addView(guardian)

        val activity = card()
        activity.addView(text("ACTIVITY & REPORTS", 13f, violet, true))
        activityFeed = text("No completed activity has been recorded yet.", 15f, Color.WHITE, false)
        activity.addView(activityFeed)
        activity.addView(text("Private, bounded history stored only by ROMVERSE Companion on this phone. It does not include device identifiers, APK names, hashes, or Galaxy message text.", 13f, muted, false))
        activity.addView(sectionAction("COPY ACTIVITY REPORT") {
            val report = activityReport()
            val clipboard = getSystemService(CLIPBOARD_SERVICE) as ClipboardManager
            clipboard.setPrimaryClip(ClipData.newPlainText("ROMVERSE Companion activity", report))
        })
        activity.addView(sectionAction("CLEAR LOCAL ACTIVITY") {
            AlertDialog.Builder(this)
                .setTitle("Clear private activity history?")
                .setMessage("This removes only ROMVERSE Companion's local activity list. It does not change your phone, projects, pairings, or Galaxy topics.")
                .setNegativeButton("Cancel", null)
                .setPositiveButton("Clear") { _, _ ->
                    activityPrefs.edit().remove("events_v1").apply()
                    renderActivityFeed()
                }
                .show()
        })
        renderActivityFeed()
        page.addView(activity)

        val community = card()
        community.addView(text("GALAXY", 13f, violet, true))
        community.addView(text("Community Preview • Local Workspace", 20f, Color.WHITE, true))
        community.addView(text("Create real local topics, replies, and votes now. Nothing is public or synchronized until the secure Galaxy service is ready.", 14f, muted, false))
        community.addView(sectionAction("OPEN COMMUNITY LAB") {
            showSection("ROMVERSE GALAXY", "Private local forum for ROM builds, troubleshooting, Recipes, and ideas.")
        })
        page.addView(community)

        homeTab.setOnClickListener { scroll.smoothScrollTo(0, 0) }
        healthTab.setOnClickListener { scroll.smoothScrollTo(0, health.top) }
        repairTab.setOnClickListener { scroll.smoothScrollTo(0, identity.top) }
        apkTab.setOnClickListener { scroll.smoothScrollTo(0, health.top) }
        galaxyTab.setOnClickListener { scroll.smoothScrollTo(0, community.top) }
        aboutTab.setOnClickListener { scroll.smoothScrollTo(0, activity.top) }
        page.addView(space(dp(20)))
        val footer = text("ROMVERSE Companion  •  v0.1.0\nA RadForge Labs Project", 12f, muted, false)
        footer.gravity = Gravity.CENTER
        page.addView(footer)
        scroll.addView(page)

        val bottomBar = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER
            setPadding(dp(6), dp(5), dp(6), dp(7))
            minimumHeight = dp(70)
            background = glassBarBackground()
            elevation = dp(14).toFloat()
            contentDescription = "Primary ROMVERSE navigation"
        }
        ViewCompat.setOnApplyWindowInsetsListener(bottomBar) { view, insets ->
            val bottomInset = insets.getInsets(WindowInsetsCompat.Type.navigationBars()).bottom
            view.setPadding(dp(6), dp(5), dp(6), dp(7) + bottomInset)
            insets
        }
        CompanionNavigation.bottomDestinations.forEach { destination ->
            val kind = destination.navKind()
            val button = RomverseNavButton(this, kind, displayMode()).apply {
                setOnClickListener { openDestination(destination) }
                layoutParams = LinearLayout.LayoutParams(0, dp(58), 1f).apply {
                    marginStart = dp(2)
                    marginEnd = dp(2)
                }
            }
            registerNavigationButton(kind, button)
            bottomBar.addView(button)
        }
        appShell.addView(bottomBar, LinearLayout.LayoutParams(-1, -2))
        mainSurface.addView(appShell, FrameLayout.LayoutParams(-1, -1))
        root.addView(mainSurface, DrawerLayout.LayoutParams(-1, -1))

        val drawerScroll = ScrollView(this).apply {
            isFillViewport = true
            background = glassSidebarBackground()
            contentDescription = "ROMVERSE swipe navigation drawer"
        }
        val drawer = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(14), dp(28), dp(14), dp(18))
        }
        ViewCompat.setOnApplyWindowInsetsListener(drawer) { view, insets ->
            val bars = insets.getInsets(WindowInsetsCompat.Type.systemBars())
            view.setPadding(dp(14), dp(20) + bars.top, dp(14), dp(18) + bars.bottom)
            insets
        }
        drawer.addView(ImageView(this).apply {
            setImageResource(R.drawable.romverse_app_icon)
            scaleType = ImageView.ScaleType.CENTER_INSIDE
            contentDescription = "ROMVERSE Companion"
            layoutParams = LinearLayout.LayoutParams(-1, dp(92))
        })
        drawer.addView(text("ROMVERSE COMPANION", 17f, Color.WHITE, true).apply {
            gravity = Gravity.CENTER
            letterSpacing = 0.08f
        })
        drawer.addView(text("SWIPE NAVIGATION  •  GALAXY INTERFACE", 10f, cyan, true).apply {
            gravity = Gravity.CENTER
        })
        drawer.addView(text("EXPLORE", 11f, violet, true))
        CompanionNavigation.drawerDestinations.forEach { destination ->
            val kind = destination.navKind()
            val button = RomverseNavButton(this, kind, displayMode()).apply {
                setOnClickListener { openDestination(destination) }
                layoutParams = LinearLayout.LayoutParams(-1, dp(58)).apply {
                    topMargin = dp(4)
                }
            }
            registerNavigationButton(kind, button)
            drawer.addView(button)
        }
        drawer.addView(space(dp(12)))
        drawer.addView(text(
            "Swipe from the left edge at any time. Your current work stays safely in place.",
            12f,
            muted,
            false,
        ).apply { gravity = Gravity.CENTER })
        drawerScroll.addView(drawer, FrameLayout.LayoutParams(-1, -2))
        val drawerWidth = dp(340).coerceAtMost((resources.displayMetrics.widthPixels * 0.86f).roundToInt())
        root.addView(drawerScroll, DrawerLayout.LayoutParams(drawerWidth, -1).apply {
            gravity = GravityCompat.START
        })
        selectNavigation(NavKind.COMMAND)
        root.post { homeScroll?.scrollTo(0, 0) }
        return root
    }

    private fun CompanionDestination.navKind(): NavKind = when (this) {
        CompanionDestination.HOME -> NavKind.COMMAND
        CompanionDestination.LINK -> NavKind.LINK
        CompanionDestination.LIVE_CONSOLE -> NavKind.CONSOLE
        CompanionDestination.VITALIS -> NavKind.QUANTUM
        CompanionDestination.MORE -> NavKind.MORE
        CompanionDestination.LIFELINE -> NavKind.RECOVERY
        CompanionDestination.DEVICE_DNA -> NavKind.DEVICE_DNA
        CompanionDestination.ASCENSION_PROTOCOL -> NavKind.ASCENSION
        CompanionDestination.APP_LAUNCHPAD -> NavKind.APPS
        CompanionDestination.MEMBERS -> NavKind.MEMBERS
        CompanionDestination.GALAXY -> NavKind.GALAXY
        CompanionDestination.SETTINGS -> NavKind.SETTINGS
        CompanionDestination.ABOUT -> NavKind.ABOUT
    }

    private fun registerNavigationButton(kind: NavKind, button: RomverseNavButton) {
        navigationButtons.getOrPut(kind) { mutableListOf() }.add(button)
    }

    private fun selectNavigation(kind: NavKind) {
        navigationButtons.forEach { (candidate, buttons) ->
            buttons.forEach { it.activeSelection = candidate == kind }
        }
    }

    private fun clearSectionPage() {
        sectionPage?.let { page -> (page.parent as? FrameLayout)?.removeView(page) }
        sectionPage = null
    }

    private fun showHome() {
        currentRoute = CompanionRoute.HOME
        clearSectionPage()
        navigationTitleView?.text = "COMMAND DECK"
        selectNavigation(NavKind.COMMAND)
        navigationDrawer?.closeDrawer(GravityCompat.START)
        homeScroll?.post { homeScroll?.smoothScrollTo(0, 0) }
        applyPrivacyCurtain()
    }

    private fun openDestination(destination: CompanionDestination) {
        navigationDrawer?.closeDrawer(GravityCompat.START)
        when (destination) {
            CompanionDestination.HOME -> showHome()
            CompanionDestination.LINK -> {
                currentRoute = CompanionRoute.LINK
                clearSectionPage()
                navigationTitleView?.text = "ROMVERSE LINK"
                selectNavigation(NavKind.LINK)
                homeScroll?.post {
                    homeScroll?.smoothScrollTo(0, pairSyncCard?.top ?: 0)
                }
            }
            CompanionDestination.LIVE_CONSOLE -> showSection(
                "LIVE CONSOLE",
                "Genuine Desktop Nexus, Pathfinder, Guardian, and operation events received through ROMVERSE Link.",
            )
            CompanionDestination.VITALIS -> showSection(
                "VITALIS",
                "Read-only health evidence, diagnostics, and desktop telemetry.",
            )
            CompanionDestination.MORE -> navigationDrawer?.openDrawer(GravityCompat.START)
            CompanionDestination.LIFELINE -> showSection(
                "LIFELINE",
                "Read-only System Scan and guided repair knowledge protected by Guardian Core.",
            )
            CompanionDestination.DEVICE_DNA -> showSection(
                "DEVICE DNA",
                "Evidence-backed Desktop device and firmware capabilities. No phone-control authority is transferred.",
            )
            CompanionDestination.ASCENSION_PROTOCOL -> showSection(
                "ASCENSION PROTOCOL",
                "Follow Desktop root preparation with Guardian proof at every stage.",
            )
            CompanionDestination.APP_LAUNCHPAD -> showSection(
                "APP LAUNCHPAD",
                "Safely stage and verify APK packages before Android installation.",
            )
            CompanionDestination.MEMBERS -> showSection(
                "ROMVERSE MEMBERS",
                "Secure browser sign-in and server-verified membership status.",
            )
            CompanionDestination.GALAXY -> showSection(
                "ROMVERSE GALAXY",
                "Optional ROMVERSE ecosystem for Recipes, Device Atlas, guides, and community services.",
            )
            CompanionDestination.SETTINGS -> showSection(
                "ROMVERSE SETTINGS",
                "Control online intelligence, privacy, accessibility, and account service configuration.",
            )
            CompanionDestination.ABOUT -> showSection(
                "ABOUT ROMVERSE COMPANION",
                "ROMVERSE Companion\nBuild. Optimize. Perfect.\n\nA RadForge Labs Project",
            )
        }
        applyPrivacyCurtain()
    }

    private fun restoreRoute(route: CompanionRoute) {
        when (route) {
            CompanionRoute.HOME -> showHome()
            CompanionRoute.LINK -> openDestination(CompanionDestination.LINK)
            else -> {
                val title = route.sectionTitle ?: return showHome()
                showSection(title, route.restoredDetail)
            }
        }
    }

    private fun navigationKindForSection(title: String): NavKind? = when (title) {
        "DEVICE DNA" -> NavKind.DEVICE_DNA
        "ASCENSION PROTOCOL" -> NavKind.ASCENSION
        "LIVE CONSOLE" -> NavKind.CONSOLE
        "VITALIS" -> NavKind.QUANTUM
        "LIFELINE" -> NavKind.RECOVERY
        "APP LAUNCHPAD" -> NavKind.APPS
        "ROMVERSE MEMBERS" -> NavKind.MEMBERS
        "ROMVERSE GALAXY" -> NavKind.GALAXY
        "ROMVERSE SETTINGS" -> NavKind.SETTINGS
        "ABOUT ROMVERSE COMPANION" -> NavKind.ABOUT
        else -> null
    }

    private fun card(): LinearLayout = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        setPadding(
            dp(CompanionLayoutSpec.CARD_HORIZONTAL_PADDING_DP),
            dp(CompanionLayoutSpec.CARD_VERTICAL_PADDING_DP),
            dp(CompanionLayoutSpec.CARD_HORIZONTAL_PADDING_DP),
            dp(CompanionLayoutSpec.CARD_VERTICAL_PADDING_DP),
        )
        background = glassCardBackground()
        elevation = dp(2).toFloat()
        layoutParams = LinearLayout.LayoutParams(-1, -2).apply {
            bottomMargin = dp(CompanionLayoutSpec.CARD_GAP_DP)
        }
    }

    private fun metric(name: String, value: String, detail: String): TextView = text(
        "$name  •  $value\n$detail", 15f, Color.WHITE, false
    ).apply { setPadding(0, dp(12), 0, dp(12)) }

    private fun infoRow(name: String, value: String, detail: String): LinearLayout =
        LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(0, dp(10), 0, dp(10))
            addView(text(name.uppercase(), 11f, muted, true))
            addView(text(value, 14f, Color.WHITE, true).apply {
                setPadding(0, dp(2), 0, 0)
            })
            addView(text(detail, 11f, cyan, false).apply {
                setPadding(0, dp(2), 0, 0)
            })
        }

    private fun button(label: String): TextView = text(label, 13f, cyan, true).apply {
        gravity = Gravity.CENTER
        setPadding(dp(12), dp(16), dp(12), dp(16))
        setBackgroundColor("#1A2448".toColorInt())
        isClickable = true
        setOnClickListener { text = "PAIRING READY  •  OPEN ROMVERSE STUDIO" }
    }

    private fun text(value: String, size: Float, color: Int, bold: Boolean): TextView = TextView(this).apply {
        text = value
        textSize = size
        setTextColor(color)
        if (bold) setTypeface(typeface, android.graphics.Typeface.BOLD)
        includeFontPadding = false
        setPadding(0, dp(3), 0, dp(3))
    }

    private fun space(height: Int): View = View(this).apply {
        layoutParams = LinearLayout.LayoutParams(1, height)
    }

    private fun cosmicBackground() = GradientDrawable(
        GradientDrawable.Orientation.TL_BR,
        displayPalette().cosmicGradient.map(String::toColorInt).toIntArray(),
    )

    private fun outlinedPanel() = GradientDrawable().apply {
        setColor(panel)
        setStroke(dp(1), "#263650".toColorInt())
        cornerRadius = dp(11).toFloat()
    }

    private fun glassCardBackground() = GradientDrawable(
        GradientDrawable.Orientation.TL_BR,
        displayPalette().cardGradient.map(String::toColorInt).toIntArray(),
    ).apply {
        setStroke(dp(1), "#70405B82".toColorInt())
        cornerRadius = dp(14).toFloat()
    }

    /** Static translucent depth keeps the cosmic scene visible without costly live blur. */
    private fun glassSidebarBackground() = GradientDrawable(
        GradientDrawable.Orientation.TL_BR,
        displayPalette().sidebarGradient.map(String::toColorInt).toIntArray(),
    ).apply {
        setStroke(dp(1), "#9A45CFE8".toColorInt())
        cornerRadius = 0f
    }

    /** Layered translucent chrome for the persistent app bar and bottom navigation. */
    private fun glassBarBackground() = GradientDrawable(
        GradientDrawable.Orientation.TL_BR,
        displayPalette().barGradient.map(String::toColorInt).toIntArray(),
    ).apply {
        setStroke(dp(1), "#7545CFE8".toColorInt())
    }

    private fun dp(value: Int): Int = (value * resources.displayMetrics.density).roundToInt()

    private fun displayMode(): CompanionDisplayMode = CompanionDisplayMode.parse(
        userSettingsPrefs.getString("display_mode", null),
    )

    private fun displayPalette(): CompanionDisplayPalette =
        CompanionDisplayPolicy.palette(displayMode())

    @Suppress("DEPRECATION")
    private fun applySystemBarPalette() {
        val color = displayPalette().sectionSurface.toColorInt()
        window.setBackgroundDrawable(ColorDrawable(color))
        window.statusBarColor = color
        window.navigationBarColor = color
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            window.isNavigationBarContrastEnforced = false
            window.isStatusBarContrastEnforced = false
        }
        WindowCompat.getInsetsController(window, window.decorView).apply {
            isAppearanceLightStatusBars = false
            isAppearanceLightNavigationBars = false
        }
    }

    private fun timeGreeting(): String = when (Calendar.getInstance().get(Calendar.HOUR_OF_DAY)) {
        in 0..11 -> "Good morning"
        in 12..17 -> "Good afternoon"
        else -> "Good evening"
    }

    private fun greetingText(): String {
        val candidate = memberSession?.profile?.displayName
            ?: userSettingsPrefs.getString("preferred_display_name", null)
        return "${timeGreeting()}, ${CompanionPersonalization.displayNameOrDefault(candidate)}"
    }

    private fun refreshGreeting() {
        greetingView?.text = greetingText()
    }

    private fun refreshHomeHero() {
        val assessment = VitalisAssessmentEngine.assess(captureVitalisSnapshot())
        val console = desktopLiveConsoleStatus
        val running = console?.events?.firstOrNull { it.state == "running" }
        val guardianBlocked = console?.guardianReviewState == "blocked"
        val healthAttention = assessment.state != "OPTIMAL"
        val secureLink = hasSecureWirelessSession()
        val usbConnected = isUsbConnected()
        val headlineColor: Int
        val heroKind = CompanionHomeHeroPolicy.choose(
            guardianBlocked = guardianBlocked,
            missionRunning = running != null,
            healthAttention = healthAttention,
        )

        when (heroKind) {
            CompanionHomeHeroKind.GUARDIAN -> {
                homeHeroEyebrow?.text = "GUARDIAN"
                nextActionTitle?.text = "Review required"
                homeHeroDetail?.text =
                    "Desktop evidence reports a Guardian hold. Review the explanation before continuing."
                headlineColor = "#FFB454".toColorInt()
                nextActionButton?.text = "REVIEW LIVE EVIDENCE"
            }
            CompanionHomeHeroKind.MISSION -> {
                val mission = checkNotNull(running)
                homeHeroEyebrow?.text = "NEXUS MISSION"
                nextActionTitle?.text = mission.title
                homeHeroDetail?.text =
                    "${mission.stage}  •  ${mission.progressPercent}%  •  ${mission.stateLabel}"
                headlineColor = cyan
                nextActionButton?.text = "OPEN LIVE CONSOLE"
            }
            CompanionHomeHeroKind.VITALIS -> {
                homeHeroEyebrow?.text = "VITALIS"
                nextActionTitle?.text = "Device health needs attention"
                homeHeroDetail?.text =
                    "${assessment.state}  •  ${assessment.evidencePercent}% evidence coverage"
                headlineColor = "#FFB454".toColorInt()
                nextActionButton?.text = "OPEN VITALIS"
            }
            CompanionHomeHeroKind.ROM_HEALTH -> {
                homeHeroEyebrow?.text = "ROM HEALTH"
                nextActionTitle?.text = "${localDeviceIdentity.displayName}  •  ${assessment.state}"
                homeHeroDetail?.text =
                    "Read-only local evidence  •  ${assessment.evidencePercent}% coverage"
                headlineColor = "#72FFB2".toColorInt()
                nextActionButton?.text = if (secureLink || usbConnected) {
                    "OPEN VITALIS"
                } else {
                    "GO TO ROMVERSE LINK"
                }
            }
        }
        nextActionTitle?.setTextColor(headlineColor)
        homeHeroLink?.text = when {
            secureLink -> "●  ROMVERSE LINK  •  SECURELY PAIRED"
            usbConnected -> "●  USB CONNECTED  •  ROMVERSE LINK NOT PAIRED"
            else -> "?  ROMVERSE LINK  •  NOT CONNECTED"
        }
        homeHeroLink?.setTextColor(if (secureLink) "#72FFB2".toColorInt() else muted)
        homeHeroGuardian?.text = when {
            guardianBlocked -> "△  GUARDIAN  •  REVIEW REQUIRED"
            console?.guardianReviewState == "ready" -> "✓  GUARDIAN  •  READY"
            else -> "✓  GUARDIAN  •  READ-ONLY PROTECTION ACTIVE"
        }
        homeHeroGuardian?.setTextColor(
            if (guardianBlocked) "#FFB454".toColorInt() else "#72FFB2".toColorInt(),
        )
        homeHeroMission?.text = when {
            running != null -> "◉  ACTIVE  •  ${running.stage}  •  ${running.progressPercent}%"
            console == null -> "?  DESKTOP MISSION  •  LIVE STATE UNCONFIRMED"
            else -> "○  DESKTOP MISSION  •  NO ACTIVE RUNNING EVENT"
        }
    }

    private fun experienceMode(): CompanionExperienceMode =
        CompanionExperienceMode.parse(
            userSettingsPrefs.getString("experience_mode", null),
        )

    private fun actionBackground() = GradientDrawable(
        GradientDrawable.Orientation.LEFT_RIGHT,
        intArrayOf("#25134B".toColorInt(), "#102E58".toColorInt()),
    ).apply {
        setStroke(dp(1), violet)
        cornerRadius = dp(12).toFloat()
    }

    private fun selectedNavBackground() = GradientDrawable(
        GradientDrawable.Orientation.LEFT_RIGHT,
        intArrayOf("#522078".toColorInt(), "#241137".toColorInt()),
    ).apply {
        setStroke(dp(1), violet)
        cornerRadius = dp(9).toFloat()
    }

    private fun successBackground() = GradientDrawable().apply {
        setColor("#123D35".toColorInt())
        setStroke(dp(1), "#29D98B".toColorInt())
        cornerRadius = dp(12).toFloat()
    }

    private fun onlineStatusBadge(): TextView = text("●  CHECKING", 10f, muted, true).apply {
        gravity = Gravity.CENTER
        setPadding(dp(9), dp(5), dp(9), dp(5))
        background = outlinedPanel()
        contentDescription = "Checking ROMVERSE internet connectivity"
        check(networkStatusView == null) {
            "The persistent app bar is the only owner of ROMVERSE network status"
        }
        networkStatusView = this
        post { updateNetworkStatus() }
    }

    private fun updateNetworkStatus() {
        val manager = getSystemService(CONNECTIVITY_SERVICE) as ConnectivityManager
        val capabilities = manager.activeNetwork?.let(manager::getNetworkCapabilities)
        val online = capabilities?.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET) == true &&
            capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED)
        networkStatusView?.apply {
            text = if (online) "●  ONLINE" else "●  OFFLINE"
            setTextColor(if (online) "#35F0A2".toColorInt() else "#FF526D".toColorInt())
            contentDescription = if (online) {
                "ROMVERSE online intelligence available"
            } else {
                "ROMVERSE is offline"
            }
        }
        if (online && !lastNetworkOnline) {
            resumeRememberedLink()
        }
        lastNetworkOnline = online
    }

    private fun isUsbConnected(): Boolean {
        val deviceUsbState = registerReceiver(
            null,
            IntentFilter("android.hardware.usb.action.USB_STATE"),
        )?.getBooleanExtra("connected", false) == true
        if (deviceUsbState) return true
        val batteryState = registerReceiver(null, IntentFilter(Intent.ACTION_BATTERY_CHANGED))
        val poweredByUsb = batteryState?.getIntExtra(BatteryManager.EXTRA_PLUGGED, 0) ==
            BatteryManager.BATTERY_PLUGGED_USB
        if (poweredByUsb) return true
        val usb = getSystemService(USB_SERVICE) as UsbManager
        return usb.deviceList.isNotEmpty()
    }

    private fun showSection(title: String, detail: String) {
        currentRoute = CompanionRoute.fromSectionTitle(title)
        apkDetailView = null
        clearSectionPage()
        val host = sectionHost ?: return
        navigationDrawer?.closeDrawer(GravityCompat.START)
        navigationTitleView?.text = title
        navigationKindForSection(title)?.let(::selectNavigation)
        val overlay = FrameLayout(this).apply {
            setBackgroundColor(displayPalette().sectionSurface.toColorInt())
            elevation = 20f
        }
        overlay.addView(starfieldLayer(), FrameLayout.LayoutParams(-1, -1))
        sectionPage = overlay
        val shell = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(
                dp(CompanionLayoutSpec.CONTENT_HORIZONTAL_DP),
                dp(CompanionLayoutSpec.CONTENT_TOP_DP),
                dp(CompanionLayoutSpec.CONTENT_HORIZONTAL_DP),
                dp(CompanionLayoutSpec.CONTENT_BOTTOM_DP),
            )
        }
        val sectionScroll = ScrollView(this).apply {
            isFillViewport = true
            clipToPadding = false
            setBackgroundColor(Color.TRANSPARENT)
        }
        val panel = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(0, dp(12), 0, dp(32))
        }
        sectionScroll.addView(panel, FrameLayout.LayoutParams(-1, -2))
        shell.addView(sectionScroll, LinearLayout.LayoutParams(-1, 0, 1f))
        val detailView = text(detail, 15f, Color.WHITE, false).apply {
            setPadding(0, dp(4), 0, dp(16))
        }
        panel.addView(detailView)
        when (title) {
            "HOME" -> {
                val memory = ActivityManager.MemoryInfo().also {
                    (getSystemService(ACTIVITY_SERVICE) as ActivityManager).getMemoryInfo(it)
                }
                val usedRam = memory.totalMem - memory.availMem
                val ramPct = if (memory.totalMem > 0) {
                    ((usedRam * 100) / memory.totalMem).toInt().coerceIn(0, 100)
                } else 0
                val battery = (getSystemService(BATTERY_SERVICE) as BatteryManager)
                    .getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY).coerceIn(0, 100)
                val storage = StatFs(Environment.getDataDirectory().path)
                val storagePct = if (storage.totalBytes > 0) {
                    ((storage.totalBytes - storage.availableBytes) * 100 / storage.totalBytes).toInt()
                } else 0
                val overview = card()
                overview.addView(text("DEVICE PORTAL", 12f, violet, true))
                overview.addView(text(localDeviceIdentity.displayName, 20f, Color.WHITE, true))
                overview.addView(text(
                    "${if (localDeviceIdentity.verifiedExact) "VERIFIED EXACT" else "UNCONFIRMED"}  •  " +
                        "${localDeviceIdentity.rawModel}  •  ${localDeviceIdentity.codename}",
                    13f,
                    cyan,
                    false,
                ))
                overview.addView(infoRow(
                    "Android",
                    "${Build.VERSION.RELEASE}  •  API ${Build.VERSION.SDK_INT}",
                    "Live operating-system evidence",
                ))
                overview.addView(infoRow(
                    "Security patch",
                    Build.VERSION.SECURITY_PATCH.ifBlank { "Unavailable" },
                    "Verified locally",
                ))
                overview.addView(infoRow(
                    "Desktop Link",
                    if (pairingPrefs.getBoolean("paired", false)) "PAIRED"
                    else if (isUsbConnected()) "USB CONNECTED" else "OFFLINE",
                    "Guardian-protected connection",
                ))
                panel.addView(overview)
                panel.addView(space(dp(12)))

                val deviceDna = desktopDeviceDnaStatus
                val dnaCard = card()
                dnaCard.addView(text("DEVICE DNA  •  DESKTOP EVIDENCE", 12f, violet, true))
                if (deviceDna == null) {
                    dnaCard.addView(text("WAITING FOR A DESKTOP PROFILE", 16f, "#FFB454".toColorInt(), true))
                    dnaCard.addView(text(
                        "Pair with ROMVERSE Desktop and select an imported ROM project. Unknown evidence remains unconfirmed.",
                        12f,
                        muted,
                        false,
                    ))
                } else {
                    val dnaColor = if (deviceDna.state == "ready") {
                        "#72FFB2".toColorInt()
                    } else {
                        "#FFB454".toColorInt()
                    }
                    dnaCard.addView(text(deviceDna.headline, 16f, dnaColor, true))
                    dnaCard.addView(text(
                        "${deviceDna.project}  •  profile ${deviceDna.profileRef}…  •  " +
                            "${deviceDna.attentionCount} item(s) need attention",
                        12f,
                        Color.WHITE,
                        false,
                    ))
                    deviceDna.capabilities.take(4).forEach { capability ->
                        dnaCard.addView(infoRow(
                            capability.label,
                            capability.state,
                            capability.detail,
                        ))
                    }
                }
                dnaCard.addView(sectionAction("OPEN DEVICE DNA & CAPABILITY MAP") {
                    showSection(
                        "DEVICE DNA",
                        "Evidence-backed Desktop device and firmware capabilities. No phone-control authority is transferred.",
                    )
                })
                panel.addView(dnaCard)
                panel.addView(space(dp(12)))

                val health = card()
                val score = optimizerHealthScore(battery, storagePct, ramPct)
                health.addView(text("SYSTEM HEALTH  •  $score / 100", 12f, violet, true))
                health.addView(ResourceGaugeStripView(
                    this,
                    listOf(
                        GaugeMetric("BATTERY", battery, cyan),
                        GaugeMetric("STORAGE", storagePct, violet),
                        GaugeMetric("RAM", ramPct, "#4F7CFF".toColorInt()),
                    ),
                ))
                health.addView(text(
                    if (score >= 85) "System status is Optimal" else "System needs attention",
                    15f,
                    if (score >= 85) "#72FFB2".toColorInt() else "#FFB454".toColorInt(),
                    true
                ))
                panel.addView(health)
                panel.addView(space(dp(12)))

                val quick = card()
                quick.addView(text("QUICK ACTIONS", 12f, violet, true))
                quick.addView(sectionAction("OPEN VITALIS") {
                    showSection("VITALIS", "Live health evidence and Guardian-safe diagnostics.")
                })
                quick.addView(sectionAction("OPEN DEVICE DNA") {
                    showSection(
                        "DEVICE DNA",
                        "Evidence-backed Desktop device and firmware Capability Map.",
                    )
                })
                quick.addView(sectionAction("OPEN LIVE CONSOLE") {
                    showSection(
                        "LIVE CONSOLE",
                        "Genuine Desktop mission progress and explanations through ROMVERSE Link.",
                    )
                })
                quick.addView(sectionAction("OPEN LIFELINE") {
                    showSection("LIFELINE", "Read-only System Scan and guided repair knowledge.")
                })
                quick.addView(sectionAction("OPEN APP LAUNCHPAD") {
                    showSection("APP LAUNCHPAD", "Stage, fingerprint, and review APK packages safely.")
                })
                quick.addView(sectionAction("OPEN ASCENSION PROTOCOL") {
                    showSection(
                        "ASCENSION PROTOCOL",
                        "Follow Desktop root preparation with Guardian proof at every stage.",
                    )
                })
                panel.addView(quick)
                panel.addView(sectionAction("REFRESH DEVICE STATUS") {
                    updateHealthMetrics()
                    showSection(
                        "HOME",
                        "Device Portal refreshed from live local evidence."
                    )
                })
            }
            "DEVICE DNA" -> {
                val status = desktopDeviceDnaStatus
                if (status == null) {
                    val unavailable = card()
                    unavailable.addView(text("DEVICE DNA UNAVAILABLE", 17f, "#FFB454".toColorInt(), true))
                    unavailable.addView(text(
                        "Select a ROM Studio project with protected firmware on Desktop, then refresh ROMVERSE Link. Companion will not invent a profile.",
                        13f,
                        muted,
                        false,
                    ))
                    panel.addView(unavailable)
                } else {
                    val summary = card()
                    val summaryColor = if (status.state == "ready") {
                        "#72FFB2".toColorInt()
                    } else {
                        "#FFB454".toColorInt()
                    }
                    summary.addView(text(status.headline, 18f, summaryColor, true))
                    summary.addView(infoRow("Project", status.project, "Profile ${status.profileRef}…"))
                    summary.addView(infoRow(
                        "Evidence summary",
                        "${status.capabilities.size} capabilities",
                        "${status.warningCount} warning(s)  •  ${status.attentionCount} actionable item(s)",
                    ))
                    summary.addView(text(
                        "Execution authority: NONE  •  Bootloader relock: NEVER",
                        12f,
                        "#72FFB2".toColorInt(),
                        true,
                    ))
                    panel.addView(summary)
                    panel.addView(space(dp(12)))
                    fun addCapability(
                        target: LinearLayout,
                        capability: DesktopDeviceDnaCapability,
                    ) {
                        val capabilityColor = when (capability.state) {
                            "SUPPORTED" -> "#72FFB2".toColorInt()
                            "UNSUPPORTED" -> "#FF6685".toColorInt()
                            else -> "#FFB454".toColorInt()
                        }
                        val capabilityCard = card()
                        capabilityCard.addView(text(capability.state, 11f, capabilityColor, true))
                        capabilityCard.addView(text(capability.label, 16f, Color.WHITE, true))
                        capabilityCard.addView(text(capability.detail, 12f, muted, false))
                        target.addView(capabilityCard)
                        target.addView(space(dp(9)))
                    }
                    val initialCapabilityCount =
                        CompanionExperiencePolicy.initialCapabilityCount(
                            experienceMode(),
                            status.capabilities.size,
                        )
                    status.capabilities.take(initialCapabilityCount).forEach { capability ->
                        addCapability(panel, capability)
                    }
                    if (initialCapabilityCount < status.capabilities.size) {
                        val technicalEvidence = LinearLayout(this).apply {
                            orientation = LinearLayout.VERTICAL
                            visibility = View.GONE
                        }
                        status.capabilities.drop(initialCapabilityCount).forEach { capability ->
                            addCapability(technicalEvidence, capability)
                        }
                        panel.addView(technicalEvidence)
                        val hiddenCount = status.capabilities.size - initialCapabilityCount
                        val revealTechnical = sectionAction(
                            "SHOW $hiddenCount MORE TECHNICAL DECISION(S)",
                        ) {}
                        revealTechnical.setOnClickListener {
                            technicalEvidence.visibility = View.VISIBLE
                            revealTechnical.visibility = View.GONE
                            detailView.text =
                                "ARCANA  •  TECHNICAL EVIDENCE REVEALED\n\nAll Capability Map decisions are now visible for this view. Guardian and execution authority remain unchanged."
                        }
                        panel.addView(revealTechnical)
                    }
                    panel.addView(sectionAction("COPY PRIVACY-SAFE DNA REPORT") {
                        val clipboard = getSystemService(CLIPBOARD_SERVICE) as ClipboardManager
                        clipboard.setPrimaryClip(
                            ClipData.newPlainText(
                                "ROMVERSE Device DNA",
                                status.privacySafeReport(),
                            ),
                        )
                        detailView.text =
                            "DEVICE DNA REPORT COPIED\n\nThe bounded report excludes source paths, full hashes, commands, approvals, and device-write authority."
                        logActivity("Privacy-safe Device DNA report copied")
                    })
                }
                addLinkRefreshAction(
                    panel,
                    detailView,
                    "DEVICE DNA",
                    "REFRESHING DEVICE DNA…\n\nRequesting fresh authenticated Desktop evidence.",
                )
            }
            "VITALIS" -> {
                val snapshot = captureVitalisSnapshot()
                val assessment = VitalisAssessmentEngine.assess(snapshot)
                val battery = snapshot.batteryPercent
                val storagePct = snapshot.storageUsedPercent
                val ramPct = snapshot.ramUsedPercent
                panel.addView(text("LIVE RESOURCE GRAPH", 12f, cyan, true))
                panel.addView(text("PULSE TELEMETRY • LIVE LOCAL EVIDENCE", 11f, violet, true))
                val batteryColor = when {
                    battery == null -> muted
                    battery < 20 -> "#FF6685".toColorInt()
                    battery < 40 -> "#FFB454".toColorInt()
                    else -> cyan
                }
                val storageColor = when {
                    storagePct == null -> muted
                    storagePct >= 90 -> "#FF6685".toColorInt()
                    storagePct >= 75 -> "#FFB454".toColorInt()
                    else -> violet
                }
                val ramColor = when {
                    ramPct == null -> muted
                    ramPct >= 90 -> "#FF6685".toColorInt()
                    ramPct >= 80 -> "#FFB454".toColorInt()
                    else -> "#72FFB2".toColorInt()
                }
                val healthColor = when (assessment.state) {
                    "OPTIMAL" -> "#72FFB2".toColorInt()
                    "ACTION RECOMMENDED" -> "#FF6685".toColorInt()
                    else -> "#FFB454".toColorInt()
                }
                panel.addView(text("SYSTEM STATUS  •  ${assessment.state}", 17f, healthColor, true))
                panel.addView(text(
                    "Guardian health score: ${assessment.score?.let { "$it / 100" } ?: "UNCONFIRMED"}",
                    14f,
                    Color.WHITE,
                    true,
                ))
                panel.addView(text(
                    "Evidence coverage: ${assessment.evidencePercent}% • unknown evidence is never treated as healthy",
                    12f,
                    muted,
                    false,
                ))
                panel.addView(ResourceGaugeStripView(
                    this,
                    listOf(
                        GaugeMetric("BATTERY", battery, batteryColor),
                        GaugeMetric("STORAGE", storagePct, storageColor),
                        GaugeMetric("RAM", ramPct, ramColor),
                    ),
                ))
                val findingsCard = card()
                findingsCard.addView(text("DIAGNOSIS & SAFE NEXT ACTIONS", 12f, violet, true))
                assessment.findings.forEach { finding ->
                    val findingColor = when (finding.severity) {
                        VitalisSeverity.HEALTHY -> "#72FFB2".toColorInt()
                        VitalisSeverity.CRITICAL -> "#FF6685".toColorInt()
                        else -> "#FFB454".toColorInt()
                    }
                    findingsCard.addView(text(finding.title, 14f, findingColor, true))
                    findingsCard.addView(text(finding.detail, 12f, Color.WHITE, false))
                    findingsCard.addView(text("Next: ${finding.nextAction}", 12f, muted, false))
                }
                panel.addView(findingsCard)

                val technicalEvidence = LinearLayout(this).apply {
                    orientation = LinearLayout.VERTICAL
                }
                val liveConsole = card()
                val scanComplete = assessment.evidencePercent == 100
                liveConsole.addView(text("ROMVERSE LIVE CONSOLE  •  VITALIS", 12f, violet, true))
                liveConsole.addView(text(
                    if (scanComplete) "LOCAL EVIDENCE SCAN COMPLETE" else "LOCAL EVIDENCE NEEDS ATTENTION",
                    16f,
                    if (scanComplete) "#72FFB2".toColorInt() else "#FFB454".toColorInt(),
                    true,
                ))
                liveConsole.addView(ProgressBar(
                    this,
                    null,
                    android.R.attr.progressBarStyleHorizontal,
                ).apply {
                    max = 100
                    progress = assessment.evidencePercent
                    progressTintList = ColorStateList.valueOf(if (scanComplete) cyan else "#FFB454".toColorInt())
                    progressBackgroundTintList = ColorStateList.valueOf("#202A43".toColorInt())
                    contentDescription = "Vitalis evidence progress ${assessment.evidencePercent} percent"
                    layoutParams = LinearLayout.LayoutParams(-1, dp(14)).apply {
                        topMargin = dp(10)
                        bottomMargin = dp(10)
                    }
                })
                liveConsole.addView(text("WHAT HAPPENED", 10f, cyan, true))
                liveConsole.addView(text(
                    "Vitalis captured ${assessment.evidencePercent}% of its bounded local health evidence and produced ${assessment.findings.size} evidence result(s).",
                    12f,
                    Color.WHITE,
                    false,
                ))
                liveConsole.addView(text("WHY", 10f, violet, true))
                liveConsole.addView(text(
                    "The same evidence model powers the gauges, Guardian score, Lifeline baseline, and fresh comparison.",
                    12f,
                    muted,
                    false,
                ))
                liveConsole.addView(text("NEXT", 10f, cyan, true))
                liveConsole.addView(text(
                    assessment.findings.joinToString("\n") { "• ${it.nextAction}" },
                    12f,
                    Color.WHITE,
                    false,
                ))
                technicalEvidence.addView(liveConsole)

                if (assessment.score == null || OptimizerTrendHistory.needsGuidedRecovery(assessment.score)) {
                    val nextAction = card()
                    nextAction.addView(text("NEXT SAFE ACTION", 12f, cyan, true))
                    nextAction.addView(text(
                        "Open Lifeline for a fresh local diagnostic, plain-language " +
                            "checkpoints, and before/after evidence. No setting, partition, root state, " +
                            "or user data changes automatically.",
                        13f,
                        muted,
                        false,
                    ))
                    nextAction.addView(sectionAction("OPEN LIFELINE") {
                        showSection(
                            "LIFELINE",
                            "Read-only System Scan and guided recovery with fresh verification.",
                        )
                    })
                    panel.addView(nextAction)
                }
                val trend = if (battery != null && storagePct != null && ramPct != null) {
                    recordOptimizerSnapshot(battery, storagePct, ramPct)
                } else {
                    readOptimizerHistory().let {
                        it.copy(reason = "Current sample not saved because core evidence is unconfirmed. ${it.reason}")
                    }
                }
                technicalEvidence.addView(text("RECENT HEALTH TREND", 12f, cyan, true).apply {
                    setPadding(0, dp(12), 0, dp(4))
                })
                val trendStatus = text(
                    trend.reason,
                    11f,
                    if (!trend.valid) "#FF6685".toColorInt() else if (trend.integrityVerified) "#72FFB2".toColorInt() else "#FFB454".toColorInt(),
                    true,
                )
                panel.addView(trendStatus)
                val trendView = ResourceHistoryView(
                    this,
                    trend.snapshots.map { it.batteryPercent.toFloat() },
                    trend.snapshots.map { it.storagePercent.toFloat() },
                    trend.snapshots.map { it.ramPercent.toFloat() },
                ).apply {
                    layoutParams = LinearLayout.LayoutParams(-1, dp(130))
                    contentDescription = "Recent Battery, Storage, and RAM trend graph"
                }
                technicalEvidence.addView(trendView)
                technicalEvidence.addView(text(
                    "Battery cyan  •  Storage violet  •  RAM green",
                    11f,
                    muted,
                    false,
                ))
                addTechnicalEvidenceDisclosure(
                    panel,
                    "Vitalis",
                    technicalEvidence,
                    detailView,
                )
                if (!trend.valid) {
                    panel.addView(sectionAction("RESET DAMAGED TREND HISTORY") {
                        AlertDialog.Builder(this)
                            .setTitle("Reset local health trend?")
                            .setMessage(
                                "The saved trend failed integrity checks. This removes only Companion's local graph history. " +
                                    "It does not change the phone, pairing, projects, or desktop evidence."
                            )
                            .setNegativeButton("Cancel", null)
                            .setPositiveButton("Reset") { _, _ ->
                                val cleared = optimizerPrefs.edit()
                                    .remove("history_v1")
                                    .remove("battery")
                                    .remove("storage")
                                    .remove("ram")
                                    .commit()
                                detailView.text = if (cleared) {
                                    "LOCAL HEALTH TREND RESET\n\nThe damaged graph history was removed. Live phone health evidence was not changed."
                                } else {
                                    "TREND RESET NEEDS ATTENTION\n\nAndroid could not preserve the reset. Existing data was left in place."
                                }
                                if (cleared) showSection("VITALIS", "Live health evidence and Guardian-safe diagnostics.")
                            }
                            .show()
                    })
                }
                panel.addView(sectionAction("REFRESH HEALTH DATA") {
                    updateHealthMetrics()
                    val report = buildRepairReport()
                    latestRepairReport = report
                    saveRepairReceipt(report)
                    detailView.text = "VITALIS REFRESH COMPLETE\n\n$report"
                    showSection("VITALIS", "Live health evidence and Guardian-safe diagnostics.")
                })
                panel.addView(sectionAction("OPEN ANDROID BATTERY SETTINGS") {
                    startActivity(Intent(Settings.ACTION_BATTERY_SAVER_SETTINGS))
                })
                panel.addView(sectionAction("OPEN ANDROID STORAGE SETTINGS") {
                    startActivity(Intent(Settings.ACTION_INTERNAL_STORAGE_SETTINGS))
                })
                lateinit var cleanupButton: Button
                cleanupButton = sectionAction("PREVIEW SAFE COMPANION CLEANUP") {
                    startCompanionCacheCleanup(detailView, cleanupButton)
                }
                panel.addView(cleanupButton)
                panel.addView(sectionAction("ANALYZE & SHOW RECOMMENDATIONS") {
                    detailView.text = "VITALIS ANALYSIS  •  ${assessment.state}\n\n" +
                        assessment.findings.joinToString("\n\n") {
                            "${it.title}\n${it.detail}\nNext: ${it.nextAction}"
                        } +
                        "\n\nGuardian-safe guidance only; no app, setting, partition, or user data was changed."
                    logActivity("Optimizer analysis completed")
                })
                panel.addView(sectionAction("COPY OPTIMIZER REPORT") {
                    val report = buildRepairReport()
                    val clipboard = getSystemService(CLIPBOARD_SERVICE) as ClipboardManager
                    clipboard.setPrimaryClip(ClipData.newPlainText("ROMVERSE Vitalis report", report))
                    detailView.text = "OPTIMIZER REPORT COPIED\n\nThe read-only report is ready to paste into a support request or desktop Guardian review."
                    logActivity("Optimizer report copied")
                })
            }
            "LIVE CONSOLE" -> {
                val status = desktopLiveConsoleStatus
                val overview = card()
                overview.addView(text("ROMVERSE LIVE CONSOLE  •  LINK V6", 12f, violet, true))
                if (status == null) {
                    overview.addView(text(
                        "PAIR WITH ROMVERSE DESKTOP",
                        18f,
                        "#FFB454".toColorInt(),
                        true,
                    ))
                    overview.addView(text(
                        "No authenticated Live Console snapshot is available. Pair through ROMVERSE Link, " +
                            "then create or run a real Desktop mission. Companion will never invent activity.",
                        13f,
                        muted,
                        false,
                    ))
                } else {
                    val trusted = status.integrity == "trusted"
                    overview.addView(text(
                        if (trusted) "●  TRUSTED REDACTED EVENT LEDGER" else "●  EVENT LEDGER NEEDS ATTENTION",
                        15f,
                        if (trusted) "#72FFB2".toColorInt() else "#FFB454".toColorInt(),
                        true,
                    ))
                    overview.addView(infoRow(
                        "Nexus mission",
                        status.nexusObjective.replace('-', ' ').uppercase(),
                        "Status: ${status.nexusStatus.replace('-', ' ')}",
                    ))
                    overview.addView(infoRow(
                        "Pathfinder position",
                        status.nexusCurrentStage.ifBlank { "No active route" },
                        "${status.nexusResearchCount} research requirement(s)",
                    ))
                    overview.addView(infoRow(
                        "Guardian review",
                        status.guardianReviewState.uppercase(),
                        "Execution authority: NONE  •  Bootloader relock: NEVER",
                    ))
                }
                panel.addView(overview)
                panel.addView(space(dp(12)))
                if (status != null && status.events.isNotEmpty()) {
                    status.events.forEach { event ->
                        val eventCard = card()
                        val stateColor = when (event.state) {
                            "succeeded" -> "#72FFB2".toColorInt()
                            "failed" -> "#FF6685".toColorInt()
                            "blocked", "attention" -> "#FFB454".toColorInt()
                            else -> cyan
                        }
                        eventCard.addView(text(
                            "${event.source.uppercase()}  •  ${event.stateLabel}",
                            11f,
                            stateColor,
                            true,
                        ))
                        eventCard.addView(text(event.title, 17f, Color.WHITE, true))
                        eventCard.addView(ProgressBar(
                            this,
                            null,
                            android.R.attr.progressBarStyleHorizontal,
                        ).apply {
                            max = 100
                            progress = event.progressPercent
                            progressTintList = ColorStateList.valueOf(stateColor)
                            progressBackgroundTintList = ColorStateList.valueOf("#202A43".toColorInt())
                            contentDescription = "${event.title} progress ${event.progressPercent} percent"
                            layoutParams = LinearLayout.LayoutParams(-1, dp(14)).apply {
                                topMargin = dp(10)
                                bottomMargin = dp(10)
                            }
                        })
                        eventCard.addView(text("WHAT HAPPENED", 10f, cyan, true))
                        eventCard.addView(text(event.summary, 13f, Color.WHITE, false))
                        eventCard.addView(text("WHY", 10f, violet, true))
                        eventCard.addView(text(event.explanation, 13f, muted, false))
                        eventCard.addView(text("NEXT", 10f, cyan, true))
                        eventCard.addView(text(event.nextAction, 13f, Color.WHITE, false))
                        eventCard.addView(text(
                            "Confidence: ${event.confidence.replace('-', ' ')}  •  Guardian protected  •  ${event.updatedAt}",
                            11f,
                            muted,
                            false,
                        ))
                        panel.addView(eventCard)
                        panel.addView(space(dp(10)))
                    }
                } else if (status != null) {
                    val empty = card()
                    empty.addView(text("NO GENUINE EVENTS YET", 14f, cyan, true))
                    empty.addView(text(
                        "The Desktop ledger is trusted but empty. Start a real ROM Studio or Nexus operation; " +
                            "ROMVERSE will not display decorative progress.",
                        13f,
                        muted,
                        false,
                    ))
                    panel.addView(empty)
                }
                val rawTerminalEvidence = LinearLayout(this).apply {
                    orientation = LinearLayout.VERTICAL
                }
                if (status != null) {
                    val attentionCount = status.rawTerminalRecords.count { !it.success }
                    val terminalSummary = card()
                    terminalSummary.addView(text(
                        "RAW TERMINAL SUMMARY",
                        12f,
                        violet,
                        true,
                    ))
                    terminalSummary.addView(text(
                        when {
                            attentionCount > 0 -> "$attentionCount READ-ONLY CHECK(S) NEED ATTENTION"
                            status.rawTerminalRecords.isNotEmpty() ->
                                "${status.rawTerminalRecords.size} READ-ONLY CHECK(S) VERIFIED"
                            else -> "NO APPROVED RAW OUTPUT YET"
                        },
                        14f,
                        if (attentionCount > 0) "#FFB454".toColorInt() else cyan,
                        true,
                    ))
                    panel.addView(terminalSummary)
                }
                if (status != null && status.rawTerminalRecords.isNotEmpty()) {
                    status.rawTerminalRecords.forEach { record ->
                        val terminal = card()
                        terminal.addView(text(
                            "RAW TERMINAL  •  ${if (record.success) "READ-ONLY CHECK COMPLETE" else "CHECK NEEDS ATTENTION"}",
                            12f,
                            if (record.success) "#72FFB2".toColorInt() else "#FFB454".toColorInt(),
                            true,
                        ))
                        terminal.addView(text(record.title, 16f, Color.WHITE, true))
                        terminal.addView(text(
                            record.lines.joinToString("\n"),
                            12f,
                            cyan,
                            false,
                        ))
                        terminal.addView(text(
                            "Privacy-filtered on Desktop  •  ${status.rawTerminalIntegrity.replace('-', ' ')}  •  commands from Companion: BLOCKED",
                            11f,
                            muted,
                            false,
                        ))
                        rawTerminalEvidence.addView(terminal)
                        rawTerminalEvidence.addView(space(dp(10)))
                    }
                } else {
                    val terminal = card()
                    terminal.addView(text("RAW TERMINAL  •  NO APPROVED OUTPUT YET", 12f, violet, true))
                    terminal.addView(text(
                        "Run a supported read-only check in Desktop Command Console. Only bounded, privacy-filtered " +
                            "results can appear here; device lists, host details, arbitrary commands, and execution authority are excluded.",
                        13f,
                        muted,
                        false,
                    ))
                    rawTerminalEvidence.addView(terminal)
                }
                addTechnicalEvidenceDisclosure(
                    panel,
                    "Live Console",
                    rawTerminalEvidence,
                    detailView,
                )
                addLinkRefreshAction(
                    panel,
                    detailView,
                    "LIVE CONSOLE",
                    "REFRESHING LIVE CONSOLE…\n\nRequesting a fresh read-only Link snapshot.",
                )
            }
            "ASCENSION PROTOCOL" -> {
                val status = desktopAscensionStatus
                val ascension = card()
                val technicalEvidence = LinearLayout(this).apply {
                    orientation = LinearLayout.VERTICAL
                }
                ascension.addView(text(
                    if (status == null) {
                        "ASCENSION PROTOCOL  •  AWAITING DESKTOP LINK"
                    } else {
                        "ASCENSION PROTOCOL  •  DESKTOP SYNCHRONIZED"
                    },
                    12f,
                    violet,
                    true,
                ))
                if (status == null) {
                    ascension.addView(text(
                        "PAIR WITH ROMVERSE DESKTOP",
                        18f,
                        "#FFB454".toColorInt(),
                        true,
                    ))
                    ascension.addView(text(
                        "Connect through ROMVERSE Link to view the exact root-preparation stage. " +
                            "Companion never receives flash commands, image hashes, serial numbers, approvals, or execution authority.",
                        13f,
                        muted,
                        false,
                    ))
                } else {
                    val stateColor = if (status.state == "review_ready") {
                        "#72FFB2".toColorInt()
                    } else if (status.state == "blocked") {
                        "#FFB454".toColorInt()
                    } else cyan
                    ascension.addView(text(status.stateLabel, 18f, stateColor, true))
                    if (status.stageNumber > 0) {
                        ascension.addView(text(
                            "STAGE ${status.stageNumber} OF 9  •  ${status.stageTitle.uppercase()}",
                            12f,
                            cyan,
                            true,
                        ))
                    }
                    ascension.addView(ProgressBar(
                        this,
                        null,
                        android.R.attr.progressBarStyleHorizontal,
                    ).apply {
                        max = 100
                        progress = status.stagePercent
                        progressTintList = ColorStateList.valueOf(stateColor)
                        progressBackgroundTintList = ColorStateList.valueOf("#202A43".toColorInt())
                        contentDescription = "Ascension progress ${status.stagePercent} percent"
                        layoutParams = LinearLayout.LayoutParams(-1, dp(16)).apply {
                            topMargin = dp(12)
                            bottomMargin = dp(12)
                        }
                    })
                    technicalEvidence.addView(infoRow(
                        "Project",
                        status.project.ifBlank { "Desktop project" },
                        "Project name only; firmware paths and hashes stay on Desktop",
                    ))
                    ascension.addView(infoRow(
                        if (status.state == "not_started") "Recommended route" else "Root route",
                        when (status.method) {
                            "magisk" -> "Magisk"
                            "kernelsu_lkm" -> "KernelSU LKM"
                            else -> "Not selected"
                        },
                        "Selected from exact source and device evidence",
                    ))
                    if (status.method != "none") {
                        if (status.managerState == "verified") {
                            ascension.addView(text(
                                "OFFICIAL ROOT TOOL  •  VERIFIED",
                                11f,
                                "#72FFB2".toColorInt(),
                                true,
                            ))
                            technicalEvidence.addView(infoRow(
                                "Manager file",
                                status.managerAsset,
                                "Exact stable APK revalidated by ROMVERSE Desktop",
                            ))
                            technicalEvidence.addView(infoRow(
                                "Official source",
                                status.managerRepository,
                                "Release ${status.managerTag}  •  package and signing certificate verified",
                            ))
                            technicalEvidence.addView(infoRow(
                                "Integrity reference",
                                status.managerSha256Ref,
                                "First 16 characters only; the full SHA-256 stays on Desktop",
                            ))
                            val launchTarget = AscensionManagerLaunchPolicy.target(status)
                            val installedSigner = launchTarget?.let {
                                installedPackageSignerSha256(it.packageName)
                            }
                            val launchIntent = launchTarget?.let {
                                packageManager.getLaunchIntentForPackage(it.packageName)
                            }
                            when {
                                launchTarget == null -> ascension.addView(text(
                                    "Manager launch unavailable because the verified route identity is incomplete.",
                                    12f,
                                    "#FF6685".toColorInt(),
                                    false,
                                ))
                                installedSigner == launchTarget.signerSha256 &&
                                    launchIntent != null -> {
                                    ascension.addView(sectionAction(
                                        "CONTINUE IN ${launchTarget.displayName.uppercase()}",
                                    ) {
                                        openVerifiedAscensionManager(launchTarget)
                                    })
                                    ascension.addView(text(
                                        "Opens the verified official manager only. ROMVERSE Companion cannot patch, root, reboot, flash, wipe, unlock, or relock your phone.",
                                        11f,
                                        muted,
                                        false,
                                    ))
                                }
                                installedSigner == null -> ascension.addView(text(
                                    "MANAGER NOT INSTALLED ON THIS PHONE\nComplete the approved Desktop handoff first. Reopen or refresh this section after Android finishes installation.",
                                    12f,
                                    "#FFB454".toColorInt(),
                                    false,
                                ))
                                else -> ascension.addView(text(
                                    "INSTALLED MANAGER BLOCKED\nThe package signing certificate does not match the pinned official signer. Companion will not open it.",
                                    12f,
                                    "#FF6685".toColorInt(),
                                    false,
                                ))
                            }
                        } else {
                            ascension.addView(text(
                                "ROOT TOOL  •  AWAITING VERIFICATION",
                                11f,
                                "#FFB454".toColorInt(),
                                true,
                            ))
                            ascension.addView(text(
                                "ROMVERSE will retrieve the current stable manager from its official repository and verify the complete file, package identity, and signing certificate before creating a patch capsule.",
                                12f,
                                muted,
                                false,
                            ))
                        }
                    }
                    technicalEvidence.addView(infoRow(
                        "Patch target",
                        status.targetPartition.ifBlank { "Not proven yet" },
                        "Desktop keeps the source-bound image and rollback evidence",
                    ))
                    ascension.addView(infoRow(
                        "Guardian gates",
                        if (status.blockerCount == 0) "READY" else "${status.blockerCount} TO RESOLVE",
                        "Resolve gates on Desktop; Companion cannot approve a write",
                    ))
                    if (status.romverseAction.isNotBlank()) {
                        ascension.addView(text("ROMVERSE IS HANDLING", 11f, "#72FFB2".toColorInt(), true))
                        ascension.addView(text(status.romverseAction, 13f, Color.WHITE, false))
                    }
                    ascension.addView(text("WHAT HAPPENS NEXT", 11f, cyan, true))
                    ascension.addView(text(status.nextStep, 13f, Color.WHITE, false))
                    if (status.whyItMatters.isNotBlank()) {
                        ascension.addView(text("WHY THIS MATTERS", 11f, violet, true))
                        ascension.addView(text(status.whyItMatters, 13f, muted, false))
                    }
                }
                panel.addView(ascension)
                panel.addView(space(dp(12)))
                if (technicalEvidence.childCount > 0) {
                    addTechnicalEvidenceDisclosure(
                        panel,
                        "Ascension Protocol",
                        technicalEvidence,
                        detailView,
                    )
                }
                val boundary = card()
                boundary.addView(text("GUARDIAN BOUNDARY", 12f, cyan, true))
                boundary.addView(text(
                    "Phone changed: NO\nExecution authority: NONE\nBootloader relock: PERMANENTLY PROHIBITED\n\n" +
                        "Continue on Desktop for source verification, official manager acquisition, image patching, backup, and final human review.",
                    13f,
                    Color.WHITE,
                    false,
                ))
                panel.addView(boundary)
                addLinkRefreshAction(
                    panel,
                    detailView,
                    "ASCENSION PROTOCOL",
                    "REFRESHING ASCENSION STATUS…\n\nROMVERSE is requesting read-only telemetry from the approved Desktop session.",
                )
            }
            "LIFELINE" -> {
                val lifelineSession = loadCompanionRepairSession()
                detailView.text = companionRepairSessionSummary(lifelineSession)
                val checkpoints = lifelineSession?.let(::repairSessionCheckpoints).orEmpty()
                val reviewedCount = lifelineSession?.getJSONArray("reviewed")?.let { reviewed ->
                    (0 until reviewed.length()).count { reviewed.optBoolean(it) }
                } ?: 0
                val lifelineStatus = lifelineSession?.optString("status").orEmpty()
                val consoleProgress = when {
                    lifelineSession == null -> 0
                    lifelineStatus == "comparison_complete" -> 100
                    checkpoints.isEmpty() -> 20
                    else -> 20 + (reviewedCount * 60 / checkpoints.size)
                }
                val lifelineConsole = card()
                lifelineConsole.addView(text("ROMVERSE LIVE CONSOLE  •  LIFELINE", 12f, violet, true))
                lifelineConsole.addView(text(
                    when {
                        lifelineSession == null -> "WAITING FOR A GENUINE BASELINE"
                        lifelineStatus == "comparison_complete" -> "FRESH EVIDENCE COMPARED"
                        lifelineStatus == "ready_for_comparison" || lifelineStatus == "ready_for_verification" ->
                            "READY FOR FRESH LOCAL SCAN"
                        else -> "GUIDED CHECKPOINTS IN PROGRESS"
                    },
                    16f,
                    when {
                        lifelineSession == null -> "#FFB454".toColorInt()
                        lifelineStatus == "comparison_complete" -> "#72FFB2".toColorInt()
                        else -> cyan
                    },
                    true,
                ))
                lifelineConsole.addView(ProgressBar(
                    this,
                    null,
                    android.R.attr.progressBarStyleHorizontal,
                ).apply {
                    max = 100
                    progress = consoleProgress
                    progressTintList = ColorStateList.valueOf(
                        if (lifelineStatus == "comparison_complete") "#72FFB2".toColorInt() else cyan,
                    )
                    progressBackgroundTintList = ColorStateList.valueOf("#202A43".toColorInt())
                    contentDescription = "Lifeline evidence progress $consoleProgress percent"
                    layoutParams = LinearLayout.LayoutParams(-1, dp(14)).apply {
                        topMargin = dp(10)
                        bottomMargin = dp(10)
                    }
                })
                lifelineConsole.addView(text("WHAT HAPPENED", 10f, cyan, true))
                lifelineConsole.addView(text(
                    if (lifelineSession == null) {
                        "No Lifeline session exists, so ROMVERSE is not displaying simulated repair progress."
                    } else {
                        "A private local baseline exists and $reviewedCount/${checkpoints.size} evidence-based checkpoints are reviewed."
                    },
                    12f,
                    Color.WHITE,
                    false,
                ))
                lifelineConsole.addView(text("WHY", 10f, violet, true))
                lifelineConsole.addView(text(
                    "Lifeline compares bounded before-and-after evidence. A checkmark records review only and never proves a repair.",
                    12f,
                    muted,
                    false,
                ))
                lifelineConsole.addView(text("NEXT", 10f, cyan, true))
                lifelineConsole.addView(text(
                    when {
                        lifelineSession == null -> "Start Lifeline to capture a fresh read-only baseline."
                        lifelineStatus == "comparison_complete" -> "Review the comparison and investigate any new or unresolved finding."
                        reviewedCount == checkpoints.size -> "Run a fresh local scan and compare it with the baseline."
                        else -> "Review the next recommended checkpoint, changing only one thing at a time."
                    },
                    12f,
                    Color.WHITE,
                    false,
                ))
                panel.addView(lifelineConsole)
                panel.addView(sectionAction("BROWSE DEVICE ATLAS") {
                    showSection(
                        "DEVICE ATLAS",
                        "Search integrity-checked OEM knowledge and authoritative references. Read-only guidance never grants build or flash authority.",
                    )
                })
                panel.addView(sectionAction("VIEW DEVICE ATLAS SAFETY CONTEXT") {
                    detailView.text = "DEVICE ATLAS • OFFLINE OEM CONTEXT\n${CompanionDeviceAtlas.catalogStatus()}\n\n${CompanionDeviceAtlas.resolveDetailed(Build.MANUFACTURER, Build.MODEL, Build.DEVICE).reportText()}"
                    logActivity("Device Atlas OEM context reviewed")
                })
                panel.addView(sectionAction("RUN COMPLETE SAFE DIAGNOSTIC") {
                    val report = buildRepairReport()
                    latestRepairReport = report
                    detailView.text = report
                    saveRepairReceipt(report)
                    logActivity("Complete safe diagnostic finished")
                })
                panel.addView(sectionAction("START LIFELINE SESSION") {
                    startCompanionRepairSession(detailView)
                })
                panel.addView(sectionAction("REVIEW GUIDED CHECKPOINTS") {
                    showCompanionRepairCheckpoints(detailView)
                })
                panel.addView(sectionAction("COMPARE WITH FRESH LOCAL SCAN") {
                    verifyCompanionRepairSession(detailView)
                })
                panel.addView(sectionAction("OPEN NETWORK SETTINGS") {
                    startActivity(Intent(Settings.ACTION_WIRELESS_SETTINGS))
                })
                panel.addView(sectionAction("OPEN BATTERY SETTINGS") {
                    startActivity(Intent(Settings.ACTION_BATTERY_SAVER_SETTINGS))
                })
                panel.addView(sectionAction("COPY DIAGNOSTIC REPORT") {
                    val report = latestRepairReport ?: buildRepairReport().also {
                        latestRepairReport = it
                        saveRepairReceipt(it)
                    }
                    val clipboard = getSystemService(CLIPBOARD_SERVICE) as ClipboardManager
                    clipboard.setPrimaryClip(ClipData.newPlainText("ROMVERSE diagnostic report", report))
                    detailView.text = "$report\n\nREPORT COPIED — ready to share with desktop Guardian or trusted support."
                    logActivity("Safe diagnostic report copied")
                })
            }
            "DEVICE ATLAS" -> {
                val current = CompanionDeviceAtlas.resolveDetailed(
                    Build.MANUFACTURER,
                    Build.MODEL,
                    Build.DEVICE,
                )
                val currentCard = card()
                currentCard.addView(text("CONNECTED DEVICE CONTEXT", 12f, cyan, true))
                currentCard.addView(text(current.pack.displayName, 18f, Color.WHITE, true))
                currentCard.addView(text(current.reason, 13f, muted, false))
                currentCard.addView(text(
                    "${current.pack.sources.size} authoritative reference(s)  •  execution authority: NONE",
                    11f,
                    if (current.ambiguous) "#FFB454".toColorInt() else "#72FFB2".toColorInt(),
                    true,
                ))
                panel.addView(currentCard)
                val query = EditText(this).apply {
                    hint = "Search OEM, family, model, codename, or source…"
                    setTextColor(Color.WHITE)
                    setHintTextColor(muted)
                    setSingleLine(true)
                    filters = arrayOf(InputFilter.LengthFilter(120))
                    setPadding(dp(12), dp(10), dp(12), dp(10))
                    background = outlinedPanel()
                    layoutParams = LinearLayout.LayoutParams(-1, dp(52)).apply {
                        topMargin = dp(14)
                    }
                }
                val results = LinearLayout(this).apply {
                    orientation = LinearLayout.VERTICAL
                    layoutParams = LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(12) }
                }
                fun renderAtlas() {
                    results.removeAllViews()
                    val packs = CompanionDeviceAtlas.search(query.text.toString())
                    detailView.text = if (packs.isEmpty()) {
                        "NO ATLAS MATCH\n\nNo integrity-checked Pack matched this search. Generic Android guidance remains available; no compatibility is inferred."
                    } else {
                        "DEVICE ATLAS RESULTS  •  ${packs.size}\n\nSelect a Pack to inspect its evidence boundary and authoritative references."
                    }
                    if (packs.isEmpty()) {
                        val empty = card()
                        empty.addView(text("NO MATCHING DEVICE PACK", 16f, violet, true))
                        empty.addView(text(
                            "Try an OEM such as Google, Samsung, Sony, Xiaomi, OnePlus, Motorola, or a published codename.",
                            13f,
                            muted,
                            false,
                        ))
                        results.addView(empty)
                    }
                    packs.forEach { pack ->
                        val packCard = card()
                        packCard.addView(text(pack.displayName, 17f, Color.WHITE, true))
                        packCard.addView(text(
                            "${pack.packId} v${pack.version}  •  priority ${pack.priority}",
                            11f,
                            cyan,
                            true,
                        ))
                        packCard.addView(text(
                            "${pack.sources.size} authoritative reference(s)  •  ${pack.manufacturers.sorted().joinToString()}",
                            12f,
                            muted,
                            false,
                        ))
                        packCard.addView(sectionAction("REVIEW PACK EVIDENCE") {
                            detailView.text = "DEVICE ATLAS • READ-ONLY PACK\n\n${pack.reportText()}"
                            logActivity("Device Atlas Pack reviewed")
                        })
                        results.addView(packCard)
                        results.addView(space(dp(8)))
                    }
                }
                panel.addView(query)
                panel.addView(sectionAction("SEARCH DEVICE ATLAS") { renderAtlas() })
                panel.addView(results)
                renderAtlas()
            }
            "APP LAUNCHPAD" -> {
                apkDetailView = detailView
                detailView.text = apkStatusText(
                    if (stagedApkUri == null) "Choose an APK to begin a protected local inspection."
                    else "A staged APK is ready for review."
                )
                panel.addView(sectionAction("CHOOSE APK FILE") {
                    apkPicker.launch(
                        arrayOf(
                            "application/vnd.android.package-archive",
                            "application/octet-stream"
                        )
                    )
                })
                panel.addView(sectionAction("REVIEW & OPEN INSTALLER") {
                    openStagedApkInstaller(detailView)
                })
            }
            "ROMVERSE MEMBERS" -> {
                memberDetailView = detailView
                fun renderMemberState() {
                    val session = memberSession
                    val authorization = memberAuthorization
                    detailView.text = when {
                        session != null -> buildString {
                            appendLine("SIGNED IN  •  ${session.profile.displayName}")
                            if (session.profile.email.isNotBlank()) appendLine(session.profile.email)
                            appendLine()
                            appendLine("${session.profile.plan}  •  ${session.profile.status.replace('_', ' ').uppercase()}")
                            if (session.profile.trialEndsAt.isNotBlank()) appendLine("Trial ends ${session.profile.trialEndsAt}")
                            if (session.profile.renewsAt.isNotBlank()) appendLine("Renews ${session.profile.renewsAt}")
                            append("Membership is reported by the configured HTTPS identity service; Companion never invents an entitlement.")
                        }
                        authorization != null ->
                            "FINISH SIGN-IN IN YOUR BROWSER\n\nCode: ${authorization.userCode}\n\nCompanion is waiting for the identity provider. No password is entered here and the code expires automatically."
                        memberConfigOrNull() != null ->
                            "READY FOR SECURE SIGN-IN\n\nCompanion uses OAuth device authorization in your browser. Access tokens remain only in memory and are discarded when the app process ends."
                        else ->
                            "MEMBERS SERVICE NOT CONFIGURED\n\nOpen ROMVERSE Settings and enter the official HTTPS issuer and public client ID supplied by RadForge Labs. Companion will not simulate an account, trial, or subscription."
                    }
                }
                renderMemberState()
                panel.addView(sectionAction("SIGN IN WITH ROMVERSE") {
                    when {
                        memberSession != null -> renderMemberState()
                        memberAuthorization != null -> {
                            val authorization = memberAuthorization!!
                            startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(
                                authorization.verificationUriComplete.ifBlank { authorization.verificationUri }
                            )))
                        }
                        else -> beginMemberSignIn()
                    }
                })
                panel.addView(sectionAction("COPY VERIFICATION CODE") {
                    val code = memberAuthorization?.userCode
                    if (code == null) {
                        detailView.text = "NO ACTIVE CODE\n\nStart a secure sign-in request first."
                    } else {
                        (getSystemService(CLIPBOARD_SERVICE) as ClipboardManager)
                            .setPrimaryClip(ClipData.newPlainText("ROMVERSE verification code", code))
                        detailView.text = "VERIFICATION CODE COPIED\n\nPaste it only into the trusted browser page."
                    }
                })
                panel.addView(sectionAction("SIGN OUT & DISCARD SESSION") {
                    memberHandler.removeCallbacksAndMessages(null)
                    memberAuthorization = null
                    memberSession = null
                    memberDiscovery = null
                    refreshGreeting()
                    renderMemberState()
                    logActivity("ROMVERSE Members session discarded")
                })
                val privacy = card()
                privacy.addView(text("MEMBERS PRIVACY", 12f, cyan, true))
                privacy.addView(text(
                    "• Password entry happens only in the trusted browser.\n" +
                        "• Tokens are session-only and never written to SharedPreferences.\n" +
                        "• Local settings cannot create or bypass membership.\n" +
                        "• Signing out immediately removes the in-memory session.",
                    13f,
                    muted,
                    false,
                ))
                panel.addView(privacy)
            }
            "ROMVERSE SETTINGS" -> {
                detailView.text = "Preferences are private to Companion. Security boundaries remain locked: no background root, flash, wipe, unlock, or bootloader relock is ever enabled here."
                val currentMode = experienceMode()
                val guidedMode = RadioButton(this).apply {
                    id = View.generateViewId()
                    text = "Guided\nArcana"
                    setTextColor(Color.WHITE)
                    textSize = 13f
                    gravity = Gravity.CENTER_VERTICAL
                    buttonTintList = ColorStateList.valueOf(cyan)
                    setPadding(dp(8), dp(8), dp(8), dp(8))
                }
                val expertMode = RadioButton(this).apply {
                    id = View.generateViewId()
                    text = "Expert\nArchitect"
                    setTextColor(Color.WHITE)
                    textSize = 13f
                    gravity = Gravity.CENTER_VERTICAL
                    buttonTintList = ColorStateList.valueOf(violet)
                    setPadding(dp(8), dp(8), dp(8), dp(8))
                }
                val modeGroup = RadioGroup(this).apply {
                    orientation = RadioGroup.HORIZONTAL
                    gravity = Gravity.CENTER
                    background = outlinedPanel()
                    addView(guidedMode, RadioGroup.LayoutParams(0, dp(64), 1f))
                    addView(expertMode, RadioGroup.LayoutParams(0, dp(64), 1f))
                    check(
                        if (currentMode == CompanionExperienceMode.EXPERT) {
                            expertMode.id
                        } else {
                            guidedMode.id
                        },
                    )
                }
                val modeExplanation = text("", 12f, muted, false)
                fun refreshModeExplanation() {
                    modeExplanation.text = if (modeGroup.checkedRadioButtonId == expertMode.id) {
                        "Expert Mode opens the full technical evidence by default. Guardian, approvals, and the permanent bootloader-relock prohibition remain unchanged."
                    } else {
                        "Guided Mode uses ROMVERSE Arcana and progressive disclosure: the essential answer first, with technical evidence available when requested."
                    }
                }
                modeGroup.setOnCheckedChangeListener { _, _ -> refreshModeExplanation() }
                refreshModeExplanation()
                val experience = card()
                experience.addView(text("ROMVERSE EXPERIENCE", 12f, violet, true))
                experience.addView(modeGroup)
                experience.addView(modeExplanation)
                panel.addView(experience)
                fun preference(label: String, key: String, default: Boolean): CheckBox =
                    CheckBox(this).apply {
                        text = label
                        setTextColor(Color.WHITE)
                        textSize = 14f
                        isChecked = userSettingsPrefs.getBoolean(key, default)
                        setPadding(0, dp(9), 0, dp(9))
                    }
                val online = preference(
                    "Allow Companion to contact configured HTTPS services",
                    "online_intelligence_enabled",
                    true,
                )
                val reducedMotion = preference(
                    "Reduce decorative motion and rare space events",
                    "reduced_motion",
                    false,
                )
                val oledMode = CheckBox(this).apply {
                    text = "Use true-black OLED surfaces while keeping ROMVERSE accent lighting"
                    setTextColor(Color.WHITE)
                    textSize = 14f
                    isChecked = displayMode() == CompanionDisplayMode.OLED
                    setPadding(0, dp(9), 0, dp(9))
                }
                val privacyCurtain = preference(
                    "Hide private content when Companion opens or returns to the foreground",
                    "privacy_curtain_enabled",
                    false,
                )
                panel.addView(online)
                panel.addView(reducedMotion)
                panel.addView(oledMode)
                panel.addView(privacyCurtain)
                val policy = card()
                policy.addView(text("REAL SETTINGS BOUNDARY", 12f, violet, true))
                policy.addView(text(
                    "The online switch controls Companion's configured public HTTPS services. " +
                        "Encrypted local ROMVERSE Link remains available. Community research, " +
                        "Desktop tool acquisition, and Desktop notifications are controlled on the PC; " +
                        "Companion does not display switches it cannot enforce. OLED mode replaces " +
                        "primary surfaces with true black without changing evidence or behavior. " +
                        "Privacy Curtain hides " +
                        "device, project, and session details and blocks Android screenshots or screen " +
                        "recording while enabled. It does not disconnect Link or change Guardian state.",
                    12f,
                    muted,
                    false,
                ))
                panel.addView(policy)
                val preferredName = EditText(this).apply {
                    hint = "Name Companion should use"
                    setText(
                        userSettingsPrefs.getString(
                            "preferred_display_name",
                            CompanionPersonalization.DEFAULT_DISPLAY_NAME,
                        ),
                    )
                    setTextColor(Color.WHITE)
                    setHintTextColor(muted)
                    setSingleLine(true)
                    filters = arrayOf(
                        InputFilter.LengthFilter(CompanionPersonalization.MAX_DISPLAY_NAME_LENGTH),
                    )
                    background = outlinedPanel()
                    setPadding(dp(12), dp(10), dp(12), dp(10))
                }
                panel.addView(text("COMPANION PROFILE", 12f, cyan, true).apply {
                    setPadding(0, dp(18), 0, dp(8))
                })
                panel.addView(preferredName, LinearLayout.LayoutParams(-1, dp(52)))
                val issuer = EditText(this).apply {
                    hint = "Official Members HTTPS issuer"
                    setText(userSettingsPrefs.getString("members_issuer", ""))
                    setTextColor(Color.WHITE)
                    setHintTextColor(muted)
                    setSingleLine(true)
                    filters = arrayOf(InputFilter.LengthFilter(2048))
                    background = outlinedPanel()
                    setPadding(dp(12), dp(10), dp(12), dp(10))
                }
                val clientId = EditText(this).apply {
                    hint = "Public OAuth device client ID"
                    setText(userSettingsPrefs.getString("members_client_id", ""))
                    setTextColor(Color.WHITE)
                    setHintTextColor(muted)
                    setSingleLine(true)
                    filters = arrayOf(InputFilter.LengthFilter(200))
                    background = outlinedPanel()
                    setPadding(dp(12), dp(10), dp(12), dp(10))
                }
                panel.addView(text("MEMBERS SERVICE", 12f, cyan, true).apply {
                    setPadding(0, dp(18), 0, dp(8))
                })
                panel.addView(issuer, LinearLayout.LayoutParams(-1, dp(52)))
                panel.addView(clientId, LinearLayout.LayoutParams(-1, dp(52)).apply {
                    topMargin = dp(8)
                })
                var activeMembersIssuer = issuer.text.toString().trim()
                var activeMembersClientId = clientId.text.toString().trim()
                panel.addView(sectionAction("SAVE SETTINGS") {
                    val normalizedName = runCatching {
                        CompanionPersonalization.validateDisplayName(
                            preferredName.text.toString(),
                        )
                    }.getOrElse {
                        preferredName.error = it.message
                        detailView.text = "SETTINGS NEED ATTENTION\n\n${it.message}"
                        return@sectionAction
                    }
                    val issuerValue = issuer.text.toString().trim()
                    val clientValue = clientId.text.toString().trim()
                    val configuration = if (issuerValue.isBlank() && clientValue.isBlank()) {
                        null
                    } else {
                        runCatching {
                            CompanionMembersConfig(issuerValue, clientValue).validated()
                        }.getOrElse {
                            detailView.text = "SETTINGS NEED ATTENTION\n\n${it.message}"
                            return@sectionAction
                        }
                    }
                    val savedIssuer = configuration?.issuer.orEmpty()
                    val savedClientId = configuration?.clientId.orEmpty()
                    val savedMode = if (modeGroup.checkedRadioButtonId == expertMode.id) {
                        CompanionExperienceMode.EXPERT
                    } else {
                        CompanionExperienceMode.GUIDED
                    }
                    val membersConfigurationChanged =
                        savedIssuer != activeMembersIssuer || savedClientId != activeMembersClientId
                    val displayModeChanged =
                        oledMode.isChecked != (displayMode() == CompanionDisplayMode.OLED)
                    userSettingsPrefs.edit()
                        .putBoolean("online_intelligence_enabled", online.isChecked)
                        .putBoolean("reduced_motion", reducedMotion.isChecked)
                        .putString(
                            "display_mode",
                            if (oledMode.isChecked) {
                                CompanionDisplayMode.OLED.persistedValue
                            } else {
                                CompanionDisplayMode.COSMIC.persistedValue
                            },
                        )
                        .putBoolean("privacy_curtain_enabled", privacyCurtain.isChecked)
                        .putString("experience_mode", savedMode.persistedValue)
                        .putString("preferred_display_name", normalizedName)
                        .putString("members_issuer", savedIssuer)
                        .putString("members_client_id", savedClientId)
                        .apply()
                    privacyCurtainState = CompanionPrivacyCurtainState(
                        enabled = privacyCurtain.isChecked,
                    )
                    activeMembersIssuer = savedIssuer
                    activeMembersClientId = savedClientId
                    starfieldLayers.forEach { it.setMotionEnabled(!reducedMotion.isChecked) }
                    val memberSessionDiscarded = membersConfigurationChanged || !online.isChecked
                    if (memberSessionDiscarded) {
                        memberHandler.removeCallbacksAndMessages(null)
                        memberAuthorization = null
                        memberSession = null
                        memberDiscovery = null
                    }
                    refreshGreeting()
                    detailView.text = "SETTINGS SAVED  •  ${savedMode.name}\n\nExperience mode, Companion profile, public HTTPS policy, decorative motion, OLED display mode, Privacy Curtain, and Members configuration are active. " +
                        if (!online.isChecked) {
                            "Public HTTPS services were disabled, so pending authorization and the in-memory Members session were safely discarded. Local ROMVERSE Link remains available. Guardian invariants were not changed."
                        } else if (membersConfigurationChanged) {
                            "The Members endpoint changed, so pending authorization and the in-memory sign-in were safely discarded. Guardian invariants were not changed."
                        } else {
                            "The Members endpoint did not change, so any valid in-memory sign-in was preserved. Guardian invariants were not changed."
                        }
                    logActivity("Companion settings updated")
                    applyPrivacyCurtain()
                    if (displayModeChanged) {
                        window.decorView.post { recreate() }
                    }
                })
            }
            "ROMVERSE GALAXY" -> {
                galaxyDetailView = detailView
                detailView.text = "OFFLINE LOCAL MODE\n\nTopics, replies, and votes stay on this phone. No account, network publishing, or synchronization is implied."
                val searchInput = EditText(this).apply {
                    hint = "Search local topics and replies…"
                    setTextColor(Color.WHITE)
                    setHintTextColor(muted)
                    setSingleLine(true)
                    setPadding(dp(12), dp(10), dp(12), dp(10))
                    background = outlinedPanel()
                    layoutParams = LinearLayout.LayoutParams(-1, dp(52)).apply { topMargin = dp(14) }
                }
                val titleInput = EditText(this).apply {
                    hint = "New topic title"
                    filters = arrayOf(InputFilter.LengthFilter(120))
                    setTextColor(Color.WHITE)
                    setHintTextColor(muted)
                    setSingleLine(true)
                    setPadding(dp(12), dp(10), dp(12), dp(10))
                    background = outlinedPanel()
                    layoutParams = LinearLayout.LayoutParams(-1, dp(52)).apply { topMargin = dp(12) }
                }
                val bodyInput = EditText(this).apply {
                    hint = "Share context, evidence, steps tried, or your ROM idea…"
                    filters = arrayOf(InputFilter.LengthFilter(10_000))
                    setTextColor(Color.WHITE)
                    setHintTextColor(muted)
                    gravity = Gravity.TOP
                    minLines = 3
                    setPadding(dp(12), dp(10), dp(12), dp(10))
                    background = outlinedPanel()
                    layoutParams = LinearLayout.LayoutParams(-1, dp(100)).apply { topMargin = dp(8) }
                }
                val restoredDraft = GalaxyRules.boundedDraft(
                    draftPrefs.getString(GALAXY_DRAFT_TITLE, "").orEmpty(),
                    draftPrefs.getString(GALAXY_DRAFT_BODY, "").orEmpty(),
                )
                titleInput.setText(restoredDraft.title)
                bodyInput.setText(restoredDraft.body)
                val draftStatus = text(
                    if (restoredDraft.title.isNotBlank() || restoredDraft.body.isNotBlank()) {
                        "Private draft restored from this phone"
                    } else {
                        "Your unfinished topic is saved privately on this phone"
                    },
                    11f,
                    muted,
                    false,
                )
                var suppressDraftSave = false
                fun saveTopicDraft() {
                    if (suppressDraftSave) return
                    val draft = GalaxyRules.boundedDraft(
                        titleInput.text.toString(),
                        bodyInput.text.toString(),
                    )
                    draftPrefs.edit()
                        .putString(GALAXY_DRAFT_TITLE, draft.title)
                        .putString(GALAXY_DRAFT_BODY, draft.body)
                        .apply()
                    draftStatus.text = if (draft.title.isBlank() && draft.body.isBlank()) {
                        "No local topic draft"
                    } else {
                        "Draft saved privately on this phone"
                    }
                }
                titleInput.doAfterTextChanged { saveTopicDraft() }
                bodyInput.doAfterTextChanged { saveTopicDraft() }
                val topicList = LinearLayout(this).apply {
                    orientation = LinearLayout.VERTICAL
                    layoutParams = LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(14) }
                }
                var topicOrder = GalaxySort.NEWEST
                fun refreshTopics(query: String = searchInput.text.toString()) {
                    renderGalaxyTopics(topicList, detailView, query, topicOrder) { refreshTopics() }
                }
                panel.addView(searchInput)
                panel.addView(sectionAction("SEARCH LOCAL COMMUNITY") { refreshTopics() })
                panel.addView(text("ORDER CONVERSATIONS", 11f, cyan, true).apply {
                    setPadding(0, dp(12), 0, dp(2))
                })
                val orderButton = sectionAction("ORDER • ${topicOrder.displayName.uppercase()}") {}
                orderButton.setOnClickListener {
                    val choices = GalaxySort.entries.map { it.displayName }.toTypedArray()
                    AlertDialog.Builder(this)
                        .setTitle("Order local conversations")
                        .setSingleChoiceItems(choices, topicOrder.ordinal) { dialog, index ->
                            topicOrder = GalaxySort.entries[index]
                            orderButton.text = "ORDER • ${topicOrder.displayName.uppercase()}"
                            refreshTopics()
                            detailView.text =
                                "LOCAL COMMUNITY ORDERED BY ${topicOrder.displayName.uppercase()}\n\n" +
                                "Search and ordering remain private on this phone."
                            dialog.dismiss()
                        }
                        .setNegativeButton("Cancel", null)
                        .show()
                }
                panel.addView(orderButton)
                val archiveRow = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
                archiveRow.addView(sectionAction("EXPORT VERIFIED ARCHIVE") {
                    val suffix = DateFormat.getDateInstance(DateFormat.SHORT)
                        .format(Date())
                        .replace(Regex("[^0-9A-Za-z]+"), "-")
                        .trim('-')
                    galaxyArchiveExporter.launch("romverse-galaxy-${suffix.ifBlank { "backup" }}.json")
                }, LinearLayout.LayoutParams(0, -2, 1f))
                archiveRow.addView(sectionAction("IMPORT & VERIFY ARCHIVE") {
                    galaxyArchiveImporter.launch(arrayOf("application/json", "text/plain"))
                }, LinearLayout.LayoutParams(0, -2, 1f))
                panel.addView(archiveRow)
                panel.addView(text("START A LOCAL TOPIC", 12f, cyan, true).apply {
                    setPadding(0, dp(16), 0, dp(2))
                })
                panel.addView(titleInput)
                panel.addView(bodyInput)
                panel.addView(draftStatus)
                panel.addView(sectionAction("SAVE LOCAL TOPIC") {
                    val titleValue = titleInput.text.toString().trim()
                    val bodyValue = bodyInput.text.toString().trim()
                    val validation = runCatching { GalaxyRules.validateTopicText(titleValue, bodyValue) }
                    if (validation.isFailure) {
                        detailView.text = "TOPIC NEEDS ATTENTION\n\n${validation.exceptionOrNull()?.message}"
                    } else {
                        runCatching {
                            val topics = loadGalaxyTopics()
                            topics.add(0, JSONObject()
                                .put("id", UUID.randomUUID().toString())
                                .put("title", titleValue)
                                .put("body", bodyValue)
                                .put("created_at", System.currentTimeMillis())
                                .put("vote", 0)
                                .put("comments", JSONArray()))
                            saveGalaxyTopics(topics)
                        }.onSuccess {
                            suppressDraftSave = true
                            titleInput.text.clear()
                            bodyInput.text.clear()
                            suppressDraftSave = false
                            draftPrefs.edit()
                                .remove(GALAXY_DRAFT_TITLE)
                                .remove(GALAXY_DRAFT_BODY)
                                .apply()
                            draftStatus.text = "No local topic draft"
                            detailView.text = "LOCAL TOPIC SAVED\n\nNothing was published or synchronized."
                            logActivity("Galaxy local topic saved")
                            refreshTopics("")
                        }.onFailure {
                            detailView.text = "COMMUNITY DATA NEEDS ATTENTION\n\n${it.message ?: "Local data could not be read safely."}"
                        }
                    }
                })
                panel.addView(text("LOCAL CONVERSATIONS", 12f, violet, true).apply {
                    setPadding(0, dp(18), 0, dp(2))
                })
                panel.addView(topicList)
                refreshTopics("")
            }
            "ABOUT ROMVERSE COMPANION" -> {
                detailView.visibility = View.GONE
                var lastMarkTap = 0L
                var originReplay: Button? = null
                val mark = ImageView(this).apply {
                    setImageResource(R.drawable.romverse_app_icon)
                    scaleType = ImageView.ScaleType.CENTER_INSIDE
                    contentDescription = "ROMVERSE mark"
                    isClickable = true
                    isFocusable = true
                    setOnClickListener {
                        val now = SystemClock.elapsedRealtime()
                        if (now - lastMarkTap in 40..420) {
                            lastMarkTap = 0L
                            val firstDiscovery = !aboutPrefs.getBoolean("origin_discovered", false)
                            val recorded = if (firstDiscovery) {
                                aboutPrefs.edit()
                                    .putBoolean("origin_discovered", true)
                                    .putBoolean("beyond_the_verse_discovered", true)
                                    .commit()
                            } else true
                            if (recorded) originReplay?.visibility = View.VISIBLE
                            performHapticFeedback(HapticFeedbackConstants.CONFIRM)
                            showSupporterTribute(firstDiscovery && recorded)
                        } else {
                            lastMarkTap = now
                        }
                    }
                    layoutParams = LinearLayout.LayoutParams(
                        dp(CompanionLayoutSpec.ABOUT_MARK_SIZE_DP),
                        dp(CompanionLayoutSpec.ABOUT_MARK_SIZE_DP),
                    ).apply {
                        gravity = Gravity.CENTER_HORIZONTAL
                        topMargin = dp(12)
                        bottomMargin = dp(12)
                    }
                }
                panel.addView(mark)
                panel.addView(text("ROMVERSE COMPANION", 21f, Color.WHITE, true).apply {
                    gravity = Gravity.CENTER
                })
                panel.addView(text("BUILD  •  OPTIMIZE  •  PERFECT", 11f, cyan, true).apply {
                    gravity = Gravity.CENTER
                })
                panel.addView(space(dp(12)))
                panel.addView(text(
                    "Your Android sidekick for safe device insight, guided care, and a direct connection to ROMVERSE Desktop.",
                    14f,
                    muted,
                    false,
                ).apply {
                    gravity = Gravity.CENTER
                    textAlignment = View.TEXT_ALIGNMENT_CENTER
                    setLineSpacing(0f, 1.08f)
                })
                panel.addView(space(dp(18)))
                fun addAboutStory(title: String, body: String, accent: Int) {
                    val story = card()
                    story.addView(text(title, 12f, accent, true).apply {
                        gravity = Gravity.CENTER
                        letterSpacing = 0.08f
                    })
                    story.addView(text(body, 13f, Color.WHITE, false).apply {
                        gravity = Gravity.CENTER
                        textAlignment = View.TEXT_ALIGNMENT_CENTER
                        setLineSpacing(0f, 1.08f)
                        setPadding(0, dp(8), 0, 0)
                    })
                    panel.addView(story)
                }
                addAboutStory(
                    "WHAT IS ROMVERSE?",
                    "An intelligent Android ROM development, diagnostics, optimization, and recovery ecosystem. Desktop, Companion, Guardian, and verified device knowledge work together without hiding uncertainty.",
                    cyan,
                )
                addAboutStory(
                    "THE ROMVERSE PROMISE",
                    "Real progress—never simulated success.\n\nEvidence before assumptions—unknown stays unconfirmed.\n\nYour device, your decision. Guardian protects high-consequence workflows.\n\nPrivacy by design.",
                    violet,
                )
                val identity = card()
                identity.addView(text("A RADFORGE LABS PROJECT", 12f, violet, true).apply {
                    gravity = Gravity.CENTER
                })
                identity.addView(text("SteveTheRad  •  Founding Creator", 14f, Color.WHITE, true).apply {
                    gravity = Gravity.CENTER
                })
                identity.addView(text("Founder & Creator of ROMVERSE", 12f, muted, false).apply {
                    gravity = Gravity.CENTER
                })
                identity.addView(text(
                    "Companion ${BuildConfig.VERSION_NAME}  •  Internal Alpha  •  Android ${Build.VERSION.RELEASE}",
                    12f,
                    muted,
                    false,
                ).apply {
                    gravity = Gravity.CENTER
                })
                panel.addView(identity)
                val status = card()
                status.addView(text("●  COMPANION RUNNING", 12f, "#72FFB2".toColorInt(), true))
                status.addView(text(
                    if (hasSecureWirelessSession()) {
                        "ROMVERSE Link is authenticated. Runtime metadata and local Guardian evidence are available."
                    } else {
                        "Local Companion runtime is active. ROMVERSE Link is currently unconfirmed; no Desktop service state is being simulated."
                    },
                    12f,
                    muted,
                    false,
                ))
                panel.addView(status)
                addAboutStory(
                    "THE ROMVERSE ECOSYSTEM",
                    "Desktop  •  Companion  •  Guardian\nOnline Intelligence  •  Community\n\nOne connected experience for building, understanding, protecting, and perfecting Android devices.",
                    "#72FFB2".toColorInt(),
                )
                val websitesCard = card()
                websitesCard.addView(text("OFFICIAL WEBSITES", 12f, cyan, true).apply {
                    gravity = Gravity.CENTER
                    textAlignment = View.TEXT_ALIGNMENT_CENTER
                    letterSpacing = 0.08f
                })
                websitesCard.addView(text(
                    "Explore ROMVERSE and the RadForge Labs studio behind the project.",
                    12f,
                    muted,
                    false,
                ).apply {
                    gravity = Gravity.CENTER
                    textAlignment = View.TEXT_ALIGNMENT_CENTER
                    setPadding(0, dp(7), 0, dp(2))
                })
                websitesCard.addView(socialAction(
                    "ROMVERSE",
                    "romverse.app  •  Product, roadmap, and updates",
                    R.drawable.ic_romverse_web,
                ) {
                    openOfficialPage(ROMVERSE_WEBSITE_URL, "romverse.app", "website")
                })
                websitesCard.addView(socialAction(
                    "RadForge Labs",
                    "radforgelabs.com  •  The studio behind ROMVERSE",
                    R.drawable.ic_radforge_labs,
                ) {
                    openOfficialPage(RADFORGE_LABS_URL, "radforgelabs.com", "RadForge Labs website")
                })
                panel.addView(websitesCard)
                val socialCard = card()
                socialCard.addView(text("CONNECT WITH ROMVERSE", 12f, violet, true).apply {
                    gravity = Gravity.CENTER
                })
                socialCard.addView(socialAction(
                    "Facebook",
                    "Follow ROMVERSEOfficial",
                    R.drawable.ic_facebook_f,
                ) {
                    openOfficialPage(FACEBOOK_URL, "www.facebook.com", "Facebook")
                })
                socialCard.addView(socialAction(
                    "Reddit",
                    "Follow u/ROMVERSE",
                    R.drawable.ic_reddit,
                ) {
                    openOfficialPage(REDDIT_URL, "www.reddit.com", "Reddit")
                })
                panel.addView(socialCard)
                originReplay = sectionAction("🌌  EXPERIENCE THE ORIGIN AGAIN") {
                    showSupporterTribute(firstDiscovery = false)
                }.apply {
                    contentDescription = "Replay ROMVERSE The Origin"
                    visibility = if (aboutPrefs.getBoolean("origin_discovered", false)) {
                        View.VISIBLE
                    } else View.GONE
                }
                panel.addView(originReplay)
                addAboutStory(
                    "TRUST & TRANSPARENCY",
                    "Guardian never treats unknown evidence as healthy, never simulates success, and never authorizes bootloader relocking. Membership, online services, and community activity appear only when genuinely available.",
                    cyan,
                )
                addAboutStory(
                    "THANK YOU FOR BEING PART OF ROMVERSE",
                    "Whether you're building your first ROM, developing your hundredth, testing a new device, helping another member or simply exploring what Android can become—you're part of the journey.\n\n— SteveTheRad\n\n27.08.2026",
                    "#D9B6FF".toColorInt(),
                )
                panel.addView(text(
                    "One membership. Every ROMVERSE experience included.\nTerms  •  Privacy  •  Open source  •  Third-party notices  •  Changelog",
                    11f,
                    muted,
                    false,
                ).apply {
                    gravity = Gravity.CENTER
                    textAlignment = View.TEXT_ALIGNMENT_CENTER
                    setPadding(0, dp(12), 0, dp(4))
                })
                val thirdPartyNotices = resources.openRawResource(R.raw.third_party_notices)
                    .bufferedReader(Charsets.UTF_8).use { it.readText() }
                panel.addView(text(thirdPartyNotices, 11f, muted, false).apply {
                    setPadding(0, dp(12), 0, dp(4))
                })
            }
        }
        panel.addView(space(dp(18)))
        overlay.addView(shell, FrameLayout.LayoutParams(-1, -1))
        host.addView(overlay, FrameLayout.LayoutParams(-1, -1))
        applyPrivacyCurtain()
    }

    private fun applyPrivacyCurtain() {
        if (privacyCurtainState.blocksScreenCapture) {
            window.addFlags(WindowManager.LayoutParams.FLAG_SECURE)
        } else {
            window.clearFlags(WindowManager.LayoutParams.FLAG_SECURE)
        }

        val host = sectionHost ?: return
        if (!privacyCurtainState.obscuresContent) {
            homeScroll?.importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_AUTO
            sectionPage?.importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_AUTO
            privacyCurtainPage?.let { page -> (page.parent as? FrameLayout)?.removeView(page) }
            privacyCurtainPage = null
            return
        }

        homeScroll?.importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO_HIDE_DESCENDANTS
        sectionPage?.importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO_HIDE_DESCENDANTS

        privacyCurtainPage?.let { page ->
            if (page.parent === host) {
                page.bringToFront()
                return
            }
            (page.parent as? FrameLayout)?.removeView(page)
        }

        val curtain = FrameLayout(this).apply {
            contentDescription = "Privacy Curtain active"
            importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_YES
            isClickable = true
            isFocusable = true
            background = cosmicBackground()
            elevation = dp(40).toFloat()
        }
        val centre = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER_HORIZONTAL
            setPadding(dp(22), dp(24), dp(22), dp(24))
            background = glassCardBackground()
        }
        centre.addView(ImageView(this).apply {
            setImageResource(R.drawable.romverse_app_icon)
            scaleType = ImageView.ScaleType.CENTER_INSIDE
            contentDescription = null
        }, LinearLayout.LayoutParams(-1, dp(92)))
        centre.addView(text("PRIVACY CURTAIN", 13f, cyan, true).apply {
            gravity = Gravity.CENTER
            textAlignment = View.TEXT_ALIGNMENT_CENTER
            letterSpacing = 0.13f
        })
        centre.addView(text("YOUR ROMVERSE DETAILS ARE HIDDEN", 20f, Color.WHITE, true).apply {
            gravity = Gravity.CENTER
            textAlignment = View.TEXT_ALIGNMENT_CENTER
            setPadding(0, dp(8), 0, dp(8))
        })
        centre.addView(text(
            "Device, project, and session details are concealed. Android screenshots and screen " +
                "recording remain blocked while Privacy Curtain is enabled. ROMVERSE Link and " +
                "Guardian continue unchanged.",
            13f,
            muted,
            false,
        ).apply {
            gravity = Gravity.CENTER
            textAlignment = View.TEXT_ALIGNMENT_CENTER
        })
        centre.addView(sectionAction("REVEAL THIS SESSION") {
            privacyCurtainState = privacyCurtainState.revealForSession()
            applyPrivacyCurtain()
        }.apply {
            contentDescription = "Reveal private ROMVERSE content for this foreground session"
        })
        curtain.addView(centre, FrameLayout.LayoutParams(-1, -2, Gravity.CENTER).apply {
            marginStart = dp(22)
            marginEnd = dp(22)
        })
        privacyCurtainPage = curtain
        host.addView(curtain, FrameLayout.LayoutParams(-1, -1))
    }

    private fun starfieldLayer(): StarfieldView = StarfieldView(
        this,
        displayMode() == CompanionDisplayMode.OLED,
    ).also { layer ->
        layer.setMotionEnabled(
            !userSettingsPrefs.getBoolean("reduced_motion", false),
        )
        starfieldLayers.add(layer)
    }

    private fun loadGalaxyTopics(): MutableList<JSONObject> {
        val raw = draftPrefs.getString("topics_v1", null) ?: run {
            galaxyIntegrityStatus = "No local Galaxy data saved yet."
            galaxyIntegrityVerified = false
            galaxyDataExists = false
            return mutableListOf()
        }
        return decodeGalaxyArchive(raw)
    }

    private fun decodeGalaxyArchive(raw: String): MutableList<JSONObject> {
        require(raw.toByteArray(Charsets.UTF_8).size <= GalaxyRules.MAX_PERSISTED_BYTES) {
            "Local Galaxy data exceeds the safe storage boundary."
        }
        val root = JSONObject(raw)
        require(root.optString("format") == "romverse.galaxy.community") {
            "Unsupported local Galaxy data format."
        }
        require(root.optInt("schema_version", 0) == 1) { "Unsupported local Galaxy data version." }
        require(root.optString("mode") == "offline-local") {
            "Local Galaxy data has an invalid publishing boundary."
        }
        val array = root.getJSONArray("topics")
        require(array.length() <= GalaxyRules.MAX_TOPICS) { "Local Galaxy topic limit exceeded." }
        val topics = MutableList(array.length()) { index ->
            val topic = array.getJSONObject(index)
            require(topic.getString("id").isNotBlank()) { "A local topic has no identifier." }
            require(topic.getString("title").length in 1..120) { "A local topic title is invalid." }
            require(topic.getString("body").length in 1..10000) { "A local topic message is invalid." }
            require(topic.getJSONArray("comments").length() <= 1000) { "A local reply list is too large." }
            GalaxyRules.validateTopic(galaxyTopicData(topic))
            topic
        }
        val topicData = topics.map(::galaxyTopicData)
        GalaxyRules.validateTopics(topicData)
        val hasVersion = root.has("integrity_version")
        val hasDigest = root.has("community_digest")
        require(hasVersion == hasDigest) { "Local Galaxy integrity envelope is incomplete." }
        if (hasVersion) {
            require(root.optInt("integrity_version", 0) == GalaxyRules.INTEGRITY_VERSION) {
                "Unsupported local Galaxy integrity format."
            }
            require(
                GalaxyRules.verifyCommunityDigest(
                    topicData,
                    root.optString("community_digest"),
                ),
            ) { "Local Galaxy data integrity mismatch." }
            galaxyIntegrityStatus =
                "Integrity verified  •  SHA-256 ${root.getString("community_digest").take(12)}…"
            galaxyIntegrityVerified = true
        } else {
            galaxyIntegrityStatus =
                "Legacy / unverified  •  the next successful save adds integrity protection."
            galaxyIntegrityVerified = false
        }
        galaxyDataExists = true
        return topics
    }

    private fun saveGalaxyTopics(topics: List<JSONObject>) {
        require(topics.size <= GalaxyRules.MAX_TOPICS) { "Local Galaxy topic limit exceeded." }
        val root = galaxyArchiveRoot(topics)
        require(root.toString().toByteArray(Charsets.UTF_8).size <= GalaxyRules.MAX_PERSISTED_BYTES) {
            "Local Galaxy data exceeds the safe storage boundary."
        }
        draftPrefs.edit().putString("topics_v1", root.toString()).commit().also {
            require(it) { "Android could not preserve local Galaxy data." }
        }
        loadGalaxyTopics()
        require(galaxyIntegrityVerified) {
            "Android could not verify the preserved local Galaxy data."
        }
    }

    private fun galaxyArchiveRoot(topics: List<JSONObject>): JSONObject {
        val topicData = topics.map(::galaxyTopicData)
        GalaxyRules.validateTopics(topicData)
        return JSONObject()
            .put("format", "romverse.galaxy.community")
            .put("schema_version", 1)
            .put("mode", "offline-local")
            .put("integrity_version", GalaxyRules.INTEGRITY_VERSION)
            .put("community_digest", GalaxyRules.communityDigest(topicData))
            .put("exported_at", System.currentTimeMillis())
            .put("topics", JSONArray(topics))
    }

    private fun exportGalaxyArchive(uri: Uri) {
        galaxyDetailView?.text = "EXPORTING VERIFIED ARCHIVE…\n\nROMVERSE is validating every local topic and reply before writing the selected file."
        Thread {
            val result = runCatching {
                val topics = loadGalaxyTopics()
                val archive = galaxyArchiveRoot(topics).toString(2)
                require(archive.toByteArray(Charsets.UTF_8).size <= GalaxyRules.MAX_PERSISTED_BYTES) {
                    "The verified archive exceeds the safe export boundary."
                }
                contentResolver.openOutputStream(uri, "wt")?.bufferedWriter()?.use {
                    it.write(archive)
                    it.newLine()
                } ?: error("Android could not open the selected destination.")
                topics.size to GalaxyRules.communityDigest(topics.map(::galaxyTopicData))
            }
            runOnUiThread {
                result.onSuccess { (count, digest) ->
                    galaxyDetailView?.text = "VERIFIED ARCHIVE EXPORTED\n\n$count local topic(s) were written with integrity digest ${digest.take(16)}…\n\nThe archive remains local-only and contains only the Galaxy topics and replies you created."
                    logActivity("Galaxy verified archive exported")
                }.onFailure {
                    galaxyDetailView?.text = "ARCHIVE NOT EXPORTED\n\n${it.message ?: "The selected destination could not be written."}\n\nExisting Galaxy data was not changed."
                }
            }
        }.start()
    }

    private fun previewGalaxyArchiveImport(uri: Uri) {
        galaxyDetailView?.text = "VERIFYING IMPORT…\n\nROMVERSE is checking format, size, timestamps, identifiers, and the community integrity digest."
        Thread {
            val result = runCatching {
                val bytes = contentResolver.openInputStream(uri)?.use { input ->
                    val output = ByteArrayOutputStream()
                    val buffer = ByteArray(8192)
                    while (true) {
                        val count = input.read(buffer)
                        if (count < 0) break
                        require(output.size() + count <= GalaxyRules.MAX_PERSISTED_BYTES) {
                            "The selected archive exceeds the safe import boundary."
                        }
                        output.write(buffer, 0, count)
                    }
                    output.toByteArray()
                } ?: error("Android could not read the selected archive.")
                val topics = decodeGalaxyArchive(bytes.toString(Charsets.UTF_8))
                topics to GalaxyRules.communityDigest(topics.map(::galaxyTopicData))
            }
            runOnUiThread {
                result.onSuccess { (topics, digest) ->
                    val replies = topics.sumOf { it.getJSONArray("comments").length() }
                    AlertDialog.Builder(this)
                        .setTitle("Verified Galaxy archive")
                        .setMessage(
                            "${topics.size} topic(s) • $replies repl${if (replies == 1) "y" else "ies"}\n" +
                                "Integrity: ${digest.take(16)}…\n\n" +
                                "Importing replaces the current local Galaxy collection on this phone. " +
                                "Nothing is uploaded or published."
                        )
                        .setNegativeButton("Keep current data", null)
                        .setPositiveButton("Replace with verified archive") { _, _ ->
                            runCatching { saveGalaxyTopics(topics) }
                                .onSuccess {
                                    logActivity("Galaxy verified archive imported")
                                    showSection(
                                        "ROMVERSE GALAXY",
                                        "VERIFIED ARCHIVE IMPORTED\n\n${topics.size} topic(s) are available locally. Nothing was published or synchronized.",
                                    )
                                }
                                .onFailure {
                                    galaxyDetailView?.text = "ARCHIVE NOT IMPORTED\n\n${it.message}\n\nExisting Galaxy data was preserved."
                                }
                        }
                        .show()
                }.onFailure {
                    galaxyDetailView?.text = "ARCHIVE REJECTED\n\n${it.message ?: "The selected archive is invalid."}\n\nExisting Galaxy data was preserved."
                    logActivity("Galaxy archive import rejected")
                }
            }
        }.start()
    }

    private fun updateGalaxyTopic(id: String, update: (JSONObject) -> Unit) {
        val topics = loadGalaxyTopics()
        val topic = topics.firstOrNull { it.optString("id") == id }
            ?: error("Local Galaxy topic was not found.")
        update(topic)
        saveGalaxyTopics(topics)
    }

    private fun renderGalaxyTopics(
        container: LinearLayout,
        detailView: TextView,
        query: String,
        order: GalaxySort,
        rerender: () -> Unit,
    ) {
        container.removeAllViews()
        val topics = runCatching { loadGalaxyTopics() }.getOrElse {
            detailView.text = "COMMUNITY DATA NEEDS ATTENTION\n\n${it.message ?: "The local forum data is unreadable."}\n\nROMVERSE preserved the original data and will not overwrite it."
            container.addView(text("Local Community Lab data could not be loaded safely.", 14f, "#FF6685".toColorInt(), true))
            return
        }
        val integrityCard = card()
        val integrityColor = when {
            galaxyIntegrityVerified -> "#44E39A".toColorInt()
            galaxyDataExists -> "#FFB454".toColorInt()
            else -> muted
        }
        integrityCard.addView(text("LOCAL DATA INTEGRITY", 11f, cyan, true))
        integrityCard.addView(text(galaxyIntegrityStatus, 13f, integrityColor, true))
        integrityCard.addView(text("Local preview boundary locked", 11f, muted, false))
        container.addView(integrityCard)
        container.addView(space(dp(10)))
        val normalized = query.trim().lowercase()
        val filtered = topics.filter { topic ->
            if (normalized.isBlank()) true else {
                GalaxyRules.matches(galaxyTopicData(topic), normalized)
            }
        }
        val ordered = GalaxyRules.sortTopics(filtered.map(::galaxyTopicData), order)
        val byId = topics.associateBy { it.optString("id") }
        if (filtered.isEmpty()) {
            val empty = card()
            empty.addView(text(if (normalized.isBlank()) "NO LOCAL TOPICS YET" else "NO MATCHING TOPICS", 16f, violet, true))
            empty.addView(text("Start with a ROM idea, a verified troubleshooting discovery, or a question for the future community.", 13f, muted, false))
            container.addView(empty)
            return
        }
        container.addView(text(
            "${ordered.size} conversation${if (ordered.size == 1) "" else "s"}  •  ${order.displayName}",
            11f,
            cyan,
            true,
        ))
        container.addView(space(dp(8)))
        ordered.forEach { topicData ->
            val topic = byId[topicData.id] ?: return@forEach
            val topicId = topic.optString("id")
            val comments = topic.optJSONArray("comments") ?: JSONArray()
            val topicCard = card()
            topicCard.addView(text(topic.optString("title"), 18f, Color.WHITE, true))
            topicCard.addView(text(
                "YOU  •  ${galaxyTime(topic.optLong("created_at"))}  •  ${comments.length()} replies  •  score ${topic.optInt("vote", 0)}",
                11f,
                cyan,
                true,
            ))
            topicCard.addView(text(topic.optString("body"), 14f, muted, false).apply {
                setPadding(0, dp(8), 0, dp(8))
            })
            if (comments.length() > 0) {
                topicCard.addView(text("LOCAL REPLIES", 11f, violet, true))
                for (index in 0 until comments.length()) {
                    val reply = comments.optJSONObject(index) ?: continue
                    topicCard.addView(text(
                        "YOU  •  ${galaxyTime(reply.optLong("created_at"))}\n${reply.optString("body")}",
                        13f,
                        Color.WHITE,
                        false,
                    ).apply {
                        setPadding(dp(10), dp(8), dp(10), dp(8))
                        background = outlinedPanel()
                    })
                }
            }
            val voteRow = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
            val currentVote = topic.optInt("vote", 0)
            voteRow.addView(sectionAction(if (currentVote == 1) "▲ HELPFUL" else "△ HELPFUL") {
                runCatching {
                    updateGalaxyTopic(topicId) {
                        it.put("vote", GalaxyRules.toggleVote(it.optInt("vote"), 1))
                    }
                }.onSuccess { rerender() }
                    .onFailure { detailView.text = "VOTE NOT SAVED\n\n${it.message}" }
            }, LinearLayout.LayoutParams(0, -2, 1f))
            voteRow.addView(sectionAction(if (currentVote == -1) "▼ NEEDS WORK" else "▽ NEEDS WORK") {
                runCatching {
                    updateGalaxyTopic(topicId) {
                        it.put("vote", GalaxyRules.toggleVote(it.optInt("vote"), -1))
                    }
                }.onSuccess { rerender() }
                    .onFailure { detailView.text = "VOTE NOT SAVED\n\n${it.message}" }
            }, LinearLayout.LayoutParams(0, -2, 1f))
            topicCard.addView(voteRow)
            val replyInput = EditText(this).apply {
                hint = "Add a local reply…"
                setTextColor(Color.WHITE)
                setHintTextColor(muted)
                setPadding(dp(10), dp(8), dp(10), dp(8))
                background = outlinedPanel()
                layoutParams = LinearLayout.LayoutParams(-1, dp(64)).apply { topMargin = dp(8) }
            }
            topicCard.addView(replyInput)
            topicCard.addView(sectionAction("POST LOCAL REPLY") {
                val replyBody = replyInput.text.toString().trim()
                val validation = runCatching { GalaxyRules.validateReplyText(replyBody) }
                if (validation.isFailure) {
                    detailView.text = "REPLY NEEDS ATTENTION\n\n${validation.exceptionOrNull()?.message}"
                } else {
                    runCatching {
                        updateGalaxyTopic(topicId) {
                            it.getJSONArray("comments").put(JSONObject()
                                .put("id", UUID.randomUUID().toString())
                                .put("body", replyBody)
                                .put("created_at", System.currentTimeMillis()))
                        }
                    }.onSuccess {
                        logActivity("Galaxy local reply saved")
                        rerender()
                    }.onFailure { detailView.text = "REPLY NOT SAVED\n\n${it.message}" }
                }
            })
            val manageRow = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
            manageRow.addView(sectionAction("SHARE COPY") {
                val share = Intent(Intent.ACTION_SEND).apply {
                    type = "text/plain"
                    putExtra(Intent.EXTRA_SUBJECT, topic.optString("title"))
                    putExtra(Intent.EXTRA_TEXT, "${topic.optString("title")}\n\n${topic.optString("body")}\n\nROMVERSE Galaxy • Local preview topic")
                }
                startActivity(Intent.createChooser(share, "Share a copy of this local topic"))
            }, LinearLayout.LayoutParams(0, -2, 1f))
            manageRow.addView(sectionAction("DELETE") {
                AlertDialog.Builder(this)
                    .setTitle("Delete local topic?")
                    .setMessage("This removes the topic and ${comments.length()} replies from this phone. It cannot be undone.")
                    .setNegativeButton("Cancel", null)
                    .setPositiveButton("Delete") { _, _ ->
                        runCatching {
                            val retained = loadGalaxyTopics().filterNot { it.optString("id") == topicId }
                            saveGalaxyTopics(retained)
                        }.onSuccess { rerender() }
                            .onFailure { detailView.text = "TOPIC NOT DELETED\n\n${it.message}" }
                    }
                    .show()
            }, LinearLayout.LayoutParams(0, -2, 1f))
            topicCard.addView(manageRow)
            container.addView(topicCard)
            container.addView(space(dp(10)))
        }
    }

    private fun galaxyTime(epochMillis: Long): String = if (epochMillis > 0) {
        DateFormat.getDateTimeInstance(DateFormat.MEDIUM, DateFormat.SHORT).format(Date(epochMillis))
    } else "Unknown time"

    private fun galaxyTopicData(topic: JSONObject): GalaxyTopicData {
        val comments = topic.getJSONArray("comments")
        return GalaxyTopicData(
            topic.getString("id"),
            topic.getString("title"),
            topic.getString("body"),
            topic.getLong("created_at"),
            topic.optInt("vote", 0),
            List(comments.length()) { index ->
                val reply = comments.getJSONObject(index)
                GalaxyReplyData(
                    reply.getString("id"),
                    reply.getString("body"),
                    reply.getLong("created_at"),
                )
            },
        )
    }

    private fun showSupporterTribute(firstDiscovery: Boolean) {
        if (supporterOverlay != null) return
        val host = window.decorView.findViewById<FrameLayout>(android.R.id.content) ?: return
        var reducedMotion = userSettingsPrefs.getBoolean("reduced_motion", false)
        var sceneIndex = 0
        var sceneElapsedMs = 0L
        var lastTickMs = SystemClock.uptimeMillis()
        var paused = false
        var soundEnabled = false
        val overlay = FrameLayout(this).apply {
            setBackgroundColor("#010307".toColorInt())
            elevation = 80f
            alpha = if (reducedMotion) 1f else 0f
        }
        supporterOverlay = overlay
        supporterBackCallback = object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() = closeSupporterTribute()
        }.also { onBackPressedDispatcher.addCallback(this, it) }
        val portal = SupporterPortalView(this, R.drawable.romverse_app_icon, !reducedMotion)
        overlay.addView(portal, FrameLayout.LayoutParams(-1, -1))

        val experience = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER_HORIZONTAL
            setPadding(dp(22), dp(272), dp(22), dp(16))
            alpha = if (reducedMotion) 1f else 0f
        }
        val chapter = text("", 10f, cyan, true).apply {
            gravity = Gravity.CENTER
            letterSpacing = 0.16f
            textAlignment = View.TEXT_ALIGNMENT_CENTER
        }
        experience.addView(chapter)
        val progress = ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal).apply {
            max = 1000
            progressTintList = ColorStateList.valueOf(cyan)
            progressBackgroundTintList = ColorStateList.valueOf("#212941".toColorInt())
            contentDescription = "The Origin story progress"
            layoutParams = LinearLayout.LayoutParams(-1, dp(5)).apply {
                topMargin = dp(7)
                bottomMargin = dp(10)
            }
        }
        experience.addView(progress)
        val sceneTitle = text("", 20f, "#E3B4FF".toColorInt(), true).apply {
            gravity = Gravity.CENTER
            textAlignment = View.TEXT_ALIGNMENT_CENTER
            letterSpacing = 0.06f
        }
        experience.addView(sceneTitle)
        val constellation = text("", 9.5f, cyan, true).apply {
            gravity = Gravity.CENTER
            textAlignment = View.TEXT_ALIGNMENT_CENTER
            letterSpacing = 0.12f
            setPadding(0, dp(6), 0, dp(7))
        }
        experience.addView(constellation)
        val storyBody = text("", 12.8f, Color.WHITE, false).apply {
            gravity = Gravity.CENTER
            textAlignment = View.TEXT_ALIGNMENT_CENTER
            setLineSpacing(0f, 1.07f)
            setPadding(dp(3), dp(4), dp(3), dp(10))
        }
        experience.addView(ScrollView(this).apply {
            isFillViewport = true
            clipToPadding = false
            addView(storyBody, FrameLayout.LayoutParams(-1, -2))
        }, LinearLayout.LayoutParams(-1, 0, 1f))
        if (firstDiscovery) {
            experience.addView(text(
                "SECRET AWARD UNLOCKED  •  BEYOND THE VERSE\n" +
                    "You discovered the story behind ROMVERSE. Discovery is recorded locally; " +
                    "account XP is never simulated.",
                10.5f,
                "#72FFB2".toColorInt(),
                true,
            ).apply {
                gravity = Gravity.CENTER
                textAlignment = View.TEXT_ALIGNMENT_CENTER
                background = outlinedPanel()
                setPadding(dp(12), dp(9), dp(12), dp(9))
            })
        }

        fun originControl(label: String, action: (Button) -> Unit) = Button(this).apply {
            text = label
            isAllCaps = false
            textSize = 9.5f
            setTextColor(cyan)
            background = actionBackground()
            setPadding(dp(8), dp(8), dp(8), dp(8))
            minimumHeight = dp(42)
            setOnClickListener { action(this) }
        }

        val accessibilityRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER
        }
        val soundButton = originControl("Sound Off") { button ->
            soundEnabled = !soundEnabled
            if (soundEnabled) {
                val player = supporterMediaPlayer ?: MediaPlayer.create(this, R.raw.origin_ambient)?.also {
                    it.isLooping = true
                    it.setVolume(0.22f, 0.22f)
                    supporterMediaPlayer = it
                }
                if (player == null) {
                    soundEnabled = false
                    button.text = "Sound Unavailable"
                    button.isEnabled = false
                } else {
                    player.start()
                    button.text = "Sound On"
                }
            } else {
                supporterMediaPlayer?.pause()
                button.text = "Sound Off"
            }
        }
        accessibilityRow.addView(soundButton, LinearLayout.LayoutParams(0, -2, 1f))
        val reducedButton = originControl(
            if (reducedMotion) "Reduced Effects On" else "Reduced Effects Off",
        ) { button ->
            reducedMotion = !reducedMotion
            userSettingsPrefs.edit().putBoolean("reduced_motion", reducedMotion).apply()
            starfieldLayers.forEach { it.setMotionEnabled(!reducedMotion) }
            portal.setMotionEnabled(!reducedMotion)
            button.text = if (reducedMotion) "Reduced Effects On" else "Reduced Effects Off"
        }
        accessibilityRow.addView(reducedButton, LinearLayout.LayoutParams(0, -2, 1f).apply {
            marginStart = dp(8)
        })
        val pauseButton = originControl("Pause") { button ->
            paused = !paused
            lastTickMs = SystemClock.uptimeMillis()
            button.text = if (paused) "Resume" else "Pause"
        }
        accessibilityRow.addView(pauseButton, LinearLayout.LayoutParams(0, -2, 1f).apply {
            marginStart = dp(8)
        })
        experience.addView(accessibilityRow, LinearLayout.LayoutParams(-1, -2).apply {
            topMargin = dp(10)
        })

        val navigationRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER
        }
        lateinit var previousButton: Button
        lateinit var nextButton: Button
        lateinit var skipButton: Button

        fun updateProgress() {
            val completed = ORIGIN_SCENES.take(sceneIndex).sumOf { it.durationMs }
            val current = sceneElapsedMs.coerceAtMost(ORIGIN_SCENES[sceneIndex].durationMs)
            val total = ORIGIN_SCENES.sumOf { it.durationMs }
            progress.progress = (((completed + current) * 1000L) / total).toInt()
        }

        fun renderScene(index: Int) {
            sceneIndex = index.coerceIn(0, ORIGIN_SCENES.lastIndex)
            sceneElapsedMs = 0L
            lastTickMs = SystemClock.uptimeMillis()
            val scene = ORIGIN_SCENES[sceneIndex]
            chapter.text = "${scene.eyebrow}  •  ${sceneIndex + 1}/${ORIGIN_SCENES.size}"
            sceneTitle.text = scene.title
            constellation.text = scene.constellation
            storyBody.text = scene.body
            previousButton.isEnabled = sceneIndex > 0
            val finale = sceneIndex == ORIGIN_SCENES.lastIndex
            nextButton.text = if (finale) "Finish" else "Next  →"
            skipButton.visibility = if (finale) View.GONE else View.VISIBLE
            updateProgress()
            if (!reducedMotion) {
                storyBody.alpha = 0f
                storyBody.animate().alpha(1f).setDuration(520).start()
            } else {
                storyBody.alpha = 1f
            }
            if (sceneIndex in setOf(2, 4, 6)) {
                overlay.performHapticFeedback(HapticFeedbackConstants.CONFIRM)
            }
        }

        previousButton = originControl("←  Previous") {
            if (sceneIndex > 0) renderScene(sceneIndex - 1)
        }
        navigationRow.addView(previousButton, LinearLayout.LayoutParams(0, -2, 1f))
        skipButton = originControl("Skip to Finale") { renderScene(ORIGIN_SCENES.lastIndex) }
        navigationRow.addView(skipButton, LinearLayout.LayoutParams(0, -2, 1f).apply {
            marginStart = dp(8)
        })
        nextButton = originControl("Next  →") {
            if (sceneIndex == ORIGIN_SCENES.lastIndex) {
                closeSupporterTribute()
            } else {
                renderScene(sceneIndex + 1)
            }
        }
        navigationRow.addView(nextButton, LinearLayout.LayoutParams(0, -2, 1f).apply {
            marginStart = dp(8)
        })
        experience.addView(navigationRow, LinearLayout.LayoutParams(-1, -2).apply {
            topMargin = dp(8)
        })
        experience.addView(originControl("Exit / Return to ROMVERSE") {
            closeSupporterTribute()
        }, LinearLayout.LayoutParams(-1, -2).apply {
            topMargin = dp(8)
        })

        overlay.addView(experience, FrameLayout.LayoutParams(-1, -1))

        val close = Button(this).apply {
            text = "×"
            contentDescription = "Exit The Origin"
            setTextColor(Color.WHITE)
            textSize = 22f
            background = outlinedPanel()
            setOnClickListener { closeSupporterTribute() }
        }
        overlay.addView(close, FrameLayout.LayoutParams(dp(46), dp(46)).apply {
            gravity = Gravity.TOP or Gravity.END
            setMargins(0, dp(48), dp(16), 0)
        })
        host.addView(overlay, FrameLayout.LayoutParams(-1, -1))
        renderScene(0)
        val tick = object : Runnable {
            override fun run() {
                if (supporterOverlay !== overlay) return
                val now = SystemClock.uptimeMillis()
                if (!paused) {
                    sceneElapsedMs += (now - lastTickMs).coerceAtLeast(0L)
                    if (sceneElapsedMs >= ORIGIN_SCENES[sceneIndex].durationMs) {
                        if (sceneIndex < ORIGIN_SCENES.lastIndex) {
                            renderScene(sceneIndex + 1)
                        } else {
                            sceneElapsedMs = ORIGIN_SCENES[sceneIndex].durationMs
                        }
                    }
                    updateProgress()
                }
                lastTickMs = now
                supporterHandler.postDelayed(this, 50L)
            }
        }
        supporterTick = tick
        supporterHandler.postDelayed(tick, 50L)
        if (!reducedMotion) {
            overlay.animate().alpha(1f).setDuration(280).start()
            overlay.postDelayed({
                if (supporterOverlay === overlay && overlay.isAttachedToWindow) {
                    experience.animate().alpha(1f).setDuration(1100).start()
                }
            }, 3300)
        }
    }

    private fun closeSupporterTribute() {
        val overlay = supporterOverlay ?: return
        supporterOverlay = null
        supporterTick?.let(supporterHandler::removeCallbacks)
        supporterTick = null
        supporterMediaPlayer?.stop()
        supporterMediaPlayer?.release()
        supporterMediaPlayer = null
        supporterBackCallback?.remove()
        supporterBackCallback = null
        overlay.animate()
            .alpha(0f)
            .setDuration(260)
            .withEndAction { (overlay.parent as? FrameLayout)?.removeView(overlay) }
            .start()
    }

    private fun sectionAction(label: String, action: () -> Unit): Button = Button(this).apply {
        text = label
        alignPanelAction()
        background = actionBackground()
        setOnClickListener { action() }
    }

    private fun addTechnicalEvidenceDisclosure(
        panel: LinearLayout,
        section: String,
        technicalEvidence: LinearLayout,
        detailView: TextView,
    ) {
        val normalizedSection = section.lowercase().replace(' ', '-')
        technicalEvidence.tag = "romverse-technical-$normalizedSection"
        technicalEvidence.contentDescription = "$section technical evidence"
        val opensImmediately = CompanionExperiencePolicy.technicalEvidenceVisible(experienceMode())
        technicalEvidence.visibility = if (opensImmediately) View.VISIBLE else View.GONE
        if (opensImmediately) {
            panel.addView(text(
                "ARCHITECT  •  FULL TECHNICAL EVIDENCE OPEN",
                11f,
                violet,
                true,
            ).apply { setPadding(0, dp(8), 0, dp(8)) })
        }
        panel.addView(technicalEvidence)
        if (!opensImmediately) {
            val reveal = sectionAction("VIEW TECHNICAL EVIDENCE") {}
            reveal.contentDescription = "Reveal $section technical evidence"
            reveal.setOnClickListener {
                technicalEvidence.visibility = View.VISIBLE
                reveal.visibility = View.GONE
                detailView.text =
                    "ARCANA  •  TECHNICAL EVIDENCE REVEALED\n\n" +
                        "The full $section evidence is visible for this view. Warnings, Guardian policy, and execution authority are unchanged."
            }
            panel.addView(reveal)
        }
    }

    private fun Button.alignPanelAction() {
        isAllCaps = false
        textSize = 12f
        setTextColor(cyan)
        setTypeface(typeface, android.graphics.Typeface.BOLD)
        gravity = Gravity.CENTER
        textAlignment = View.TEXT_ALIGNMENT_CENTER
        minimumHeight = dp(CompanionLayoutSpec.CONTROL_MIN_HEIGHT_DP)
        setPadding(dp(14), dp(11), dp(14), dp(11))
        layoutParams = LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(12) }
    }

    private fun socialAction(
        label: String,
        detail: String,
        icon: Int,
        action: () -> Unit,
    ): LinearLayout = LinearLayout(this).apply {
        orientation = LinearLayout.HORIZONTAL
        gravity = Gravity.CENTER_VERTICAL
        minimumHeight = dp(CompanionLayoutSpec.SOCIAL_ACTION_MIN_HEIGHT_DP)
        setPadding(dp(14), dp(10), dp(12), dp(10))
        background = actionBackground()
        isClickable = true
        isFocusable = true
        contentDescription = "$label. $detail"
        setOnClickListener { action() }
        layoutParams = LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(12) }
        addView(ImageView(this@MainActivity).apply {
            setImageResource(icon)
            scaleType = ImageView.ScaleType.CENTER_INSIDE
            contentDescription = null
            importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO
        }, LinearLayout.LayoutParams(dp(40), dp(40)))
        addView(LinearLayout(this@MainActivity).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER_VERTICAL
            addView(text(label, 14f, Color.WHITE, true))
            addView(text(detail, 11f, muted, false))
        }, LinearLayout.LayoutParams(0, -2, 1f).apply {
            marginStart = dp(12)
        })
        addView(text("›", 24f, cyan, true).apply {
            gravity = Gravity.CENTER
            contentDescription = null
            importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO
        }, LinearLayout.LayoutParams(dp(28), dp(40)))
    }

    private fun openOfficialPage(url: String, expectedHost: String, label: String) {
        runCatching {
            val uri = Uri.parse(url)
            require(uri.scheme == "https" && uri.host.equals(expectedHost, ignoreCase = true)) {
                "The official destination is invalid."
            }
            require(uri.userInfo == null) { "The official destination must not contain user info." }
            startActivity(Intent(Intent.ACTION_VIEW, uri).apply {
                addCategory(Intent.CATEGORY_BROWSABLE)
            })
        }.onFailure {
            logActivity("Unable to open the official ROMVERSE $label page.")
        }
    }

    @Suppress("DEPRECATION")
    private fun installedPackageSignerSha256(packageName: String): String? = runCatching {
        val flags = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            PackageManager.GET_SIGNING_CERTIFICATES
        } else {
            PackageManager.GET_SIGNATURES
        }
        val packageInfo = packageManager.getPackageInfo(packageName, flags)
        val signatures = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            packageInfo.signingInfo?.apkContentsSigners.orEmpty()
        } else {
            packageInfo.signatures.orEmpty()
        }
        if (signatures.size != 1) return@runCatching null
        MessageDigest.getInstance("SHA-256")
            .digest(signatures.single().toByteArray())
            .joinToString("") { byte -> "%02x".format(byte) }
    }.getOrNull()

    private fun openVerifiedAscensionManager(target: AscensionManagerLaunchTarget) {
        val signer = installedPackageSignerSha256(target.packageName)
        val launchIntent = packageManager.getLaunchIntentForPackage(target.packageName)
        if (signer != target.signerSha256 || launchIntent == null) {
            AlertDialog.Builder(this)
                .setTitle("Verified manager unavailable")
                .setMessage(
                    if (signer == null) {
                        "${target.displayName} is not installed and launchable yet. Complete the approved Ascension handoff on Desktop, then refresh this section."
                    } else {
                        "The installed package does not match ROMVERSE's pinned official signing certificate. It was not opened."
                    },
                )
                .setPositiveButton("OK", null)
                .show()
            return
        }
        runCatching { startActivity(launchIntent) }
            .onSuccess { logActivity("Verified ${target.displayName} manager opened") }
            .onFailure {
                AlertDialog.Builder(this)
                    .setTitle("Manager could not open")
                    .setMessage(
                        "Android could not open the verified manager. Return to Desktop Ascension and retry the approved handoff.",
                    )
                    .setPositiveButton("OK", null)
                    .show()
            }
    }

    private fun addLinkRefreshAction(
        panel: LinearLayout,
        status: TextView,
        section: String,
        busyMessage: String,
    ) {
        val progress = ProgressBar(this).apply {
            isIndeterminate = true
            indeterminateTintList = ColorStateList.valueOf(cyan)
            visibility = View.GONE
            contentDescription = "$section refresh in progress"
            layoutParams = LinearLayout.LayoutParams(-1, dp(8)).apply {
                topMargin = dp(12)
            }
        }
        val action = sectionAction("REFRESH FROM DESKTOP") {}
        action.setOnClickListener {
            action.isEnabled = false
            progress.visibility = View.VISIBLE
            status.text = busyMessage
            refreshTelemetry(status, section) {
                progress.visibility = View.GONE
                action.isEnabled = true
            }
        }
        panel.addView(progress)
        panel.addView(action)
    }

    private fun usageBar(label: String, percent: Int, color: Int): LinearLayout = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        setPadding(0, dp(8), 0, dp(4))
        addView(text("$label  •  $percent%", 13f, Color.WHITE, true))
        addView(ProgressBar(this@MainActivity, null, android.R.attr.progressBarStyleHorizontal).apply {
            max = 100
            progress = percent.coerceIn(0, 100)
            progressTintList = ColorStateList.valueOf(color)
            progressBackgroundTintList = ColorStateList.valueOf("#202A46".toColorInt())
            layoutParams = LinearLayout.LayoutParams(-1, dp(12))
        })
    }

    private fun readOptimizerHistory(
        now: Long = System.currentTimeMillis(),
    ): OptimizerHistoryRead {
        val encoded = optimizerPrefs.getString("history_v1", null)
        return if (encoded == null) {
            OptimizerTrendHistory.migrateLegacy(
                optimizerPrefs.getString("battery", "").orEmpty(),
                optimizerPrefs.getString("storage", "").orEmpty(),
                optimizerPrefs.getString("ram", "").orEmpty(),
                now,
            )
        } else {
            OptimizerTrendHistory.decode(encoded, now)
        }
    }

    private fun recordOptimizerSnapshot(
        battery: Int,
        storage: Int,
        ram: Int,
    ): OptimizerHistoryRead {
        val now = System.currentTimeMillis()
        val loaded = readOptimizerHistory(now)
        if (!loaded.valid) return loaded
        val capturedAt = maxOf(now, (loaded.snapshots.lastOrNull()?.capturedAtEpochMs ?: 0L) + 1L)
        val snapshot = OptimizerSnapshot(
            capturedAt,
            battery.coerceIn(0, 100),
            storage.coerceIn(0, 100),
            ram.coerceIn(0, 100),
            optimizerHealthScore(battery, storage, ram),
        )
        val updated = runCatching {
            OptimizerTrendHistory.append(loaded.snapshots, snapshot)
        }.getOrElse {
            return OptimizerHistoryRead(false, false, emptyList(), it.message ?: "Health trend update failed")
        }
        val preserved = optimizerPrefs.edit()
            .putString("history_v1", OptimizerTrendHistory.encode(updated))
            .commit()
        if (!preserved) {
            return OptimizerHistoryRead(
                false,
                false,
                loaded.snapshots,
                "Android could not preserve the health trend; previous evidence was retained",
            )
        }
        val verified = OptimizerTrendHistory.decode(
            optimizerPrefs.getString("history_v1", "").orEmpty(),
            now,
        )
        return if (!loaded.integrityVerified && verified.valid) {
            verified.copy(reason = "Legacy health trend migrated; SHA-256 integrity verified")
        } else {
            verified
        }
    }

    private fun optimizerHealthScore(battery: Int, storage: Int, ram: Int): Int {
        return OptimizerTrendHistory.healthScore(
            battery.coerceIn(0, 100),
            storage.coerceIn(0, 100),
            ram.coerceIn(0, 100),
        )
    }

    private fun optimizerRecommendations(battery: Int, storage: Int, ram: Int): List<String> {
        val recommendations = mutableListOf<String>()
        if (battery < 20) recommendations += "• Connect a charger before diagnostics or repair work."
        if (storage >= 90) recommendations += "• Storage is critical: review large files and verified backups."
        else if (storage >= 75) recommendations += "• Storage is filling up: review downloads and unused media."
        if (ram >= 90) recommendations += "• RAM pressure is high: close unused apps from Android Recents."
        else if (ram >= 80) recommendations += "• RAM use is elevated: monitor performance before heavy work."
        if (recommendations.isEmpty()) recommendations += "• Resources are healthy. No optimization is currently required."
        return recommendations
    }

    private fun formatBytes(bytes: Long): String {
        val units = arrayOf("B", "KB", "MB", "GB", "TB")
        var value = bytes.toDouble()
        var index = 0
        while (value >= 1024 && index < units.lastIndex) {
            value /= 1024
            index++
        }
        return if (index == 0) "${value.toLong()} ${units[index]}" else "%.1f %s".format(value, units[index])
    }

    private fun startCompanionCacheCleanup(detailView: TextView, triggerButton: Button) {
        if (activeCacheCleanupFlow?.isActive == true) {
            detailView.text =
                "SAFE CLEANUP ALREADY ACTIVE\n\nROMVERSE is finishing the current cleanup phase. " +
                "The control remains locked so the same operation cannot run twice."
            return
        }
        val flow = CacheCleanupUiFlow().apply { beginPreview() }
        activeCacheCleanupFlow = flow
        triggerButton.isEnabled = false
        triggerButton.text = "BUILDING CLEANUP PREVIEW…"
        showCacheCleanupProgress(
            detailView,
            "BUILDING SAFE CLEANUP PREVIEW",
            "ROMVERSE is hashing and checking its private cache boundary. No files are being changed.",
        )
        val optimizer = CompanionCacheOptimizer(java.io.File(filesDir, "optimizer"))
        Thread {
            val preview = runCatching { optimizer.preview(cacheDir) }
            runOnUiThread {
                if (isFinishing || isDestroyed) return@runOnUiThread
                preview.onFailure {
                    flow.fail()
                    finishCacheCleanupUi(triggerButton)
                    detailView.text = "CLEANUP PREVIEW STOPPED\n\n${it.message ?: "The cache boundary could not be verified."}\n\nNo files were changed."
                }.onSuccess { plan ->
                    flow.previewCompleted(plan.candidates.isNotEmpty())
                    clearCacheCleanupProgress()
                    if (plan.candidates.isEmpty()) {
                        finishCacheCleanupUi(triggerButton)
                        detailView.text =
                            "COMPANION CACHE IS ALREADY CLEAN\n\n" +
                            "No files older than 24 hours are eligible.\n" +
                            "Recent files preserved: ${plan.skippedRecent}\n" +
                            "Unsafe links or oversized files preserved: ${plan.skippedUnsafe}\n\n" +
                            "Other apps, personal files, projects, pairing, and phone settings were not scanned."
                        return@onSuccess
                    }
                    AlertDialog.Builder(this)
                        .setTitle("Clean verified stale cache?")
                        .setMessage(
                            "ROMVERSE found ${plan.candidates.size} stale Companion cache file(s), " +
                                "recovering up to ${formatBytes(plan.totalBytes)}.\n\n" +
                                "Safety window: 24 hours\n" +
                                "Recent files preserved: ${plan.skippedRecent}\n" +
                                "Unsafe or oversized files preserved: ${plan.skippedUnsafe}\n" +
                                "Plan: ${plan.planDigest.take(20)}…\n\n" +
                                "Only ROMVERSE Companion's app-private cache is in scope. " +
                                "Every candidate is rechecked before deletion."
                        )
                        .setNegativeButton("Cancel") { _, _ ->
                            flow.cancel()
                            finishCacheCleanupUi(triggerButton)
                            detailView.text = "SAFE CLEANUP CANCELLED\n\nNo files were changed."
                        }
                        .setPositiveButton("Clean") { _, _ ->
                            flow.beginCleaning()
                            runCompanionCacheCleanup(
                                optimizer,
                                plan,
                                detailView,
                                triggerButton,
                                flow,
                            )
                        }
                        .setOnCancelListener {
                            if (flow.phase == CacheCleanupUiPhase.AWAITING_CONFIRMATION) {
                                flow.cancel()
                                finishCacheCleanupUi(triggerButton)
                                detailView.text = "SAFE CLEANUP CANCELLED\n\nNo files were changed."
                            }
                        }
                        .show()
                }
            }
        }.start()
    }

    private fun runCompanionCacheCleanup(
        optimizer: CompanionCacheOptimizer,
        plan: CacheCleanupPlan,
        detailView: TextView,
        triggerButton: Button,
        flow: CacheCleanupUiFlow,
    ) {
        triggerButton.text = "VERIFYING CLEANUP…"
        showCacheCleanupProgress(
            detailView,
            "VERIFYING AND CLEANING",
            "ROMVERSE is rechecking every approved candidate before removal. Changed files will be preserved.",
        )
        Thread {
            val completed = runCatching { optimizer.clean(plan) }
            runOnUiThread {
                if (isFinishing || isDestroyed) return@runOnUiThread
                completed.onFailure {
                    flow.fail()
                    finishCacheCleanupUi(triggerButton)
                    detailView.text =
                        "SAFE CLEANUP STOPPED\n\n${it.message ?: "The cleanup plan failed verification."}\n\n" +
                        "Review the cache and try a fresh preview."
                }.onSuccess { result ->
                    flow.finishCleaning(result.receiptSaved)
                    finishCacheCleanupUi(triggerButton)
                    val receipt = if (result.receiptSaved) {
                        "Receipt ${result.receiptId.take(12)}… integrity verified."
                    } else {
                        "Receipt needs attention: ${result.receiptError}"
                    }
                    val heading = if (result.receiptSaved) {
                        "SAFE COMPANION CLEANUP COMPLETE"
                    } else {
                        "FILES CLEANED • VERIFICATION EVIDENCE FAILED"
                    }
                    val evidenceBoundary = if (result.receiptSaved) {
                        "The cleanup is verified by its saved receipt."
                    } else {
                        "ROMVERSE will not label this cleanup verified. The file result returned, " +
                            "but its evidence could not be preserved; run a fresh preview after " +
                            "resolving app storage."
                    }
                    detailView.text =
                        "$heading\n\n" +
                        "Removed: ${result.filesRemoved} verified stale file(s)\n" +
                        "Recovered: ${formatBytes(result.bytesRecovered)}\n" +
                        "Changed or missing files preserved: ${result.changedOrMissing}\n" +
                        "Unsafe paths preserved: ${result.unsafePreserved}\n\n" +
                        "$receipt\n\n$evidenceBoundary\n\n" +
                        "No other apps, personal files, or phone settings were changed."
                    logActivity(
                        "Companion cache cleanup • ${result.filesRemoved} file(s) • " +
                            if (result.receiptSaved) "receipt verified" else "receipt needs attention"
                    )
                }
            }
        }.start()
    }

    private fun showCacheCleanupProgress(
        detailView: TextView,
        title: String,
        explanation: String,
    ) {
        clearCacheCleanupProgress()
        detailView.text = "$title\n\n$explanation\n\nProgress is active; completion is shown only after this phase returns verified evidence."
        val parent = detailView.parent as? LinearLayout ?: return
        activeCacheCleanupProgress = ProgressBar(
            this,
            null,
            android.R.attr.progressBarStyleHorizontal,
        ).apply {
            isIndeterminate = true
            indeterminateTintList = ColorStateList.valueOf(cyan)
            progressBackgroundTintList = ColorStateList.valueOf("#202A43".toColorInt())
            contentDescription = "$title in progress"
            layoutParams = LinearLayout.LayoutParams(-1, dp(14)).apply {
                topMargin = dp(12)
                bottomMargin = dp(8)
            }
        }.also { progress ->
            parent.addView(progress, parent.indexOfChild(detailView) + 1)
        }
    }

    private fun clearCacheCleanupProgress() {
        activeCacheCleanupProgress?.let { progress ->
            (progress.parent as? LinearLayout)?.removeView(progress)
        }
        activeCacheCleanupProgress = null
    }

    private fun finishCacheCleanupUi(triggerButton: Button) {
        clearCacheCleanupProgress()
        activeCacheCleanupFlow = null
        triggerButton.isEnabled = true
        triggerButton.text = "PREVIEW SAFE COMPANION CLEANUP"
    }

    private fun updateHealthMetrics() {
        val manager = getSystemService(BATTERY_SERVICE) as BatteryManager
        val battery = manager.getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY)
        val batteryIntent = registerReceiver(null, IntentFilter(Intent.ACTION_BATTERY_CHANGED))
        val temperature = batteryIntent?.getIntExtra(BatteryManager.EXTRA_TEMPERATURE, Int.MIN_VALUE)
        val status = when (batteryIntent?.getIntExtra(BatteryManager.EXTRA_STATUS, -1)) {
            BatteryManager.BATTERY_STATUS_CHARGING -> "Charging"
            BatteryManager.BATTERY_STATUS_FULL -> "Full"
            BatteryManager.BATTERY_STATUS_NOT_CHARGING -> "Not charging"
            else -> "On battery"
        }
        val stats = StatFs(Environment.getDataDirectory().path)
        val totalBytes = stats.totalBytes
        val usedBytes = (totalBytes - stats.availableBytes).coerceAtLeast(0L)
        val storagePercent = if (totalBytes > 0) (usedBytes * 100 / totalBytes) else 0
        val tempText = if (temperature != null && temperature != Int.MIN_VALUE) " • ${temperature / 10.0}°C" else ""
        batteryMetric?.text = "Battery  •  ${if (battery in 0..100) "$battery%" else "—"}\n$status$tempText"
        storageMetric?.text = "Storage  •  $storagePercent% used\n${formatBytes(usedBytes)} / ${formatBytes(totalBytes)}"
        if (activityFeed != null) {
            logActivity("Health snapshot refreshed", "health-refresh", 15 * 60 * 1000L)
        }
    }

    private fun logActivity(event: String, dedupeKey: String = "", dedupeMs: Long = 0L) {
        val clean = CompanionActivityHistory.cleanTitle(event)
        if (clean.isBlank()) return
        val events = try {
            loadActivityEvents()
        } catch (_: Exception) {
            activityFeed?.text = "Activity history needs attention. Existing data was preserved and no new event was written."
            return
        }
        val existing = events.map(::activityEventFromJson)
        val updated = CompanionActivityHistory.append(
            existing,
            CompanionActivityEvent(
                UUID.randomUUID().toString(),
                System.currentTimeMillis(),
                clean,
                dedupeKey = dedupeKey,
            ),
            dedupeMs,
        )
        if (updated === existing) {
            renderActivityFeed(events)
            return
        }
        val persisted = updated.map(::activityEventToJson)
        saveActivityEvents(persisted)
        renderActivityFeed(persisted)
    }

    private fun loadActivityEvents(): MutableList<JSONObject> {
        val raw = activityPrefs.getString("events_v1", "").orEmpty()
        if (raw.isBlank()) return mutableListOf()
        try {
            val root = JSONObject(raw)
            require(root.optInt("schema_version") == 1) { "Unsupported activity schema" }
            require(root.optString("privacy") == "private-local") { "Invalid privacy marker" }
            val array = root.getJSONArray("events")
            require(array.length() <= CompanionActivityHistory.MAX_EVENTS) { "Activity history is too large" }
            return MutableList(array.length()) { index ->
                val item = array.getJSONObject(index)
                activityEventFromJson(item)
                item
            }
        } catch (error: Exception) {
            activityPrefs.edit().putString("events_v1_corrupt_backup", raw).apply()
            throw error
        }
    }

    private fun saveActivityEvents(events: List<JSONObject>) {
        val root = JSONObject()
            .put("schema_version", 1)
            .put("privacy", "private-local")
            .put("events", JSONArray(events))
        activityPrefs.edit().putString("events_v1", root.toString()).apply()
    }

    private fun activityEventFromJson(item: JSONObject): CompanionActivityEvent =
        CompanionActivityEvent(
            item.getString("event_id"),
            item.getLong("recorded_at_epoch_ms"),
            item.getString("title"),
            item.optString("source", "ROMVERSE Companion"),
            item.optString("outcome", "information"),
            item.optString("dedupe_key"),
        )

    private fun activityEventToJson(item: CompanionActivityEvent): JSONObject = JSONObject()
        .put("event_id", item.eventId)
        .put("recorded_at_epoch_ms", item.recordedAtEpochMs)
        .put("title", item.title)
        .put("source", item.source)
        .put("outcome", item.outcome)
        .put("dedupe_key", item.dedupeKey)

    private fun renderActivityFeed(events: List<JSONObject>? = null) {
        val target = activityFeed ?: return
        val loaded = try {
            events ?: loadActivityEvents()
        } catch (_: Exception) {
            target.text = "Activity history needs attention. Existing data was preserved."
            return
        }
        target.text = if (loaded.isEmpty()) {
            "No completed activity has been recorded yet."
        } else {
            loaded.take(12).joinToString("\n\n") { item ->
                val time = DateFormat.getDateTimeInstance(DateFormat.SHORT, DateFormat.SHORT)
                    .format(Date(item.getLong("recorded_at_epoch_ms")))
                "◆  ${item.getString("title")}\n    $time"
            }
        }
    }

    private fun activityReport(): String {
        val events = try {
            loadActivityEvents()
        } catch (_: Exception) {
            return "ROMVERSE Companion activity history needs attention. Existing local data was preserved."
        }
        if (events.isEmpty()) return "ROMVERSE Companion\nNo completed activity recorded."
        return buildString {
            appendLine("ROMVERSE COMPANION • PRIVATE ACTIVITY REPORT")
            appendLine("Generated ${DateFormat.getDateTimeInstance().format(Date())}")
            appendLine("Guardian boundary: no device identifiers or user content included")
            events.forEach { item ->
                val time = DateFormat.getDateTimeInstance().format(
                    Date(item.getLong("recorded_at_epoch_ms"))
                )
                appendLine("• $time — ${item.getString("title")}")
            }
        }.trim()
    }

    private val companionRepairSteps: Array<String>
        get() = LifelinePlanBuilder.checkpoints(emptyList()).toTypedArray()

    private fun repairScore(report: String): Int? = Regex("Guardian health score: (\\d+) / 100")
        .find(report)
        ?.groupValues
        ?.getOrNull(1)
        ?.toIntOrNull()
        ?.coerceIn(0, 100)

    private fun repairFindings(report: String): List<String> = report
        .substringAfter("FINDINGS\n", "")
        .substringBefore("\n\nDEVICE ATLAS CONTEXT")
        .lineSequence()
        .map(String::trim)
        .filter { it.startsWith("• ") }
        .map { it.substringBefore(" —").take(120) }
        .distinct()
        .toList()

    private fun repairSessionCheckpoints(session: JSONObject): Array<String> {
        val stored = session.optJSONArray("checkpoints") ?: return companionRepairSteps
        return Array(stored.length()) { index -> stored.getString(index) }
    }

    private fun lifelineSessionSnapshot(session: JSONObject): LifelineSessionSnapshot {
        fun stringList(name: String): List<String> {
            val array = session.optJSONArray(name) ?: return emptyList()
            return List(array.length()) { index -> array.getString(index) }
        }
        val reviewed = session.getJSONArray("reviewed")
        return LifelineSessionSnapshot(
            sessionId = session.getString("session_id"),
            createdAtEpochMs = session.getLong("created_at_epoch_ms"),
            updatedAtEpochMs = session.getLong("updated_at_epoch_ms"),
            status = session.getString("status"),
            baselineScore = if (session.isNull("baseline_score")) null else session.getInt("baseline_score"),
            baselineFindings = stringList("baseline_findings"),
            checkpoints = repairSessionCheckpoints(session).toList(),
            reviewed = List(reviewed.length()) { index -> reviewed.getBoolean(index) },
            verificationScore = if (
                !session.has("verification_score") || session.isNull("verification_score")
            ) null else session.getInt("verification_score"),
            verificationFindings = stringList("verification_findings"),
            verificationSummary = session.optString("verification_summary"),
        )
    }

    private fun lifelineLegacySessionSnapshot(session: JSONObject): LifelineLegacySessionSnapshot {
        fun stringList(name: String): List<String> {
            val array = session.optJSONArray(name) ?: return emptyList()
            return List(array.length()) { index -> array.getString(index) }
        }
        val reviewed = session.getJSONArray("reviewed")
        return LifelineLegacySessionSnapshot(
            sessionId = session.getString("session_id"),
            createdAtEpochMs = session.getLong("created_at_epoch_ms"),
            updatedAtEpochMs = session.getLong("updated_at_epoch_ms"),
            status = session.getString("status"),
            baselineScore = if (session.isNull("baseline_score")) null else session.getInt("baseline_score"),
            baselineFindings = stringList("baseline_findings"),
            checkpoints = repairSessionCheckpoints(session).toList(),
            reviewed = List(reviewed.length()) { index -> reviewed.getBoolean(index) },
            verificationScore = if (
                !session.has("verification_score") || session.isNull("verification_score")
            ) null else session.getInt("verification_score"),
            verificationFindings = stringList("verification_findings"),
            verificationSummary = session.optString("verification_summary"),
        )
    }

    private fun preserveCompanionRepairSession(session: JSONObject): Boolean = runCatching {
        if (session.optInt("schema_version") >= 3) {
            session.put(
                "session_digest",
                LifelineSessionIntegrity.digest(lifelineSessionSnapshot(session)),
            )
        }
        repairPrefs.edit()
            .putString("session_v1", session.toString())
            .commit()
    }.getOrDefault(false)

    private fun startCompanionRepairSession(detailView: TextView) {
        val report = buildRepairReport()
        latestRepairReport = report
        saveRepairReceipt(report)
        val now = System.currentTimeMillis()
        val findings = repairFindings(report)
        val checkpoints = LifelinePlanBuilder.checkpoints(findings)
        val session = JSONObject()
            .put("schema_version", 3)
            .put("privacy", "private-local")
            .put("session_id", UUID.randomUUID().toString())
            .put("created_at_epoch_ms", now)
            .put("updated_at_epoch_ms", now)
            .put("status", "active")
            .put("baseline_score", repairScore(report) ?: JSONObject.NULL)
            .put("baseline_findings", JSONArray(findings))
            .put("checkpoints", JSONArray(checkpoints))
            .put("reviewed", JSONArray(List(checkpoints.size) { false }))
            .put("device_modified", false)
        if (!preserveCompanionRepairSession(session)) {
            detailView.text = "LIFELINE NEEDS ATTENTION\n\nAndroid could not preserve the private local baseline. No session was started and no device change was attempted."
            logActivity("Lifeline session persistence failed")
            return
        }
        detailView.text = companionRepairSessionSummary(session) +
            "\n\nBaseline diagnostic saved. Checkpoints do not prove a repair; use a fresh comparison after reviewing them."
        logActivity("Lifeline session started")
        showCompanionRepairCheckpoints(detailView)
    }

    private fun loadCompanionRepairSession(): JSONObject? {
        val raw = repairPrefs.getString("session_v1", "").orEmpty()
        if (raw.isBlank()) return null
        try {
            val session = JSONObject(raw)
            val schemaVersion = session.optInt("schema_version")
            require(schemaVersion in 1..3) { "Unsupported repair session schema" }
            require(session.optString("privacy") == "private-local") { "Invalid repair privacy marker" }
            require(session.getString("session_id").length in 1..80) { "Invalid repair session" }
            val now = System.currentTimeMillis()
            val createdAt = session.getLong("created_at_epoch_ms")
            val updatedAt = session.getLong("updated_at_epoch_ms")
            require(createdAt > 0L && createdAt <= now + 5L * 60L * 1_000L) {
                "Invalid repair creation timestamp"
            }
            require(updatedAt in createdAt..(now + 5L * 60L * 1_000L)) {
                "Invalid repair update timestamp"
            }
            require(session.optBoolean("device_modified", true).not()) { "Invalid device-change marker" }
            val status = session.optString("status")
            require(
                status in setOf(
                    "active",
                    "ready_for_verification",
                    "ready_for_comparison",
                    "comparison_complete",
                ),
            ) { "Invalid repair session status" }
            require(
                session.isNull("baseline_score") || session.getInt("baseline_score") in 0..100
            ) { "Invalid baseline score" }
            val findings = session.getJSONArray("baseline_findings")
            require(findings.length() <= 30) { "Too many findings" }
            for (index in 0 until findings.length()) {
                require(findings.getString(index).length in 1..120) { "Invalid repair finding" }
            }
            val checkpoints = repairSessionCheckpoints(session)
            require(checkpoints.size in 2..12) { "Invalid checkpoint count" }
            require(checkpoints.all { it.length in 1..240 && it.none(Char::isISOControl) }) {
                "Invalid repair checkpoint"
            }
            require(session.getJSONArray("reviewed").length() == checkpoints.size) { "Invalid checkpoints" }
            if (schemaVersion >= 2) {
                val baseFields = setOf(
                    "schema_version",
                    "privacy",
                    "session_id",
                    "created_at_epoch_ms",
                    "updated_at_epoch_ms",
                    "status",
                    "baseline_score",
                    "baseline_findings",
                    "checkpoints",
                    "reviewed",
                    "device_modified",
                    "session_digest",
                )
                val expectedFields = if (status == "comparison_complete") {
                    baseFields + setOf(
                        "verification_score",
                        "verification_findings",
                        "verification_summary",
                    )
                } else baseFields
                require(session.keys().asSequence().toSet() == expectedFields) {
                    "Repair session fields are invalid"
                }
                if (schemaVersion == 2) {
                    require(
                        LifelineSessionIntegrity.verifiesLegacyV2(
                            lifelineLegacySessionSnapshot(session),
                            session.getString("session_digest"),
                        ),
                    ) { "Legacy repair session integrity mismatch" }
                    return migrateLifelineSessionV2(session, raw)
                }
                require(
                    LifelineSessionIntegrity.verifies(
                        lifelineSessionSnapshot(session),
                        session.getString("session_digest"),
                    ),
                ) { "Repair session integrity mismatch" }
            }
            return session
        } catch (_: Exception) {
            repairPrefs.edit().putString("session_v1_corrupt_backup", raw).apply()
            return null
        }
    }

    private fun migrateLifelineSessionV2(session: JSONObject, raw: String): JSONObject {
        val migrated = LifelineSessionMigration.fromV2(lifelineLegacySessionSnapshot(session))
        session.put("status", migrated.status)
        session.put("baseline_findings", JSONArray(migrated.baselineFindings))
        if (migrated.status == "comparison_complete") {
            session.put("verification_score", migrated.verificationScore ?: JSONObject.NULL)
            session.put("verification_findings", JSONArray(migrated.verificationFindings))
            session.put("verification_summary", migrated.verificationSummary)
        } else {
            session.remove("verification_score")
            session.remove("verification_findings")
            session.remove("verification_summary")
        }
        session.put("schema_version", 3)
        session.put(
            "session_digest",
            LifelineSessionIntegrity.digest(migrated),
        )
        require(
            repairPrefs.edit()
                .putString("session_v2_migration_backup", raw)
                .putString("session_v1", session.toString())
                .commit(),
        ) { "Migrated repair session could not be preserved" }
        return session
    }

    private fun showCompanionRepairCheckpoints(detailView: TextView) {
        val session = loadCompanionRepairSession()
        if (session == null) {
            detailView.text = "NO LIFELINE SESSION\n\nStart a session first. ROMVERSE will preserve a local diagnostic baseline before showing checkpoints."
            return
        }
        val checkpoints = repairSessionCheckpoints(session)
        val reviewed = session.getJSONArray("reviewed")
        val checked = BooleanArray(checkpoints.size) { index -> reviewed.optBoolean(index) }
        AlertDialog.Builder(this)
            .setTitle("Lifeline checkpoints")
            .setMessage("Mark only steps you genuinely reviewed or tried. Checkmarks never mean the phone is repaired.")
            .setMultiChoiceItems(checkpoints, checked) { _, index, value -> checked[index] = value }
            .setNegativeButton("Cancel", null)
            .setPositiveButton("Save progress") { _, _ ->
                session.put("reviewed", JSONArray(checked.toList()))
                session.put("updated_at_epoch_ms", System.currentTimeMillis())
                session.put("status", if (checked.all { it }) "ready_for_comparison" else "active")
                if (preserveCompanionRepairSession(session)) {
                    detailView.text = companionRepairSessionSummary(session) +
                        "\n\n${checked.count { it }}/${checked.size} checkpoints reviewed. No repair success has been claimed."
                    logActivity("Lifeline progress saved")
                } else {
                    detailView.text = "LIFELINE PROGRESS NOT SAVED\n\nAndroid could not preserve this checkpoint update. The phone was not changed; reopen Lifeline and try again."
                    logActivity("Lifeline progress persistence failed")
                }
            }
            .show()
    }

    private fun verifyCompanionRepairSession(detailView: TextView) {
        val session = loadCompanionRepairSession()
        if (session == null) {
            detailView.text = "NO LIFELINE SESSION\n\nStart a session before requesting verification."
            return
        }
        val reviewed = session.getJSONArray("reviewed")
        val reviewedCount = (0 until reviewed.length()).count { reviewed.optBoolean(it) }
        if (reviewedCount != reviewed.length()) {
            detailView.text =
                "REVIEW CHECKPOINTS FIRST\n\n" +
                "Lifeline has $reviewedCount/${reviewed.length()} reviewed checkpoints. " +
                "ROMVERSE opened the guided checklist; mark only steps you genuinely reviewed. " +
                "A checkmark still does not prove a repair."
            showCompanionRepairCheckpoints(detailView)
            return
        }
        val report = buildRepairReport()
        latestRepairReport = report
        saveRepairReceipt(report)
        val baselineScore = if (session.isNull("baseline_score")) {
            null
        } else session.getInt("baseline_score")
        val currentScore = repairScore(report)
        val baselineFindings = session.getJSONArray("baseline_findings").let { array ->
            List(array.length()) { index -> array.getString(index) }.toSet()
        }
        val currentFindings = repairFindings(report).toSet()
        val comparison = RecoveryEvidenceComparator.compare(
            RecoveryEvidence(baselineScore, baselineFindings),
            RecoveryEvidence(currentScore, currentFindings),
        )
        val summary = comparison.summary()
        session.put("status", "comparison_complete")
            .put("updated_at_epoch_ms", System.currentTimeMillis())
            .put("verification_score", currentScore ?: JSONObject.NULL)
            .put("verification_findings", JSONArray(currentFindings.toList()))
            .put("verification_summary", summary)
        if (preserveCompanionRepairSession(session)) {
            detailView.text = "$summary\n\n$report\n\nThis comparison describes evidence only; it does not certify a hardware or software repair."
            logActivity("Lifeline evidence comparison completed")
        } else {
            detailView.text = "LIFELINE COMPARISON NOT SAVED\n\nThe fresh scan completed, but Android could not preserve its comparison. No repair success was claimed and the phone was not changed.\n\n$report"
            logActivity("Lifeline comparison persistence failed")
        }
    }

    private fun companionRepairSessionSummary(session: JSONObject? = loadCompanionRepairSession()): String {
        if (session == null) {
            return "LIFELINE\n\nRun a complete diagnostic or start a Lifeline session. ROMVERSE uses read-only evidence and never flashes, wipes, roots, unlocks, or silently changes settings."
        }
        val reviewed = session.getJSONArray("reviewed")
        val reviewedCount = (0 until reviewed.length()).count { reviewed.optBoolean(it) }
        val checkpointCount = repairSessionCheckpoints(session).size
        val created = DateFormat.getDateTimeInstance().format(Date(session.getLong("created_at_epoch_ms")))
        val verification = session.optString("verification_summary")
        return buildString {
            appendLine("LIFELINE • ${session.optString("status").replace('_', ' ').uppercase()}")
            val baseline = if (session.isNull("baseline_score")) {
                "UNCONFIRMED"
            } else "${session.getInt("baseline_score")} / 100"
            appendLine("Baseline: $baseline • $created")
            appendLine("Progress: $reviewedCount/$checkpointCount checkpoints reviewed")
            if (verification.isNotBlank()) appendLine(verification)
            append("Guardian boundary: evidence and guidance only; device-changing repair remains locked.")
        }
    }

    private fun buildHealthSummary(): String {
        val manager = getSystemService(BATTERY_SERVICE) as BatteryManager
        val battery = manager.getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY)
        val stats = StatFs(Environment.getDataDirectory().path)
        val total = stats.totalBytes
        val used = (total - stats.availableBytes).coerceAtLeast(0L)
        return """ROMVERSE Companion health summary
Model: ${localDeviceIdentity.displayName}
Reported identity: ${localDeviceIdentity.rawModel} • ${localDeviceIdentity.codename} • ${if (localDeviceIdentity.verifiedExact) "verified exact" else "unconfirmed"}
Android: ${Build.VERSION.RELEASE} (API ${Build.VERSION.SDK_INT})
Battery: ${if (battery in 0..100) "$battery%" else "unknown"}
Storage: ${formatBytes(used)} / ${formatBytes(total)}
Guardian: ACTIVE (read-only)
""".trim()
    }

    private data class MemberHttpResult(val code: Int, val payload: JSONObject)

    private fun memberConfigOrNull(): CompanionMembersConfig? {
        val issuer = userSettingsPrefs.getString("members_issuer", "").orEmpty()
        val clientId = userSettingsPrefs.getString("members_client_id", "").orEmpty()
        if (issuer.isBlank() || clientId.isBlank()) return null
        return runCatching { CompanionMembersConfig(issuer, clientId).validated() }.getOrNull()
    }

    private fun beginMemberSignIn() {
        val detail = memberDetailView ?: return
        if (!userSettingsPrefs.getBoolean("online_intelligence_enabled", true)) {
            detail.text =
                "PUBLIC HTTPS SERVICES DISABLED\n\nOpen ROMVERSE Settings and enable Companion's configured HTTPS services before starting Members sign-in. Local ROMVERSE Link remains available."
            return
        }
        val configuration = memberConfigOrNull()
        if (configuration == null) {
            detail.text = "MEMBERS SERVICE NOT CONFIGURED\n\nOpen ROMVERSE Settings and enter the official HTTPS issuer and public client ID."
            return
        }
        detail.text = "CONTACTING TRUSTED MEMBERS SERVICE…\n\nPasswords are never requested by Companion."
        Thread {
            runCatching {
                val discoveryPayload = memberHttp(
                    "${configuration.issuer}/.well-known/openid-configuration"
                )
                require(discoveryPayload.code in 200..299) {
                    "The Members discovery service rejected the request."
                }
                val discovery = CompanionMembersDiscovery.parse(
                    discoveryPayload.payload,
                    configuration.issuer,
                )
                val authorizationPayload = memberHttp(
                    discovery.deviceEndpoint,
                    "POST",
                    mapOf("client_id" to configuration.clientId, "scope" to configuration.scope),
                )
                require(authorizationPayload.code in 200..299) {
                    "The Members service could not start browser authorization."
                }
                val authorization = CompanionDeviceAuthorization.parse(
                    authorizationPayload.payload,
                    System.currentTimeMillis(),
                )
                discovery to authorization
            }.onSuccess { (discovery, authorization) ->
                runOnUiThread {
                    memberDiscovery = discovery
                    memberAuthorization = authorization
                    memberPollDelaySeconds = authorization.intervalSeconds
                    memberDetailView?.text =
                        "FINISH SIGN-IN IN YOUR BROWSER\n\nCode: ${authorization.userCode}\n\nCompanion is waiting securely. The code expires automatically."
                    startActivity(
                        Intent(
                            Intent.ACTION_VIEW,
                            Uri.parse(
                                authorization.verificationUriComplete.ifBlank {
                                    authorization.verificationUri
                                },
                            ),
                        ),
                    )
                    memberHandler.postDelayed(
                        { pollMemberSignIn(configuration) },
                        memberPollDelaySeconds * 1000L,
                    )
                }
            }.onFailure { error ->
                runOnUiThread {
                    memberDetailView?.text =
                        "SIGN-IN NEEDS ATTENTION\n\n${error.message ?: "The Members service could not be reached securely."}\n\nNo account data or token was saved."
                }
            }
        }.start()
    }

    private fun pollMemberSignIn(configuration: CompanionMembersConfig) {
        val discovery = memberDiscovery ?: return
        val authorization = memberAuthorization ?: return
        if (System.currentTimeMillis() >= authorization.expiresAtEpochMs) {
            memberAuthorization = null
            memberDetailView?.text =
                "SIGN-IN EXPIRED\n\nNothing was saved. Start a new secure browser sign-in when ready."
            return
        }
        Thread {
            runCatching {
                memberHttp(
                    discovery.tokenEndpoint,
                    "POST",
                    mapOf(
                        "grant_type" to "urn:ietf:params:oauth:grant-type:device_code",
                        "device_code" to authorization.deviceCode,
                        "client_id" to configuration.clientId,
                    ),
                )
            }.onSuccess { result ->
                val error = result.payload.optString("error")
                when {
                    result.code in 200..299 -> completeMemberSignIn(discovery, result.payload)
                    error == "authorization_pending" -> scheduleMemberPoll(configuration)
                    error == "slow_down" -> {
                        memberPollDelaySeconds = (memberPollDelaySeconds + 5).coerceAtMost(30)
                        scheduleMemberPoll(configuration)
                    }
                    error == "expired_token" || error == "access_denied" -> runOnUiThread {
                        memberAuthorization = null
                        memberDetailView?.text =
                            "SIGN-IN ENDED\n\nThe browser request expired or was declined. No token was saved."
                    }
                    else -> runOnUiThread {
                        memberDetailView?.text =
                            "SIGN-IN NEEDS ATTENTION\n\nThe identity service rejected the request. No token was saved."
                    }
                }
            }.onFailure { error -> runOnUiThread {
                memberDetailView?.text =
                    "SIGN-IN NEEDS ATTENTION\n\n${error.message ?: "The service could not be reached securely."}"
            } }
        }.start()
    }

    private fun scheduleMemberPoll(configuration: CompanionMembersConfig) {
        runOnUiThread {
            memberDetailView?.text =
                "WAITING FOR BROWSER AUTHORIZATION…\n\nCode: ${memberAuthorization?.userCode.orEmpty()}"
            memberHandler.postDelayed(
                { pollMemberSignIn(configuration) },
                memberPollDelaySeconds * 1000L,
            )
        }
    }

    private fun completeMemberSignIn(
        discovery: CompanionMembersDiscovery,
        tokenPayload: JSONObject,
    ) {
        Thread {
            runCatching {
                val accessToken = tokenPayload.optString("access_token")
                require(accessToken.length in 16..16_384) {
                    "The identity service returned an invalid access token."
                }
                require(tokenPayload.optString("token_type").equals("Bearer", ignoreCase = true)) {
                    "The identity service returned an unsupported token type."
                }
                val expiresIn = tokenPayload.optInt("expires_in", -1)
                require(expiresIn in 60..86_400) {
                    "The identity service returned an invalid token expiry."
                }
                val profileResult = memberHttp(
                    discovery.userInfoEndpoint,
                    bearer = accessToken,
                )
                require(profileResult.code in 200..299) {
                    "The identity service did not verify the member profile."
                }
                CompanionMemberSession(
                    accessToken,
                    System.currentTimeMillis() + expiresIn * 1000L,
                    CompanionMemberProfile.parse(profileResult.payload),
                )
            }.onSuccess { session -> runOnUiThread {
                memberSession = session
                refreshGreeting()
                memberAuthorization = null
                memberDiscovery = null
                memberDetailView?.text = buildString {
                    appendLine("SIGNED IN  •  ${session.profile.displayName}")
                    if (session.profile.email.isNotBlank()) appendLine(session.profile.email)
                    appendLine()
                    append("${session.profile.plan}  •  ${session.profile.status.uppercase()}\n\nServer-verified profile; token held only in memory.")
                }
                logActivity("ROMVERSE Members sign-in verified")
            } }.onFailure { error -> runOnUiThread {
                memberAuthorization = null
                memberDetailView?.text =
                    "MEMBER PROFILE NEEDS ATTENTION\n\n${error.message}\n\nThe incomplete session was discarded."
            } }
        }.start()
    }

    private fun memberHttp(
        rawUrl: String,
        method: String = "GET",
        form: Map<String, String>? = null,
        bearer: String? = null,
    ): MemberHttpResult {
        val trustedUrl = trustedMembersUrl(rawUrl, "Members endpoint")
        val connection = (URL(trustedUrl).openConnection() as HttpURLConnection).apply {
            requestMethod = method
            connectTimeout = 12_000
            readTimeout = 12_000
            instanceFollowRedirects = false
            setRequestProperty("Accept", "application/json")
            setRequestProperty("User-Agent", "ROMVERSE-Companion/0.1 Members")
            if (bearer != null) setRequestProperty("Authorization", "Bearer $bearer")
            if (form != null) {
                doOutput = true
                setRequestProperty("Content-Type", "application/x-www-form-urlencoded")
            }
        }
        if (form != null) {
            val body = form.entries.joinToString("&") { (key, value) ->
                "${URLEncoder.encode(key, Charsets.UTF_8.name())}=" +
                    URLEncoder.encode(value, Charsets.UTF_8.name())
            }.toByteArray()
            require(body.size <= 32 * 1024) { "The Members request is too large." }
            connection.outputStream.use { it.write(body) }
        }
        val code = connection.responseCode
        require(code !in 300..399) { "The Members service returned an unsafe redirect." }
        val input = if (code in 200..299) connection.inputStream else connection.errorStream
        val bytes = input?.use { stream ->
            val output = ByteArrayOutputStream()
            val buffer = ByteArray(8 * 1024)
            while (true) {
                val count = stream.read(buffer)
                if (count < 0) break
                require(output.size() + count <= 512 * 1024) {
                    "The Members response is too large."
                }
                output.write(buffer, 0, count)
            }
            output.toByteArray()
        } ?: ByteArray(0)
        val payload = if (bytes.isEmpty()) JSONObject() else JSONObject(bytes.toString(Charsets.UTF_8))
        return MemberHttpResult(code, payload)
    }

    private fun postPairRequest(host: String, code: String, certificateSha256: String): String? {
        return try {
            val connection = openDesktopConnection(host, "/pair", certificateSha256).apply {
                requestMethod = "POST"
                connectTimeout = 4000
                readTimeout = 4000
                doOutput = true
                setRequestProperty("Content-Type", "application/json")
            }
            connection.outputStream.use {
                it.write(JSONObject().put("code", code).toString().toByteArray())
            }
            if (connection.responseCode !in 200..299) return null
            val payload = JSONObject(connection.inputStream.bufferedReader().use { it.readText() })
            payload.optString("request_id").takeIf {
                payload.optInt("protocol_version") == DesktopLinkSecurity.PROTOCOL_VERSION &&
                    payload.optString("status") == "pending" &&
                    it.length in 24..128
            }
        } catch (_: Exception) {
            null
        }
    }

    private fun getPairStatus(
        host: String,
        requestId: String,
        certificateSha256: String,
    ): PairStatus {
        return try {
            val connection = openDesktopConnection(host, "/status", certificateSha256).apply {
                connectTimeout = 2500
                readTimeout = 2500
                setRequestProperty("X-ROMVERSE-Pairing-Request", requestId)
            }
            if (connection.responseCode !in 200..299) return PairStatus("")
            val payload = JSONObject(connection.inputStream.bufferedReader().use { it.readText() })
            if (payload.optInt("protocol_version") != DesktopLinkSecurity.PROTOCOL_VERSION) {
                return PairStatus("")
            }
            PairStatus(
                payload.optString("status"),
                payload.optString("session_token"),
                payload.optLong("expires_in_seconds", 0L).coerceIn(
                    0L,
                    DesktopLinkSecurity.MAX_REMEMBERED_SESSION_SECONDS,
                ),
            )
        } catch (_: Exception) {
            PairStatus("")
        }
    }

    private fun getTelemetrySummary(
        host: String,
        token: String,
        certificateSha256: String,
    ): TelemetryResult {
        return try {
            val connection = openDesktopConnection(host, "/telemetry", certificateSha256).apply {
                connectTimeout = 2500
                readTimeout = 2500
                setRequestProperty("Authorization", "Bearer $token")
            }
            if (connection.responseCode == 401) return TelemetryResult(unauthorized = true)
            if (connection.responseCode !in 200..299) return TelemetryResult()
            val payload = JSONObject(connection.inputStream.bufferedReader().use { it.readText() })
            val schema = payload.optInt("schema_version", 0)
            if (schema !in 1..6) return TelemetryResult()
            val battery = payload.optInt("battery_percent", -1).takeIf { it >= 0 }?.let { "$it%" } ?: "unknown"
            val used = payload.optLong("storage_used_bytes", -1).takeIf { it >= 0 }?.let { formatBytes(it) } ?: "unknown"
            val total = payload.optLong("storage_total_bytes", -1).takeIf { it >= 0 }?.let { formatBytes(it) } ?: "unknown"
            TelemetryResult(
                summary = "Desktop telemetry: battery $battery  •  storage $used / $total  •  Guardian active",
                ascension = DesktopAscensionStatus.parse(
                    schemaVersion = schema,
                    state = payload.optString("ascension_state"),
                    project = payload.optString("ascension_project"),
                    method = payload.optString("ascension_method"),
                    targetPartition = payload.optString("ascension_target_partition"),
                    blockerCount = payload.optInt("ascension_blocker_count", -1),
                    phoneChanged = payload.optBoolean("ascension_phone_changed", true),
                    executionAuthority = payload.optString("ascension_execution_authority"),
                    stageNumber = payload.optInt("ascension_stage_number", 0),
                    stageTitle = payload.optString("ascension_stage_title"),
                    guidedNextAction = payload.optString("ascension_next_action"),
                    whyItMatters = payload.optString("ascension_why"),
                    romverseAction = payload.optString("ascension_romverse_action"),
                    managerState = payload.optString(
                        "ascension_manager_state",
                        "unavailable",
                    ),
                    managerRepository = payload.optString("ascension_manager_repository"),
                    managerTag = payload.optString("ascension_manager_tag"),
                    managerAsset = payload.optString("ascension_manager_asset"),
                    managerSha256Ref = payload.optString("ascension_manager_sha256_ref"),
                ),
                liveConsole = if (schema >= 5) {
                    DesktopLiveConsoleStatus.parse(schema, payload)
                } else null,
                deviceDna = if (schema >= 6) {
                    DesktopDeviceDnaStatus.parse(schema, payload)
                } else null,
            )
        } catch (_: Exception) {
            TelemetryResult()
        }
    }

    private fun buildCompanionHealthSnapshot(): CompanionHealthSnapshot {
        val capturedAt = System.currentTimeMillis()
        val battery = (getSystemService(BATTERY_SERVICE) as BatteryManager)
            .getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY)
            .takeIf { it in 0..100 }
        val batteryIntent = registerReceiver(null, IntentFilter(Intent.ACTION_BATTERY_CHANGED))
        val temperature = batteryIntent
            ?.getIntExtra(BatteryManager.EXTRA_TEMPERATURE, Int.MIN_VALUE)
            ?.takeUnless { it == Int.MIN_VALUE }
            ?.div(10.0)
            ?.takeIf { it in -20.0..100.0 }
        val storage = StatFs(Environment.getDataDirectory().path)
        val storageTotal = storage.totalBytes.takeIf { it > 0 }
        val storageUsed = storageTotal?.let { (it - storage.availableBytes).coerceIn(0L, it) }
        val memory = ActivityManager.MemoryInfo().also {
            (getSystemService(ACTIVITY_SERVICE) as ActivityManager).getMemoryInfo(it)
        }
        val memoryTotal = memory.totalMem.takeIf { it > 0 }
        val memoryAvailable = memoryTotal?.let { memory.availMem.coerceIn(0L, it) }
        val storagePercent = if (storageUsed != null) {
            ((storageUsed * 100) / storageTotal).toInt().coerceIn(0, 100)
        } else null
        val ramPercent = if (memoryAvailable != null) {
            (((memoryTotal - memoryAvailable) * 100) / memoryTotal).toInt().coerceIn(0, 100)
        } else null
        val connectivity = getSystemService(CONNECTIVITY_SERVICE) as ConnectivityManager
        val networkCapabilities = connectivity.activeNetwork?.let(connectivity::getNetworkCapabilities)
        val networkValidated = if (networkCapabilities == null) {
            false
        } else {
            networkCapabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED)
        }
        val usbConnected = isUsbConnected()
        val vitalis = VitalisSnapshot(
            batteryPercent = battery,
            temperatureCelsius = temperature,
            storageUsedPercent = storagePercent,
            ramUsedPercent = ramPercent,
            networkValidated = networkValidated,
            usbConnected = usbConnected,
            capturedAtEpochMs = capturedAt,
        )
        val assessment = VitalisAssessmentEngine.assess(vitalis, capturedAt)
        return CompanionHealthSnapshot(
            capturedAtEpochMs = capturedAt,
            manufacturer = wireText(Build.MANUFACTURER),
            model = wireText(Build.MODEL),
            deviceCodename = wireText(Build.DEVICE),
            androidVersion = wireText(Build.VERSION.RELEASE),
            sdkInt = Build.VERSION.SDK_INT,
            companionVersion = wireText(BuildConfig.VERSION_NAME),
            batteryPercent = battery,
            batteryTemperatureCelsius = temperature,
            storageUsedBytes = storageUsed,
            storageTotalBytes = storageTotal,
            memoryAvailableBytes = memoryAvailable,
            memoryTotalBytes = memoryTotal,
            networkValidated = networkValidated,
            usbConnected = usbConnected,
            healthScore = assessment.score,
            vitalisState = assessment.state,
            vitalisEvidencePercent = assessment.evidencePercent,
            kernelRelease = wireText(
                System.getProperty("os.version").orEmpty().ifBlank { "Unknown" },
                160,
            ),
            rootSignal = localRootSignal(),
            rootManagerCandidate = AscensionManagerLaunchPolicy.installedCandidate(
                ::installedPackageSignerSha256,
            ),
            bootloaderState = "unknown",
            kernelSuSupport = "unknown",
        )
    }

    private fun postCompanionHealthSnapshot(
        host: String,
        token: String,
        certificateSha256: String,
    ): SnapshotPostResult {
        return try {
            val body = JSONObject(buildCompanionHealthSnapshot().asWireMap())
                .toString()
                .toByteArray(Charsets.UTF_8)
            val connection = openDesktopConnection(
                host,
                "/companion/telemetry",
                certificateSha256,
            ).apply {
                requestMethod = "POST"
                connectTimeout = 2500
                readTimeout = 2500
                doOutput = true
                setFixedLengthStreamingMode(body.size)
                setRequestProperty("Authorization", "Bearer $token")
                setRequestProperty("Content-Type", "application/json")
            }
            connection.outputStream.use { it.write(body) }
            if (connection.responseCode == 401) return SnapshotPostResult(unauthorized = true)
            if (connection.responseCode !in 200..299) return SnapshotPostResult()
            val payload = JSONObject(connection.inputStream.bufferedReader().use { it.readText() })
            SnapshotPostResult(
                accepted = payload.optInt("protocol_version") == DesktopLinkSecurity.PROTOCOL_VERSION &&
                    payload.optString("status") == "accepted" &&
                    payload.optString("privacy_scope") == "health_and_device_safety",
            )
        } catch (_: Exception) {
            SnapshotPostResult()
        }
    }

    private fun wireText(value: String, maximum: Int = 80): String = value
        .filterNot(Char::isISOControl)
        .trim()
        .ifBlank { "Unknown" }
        .take(maximum)

    private fun localRootSignal(): String {
        val testKeys = Build.TAGS?.contains("test-keys", ignoreCase = true) == true
        val knownSu = listOf(
            "/system/bin/su",
            "/system/xbin/su",
            "/sbin/su",
            "/debug_ramdisk/su",
        ).any { java.io.File(it).isFile }
        return if (testKeys || knownSu) "observed" else "not_observed"
    }

    private fun scheduleTelemetryRefresh(label: TextView, delayMillis: Long = 10_000L) {
        telemetryHandler.removeCallbacksAndMessages(null)
        if (!activityResumed) return
        telemetryHandler.postDelayed({
            refreshTelemetry(label)
        }, delayMillis.coerceIn(0L, 60_000L))
    }

    private fun resumeRememberedLink() {
        val label = desktopTelemetryView ?: return
        if (!hasSecureWirelessSession()) {
            if (hasRememberedDesktop()) {
                telemetryHost = pairingPrefs.getString("paired_host", null)
                telemetryToken = null
                telemetryCertificateSha256 = pairingPrefs.getString("certificate_sha256", null)
                label.text = "Desktop remembered securely • approval expired • enter a new Link code"
            }
            return
        }
        telemetryHost = pairingPrefs.getString("paired_host", null)
        telemetryToken = linkSessionVault.load()
        telemetryCertificateSha256 = pairingPrefs.getString("certificate_sha256", null)
        label.text = "Desktop telemetry: reconnecting securely…"
        scheduleTelemetryRefresh(label, 0L)
    }

    private fun refreshTelemetry(
        label: TextView,
        reopenSection: String? = null,
        onFinished: (() -> Unit)? = null,
    ) {
        if (!hasSecureWirelessSession()) {
            clearWirelessSession(forgetTrustedDesktop = !hasRememberedDesktop())
            telemetryToken = null
            label.text = if (hasRememberedDesktop()) {
                "Desktop remembered securely • approval expired • enter a new Link code"
            } else {
                "Desktop telemetry: secure session expired • pair again"
            }
            refreshHomeHero()
            onFinished?.invoke()
            return
        }
        if (telemetryRefreshInFlight) {
            onFinished?.invoke()
            return
        }
        val host = telemetryHost
        val token = telemetryToken
        val certificateSha256 = telemetryCertificateSha256
        if (host == null || token == null || certificateSha256 == null) {
            label.text = "Desktop telemetry: secure session details are unavailable • pair again"
            onFinished?.invoke()
            return
        }
        telemetryRefreshInFlight = true
        Thread {
            val telemetry = getTelemetrySummary(host, token, certificateSha256)
            val phoneSync = if (!telemetry.unauthorized) {
                postCompanionHealthSnapshot(host, token, certificateSha256)
            } else SnapshotPostResult()
            if (telemetry.unauthorized || phoneSync.unauthorized) {
                runOnUiThread {
                    telemetryRefreshInFlight = false
                    clearWirelessSession(forgetTrustedDesktop = false)
                    label.text =
                        "Trusted Desktop remembered • approval ended • enter a new Link code"
                    refreshHomeHero()
                    onFinished?.invoke()
                }
                return@Thread
            }
            if (telemetry.summary != null) {
                runOnUiThread {
                    telemetryRefreshInFlight = false
                    telemetryRetryAttempt = 0
                    val hydrateVisibleRoute = currentRoute.needsTelemetryHydration(
                        hasAscension = desktopAscensionStatus != null,
                        hasLiveConsole = desktopLiveConsoleStatus != null,
                        hasDeviceDna = desktopDeviceDnaStatus != null,
                    )
                    desktopAscensionStatus = telemetry.ascension
                    desktopLiveConsoleStatus = telemetry.liveConsole
                    desktopDeviceDnaStatus = telemetry.deviceDna
                    refreshHomeHero()
                    label.text = if (phoneSync.accepted) {
                        "${telemetry.summary}  •  phone health synced"
                    } else {
                        "${telemetry.summary}  •  phone sync retrying"
                    }
                    if (reopenSection != null) {
                        showSection(
                            reopenSection,
                            "Fresh authenticated ROMVERSE Link evidence received from Desktop.",
                        )
                    } else if (hydrateVisibleRoute) {
                        restoreRoute(currentRoute)
                    }
                    onFinished?.invoke()
                    scheduleTelemetryRefresh(label)
                }
            } else {
                runOnUiThread {
                    telemetryRefreshInFlight = false
                    val delay = DesktopLinkSecurity.retryDelayMillis(telemetryRetryAttempt)
                    telemetryRetryAttempt = (telemetryRetryAttempt + 1).coerceAtMost(50)
                    label.text = "Desktop temporarily unavailable • reconnecting automatically"
                    onFinished?.invoke()
                    scheduleTelemetryRefresh(label, delay)
                    val addressField = linkAddressField
                    val fingerprintField = linkFingerprintField
                    val safetyLabel = linkSafetyLabel
                    if (
                        addressField != null &&
                        fingerprintField != null &&
                        safetyLabel != null
                    ) {
                        discoverPc(addressField, fingerprintField, safetyLabel)
                    }
                }
            }
        }.start()
    }

    private fun hasSecureWirelessSession(): Boolean =
        pairingPrefs.getBoolean("paired", false) &&
            !pairingPrefs.getString("paired_host", "").isNullOrBlank() &&
            !linkSessionVault.load().isNullOrBlank() &&
            DesktopLinkSecurity.isCurrentSession(
                pairingPrefs.getInt("link_protocol_version", 0),
                pairingPrefs.getString("certificate_sha256", "").orEmpty(),
                pairingPrefs.getLong("session_expires_at_epoch_ms", 0L),
                System.currentTimeMillis(),
            )

    private fun hasRememberedDesktop(): Boolean = DesktopLinkSecurity.isRememberedDesktop(
        pairingPrefs.getInt("link_protocol_version", 0),
        pairingPrefs.getString("certificate_sha256", "").orEmpty(),
        pairingPrefs.getString("paired_host", "").orEmpty(),
    )

    private fun rememberedDesktopFingerprint(): String? = if (hasRememberedDesktop()) {
        DesktopLinkSecurity.normalizeFingerprint(
            pairingPrefs.getString("certificate_sha256", "").orEmpty(),
        )
    } else null

    private fun clearWirelessSession(forgetTrustedDesktop: Boolean) {
        if (forgetTrustedDesktop) telemetryHost = null
        telemetryToken = null
        if (forgetTrustedDesktop) telemetryCertificateSha256 = null
        telemetryRefreshInFlight = false
        telemetryRetryAttempt = 0
        linkSessionVault.clear()
        val editor = pairingPrefs.edit()
            .remove("paired")
            .remove("session_expires_at_epoch_ms")
        if (forgetTrustedDesktop) {
            editor
                .remove("desktop_trusted")
                .remove("paired_host")
                .remove("certificate_sha256")
                .remove("link_protocol_version")
        }
        editor.apply()
    }

    private fun desktopEndpoint(host: String, path: String): URL {
        require(host.length in 3..255 && host.none { it.isWhitespace() || it in "@/\\?#" }) {
            "Invalid desktop endpoint"
        }
        val endpoint = URL("https://$host$path")
        require(endpoint.protocol == "https" && endpoint.userInfo == null && endpoint.path == path)
        require(endpoint.port in 1..65535) { "Desktop endpoint must include a valid port" }
        val address = InetAddress.getByName(endpoint.host)
        val uniqueLocalIpv6 = address is Inet6Address &&
            ((address.address.first().toInt() and 0xFE) == 0xFC)
        require(
            address.isSiteLocalAddress || address.isLinkLocalAddress ||
                address.isLoopbackAddress || uniqueLocalIpv6
        ) { "Desktop endpoint must be on the local network" }
        return endpoint
    }

    private fun openDesktopConnection(
        host: String,
        path: String,
        certificateSha256: String,
    ): HttpsURLConnection = (desktopEndpoint(host, path).openConnection() as HttpsURLConnection).apply {
        instanceFollowRedirects = false
        setRequestProperty("Accept", "application/json")
        DesktopLinkSecurity.configure(this, certificateSha256)
    }

    override fun onDestroy() {
        supporterTick?.let(supporterHandler::removeCallbacks)
        supporterTick = null
        supporterMediaPlayer?.release()
        supporterMediaPlayer = null
        telemetryHost = null
        telemetryToken = null
        telemetryCertificateSha256 = null
        desktopTelemetryView = null
        telemetryRefreshInFlight = false
        linkAddressField = null
        linkFingerprintField = null
        linkSafetyLabel = null
        telemetryHandler.removeCallbacksAndMessages(null)
        memberHandler.removeCallbacksAndMessages(null)
        super.onDestroy()
    }

    private fun discoverPc(
        addressField: EditText,
        fingerprintField: EditText,
        safetyLabel: TextView,
    ) {
        if (linkDiscoveryInFlight) return
        linkDiscoveryInFlight = true
        Thread {
            try {
                DatagramSocket(45678).use { socket ->
                    socket.soTimeout = 1500
                    val buffer = ByteArray(512)
                    repeat(40) {
                        val packet = DatagramPacket(buffer, buffer.size)
                        try {
                            socket.receive(packet)
                        } catch (_: SocketTimeoutException) {
                            return@repeat
                        }
                        val message = JSONObject(String(packet.data, 0, packet.length))
                        val fingerprint = DesktopLinkSecurity.normalizeFingerprint(
                            message.optString("certificate_sha256"),
                        )
                        val expectedSafetyCode = fingerprint?.let(DesktopLinkSecurity::safetyCode)
                        val port = message.optInt("port")
                        val rememberedFingerprint = rememberedDesktopFingerprint()
                        if (
                            message.optString("service") == "ROMVERSE_COMPANION" &&
                            message.optString("scheme") == "https" &&
                            message.optInt("protocol_version") ==
                            DesktopLinkSecurity.PROTOCOL_VERSION &&
                            port in 1..65535 &&
                            fingerprint != null &&
                            DesktopLinkSecurity.acceptsDiscoveredIdentity(
                                rememberedFingerprint,
                                fingerprint,
                            ) &&
                            expectedSafetyCode != null &&
                            message.optString("safety_code") == expectedSafetyCode
                        ) {
                            val discoveredHost = packet.address.hostAddress.orEmpty()
                            val endpointHost = if (packet.address is Inet6Address) {
                                "[$discoveredHost]"
                            } else discoveredHost
                            val address = "$endpointHost:$port"
                            val currentToken = telemetryToken
                                ?: linkSessionVault.load()
                            val sessionActive = hasSecureWirelessSession() && currentToken != null
                            val proof = if (rememberedFingerprint != null && sessionActive) {
                                getTelemetrySummary(address, currentToken, fingerprint)
                            } else null
                            if (sessionActive && proof?.summary == null) {
                                return@repeat
                            }
                            val trustedEndpoint = DesktopLinkSecurity.trustedRediscoveredEndpoint(
                                DesktopLinkSecurity.PROTOCOL_VERSION,
                                rememberedFingerprint,
                                fingerprint,
                                address,
                                proof?.summary != null && !proof.unauthorized,
                            )
                            runOnUiThread {
                                addressField.setText(address)
                                fingerprintField.setText(fingerprint)
                                if (trustedEndpoint != null) {
                                    val previous = pairingPrefs.getString("paired_host", "").orEmpty()
                                    pairingPrefs.edit()
                                        .putString("paired_host", trustedEndpoint)
                                        .apply()
                                    telemetryHost = trustedEndpoint
                                    telemetryCertificateSha256 = fingerprint
                                    telemetryRetryAttempt = 0
                                    safetyLabel.text =
                                        "TRUSTED DESKTOP RECONNECTED  •  $expectedSafetyCode\n" +
                                        "The saved certificate and active approval both verified."
                                    proof?.let {
                                        desktopAscensionStatus = it.ascension
                                        desktopLiveConsoleStatus = it.liveConsole
                                        desktopDeviceDnaStatus = it.deviceDna
                                    }
                                    desktopTelemetryView?.text =
                                        "Trusted Desktop found at its new network address • syncing securely…"
                                    if (previous != trustedEndpoint) {
                                        logActivity("Trusted Desktop network address recovered")
                                    }
                                    desktopTelemetryView?.let { scheduleTelemetryRefresh(it, 0L) }
                                } else {
                                    safetyLabel.text = if (rememberedFingerprint != null) {
                                        "KNOWN DESKTOP IDENTITY FOUND  •  $expectedSafetyCode\n" +
                                            "Approval is not active; enter a new Link code to verify this address."
                                    } else {
                                        "LINK SAFETY CODE  •  $expectedSafetyCode\n" +
                                            "Compare this exact code with ROMVERSE Desktop."
                                    }
                                }
                            }
                            return@Thread
                        }
                    }
                }
            } catch (_: Exception) {
                // Manual PC address remains available when discovery is blocked by the network.
            } finally {
                runOnUiThread { linkDiscoveryInFlight = false }
            }
        }.start()
    }
}

private class SupporterPortalView(
    context: android.content.Context,
    iconResource: Int,
    private var motionEnabled: Boolean,
) : View(context) {
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG)
    private val mark = BitmapFactory.decodeResource(resources, iconResource)
    private val startedAt = SystemClock.uptimeMillis()
    private val density = resources.displayMetrics.density
    private val stars = List(72) { index ->
        floatArrayOf(
            ((index * 83 + 17) % 997) / 997f,
            ((index * 151 + 41) % 991) / 991f,
            0.65f + (index % 4) * 0.36f,
        )
    }

    fun setMotionEnabled(enabled: Boolean) {
        motionEnabled = enabled
        invalidate()
    }

    override fun onDraw(canvas: Canvas) {
        val progress = if (motionEnabled) {
            ((SystemClock.uptimeMillis() - startedAt) / 4400f).coerceIn(0f, 1f)
        } else 1f
        paint.style = Paint.Style.FILL
        paint.alpha = 255
        paint.shader = LinearGradient(
            0f,
            0f,
            width.toFloat(),
            height.toFloat(),
            intArrayOf("#010307".toColorInt(), "#040812".toColorInt(), "#060712".toColorInt()),
            null,
            Shader.TileMode.CLAMP,
        )
        canvas.drawRect(0f, 0f, width.toFloat(), height.toFloat(), paint)
        paint.shader = null

        val centerX = width * 0.5f
        val centerY = height * 0.205f
        val gather = (((progress - 0.03f) / 0.48f).coerceIn(0f, 1f) * 0.58f)
        stars.forEachIndexed { index, star ->
            val originX = star[0] * width
            val originY = star[1] * height
            val x = originX + (centerX - originX) * gather
            val y = originY + (centerY - originY) * gather
            val shimmer = 0.58f + 0.42f * sin(progress * 24f + index * 1.7f)
            paint.style = Paint.Style.FILL
            paint.color = Color.argb((112 * shimmer).roundToInt(), 165, 219, 255)
            canvas.drawCircle(x, y, star[2] * density * 0.52f, paint)
            if (progress in 0.18f..0.58f && index % 4 == 0) {
                paint.style = Paint.Style.STROKE
                paint.strokeWidth = density * 0.32f
                paint.color = Color.argb(52, 116, 103, 255)
                canvas.drawLine(originX, originY, x, y, paint)
            }
        }

        val opening = ((progress - 0.08f) / 0.34f).coerceIn(0f, 1f)
        val collapse = (1f - ((progress - 0.62f) / 0.18f).coerceIn(0f, 1f)).coerceIn(0f, 1f)
        val portalAlpha = opening * collapse
        val radius = density * (18f + 92f * opening)
        if (portalAlpha > 0f) {
            paint.style = Paint.Style.FILL
            paint.alpha = (255 * portalAlpha).roundToInt()
            paint.shader = RadialGradient(
                centerX,
                centerY,
                radius * 1.72f,
                intArrayOf(
                    Color.argb(235, 255, 255, 255),
                    Color.argb(205, 76, 220, 255),
                    Color.argb(150, 94, 93, 255),
                    Color.argb(82, 193, 62, 255),
                    Color.TRANSPARENT,
                ),
                floatArrayOf(0f, 0.12f, 0.34f, 0.61f, 1f),
                Shader.TileMode.CLAMP,
            )
            canvas.save()
            canvas.scale(1f, 0.43f, centerX, centerY)
            canvas.drawCircle(centerX, centerY, radius * 1.72f, paint)
            canvas.restore()
            paint.shader = null

            canvas.save()
            canvas.scale(1f, 0.38f, centerX, centerY)
            val colors = intArrayOf(
                "#D84CFF".toColorInt(),
                "#43DFFF".toColorInt(),
                "#776AFF".toColorInt(),
            )
            val scales = floatArrayOf(1.48f, 1.28f, 1.08f)
            for (index in colors.indices) {
                paint.style = Paint.Style.STROKE
                paint.strokeCap = Paint.Cap.ROUND
                paint.strokeWidth = density * (3.0f - index * 0.65f)
                paint.color = colors[index]
                paint.alpha = (235 * portalAlpha).roundToInt()
                val ringRadius = radius * scales[index]
                val ring = RectF(
                    centerX - ringRadius,
                    centerY - ringRadius,
                    centerX + ringRadius,
                    centerY + ringRadius,
                )
                val direction = if (index % 2 == 0) 1f else -1f
                canvas.drawArc(ring, progress * 920f * direction + index * 70f, 224f - index * 24f, false, paint)
            }
            canvas.restore()

            paint.style = Paint.Style.FILL
            paint.alpha = (255 * portalAlpha).roundToInt()
            paint.shader = RadialGradient(
                centerX,
                centerY,
                radius * 0.72f,
                intArrayOf(Color.BLACK, "#010209".toColorInt(), "#160B42".toColorInt()),
                floatArrayOf(0f, 0.75f, 1f),
                Shader.TileMode.CLAMP,
            )
            canvas.drawCircle(centerX, centerY, radius * 0.67f, paint)
            paint.shader = null

            paint.style = Paint.Style.STROKE
            paint.strokeWidth = density * 0.48f
            paint.color = Color.argb((160 * portalAlpha).roundToInt(), 220, 236, 255)
            for (index in 0 until 14) {
                val angle = progress * 8f + index * Math.PI.toFloat() / 7f
                val innerX = centerX + cos(angle) * radius * 0.82f
                val innerY = centerY + sin(angle) * radius * 0.33f
                val outerX = centerX + cos(angle) * radius * (1.18f + (index % 3) * 0.12f)
                val outerY = centerY + sin(angle) * radius * (0.50f + (index % 2) * 0.08f)
                canvas.drawLine(innerX, innerY, outerX, outerY, paint)
            }
        }

        val pulse = (1f - abs(progress - 0.66f) / 0.11f).coerceIn(0f, 1f)
        if (pulse > 0f) {
            val pulseRadius = radius * (0.48f + pulse * 1.72f)
            paint.style = Paint.Style.FILL
            paint.alpha = 255
            paint.shader = RadialGradient(
                centerX,
                centerY,
                pulseRadius,
                intArrayOf(
                    Color.argb((245 * pulse).roundToInt(), 255, 255, 255),
                    Color.argb((210 * pulse).roundToInt(), 82, 225, 255),
                    Color.argb((95 * pulse).roundToInt(), 177, 66, 255),
                    Color.TRANSPARENT,
                ),
                floatArrayOf(0f, 0.2f, 0.58f, 1f),
                Shader.TileMode.CLAMP,
            )
            canvas.drawCircle(centerX, centerY, pulseRadius, paint)
            paint.shader = null
        }

        val reveal = ((progress - 0.69f) / 0.22f).coerceIn(0f, 1f)
        if (reveal > 0f && mark != null) {
            val eased = 1f - (1f - reveal) * (1f - reveal) * (1f - reveal)
            val iconSize = density * (84f + 92f * eased)
            paint.style = Paint.Style.FILL
            paint.shader = RadialGradient(
                centerX,
                centerY,
                iconSize * 0.76f,
                intArrayOf(Color.argb((105 * reveal).roundToInt(), 112, 82, 255), Color.TRANSPARENT),
                null,
                Shader.TileMode.CLAMP,
            )
            paint.alpha = 255
            canvas.drawCircle(centerX, centerY, iconSize * 0.78f, paint)
            paint.shader = null
            paint.alpha = (255 * reveal).roundToInt()
            canvas.drawBitmap(
                mark,
                null,
                RectF(
                    centerX - iconSize / 2f,
                    centerY - iconSize / 2f,
                    centerX + iconSize / 2f,
                    centerY + iconSize / 2f,
                ),
                paint,
            )
            paint.alpha = 255
        }

        if (motionEnabled && progress < 1f) postInvalidateOnAnimation()
    }
}

private enum class NavKind(val label: String) {
    COMMAND("Home"),
    LINK("Link"),
    CONSOLE("Console"),
    QUANTUM("Vitalis"),
    RECOVERY("Lifeline"),
    DEVICE_DNA("Device DNA"),
    ASCENSION("Ascension"),
    APPS("Launchpad"),
    MEMBERS("Members"),
    GALAXY("Galaxy"),
    SETTINGS("Settings"),
    ABOUT("About"),
    MORE("More"),
}

/** Crisp vector navigation icons that remain legible on narrow phone sidebars. */
private class RomverseNavButton(
    context: android.content.Context,
    private val kind: NavKind,
    displayMode: CompanionDisplayMode,
) : View(context) {
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG)
    private val density = resources.displayMetrics.density
    private val palette = CompanionDisplayPolicy.palette(displayMode)
    var activeSelection: Boolean = false
        set(value) {
            field = value
            isSelected = value
            invalidate()
        }

    init {
        isClickable = true
        isFocusable = true
        contentDescription = kind.label
        importantForAccessibility = IMPORTANT_FOR_ACCESSIBILITY_YES
    }

    override fun drawableStateChanged() {
        super.drawableStateChanged()
        invalidate()
    }

    override fun onDraw(canvas: Canvas) {
        val bounds = RectF(1f, 1f, width - 1f, height - 1f)
        paint.style = Paint.Style.FILL
        paint.color = when {
            activeSelection -> "#28123F".toColorInt()
            isPressed -> palette.navigationPressed.toColorInt()
            else -> palette.navigationIdle.toColorInt()
        }
        canvas.drawRoundRect(bounds, 10f * density, 10f * density, paint)
        paint.style = Paint.Style.STROKE
        paint.strokeWidth = if (activeSelection) 1.3f * density else 0.8f * density
        paint.color = if (activeSelection) "#B45CFF".toColorInt() else "#263650".toColorInt()
        canvas.drawRoundRect(bounds, 10f * density, 10f * density, paint)

        val iconColor = if (activeSelection) "#D98CFF".toColorInt() else "#6DD9F5".toColorInt()
        val centerX = width * 0.5f
        val centerY = height * 0.35f
        val radius = minOf(width, height) * 0.17f
        paint.color = iconColor
        paint.strokeWidth = 1.8f * density
        paint.strokeCap = Paint.Cap.ROUND
        paint.strokeJoin = Paint.Join.ROUND
        paint.style = Paint.Style.STROKE
        drawIcon(canvas, centerX, centerY, radius)

        paint.style = Paint.Style.FILL
        paint.textAlign = Paint.Align.CENTER
        paint.typeface = android.graphics.Typeface.DEFAULT_BOLD
        paint.textSize = 9.2f * density
        paint.color = if (activeSelection) Color.WHITE else "#B5C0D6".toColorInt()
        canvas.drawText(kind.label, centerX, height * 0.82f, paint)
    }

    private fun drawIcon(canvas: Canvas, x: Float, y: Float, r: Float) {
        when (kind) {
            NavKind.COMMAND -> {
                val cell = r * 0.72f
                for (row in 0..1) for (column in 0..1) {
                    val left = x + (column - 1) * cell + r * 0.12f
                    val top = y + (row - 1) * cell + r * 0.12f
                    canvas.drawRoundRect(
                        RectF(left, top, left + cell * 0.65f, top + cell * 0.65f),
                        r * 0.12f,
                        r * 0.12f,
                        paint,
                    )
                }
            }
            NavKind.LINK -> {
                canvas.drawCircle(x - r * 0.5f, y + r * 0.38f, r * 0.32f, paint)
                canvas.drawCircle(x + r * 0.5f, y - r * 0.38f, r * 0.32f, paint)
                canvas.drawLine(x - r * 0.28f, y + r * 0.14f, x + r * 0.28f, y - r * 0.14f, paint)
                canvas.drawLine(x - r * 0.08f, y + r * 0.34f, x + r * 0.48f, y + r * 0.06f, paint)
            }
            NavKind.CONSOLE -> {
                canvas.drawRoundRect(
                    RectF(x - r, y - r * 0.8f, x + r, y + r * 0.8f),
                    r * 0.16f,
                    r * 0.16f,
                    paint,
                )
                canvas.drawLine(x - r * 0.62f, y - r * 0.3f, x - r * 0.18f, y, paint)
                canvas.drawLine(x - r * 0.18f, y, x - r * 0.62f, y + r * 0.3f, paint)
                canvas.drawLine(x, y + r * 0.34f, x + r * 0.58f, y + r * 0.34f, paint)
            }
            NavKind.QUANTUM -> {
                for (offset in listOf(-0.65f, 0f, 0.65f)) {
                    canvas.drawLine(x - r, y + r * offset, x + r, y + r * offset, paint)
                }
                canvas.drawCircle(x - r * 0.35f, y - r * 0.65f, r * 0.18f, paint)
                canvas.drawCircle(x + r * 0.42f, y, r * 0.18f, paint)
                canvas.drawCircle(x - r * 0.1f, y + r * 0.65f, r * 0.18f, paint)
            }
            NavKind.RECOVERY -> {
                val shield = android.graphics.Path().apply {
                    moveTo(x, y - r)
                    lineTo(x + r * 0.82f, y - r * 0.55f)
                    lineTo(x + r * 0.65f, y + r * 0.48f)
                    lineTo(x, y + r)
                    lineTo(x - r * 0.65f, y + r * 0.48f)
                    lineTo(x - r * 0.82f, y - r * 0.55f)
                    close()
                }
                canvas.drawPath(shield, paint)
                canvas.drawLine(x - r * 0.38f, y, x + r * 0.38f, y, paint)
                canvas.drawLine(x, y - r * 0.38f, x, y + r * 0.38f, paint)
            }
            NavKind.DEVICE_DNA -> {
                val left = android.graphics.Path().apply {
                    moveTo(x - r * 0.62f, y - r)
                    cubicTo(
                        x + r * 0.72f,
                        y - r * 0.56f,
                        x - r * 0.72f,
                        y + r * 0.56f,
                        x + r * 0.62f,
                        y + r,
                    )
                }
                val right = android.graphics.Path().apply {
                    moveTo(x + r * 0.62f, y - r)
                    cubicTo(
                        x - r * 0.72f,
                        y - r * 0.56f,
                        x + r * 0.72f,
                        y + r * 0.56f,
                        x - r * 0.62f,
                        y + r,
                    )
                }
                canvas.drawPath(left, paint)
                canvas.drawPath(right, paint)
                for (offset in listOf(-0.62f, 0f, 0.62f)) {
                    canvas.drawLine(
                        x - r * 0.45f,
                        y + r * offset,
                        x + r * 0.45f,
                        y + r * offset,
                        paint,
                    )
                }
            }
            NavKind.ASCENSION -> {
                val arrow = android.graphics.Path().apply {
                    moveTo(x, y - r)
                    lineTo(x + r * 0.72f, y - r * 0.18f)
                    lineTo(x + r * 0.3f, y - r * 0.18f)
                    lineTo(x + r * 0.3f, y + r * 0.72f)
                    lineTo(x - r * 0.3f, y + r * 0.72f)
                    lineTo(x - r * 0.3f, y - r * 0.18f)
                    lineTo(x - r * 0.72f, y - r * 0.18f)
                    close()
                }
                canvas.drawPath(arrow, paint)
                canvas.drawArc(
                    RectF(x - r, y + r * 0.38f, x + r, y + r * 1.08f),
                    18f,
                    144f,
                    false,
                    paint,
                )
            }
            NavKind.APPS -> {
                canvas.drawRoundRect(
                    RectF(x - r * 0.78f, y - r, x + r * 0.78f, y + r),
                    r * 0.16f,
                    r * 0.16f,
                    paint,
                )
                canvas.drawLine(x - r * 0.78f, y - r * 0.35f, x + r * 0.78f, y - r * 0.35f, paint)
                canvas.drawLine(x - r * 0.36f, y - r, x, y - r * 0.35f, paint)
                canvas.drawLine(x + r * 0.36f, y - r, x, y - r * 0.35f, paint)
                canvas.drawLine(x - r * 0.28f, y + r * 0.34f, x - r * 0.02f, y + r * 0.6f, paint)
                canvas.drawLine(x - r * 0.02f, y + r * 0.6f, x + r * 0.42f, y + r * 0.08f, paint)
            }
            NavKind.GALAXY -> {
                canvas.drawCircle(x, y, r * 0.28f, paint)
                canvas.save()
                canvas.rotate(-25f, x, y)
                canvas.drawOval(RectF(x - r, y - r * 0.42f, x + r, y + r * 0.42f), paint)
                canvas.restore()
                paint.style = Paint.Style.FILL
                canvas.drawCircle(x + r * 0.74f, y - r * 0.35f, r * 0.15f, paint)
                paint.style = Paint.Style.STROKE
            }
            NavKind.MEMBERS -> {
                canvas.drawCircle(x, y - r * 0.42f, r * 0.38f, paint)
                canvas.drawArc(
                    RectF(x - r * 0.82f, y + r * 0.02f, x + r * 0.82f, y + r * 1.18f),
                    190f,
                    160f,
                    false,
                    paint,
                )
                canvas.drawLine(x + r * 0.45f, y - r * 0.42f, x + r * 0.68f, y - r * 0.2f, paint)
                canvas.drawLine(x + r * 0.68f, y - r * 0.2f, x + r, y - r * 0.62f, paint)
            }
            NavKind.SETTINGS -> {
                canvas.drawCircle(x, y, r * 0.34f, paint)
                for (index in 0 until 8) {
                    val angle = Math.toRadians(index * 45.0)
                    canvas.drawLine(
                        x + cos(angle).toFloat() * r * 0.56f,
                        y + sin(angle).toFloat() * r * 0.56f,
                        x + cos(angle).toFloat() * r,
                        y + sin(angle).toFloat() * r,
                        paint,
                    )
                }
            }
            NavKind.ABOUT -> {
                canvas.drawCircle(x, y, r, paint)
                canvas.drawCircle(x, y - r * 0.43f, r * 0.08f, paint)
                canvas.drawLine(x, y - r * 0.08f, x, y + r * 0.52f, paint)
            }
            NavKind.MORE -> {
                paint.style = Paint.Style.FILL
                for (offset in listOf(-0.7f, 0f, 0.7f)) {
                    canvas.drawCircle(x + r * offset, y, r * 0.16f, paint)
                }
                paint.style = Paint.Style.STROKE
            }
        }
    }
}

private class ResourceHistoryView(
    context: android.content.Context,
    battery: List<Float>,
    storage: List<Float>,
    ram: List<Float>,
) : View(context) {
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG)
    private var batterySeries = battery
    private var storageSeries = storage
    private var ramSeries = ram

    fun setSeries(battery: List<Float>, storage: List<Float>, ram: List<Float>) {
        batterySeries = battery
        storageSeries = storage
        ramSeries = ram
        invalidate()
    }

    override fun onDraw(canvas: Canvas) {
        val left = 8f
        val right = width - 8f
        val top = 8f
        val bottom = height - 8f
        paint.color = "#26375F".toColorInt()
        paint.strokeWidth = 1f
        for (level in 0..4) {
            val y = top + (bottom - top) * level / 4f
            canvas.drawLine(left, y, right, y, paint)
        }
        drawSeries(canvas, batterySeries, "#28E7F5".toColorInt(), left, right, top, bottom)
        drawSeries(canvas, storageSeries, "#B45CFF".toColorInt(), left, right, top, bottom)
        drawSeries(canvas, ramSeries, "#72FFB2".toColorInt(), left, right, top, bottom)
    }

    private fun drawSeries(
        canvas: Canvas,
        values: List<Float>,
        color: Int,
        left: Float,
        right: Float,
        top: Float,
        bottom: Float,
    ) {
        if (values.isEmpty()) return
        paint.color = color
        paint.strokeWidth = 4f
        paint.style = Paint.Style.STROKE
        val path = android.graphics.Path()
        values.forEachIndexed { index, value ->
            val x = if (values.size == 1) left else left + (right - left) * index / (values.size - 1f)
            val y = bottom - (bottom - top) * value.coerceIn(0f, 100f) / 100f
            if (index == 0) path.moveTo(x, y) else path.lineTo(x, y)
        }
        canvas.drawPath(path, paint)
        paint.style = Paint.Style.FILL
    }
}

private data class GaugeMetric(
    val label: String,
    val percent: Int?,
    val color: Int,
)

/** Compact phone-native gauges backed exclusively by the live Android snapshot. */
private class ResourceGaugeStripView(
    context: android.content.Context,
    private val metrics: List<GaugeMetric>,
) : View(context) {
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG)
    private val density = resources.displayMetrics.density
    private val startedAt = SystemClock.uptimeMillis()

    init {
        require(metrics.isNotEmpty() && metrics.size <= 4)
        contentDescription = metrics.joinToString("; ") {
            "${it.label} ${it.percent?.let { value -> "$value%" } ?: "unconfirmed"}"
        }
        importantForAccessibility = IMPORTANT_FOR_ACCESSIBILITY_YES
    }

    override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
        val desiredHeight = (154f * density).roundToInt()
        setMeasuredDimension(
            resolveSize(suggestedMinimumWidth, widthMeasureSpec),
            resolveSize(desiredHeight, heightMeasureSpec),
        )
    }

    override fun onDraw(canvas: Canvas) {
        val animated = android.animation.ValueAnimator.areAnimatorsEnabled()
        val reveal = if (animated) {
            ((SystemClock.uptimeMillis() - startedAt) / 650f).coerceIn(0f, 1f)
        } else 1f
        val columnWidth = width.toFloat() / metrics.size
        val radius = minOf(columnWidth * 0.31f, height * 0.28f)
        val centerY = height * 0.44f
        val stroke = (7f * density).coerceAtMost(radius * 0.32f)
        metrics.forEachIndexed { index, metric ->
            val centerX = columnWidth * (index + 0.5f)
            val ring = RectF(
                centerX - radius,
                centerY - radius,
                centerX + radius,
                centerY + radius,
            )
            paint.style = Paint.Style.STROKE
            paint.strokeCap = Paint.Cap.ROUND
            paint.strokeWidth = stroke
            paint.color = "#182038".toColorInt()
            canvas.drawArc(ring, -90f, 360f, false, paint)
            metric.percent?.let { percent ->
                paint.color = metric.color
                paint.alpha = 70
                paint.strokeWidth = stroke * 1.7f
                canvas.drawArc(
                    ring,
                    -90f,
                    percent.coerceIn(0, 100) * 3.6f * reveal,
                    false,
                    paint,
                )
                paint.alpha = 255
                paint.strokeWidth = stroke
                canvas.drawArc(
                    ring,
                    -90f,
                    percent.coerceIn(0, 100) * 3.6f * reveal,
                    false,
                    paint,
                )
            }
            paint.style = Paint.Style.FILL
            paint.textAlign = Paint.Align.CENTER
            paint.typeface = android.graphics.Typeface.DEFAULT_BOLD
            paint.textSize = (17f * density).coerceAtMost(radius * 0.72f)
            paint.color = Color.WHITE
            canvas.drawText(
                metric.percent?.let { "${(it.coerceIn(0, 100) * reveal).roundToInt()}%" }
                    ?: "N/A",
                centerX,
                centerY + paint.textSize * 0.34f,
                paint,
            )
            paint.textSize = (9.5f * density).coerceAtMost(columnWidth * 0.14f)
            paint.color = metric.color
            canvas.drawText(metric.label, centerX, centerY + radius + 24f * density, paint)
        }
        paint.alpha = 255
        if (reveal < 1f && animated) postInvalidateOnAnimation()
    }
}

private class StarfieldView(
    context: android.content.Context,
    private val oledMode: Boolean,
) : View(context) {
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG)
    private val random = java.util.Random()
    private val stars = List(48) { index ->
        floatArrayOf(
            ((index * 47 + 11) % 101) / 101f,
            ((index * 83 + 19) % 103) / 103f,
            0.75f + index % 3,
        )
    }
    private val startedAt = SystemClock.uptimeMillis()
    private var shootingStartedAt = -1L
    private var shootingY = 0.25f
    private var nextShootingAt = startedAt + randomDelay(12_000L, 28_000L)
    private var battleStartedAt = -1L
    private var nextBattleAt = startedAt + randomDelay(75_000L, 135_000L)
    private var active = true
    private var motionEnabled = true

    fun setMotionEnabled(enabled: Boolean) {
        motionEnabled = enabled
        if (!enabled) {
            shootingStartedAt = -1L
            battleStartedAt = -1L
        }
        invalidate()
    }

    override fun onDraw(canvas: Canvas) {
        val now = SystemClock.uptimeMillis()
        val palette = CompanionDisplayPolicy.palette(
            if (oledMode) CompanionDisplayMode.OLED else CompanionDisplayMode.COSMIC,
        )
        val gradient = LinearGradient(
            0f,
            0f,
            width.toFloat(),
            height.toFloat(),
            palette.cosmicGradient.map(String::toColorInt).toIntArray(),
            null,
            Shader.TileMode.CLAMP,
        )
        paint.shader = gradient
        canvas.drawRect(0f, 0f, width.toFloat(), height.toFloat(), paint)
        paint.shader = null
        if (palette.ambientNebula) {
            paint.alpha = 100
            paint.shader = RadialGradient(
                width * 0.78f,
                height * 0.15f,
                width * 0.72f,
                intArrayOf("#182351".toColorInt(), "#080B1A".toColorInt(), Color.TRANSPARENT),
                null,
                Shader.TileMode.CLAMP,
            )
            canvas.drawCircle(width * 0.78f, height * 0.15f, width * 0.72f, paint)
            paint.shader = null
        }
        paint.alpha = 255
        val drift = if (motionEnabled) {
            ((now - startedAt) * 0.0025f) % width.coerceAtLeast(1)
        } else {
            0f
        }
        stars.forEach { star ->
            val x = ((star[0] * width) + drift * star[2]) % width
            val y = star[1] * height
            val pulse = if (motionEnabled) {
                0.65f + 0.35f * kotlin.math.sin(now / 850f + star[0] * 13f)
            } else {
                1f
            }
            paint.alpha = (70 + pulse * 90).roundToInt().coerceIn(0, 160)
            paint.color = if (star[2] > 2f) "#56D8F2".toColorInt() else "#8E7AC8".toColorInt()
            canvas.drawCircle(x, y, star[2], paint)
        }
        paint.alpha = 255

        val animationsEnabled = android.animation.ValueAnimator.areAnimatorsEnabled()
        if (motionEnabled && animationsEnabled) {
            drawShootingStar(canvas, now)
            drawRareEncounter(canvas, now)
        }
        if (active && motionEnabled && isShown) {
            val eventActive = shootingStartedAt >= 0L || battleStartedAt >= 0L
            postInvalidateDelayed(if (eventActive) 33L else 100L)
        }
    }

    private fun drawShootingStar(canvas: Canvas, now: Long) {
        if (battleStartedAt >= 0L) return
        if (shootingStartedAt < 0L && now >= nextShootingAt) {
            shootingStartedAt = now
            shootingY = 0.12f + random.nextFloat() * 0.48f
        }
        if (shootingStartedAt < 0L) return
        val elapsed = now - shootingStartedAt
        val duration = 1_650L
        if (elapsed > duration) {
            shootingStartedAt = -1L
            nextShootingAt = now + randomDelay(22_000L, 52_000L)
            return
        }
        val progress = elapsed / duration.toFloat()
        val x = width * (-0.16f + progress * 1.32f)
        val y = height * (shootingY + progress * 0.12f)
        val tailX = x - width * 0.16f
        val tailY = y - height * 0.045f
        paint.style = Paint.Style.STROKE
        paint.strokeCap = Paint.Cap.ROUND
        paint.strokeWidth = 2.2f * resources.displayMetrics.density
        paint.shader = LinearGradient(
            tailX,
            tailY,
            x,
            y,
            intArrayOf(Color.TRANSPARENT, "#8B5CFF".toColorInt(), "#72F3FF".toColorInt()),
            null,
            Shader.TileMode.CLAMP,
        )
        canvas.drawLine(tailX, tailY, x, y, paint)
        paint.shader = null
        paint.style = Paint.Style.FILL
        paint.color = Color.WHITE
        paint.alpha = 210
        canvas.drawCircle(x, y, 1.8f * resources.displayMetrics.density, paint)
        paint.alpha = 255
    }

    private fun drawRareEncounter(canvas: Canvas, now: Long) {
        if (battleStartedAt < 0L && now >= nextBattleAt) battleStartedAt = now
        if (battleStartedAt < 0L) return
        val elapsed = now - battleStartedAt
        val duration = 10_500L
        if (elapsed > duration) {
            battleStartedAt = -1L
            nextBattleAt = now + randomDelay(150_000L, 300_000L)
            return
        }
        val progress = elapsed / duration.toFloat()
        val wave = kotlin.math.sin(progress * Math.PI.toFloat() * 2f)
        val firstX = width * (-0.12f + progress * 1.24f)
        val secondX = width * (1.12f - progress * 1.24f)
        val firstY = height * (0.24f + wave * 0.055f)
        val secondY = height * (0.40f - wave * 0.055f)
        val shipScale = (4.2f * resources.displayMetrics.density).coerceAtMost(width * 0.018f)
        drawShip(canvas, firstX, firstY, shipScale, "#35E7F5".toColorInt(), false)
        drawShip(canvas, secondX, secondY, shipScale, "#B45CFF".toColorInt(), true)

        if (elapsed in 2_100L..8_700L && (elapsed / 520L) % 3L != 2L) {
            val fromFirst = (elapsed / 520L) % 2L == 0L
            val pulse = (elapsed % 520L) / 520f
            val fromX = if (fromFirst) firstX else secondX
            val fromY = if (fromFirst) firstY else secondY
            val toX = if (fromFirst) secondX else firstX
            val toY = if (fromFirst) secondY else firstY
            val pulseX = fromX + (toX - fromX) * pulse
            val pulseY = fromY + (toY - fromY) * pulse
            paint.style = Paint.Style.STROKE
            paint.strokeWidth = resources.displayMetrics.density
            paint.color = if (fromFirst) "#35E7F5".toColorInt() else "#C465FF".toColorInt()
            paint.alpha = 58
            canvas.drawLine(fromX, fromY, toX, toY, paint)
            paint.style = Paint.Style.FILL
            paint.alpha = 150
            canvas.drawCircle(pulseX, pulseY, 1.6f * resources.displayMetrics.density, paint)
            paint.alpha = 255
        }
    }

    private fun drawShip(
        canvas: Canvas,
        x: Float,
        y: Float,
        scale: Float,
        color: Int,
        facingLeft: Boolean,
    ) {
        canvas.save()
        canvas.translate(x, y)
        if (facingLeft) canvas.scale(-1f, 1f)
        val path = android.graphics.Path().apply {
            moveTo(3.8f * scale, 0f)
            lineTo(-2.8f * scale, -1.8f * scale)
            lineTo(-1.4f * scale, 0f)
            lineTo(-2.8f * scale, 1.8f * scale)
            close()
        }
        paint.style = Paint.Style.STROKE
        paint.strokeWidth = 1.2f * resources.displayMetrics.density
        paint.color = color
        paint.alpha = 115
        canvas.drawPath(path, paint)
        paint.style = Paint.Style.FILL
        paint.alpha = 45
        canvas.drawPath(path, paint)
        paint.alpha = 70
        canvas.drawCircle(-2.9f * scale, 0f, 0.65f * scale, paint)
        paint.alpha = 255
        canvas.restore()
    }

    private fun randomDelay(minimum: Long, maximum: Long): Long =
        minimum + (random.nextDouble() * (maximum - minimum)).toLong()

    override fun onAttachedToWindow() {
        super.onAttachedToWindow()
        active = true
        invalidate()
    }

    override fun onDetachedFromWindow() {
        active = false
        super.onDetachedFromWindow()
    }

    override fun onWindowVisibilityChanged(visibility: Int) {
        super.onWindowVisibilityChanged(visibility)
        active = visibility == VISIBLE
        if (active) invalidate()
    }
}
