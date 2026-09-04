from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from romverse.device.catalog import GooglePlayDeviceCatalog
from romverse.intelligence.synapse import (
    SynapseKnowledge,
    SynapseKnowledgeState,
    SynapseStore,
    SynapseStoreError,
)
from romverse.knowledge.archives import (
    ALL_CATEGORIES,
    CATEGORIES,
    ArchiveArticle,
    build_catalog,
    catalog_metrics,
    search_catalog,
    source_lane,
)
from romverse.knowledge.resolution_memory import (
    ArchivesResolutionMemory,
    ArticleResolutionMemory,
)
from romverse.ui.vocabulary import FEATURES, feature

LEGACY_GUIDES = (
    (
        "Device Engine",
        "Connect a phone with USB debugging enabled, accept the RSA prompt, then run Scan now. Only read-only probes are used in v0.1.",
    ),
    (
        "ADB needs attention",
        "Install Android SDK Platform Tools, confirm adb is on PATH, reconnect the phone, and authorize the computer on the device. ROMVERSE never changes device state during scans.",
    ),
    (
        "Guardian safety",
        "Guardian is deny-by-default. Read-only probes are allowlisted; privileged, state-changing, and destructive operations require explicit policy, approval, rollback, and verification.",
    ),
    (
        "Time Machine",
        "Create device recovery-readiness plans before risky work. For ROM Studio projects, Time Machine can verify and restore isolated local working-baseline snapshots after typed digest-bound approval. It preserves the current baseline first, verifies the result, records a receipt, and never targets phone partitions.",
    ),
    (
        "App Launchpad",
        "Choose an APK to generate a preflight receipt. The receipt records a redacted device identity, plan digest, risk, and approval requirement. Installation is available only after Guardian inspection, exact-plan approval, immediate revalidation, and Android's own confirmation.",
    ),
    (
        "ROM Studio",
        "Import an original ROM, verify its hash, create a working copy, inspect its structure, extract a tree, and create a build plan before any recipe is considered.",
    ),
    (
        "Which firmware source do I have?",
        "Start in ROM Studio and choose the firmware file exactly as downloaded. Genesis Sequence fingerprints the protected source before extraction. A payload.bin or OTA ZIP follows the verified payload route; a fastboot/factory image archive follows the image-set route; a raw partition image follows bounded image inspection. ROMVERSE must detect the format from bytes and structure, not from a renamed extension. If required tools are missing, Forge Arsenal installs and verifies them before the stage retries. The original source is never modified in place.",
    ),
    (
        "Recipes and ROM DNA",
        "Recipes are previewed before execution. ROM DNA binds the project, device pack, original hash, working tree, and recipe digest so provenance changes are detectable.",
    ),
    (
        "Privacy",
        "Device serials are masked in the UI and redacted in logs. Guardian records operation metadata and outcomes, never command output or private device contents.",
    ),
    (
        "Diagnostics",
        "Run a read-only System Scan before interpreting symptoms. Findings are evidence-based and can be saved to Health Timeline for comparison across scans.",
    ),
    (
        "Recovery Bay",
        "Repair workflows begin with assessment and a Guardian preflight. Never skip backup readiness, device identity verification, or rollback planning.",
    ),
    (
        "Device Atlas",
        "Device Atlas provides model-specific compatibility profiles through signed Device Packs. Match manufacturer, model, codename, and Android generation before using a ROM recipe.",
    ),
    (
        "Windows setup",
        "Install Android SDK Platform Tools and the correct OEM USB driver. Confirm adb devices lists the phone as authorized, then restart ROMVERSE if the tool was installed while it was open.",
    ),
    (
        "Linux setup",
        "Install Platform Tools through your distribution, add udev rules for the phone vendor, reconnect the USB cable, and verify adb devices shows an authorized state.",
    ),
    (
        "Performance",
        "ROMVERSE keeps device probes off the UI thread. If scans feel slow, check the USB cable, hub, ADB responsiveness, and scan interval before repeating operations.",
    ),
    (
        "Logs and history",
        "Health history stores small metric samples locally. Guardian audit records are append-only and hash-linked; a broken chain blocks further gateway execution until reviewed.",
    ),
    (
        "Recovery checklist",
        "Before any future state-changing work: identify the exact device, verify the original hash, confirm a tested backup, record a rollback point, review the manifest, and approve only the intended scope.",
    ),
    (
        "USB authorization",
        "A phone marked unauthorized is waiting for its computer-debugging approval. Unlock the phone, accept the RSA fingerprint prompt, keep the cable connected, and scan again.",
    ),
    (
        "Battery and storage",
        "Low battery or nearly full /data storage increases recovery risk. Treat the observed thresholds as readiness signals, not guarantees; charge and make space before future changes.",
    ),
    (
        "Verified Boot",
        "A green Verified Boot state indicates the device reports a trusted verified chain. Unknown or orange states should be reviewed before trusting firmware provenance.",
    ),
    (
        "Root state",
        "Root detection is evidence only. ROMVERSE does not assume root access, request elevated shells, or use root to bypass Guardian policy.",
    ),
    (
        "Ascension Protocol beginner journey",
        "Ascension prepares an optional rooted ROM input through nine evidence-backed stages. "
        "Ascension stage 1 resolves the exact firmware, phone, rollback, tools and source image. "
        "Ascension stage 2 verifies the official Magisk or supported KernelSU manager and its "
        "published identity. Ascension stage 3 creates an isolated, source-bound patch capsule. "
        "Ascension stage 4 presents Guardian review before any approved app install or file copy. "
        "Ascension stage 5 guides the user through the official manager's image-patch step and "
        "verifies the returned output. Ascension stage 6 integrates only that verified image into "
        "the isolated ROM tree with rollback. Ascension stage 7 seals the exact rooted build input. "
        "Ascension stage 8 binds the output to fresh Device DNA, partition, slot, backup and "
        "recovery evidence. Ascension stage 9 compiles the final Guardian review. Preparation never "
        "silently unlocks, roots, wipes, flashes, or relocks a phone; bootloader relocking is always "
        "prohibited, and every device-changing action requires its own exact informed approval.",
    ),
    (
        "ROM inspection",
        "Inspection identifies archive structure and evidence without modifying the protected original. If extraction reports no content, confirm the source format and inspect the generated report before retrying.",
    ),
    (
        "Build plans",
        "A build plan binds the working tree hash to a project and device pack. Re-verify the tree after changes; a mismatch means the plan must be regenerated.",
    ),
    (
        "Verified HyperOS rebuild pattern",
        "The Xiaomi 17 Pro Max (popsicle) OS4.0.0.25.XPBCNXM workflow succeeded by preserving a verified stock base and existing Google framework, changing only product, retaining ownership, modes, SELinux contexts/xattrs, EROFS UUID/features and AVB topology, then expanding and unpacking the rebuilt sparse super image and byte-comparing all nine slot-A logical partitions. The exact package clean-flashed and reached a user-confirmed working Android Auto/Gboard result on one real phone. This is strong model/build/package-scoped evidence, not a guarantee for every unit or permission to flash another target.",
    ),
    (
        "Dynamic partition and AVB validation",
        "Before accepting a rebuilt image, record original logical partition groups, physical super size, metadata slots, A/B slot layout, filesystem size, AVB algorithm, salt, root digest and descriptor chain. After lpmake, convert sparse output when required, inspect it with LP Dump, unpack it with LP Unpack, and compare unchanged partitions byte-for-byte with their protected originals. A matching hash proves file identity only; it does not replace a tested recovery route or Guardian approval.",
    ),
    (
        "AVB policy: reference-only",
        "The successful popsicle OS4.0.0.20 workflow preserved Xiaomi's signed top-level vbmeta and used a descriptor-correct unsigned vbmeta_system through a bootloader that explicitly reported unlocked and critical-unlocked. ROMVERSE can recognize that topology, but it cannot authorize OS4.0.0.23 or another build from historical evidence. The exact firmware still needs its own signed physical validation and recovery attestation.",
    ),
    (
        "Adding another phone to Device Atlas",
        "A phone becomes build-capable only after ROMVERSE has exact manufacturer, model, codename, region/carrier and firmware identifiers; authoritative source provenance and hashes; partition, filesystem, slot and AVB contracts; verified tool requirements; known recovery artifacts and failure codes; and deterministic local fixtures. Flash authority additionally requires signed physical recovery and first-boot attestations for that exact contract. Similar names never inherit compatibility.",
    ),
    (
        "Privileged Android Auto integration",
        "The field-validated popsicle OS4.0.0.25 workflow treated Android Auto as a complete privileged system integration, not a copied APK. It preserved the base Google framework, verified the Google signer, added the privileged stub and reviewed permission XML, used a minimal static overlay for the projection role and notification-listener allowlist, resolved the exact build's CarWith conflict, retained filesystem metadata and updated only product's AVB descriptor before a full super round-trip. A visible app icon or successful boot does not prove projection: verify the installed system role, permissions, overlay, dependencies and a real car connection separately.",
    ),
    (
        "First-boot evidence after a ROM change",
        "A moving boot animation may reflect data initialization and app optimization, but it is not proof of success. Boot Observatory records read-only boot-completion, device-uptime, active-slot and build-identity samples, flags uptime resets, and requires a consistent observation window before reporting stability. Stability alone is not verified first boot without a matching Guardian flash receipt. For the proven HyperOS workflow, setup appearance, one clean reboot, Wi-Fi, mobile network, calls, messaging, cameras, audio, fingerprint, Bluetooth, Android Auto and critical app checks were separate verification gates. Never relock a bootloader merely because first boot succeeded.",
    ),
    (
        "Incremental debloat safety",
        "Removing many OEM packages at once hides dependency failures. Keep an immutable stock-product rollback point, remove a small reviewed batch, rebuild and verify, then test boot and core services before the next batch. Preserve shared backends, overlays, permission XML, signed top-level partitions and zero-byte compatibility stubs unless their dependency graph is understood. A package that looks like bloat may still be required by system_server, setup, telephony, themes or another overlay.",
    ),
    (
        "Recipe safety",
        "Preview every recipe before applying it. Recipes operate on a working copy, require an approval record, create rollback material, and never target the protected original.",
    ),
    (
        "Recipe Forger beginner journey",
        "Recipe Forger turns one understandable intention into a contained, reviewable ROM change "
        "through six stages. Recipe Forger stage 1 gives the Recipe a clear name and purpose so its "
        "receipt remains understandable later. Recipe Forger stage 2 chooses one bounded operation: "
        "inspect, replace a file, set a property, or remove a reviewed package or path. Recipe Forger "
        "stage 3 selects one real contained working-tree target; the protected firmware and connected "
        "phone can never be targets. Recipe Forger stage 4 collects only the values required by that "
        "operation and explains whether it is read-only or reversible. Recipe Forger stage 5 previews "
        "every target, overlap, conflict, and consequence before saving. Recipe Forger stage 6 records "
        "the exact digest and leaves execution locked. Saving a Recipe does not run it: Guardian still "
        "requires an exact preview, approval, rollback snapshot, verification, and a separate future "
        "review for any device-changing work.",
    ),
    (
        "Companion and Galaxy",
        "Companion, Galaxy, and ROMVERSE Intelligence are connected layers. Verified online sources keep tools, Device Packs, compatibility rules, fixes, recovery routes, and community knowledge current. Cached evidence lets an interrupted workflow resume; Guardian never lowers policy when connectivity changes.",
    ),
    (
        "When a scan fails",
        "Read the visible error first, check ADB availability, reconnect the phone, and retry once. Avoid repeated commands when the audit trail reports an integrity failure—resolve that condition first.",
    ),
    (
        "ADB error: device offline",
        "Meaning: ADB sees the device but the transport is unavailable. Fix: unplug and reconnect, use a direct USB port, restart the ADB server, unlock the phone, and scan again.",
    ),
    (
        "ADB error: unauthorized",
        "Meaning: the phone has not trusted this computer. Fix: unlock the phone, accept the RSA prompt, revoke stale USB debugging authorizations if needed, reconnect, and retry.",
    ),
    (
        "ADB error: no devices",
        "Meaning: no usable ADB transport was found. Fix: verify Platform Tools installation, cable/data mode, USB permissions or OEM drivers, then run adb devices outside ROMVERSE to confirm the host setup.",
    ),
    (
        "Exit code 1",
        "Meaning: the command failed generically. Fix: read the operation card, verify the selected device and inputs, preserve the evidence, and do not repeat a state-changing action automatically.",
    ),
    (
        "Exit code 127",
        "Meaning: the executable or command was not found. Fix: install the required tool, add it to PATH, restart ROMVERSE, and confirm the Tool Verification result.",
    ),
    (
        "Permission denied",
        "Meaning: the host account cannot access the tool, USB device, or workspace. Fix: correct udev rules or OEM drivers, choose a writable workspace, and avoid running the app as root unless platform documentation requires it.",
    ),
    (
        "No space left on device",
        "Meaning: the destination volume cannot accept more data. Fix: check workspace and phone storage, remove only confirmed temporary files, then recreate the plan after space is available.",
    ),
    (
        "Guardian integrity failure",
        "Meaning: the append-only audit hash chain no longer verifies. Fix: stop execution, preserve the log for review, identify unauthorized edits or corruption, and restore integrity before retrying any operation.",
    ),
    (
        "ROM DNA mismatch",
        "Meaning: project, original hash, tree hash, device pack, or recipe digest changed. Fix: inspect the diff, regenerate the build plan or DNA only after confirming the change is intentional.",
    ),
    (
        "Recommended action format",
        "Every diagnostic should explain meaning, confidence, recommended next step, and whether the action is safe to automate. Prefer reversible host-side fixes; ask for approval before anything that changes a phone or protected ROM.",
    ),
    (
        "Connected self-diagnosis",
        "ROMVERSE combines live verified knowledge with cached tool checks, ADB state, device evidence, audit integrity, workspace permissions, hashes, and history. Online evidence is source-attributed and content-addressed; losing connectivity never lowers Guardian policy.",
    ),
    (
        "Verified online remediation",
        "ROMVERSE fingerprints the exact error, device retail name and model code, codename, firmware build, source format, and tool version before researching a fix. Official Android, Google, OEM, and maintainer documentation ranks above community reports. Reddit and wider Google discovery may reveal useful model-specific experience, but a community claim is never executed directly or labeled working until it is independently corroborated and the matching typed ROMVERSE repair succeeds locally. Every lookup is cached with its source URL, timestamp, and receipt hash; Guardian policy is never weakened by online advice.",
    ),
    (
        "Safe automatic fixes",
        "Recommended automatic fixes are limited to host-side actions such as refreshing a scan, validating PATH, creating missing workspace folders, rebuilding local indexes, and clearing confirmed temporary files. Each action must be logged and reversible.",
    ),
    (
        "Fixes requiring approval",
        "Flashing, installing or removing packages, changing boot state, writing to a device, altering a protected original, or deleting user data can never be silently repaired. Guardian must produce a manifest, backup check, approval, rollback path, and verification receipt first.",
    ),
    (
        "Recommended: collect evidence first",
        "When an error appears, preserve the exact code, timestamp, selected device, tool version, online source receipt, and recent Guardian decision. Evidence prevents repeated mistakes and makes automated diagnosis more reliable.",
    ),
)


ARCHIVE_ARTICLES = build_catalog(LEGACY_GUIDES)
ARTICLES = tuple((article.title, article.plain_text) for article in ARCHIVE_ARTICLES)
ARTICLE_BY_KEY = {article.key: article for article in ARCHIVE_ARTICLES}


def matching_articles(query: str) -> tuple[tuple[str, str], ...]:
    """Return ranked, bounded local guides using the Archives retrieval rules."""

    return tuple(
        (match.article.title, match.article.plain_text)
        for match in search_catalog(ARCHIVE_ARTICLES, query, limit=256)
    )


class KnowledgeGuideDialog(QDialog):
    """Focused Archives guidance that does not discard the workflow underneath it."""

    def __init__(
        self,
        query: str,
        stage_label: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.query = query.strip()[:160]
        self.stage_label = stage_label.strip()[:120]
        matches = matching_articles(self.query)
        self.match_count = len(matches)
        self.article_title = matches[0][0] if matches else "No verified guide found"
        self.article_body = (
            matches[0][1]
            if matches
            else (
                "ROMVERSE Archives has no verified local guide for this exact stage. The workflow "
                "remains unchanged; ROMVERSE will not invent instructions or advance readiness."
            )
        )

        self.setWindowTitle("ROMVERSE Archives • Stage guide")
        self.setModal(True)
        self.setMinimumSize(660, 440)
        self.resize(760, 500)
        self.setStyleSheet(self._stylesheet())

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QFrame()
        header.setObjectName("GuideHeader")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(28, 22, 28, 20)
        header_layout.setSpacing(6)
        eyebrow = QLabel("ROMVERSE ARCHIVES  •  VERIFIED LOCAL GUIDE")
        eyebrow.setObjectName("GuideEyebrow")
        title = QLabel(self.stage_label or self.article_title)
        title.setObjectName("GuideTitle")
        title.setWordWrap(True)
        subtitle = QLabel(self.article_title)
        subtitle.setObjectName("GuideMuted")
        subtitle.setWordWrap(True)
        header_layout.addWidget(eyebrow)
        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)
        root.addWidget(header)

        content = QFrame()
        content.setObjectName("GuideContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(28, 22, 28, 22)
        content_layout.setSpacing(14)
        self.detail = QTextBrowser()
        self.detail.setObjectName("GuideDetail")
        self.detail.setOpenExternalLinks(False)
        self.detail.setPlainText(self.article_body)
        content_layout.addWidget(self.detail, 1)
        boundary = QLabel(
            "GUIDANCE ONLY  •  Your draft and evidence stay unchanged  •  Guardian authority stays locked"
        )
        boundary.setObjectName("GuideBoundary" if matches else "GuideWarning")
        boundary.setWordWrap(True)
        content_layout.addWidget(boundary)
        actions = QHBoxLayout()
        actions.addStretch()
        done = QPushButton("Keep working")
        done.setObjectName("GuidePrimary")
        done.clicked.connect(self.accept)
        actions.addWidget(done)
        content_layout.addLayout(actions)
        root.addWidget(content, 1)

    @staticmethod
    def _stylesheet() -> str:
        return """
            QDialog { background: #050812; color: #EAF4FF; }
            QFrame#GuideHeader { background: #070C18; border-bottom: 1px solid #183552; }
            QFrame#GuideContent { background: #050812; }
            QLabel#GuideEyebrow { color: #38D8EA; font-size: 11px; font-weight: 900; letter-spacing: 2px; }
            QLabel#GuideTitle { color: #FFFFFF; font-size: 25px; font-weight: 900; }
            QLabel#GuideMuted { color: #8EA5C7; font-size: 13px; }
            QTextBrowser#GuideDetail {
                color: #DCE9FA; background: rgba(10, 20, 36, 220); border: 1px solid #1D4964;
                border-radius: 12px; padding: 16px; font-size: 14px;
            }
            QLabel#GuideBoundary {
                color: #67E6B3; background: rgba(8, 40, 32, 210); border: 1px solid #247B5C;
                border-radius: 9px; padding: 10px; font-weight: 800;
            }
            QLabel#GuideWarning {
                color: #FFD67A; background: rgba(46, 34, 8, 210); border: 1px solid #8A6821;
                border-radius: 9px; padding: 10px; font-weight: 800;
            }
            QPushButton {
                color: #DDEBFA; background: rgba(17, 31, 52, 230); border: 1px solid #294B70;
                border-radius: 9px; padding: 9px 16px; font-weight: 800;
            }
            QPushButton:hover { border-color: #42D8EA; background: rgba(22, 50, 69, 240); }
            QPushButton#GuidePrimary { color: #041019; background: #43E0B0; border-color: #69F0C4; }
        """


class SynapseLearningDialog(QDialog):
    """Search integrity-checked private learning without turning it into authority."""

    def __init__(
        self,
        knowledge: tuple[SynapseKnowledge, ...],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.knowledge = knowledge
        self.visible_knowledge: tuple[SynapseKnowledge, ...] = ()
        self.setWindowTitle("ROMVERSE Archives • Local Learning")
        self.setMinimumSize(860, 560)
        self.resize(980, 650)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 22)
        root.setSpacing(12)
        eyebrow = QLabel("ROMVERSE SYNAPSE  •  PRIVATE LOCAL EVIDENCE BANK")
        eyebrow.setObjectName("Eyebrow")
        title = QLabel("Learned fixes, with their limits intact")
        title.setObjectName("Title")
        subtitle = QLabel(
            "Only privacy-scrubbed typed outcomes with local verification evidence appear here. "
            "Retired knowledge remains visible so ROMVERSE does not repeat an invalid fix."
        )
        subtitle.setObjectName("Muted")
        subtitle.setWordWrap(True)
        root.addWidget(eyebrow)
        root.addWidget(title)
        root.addWidget(subtitle)

        self.search = QLineEdit()
        self.search.setMaxLength(160)
        self.search.setClearButtonEnabled(True)
        self.search.setAccessibleName("Search private ROMVERSE learned outcomes")
        self.search.setPlaceholderText(
            "Search operation, source format, device, build, tool, solution, or outcome…"
        )
        self.search.textChanged.connect(self._filter)
        root.addWidget(self.search)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setObjectName("ArchivesLearningSplitter")
        self.list = QListWidget()
        self.list.setObjectName("ArchivesLearningList")
        self.list.setAccessibleName("Integrity-verified local learning records")
        self.list.currentRowChanged.connect(self._select)
        self.detail = QTextBrowser()
        self.detail.setObjectName("ArchivesLearningDetail")
        self.detail.setAccessibleName("Selected local learning evidence")
        splitter.addWidget(self.list)
        splitter.addWidget(self.detail)
        splitter.setSizes([350, 590])
        root.addWidget(splitter, 1)

        boundary = QLabel(
            "GUIDANCE ONLY  •  No upload  •  No remote instruction execution  •  Exact scope "
            "must match again  •  Guardian remains the only approval boundary"
        )
        boundary.setObjectName("SynapseBoundary")
        boundary.setWordWrap(True)
        root.addWidget(boundary)
        actions = QHBoxLayout()
        self.result_status = QLabel()
        self.result_status.setObjectName("Muted")
        actions.addWidget(self.result_status, 1)
        close = QPushButton("Return to Archives")
        close.setObjectName("Primary")
        close.clicked.connect(self.accept)
        actions.addWidget(close)
        root.addLayout(actions)
        self._filter("")

    def _filter(self, _value: object = None) -> None:
        tokens = self.search.text().casefold().split()[:16]
        self.visible_knowledge = tuple(
            item
            for item in self.knowledge
            if not tokens or all(token in self._search_document(item) for token in tokens)
        )
        self.list.blockSignals(True)
        self.list.clear()
        for item in self.visible_knowledge:
            marker = {
                SynapseKnowledgeState.TRUSTED: "✶",
                SynapseKnowledgeState.STRONG: "◆",
                SynapseKnowledgeState.VERIFIED_SUCCESS: "✓",
                SynapseKnowledgeState.CANDIDATE: "◇",
                SynapseKnowledgeState.RETIRED: "×",
            }[item.state]
            row = QListWidgetItem(
                f"{marker}  {item.solution_id.replace('-', ' ').title()}\n"
                f"{item.scope.operation.replace('-', ' ').title()}  •  "
                f"{item.state.value.replace('-', ' ').upper()}  "
                f"•  {item.confidence}%"
            )
            row.setData(Qt.ItemDataRole.UserRole, item.knowledge_id)
            row.setSizeHint(QSize(0, 58))
            row.setToolTip(item.summary)
            self.list.addItem(row)
        self.list.blockSignals(False)
        self.result_status.setText(
            f"Showing {len(self.visible_knowledge)} of {len(self.knowledge)} local knowledge records"
        )
        if self.visible_knowledge:
            self.list.setCurrentRow(0)
            self._select(0)
        else:
            self.detail.setPlainText(
                "No integrity-verified local learning record matched this search. ROMVERSE will "
                "not broaden the scope or invent a learned fix."
            )

    def _select(self, row: int) -> None:
        if not 0 <= row < len(self.visible_knowledge):
            return
        item = self.visible_knowledge[row]
        scope = item.scope
        state = item.state.value.replace("-", " ").upper()
        source_families = ", ".join(item.independent_source_families) or "None verified"
        self.detail.setPlainText(
            f"SOLUTION\n{item.solution_id}\n\n"
            f"KNOWLEDGE STATE\n{state}  •  {item.confidence}% confidence\n"
            f"{item.successful_verifications} successful verification(s)  •  "
            f"{item.failed_verifications} failed or drifted verification(s)\n\n"
            "EXACT LEARNING SCOPE\n"
            f"Operation: {scope.operation.replace('-', ' ')}\n"
            f"Source format: {scope.source_kind or 'UNCONFIRMED'}\n"
            f"Device codename: {scope.device_codename or 'UNCONFIRMED'}\n"
            f"Build family: {scope.build_family or 'UNCONFIRMED'}\n"
            f"Tool: {scope.tool_name or 'UNCONFIRMED'} "
            f"{scope.tool_version or '(version unconfirmed)'}\n\n"
            f"VERIFIED OUTCOME\n{item.summary}\n\n"
            f"Independent source families: {source_families}\n"
            f"Last observed: {item.last_observed_at}\n"
            f"Last verified success: {item.last_verified_at or 'NONE'}\n"
            f"Knowledge reference: {item.knowledge_id[:16]}…\n\n"
            "AUTOMATION BOUNDARY\n"
            "This record is guidance-only. A new error fingerprint and exact scope must match, "
            "then the same built-in typed action must produce fresh verification evidence. "
            "It cannot approve, build, flash, change a phone, or execute remote text."
        )

    @staticmethod
    def _search_document(item: SynapseKnowledge) -> str:
        scope = item.scope
        return " ".join(
            (
                item.solution_id,
                item.state.value,
                item.summary,
                scope.operation,
                scope.source_kind,
                scope.device_codename,
                scope.build_family,
                scope.tool_name,
                scope.tool_version,
                *item.independent_source_families,
            )
        ).casefold()


class KnowledgeCenter(QWidget):
    route_requested = Signal(str)

    def __init__(
        self,
        resolution_memory: ArchivesResolutionMemory | None = None,
        synapse_store: SynapseStore | None = None,
        device_catalog: GooglePlayDeviceCatalog | None = None,
    ) -> None:
        super().__init__()
        self.resolution_memory = resolution_memory
        self.synapse_store = synapse_store
        self.device_catalog = device_catalog
        self.synapse_knowledge: tuple[SynapseKnowledge, ...] = ()
        self.learning_dialog: SynapseLearningDialog | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 26, 30, 30)
        layout.setSpacing(14)
        eyebrow = QLabel("ROMVERSE ARCHIVES  •  CONNECTED INTELLIGENCE")
        eyebrow.setObjectName("Eyebrow")
        layout.addWidget(eyebrow)
        title = QLabel("ROMVERSE Archives")
        title.setObjectName("Title")
        layout.addWidget(title)
        subtitle = QLabel("Search verified ROMVERSE knowledge, cached evidence, and guided fixes.")
        subtitle.setObjectName("Muted")
        layout.addWidget(subtitle)

        self.source_context = QFrame()
        self.source_context.setObjectName("DiagnosticHandoffBar")
        source_layout = QHBoxLayout(self.source_context)
        source_layout.setContentsMargins(18, 11, 18, 11)
        source_copy = QVBoxLayout()
        source_eyebrow = QLabel("SOURCE WORKFLOW  •  NAVIGATION ONLY")
        source_eyebrow.setObjectName("Eyebrow")
        self.source_context_detail = QLabel()
        self.source_context_detail.setObjectName("Muted")
        self.source_context_detail.setWordWrap(True)
        source_copy.addWidget(source_eyebrow)
        source_copy.addWidget(self.source_context_detail)
        source_layout.addLayout(source_copy, 1)
        self.source_return = QPushButton()
        self.source_return.clicked.connect(self._return_to_source)
        source_layout.addWidget(self.source_return)
        self.source_context.setVisible(False)
        layout.addWidget(self.source_context)

        controls = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setMaxLength(160)
        self.search.setAccessibleName("Search ROMVERSE Archives")
        self.search.setPlaceholderText(
            "Search an error code, symptom, tool, firmware format, or workflow…"
        )
        self.search.textChanged.connect(self._filter)
        controls.addWidget(self.search, 1)
        self.category = QComboBox()
        self.category.setAccessibleName("Archives category")
        self.category.addItem("All knowledge", ALL_CATEGORIES)
        for category in CATEGORIES:
            self.category.addItem(category.title(), category)
        self.category.currentIndexChanged.connect(self._filter)
        controls.addWidget(self.category)
        self.evidence_lane = QComboBox()
        self.evidence_lane.setAccessibleName("Archives evidence lane")
        self.evidence_lane.addItem("All evidence", "all")
        self.evidence_lane.addItem("Official / OEM / AOSP", "official")
        self.evidence_lane.addItem("Maintainer & community", "community")
        self.evidence_lane.addItem("ROMVERSE field evidence", "field")
        self.evidence_lane.currentIndexChanged.connect(self._filter)
        controls.addWidget(self.evidence_lane)
        layout.addLayout(controls)

        quick = QHBoxLayout()
        quick.addWidget(QLabel("Quick help:"))
        for label, query in (
            ("Device IDs", "android device id"),
            ("ADB", "adb unauthorized"),
            ("payload.bin", "payload.bin"),
            ("Boot loop", "boot loop"),
            ("APK install", "install_failed"),
            ("AVB", "avb mismatch"),
            ("EROFS", "erofs read only"),
        ):
            button = QPushButton(label)
            button.clicked.connect(lambda _checked=False, value=query: self.search.setText(value))
            quick.addWidget(button)
        quick.addStretch()
        layout.addLayout(quick)

        metrics = catalog_metrics(ARCHIVE_ARTICLES)
        metrics_row = QHBoxLayout()
        for text in (
            f"{metrics['guides']} VERIFIED GUIDES",
            f"{metrics['known_fixes']} KNOWN FIXES",
            f"{metrics['categories']} CATEGORIES",
            f"{metrics['official_sources']} OFFICIAL GUIDES",
            f"{metrics['community_sources']} COMMUNITY GUIDES",
        ):
            metric = QLabel(text)
            metric.setObjectName("Good")
            metrics_row.addWidget(metric)
        metrics_row.addStretch()
        layout.addLayout(metrics_row)

        self.device_catalog_status = QLabel()
        self.device_catalog_status.setAccessibleName("Official Android device ID catalog status")
        self.device_catalog_status.setWordWrap(True)
        layout.addWidget(self.device_catalog_status)
        self.refresh_device_catalog()

        self.learning_panel = QFrame()
        self.learning_panel.setObjectName("SynapseLearningPanel")
        self.learning_panel.setProperty("learningState", "empty")
        learning_layout = QHBoxLayout(self.learning_panel)
        learning_layout.setContentsMargins(16, 11, 13, 11)
        learning_layout.setSpacing(13)
        learning_copy = QVBoxLayout()
        learning_copy.setSpacing(3)
        self.learning_eyebrow = QLabel("LOCAL LEARNING  •  ROMVERSE SYNAPSE")
        self.learning_eyebrow.setObjectName("SynapseLearningTitle")
        self.learning_status = QLabel("Checking the private local evidence bank…")
        self.learning_status.setObjectName("Muted")
        self.learning_status.setAccessibleName("Private local ROMVERSE learning status")
        self.learning_status.setWordWrap(True)
        learning_copy.addWidget(self.learning_eyebrow)
        learning_copy.addWidget(self.learning_status)
        learning_layout.addLayout(learning_copy, 1)
        self.learning_button = QPushButton("How local learning works  →")
        self.learning_button.setObjectName("SynapseLearningAction")
        self.learning_button.setAccessibleName(
            "Inspect private integrity-verified ROMVERSE learning"
        )
        self.learning_button.clicked.connect(self._open_local_learning)
        learning_layout.addWidget(self.learning_button)
        layout.addWidget(self.learning_panel)

        self.search_status = QLabel(f"{len(ARCHIVE_ARTICLES)} verified local guides available.")
        self.search_status.setObjectName("Muted")
        layout.addWidget(self.search_status)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setObjectName("ArchivesSplitter")
        self.list = QListWidget()
        self.list.setObjectName("ArchivesList")
        self.list.setAccessibleName("Matching ROMVERSE Archives guides")
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.detail = QTextBrowser()
        self.detail.setObjectName("ArchivesDetail")
        self.detail.setAccessibleName("Selected ROMVERSE Archives guide")
        self.detail.setOpenExternalLinks(False)
        splitter.addWidget(self.list)
        splitter.addWidget(self.detail)
        splitter.setSizes([320, 700])
        layout.addWidget(splitter, 1)

        self.resolution_status = QLabel("")
        self.resolution_status.setObjectName("Eyebrow")
        self.resolution_status.setAccessibleName("Local Archives resolution memory")
        self.resolution_status.setWordWrap(True)
        self.resolution_status.setVisible(False)
        self.resolution_status.setToolTip(
            "Integrity-verified before/after correlation only. It is not proof that a guide "
            "caused the result and never grants execution authority."
        )
        layout.addWidget(self.resolution_status)

        actions = QHBoxLayout()
        self.open_source = QPushButton("Open official source")
        self.open_source.setVisible(False)
        self.open_source.clicked.connect(self._open_current_source)
        actions.addWidget(self.open_source)
        actions.addStretch()
        self.open_route = QPushButton("Open relevant ROMVERSE section")
        self.open_route.setObjectName("Primary")
        self.open_route.setVisible(False)
        self.open_route.clicked.connect(self._open_current_route)
        actions.addWidget(self.open_route)
        layout.addLayout(actions)

        self.list.currentItemChanged.connect(self._show_article)
        self.refresh_synapse_memory()
        self._filter("")

    def open_query(self, query: str, *, source_route: str = "") -> None:
        """Open one verified guide query supplied by another ROMVERSE workflow."""

        self.set_source_context(source_route)
        normalized = query.strip()[:160]
        self.category.setCurrentIndex(0)
        self.evidence_lane.setCurrentIndex(0)
        if self.search.text() == normalized:
            self._filter(normalized)
        else:
            self.search.setText(normalized)
        self.search.setFocus(Qt.FocusReason.OtherFocusReason)

    def open_feature_destination(self, route: str) -> bool:
        """Reveal the private Synapse evidence bank without opening a dialog or network path."""

        if str(route).strip() != "romverse_synapse":
            return False
        self.clear_source_context()
        self.refresh_synapse_memory()
        self.learning_eyebrow.setText(
            "FIND ANYTHING  •  ROMVERSE SYNAPSE  •  PRIVATE LOCAL EVIDENCE"
        )
        self.learning_panel.setToolTip(
            "Find Anything opened ROMVERSE Synapse's private integrity-verified local evidence "
            "bank. No query, upload, contribution, network request, repair, or phone action started."
        )
        self.learning_button.setFocus(Qt.FocusReason.OtherFocusReason)
        return True

    def open_article(self, key: str, *, source_route: str = "") -> bool:
        """Select one exact guide identity supplied by a typed ROMVERSE workflow."""

        self.set_source_context(source_route)
        article = ARTICLE_BY_KEY.get(key.strip()[:80])
        if article is None:
            self.category.setCurrentIndex(0)
            self.search.blockSignals(True)
            self.search.clear()
            self.search.blockSignals(False)
            self.list.blockSignals(True)
            self.list.clear()
            self.list.blockSignals(False)
            self.detail.setText(
                "The requested verified Archives article identity could not be resolved. "
                "ROMVERSE will not substitute a text-search match or invent guidance."
            )
            self.search_status.setObjectName("Warning")
            self.search_status.setText("Exact verified guide unavailable.")
            self.open_route.setVisible(False)
            self.open_source.setVisible(False)
            self.resolution_status.setVisible(False)
            self.search_status.style().unpolish(self.search_status)
            self.search_status.style().polish(self.search_status)
            return False
        self.category.setCurrentIndex(0)
        self.evidence_lane.setCurrentIndex(0)
        if self.search.text() == article.title:
            self._filter(article.title)
        else:
            self.search.setText(article.title)
        for row in range(self.list.count()):
            item = self.list.item(row)
            if item.data(Qt.ItemDataRole.UserRole) == article.key:
                self.list.setCurrentItem(item)
                self.list.scrollToItem(item)
                self.search.setFocus(Qt.FocusReason.OtherFocusReason)
                return True
        return False

    def set_source_context(self, route: str) -> None:
        """Keep a safe return path to the workflow that requested Archives guidance."""

        normalized = route.strip()[:80]
        if normalized not in FEATURES or normalized == "archives":
            self.clear_source_context()
            return
        title = feature(normalized).title
        self.source_context.setProperty("source_route", normalized)
        self.source_context_detail.setText(
            f"Opened from {title}. Return to the unchanged source workflow after reviewing this "
            "guide; Archives navigation starts no worker, repair, build, or phone action."
        )
        self.source_return.setText(f"Return to {title}")
        self.source_context.setVisible(True)

    def clear_source_context(self) -> None:
        self.source_context.setProperty("source_route", "")
        self.source_context_detail.clear()
        self.source_return.setText("")
        self.source_context.setVisible(False)

    def _filter(self, _value: object = None) -> None:
        query = self.search.text().strip()[:160]
        category = str(self.category.currentData() or ALL_CATEGORIES)
        matches = search_catalog(ARCHIVE_ARTICLES, query, category, limit=256)
        evidence_lane = str(self.evidence_lane.currentData() or "all")
        if evidence_lane != "all":
            matches = tuple(
                match for match in matches if source_lane(match.article.source) == evidence_lane
            )

        self.list.blockSignals(True)
        self.list.clear()
        for match in matches:
            item = QListWidgetItem(match.article.title)
            item.setData(Qt.ItemDataRole.UserRole, match.article.key)
            item.setToolTip(
                f"{match.article.category.title()}  •  {match.article.source.authority}"
            )
            self.list.addItem(item)
        self.list.blockSignals(False)

        if matches:
            self.list.setCurrentRow(0)
            self._show_article(self.list.currentItem(), None)
            self.search_status.setObjectName("Good" if query else "Muted")
            guide_count = f"{len(matches)} verified guide{'s' if len(matches) != 1 else ''}"
            self.search_status.setText(
                f"{guide_count} found for “{query}”." if query else f"{guide_count} available."
            )
        else:
            self.detail.setText(
                "No verified ROMVERSE guide matched this search. Try a shorter symptom, exact "
                "error code, tool name, firmware format, or phone feature. ROMVERSE will not "
                "invent a fix when its local knowledge has no match."
            )
            self.search_status.setObjectName("Warning")
            self.search_status.setText(f"No verified guide matched “{query}”.")
            self.open_route.setVisible(False)
            self.open_source.setVisible(False)
            self.resolution_status.setVisible(False)
        self.search_status.style().unpolish(self.search_status)
        self.search_status.style().polish(self.search_status)

    def _show_article(
        self, current: QListWidgetItem | None, _previous: QListWidgetItem | None
    ) -> None:
        article = self._article_for(current)
        memory = (
            self.resolution_memory.for_article(article.key)
            if article is not None and self.resolution_memory is not None
            else None
        )
        detail = article.plain_text if article else "Select a topic."
        if memory is not None:
            detail += "\n\n" + memory.plain_text
        self.detail.setPlainText(detail)
        self._show_resolution_memory(memory)
        route = article.route if article is not None else ""
        self.open_route.setProperty("route", route)
        self.open_route.setText(
            f"Open {feature(route).title}" if route and route != "archives" else ""
        )
        self.open_route.setVisible(bool(route and route != "archives"))
        source_url = article.source.url if article is not None else ""
        self.open_source.setProperty("source_url", source_url)
        lane = source_lane(article.source) if article is not None else "local"
        if lane == "community":
            source_label = (
                "Open maintainer source"
                if article is not None and article.source.authority.startswith("MAINTAINER/")
                else "Open community report"
            )
        else:
            source_label = "Open official source"
        self.open_source.setText(source_label)
        self.open_source.setAccessibleName(source_label)
        self.open_source.setVisible(bool(source_url))

    def refresh_resolution_memory(self) -> None:
        """Refresh presentation after Recovery Bay records a fresh comparison."""

        self._show_article(self.list.currentItem(), None)

    def refresh_device_catalog(self) -> None:
        """Show current integrity-checked naming coverage without implying flash support."""

        status = self.device_catalog.status() if self.device_catalog is not None else None
        if status is None:
            self.device_catalog_status.setObjectName("Muted")
            self.device_catalog_status.setText(
                "OFFICIAL DEVICE IDS  •  Open Device Atlas to sync and search Google's naming "
                "catalog  •  IDENTITY ONLY"
            )
        elif status.valid:
            state = "CURRENT" if status.fresh else "UPDATE DUE"
            self.device_catalog_status.setObjectName("Good" if status.fresh else "Warning")
            self.device_catalog_status.setText(
                f"{status.entry_count:,} OFFICIAL ANDROID DEVICE ID ROWS  •  {state}  •  "
                "INTEGRITY CHECKED  •  NAMES AND IDS ONLY — NOT BUILD OR FLASH AUTHORITY"
            )
        else:
            self.device_catalog_status.setObjectName("Warning")
            self.device_catalog_status.setText(
                "OFFICIAL DEVICE IDS UNAVAILABLE  •  Existing guides remain local  •  Open Device "
                "Atlas to sync when online sources are enabled"
            )
        self.device_catalog_status.style().unpolish(self.device_catalog_status)
        self.device_catalog_status.style().polish(self.device_catalog_status)

    def refresh_synapse_memory(self) -> None:
        """Reload only integrity-checked private learning when Archives is opened."""

        self.learning_eyebrow.setText("LOCAL LEARNING  •  ROMVERSE SYNAPSE")
        if self.synapse_store is None:
            self.synapse_knowledge = ()
            self._set_learning_state(
                "0 LOCAL OUTCOMES  •  Learning begins only after a typed fix is verified  •  "
                "GUIDANCE ONLY",
                "empty",
            )
            self.learning_button.setText("How local learning works  →")
            return
        try:
            self.synapse_knowledge = self.synapse_store.list_knowledge()
        except SynapseStoreError:
            self.synapse_knowledge = ()
            self._set_learning_state(
                "LOCAL LEARNING UNAVAILABLE  •  The integrity check rejected this private "
                "cache  •  ORIGINAL PRESERVED",
                "unavailable",
            )
            self.learning_button.setText("Review the safety boundary  →")
            return
        usable_states = {
            SynapseKnowledgeState.VERIFIED_SUCCESS,
            SynapseKnowledgeState.STRONG,
            SynapseKnowledgeState.TRUSTED,
        }
        usable = sum(item.state in usable_states for item in self.synapse_knowledge)
        trusted = sum(
            item.state is SynapseKnowledgeState.TRUSTED for item in self.synapse_knowledge
        )
        retired = sum(
            item.state is SynapseKnowledgeState.RETIRED for item in self.synapse_knowledge
        )
        if not self.synapse_knowledge:
            self._set_learning_state(
                "0 LOCAL OUTCOMES  •  Learning begins only after a typed fix is verified  •  "
                "NO UPLOAD OR EXECUTION AUTHORITY",
                "empty",
            )
            self.learning_button.setText("How local learning works  →")
            return
        self._set_learning_state(
            f"{len(self.synapse_knowledge)} LOCAL KNOWLEDGE RECORD(S)  •  {usable} USABLE  •  "
            f"{trusted} TRUSTED  •  {retired} RETIRED  •  GUIDANCE ONLY",
            "verified" if usable and not retired else "attention",
        )
        self.learning_button.setText("Inspect learned fixes  →")

    def _set_learning_state(self, text: str, state: str) -> None:
        self.learning_status.setText(text)
        self.learning_status.setObjectName(
            "Good" if state == "verified" else "Danger" if state == "unavailable" else "Warning"
        )
        self.learning_panel.setProperty("learningState", state)
        for widget in (self.learning_status, self.learning_panel):
            widget.style().unpolish(widget)
            widget.style().polish(widget)

    def _open_local_learning(self) -> None:
        if not self.synapse_knowledge:
            self.open_article("archives-local-learning-boundary")
            return
        dialog = SynapseLearningDialog(self.synapse_knowledge, self)
        self.learning_dialog = dialog
        dialog.finished.connect(lambda _result, opened=dialog: self._learning_closed(opened))
        dialog.open()

    def _learning_closed(self, dialog: SynapseLearningDialog) -> None:
        if self.learning_dialog is dialog:
            self.learning_dialog = None

    def _show_resolution_memory(self, memory: ArticleResolutionMemory | None) -> None:
        if memory is None:
            self.resolution_status.clear()
            self.resolution_status.setVisible(False)
            return
        noun = "comparison" if memory.comparisons == 1 else "comparisons"
        self.resolution_status.setText(
            f"LOCAL RESOLUTION MEMORY  •  {memory.comparisons} INTEGRITY-VERIFIED {noun.upper()}  "
            f"•  {memory.improved} IMPROVED  •  {memory.unchanged} UNCHANGED  •  "
            f"{memory.needs_attention} NEEDS ATTENTION  •  CORRELATION, NOT CAUSATION"
        )
        self.resolution_status.setVisible(True)

    @staticmethod
    def _article_for(current: QListWidgetItem | None) -> ArchiveArticle | None:
        if current is None:
            return None
        return ARTICLE_BY_KEY.get(str(current.data(Qt.ItemDataRole.UserRole) or ""))

    def _open_current_route(self) -> None:
        route = str(self.open_route.property("route") or "")
        if route:
            self.route_requested.emit(route)

    def _open_current_source(self) -> None:
        source_url = str(self.open_source.property("source_url") or "")
        if source_url and not QDesktopServices.openUrl(QUrl(source_url)):
            self.search_status.setObjectName("Warning")
            self.search_status.setText(
                "The verified source link could not be opened. The local guide remains available."
            )
            self.search_status.style().unpolish(self.search_status)
            self.search_status.style().polish(self.search_status)

    def _return_to_source(self) -> None:
        route = str(self.source_context.property("source_route") or "")
        if route in FEATURES and route != "archives":
            self.route_requested.emit(route)
