from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

COLORS = {
    "background": "#02050A",
    "surface": "#060A11",
    "surface_alt": "#0A0F1B",
    "border": "#202C43",
    "text": "#EDF4FF",
    "muted": "#8C9ABC",
    "purple": "#A855F7",
    "blue": "#4F7CFF",
    "cyan": "#28E7F5",
    "green": "#44E39A",
    "orange": "#FFB454",
    "red": "#FF6685",
}

STYLESHEET = """
* { font-family: Inter, "Noto Sans", "Segoe UI", sans-serif; }
QMainWindow, QWidget#AppRoot { background: #02050A; color: #EDF4FF; }
QDialog { background: #090D24; color: #EDF4FF; }
QWidget { color: #EDF4FF; font-size: 14px; }
QFrame#Sidebar {
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:1,
        stop:0 rgba(2, 5, 10, 226),
        stop:0.46 rgba(6, 10, 22, 216),
        stop:0.82 rgba(14, 10, 35, 204),
        stop:1 rgba(5, 18, 29, 218)
    );
    border: 1px solid rgba(78, 115, 169, 145);
    border-right: 1px solid rgba(78, 221, 245, 150);
    border-radius: 0px;
}
QFrame#WorkspaceBar {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 rgba(4,8,17,244),stop:0.58 rgba(6,12,27,238),stop:1 rgba(10,12,31,232));
    border: 0;
    border-bottom: 1px solid rgba(67, 102, 157, 155);
}
QFrame#WorkspaceBar[focusMode="true"] {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 rgba(16,8,34,246),stop:0.52 rgba(6,18,35,242),stop:1 rgba(4,30,37,236));
    border-bottom: 1px solid rgba(64, 224, 234, 185);
}
QLabel#WorkspaceSection { color: #6FCFE3; font-size: 9px; font-weight: 850; letter-spacing: 1.25px; }
QLabel#WorkspaceRouteTitle { color: #F1F5FF; font-size: 14px; font-weight: 780; }
QToolButton#WorkspaceControl, QToolButton#FocusWorkspaceControl {
    color: #BCD0EC; background: rgba(8,16,31,190); border: 1px solid rgba(58,86,132,180);
    border-radius: 8px; min-width: 34px; min-height: 32px; padding: 2px 7px; font-weight: 800;
}
QToolButton#WorkspaceControl:hover, QToolButton#FocusWorkspaceControl:hover {
    color: #FFFFFF; background: rgba(22,36,65,225); border-color: #35E7F5;
}
QToolButton#FocusWorkspaceControl { color: #C9B4FF; min-width: 68px; font-size: 10px; letter-spacing: 1px; }
QToolButton#FocusWorkspaceControl[active="true"] {
    color: #FFFFFF; background: rgba(59,31,94,230); border-color: #B45CFF; min-width: 116px;
}
QFrame#TopBar { background: #05080E; border-bottom: 1px solid #1A2539; }
QFrame#ConnectionBar { background: rgba(3, 7, 13, 250); border: 1px solid #22324E; border-radius: 11px; }
QFrame#Card { background: rgba(5, 9, 16, 250); border: 1px solid #202C43; border-radius: 13px; }
QFrame#HeroCard { background: rgba(5, 9, 16, 250); border: 1px solid #283A58; border-radius: 13px; }
QFrame#AboutEvidencePanel {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 rgba(12,17,45,246),stop:0.5 rgba(5,24,38,244),stop:1 rgba(24,12,43,242));
    border: 1px solid rgba(77, 214, 235, 155); border-top: 2px solid rgba(180, 92, 255, 190); border-radius: 14px;
}
QFrame#AboutEvidenceCard {
    background: rgba(4, 10, 22, 238); border: 1px solid rgba(61, 91, 143, 175);
    border-left: 3px solid #536785; border-radius: 10px;
}
QFrame#AboutEvidenceCard[evidenceState="verified"] { border-left-color: #44E39A; }
QFrame#AboutEvidenceCard[evidenceState="attention"] { border-left-color: #FFB454; }
QFrame#AboutEvidenceCard[evidenceState="unavailable"] { border-left-color: #FF6685; }
QLabel#AboutEvidenceTitle { color: #72EAF5; font-size: 10px; font-weight: 850; letter-spacing: 1.2px; }
QLabel#AboutEvidenceValue { color: #F1F5FF; font-size: 15px; font-weight: 820; padding-top: 3px; }
QPushButton#AboutEvidenceAction {
    color: #DDE8FF; background: rgba(19, 31, 61, 215); border: 1px solid rgba(87, 125, 194, 190);
    border-radius: 7px; padding: 6px 9px; font-size: 10px; font-weight: 760;
}
QPushButton#AboutEvidenceAction:hover { color: #FFFFFF; border-color: #63ECF8; background: rgba(27, 48, 83, 235); }
QPushButton#AboutEvidenceAction:focus { border: 2px solid #FFFFFF; }
QPushButton#AboutEvidenceGuide {
    color: #E4D3FF; background: rgba(43, 20, 70, 220); border: 1px solid rgba(180, 92, 255, 175);
    border-radius: 8px; padding: 8px 11px; font-size: 10px; font-weight: 790;
}
QPushButton#AboutEvidenceGuide:hover { color: #FFFFFF; border-color: #63ECF8; }
QFrame#AboutTrustDock {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 rgba(8,20,34,242),stop:0.5 rgba(18,13,42,240),stop:1 rgba(30,17,23,238));
    border: 1px solid rgba(105, 122, 197, 160); border-top: 2px solid rgba(255, 180, 84, 190); border-radius: 14px;
}
QPushButton#AboutTrustAction {
    color: #EAF1FF; background: rgba(5, 10, 23, 232); border: 1px solid rgba(69, 94, 145, 185);
    border-left: 3px solid #60718E; border-radius: 9px; padding: 10px 12px; min-height: 58px;
    text-align: left; font-size: 10px; font-weight: 740;
}
QPushButton#AboutTrustAction[trustState="verified"] { border-left-color: #44E39A; }
QPushButton#AboutTrustAction[trustState="caution"] { border-left-color: #FFB454; }
QPushButton#AboutTrustAction[trustState="attention"] { border-left-color: #FF8D74; }
QPushButton#AboutTrustAction[trustState="proof"] { border-left-color: #35E7F5; }
QPushButton#AboutTrustAction:hover { color: #FFFFFF; background: rgba(24, 33, 64, 240); border-color: #B45CFF; }
QPushButton#AboutTrustAction:focus { border: 2px solid #FFFFFF; }
QFrame#DiagnosticHandoffBar {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 rgba(20,13,43,238),stop:1 rgba(5,31,42,232));
    border: 1px solid rgba(64, 220, 235, 160); border-left: 3px solid #A855F7; border-radius: 9px;
}
QFrame#RequirementsBlueprint {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 rgba(12,18,42,246),stop:0.5 rgba(10,25,43,244),stop:1 rgba(20,11,42,242));
    border: 1px solid rgba(82, 117, 187, 185); border-top: 2px solid rgba(53, 222, 239, 180); border-radius: 11px;
}
QFrame#RequirementLane {
    background: rgba(5, 11, 23, 238); border: 1px solid rgba(54, 80, 126, 180); border-radius: 9px;
}
QFrame#RequirementLane[state="verified"] { border-left: 3px solid #44E39A; }
QFrame#RequirementLane[state="declared"] { border-left: 3px solid #4F7CFF; }
QFrame#RequirementLane[state="needs-evidence"] { border-left: 3px solid #FFB454; }
QFrame#RequirementLane[state="locked"] { border-left: 3px solid #FF6685; }
QLabel#RequirementNeeds {
    color: #AABAD6; background: rgba(6, 14, 28, 180); border: 1px solid rgba(42, 64, 101, 140);
    border-radius: 7px; padding: 8px; font-size: 11px;
}
QFrame#NexusReviewCard {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 rgba(31,16,58,248),stop:0.52 rgba(8,21,43,246),stop:1 rgba(5,35,43,244));
    border: 1px solid rgba(65, 222, 236, 185); border-left: 4px solid #B45CFF; border-radius: 11px;
}
QFrame#BackupReviewCard {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 rgba(14,32,55,248),stop:0.55 rgba(15,18,48,246),stop:1 rgba(37,15,54,244));
    border: 1px solid rgba(178, 94, 255, 185); border-left: 4px solid #42DDEA; border-radius: 11px;
}
QFrame#StudioReviewCard {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 rgba(29,13,53,248),stop:0.48 rgba(8,22,45,246),stop:1 rgba(5,38,43,244));
    border: 1px solid rgba(72, 226, 239, 195); border-left: 4px solid #C45CFF; border-radius: 11px;
}
QFrame#Card[diagnosticFocus="true"] {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 rgba(31,16,58,248),stop:1 rgba(5,31,43,248));
    border: 2px solid #42DDEA; border-left: 4px solid #B45CFF;
}
QFrame#DashboardCard { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 rgba(4, 8, 14, 252),stop:1 rgba(7, 12, 20, 252)); border: 1px solid #24334D; border-radius: 12px; }
QFrame#GenesisFlightPlan {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 rgba(18,11,39,248),stop:0.52 rgba(7,16,34,246),stop:1 rgba(5,25,35,244));
    border: 1px solid rgba(106, 116, 255, 190);
    border-top: 1px solid rgba(55, 226, 241, 185);
    border-radius: 12px;
}
QFrame#FlightPlanTile { background: rgba(8, 16, 31, 220); border: 1px solid rgba(61, 93, 146, 175); border-radius: 8px; }
QLabel#FlightPlanRoute { color: #49DDED; font-size: 10px; font-weight: 850; letter-spacing: 1.5px; }
QLabel#FlightPlanTitle { color: #F4F7FF; font-size: 20px; font-weight: 780; }
QLabel#FlightPlanNext { color: #D5B5FF; font-size: 11px; font-weight: 800; letter-spacing: 0.8px; }
QLabel#FlightPlanWarning { color: #FFBF69; background: rgba(48, 28, 8, 145); border: 1px solid rgba(255, 180, 84, 110); border-radius: 7px; padding: 8px; }
QLabel#FlightPlanDanger { color: #FF849A; background: rgba(52, 10, 24, 150); border: 1px solid rgba(255, 102, 133, 120); border-radius: 7px; padding: 8px; }
QFrame#HealthStrip { background: rgba(5, 10, 19, 250); border: 1px solid #294069; border-radius: 8px; }
QFrame#ProcessStatusRow { background: rgba(4, 10, 21, 225); border: 1px solid rgba(45, 72, 112, 145); border-radius: 8px; }
QLabel#ProcessStatusIdle { color: #7385A6; font-size: 9px; font-weight: 800; letter-spacing: 1.2px; }
QLabel#ProcessStatusActive { color: #47DDEA; font-size: 9px; font-weight: 850; letter-spacing: 1.2px; }
QFrame#DeviceMiniCard { background: rgba(3, 10, 15, 252); border: 1px solid #164551; border-radius: 11px; }
QFrame#TelemetryStats, QFrame#TelemetryHistory { background: rgba(2, 7, 14, 205); border: 1px solid rgba(45, 72, 112, 165); border-radius: 10px; }
QFrame#TelemetryTile { background: rgba(8, 16, 30, 224); border: 1px solid rgba(55, 86, 132, 175); border-radius: 8px; }
QFrame#TelemetryTile:hover { background: rgba(14, 26, 47, 232); border-color: rgba(66, 215, 235, 185); }
QLabel#Brand { font-size: 24px; font-weight: 800; letter-spacing: 3px; color: #F4F8FF; }
QLabel#ProjectBrand { color: #C789FF; font-size: 9px; font-weight: 700; letter-spacing: 1.2px; padding: 2px 0 0 0; }
QLabel#Eyebrow { color: #28E7F5; font-size: 11px; font-weight: 700; letter-spacing: 2px; }
QLabel#Title { font-size: 27px; font-weight: 750; }
QLabel#HeroTitle { font-size: 25px; font-weight: 750; }
QLabel#SectionTitle { font-size: 17px; font-weight: 700; }
QLabel#DashboardHeading { color: #B45CFF; font-size: 15px; font-weight: 800; letter-spacing: 0.7px; }
QLabel#DashboardHero { color: #F5F7FF; font-size: 20px; font-weight: 700; }
QLabel#TelemetryLabel { color: #6FCFE3; font-size: 9px; font-weight: 850; letter-spacing: 1.1px; }
QLabel#TelemetryValue { color: #F0F5FF; font-size: 13px; font-weight: 700; }
QLabel#TelemetryChartTitle { color: #C6D6F0; font-size: 11px; font-weight: 750; }
QLabel#Muted { color: #8C9ABC; }
QLabel#Value { font-size: 15px; font-weight: 650; }
QLabel#Good { color: #44E39A; font-weight: 650; }
QLabel#Warning { color: #FFB454; font-weight: 650; }
QLabel#Danger { color: #FF6685; font-weight: 650; }
QPushButton { background: #090E19; border: 1px solid #2A3D67; border-radius: 9px; padding: 9px 15px; font-weight: 650; }
QPushButton:hover { background: #11192A; border-color: #6B4BC4; }
QPushButton:pressed { background: #0A1120; }
QPushButton:disabled { color: #65708C; border-color: #263150; background: #12172A; }
QPushButton#ArchitectModeButton:checked {
    color: #FFFFFF; background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #6A32C8,stop:1 #1F718F);
    border: 1px solid #63ECF8;
}
QPushButton#Primary { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #6236CA,stop:1 #2567B9); border-color: #8B72FF; }
QPushButton#Primary:hover { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #7847E0,stop:1 #2D79CF); border-color: #A88BFF; }
QPushButton#Nav { text-align: left; border: 0; border-radius: 8px; background: transparent; color: #AEB8CD; padding: 8px 12px; min-height: 30px; font-weight: 600; }
QPushButton#Nav:hover { background: rgba(20, 31, 55, 185); color: #F4F7FF; border: 1px solid rgba(77, 142, 210, 90); }
QPushButton#Nav[active="true"] { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 rgba(103,35,151,210),stop:0.55 rgba(46,22,87,190),stop:1 rgba(18,53,76,175)); color: #FFFFFF; border: 1px solid rgba(183,92,255,145); border-left: 3px solid #B45CFF; padding-left: 9px; }
QPushButton#Nav[collapsed="true"] { text-align: center; padding: 8px; min-height: 34px; }
QPushButton#Nav[collapsed="true"][active="true"] { padding: 8px 6px; border-left: 3px solid #B45CFF; }
QPushButton#CommandPaletteButton { text-align: left; color: #C8D5EE; background: rgba(8,16,31,180); border: 1px solid #2B416B; padding: 8px 11px; font-size: 11px; letter-spacing: 0.4px; }
QPushButton#CommandPaletteButton:hover { color: #FFFFFF; border-color: #35E7F5; background: rgba(17,31,55,210); }
QLabel#NavSection { color: #647594; background: transparent; border: 0; padding: 10px 10px 3px 10px; font-size: 9px; font-weight: 800; letter-spacing: 1.4px; }
QPushButton#QuickAction, QToolButton#QuickAction { background: rgba(5, 9, 16, 250); border: 1px solid #2B416B; border-radius: 9px; color: #E9EDFF; font-size: 14px; padding: 9px; }
QPushButton#QuickAction:hover, QToolButton#QuickAction:hover { background: rgba(28, 13, 47, 250); border-color: #A855F7; color: #E5B9FF; }
QToolButton#QuickAction[evidenceReady="true"] {
    color: #FFFFFF;
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 rgba(42,20,76,245),stop:1 rgba(5,47,61,240));
    border: 2px solid #3EDDEB; border-left: 4px solid #B45CFF;
}
QFrame#StudioCommandGroup {
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:1,
        stop:0 rgba(14, 26, 49, 232),
        stop:0.52 rgba(9, 17, 34, 220),
        stop:1 rgba(30, 12, 51, 216)
    );
    border: 1px solid rgba(85, 137, 210, 185);
    border-top: 1px solid rgba(89, 231, 248, 180);
    border-radius: 13px;
}
QTabWidget#StudioCommandTabs::pane {
    background: rgba(4, 9, 18, 205);
    border: 1px solid rgba(82, 134, 204, 175);
    border-radius: 12px;
    top: -1px;
}
QTabWidget#StudioCommandTabs QTabBar::tab {
    color: #91A4C8;
    background: rgba(7, 13, 27, 220);
    border: 1px solid rgba(53, 79, 124, 155);
    border-bottom: 0;
    padding: 10px 22px;
    margin-right: 4px;
    min-width: 148px;
    font-size: 12px;
    font-weight: 750;
}
QTabWidget#StudioCommandTabs QTabBar::tab:first { border-top-left-radius: 9px; }
QTabWidget#StudioCommandTabs QTabBar::tab:last { border-top-right-radius: 9px; }
QTabWidget#StudioCommandTabs QTabBar::tab:selected {
    color: #FFFFFF;
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 rgba(83,35,132,240),stop:1 rgba(13,69,93,235));
    border-color: #55E8F5;
}
QTabWidget#StudioCommandTabs QTabBar::tab:hover { color: #D8F8FF; border-color: #A855F7; }
QScrollArea#StudioDetailScroll { background: transparent; border: 0; }
QLabel#StudioCommandTitle { color: #55E8F5; font-size: 13px; font-weight: 850; letter-spacing: 1.7px; }
QLabel#StudioCommandSummary { color: #A4B6D6; font-size: 11px; padding-bottom: 2px; }
QPushButton#StudioAction {
    color: #E9F2FF;
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 rgba(16,26,49,238),stop:1 rgba(11,14,31,225));
    border: 1px solid rgba(67, 112, 180, 175);
    border-top: 1px solid rgba(113, 180, 235, 145);
    border-radius: 9px;
    padding: 9px 12px;
    font-size: 13px;
    font-weight: 750;
}
QPushButton#StudioAction:hover {
    color: #FFFFFF;
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 rgba(42,25,78,245),stop:1 rgba(10,54,76,242));
    border: 1px solid #55E8F5;
}
QPushButton#StudioAction[featured="true"] {
    color: #F4E9FF;
    border: 1px solid rgba(190, 91, 255, 210);
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 rgba(73,29,113,235),stop:1 rgba(12,48,79,232));
}
QPushButton#StudioAction:disabled {
    color: rgba(144, 158, 190, 105);
    background: rgba(9, 14, 27, 170);
    border: 1px solid rgba(47, 65, 100, 115);
}
QComboBox, QLineEdit { background: #0B1022; border: 1px solid #2B3C70; border-radius: 8px; padding: 8px; }
QComboBox::drop-down { border: 0; }
QTextEdit, QPlainTextEdit, QTextBrowser {
    color: #DCE8F8;
    background: #060B16;
    border: 1px solid #29466F;
    border-radius: 9px;
    padding: 7px;
    selection-color: #FFFFFF;
    selection-background-color: #523B9B;
}
QTextEdit:disabled, QPlainTextEdit:disabled, QTextBrowser:disabled {
    color: #65708C; background: #080D18; border-color: #25334E;
}
QAbstractItemView {
    color: #DCE8F8;
    background: #060B16;
    alternate-background-color: #0B1322;
    border: 1px solid #29466F;
    border-radius: 9px;
    outline: 0;
    selection-color: #FFFFFF;
    selection-background-color: #28589C;
}
QAbstractItemView:disabled { color: #65708C; background: #080D18; border-color: #25334E; }
QAbstractItemView::item { color: #DCE8F8; padding: 6px; }
QAbstractItemView::item:hover { color: #FFFFFF; background: #142440; }
QAbstractItemView::item:selected {
    color: #FFFFFF;
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #523B9B,stop:1 #236996);
}
QHeaderView::section {
    color: #CFE1F7; background: #0D1729; border: 0; border-right: 1px solid #29466F;
    border-bottom: 1px solid #3B5E8E; padding: 7px;
}
QTableCornerButton::section { background: #0D1729; border: 1px solid #29466F; }
QProgressBar { background: #070B18; border: 1px solid #273867; border-radius: 5px; height: 9px; text-align: center; }
QProgressBar::chunk { background: #4F7CFF; border-radius: 4px; }
QProgressBar#FlightPlanProgress { min-height: 18px; color: #F5F8FF; font-size: 10px; font-weight: 750; }
QProgressBar#FlightPlanProgress::chunk { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #8C45E8,stop:0.55 #536FFF,stop:1 #2ADCEB); }
QScrollArea, QWidget#ScrollContent { border: 0; background: transparent; }
QScrollArea > QWidget, QScrollArea > QWidget > QWidget { background: transparent; }
QScrollArea::viewport { background: #050A16; }
QScrollArea#NexusScroll, QScrollArea#NexusScroll > QWidget,
QScrollArea#NexusScroll > QWidget > QWidget { background: #02050A; }
QScrollBar:vertical { background: #090D1D; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: #31467F; border-radius: 5px; min-height: 36px; }
QScrollBar::handle:vertical:hover { background: #4F7CFF; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QListWidget#HistoryList { background: #0D1226; border: 1px solid #253462; border-radius: 12px; padding: 7px; outline: 0; }
QListWidget#HistoryList::item { color: #AAB6D3; border-radius: 8px; padding: 12px 10px; margin: 2px; }
QListWidget#HistoryList::item:hover { background: #151F40; color: #EDF4FF; }
QListWidget#HistoryList::item:selected { background: #1B2A5A; color: #63ECF8; }
QSplitter#ArchivesSplitter::handle { background: #17253E; width: 6px; }
QListWidget#ArchivesList {
    background: rgba(6, 11, 23, 245); border: 1px solid #28426C; border-radius: 10px;
    padding: 6px; outline: 0;
}
QListWidget#ArchivesList::item {
    color: #AEBED9; border-radius: 7px; padding: 9px 10px; margin: 1px;
}
QListWidget#ArchivesList::item:hover { color: #FFFFFF; background: rgba(25, 42, 72, 220); }
QListWidget#ArchivesList::item:selected {
    color: #FFFFFF;
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 rgba(87,42,143,235),stop:1 rgba(17,73,96,225));
    border: 1px solid rgba(62, 220, 238, 150);
}
QFrame#SynapseLearningPanel {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 rgba(17,13,43,235),stop:1 rgba(5,31,40,232));
    border: 1px solid rgba(100, 92, 180, 155); border-left: 3px solid #7A75FF; border-radius: 10px;
}
QFrame#SynapseLearningPanel[learningState="verified"] { border-left-color: #44E39A; }
QFrame#SynapseLearningPanel[learningState="attention"] { border-left-color: #FFB454; }
QFrame#SynapseLearningPanel[learningState="unavailable"] { border-left-color: #FF6685; }
QLabel#SynapseLearningTitle { color: #63ECF8; font-size: 10px; font-weight: 850; letter-spacing: 1.15px; }
QPushButton#SynapseLearningAction {
    color: #E7D9FF; background: rgba(46, 24, 76, 220); border: 1px solid rgba(180, 92, 255, 175);
    border-radius: 8px; padding: 8px 12px; font-size: 11px; font-weight: 780;
}
QPushButton#SynapseLearningAction:hover { color: #FFFFFF; border-color: #63ECF8; }
QSplitter#ArchivesLearningSplitter::handle { background: #17253E; width: 6px; }
QListWidget#ArchivesLearningList {
    color: #C9D7ED; background: #060B17; border: 1px solid #28426C; border-radius: 10px;
    padding: 6px; outline: 0;
}
QListWidget#ArchivesLearningList::item { border-radius: 7px; padding: 11px 10px; margin: 2px; }
QListWidget#ArchivesLearningList::item:hover { color: #FFFFFF; background: #13223A; }
QListWidget#ArchivesLearningList::item:selected {
    color: #FFFFFF; background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #54378B,stop:1 #18506A);
    border: 1px solid rgba(77, 221, 238, 155);
}
QTextBrowser#ArchivesLearningDetail {
    color: #DCE9FA; background: #060C19; border: 1px solid #28426C;
    border-radius: 10px; padding: 15px; selection-background-color: #5F3AA8;
}
QLabel#SynapseBoundary {
    color: #8EEAC8; background: rgba(7, 33, 29, 220); border: 1px solid rgba(51, 160, 124, 165);
    border-radius: 8px; padding: 9px 12px; font-size: 10px; font-weight: 780;
}
QTextBrowser#ArchivesDetail {
    color: #DCE9FA; background: rgba(6, 12, 25, 248); border: 1px solid #28426C;
    border-radius: 10px; padding: 15px; selection-background-color: #5F3AA8;
}
QTableWidget#LiveConsoleTable {
    color: #DCE8F8;
    background: #060B16;
    alternate-background-color: #0B1322;
    gridline-color: #223653;
    border: 1px solid #29466F;
    border-radius: 10px;
    outline: 0;
    selection-color: #FFFFFF;
    selection-background-color: #28589C;
}
QTableWidget#LiveConsoleTable::item {
    color: #DCE8F8;
    background: transparent;
    border: 0;
    padding: 7px 6px;
}
QTableWidget#LiveConsoleTable::item:alternate { background: #0B1322; }
QTableWidget#LiveConsoleTable::item:hover { background: #142440; color: #FFFFFF; }
QTableWidget#LiveConsoleTable::item:selected {
    color: #FFFFFF;
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #523B9B,stop:1 #236996);
}
QHeaderView#LiveConsoleHeader::section {
    color: #CFE1F7;
    background: #0D1729;
    border: 0;
    border-right: 1px solid #29466F;
    border-bottom: 1px solid #3B5E8E;
    padding: 8px 7px;
    font-weight: 750;
}
QLineEdit#CommandPaletteSearch { min-height: 30px; border: 1px solid #4869B5; border-radius: 10px; padding: 10px 12px; font-size: 15px; }
QLineEdit#CommandPaletteSearch:focus { border-color: #35E7F5; background: #0D1530; }
QListWidget#CommandPaletteResults { background: #080D1C; border: 1px solid #253C6B; border-radius: 12px; padding: 7px; outline: 0; }
QListWidget#CommandPaletteResults::item { color: #C2CDE3; border-radius: 8px; padding: 8px 11px; margin: 2px; }
QListWidget#CommandPaletteResults::item:hover { background: #151F40; color: #FFFFFF; }
QListWidget#CommandPaletteResults::item:selected { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 rgba(79,45,139,230),stop:1 rgba(18,70,92,225)); color: #FFFFFF; border: 1px solid rgba(53,231,245,145); }
QToolTip {
    color: #F4F8FF;
    background: rgba(7, 13, 29, 246);
    border: 1px solid rgba(77, 221, 244, 175);
    border-radius: 8px;
    padding: 8px 10px;
}
"""


def apply_dark_palette(app: QApplication) -> QPalette:
    """Remove host-theme ambiguity while preserving transparent layered widgets."""

    palette = QPalette()
    for group in (
        QPalette.ColorGroup.Active,
        QPalette.ColorGroup.Inactive,
        QPalette.ColorGroup.Disabled,
    ):
        palette.setColor(group, QPalette.ColorRole.Window, QColor(COLORS["background"]))
        palette.setColor(group, QPalette.ColorRole.WindowText, QColor(COLORS["text"]))
        palette.setColor(group, QPalette.ColorRole.Base, QColor("#060B16"))
        palette.setColor(group, QPalette.ColorRole.AlternateBase, QColor("#0B1322"))
        palette.setColor(group, QPalette.ColorRole.ToolTipBase, QColor("#070D1D"))
        palette.setColor(group, QPalette.ColorRole.ToolTipText, QColor("#F4F8FF"))
        palette.setColor(group, QPalette.ColorRole.Text, QColor("#DCE8F8"))
        palette.setColor(group, QPalette.ColorRole.Button, QColor("#090E19"))
        palette.setColor(group, QPalette.ColorRole.ButtonText, QColor(COLORS["text"]))
        palette.setColor(group, QPalette.ColorRole.BrightText, QColor("#FFFFFF"))
        palette.setColor(group, QPalette.ColorRole.Highlight, QColor("#28589C"))
        palette.setColor(group, QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
        palette.setColor(group, QPalette.ColorRole.Link, QColor(COLORS["cyan"]))
        palette.setColor(group, QPalette.ColorRole.LinkVisited, QColor("#C78AFF"))
        palette.setColor(group, QPalette.ColorRole.PlaceholderText, QColor("#65708C"))
    disabled = QPalette.ColorGroup.Disabled
    for role in (
        QPalette.ColorRole.WindowText,
        QPalette.ColorRole.Text,
        QPalette.ColorRole.ButtonText,
        QPalette.ColorRole.PlaceholderText,
    ):
        palette.setColor(disabled, role, QColor("#65708C"))
    app.setPalette(palette)
    return palette
