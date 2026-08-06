import sys
import math
import json
import os
import urllib.request
import urllib.error
import subprocess
import webbrowser

def resource_path(filename):
    import sys, os
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, filename)
    return filename

CURRENT_VERSION = "v1.0.5"
GITHUB_REPO = "knv0409/BSR-Calculator"
from PyQt5.QtWidgets import *
from PyQt5.QtGui import *
from PyQt5.QtCore import Qt, pyqtSignal, QTimer, QDate, QThread

# --- 데이터 테이블 정의 ---
LEVELS =[1, 20, 30, 40, 50, 60, 70, 80, 90, 100]

CHAR_EXP = {20: 35792, 30: 63484, 40: 117632, 50: 204127, 60: 331578, 70: 503971, 80: 716734, 90: 957145, 100: 1193241}
WEAP_EXP = {20: 19120, 30: 33876, 40: 62756, 50: 108888, 60: 176864, 70: 268808, 80: 382280, 90: 510496, 100: 636384}

CHAR_UNCAP = {
    30: (6, 0, 0, 2500), 40: (12, 0, 0, 5000),
    50: (0, 6, 0, 10000), 60: (0, 10, 0, 15000), 70: (0, 14, 0, 20000),
    80: (0, 0, 6, 30000), 90: (0, 0, 7, 40000), 100: (0, 0, 8, 50000)
}
WEAP_UNCAP = {
    30: (6, 0, 0, 1500), 40: (12, 0, 0, 3000),
    50: (0, 6, 0, 6000), 60: (0, 10, 0, 9000), 70: (0, 14, 0, 12000),
    80: (0, 0, 6, 18000), 90: (0, 0, 7, 24000), 100: (0, 0, 8, 30000)
}

ACTIVE_SKILL = {
    2: (2, 0, 0, 2500), 3: (4, 0, 0, 4000), 4: (8, 0, 0, 7000),
    5: (0, 4, 0, 11000), 6: (0, 7, 0, 18000),
    7: (0, 0, 5, 29000), 8: (0, 0, 7, 46500), 9: (0, 0, 10, 75000)
}

PASSIVE_SKILL = {
    1: {1: (2, 6000), 2: (8, 21500), 3: (14, 70000)},
    2: {1: (4, 10500), 2: (10, 27000), 3: (16, 100000)},
    3: {1: (6, 16500), 2: (12, 43500), 3: (18, 125000)}
}

PROPERTIES =["참술", "백타", "돌격", "영술", "기예"]
TYPES =["강습", "전술", "지원"]
AUTOSAVE_FILE = "BSRCal_autosave.json"

# --- 각인 레벨 및 비용 테이블 ---
ENGRAVE_LEVELS = [1, 10, 15, 20, 25, 30]
# 세트각인 1개당 구간별 비용 (hwan, engrave_exp, engrave_core) × 3개 필요
SET_ENGRAVE_COST = {
    (1, 10):  (14640,   0,  0),
    (10, 15): (29340,  30,  0),
    (15, 20): (52470,  60,  0),
    (20, 25): (79920,  90,  0),
    (25, 30): (120630, 150, 10),
}
# 핵심각인 1개당 구간별 비용 (hwan, engrave_exp) × 1개 필요
CORE_ENGRAVE_COST = {
    (1, 10):  (29280,   0),
    (10, 15): (58680,  60),
    (15, 20): (104940, 120),
    (20, 25): (159840, 180),
    (25, 30): (241260, 300),
}

# --- 스킬 상한 계산 및 아이템 포맷 함수 ---
def get_max_active_lv(char_lv):
    if char_lv >= 80: return 9
    if char_lv >= 70: return 8
    if char_lv >= 60: return 7
    if char_lv >= 50: return 6
    if char_lv >= 40: return 5
    if char_lv >= 30: return 4
    if char_lv >= 20: return 3
    return 2

def get_max_passive_lv(char_lv, p_idx):
    reqs = [[25, 45, 75],[35, 55, 85],[45, 65, 95]]
    if p_idx >= len(reqs): return 0
    lv_req = reqs[p_idx]
    if char_lv >= lv_req[2]: return 3
    if char_lv >= lv_req[1]: return 2
    if char_lv >= lv_req[0]: return 1
    return 0

def resolve_material_shortage(req_n, req_a, req_r, inv_n, inv_a, inv_r):
    """
    등급별 재화 부족량 계산.
    우선순위: 같은 등급 → 상위 등급 분해(1→3) → 하위 등급 조합(3→1)
    처리 순서: 희귀 → 고급 → 일반 (고가 재화 우선 소비)
    """
    n, a, r = inv_n, inv_a, inv_r

    # 희귀 충족
    use = min(r, req_r); r -= use; need_r = req_r - use
    if need_r > 0:  # 하위 조합: 고급3→희귀1
        made = min(a // 3, need_r); a -= made * 3; need_r -= made
    if need_r > 0:  # 하위 조합: 일반9→희귀1
        made = min(n // 9, need_r); n -= made * 9; need_r -= made
    miss_r = need_r

    # 고급 충족
    use = min(a, req_a); a -= use; need_a = req_a - use
    if need_a > 0:  # 상위 분해: 희귀1→고급3
        rare_split = min(r, math.ceil(need_a / 3))
        got = rare_split * 3; r -= rare_split
        used = min(got, need_a); need_a -= used; a += (got - used)
    if need_a > 0:  # 하위 조합: 일반3→고급1
        made = min(n // 3, need_a); n -= made * 3; need_a -= made
    miss_a = need_a

    # 일반 충족
    use = min(n, req_n); n -= use; need_n = req_n - use
    if need_n > 0:  # 상위 분해: 고급1→일반3
        adv_split = min(a, math.ceil(need_n / 3))
        got = adv_split * 3; a -= adv_split
        used = min(got, need_n); need_n -= used
    if need_n > 0:  # 상위 분해: 희귀1→일반9
        rare_split = min(r, math.ceil(need_n / 9))
        got = rare_split * 9; r -= rare_split
        used = min(got, need_n); need_n -= used
    miss_n = need_n

    return max(0, miss_n), max(0, miss_a), max(0, miss_r)

def format_grade_items(miss_n, miss_a, miss_r, c_rare, c_adv, c_nor):
    """희귀/고급/일반 부족량을 HTML 문자열로 포맷."""
    parts = []
    if miss_r: parts.append(f"{c_rare} {miss_r:,}개")
    if miss_a: parts.append(f"{c_adv} {miss_a:,}개")
    if miss_n: parts.append(f"{c_nor} {miss_n:,}개")
    return ", ".join(parts)

def format_item_amount(val, item_type):
    if val <= 0: return ""
    res =[]
    c_leg = "<span style='background-color:#fff3cd; color:#333;'><b>&nbsp;전설&nbsp;</b></span>"
    c_rare = "<span style='background-color:#e2d9f3; color:#333;'><b>&nbsp;희귀&nbsp;</b></span>"
    c_adv = "<span style='background-color:#d0ebff; color:#333;'><b>&nbsp;고급&nbsp;</b></span>"
    c_nor = "<span style='background-color:#d4edda; color:#333;'><b>&nbsp;일반&nbsp;</b></span>"
    
    if item_type == "char_exp":
        leg = val // 20000; rem = val % 20000
        rare = rem // 10000; rem %= 10000
        adv = rem // 3000; rem %= 3000
        nor = math.ceil(rem / 500)
        if leg: res.append(f"{c_leg} {leg:,}개")
        if rare: res.append(f"{c_rare} {rare:,}개")
        if adv: res.append(f"{c_adv} {adv:,}개")
        if nor: res.append(f"{c_nor} {nor:,}개")
    elif item_type == "weap_exp":
        leg = val // 10000; rem = val % 10000
        rare = rem // 5000; rem %= 5000
        adv = rem // 2000; rem %= 2000
        nor = math.ceil(rem / 500)
        if leg: res.append(f"{c_leg} {leg:,}개")
        if rare: res.append(f"{c_rare} {rare:,}개")
        if adv: res.append(f"{c_adv} {adv:,}개")
        if nor: res.append(f"{c_nor} {nor:,}개")
    elif item_type in["ouyi", "yoryung", "hammer"]:
        rare = val // 9; rem = val % 9
        adv = rem // 3; nor = rem % 3
        if rare: res.append(f"{c_rare} {rare:,}개")
        if adv: res.append(f"{c_adv} {adv:,}개")
        if nor: res.append(f"{c_nor} {nor:,}개")
    return ", ".join(res)

# --- 마우스 휠 방지 위젯 정의 ---
class NoScrollSpinBox(QSpinBox):
    def wheelEvent(self, event):
        event.ignore()

class NoScrollComboBox(QComboBox):
    def wheelEvent(self, event):
        event.ignore()

class NoScrollDateEdit(QDateEdit):
    def wheelEvent(self, event):
        event.ignore()
        
class ToggleSwitch(QWidget):
    toggled = pyqtSignal(bool)

    def __init__(self, checked=True, parent=None):
        super().__init__(parent)
        self._checked = checked
        self.setFixedSize(52, 28)
        self.setCursor(Qt.PointingHandCursor)

    def isChecked(self):
        return self._checked

    def setChecked(self, val):
        self._checked = val
        self.update()

    def mouseReleaseEvent(self, e):
        self._checked = not self._checked
        self.toggled.emit(self._checked)
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        # 트랙
        track_color = QColor("#2196F3") if self._checked else QColor("#aaaaaa")
        p.setBrush(track_color)
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(0, 4, 52, 20, 10, 10)
        # 썸
        x = 28 if self._checked else 4
        p.setBrush(QColor("white"))
        p.drawEllipse(x, 2, 24, 24)
        p.end()

class CustomSpinBox(QSpinBox):
    grid_map = {}
    row_max_col = {}
    def __init__(self, r=-1, c=-1, width=70, max_val=999999999, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.r = r; self.c = c
        self._normal_minimum = 0
        self._normal_maximum = max_val
        self._resource_add_mode = False
        self._value_before_edit = 0
        self._applying_delta = False
        self.setRange(self._normal_minimum, self._normal_maximum)
        self.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.editingFinished.connect(self.apply_resource_delta_if_needed)
        if width: self.setFixedWidth(width)
        if r != -1 and c != -1:
            CustomSpinBox.grid_map[(r, c)] = self
            if r not in CustomSpinBox.row_max_col or c > CustomSpinBox.row_max_col[r]:
                CustomSpinBox.row_max_col[r] = c
                
    def wheelEvent(self, event):
        event.ignore()

    def set_resource_add_mode(self, enabled):
        self._resource_add_mode = enabled
        if enabled:
            self.setRange(-self._normal_maximum, self._normal_maximum)
        else:
            self.setRange(self._normal_minimum, self._normal_maximum)

    def focusInEvent(self, event):
        self._value_before_edit = self.value()
        super().focusInEvent(event)
        self.selectAll()

    def apply_resource_delta_if_needed(self):
        if not self._resource_add_mode or self._applying_delta:
            return
        try:
            delta = int(self.lineEdit().text().replace(",", "").strip())
        except ValueError:
            return
        self._applying_delta = True
        self.setValue(max(self._normal_minimum, min(self._normal_maximum, self._value_before_edit + delta)))
        self._value_before_edit = self.value()
        self._applying_delta = False

    def keyPressEvent(self, event):
        if self.r != -1 and self.c != -1:
            if event.key() == Qt.Key_Down: self.navigate(1, 0); return
            elif event.key() == Qt.Key_Up: self.navigate(-1, 0); return
            line_edit = self.findChild(QLineEdit)
            if line_edit:
                if event.key() == Qt.Key_Left:
                    if line_edit.hasSelectedText() or line_edit.cursorPosition() == 0: self.navigate(0, -1); return
                elif event.key() == Qt.Key_Right:
                    if line_edit.hasSelectedText() or line_edit.cursorPosition() == len(line_edit.text()): self.navigate(0, 1); return
        super().keyPressEvent(event)
        
    def navigate(self, dr, dc):
        target_r = self.r + dr; target_c = self.c + dc
        if dr != 0: 
            if target_r in CustomSpinBox.row_max_col: target_c = min(self.c, CustomSpinBox.row_max_col[target_r])
            else: return
        else: 
            if target_c < 0:
                target_r -= 1
                if target_r in CustomSpinBox.row_max_col: target_c = CustomSpinBox.row_max_col[target_r]
                else: return
            elif target_c > CustomSpinBox.row_max_col.get(self.r, 0):
                target_r += 1
                if target_r in CustomSpinBox.row_max_col: target_c = 0
                else: return
        target_widget = CustomSpinBox.grid_map.get((target_r, target_c))
        if target_widget:
            target_widget.setFocus()
            target_widget.selectAll() 
            p = target_widget.parentWidget()
            while p:
                if isinstance(p, QScrollArea): p.ensureWidgetVisible(target_widget); break
                p = p.parentWidget()
                
# ==========================================================
# --- 새 버전 확인 및 팝업창 클래스 ---
# ==========================================================

class VersionCheckThread(QThread):
    version_fetched = pyqtSignal(str, str)
    error_occurred = pyqtSignal(str)

    def run(self):
        try:
            url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req) as response:
                data = json.loads(response.read().decode('utf-8'))
                latest_version = data.get("tag_name", "Unknown")
                download_url = ""
                for asset in data.get("assets",[]):
                    if asset.get("name", "").endswith(".exe"):
                        download_url = asset.get("browser_download_url", "")
                        break
                self.version_fetched.emit(latest_version, download_url)
        except Exception as e:
            self.error_occurred.emit(str(e))

class InfoDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("프로그램 정보")
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)  # ← 추가
        self.setFixedSize(450, 400)
        self.initUI()
        self.check_version()

    def initUI(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        
        lbl_img = QLabel()
        lbl_img.setAlignment(Qt.AlignCenter)
        pixmap = QPixmap(resource_path("info_image.png"))
        if not pixmap.isNull():
            lbl_img.setPixmap(pixmap.scaledToHeight(120, Qt.SmoothTransformation))
        layout.addWidget(lbl_img)

        lbl_title = QLabel("<h2>블리치 소울 레조넌스 종합 계산기</h2>")
        lbl_title.setAlignment(Qt.AlignCenter)
        layout.addWidget(lbl_title)
        
        layout.addSpacing(20)

        lbl_info = QLabel(
            "<p style='text-align:center; font-size:13px;'>"
            "Developed by <b>knv0409</b><br>"
            "with Claude code"
            "</p>"
        )
        lbl_info.setAlignment(Qt.AlignCenter)
        layout.addWidget(lbl_info)
        
        layout.addSpacing(20)

        lbl_links = QLabel(
            "<p style='text-align:center; font-size:12px;'>"
            "<a href='https://github.com/knv0409/BSR-Calculator'>🌐 깃허브(GitHub) 링크</a><br>"
            "<a href='https://www.pixiv.net/users/110879337'>🎨 픽시브(Pixiv) 링크</a>"
            "</p>"
        )
        lbl_links.setOpenExternalLinks(True)
        lbl_links.setAlignment(Qt.AlignCenter)
        layout.addWidget(lbl_links)
        
        layout.addSpacing(20)

        self.lbl_version = QLabel(f"<p style='text-align:center; font-size:13px; color:#555;'>현재 버전: <b>{CURRENT_VERSION}</b><br>최신 버전: 확인 중...</p>")
        self.lbl_version.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.lbl_version)
        
        layout.addSpacing(20)

        self.btn_update = QPushButton("🔄 최신 버전 다운로드 페이지 열기")
        self.btn_update.setStyleSheet("background-color: #007BFF; color: white; font-weight: bold; padding: 10px; border-radius: 5px;")
        self.btn_update.setEnabled(False)
        self.btn_update.clicked.connect(self.open_release_page)
        layout.addWidget(self.btn_update)

    def check_version(self):
        self.v_thread = VersionCheckThread(self)
        self.v_thread.version_fetched.connect(self.on_version_fetched)
        self.v_thread.error_occurred.connect(self.on_version_error)
        self.v_thread.start()
            
    def on_version_fetched(self, latest_version, download_url):
        if latest_version != CURRENT_VERSION:
            # 구버전일 때: 현재 버전은 빨간색, 최신 버전은 파란색으로 강조
            self.lbl_version.setText(
                f"<p style='text-align:center; font-size:13px; color:#555;'>"
                f"현재 버전: <b style='color:#dc3545;'>{CURRENT_VERSION}</b> (업데이트 필요)<br>"
                f"최신 버전: <b style='color:#007BFF;'>{latest_version}</b></p>"
            )
            self.btn_update.setEnabled(True)
            self.btn_update.setStyleSheet("background-color: #28A745; color: white; font-weight: bold; padding: 10px; border-radius: 5px;")
        else:
            # 최신버전일 때: 현재 버전을 초록색으로 표시하여 안심시킴
            self.lbl_version.setText(
                f"<p style='text-align:center; font-size:13px; color:#555;'>"
                f"현재 버전: <b style='color:#28a745;'>{CURRENT_VERSION}</b> (최신 버전입니다)<br>"
                f"최신 버전: <b>{latest_version}</b></p>"
            )

    def on_version_error(self, err_msg):
        self.lbl_version.setText(f"<p style='text-align:center; font-size:13px; color:#555;'>현재 버전: <b>{CURRENT_VERSION}</b><br>최신 버전: <span style='color:red;'>확인 실패</span></p>")

    def open_release_page(self):
        webbrowser.open(f"https://github.com/{GITHUB_REPO}/releases/latest")


class PackageWidget(QFrame):
    deleteRequested = pyqtSignal(int)
    noteChanged = pyqtSignal()
    def __init__(self, pkg_info, parent=None):
        super().__init__(parent)
        self.pkg_info = pkg_info
        self.initUI()
    def initUI(self):
        self.setObjectName("pkgFrame")
        if self.pkg_info.get("is_new", False):
            self.setStyleSheet("#pkgFrame { background-color: #e6f7ff; border: 2px solid #007bff; border-radius: 5px; margin: 2px; }")
        else:
            self.setStyleSheet("#pkgFrame { background-color: white; border: 1px solid #ccc; border-radius: 5px; margin: 2px; }")

        main_vbox = QVBoxLayout(self)
        top_hbox = QHBoxLayout()
        price = self.pkg_info["price"]; yeongok = self.pkg_info["yeongok"]; tickets = self.pkg_info["tickets"]
        total_yeongok = yeongok + (tickets * 160)
        total_pulls = total_yeongok / 160
        base_value_krw = total_yeongok * 20
        multiplier = (base_value_krw / price) if price > 0 else float('inf')
        price_per_pull = (price / total_pulls) if total_pulls > 0 else 0

        info_text = (f"<span style='font-size:16px;'><b>📦 {self.pkg_info['name']}</b></span><br>"
                     f"가격: <b>{price:,}원</b> | 구성: 영옥 {yeongok:,}개, 티켓 {tickets:,}장<br>"
                     f"<span style='color:#555;'>환산 가치: 총 <b>{total_yeongok:,} 영옥</b> ({total_pulls:.1f}뽑 분량)</span>")
        
        eff_text = "<span style='color:#28A745; font-size:16px;'><b>효율: 무료 (∞배)</b></span>" if price == 0 else (f"<span style='color:#28A745; font-size:18px;'><b>효율: {multiplier:.2f}배</b></span><br><span style='color:#e0245e; font-weight:bold;'>1뽑당 {int(price_per_pull):,}원</span>")

        lbl_info = QLabel(info_text); lbl_eff = QLabel(eff_text)
        lbl_eff.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        
        btn_delete = QPushButton("🗑️ 삭제")
        btn_delete.setFixedSize(60, 40)
        btn_delete.setStyleSheet("background-color: #ff4d4f; color: white; font-size: 13px; font-weight: bold; border-radius: 5px;")
        btn_delete.clicked.connect(lambda: self.deleteRequested.emit(self.pkg_info["id"]))

        top_hbox.addWidget(lbl_info); top_hbox.addStretch(); top_hbox.addWidget(lbl_eff); top_hbox.addSpacing(15); top_hbox.addWidget(btn_delete)
        
        bot_hbox = QHBoxLayout()
        bot_hbox.addWidget(QLabel("📝 비고:"))
        self.inp_note = QLineEdit()
        self.inp_note.setText(self.pkg_info.get("note", ""))
        self.inp_note.setPlaceholderText("자유롭게 메모를 입력하세요 (자동 저장됩니다)")
        self.inp_note.setStyleSheet("background-color: #f8f9fa; border: 1px solid #ced4da; border-radius: 3px; padding: 4px;")
        self.inp_note.textChanged.connect(self.update_note)
        bot_hbox.addWidget(self.inp_note)
        main_vbox.addLayout(top_hbox)
        main_vbox.addLayout(bot_hbox)
    def update_note(self, text):
        self.pkg_info["note"] = text
        self.noteChanged.emit()

class SkillDialog(QDialog):
    def __init__(self, parent, name, rarity, char_type, skill_data, char_targ_lv):
        super().__init__(parent)
        self.setWindowTitle(f"{name} - 스킬 및 각인 설정")
        self.skill_data = skill_data
        # 구버전 각인 형식(bool) 호환 처리
        if 'engrave_curr' in skill_data and 'engrave_set1_curr_lv' not in skill_data:
            default_targ = 30 if (not skill_data.get('engrave_curr', False) and skill_data.get('engrave_targ', True)) else 1
            for key in ["set1", "set2", "set3", "core"]:
                skill_data[f"engrave_{key}_curr_lv"] = 1
                skill_data[f"engrave_{key}_targ_lv"] = default_targ
        # 구버전 단일 레벨 형식 호환 처리
        if 'engrave_curr_lv' in skill_data and 'engrave_set1_curr_lv' not in skill_data:
            for key in ["set1", "set2", "set3", "core"]:
                skill_data[f"engrave_{key}_curr_lv"] = skill_data.get('engrave_curr_lv', 1)
                skill_data[f"engrave_{key}_targ_lv"] = skill_data.get('engrave_targ_lv', 1)
        self.char_targ_lv = char_targ_lv
        self.ui_active, self.ui_passive, self.ui_engrave = [], [], []
        self.active_cnt = 5 if char_type == "전술" else 4
        self.passive_cnt = 2 if rarity == "SR" else 3
        self.active_names = ["1. 봉멸", "2. 일반공격", "3. 전투 스킬", "4. 필살기", "5. 전장 스킬"]
        self.passive_names = ["강화 패시브 1", "강화 패시브 2", "강화 패시브 3"]
        self.initUI()
    def initUI(self):
        layout = QVBoxLayout()
        form_layout = QGridLayout()
        form_layout.addWidget(QLabel("<b>[구분]</b>"), 0, 0)
        form_layout.addWidget(QLabel("<b>[현재 레벨]</b>"), 0, 1)
        form_layout.addWidget(QLabel("<b>[목표 레벨]</b>"), 0, 2)
        row = 1
        max_act = get_max_active_lv(self.char_targ_lv)
        for i in range(self.active_cnt):
            lbl = QLabel(self.active_names[i])
            sp_curr = QSpinBox(); sp_curr.setRange(1, 9); sp_curr.setValue(self.skill_data['active_curr'][i])
            sp_targ = QSpinBox(); sp_targ.setRange(1, max(sp_curr.value(), max_act)); sp_targ.setValue(self.skill_data['active_targ'][i])
            sp_curr.valueChanged.connect(lambda val, t=sp_targ: t.setMinimum(val))
            sp_targ.setMinimum(sp_curr.value())
            form_layout.addWidget(lbl, row, 0); form_layout.addWidget(sp_curr, row, 1); form_layout.addWidget(sp_targ, row, 2)
            self.ui_active.append((sp_curr, sp_targ)); row += 1
        for i in range(self.passive_cnt):
            max_pas = get_max_passive_lv(self.char_targ_lv, i)
            lbl = QLabel(self.passive_names[i])
            sp_curr = QSpinBox(); sp_curr.setRange(0, 3); sp_curr.setValue(self.skill_data['passive_curr'][i])
            sp_targ = QSpinBox(); sp_targ.setRange(0, max(sp_curr.value(), max_pas)); sp_targ.setValue(self.skill_data['passive_targ'][i])
            sp_curr.valueChanged.connect(lambda val, t=sp_targ: t.setMinimum(val))
            sp_targ.setMinimum(sp_curr.value())
            form_layout.addWidget(lbl, row, 0); form_layout.addWidget(sp_curr, row, 1); form_layout.addWidget(sp_targ, row, 2)
            self.ui_passive.append((sp_curr, sp_targ)); row += 1
        # 구분선
        sep = QFrame(); sep.setFrameShape(QFrame.HLine); sep.setFrameShadow(QFrame.Sunken)
        form_layout.addWidget(sep, row, 0, 1, 3); row += 1
        # 각인 4개 (세트1,2,3 + 핵심)
        for label, set_key in [("세트각인 1", "set1"), ("세트각인 2", "set2"), ("세트각인 3", "set3"), ("핵심각인", "core")]:
            curr_key = f"engrave_{set_key}_curr_lv"; targ_key = f"engrave_{set_key}_targ_lv"
            curr_val = self.skill_data.get(curr_key, 1); targ_val = self.skill_data.get(targ_key, 1)
            cb_c = QComboBox(); cb_c.addItems([str(x) for x in ENGRAVE_LEVELS]); cb_c.setCurrentText(str(curr_val))
            cb_t = QComboBox(); cb_t.addItems([str(x) for x in ENGRAVE_LEVELS if x >= curr_val]); cb_t.setCurrentText(str(targ_val))
            def make_updater(cb_targ):
                def updater(v):
                    prev = cb_targ.currentText()
                    cb_targ.blockSignals(True); cb_targ.clear()
                    valid = [str(x) for x in ENGRAVE_LEVELS if x >= int(v)]
                    cb_targ.addItems(valid)
                    cb_targ.setCurrentText(prev if prev in valid else str(int(v)))
                    cb_targ.blockSignals(False)
                return updater
            cb_c.currentTextChanged.connect(make_updater(cb_t))
            form_layout.addWidget(QLabel(label), row, 0)
            form_layout.addWidget(cb_c, row, 1)
            form_layout.addWidget(cb_t, row, 2)
            self.ui_engrave.append((curr_key, targ_key, cb_c, cb_t)); row += 1
        layout.addLayout(form_layout)
        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self.save_and_close); btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)
        self.setLayout(layout)
    def save_and_close(self):
        self.skill_data['active_curr'] = [sp[0].value() for sp in self.ui_active]
        self.skill_data['active_targ'] = [sp[1].value() for sp in self.ui_active]
        self.skill_data['passive_curr'] = [sp[0].value() for sp in self.ui_passive]
        self.skill_data['passive_targ'] = [sp[1].value() for sp in self.ui_passive]
        for curr_key, targ_key, cb_c, cb_t in self.ui_engrave:
            self.skill_data[curr_key] = int(cb_c.currentText())
            self.skill_data[targ_key] = int(cb_t.currentText())
        self.skill_data.pop('engrave_curr', None); self.skill_data.pop('engrave_targ', None)
        self.skill_data.pop('engrave_curr_lv', None); self.skill_data.pop('engrave_targ_lv', None)
        self.accept()

class CharacterWidget(QFrame):
    deleteRequested = pyqtSignal(object)
    growthRequested = pyqtSignal(object)
    growthCancelRequested = pyqtSignal(object)
    def __init__(self, char_info, parent=None):
        super().__init__(parent)
        self.setObjectName("charFrame")
        self.char_info = char_info
        ac_cnt = 5 if char_info["type"] == "전술" else 4
        pa_cnt = 2 if char_info["rarity"] == "SR" else 3
        self.skill_data = {"active_curr":[1]*ac_cnt, "active_targ": [9]*ac_cnt, "passive_curr": [0]*pa_cnt, "passive_targ":[3]*pa_cnt,
                           "engrave_set1_curr_lv": 1, "engrave_set1_targ_lv": 30,
                           "engrave_set2_curr_lv": 1, "engrave_set2_targ_lv": 30,
                           "engrave_set3_curr_lv": 1, "engrave_set3_targ_lv": 30,
                           "engrave_core_curr_lv": 1, "engrave_core_targ_lv": 30}
        self._growth_done = False
        self._cost_snapshot = {}
        self.initUI()
        self.update_active_style()
    def initUI(self):
        main_layout = QHBoxLayout()
        info_layout = QVBoxLayout()
        self.lbl_info = QLabel(f"<b>{self.char_info['name']}</b><br>[{self.char_info['rarity']}] {self.char_info['prop']} / {self.char_info['type']}")
        self.lbl_info.setMinimumWidth(150)
        info_layout.addWidget(self.lbl_info)
        self.chk_active = QCheckBox("✅ 계산 포함 (On/Off)")
        self.chk_active.setChecked(self.char_info.get("is_active", True))
        self.chk_active.setStyleSheet("color: #007BFF; font-weight: bold;")
        self.chk_active.stateChanged.connect(self.update_active_style)
        info_layout.addWidget(self.chk_active)
        main_layout.addLayout(info_layout)
        
        level_layout = QGridLayout()
        level_strs =[str(x) for x in LEVELS]
        self.cb_char_curr = QComboBox(); self.cb_char_curr.addItems(level_strs)
        self.cb_char_targ = QComboBox(); self.cb_char_targ.addItems(level_strs)
        self.cb_weap_curr = QComboBox(); self.cb_weap_curr.addItems(level_strs)
        self.cb_weap_targ = QComboBox(); self.cb_weap_targ.addItems(level_strs)
        self.cb_char_curr.currentTextChanged.connect(self.update_char_target_options)
        self.cb_char_targ.currentTextChanged.connect(self.auto_adjust_skills_on_level_change)
        self.cb_weap_curr.currentTextChanged.connect(self.update_weap_target_options)
        self.cb_char_targ.setCurrentText("100"); self.cb_weap_targ.setCurrentText("100")
        # 💡 setHorizontalSpacing(숫자)를 통해 격자 사이의 여백을 픽셀 단위로 조절합니다.
        level_layout.setHorizontalSpacing(0) 

        level_layout.addWidget(QLabel("캐릭터 Lv:"), 0, 0); level_layout.addWidget(self.cb_char_curr, 0, 1)
        level_layout.addWidget(QLabel("➔"), 0, 2, Qt.AlignCenter); level_layout.addWidget(self.cb_char_targ, 0, 3)
        
        level_layout.addWidget(QLabel("무기 Lv:"), 1, 0); level_layout.addWidget(self.cb_weap_curr, 1, 1)
        level_layout.addWidget(QLabel("➔"), 1, 2, Qt.AlignCenter); level_layout.addWidget(self.cb_weap_targ, 1, 3)
        
        main_layout.addLayout(level_layout)
        
        ctrl_layout = QHBoxLayout()
        left_col = QVBoxLayout()
        self.btn_skill = QPushButton("⚙️ 스킬/각인 설정")
        self.btn_skill.clicked.connect(lambda: SkillDialog(self, self.char_info['name'], self.char_info['rarity'], self.char_info['type'], self.skill_data, int(self.cb_char_targ.currentText())).exec_())
        self.btn_growth = QPushButton("✅ 성장 완료")
        self.btn_growth.setStyleSheet("color: #28A745; font-weight: bold;")
        self.btn_growth.clicked.connect(self._on_growth_clicked)
        left_col.addWidget(self.btn_skill); left_col.addWidget(self.btn_growth)
        btn_delete = QPushButton("🗑️ 삭제"); btn_delete.setStyleSheet("color: red; font-weight: bold;"); btn_delete.setFixedWidth(70)
        def confirm_delete():
            if QMessageBox.question(self, "삭제 확인",
                f"'{self.char_info['name']}'을(를) 정말 삭제하겠습니까?",
                QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
                self.deleteRequested.emit(self)
        btn_delete.clicked.connect(confirm_delete)
        ctrl_layout.addLayout(left_col)
        ctrl_layout.addSpacing(20)
        ctrl_layout.addWidget(btn_delete, alignment=Qt.AlignVCenter)
        main_layout.addLayout(ctrl_layout)
        self.setLayout(main_layout)
    def update_active_style(self):
        if self.chk_active.isChecked():
            self.setStyleSheet("QFrame#charFrame { background-color: white; border: 1px solid #ccc; border-radius: 5px; }")
            self.lbl_info.setStyleSheet("color: black;")
            self.cb_char_curr.setEnabled(True); self.cb_char_targ.setEnabled(True)
            self.cb_weap_curr.setEnabled(True); self.cb_weap_targ.setEnabled(True)
            self.btn_skill.setEnabled(True)
        else:
            self.setStyleSheet("QFrame#charFrame { background-color: #f0f0f0; border: 2px dashed #aaa; border-radius: 5px; }")
            self.lbl_info.setStyleSheet("color: gray;")
            self.cb_char_curr.setEnabled(False); self.cb_char_targ.setEnabled(False)
            self.cb_weap_curr.setEnabled(False); self.cb_weap_targ.setEnabled(False)
            self.btn_skill.setEnabled(False)
    def update_char_target_options(self, curr_text):
        curr_val = int(curr_text); prev_target = self.cb_char_targ.currentText()
        self.cb_char_targ.blockSignals(True)
        self.cb_char_targ.clear()
        self.cb_char_targ.addItems([str(x) for x in LEVELS if x >= curr_val])
        self.cb_char_targ.setCurrentText(prev_target if int(prev_target) >= curr_val else str(curr_val))
        self.cb_char_targ.blockSignals(False)
    def auto_adjust_skills_on_level_change(self, targ_text):
        if not targ_text: return
        targ_lv = int(targ_text)
        max_act = get_max_active_lv(targ_lv)
        self.skill_data["active_targ"] =[max_act] * len(self.skill_data["active_targ"])
        for i in range(len(self.skill_data["passive_targ"])):
            self.skill_data["passive_targ"][i] = get_max_passive_lv(targ_lv, i)
    def update_weap_target_options(self, curr_text):
        curr_val = int(curr_text); prev_target = self.cb_weap_targ.currentText()
        self.cb_weap_targ.clear()
        self.cb_weap_targ.addItems([str(x) for x in LEVELS if x >= curr_val])
        self.cb_weap_targ.setCurrentText(prev_target if int(prev_target) >= curr_val else str(curr_val))
    def _on_growth_clicked(self):
        if self._growth_done: self.growthCancelRequested.emit(self)
        else: self.growthRequested.emit(self)
    def set_growth_done(self, cost):
        self._growth_done = True; self._cost_snapshot = cost
        self.chk_active.setChecked(False); self.chk_active.setEnabled(False)
        self.btn_growth.setText("🔄 성장 취소"); self.btn_growth.setStyleSheet("color: #e0245e; font-weight: bold;")
    def set_growth_undone(self):
        self._growth_done = False; self._cost_snapshot = {}
        self.chk_active.setEnabled(True); self.chk_active.setChecked(True)
        self.btn_growth.setText("✅ 성장 완료"); self.btn_growth.setStyleSheet("color: #28A745; font-weight: bold;")
    def get_data(self):
        data = self.char_info.copy()
        data["is_active"] = self.chk_active.isChecked()
        data["char_curr"] = int(self.cb_char_curr.currentText())
        data["char_targ"] = int(self.cb_char_targ.currentText())
        data["weap_curr"] = int(self.cb_weap_curr.currentText())
        data["weap_targ"] = int(self.cb_weap_targ.currentText())
        data["skill_data"] = self.skill_data
        data["growth_done"] = self._growth_done
        data["growth_snapshot"] = self._cost_snapshot
        return data
    def set_data(self, data):
        self.chk_active.setChecked(data.get("is_active", True))
        self.update_active_style()
        self.cb_char_curr.setCurrentText(str(data.get("char_curr", 1)))
        self.cb_char_targ.blockSignals(True)
        self.cb_char_targ.setCurrentText(str(data.get("char_targ", 100)))
        self.cb_char_targ.blockSignals(False)
        self.cb_weap_curr.setCurrentText(str(data.get("weap_curr", 1)))
        self.cb_weap_targ.setCurrentText(str(data.get("weap_targ", 100)))
        sd = data.get("skill_data", self.skill_data)
        # 구버전 bool 형식 호환
        if 'engrave_curr' in sd and 'engrave_set1_curr_lv' not in sd:
            default_targ = 30 if (not sd.get('engrave_curr', False) and sd.get('engrave_targ', True)) else 1
            for key in ["set1", "set2", "set3", "core"]:
                sd[f"engrave_{key}_curr_lv"] = 1; sd[f"engrave_{key}_targ_lv"] = default_targ
        # 구버전 단일 레벨 형식 호환
        if 'engrave_curr_lv' in sd and 'engrave_set1_curr_lv' not in sd:
            for key in ["set1", "set2", "set3", "core"]:
                sd[f"engrave_{key}_curr_lv"] = sd.get('engrave_curr_lv', 1)
                sd[f"engrave_{key}_targ_lv"] = sd.get('engrave_targ_lv', 1)
        self.skill_data = sd
        # 성장완료 상태 복원
        self._growth_done = data.get("growth_done", False)
        self._cost_snapshot = data.get("growth_snapshot", {})
        if self._growth_done:
            self.chk_active.setEnabled(False)
            self.btn_growth.setText("🔄 성장 취소"); self.btn_growth.setStyleSheet("color: #e0245e; font-weight: bold;")


class BleachCalcApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.bg_enabled = True
        self.setWindowTitle(f"블리치 소울 레조넌스 종합 계산기  |  {CURRENT_VERSION}")
        self.resize(860, 850)
        self.char_widgets =[]
        self.inv_inputs = {}
        self.packages =[]
        self.pkg_id_counter = 1
        self.selected_dungeon_levels = {}
        self.init_dungeon_drops()
        
        central = QWidget()
        main_layout = QVBoxLayout(central)
        top_bar = QHBoxLayout()
        
        self.setup_top_toolbar(top_bar)
        top_bar.addStretch()
        
        self.chk_top = QCheckBox("📌 창을 항상 위에 고정")
        self.chk_top.stateChanged.connect(self.toggle_top)
        top_bar.addWidget(self.chk_top)
        
        self.tabs = QTabWidget()
        main_layout.addLayout(top_bar)
        main_layout.addWidget(self.tabs)
        self.setCentralWidget(central)
        
        self.initUI()
        self.load_autosave()

    def setup_top_toolbar(self, top_bar_layout):
        btn_style = """
            QPushButton {
                background-color: #ffffff;
                border: 1px solid #dcdcdc;
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 13px;
                font-weight: bold;
                color: #333333;
            }
            QPushButton:hover {
                background-color: #f0f0f0;
                border: 1px solid #b0b0b0;
            }
            QPushButton:pressed {
                background-color: #e0e0e0;
            }
        """
        
        btn_load = QPushButton("📂 설정 불러오기")
        btn_load.setStyleSheet(btn_style)
        btn_load.clicked.connect(self.load_from_file)
        
        btn_save = QPushButton("💾 다른 이름으로 저장")
        btn_save.setStyleSheet(btn_style)
        btn_save.clicked.connect(self.save_as_file)
        
        btn_info = QPushButton("ℹ️ 정보 및 업데이트")
        btn_info.setStyleSheet(btn_style)
        btn_info.clicked.connect(self.show_info_dialog)
        
        self.btn_toggle_bg = ToggleSwitch(checked=True)
        self.btn_toggle_bg.toggled.connect(lambda checked: self.toggle_background())
        
        bg_toggle_wrap = QWidget()
        bg_toggle_layout = QHBoxLayout(bg_toggle_wrap)
        bg_toggle_layout.setContentsMargins(0, 0, 0, 0)
        bg_toggle_layout.setSpacing(5)
        bg_toggle_layout.addWidget(QLabel("배경 표시"))
        bg_toggle_layout.addWidget(self.btn_toggle_bg)
        
        top_bar_layout.addWidget(btn_load)
        top_bar_layout.addWidget(btn_save)
        top_bar_layout.addWidget(btn_info)
        top_bar_layout.addWidget(bg_toggle_wrap)

    def toggle_background(self):
        self.bg_enabled = not self.bg_enabled
        self.btn_toggle_bg.setChecked(self.bg_enabled)  # ← 이 줄로 교체 (setText 대신)
        self.update_backgrounds()

    def update_backgrounds(self):
        from PyQt5.QtCore import QEvent, QObject
        from PyQt5.QtGui import QPixmap

        # 최초 1회만 QLabel과 ResizeFilter 생성
        if not hasattr(self, '_bg_initialized'):
            class ResizeFilter(QObject):
                def __init__(self, callback):
                    super().__init__()
                    self._cb = callback
                def eventFilter(self, obj, event):
                    if event.type() == QEvent.Resize:
                        self._cb()
                    return False

            self._bg_filter = ResizeFilter(self._reposition_bg_labels)
            self.tab_char.installEventFilter(self._bg_filter)
            self.tab_inv.installEventFilter(self._bg_filter)
            self.tab_result.installEventFilter(self._bg_filter)
            self.tab_package.installEventFilter(self._bg_filter)

            self.bg_lbl1 = QLabel(self.tab_char)
            self.bg_lbl1.setAttribute(Qt.WA_TransparentForMouseEvents)
            self.bg_lbl1.lower()
            self.bg_lbl1.show()

            self.bg_lbl2 = QLabel(self.tab_inv)
            self.bg_lbl2.setAttribute(Qt.WA_TransparentForMouseEvents)
            self.bg_lbl2.lower()
            self.bg_lbl2.show()
            
            self.bg_lbl3 = QLabel(self.tab_result)
            self.bg_lbl3.setAttribute(Qt.WA_TransparentForMouseEvents)
            self.bg_lbl3.lower()
            self.bg_lbl3.show()

            self.bg_lbl4 = QLabel(self.tab_package)
            self.bg_lbl4.setAttribute(Qt.WA_TransparentForMouseEvents)
            self.bg_lbl4.lower()
            self.bg_lbl4.show()

            # ── 투명화: setStyleSheet 대신 setAutoFillBackground(False) 사용 ──
            # setStyleSheet("background: transparent")는 자식 위젯에 cascade되어
            # QComboBox·QPushButton·QSpinBox까지 투명하게 만드는 부작용이 있음.
            # setAutoFillBackground(False)는 해당 위젯의 배경 자동 채우기만 끄고
            # 자식 위젯에는 전혀 영향을 주지 않는다.
            self.tab_char.setAutoFillBackground(False)
            self.tab_inv.setAutoFillBackground(False)
            self.tab_result.setAutoFillBackground(False)
            self.tab_package.setAutoFillBackground(False)

            self.scroll_area.setAutoFillBackground(False)
            self.scroll_area.viewport().setAutoFillBackground(False)
            self.list_widget.setAutoFillBackground(False)

            self.inv_scroll.setAutoFillBackground(False)
            self.inv_scroll.viewport().setAutoFillBackground(False)
            self.inv_container.setAutoFillBackground(False)

            self.pkg_scroll.setAutoFillBackground(False)
            self.pkg_scroll.viewport().setAutoFillBackground(False)
            self.pkg_container.setAutoFillBackground(False)

            self._bg_initialized = True

        # 픽스맵 로드 또는 클리어
        import random
        bg_images = [resource_path(f"bg{i}.webp") for i in range(1, 14)]  # ← 파일 목록 원하는 만큼 추가
        if self.bg_enabled:
            self._bg_pixmap1 = QPixmap(random.choice(bg_images))
            self._bg_pixmap2 = QPixmap(random.choice(bg_images))
            self._bg_pixmap3 = QPixmap(random.choice(bg_images))
            self._bg_pixmap4 = QPixmap(random.choice(bg_images))
        else:
            self._bg_pixmap1 = QPixmap()
            self._bg_pixmap2 = QPixmap()
            self._bg_pixmap3 = QPixmap()
            self._bg_pixmap4 = QPixmap()

        self._reposition_bg_labels()

    def _reposition_bg_labels(self):
        if not hasattr(self, 'bg_lbl1'):
            return
        from PyQt5.QtGui import QPixmap
        for lbl, tab, pix in [
            (self.bg_lbl1, self.tab_char,    getattr(self, '_bg_pixmap1', QPixmap())),
            (self.bg_lbl2, self.tab_inv,     getattr(self, '_bg_pixmap2', QPixmap())),
            (self.bg_lbl3, self.tab_result,  getattr(self, '_bg_pixmap3', QPixmap())),
            (self.bg_lbl4, self.tab_package, getattr(self, '_bg_pixmap4', QPixmap())),
        ]:
            if not pix.isNull():
                iw, ih = pix.width(), pix.height()
                x = max(0, tab.width()  - iw)
                y = max(0, tab.height() - ih)
                opacity = 1  # 0.0 (완전 투명) ~ 1.0 (완전 불투명), 원하는 값으로 조절
                tmp = QPixmap(pix.size())
                tmp.fill(Qt.transparent)
                painter = QPainter(tmp)
                painter.setOpacity(opacity)
                painter.drawPixmap(0, 0, pix)
                painter.end()
                lbl.setPixmap(tmp)
                lbl.setGeometry(x, y, iw, ih)
            else:
                lbl.clear()
                lbl.setGeometry(0, 0, 0, 0)
            lbl.lower()

    def show_info_dialog(self):
        dialog = InfoDialog(self)
        dialog.exec_()

    def load_from_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "설정 불러오기", "", "JSON Files (*.json)")
        if path:
            self.apply_save_data(path)
            QMessageBox.information(self, "완료", "설정을 성공적으로 불러왔습니다.")

    def save_as_file(self):
        path, _ = QFileDialog.getSaveFileName(self, "다른 이름으로 저장", "my_bleach_save.json", "JSON Files (*.json)")
        if path:
            self.export_save_data(path)
            QMessageBox.information(self, "완료", "설정을 성공적으로 저장했습니다.")

    def restore_default_size(self):
        self.resize(860, 850)

    def get_preset_packages(self):
        return[
            {"id": 1, "name": "월간 패스 회원권", "price": 5900, "yeongok": 3300, "tickets": 0, "note": "GOAT", "is_new": False},
            {"id": 2, "name": "수행수기(배틀패스)", "price": 12000, "yeongok": 680, "tickets": 10, "note": "12,000원짜리 픽업 한정 패키지와 효율은 같지만 배틀패스가 재료템을 더 많이줌", "is_new": False},
            {"id": 3, "name": "공홈 전용 10뽑", "price": 5900, "yeongok": 0, "tickets": 10, "note": "월 1회 한정", "is_new": False},
            {"id": 4, "name": "여정 시작 지원", "price": 25000, "yeongok": 1280, "tickets": 42, "note": "1회 제한", "is_new": False},
            {"id": 5, "name": "루키아 패키지(빙설의 여정)", "price": 1200, "yeongok": 300, "tickets": 2, "note": "1회 제한", "is_new": False},
            {"id": 6, "name": "컬렉션 소집 선물상자", "price": 30000, "yeongok": 1680, "tickets": 20, "note": "매 픽업 당 1회 제한", "is_new": False}
        ]

    def init_dungeon_drops(self):
        self.dungeon_drops = {
            "현세 순찰 (캐릭터 경험치)": {
                "Lv.70": {"char_exp_legend": 1, "char_exp_rare": 3, "char_exp_advanced": 4, "hwan": 2200},
                "Lv.60": {"char_exp_legend": 1, "char_exp_rare": 2, "char_exp_advanced": 5, "hwan": 2000},
                "Lv.50": {"char_exp_rare": 3, "char_exp_advanced": 6, "hwan": 1700},
                "Lv.40": {"char_exp_rare": 3, "char_exp_advanced": 4, "hwan": 1400},
            },
            "자금 수집 (환)": {
                "Lv.70": {"hwan": 45600}, "Lv.60": {"hwan": 41000},
                "Lv.50": {"hwan": 36400}, "Lv.40": {"hwan": 31900},
            },
            "호로 토벌 (무기 경험치)": {
                "Lv.70": {"weap_exp_legend": 3, "weap_exp_rare": 3, "weap_exp_advanced": 2, "hwan": 2200},
                "Lv.60": {"weap_exp_legend": 3, "weap_exp_rare": 2, "weap_exp_advanced": 2, "hwan": 2000},
                "Lv.50": {"weap_exp_rare": 6, "weap_exp_advanced": 5, "hwan": 1700},
                "Lv.40": {"weap_exp_rare": 5, "weap_exp_advanced": 4, "hwan": 1400},
            },
            "혼백의 호위 (각인의 영질)": {
                "Lv.70": {"engrave_exp": 50, "hwan": 2200}, "Lv.60": {"engrave_exp": 45, "hwan": 2000},
                "Lv.50": {"engrave_exp": 40, "hwan": 1700}, "Lv.40": {"engrave_exp": 35, "hwan": 1400},
            }
        }
        for p in PROPERTIES:
            self.dungeon_drops[f"학원 특훈 [{p}] (요령)"] = {
                "Lv.70": {f"yoryung_{p}_rare": 1, f"yoryung_{p}_advanced": 3, f"yoryung_{p}_normal": 4, "hwan": 2200},
                "Lv.60": {f"yoryung_{p}_rare": 1, f"yoryung_{p}_advanced": 2, f"yoryung_{p}_normal": 3, "hwan": 2000},
                "Lv.50": {f"yoryung_{p}_advanced": 3, f"yoryung_{p}_normal": 6, "hwan": 1700},
                "Lv.40": {f"yoryung_{p}_advanced": 2, f"yoryung_{p}_normal": 6, "hwan": 1400},
            }
            self.dungeon_drops[f"카라쿠라 수비 [{p}] (오의)"] = {
                "Lv.70": {f"ouyi_{p}_rare": 1, f"ouyi_{p}_advanced": 2, "hwan": 2200},
                "Lv.60": {f"ouyi_{p}_advanced": 4, f"ouyi_{p}_normal": 2, "hwan": 2000},
                "Lv.50": {f"ouyi_{p}_advanced": 4, "hwan": 1700},
                "Lv.40": {f"ouyi_{p}_advanced": 3, f"ouyi_{p}_normal": 1, "hwan": 1400},
            }
            self.dungeon_drops[f"호정 연습 [{p}] (망치)"] = {
                "Lv.70": {f"hammer_{p}_rare": 2, "hwan": 2200},
                "Lv.60": {f"hammer_{p}_rare": 1, f"hammer_{p}_advanced": 2, "hwan": 2000},
                "Lv.50": {f"hammer_{p}_advanced": 4, f"hammer_{p}_normal": 2, "hwan": 1700},
                "Lv.40": {f"hammer_{p}_advanced": 3, f"hammer_{p}_normal": 3, "hwan": 1400},
            }
        for t in TYPES:
            self.dungeon_drops[f"호로 무리 정화 [{t}] (오마모리)"] = {
                "Lv.75": {f"omamori_{t}": 8, "hwan": 4400}, "Lv.65": {f"omamori_{t}": 7, "hwan": 4000},
                "Lv.55": {f"omamori_{t}": 6, "hwan": 3400}, "Lv.45": {f"omamori_{t}": 6, "hwan": 2800},
            }

    def toggle_top(self, state):
        if state == Qt.Checked: self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        else: self.setWindowFlags(self.windowFlags() & ~Qt.WindowStaysOnTopHint)
        self.show()

    def closeEvent(self, event):
        self.save_autosave()
        event.accept()

    def initUI(self):
        self.tab_char = QWidget(); self.setup_char_tab(); self.tabs.addTab(self.tab_char, "1. 캐릭터 설정")
        self.tab_inv = QWidget(); self.setup_inv_tab(); self.tabs.addTab(self.tab_inv, "2. 보유 재화 상세 입력")
        self.tab_result = QWidget(); self.setup_result_tab(); self.tabs.addTab(self.tab_result, "3. 결과 및 파밍 플랜")
        self.tab_package = QWidget(); self.setup_package_tab(); self.tabs.addTab(self.tab_package, "4. 패키지 효율 계산")
        self.tab_planner = QWidget(); self.setup_planner_tab(); self.tabs.addTab(self.tab_planner, "5. 가챠/과금 플래너")
        self.tabs.currentChanged.connect(self.update_backgrounds)
        self.update_backgrounds()
        # 기존 끝부분에 아래 3줄 추가
        self.dungeon_scroll.setAutoFillBackground(False)
        self.dungeon_scroll.viewport().setAutoFillBackground(False)
        self.dungeon_container.setAutoFillBackground(False)

    # ==========================
    # 1~4번 탭
    # ==========================
    def setup_char_tab(self):
        main_layout = QVBoxLayout(self.tab_char)
        add_group = QGroupBox("새로운 캐릭터 추가")
        add_layout = QVBoxLayout()
        row1 = QHBoxLayout()
        self.inp_name = QLineEdit(); self.inp_name.setPlaceholderText("캐릭터 이름")
        self.inp_rarity = QComboBox(); self.inp_rarity.addItems(["SSR", "SR"])
        self.inp_prop = QComboBox(); self.inp_prop.addItems(PROPERTIES)
        self.inp_type = QComboBox(); self.inp_type.addItems(TYPES)
        btn_add = QPushButton("➕ 추가하기")
        btn_add.setStyleSheet("background-color: #007BFF; color: white; font-weight: bold; padding: 5px;")
        btn_add.clicked.connect(self.add_character)
        for w in[QLabel("이름:"), self.inp_name, QLabel("등급:"), self.inp_rarity, QLabel("속성:"), self.inp_prop, QLabel("타입:"), self.inp_type, btn_add]:
            row1.addWidget(w)
        add_layout.addLayout(row1)
        add_group.setLayout(add_layout)
        main_layout.addWidget(add_group)
        main_layout.addWidget(QLabel("<b>[등록된 육성 대기열]</b> (체크박스 해제 시 계산에서 제외됩니다)"))
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.list_widget = QWidget()
        self.list_layout = QVBoxLayout()
        self.list_layout.setAlignment(Qt.AlignTop)
        self.list_widget.setLayout(self.list_layout)
        self.scroll_area.setWidget(self.list_widget)
        main_layout.addWidget(self.scroll_area)

    def add_character(self):
        name = self.inp_name.text()
        if not name: return QMessageBox.warning(self, "경고", "캐릭터 이름을 입력하세요.")
        char_info = {"name": name, "rarity": self.inp_rarity.currentText(), "prop": self.inp_prop.currentText(), "type": self.inp_type.currentText(), "is_active": True}
        widget = CharacterWidget(char_info)
        widget.deleteRequested.connect(self.remove_character)
        widget.growthRequested.connect(self.on_growth_requested)
        widget.growthCancelRequested.connect(self.on_growth_cancel_requested)
        self.list_layout.addWidget(widget)
        self.char_widgets.append(widget)
        self.inp_name.clear()

    def remove_character(self, widget):
        self.list_layout.removeWidget(widget)
        self.char_widgets.remove(widget)
        widget.deleteLater()

    def _calc_char_req(self, c):
        """단일 캐릭터 필요 재화 계산 (등급별 추적)."""
        req = {"hwan": 0, "char_exp": 0, "weap_exp": 0, "engrave_exp": 0, "engrave_core": 0}
        for p in PROPERTIES:
            for g in ["normal", "advanced", "rare"]:
                req[f"ouyi_{p}_{g}"] = 0; req[f"hammer_{p}_{g}"] = 0; req[f"yoryung_{p}_{g}"] = 0
        for t in TYPES: req[f"omamori_{t}"] = 0
        req["omamori_universal"] = 0
        prop = c["prop"]; ctype = c["type"]
        for lv in LEVELS:
            if lv > 1 and c["char_curr"] < lv <= c["char_targ"]:
                req["char_exp"] += CHAR_EXP[lv]
                if lv in CHAR_UNCAP:
                    nor, adv, rar, hw = CHAR_UNCAP[lv]
                    req[f"ouyi_{prop}_normal"] += nor; req[f"ouyi_{prop}_advanced"] += adv
                    req[f"ouyi_{prop}_rare"] += rar; req["hwan"] += hw
        for lv in LEVELS:
            if lv > 1 and c["weap_curr"] < lv <= c["weap_targ"]:
                req["weap_exp"] += WEAP_EXP[lv]
                if lv in WEAP_UNCAP:
                    nor, adv, rar, hw = WEAP_UNCAP[lv]
                    req[f"hammer_{prop}_normal"] += nor; req[f"hammer_{prop}_advanced"] += adv
                    req[f"hammer_{prop}_rare"] += rar; req["hwan"] += hw
        for start_lv, targ_lv in zip(c["skill_data"]["active_curr"], c["skill_data"]["active_targ"]):
            for lv in range(start_lv + 1, targ_lv + 1):
                nor, adv, rar, hw = ACTIVE_SKILL[lv]
                req[f"yoryung_{prop}_normal"] += nor; req[f"yoryung_{prop}_advanced"] += adv
                req[f"yoryung_{prop}_rare"] += rar; req["hwan"] += hw
        for idx, (start_lv, targ_lv) in enumerate(zip(c["skill_data"]["passive_curr"], c["skill_data"]["passive_targ"])):
            p_id = idx + 1
            for lv in range(start_lv + 1, targ_lv + 1):
                req[f"omamori_{ctype}"] += PASSIVE_SKILL[p_id][lv][0]; req["hwan"] += PASSIVE_SKILL[p_id][lv][1]
        if 'engrave_set1_curr_lv' in c["skill_data"]:
            for set_key, cost_table in [("set1", SET_ENGRAVE_COST), ("set2", SET_ENGRAVE_COST), ("set3", SET_ENGRAVE_COST), ("core", CORE_ENGRAVE_COST)]:
                curr_elv = c["skill_data"].get(f"engrave_{set_key}_curr_lv", 1)
                targ_elv = c["skill_data"].get(f"engrave_{set_key}_targ_lv", 1)
                if curr_elv < targ_elv:
                    for i in range(len(ENGRAVE_LEVELS) - 1):
                        seg_s, seg_e = ENGRAVE_LEVELS[i], ENGRAVE_LEVELS[i+1]
                        if seg_s >= curr_elv and seg_e <= targ_elv:
                            if cost_table is SET_ENGRAVE_COST:
                                sh, se, sc = SET_ENGRAVE_COST[(seg_s, seg_e)]
                                req["hwan"] += sh; req["engrave_exp"] += se; req["engrave_core"] += sc
                            else:
                                ch, ce = CORE_ENGRAVE_COST[(seg_s, seg_e)]
                                req["hwan"] += ch; req["engrave_exp"] += ce
        elif not c["skill_data"].get("engrave_curr", False) and c["skill_data"].get("engrave_targ", True):
            req["hwan"] += 1485000; req["engrave_exp"] += 1650; req["engrave_core"] += 30
        req["hwan"] += req["char_exp"] // 5; req["hwan"] += req["weap_exp"] // 5
        return req

    def _get_owned_pts(self):
        """현재 보유 재화를 포인트 기준으로 반환."""
        owned = {
            "hwan": self.inv_inputs["hwan"].value(),
            "engrave_exp": self.inv_inputs["engrave_exp"].value(),
            "engrave_core": self.inv_inputs["engrave_core"].value(),
            "char_exp": (self.inv_inputs["char_exp_normal"].value() * 500 + self.inv_inputs["char_exp_advanced"].value() * 3000 +
                         self.inv_inputs["char_exp_rare"].value() * 10000 + self.inv_inputs["char_exp_legend"].value() * 20000),
            "weap_exp": (self.inv_inputs["weap_exp_normal"].value() * 500 + self.inv_inputs["weap_exp_advanced"].value() * 2000 +
                         self.inv_inputs["weap_exp_rare"].value() * 5000 + self.inv_inputs["weap_exp_legend"].value() * 10000),
        }
        for p in PROPERTIES:
            owned[f"ouyi_{p}"] = self.inv_inputs[f"ouyi_{p}_normal"].value() + self.inv_inputs[f"ouyi_{p}_advanced"].value() * 3 + self.inv_inputs[f"ouyi_{p}_rare"].value() * 9
            owned[f"hammer_{p}"] = self.inv_inputs[f"hammer_{p}_normal"].value() + self.inv_inputs[f"hammer_{p}_advanced"].value() * 3 + self.inv_inputs[f"hammer_{p}_rare"].value() * 9
            owned[f"yoryung_{p}"] = self.inv_inputs[f"yoryung_{p}_normal"].value() + self.inv_inputs[f"yoryung_{p}_advanced"].value() * 3 + self.inv_inputs[f"yoryung_{p}_rare"].value() * 9
        for t in TYPES: owned[f"omamori_{t}"] = self.inv_inputs[f"omamori_{t}"].value()
        return owned

    def _deduct_pts(self, prefix, total_pts, grades):
        """EXP 포인트 단위로 등급 재화를 지정 순서대로 차감 (경력/접쇠용)."""
        if total_pts <= 0: return
        remaining = total_pts
        for suffix, val in grades:
            key = f"{prefix}{suffix}"
            if key in self.inv_inputs and remaining > 0:
                available = self.inv_inputs[key].value()
                use = min(available, math.ceil(remaining / val))
                if use > 0:
                    self.inv_inputs[key].setValue(available - use)
                    remaining -= use * val

    def _deduct_grade_material(self, prefix, req_n, req_a, req_r):
        if req_n == 0 and req_a == 0 and req_r == 0: return
        n = self.inv_inputs[f"{prefix}_normal"].value()
        a = self.inv_inputs[f"{prefix}_advanced"].value()
        r = self.inv_inputs[f"{prefix}_rare"].value()

    # 1. 희귀 소비
        use_r = min(r, req_r); r -= use_r; need_r = req_r - use_r
    # 부족한 희귀는 고급 조합으로 충당
        if need_r > 0:
            made = min(a // 3, need_r); a -= made * 3; need_r -= made
    # 그래도 부족하면 일반 조합으로 충당
        if need_r > 0:
            made = min(n // 9, need_r); n -= made * 9; need_r -= made

    # 2. 고급 소비
        use_a = min(a, req_a); a -= use_a; need_a = req_a - use_a
    # 부족한 고급은 희귀 분해로 충당
        if need_a > 0:
            split = min(r, math.ceil(need_a / 3))
            got = split * 3; r -= split
            used = min(got, need_a); need_a -= used; a += (got - used)  # 잉여 고급 반환
    # 그래도 부족하면 일반 조합
        if need_a > 0:
            made = min(n // 3, need_a); n -= made * 3; need_a -= made

    # 3. 일반 소비
        use_n = min(n, req_n); n -= use_n; need_n = req_n - use_n
    # 부족한 일반은 고급 분해로 충당
        if need_n > 0:
            split = min(a, math.ceil(need_n / 3))
            got = split * 3; a -= split
            used = min(got, need_n); need_n -= used; n += (got - used)  # 잉여 일반 반환
        # 그래도 부족하면 희귀 분해로 충당 (희귀→일반 9배)
        if need_n > 0:
            split = min(r, math.ceil(need_n / 9))
            got = split * 9; r -= split
            used = min(got, need_n); need_n -= used; n += (got - used)  # 잉여 일반 반환
    
        self.inv_inputs[f"{prefix}_normal"].setValue(max(0, n))
        self.inv_inputs[f"{prefix}_advanced"].setValue(max(0, a))
        self.inv_inputs[f"{prefix}_rare"].setValue(max(0, r))
    
    def _req_key_label(self, key):
        if key == "hwan": return "환"
        if key == "char_exp": return "캐릭터 경력"
        if key == "weap_exp": return "무기 접쇠"
        if key == "engrave_exp": return "각인의 영질"
        if key == "engrave_core": return "각인의 핵심"
        for p in PROPERTIES:
            for prefix, label in [("yoryung", "요령"), ("hammer", "망치"), ("ouyi", "오의")]:
                for g, gl in [("normal", "일반"), ("advanced", "고급"), ("rare", "희귀")]:
                    if key == f"{prefix}_{p}_{g}": return f"{label} {gl} ({p})"
        for t in TYPES:
            if key == f"omamori_{t}": return f"오마모리 ({t})"
        if key == "omamori_universal": return "범용 오마모리"
        if key == "yoryung_universal": return "범용 요령"
        return key

    def on_growth_requested(self, widget):
        c = widget.get_data()
        req = self._calc_char_req(c)
        # 부족 여부 판단 (교환 로직 적용)
        missing_lines = []
        # 단순 재화
        for key in ["hwan", "engrave_exp", "engrave_core"]:
            have = self.inv_inputs[key].value() if key in self.inv_inputs else 0
            if req[key] > have:
                missing_lines.append(f"  • {self._req_key_label(key)}: {req[key]-have:,} 부족")
        # 경력 (EXP 합산)
        char_have = (self.inv_inputs["char_exp_normal"].value()*500 + self.inv_inputs["char_exp_advanced"].value()*3000 +
                     self.inv_inputs["char_exp_rare"].value()*10000 + self.inv_inputs["char_exp_legend"].value()*20000)
        if req["char_exp"] > char_have:
            missing_lines.append(f"  • 캐릭터 경력: {req['char_exp']-char_have:,} EXP 부족")
        # 접쇠 (EXP 합산)
        weap_have = (self.inv_inputs["weap_exp_normal"].value()*500 + self.inv_inputs["weap_exp_advanced"].value()*2000 +
                     self.inv_inputs["weap_exp_rare"].value()*5000 + self.inv_inputs["weap_exp_legend"].value()*10000)
        if req["weap_exp"] > weap_have:
            missing_lines.append(f"  • 무기 접쇠: {req['weap_exp']-weap_have:,} EXP 부족")
        # 등급별 재화
        prop = c["prop"]
        for prefix, label in [("yoryung", "요령"), ("hammer", "망치"), ("ouyi", "오의")]:
            rn = req[f"{prefix}_{prop}_normal"]; ra = req[f"{prefix}_{prop}_advanced"]; rr = req[f"{prefix}_{prop}_rare"]
            hn = self.inv_inputs[f"{prefix}_{prop}_normal"].value()
            if prefix == "yoryung": hn += self.inv_inputs["yoryung_universal"].value()
            ha = self.inv_inputs[f"{prefix}_{prop}_advanced"].value()
            hr = self.inv_inputs[f"{prefix}_{prop}_rare"].value()
            mn, ma, mr = resolve_material_shortage(rn, ra, rr, hn, ha, hr)
            if mn: missing_lines.append(f"  • {label} 일반({prop}): {mn:,}개 부족")
            if ma: missing_lines.append(f"  • {label} 고급({prop}): {ma:,}개 부족")
            if mr: missing_lines.append(f"  • {label} 희귀({prop}): {mr:,}개 부족")
        ctype = c["type"]
        for t in TYPES:
            need = req.get(f"omamori_{t}", 0)
            have = self.inv_inputs[f"omamori_{t}"].value()
            universal = self.inv_inputs["omamori_universal"].value()
            if need > have + universal: missing_lines.append(f"  • {t} 오마모리: {need-have-universal:,}개 부족")

        if missing_lines:
            msg = "다음 재화가 부족합니다:\n" + "\n".join(missing_lines) + "\n\n그래도 성장완료 처리하겠습니까?"
            if QMessageBox.question(self, "재화 부족", msg, QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
                return

        snapshot = {k: v.value() for k, v in self.inv_inputs.items()}
        # 차감 전 실제 소비량 추적용 cost 딕셔너리
        cost = {}
        def deduct_and_track(key, amount):
            before = self.inv_inputs[key].value()
            self.inv_inputs[key].setValue(max(0, before - amount))
            cost[key] = cost.get(key, 0) + (before - self.inv_inputs[key].value())

        deduct_and_track("hwan", req["hwan"])
        deduct_and_track("engrave_exp", req["engrave_exp"])
        deduct_and_track("engrave_core", req["engrave_core"])

        # 경력: 하위 등급부터
        for suffix, val in [("_normal", 500), ("_advanced", 3000), ("_rare", 10000), ("_legend", 20000)]:
            key = f"char_exp{suffix}"
            if key in self.inv_inputs and req["char_exp"] > 0:
                before = self.inv_inputs[key].value()
                use = min(before, math.ceil(req["char_exp"] / val))
                self.inv_inputs[key].setValue(before - use)
                cost[key] = cost.get(key, 0) + use
                req["char_exp"] = max(0, req["char_exp"] - use * val)

        # 접쇠: 하위 등급부터
        for suffix, val in [("_normal", 500), ("_advanced", 2000), ("_rare", 5000), ("_legend", 10000)]:
            key = f"weap_exp{suffix}"
            if key in self.inv_inputs and req["weap_exp"] > 0:
                before = self.inv_inputs[key].value()
                use = min(before, math.ceil(req["weap_exp"] / val))
                self.inv_inputs[key].setValue(before - use)
                cost[key] = cost.get(key, 0) + use
                req["weap_exp"] = max(0, req["weap_exp"] - use * val)

        # 등급별 재화: 차감 전후 차이로 비용 기록
        for prefix in ["yoryung", "hammer", "ouyi"]:
            for g in ["normal", "advanced", "rare"]:
                key = f"{prefix}_{prop}_{g}"
                cost[key] = self.inv_inputs[key].value()
            if prefix == "yoryung":
                cost["yoryung_universal"] = self.inv_inputs["yoryung_universal"].value()
            if prefix == "yoryung":
                normal_key = f"{prefix}_{prop}_normal"
                universal_key = "yoryung_universal"
                specific, universal = self.inv_inputs[normal_key].value(), self.inv_inputs[universal_key].value()
                self.inv_inputs[normal_key].setValue(specific + universal)
                self._deduct_grade_material(f"{prefix}_{prop}", req[f"{prefix}_{prop}_normal"], req[f"{prefix}_{prop}_advanced"], req[f"{prefix}_{prop}_rare"])
                remaining = self.inv_inputs[normal_key].value()
                self.inv_inputs[universal_key].setValue(min(universal, remaining))
                self.inv_inputs[normal_key].setValue(remaining - self.inv_inputs[universal_key].value())
            else:
                self._deduct_grade_material(f"{prefix}_{prop}", req[f"{prefix}_{prop}_normal"], req[f"{prefix}_{prop}_advanced"], req[f"{prefix}_{prop}_rare"])
            for g in ["normal", "advanced", "rare"]:
                key = f"{prefix}_{prop}_{g}"
                cost[key] = cost[key] - self.inv_inputs[key].value()  # 차감된 양
            if prefix == "yoryung": cost["yoryung_universal"] -= self.inv_inputs["yoryung_universal"].value()

        for t in TYPES:
            need = req.get(f"omamori_{t}", 0)
            if need > 0:
                key = f"omamori_{t}"
                before = self.inv_inputs[key].value()
                used_specific = min(before, need)
                self.inv_inputs[key].setValue(before - used_specific)
                cost[key] = cost.get(key, 0) + used_specific
                remaining = need - used_specific
                if remaining:
                    universal_key = "omamori_universal"; universal_before = self.inv_inputs[universal_key].value()
                    used_universal = min(universal_before, remaining)
                    self.inv_inputs[universal_key].setValue(universal_before - used_universal)
                    cost[universal_key] = cost.get(universal_key, 0) + used_universal

        widget.set_growth_done(cost)
        self.save_autosave()

    def on_growth_cancel_requested(self, widget):
        # 비용만큼 정확히 돌려줌 (순서 무관)
        for k, v in widget._cost_snapshot.items():
            if k in self.inv_inputs and v > 0:
                self.inv_inputs[k].setValue(self.inv_inputs[k].value() + v)
        widget.set_growth_undone()
        self.save_autosave()

    def export_save_data(self, path):
        roster_data =[w.get_data() for w in self.char_widgets]
        inv_data = {k: v.value() for k, v in self.inv_inputs.items()}
        pkg_data =[]
        for p in self.packages:
            p_copy = p.copy()
            p_copy['is_new'] = False
            pkg_data.append(p_copy)
        timeline_data = []
        for i in range(self.p_timeline_layout.count()):
            w = self.p_timeline_layout.itemAt(i).widget()
            if w:
                timeline_data.append({
                    "name": w.findChild(QLineEdit, "pickup_name").text(),
                    "start": w.findChild(QDateEdit, "start_date").date().toString("yyyy-MM-dd"),
                    "char": w.findChild(QComboBox, "cb_char").currentText(),
                    "weap": w.findChild(QComboBox, "cb_weap").currentText(),
                })
        planner_data = {
            "yeongok": self.p_curr_yeongok.value(),
            "char_t": self.p_curr_char_t.value(),
            "weap_t": self.p_curr_weap_t.value(),
            "cert": self.p_curr_cert.value(),
            "c_pity": self.p_curr_c_pity.value(),
            "w_pity": self.p_curr_w_pity.value(),
            "cert_done": self.p_chk_cert_done.isChecked(),
            "pickup_done": self.p_chk_pickup_done.isChecked(),
            "date_start": self.p_date_start.date().toString("yyyy-MM-dd"),
            "date_end": self.p_date_end.date().toString("yyyy-MM-dd"),
            "timeline": timeline_data,
            "chk_monthly": self.p_chk_monthly.isChecked(),
            "sp_monthly_days": self.p_sp_monthly_days.value(),
            "sp_monthly_cnt": self.p_sp_monthly_cnt.value(),
            "chk_webchar": self.p_chk_webchar.isChecked(),
            "sp_webchar_cnt": self.p_sp_webchar_cnt.value(),
            "chk_webweap": self.p_chk_webweap.isChecked(),
            "sp_webweap_cnt": self.p_sp_webweap_cnt.value(),
            "chk_bp": self.p_chk_bp.isChecked(),
            "sp_bp_cnt": self.p_sp_bp_cnt.value(),
            "chk_pickcol": self.p_chk_pickcol.isChecked(),
            "sp_pickcol_cnt": self.p_sp_pickcol_cnt.value(),
            "chk_pickchar": self.p_chk_pickchar.isChecked(),
            "sp_pickchar_cnt": self.p_sp_pickchar_cnt.value(),
            "chk_pickweap": self.p_chk_pickweap.isChecked(),
            "sp_pickweap_cnt": self.p_sp_pickweap_cnt.value(),
        }
        data = {"window_size":[self.width(), self.height()], "roster": roster_data, "inventory": inv_data, "packages": pkg_data, "bg_enabled": self.bg_enabled, "planner": planner_data}
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
        except: pass

    def save_autosave(self):
        self.export_save_data(AUTOSAVE_FILE)

    def apply_save_data(self, path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            sz = data.get("window_size",[860, 850])
            self.resize(sz[0], sz[1])
            while self.char_widgets:
                self.remove_character(self.char_widgets[0])
            for item in data.get("roster",[]):
                w = CharacterWidget({"name": item["name"], "rarity": item["rarity"], "prop": item["prop"], "type": item["type"]})
                w.set_data(item)
                w.deleteRequested.connect(self.remove_character)
                w.growthRequested.connect(self.on_growth_requested)
                w.growthCancelRequested.connect(self.on_growth_cancel_requested)
                self.list_layout.addWidget(w)
                self.char_widgets.append(w)
            for k, v in data.get("inventory", {}).items():
                if k in self.inv_inputs:
                    self.inv_inputs[k].setValue(v)
            self.packages = data.get("packages",[])
            if not self.packages:
                self.packages = self.get_preset_packages()
                self.pkg_id_counter = 7
            else:
                self.pkg_id_counter = max([p["id"] for p in self.packages]) + 1
            self.render_packages()

            # ↓ 여기서부터 추가
            pl = data.get("planner", {})
            if pl:
                self.p_curr_yeongok.setValue(pl.get("yeongok", 0))
                self.p_curr_char_t.setValue(pl.get("char_t", 0))
                self.p_curr_weap_t.setValue(pl.get("weap_t", 0))
                self.p_curr_cert.setValue(pl.get("cert", 0))
                self.p_curr_c_pity.setValue(pl.get("c_pity", 0))
                self.p_curr_w_pity.setValue(pl.get("w_pity", 0))
                self.p_chk_cert_done.setChecked(pl.get("cert_done", False))
                self.p_chk_pickup_done.setChecked(pl.get("pickup_done", False))
                self.p_date_start.setDate(QDate.fromString(pl.get("date_start", QDate.currentDate().toString("yyyy-MM-dd")), "yyyy-MM-dd"))
                self.p_date_end.setDate(QDate.fromString(pl.get("date_end", QDate.currentDate().addDays(30).toString("yyyy-MM-dd")), "yyyy-MM-dd"))

                # 타임라인 복원
                while self.p_timeline_layout.count():
                    item = self.p_timeline_layout.takeAt(0)
                    if item.widget(): item.widget().deleteLater()
                for tl in pl.get("timeline", []):
                    self.add_planner_timeline()
                    w = self.p_timeline_layout.itemAt(self.p_timeline_layout.count() - 1).widget()
                    if w:
                        w.findChild(QLineEdit, "pickup_name").setText(tl.get("name", ""))
                        w.findChild(QDateEdit, "start_date").setDate(QDate.fromString(tl.get("start", ""), "yyyy-MM-dd"))
                        w.findChild(QComboBox, "cb_char").setCurrentText(tl.get("char", "패스"))
                        w.findChild(QComboBox, "cb_weap").setCurrentText(tl.get("weap", "패스"))

                self.p_chk_monthly.setChecked(pl.get("chk_monthly", False))
                self.p_sp_monthly_days.setValue(pl.get("sp_monthly_days", 0))
                self.p_sp_monthly_cnt.setValue(pl.get("sp_monthly_cnt", 0))
                self.p_chk_webchar.setChecked(pl.get("chk_webchar", False))
                self.p_sp_webchar_cnt.setValue(pl.get("sp_webchar_cnt", 0))
                self.p_chk_webweap.setChecked(pl.get("chk_webweap", False))
                self.p_sp_webweap_cnt.setValue(pl.get("sp_webweap_cnt", 0))
                self.p_chk_bp.setChecked(pl.get("chk_bp", False))
                self.p_sp_bp_cnt.setValue(pl.get("sp_bp_cnt", 0))
                self.p_chk_pickcol.setChecked(pl.get("chk_pickcol", False))
                self.p_sp_pickcol_cnt.setValue(pl.get("sp_pickcol_cnt", 0))
                self.p_chk_pickchar.setChecked(pl.get("chk_pickchar", False))
                self.p_sp_pickchar_cnt.setValue(pl.get("sp_pickchar_cnt", 0))
                self.p_chk_pickweap.setChecked(pl.get("chk_pickweap", False))
                self.p_sp_pickweap_cnt.setValue(pl.get("sp_pickweap_cnt", 0))
            self.bg_enabled = data.get("bg_enabled", True)   # ← 추가
            self.btn_toggle_bg.setChecked(self.bg_enabled)    # ← 추가
            self.update_backgrounds()
        except Exception as e:
            if path == AUTOSAVE_FILE:
                self.resize(860, 850)
                self.packages = self.get_preset_packages()
                self.pkg_id_counter = 7
                self.render_packages()

    def load_autosave(self):
        if os.path.exists(AUTOSAVE_FILE): self.apply_save_data(AUTOSAVE_FILE)
        else:
            self.resize(860, 850)
            self.packages = self.get_preset_packages()
            self.pkg_id_counter = 7
            self.render_packages()
            self.bg_enabled = True

    def get_colored_grade_label(self, text):
        lbl = QLabel(text)
        lbl.setAlignment(Qt.AlignCenter)
        colors = {"일반": "#d4edda", "고급": "#d0ebff", "희귀": "#e2d9f3", "전설": "#fff3cd"}
        color = colors.get(text, "transparent")
        lbl.setStyleSheet(f"background-color: {color}; border-radius: 4px; padding: 4px; font-weight: bold; color: #333;")
        return lbl

    def get_colored_prop_label(self, prop_name):
        lbl = QLabel(f"{prop_name} 속성")
        lbl.setAlignment(Qt.AlignCenter)
        colors = {"참술": "#f8d7da", "백타": "#ffdfba", "돌격": "#fff3cd", "영술": "#d0ebff", "기예": "#e2d9f3"}
        color = colors.get(prop_name, "transparent")
        lbl.setStyleSheet(f"background-color: {color}; border-radius: 4px; padding: 4px; font-weight: bold; color: #333;")
        return lbl

    def _inventory_item_label(self, key):
        direct_labels = {
            "hwan": "환", "engrave_exp": "각인의 영질", "engrave_core": "각인의 핵심",
            "omamori_universal": "범용 오마모리", "yoryung_universal": "범용 요령",
        }
        if key in direct_labels:
            return direct_labels[key]
        grade_labels = {"normal": "일반", "advanced": "고급", "rare": "희귀", "legend": "전설"}
        if key.startswith("char_exp_"):
            return f"캐릭터 경력 - {grade_labels[key.removeprefix('char_exp_')]}"
        if key.startswith("weap_exp_"):
            return f"무기 접쇠 - {grade_labels[key.removeprefix('weap_exp_')]}"
        for t in TYPES:
            if key == f"omamori_{t}":
                return f"{t} 오마모리"
        for prop in PROPERTIES:
            for prefix, label in [("yoryung", "요령"), ("hammer", "망치"), ("ouyi", "오의")]:
                for grade, grade_label in grade_labels.items():
                    if key == f"{prefix}_{prop}_{grade}":
                        return f"{prop} {label} - {grade_label}"
        return key

    def set_resource_add_mode(self, enabled):
        for spinbox in self.inv_inputs.values():
            if isinstance(spinbox, CustomSpinBox):
                spinbox.set_resource_add_mode(enabled)
        self.inv_scroll.viewport().setStyleSheet("background-color: #fff8e1;" if enabled else "")
        self.btn_resource_add_mode.setText("➖ 재화 추가 모드 해제" if enabled else "➕ 재화 추가 모드")
        self.btn_resource_add_mode.setStyleSheet(
            "background-color: #f0ad4e; color: #222; font-weight: bold; padding: 6px 12px;"
            if enabled else
            "background-color: #17a2b8; color: white; font-weight: bold; padding: 6px 12px;"
        )

    def setup_inv_tab(self):
        CustomSpinBox.grid_map.clear()
        CustomSpinBox.row_max_col.clear()
        # ── self.inv_scroll, self.inv_container 로 승격 ──
        # update_backgrounds()에서 setAutoFillBackground(False) 호출이 필요하기 때문
        self.inv_scroll = QScrollArea()
        self.inv_scroll.setWidgetResizable(True)
        self.inv_container = QWidget()
        layout = QVBoxLayout(self.inv_container)
        current_r = 0
        g_top = QGroupBox("💰 공통, 각인 및 패시브 재화")
        l_top_main = QVBoxLayout()
        row1 = QHBoxLayout()
        self.inv_inputs["hwan"] = CustomSpinBox(r=current_r, c=0, width=110)
        self.inv_inputs["engrave_exp"] = CustomSpinBox(r=current_r, c=1, width=70)
        self.inv_inputs["engrave_core"] = CustomSpinBox(r=current_r, c=2, width=70)
        row1.addWidget(QLabel("보유 환:")); row1.addWidget(self.inv_inputs["hwan"])
        row1.addSpacing(10)
        row1.addWidget(QLabel("각인의 영질:")); row1.addWidget(self.inv_inputs["engrave_exp"])
        row1.addSpacing(10)
        row1.addWidget(QLabel("각인의 핵심 (별사탕):")); row1.addWidget(self.inv_inputs["engrave_core"])
        row1.addStretch()
        current_r += 1
        row2 = QHBoxLayout()
        for c_idx, t in enumerate(TYPES):
            sp = CustomSpinBox(r=current_r, c=c_idx, width=70)
            self.inv_inputs[f"omamori_{t}"] = sp
            row2.addWidget(QLabel(f"[{t}] 오마모리:")); row2.addWidget(sp)
            row2.addSpacing(5)
        self.inv_inputs["omamori_universal"] = CustomSpinBox(r=current_r, c=len(TYPES), width=70)
        row2.addWidget(QLabel("범용 오마모리:")); row2.addWidget(self.inv_inputs["omamori_universal"])
        row2.addStretch()
        current_r += 1
        action_row = QHBoxLayout()
        self.btn_resource_add_mode = QPushButton("➕ 재화 추가 모드")
        self.btn_resource_add_mode.setCheckable(True)
        self.btn_resource_add_mode.setStyleSheet("background-color: #17a2b8; color: white; font-weight: bold; padding: 6px 12px;")
        self.btn_resource_add_mode.toggled.connect(self.set_resource_add_mode)
        action_row.addWidget(self.btn_resource_add_mode)
        action_row.addWidget(QLabel("모드 중에는 입력한 수량만큼 더하거나 뺍니다. (예: 50, -50)"))
        action_row.addStretch()
        l_top_main.addLayout(row1); l_top_main.addLayout(row2); l_top_main.addLayout(action_row)
        g_top.setLayout(l_top_main); layout.addWidget(g_top)

        def apply_compact_grid(grid, spacer_col):
            grid.setHorizontalSpacing(15); grid.setColumnStretch(spacer_col, 1)

        g_char_exp = QGroupBox("📘 경력 - 캐릭터 경험치")
        l_char_exp = QGridLayout()
        l_char_exp.addWidget(QLabel("<b>[구분]</b>"), 0, 0)
        for c, t in enumerate(["일반", "고급", "희귀", "전설"], 1): l_char_exp.addWidget(self.get_colored_grade_label(t), 0, c)
        l_char_exp.addWidget(QLabel("경력 보유량"), 1, 0)
        for c, suffix in enumerate(["_normal", "_advanced", "_rare", "_legend"]):
            sp = CustomSpinBox(r=current_r, c=c, width=70)
            self.inv_inputs[f"char_exp{suffix}"] = sp
            l_char_exp.addWidget(sp, 1, c + 1)
        apply_compact_grid(l_char_exp, 5)
        g_char_exp.setLayout(l_char_exp); layout.addWidget(g_char_exp)
        current_r += 1

        g_yoryung = QGroupBox("📜 요령 - 액티브 스킬 재료")
        l_yoryung = QGridLayout()
        l_yoryung.addWidget(QLabel("<b>[속성]</b>"), 0, 0)
        for c, t in enumerate(["일반", "고급", "희귀"], 1): l_yoryung.addWidget(self.get_colored_grade_label(t), 0, c)
        l_yoryung.addWidget(QLabel("범용 요령"), 1, 0)
        self.inv_inputs["yoryung_universal"] = CustomSpinBox(r=current_r, c=0, width=70)
        l_yoryung.addWidget(self.inv_inputs["yoryung_universal"], 1, 1)
        current_r += 1
        for r_idx, prop in enumerate(PROPERTIES):
            l_yoryung.addWidget(self.get_colored_prop_label(prop), r_idx + 2, 0)
            for c, suffix in enumerate(["_normal", "_advanced", "_rare"]):
                sp = CustomSpinBox(r=current_r, c=c, width=70)
                self.inv_inputs[f"yoryung_{prop}{suffix}"] = sp
                l_yoryung.addWidget(sp, r_idx + 2, c + 1)
            current_r += 1
        apply_compact_grid(l_yoryung, 4)
        g_yoryung.setLayout(l_yoryung); layout.addWidget(g_yoryung)

        g_weap_exp = QGroupBox("🗡️ 접쇠 - 무기 경험치")
        l_weap_exp = QGridLayout()
        l_weap_exp.addWidget(QLabel("<b>[구분]</b>"), 0, 0)
        for c, t in enumerate(["일반", "고급", "희귀", "전설"], 1): l_weap_exp.addWidget(self.get_colored_grade_label(t), 0, c)
        l_weap_exp.addWidget(QLabel("접쇠 보유량"), 1, 0)
        for c, suffix in enumerate(["_normal", "_advanced", "_rare", "_legend"]):
            sp = CustomSpinBox(r=current_r, c=c, width=70)
            self.inv_inputs[f"weap_exp{suffix}"] = sp
            l_weap_exp.addWidget(sp, 1, c + 1)
        apply_compact_grid(l_weap_exp, 5)
        g_weap_exp.setLayout(l_weap_exp); layout.addWidget(g_weap_exp)
        current_r += 1

        g_hammer = QGroupBox("🔨 망치 - 무기 해방 재료")
        l_hammer = QGridLayout()
        l_hammer.addWidget(QLabel("<b>[속성]</b>"), 0, 0)
        for c, t in enumerate(["일반", "고급", "희귀"], 1): l_hammer.addWidget(self.get_colored_grade_label(t), 0, c)
        for r_idx, prop in enumerate(PROPERTIES):
            l_hammer.addWidget(self.get_colored_prop_label(prop), r_idx + 1, 0)
            for c, suffix in enumerate(["_normal", "_advanced", "_rare"]):
                sp = CustomSpinBox(r=current_r, c=c, width=70)
                self.inv_inputs[f"hammer_{prop}{suffix}"] = sp
                l_hammer.addWidget(sp, r_idx + 1, c + 1)
            current_r += 1
        apply_compact_grid(l_hammer, 4)
        g_hammer.setLayout(l_hammer); layout.addWidget(g_hammer)

        g_ouyi = QGroupBox("🔮 오의 - 캐릭터 해방 재료")
        l_ouyi = QGridLayout()
        l_ouyi.addWidget(QLabel("<b>[속성]</b>"), 0, 0)
        for c, t in enumerate(["일반", "고급", "희귀"], 1): l_ouyi.addWidget(self.get_colored_grade_label(t), 0, c)
        for r_idx, prop in enumerate(PROPERTIES):
            l_ouyi.addWidget(self.get_colored_prop_label(prop), r_idx + 1, 0)
            for c, suffix in enumerate(["_normal", "_advanced", "_rare"]):
                sp = CustomSpinBox(r=current_r, c=c, width=70)
                self.inv_inputs[f"ouyi_{prop}{suffix}"] = sp
                l_ouyi.addWidget(sp, r_idx + 1, c + 1)
            current_r += 1
        apply_compact_grid(l_ouyi, 4)
        g_ouyi.setLayout(l_ouyi); layout.addWidget(g_ouyi)
        self.inv_scroll.setWidget(self.inv_container)
        main_layout = QVBoxLayout(self.tab_inv)
        main_layout.addWidget(self.inv_scroll)

    def setup_result_tab(self):
        main_layout = QVBoxLayout(self.tab_result)
        btn_calc = QPushButton("✨ 필요 재화 자동 합산 및 계산 (새로고침)")
        btn_calc.setMinimumHeight(50)
        btn_calc.setStyleSheet("font-size: 16px; font-weight: bold; background-color: #28A745; color: white;")
        btn_calc.clicked.connect(lambda: self.calculate_resources(is_refresh=True))
        main_layout.addWidget(btn_calc)
        self.btn_toggle_total = QPushButton("▼ 전체 필요 재화량 보기 (접혀있음)")
        self.btn_toggle_total.setStyleSheet("background-color: #f8f9fa; border: 1px solid #ddd; padding: 5px;")
        self.btn_toggle_total.clicked.connect(self.toggle_total_req)
        main_layout.addWidget(self.btn_toggle_total)
        self.total_req_container = QWidget()
        total_layout = QVBoxLayout(self.total_req_container)
        total_layout.setContentsMargins(0, 0, 0, 0)
        self.lbl_total_req = QLabel()
        self.lbl_total_req.setTextFormat(Qt.RichText)
        self.lbl_total_req.setWordWrap(True)
        self.lbl_total_req.setStyleSheet("background-color: #fff; border: 1px solid #ccc; padding: 8px;")
        total_layout.addWidget(self.lbl_total_req)
        self.total_req_container.setVisible(False)
        main_layout.addWidget(self.total_req_container)
        self.result_summary = QLabel()
        self.result_summary.setTextFormat(Qt.RichText)
        self.result_summary.setWordWrap(True)
        main_layout.addWidget(self.result_summary)
        self.dungeon_scroll = QScrollArea()
        self.dungeon_scroll.setWidgetResizable(True)
        self.dungeon_container = QWidget()
        self.dungeon_layout = QVBoxLayout(self.dungeon_container)
        self.dungeon_layout.setAlignment(Qt.AlignTop)
        self.dungeon_scroll.setWidget(self.dungeon_container)
        main_layout.addWidget(self.dungeon_scroll, stretch=1)

    def toggle_total_req(self):
        is_visible = not self.total_req_container.isVisible()
        self.total_req_container.setVisible(is_visible)
        self.btn_toggle_total.setText("▲ 전체 필요 재화량 숨기기" if is_visible else "▼ 전체 필요 재화량 보기 (접혀있음)")

    def setup_package_tab(self):
        layout = QVBoxLayout(self.tab_package)
        add_group = QGroupBox("새로운 패키지 효율 계산 추가")
        form_layout = QVBoxLayout()
        row1 = QHBoxLayout()
        self.pkg_name = QLineEdit(); self.pkg_name.setPlaceholderText("패키지 이름")
        self.pkg_price = QSpinBox(); self.pkg_price.setRange(0, 99999999); self.pkg_price.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.pkg_yeongok = QSpinBox(); self.pkg_yeongok.setRange(0, 99999999); self.pkg_yeongok.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.pkg_tickets = QSpinBox(); self.pkg_tickets.setRange(0, 99999999); self.pkg_tickets.setButtonSymbols(QAbstractSpinBox.NoButtons)
        row1.addWidget(QLabel("이름:")); row1.addWidget(self.pkg_name, stretch=2)
        row1.addWidget(QLabel("가격(원):")); row1.addWidget(self.pkg_price, stretch=1)
        row1.addWidget(QLabel("영옥:")); row1.addWidget(self.pkg_yeongok, stretch=1)
        row1.addWidget(QLabel("티켓:")); row1.addWidget(self.pkg_tickets, stretch=1)
        form_layout.addLayout(row1)
        row2 = QHBoxLayout()
        self.pkg_note = QLineEdit(); self.pkg_note.setPlaceholderText("비고 (자유 입력, 리스트에서도 수정 가능)")
        btn_add_pkg = QPushButton("➕ 효율 계산 추가")
        btn_add_pkg.setStyleSheet("background-color: #17a2b8; color: white; font-weight: bold; padding: 6px;")
        btn_add_pkg.clicked.connect(self.add_package)
        row2.addWidget(QLabel("비고:")); row2.addWidget(self.pkg_note, stretch=1); row2.addWidget(btn_add_pkg)
        form_layout.addLayout(row2)
        add_group.setLayout(form_layout)
        layout.addWidget(add_group)
        desc = QLabel("💡 <b>기준: 60영옥 = 1,200원 (1영옥=20원) | 1뽑기 티켓 = 160영옥 (3,200원)</b> <br> 리스트는 <b>효율 배수가 높은 순서대로</b> 자동 정렬됩니다.")
        layout.addWidget(desc)
        self.pkg_scroll = QScrollArea()
        self.pkg_scroll.setWidgetResizable(True)
        self.pkg_container = QWidget()
        self.pkg_layout = QVBoxLayout(self.pkg_container)
        self.pkg_layout.setAlignment(Qt.AlignTop)
        self.pkg_scroll.setWidget(self.pkg_container)
        layout.addWidget(self.pkg_scroll)

    def add_package(self):
        name = self.pkg_name.text().strip()
        if not name: return QMessageBox.warning(self, "경고", "패키지 이름을 입력하세요.")
        pkg = {"id": self.pkg_id_counter, "name": name, "price": self.pkg_price.value(), "yeongok": self.pkg_yeongok.value(), "tickets": self.pkg_tickets.value(), "note": self.pkg_note.text().strip(), "is_new": True}
        self.pkg_id_counter += 1
        for p in self.packages: p["is_new"] = False
        self.packages.append(pkg)
        self.render_packages(); self.save_autosave()
        self.pkg_name.clear(); self.pkg_price.setValue(0); self.pkg_yeongok.setValue(0); self.pkg_tickets.setValue(0); self.pkg_note.clear()
        QTimer.singleShot(100, self.scroll_to_new_package)

    def remove_package(self, pkg_id):
        self.packages =[p for p in self.packages if p["id"] != pkg_id]
        self.render_packages(); self.save_autosave()

    def scroll_to_new_package(self):
        for i in range(self.pkg_layout.count()):
            widget = self.pkg_layout.itemAt(i).widget()
            if isinstance(widget, PackageWidget) and widget.pkg_info.get("is_new"):
                self.pkg_scroll.ensureWidgetVisible(widget)
                break

    def render_packages(self):
        def eff_key(p):
            total_yeongok = p["yeongok"] + (p["tickets"] * 160)
            val_krw = total_yeongok * 20
            return val_krw / p["price"] if p["price"] > 0 else float('inf')
        self.packages.sort(key=eff_key, reverse=True)
        while self.pkg_layout.count():
            item = self.pkg_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        for pkg in self.packages:
            widget = PackageWidget(pkg)
            widget.deleteRequested.connect(self.remove_package)
            widget.noteChanged.connect(self.save_autosave)
            self.pkg_layout.addWidget(widget)

    # ==========================================================
    # --- 5번 플래너 탭 ---
    # ==========================================================

    def setup_planner_tab(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        layout = QVBoxLayout(container)
        
        group_asset = QGroupBox("💰 1. 현재 보유 가챠 자산 및 스택")
        l_asset = QVBoxLayout()
        
        row1 = QHBoxLayout()
        self.p_curr_yeongok = NoScrollSpinBox(); self.p_curr_yeongok.setRange(0, 99999999); self.p_curr_yeongok.setButtonSymbols(QAbstractSpinBox.NoButtons); self.p_curr_yeongok.setFixedWidth(90)
        self.p_curr_char_t = NoScrollSpinBox(); self.p_curr_char_t.setRange(0, 99999999); self.p_curr_char_t.setButtonSymbols(QAbstractSpinBox.NoButtons); self.p_curr_char_t.setFixedWidth(70)
        self.p_curr_weap_t = NoScrollSpinBox(); self.p_curr_weap_t.setRange(0, 99999999); self.p_curr_weap_t.setButtonSymbols(QAbstractSpinBox.NoButtons); self.p_curr_weap_t.setFixedWidth(70)
        self.p_curr_cert = NoScrollSpinBox(); self.p_curr_cert.setRange(0, 99999999); self.p_curr_cert.setButtonSymbols(QAbstractSpinBox.NoButtons); self.p_curr_cert.setFixedWidth(70)
        
        row1.addWidget(QLabel("영옥:")); row1.addWidget(self.p_curr_yeongok)
        row1.addWidget(QLabel("캐릭티켓:")); row1.addWidget(self.p_curr_char_t)
        row1.addWidget(QLabel("무기티켓:")); row1.addWidget(self.p_curr_weap_t)
        row1.addWidget(QLabel("고급 확인서:")); row1.addWidget(self.p_curr_cert)
        row1.addStretch()
        
        row2 = QHBoxLayout()
        self.p_curr_c_pity = NoScrollSpinBox(); self.p_curr_c_pity.setRange(0, 79); self.p_curr_c_pity.setButtonSymbols(QAbstractSpinBox.NoButtons); self.p_curr_c_pity.setFixedWidth(70)
        self.p_curr_w_pity = NoScrollSpinBox(); self.p_curr_w_pity.setRange(0, 39); self.p_curr_w_pity.setButtonSymbols(QAbstractSpinBox.NoButtons); self.p_curr_w_pity.setFixedWidth(70)
        
        row2.addWidget(QLabel("현재 캐릭 천장 스택:")); row2.addWidget(self.p_curr_c_pity)
        row2.addSpacing(15)
        row2.addWidget(QLabel("현재 무기 천장 스택:")); row2.addWidget(self.p_curr_w_pity)
        row2.addStretch()
        
        l_asset.addLayout(row1)
        l_asset.addLayout(row2)
        row3 = QHBoxLayout()
        self.p_chk_cert_done = QCheckBox("이번 달 확인서 교환을 이미 했다면 체크해주세요")
        self.p_chk_cert_done.setStyleSheet("color: #e0245e; font-weight: bold;")
        self.p_chk_pickup_done = QCheckBox("이번 픽업 출석 티켓을 이미 받았다면 체크해주세요")
        self.p_chk_pickup_done.setStyleSheet("color: #e0245e; font-weight: bold;")
        row3.addWidget(self.p_chk_cert_done)
        row3.addSpacing(20)
        row3.addWidget(self.p_chk_pickup_done)
        row3.addStretch()
        l_asset.addLayout(row3)
        group_asset.setLayout(l_asset)
        layout.addWidget(group_asset)

        group_date = QGroupBox("📅 2. 플랜 기간 설정 (기본: PC 오늘 날짜)")
        l_date = QHBoxLayout()
        
        self.p_date_start = NoScrollDateEdit()
        self.p_date_start.setCalendarPopup(True)
        self.p_date_start.setDate(QDate.currentDate())
        
        self.p_date_end = NoScrollDateEdit()
        self.p_date_end.setCalendarPopup(True)
        self.p_date_end.setDate(QDate.currentDate().addDays(30))
        
        btn_today = QPushButton("오늘로 복귀")
        btn_today.clicked.connect(lambda: self.p_date_start.setDate(QDate.currentDate()))

        btn_snap = QPushButton("⏬ 마지막 픽업 시작일로 자동 맞추기")
        btn_snap.setStyleSheet("color: #0056b3; font-weight: bold;")
        btn_snap.clicked.connect(self.snap_to_last_pickup)
        
        l_date.addWidget(QLabel("시작일:"))
        l_date.addWidget(self.p_date_start)
        l_date.addWidget(btn_today)
        l_date.addSpacing(20)
        l_date.addWidget(QLabel("목표일(픽업일):"))
        l_date.addWidget(self.p_date_end)
        l_date.addWidget(btn_snap)
        l_date.addStretch()
        group_date.setLayout(l_date)
        layout.addWidget(group_date)

        group_timeline = QGroupBox("🎯 3. 픽업 타임라인 및 돌파 목표")
        l_timeline = QVBoxLayout()
        btn_add_timeline = QPushButton("➕ 픽업 일정 추가 (기본 3주 단위로 자동 연결)")
        btn_add_timeline.setStyleSheet("background-color: #007BFF; color: white; font-weight: bold; padding: 5px;")
        btn_add_timeline.clicked.connect(self.add_planner_timeline)
        l_timeline.addWidget(btn_add_timeline)
        
        self.p_timeline_layout = QVBoxLayout()
        l_timeline.addLayout(self.p_timeline_layout)
        group_timeline.setLayout(l_timeline)
        layout.addWidget(group_timeline)
        
        group_pkg = QGroupBox("🛒 4. 예정된 과금 및 패키지 플랜 (체크 시 설정한 기간에 맞춰 자동으로 구매 횟수 입력)")
        l_pkg = QVBoxLayout()
        
        self.p_chk_all_pkg = QCheckBox("✅ 전체 선택 / 해제")
        self.p_chk_all_pkg.setStyleSheet("font-weight: bold; color: #007BFF; margin-bottom: 5px;")
        self.p_chk_all_pkg.stateChanged.connect(self.toggle_all_packages)
        l_pkg.addWidget(self.p_chk_all_pkg)

        grid_pkg = QGridLayout()
        self.p_chk_monthly = QCheckBox("월간 패스 회원권 (5,900원)")
        self.p_sp_monthly_days = NoScrollSpinBox(); self.p_sp_monthly_days.setRange(0, 9999); self.p_sp_monthly_days.setFixedWidth(80)
        self.p_sp_monthly_cnt = NoScrollSpinBox(); self.p_sp_monthly_cnt.setRange(0, 9999); self.p_sp_monthly_cnt.setFixedWidth(80)
        grid_pkg.addWidget(self.p_chk_monthly, 0, 0)
        grid_pkg.addWidget(QLabel("패스 남은일수:"), 0, 1); grid_pkg.addWidget(self.p_sp_monthly_days, 0, 2)
        monthly_cnt_wrap = QWidget()
        monthly_cnt_layout = QHBoxLayout(monthly_cnt_wrap)
        monthly_cnt_layout.setContentsMargins(0, 0, 0, 0)
        monthly_cnt_layout.setSpacing(4)
        monthly_cnt_layout.addWidget(QLabel("신규 구매(회):"))
        monthly_cnt_layout.addWidget(self.p_sp_monthly_cnt)
        monthly_cnt_layout.addStretch()
        grid_pkg.addWidget(monthly_cnt_wrap, 0, 3, 1, 2)  # 3~4열을 합쳐서 사용
        self.p_chk_webchar = QCheckBox("공홈 전용 캐릭티켓 (5,900원)")
        self.p_sp_webchar_cnt = NoScrollSpinBox(); self.p_sp_webchar_cnt.setRange(0, 9999); self.p_sp_webchar_cnt.setFixedWidth(80)
        self.p_chk_webweap = QCheckBox("공홈 전용 무기티켓 (5,900원)")
        self.p_sp_webweap_cnt = NoScrollSpinBox(); self.p_sp_webweap_cnt.setRange(0, 9999); self.p_sp_webweap_cnt.setFixedWidth(80)
        grid_pkg.addWidget(self.p_chk_webchar, 1, 0)
        grid_pkg.addWidget(QLabel("구매(회):"), 1, 1); grid_pkg.addWidget(self.p_sp_webchar_cnt, 1, 2)
        grid_pkg.addWidget(self.p_chk_webweap, 1, 3)
        grid_pkg.addWidget(QLabel("구매(회):"), 1, 4); grid_pkg.addWidget(self.p_sp_webweap_cnt, 1, 5)
        
        self.p_chk_bp = QCheckBox("수행수기[배틀패스] (12,000원)")
        self.p_sp_bp_cnt = NoScrollSpinBox(); self.p_sp_bp_cnt.setRange(0, 9999); self.p_sp_bp_cnt.setFixedWidth(80)
        self.p_chk_pickcol = QCheckBox("픽업 컬렉션 상자 (30,000원)")
        self.p_sp_pickcol_cnt = NoScrollSpinBox(); self.p_sp_pickcol_cnt.setRange(0, 9999); self.p_sp_pickcol_cnt.setFixedWidth(80)
        grid_pkg.addWidget(self.p_chk_bp, 2, 0)
        grid_pkg.addWidget(QLabel("구매(회):"), 2, 1); grid_pkg.addWidget(self.p_sp_bp_cnt, 2, 2)
        grid_pkg.addWidget(self.p_chk_pickcol, 2, 3)
        grid_pkg.addWidget(QLabel("구매(회):"), 2, 4); grid_pkg.addWidget(self.p_sp_pickcol_cnt, 2, 5)
        
        self.p_chk_pickchar = QCheckBox("픽업 캐릭티켓 (12,000원)")
        self.p_sp_pickchar_cnt = NoScrollSpinBox(); self.p_sp_pickchar_cnt.setRange(0, 9999); self.p_sp_pickchar_cnt.setFixedWidth(80)
        self.p_chk_pickweap = QCheckBox("픽업 무기티켓 (12,000원)")
        self.p_sp_pickweap_cnt = NoScrollSpinBox(); self.p_sp_pickweap_cnt.setRange(0, 9999); self.p_sp_pickweap_cnt.setFixedWidth(80)
        grid_pkg.addWidget(self.p_chk_pickchar, 3, 0)
        grid_pkg.addWidget(QLabel("구매(회):"), 3, 1); grid_pkg.addWidget(self.p_sp_pickchar_cnt, 3, 2)
        grid_pkg.addWidget(self.p_chk_pickweap, 3, 3)
        grid_pkg.addWidget(QLabel("구매(회):"), 3, 4); grid_pkg.addWidget(self.p_sp_pickweap_cnt, 3, 5)

        self.p_chk_monthly.stateChanged.connect(lambda s: self.auto_fill_package(s, self.p_sp_monthly_cnt, "monthly"))
        self.p_chk_webchar.stateChanged.connect(lambda s: self.auto_fill_package(s, self.p_sp_webchar_cnt, "web"))
        self.p_chk_webweap.stateChanged.connect(lambda s: self.auto_fill_package(s, self.p_sp_webweap_cnt, "web"))
        self.p_chk_bp.stateChanged.connect(lambda s: self.auto_fill_package(s, self.p_sp_bp_cnt, "bp"))
        self.p_chk_pickchar.stateChanged.connect(lambda s: self.auto_fill_package(s, self.p_sp_pickchar_cnt, "pick_tk"))
        self.p_chk_pickweap.stateChanged.connect(lambda s: self.auto_fill_package(s, self.p_sp_pickweap_cnt, "pick_tk"))
        self.p_chk_pickcol.stateChanged.connect(lambda s: self.auto_fill_package(s, self.p_sp_pickcol_cnt, "pick_col"))
        
        l_pkg.addLayout(grid_pkg)
        l_pkg.addWidget(QLabel("<hr><b>커스텀 패키지 추가</b>"))
        
        l_custom_add = QHBoxLayout()
        self.p_cus_name = QLineEdit(); self.p_cus_name.setPlaceholderText("이름"); self.p_cus_name.setFixedWidth(120)
        self.p_cus_price = NoScrollSpinBox(); self.p_cus_price.setRange(0, 9999999); self.p_cus_price.setButtonSymbols(QAbstractSpinBox.NoButtons); self.p_cus_price.setFixedWidth(70)
        self.p_cus_yeongok = NoScrollSpinBox(); self.p_cus_yeongok.setRange(0, 9999999); self.p_cus_yeongok.setButtonSymbols(QAbstractSpinBox.NoButtons); self.p_cus_yeongok.setFixedWidth(60)
        self.p_cus_char = NoScrollSpinBox(); self.p_cus_char.setRange(0, 9999999); self.p_cus_char.setButtonSymbols(QAbstractSpinBox.NoButtons); self.p_cus_char.setFixedWidth(60)
        self.p_cus_weap = NoScrollSpinBox(); self.p_cus_weap.setRange(0, 9999999); self.p_cus_weap.setButtonSymbols(QAbstractSpinBox.NoButtons); self.p_cus_weap.setFixedWidth(60)
        btn_cus_add = QPushButton("추가")
        btn_cus_add.clicked.connect(self.add_custom_planner_pkg)
        
        l_custom_add.addWidget(self.p_cus_name)
        l_custom_add.addWidget(QLabel("가격:")); l_custom_add.addWidget(self.p_cus_price)
        l_custom_add.addWidget(QLabel("영옥:")); l_custom_add.addWidget(self.p_cus_yeongok)
        l_custom_add.addWidget(QLabel("캐릭티켓:")); l_custom_add.addWidget(self.p_cus_char)
        l_custom_add.addWidget(QLabel("무기티켓:")); l_custom_add.addWidget(self.p_cus_weap)
        l_custom_add.addWidget(btn_cus_add)
        l_custom_add.addStretch()
        
        l_pkg.addLayout(l_custom_add)
        self.p_custom_pkg_layout = QVBoxLayout()
        l_pkg.addLayout(self.p_custom_pkg_layout)
        
        group_pkg.setLayout(l_pkg)
        layout.addWidget(group_pkg)

        btn_calc_planner = QPushButton("✨ 가챠 시뮬레이션 계산하기")
        btn_calc_planner.setMinimumHeight(50)
        btn_calc_planner.setStyleSheet("font-size: 16px; font-weight: bold; background-color: #28A745; color: white;")
        btn_calc_planner.clicked.connect(self.calc_planner)
        layout.addWidget(btn_calc_planner)

        # 내보내기 버튼 행
        export_row = QHBoxLayout()
        btn_copy_planner = QPushButton("📋 텍스트 복사")
        btn_copy_planner.setStyleSheet("background-color: #17a2b8; color: white; font-weight: bold; padding: 6px;")
        btn_copy_planner.clicked.connect(self.export_planner_text)
        btn_img_planner = QPushButton("🖼️ 이미지로 저장")
        btn_img_planner.setStyleSheet("background-color: #6c757d; color: white; font-weight: bold; padding: 6px;")
        btn_img_planner.clicked.connect(self.export_planner_image)
        export_row.addWidget(btn_copy_planner)
        export_row.addWidget(btn_img_planner)
        export_row.addStretch()
        layout.addLayout(export_row)
        
        self.p_lbl_result = QLabel()
        self.p_lbl_result.setTextFormat(Qt.RichText)
        self.p_lbl_result.setWordWrap(True)
        self.p_lbl_result.setStyleSheet("background-color: #f8f9fa; border: 1px solid #ccc; padding: 10px; border-radius: 5px; font-size: 14px;")
        self.p_lbl_result.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        layout.addWidget(self.p_lbl_result)

        scroll.setWidget(container)
        main_layout = QVBoxLayout(self.tab_planner)
        main_layout.addWidget(scroll)

    def toggle_all_packages(self, state):
        is_checked = (state == Qt.Checked)
        self.p_chk_monthly.setChecked(is_checked)
        self.p_chk_webchar.setChecked(is_checked)
        self.p_chk_webweap.setChecked(is_checked)
        self.p_chk_bp.setChecked(is_checked)
        self.p_chk_pickcol.setChecked(is_checked)
        self.p_chk_pickchar.setChecked(is_checked)
        self.p_chk_pickweap.setChecked(is_checked)

    def add_planner_timeline(self):
        w = QFrame()
        w.setFrameShape(QFrame.StyledPanel)
        w.setObjectName("timelineFrame")
        w.setStyleSheet("QFrame#timelineFrame { background-color: #ffffff; border: 1px solid #ddd; border-radius: 5px; padding: 2px; }")
        layout = QHBoxLayout(w)
        layout.setContentsMargins(5, 5, 5, 5)
        
        base_date = QDate(2026, 4, 3)
        period_num = 1

        if self.p_timeline_layout.count() > 0:
            # 마지막 타임라인 기준으로 다음 시작일 계산
            last_w = self.p_timeline_layout.itemAt(self.p_timeline_layout.count() - 1).widget()
            if last_w:
                last_start = last_w.findChild(QDateEdit, "start_date").date()
                next_start = last_start.addDays(21)
                last_name = last_w.findChild(QLineEdit, "pickup_name").text()
                import re
                m = re.search(r'(\d+)', last_name)
                if m: period_num = int(m.group(1)) + 1
        else:
            # 사용자가 지정한 플랜 시작일 기준으로 현재 진행 중인 픽업 찾기
            ref_date = self.p_date_start.date()
            diff = base_date.daysTo(ref_date)
            if diff < 0:
                next_start = base_date
            else:
                current_idx = diff // 21
                next_start = base_date.addDays(current_idx * 21)
            period_num = max(1, base_date.daysTo(next_start) // 21 + 1)
        
        inp_name = QLineEdit(f"{period_num}기 픽업")
        inp_name.setObjectName("pickup_name")
        inp_name.setFixedWidth(90)

        date_start = NoScrollDateEdit(next_start)
        date_start.setObjectName("start_date")
        date_start.setCalendarPopup(True)

        date_end = NoScrollDateEdit(next_start.addDays(20))
        date_end.setCalendarPopup(True)
        date_start.dateChanged.connect(lambda d, de=date_end: de.setDate(d.addDays(20)))

        cb_char = NoScrollComboBox()
        cb_char.setObjectName("cb_char")
        cb_char.addItems(["패스", "명함(0돌)", "1돌", "2돌", "3돌", "4돌", "5돌", "6돌"])
        
        cb_weap = NoScrollComboBox()
        cb_weap.setObjectName("cb_weap")
        cb_weap.addItems(["패스", "명함(1단계)", "2단계", "3단계", "4단계", "5단계"])
        
        btn_del = QPushButton("❌ 삭제")
        btn_del.setStyleSheet("color: red; border: none; background: transparent;")
        btn_del.clicked.connect(lambda: self.p_timeline_layout.removeWidget(w) or w.deleteLater())
        
        layout.addWidget(inp_name)
        layout.addWidget(date_start)
        layout.addWidget(QLabel("~"))
        layout.addWidget(date_end)
        layout.addSpacing(10)
        layout.addWidget(QLabel("캐릭 목표:"))
        layout.addWidget(cb_char)
        layout.addWidget(QLabel("무기 목표:"))
        layout.addWidget(cb_weap)
        layout.addStretch()
        layout.addWidget(btn_del)
        
        self.p_timeline_layout.addWidget(w)

    def snap_to_last_pickup(self):
        max_d = None
        for i in range(self.p_timeline_layout.count()):
            w = self.p_timeline_layout.itemAt(i).widget()
            if w:
                d = w.findChild(QDateEdit, "start_date").date()
                if not max_d or d > max_d: max_d = d
        if max_d:
            self.p_date_end.setDate(max_d)

    def auto_fill_package(self, state, sp_box, pkg_type):
        if state == Qt.Checked:
            start = self.p_date_start.date()
            end = self.p_date_end.date()
            if start > end: return
            
            days = max(0, start.daysTo(end) + 1)
            
            months_involved = 0
            temp_date = QDate(start.year(), start.month(), 1)
            
            if temp_date == QDate(2026, 3, 1):
                temp_date = temp_date.addMonths(1)
                
            while temp_date <= end:
                months_involved += 1
                temp_date = temp_date.addMonths(1)
                
            pickups_involved = 0
            pickup_date = QDate(2026, 3, 13)
            
            while pickup_date.addDays(21) <= start:
                pickup_date = pickup_date.addDays(21)
                
            if pickup_date == QDate(2026, 3, 13):
                pickup_date = pickup_date.addDays(21)
                
            while pickup_date <= end:
                pickups_involved += 1
                pickup_date = pickup_date.addDays(21)
            
            if pkg_type == "monthly":
                existing = self.p_sp_monthly_days.value()
                needed = math.ceil(max(0, days - existing) / 30.0)
                sp_box.setValue(needed)
            elif pkg_type == "web":
                sp_box.setValue(months_involved)
            elif pkg_type == "bp":
                sp_box.setValue(math.ceil(days / 30.0))
            elif pkg_type == "pick_tk":
                sp_box.setValue(pickups_involved * 2)
            elif pkg_type == "pick_col":
                sp_box.setValue(pickups_involved * 1)

    def add_custom_planner_pkg(self):
        name = self.p_cus_name.text().strip()
        if not name: return
        price = self.p_cus_price.value(); yeongok = self.p_cus_yeongok.value()
        char_t = self.p_cus_char.value(); weap_t = self.p_cus_weap.value()
        w = QWidget()
        layout = QHBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        chk = QCheckBox(f"{name} (가격: {price:,}원 | 영옥: {yeongok} | 캐릭티켓: {char_t} | 무기티켓: {weap_t})")
        chk.setChecked(True)
        chk.setObjectName("chk_custom")
        chk.setProperty("data", {"price": price, "yeongok": yeongok, "char_t": char_t, "weap_t": weap_t})
        btn_del = QPushButton("삭제"); btn_del.setFixedWidth(50)
        btn_del.clicked.connect(lambda: self.p_custom_pkg_layout.removeWidget(w) or w.deleteLater())
        layout.addWidget(chk); layout.addStretch(); layout.addWidget(btn_del)
        self.p_custom_pkg_layout.addWidget(w)
        self.p_cus_name.clear()
        self.p_cus_price.setValue(0); self.p_cus_yeongok.setValue(0)
        self.p_cus_char.setValue(0); self.p_cus_weap.setValue(0)

    def export_planner_text(self):
        import re
        raw = self.p_lbl_result.text()
        if not raw:
            QMessageBox.warning(self, "알림", "먼저 계산을 실행해주세요.")
            return
        text = re.sub(r'<[^>]+>', '', raw).strip()
        text = text.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
        QApplication.clipboard().setText(text)
        QMessageBox.information(self, "복사 완료", "플래너 결과가 클립보드에 복사되었습니다.")

    def export_planner_image(self):
        if not self.p_lbl_result.text():
            QMessageBox.warning(self, "알림", "먼저 계산을 실행해주세요.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "이미지로 저장", "planner_result.png", "PNG Files (*.png)")
        if not path:
            return
        pixmap = self.p_lbl_result.grab()
        pixmap.save(path, "PNG")
        QMessageBox.information(self, "저장 완료", f"이미지가 저장되었습니다.\n{path}")

    def calc_planner(self):
        try:
            start = self.p_date_start.date()
            end = self.p_date_end.date()
            days = max(0, start.daysTo(end) + 1)
            
            monday_cnt = sum(1 for i in range(days) if start.addDays(i).dayOfWeek() == 1)
            months_in_period = set()
            for i in range(days):
                d = start.addDays(i)
                months_in_period.add((d.year(), d.month()))
            month_cnt = len(months_in_period)
            
            cur_month = (start.year(), start.month())
            already_done = self.p_chk_cert_done.isChecked() and cur_month in months_in_period
            ticket_first_day_cnt = month_cnt - (1 if already_done else 0)
            
            pickup_base = QDate(2026, 4, 3)
            # 기간과 겹치는 픽업 회차 수집 (시작일 기준이 아니라 기간 겹침 기준)
            overlapping_pickups = set()
            for i in range(days):
                d = start.addDays(i)
                diff = pickup_base.daysTo(d)
                if diff >= 0:
                    overlapping_pickups.add(diff // 21)  # 몇 번째 픽업인지
            pickup_cnt_raw = len(overlapping_pickups)

            # 이미 받은 경우: 시작일이 속한 픽업 회차가 겹치는 경우 1 차감
            start_diff = pickup_base.daysTo(start)
            start_pickup_idx = start_diff // 21 if start_diff >= 0 else -1
            already_received = self.p_chk_pickup_done.isChecked() and start_pickup_idx in overlapping_pickups
            pickup_cnt = pickup_cnt_raw - (1 if already_received else 0)
            
            free_yeongok = days * 60 + monday_cnt * 950 + monday_cnt * 1167  # 3500÷3주 주간 분할
            free_char_t = ticket_first_day_cnt * 3 + pickup_cnt * 4
            free_weap_t = ticket_first_day_cnt * 3 + pickup_cnt * 3
            
            paid_krw = 0; paid_yeongok = 0; paid_char_t = 0; paid_weap_t = 0
            
            if self.p_chk_monthly.isChecked():
                m_cnt = self.p_sp_monthly_cnt.value(); m_days = self.p_sp_monthly_days.value()
                paid_krw += m_cnt * 5900
                active_days = min(days, m_days + m_cnt * 30)
                paid_yeongok += m_cnt * 300 + active_days * 100
            if self.p_chk_webchar.isChecked():
                cnt = self.p_sp_webchar_cnt.value(); paid_krw += cnt * 5900; paid_char_t += cnt * 10
            if self.p_chk_webweap.isChecked():
                cnt = self.p_sp_webweap_cnt.value(); paid_krw += cnt * 5900; paid_weap_t += cnt * 10
            if self.p_chk_bp.isChecked():
                cnt = self.p_sp_bp_cnt.value(); paid_krw += cnt * 12000; paid_yeongok += cnt * 680; paid_char_t += cnt * 10
            if self.p_chk_pickchar.isChecked():
                cnt = self.p_sp_pickchar_cnt.value(); paid_krw += cnt * 12000; paid_yeongok += cnt * 680; paid_char_t += cnt * 10
            if self.p_chk_pickweap.isChecked():
                cnt = self.p_sp_pickweap_cnt.value(); paid_krw += cnt * 12000; paid_yeongok += cnt * 680; paid_weap_t += cnt * 10
            if self.p_chk_pickcol.isChecked():
                cnt = self.p_sp_pickcol_cnt.value(); paid_krw += cnt * 30000; paid_yeongok += cnt * 1680; paid_char_t += cnt * 20
                
            for i in range(self.p_custom_pkg_layout.count()):
                w = self.p_custom_pkg_layout.itemAt(i).widget()
                if w:
                    chk = w.findChild(QCheckBox, "chk_custom")
                    if chk and chk.isChecked():
                        d = chk.property("data")
                        paid_krw += d["price"]; paid_yeongok += d["yeongok"]
                        paid_char_t += d["char_t"]; paid_weap_t += d["weap_t"]

            tot_yeongok = self.p_curr_yeongok.value() + free_yeongok + paid_yeongok
            tot_char_t = self.p_curr_char_t.value() + free_char_t + paid_char_t
            tot_weap_t = self.p_curr_weap_t.value() + free_weap_t + paid_weap_t
            base_cert = self.p_curr_cert.value()
            
            char_map = {"패스": 0, "명함(0돌)": 1, "1돌": 2, "2돌": 3, "3돌": 4, "4돌": 5, "5돌": 6, "6돌": 7}
            weap_map = {"패스": 0, "명함(1단계)": 1, "2단계": 2, "3단계": 3, "4단계": 4, "5단계": 5}
            
            req_c = 0; req_w = 0
            for i in range(self.p_timeline_layout.count()):
                w = self.p_timeline_layout.itemAt(i).widget()
                if w:
                    cb_char = w.findChild(QComboBox, "cb_char")
                    cb_weap = w.findChild(QComboBox, "cb_weap")
                    if cb_char and cb_weap:
                        req_c += char_map.get(cb_char.currentText(), 0)
                        req_w += weap_map.get(cb_weap.currentText(), 0)

            curr_c_pity = self.p_curr_c_pity.value()
            curr_w_pity = self.p_curr_w_pity.value()

            avg_c_pulls = max(0, 54.35 - curr_c_pity) + (req_c - 1) * 54.35 if req_c > 0 else 0
            avg_w_pulls = max(0, 31.45 - curr_w_pity) + (req_w - 1) * 31.45 if req_w > 0 else 0
            avg_pb_cert = avg_c_pulls * 1.5 + avg_w_pulls * 1.5 + req_c * 100 + req_w * 50
            avg_univ_pulls = (tot_yeongok / 160.0) + ((base_cert + avg_pb_cert) / 50.0)
            
            rem_c_avg = max(0, avg_c_pulls - tot_char_t)
            rem_w_avg = max(0, avg_w_pulls - tot_weap_t)
            def_avg = max(0, (rem_c_avg + rem_w_avg) - avg_univ_pulls)

            max_c_pulls = max(0, 80 - curr_c_pity) + (req_c - 1) * 80 if req_c > 0 else 0
            max_w_pulls = max(0, 40 - curr_w_pity) + (req_w - 1) * 40 if req_w > 0 else 0
            max_pb_cert = max_c_pulls * 1.5 + max_w_pulls * 1.5 + req_c * 100 + req_w * 50
            max_univ_pulls = (tot_yeongok / 160.0) + ((base_cert + max_pb_cert) / 50.0)
            
            rem_c_max = max(0, max_c_pulls - tot_char_t)
            rem_w_max = max(0, max_w_pulls - tot_weap_t)
            def_max = max(0, (rem_c_max + rem_w_max) - max_univ_pulls)

            html = f"""
            <div style='font-size: 12px;'> <h4 style='color:#0056b3; font-size:15px; margin-top:0px; margin-bottom:5px;'>[🗓️ 기간 내 재화 결산]</h4>
            <ul style='margin-top:0px;'>
              <li><b>플랜 기간:</b> {days}일 <span style='color:gray;'>(월요일 {monday_cnt}번, 매월 1일 {ticket_first_day_cnt}번, 픽업 {pickup_cnt}번 갱신)</span></li>
              <li><b>🎁 무료 수급 예상 총합:</b> 영옥 {free_yeongok:,}개 | 캐릭티켓 {free_char_t:,}장 | 무기티켓 {free_weap_t:,}장</li>
              <li><b>📦 설정한 예정 패키지로 얻는 자산:</b> 영옥 {paid_yeongok:,}개 | 캐릭티켓 {paid_char_t:,}장 | 무기티켓 {paid_weap_t:,}장</li>
              <li><span style='color:#0056b3;'><b>💳 위 패키지 구매를 위해 소모될 "예정 현금": {paid_krw:,}원</b></span></li>
              <hr style='margin: 5px 0;'>
              <li style='font-size:14px;'>💎 <b>보유+예상 총 가용 자산:</b> 영옥 <b style='color:#28a745;'>{tot_yeongok:,}</b>개 | 
                  캐릭티켓 <b style='color:#28a745;'>{tot_char_t:,}</b>장 | 무기티켓 <b style='color:#28a745;'>{tot_weap_t:,}</b>장 | 확인서 <b style='color:#28a745;'>{base_cert:,}</b>개</li>
            </ul>

            <h4 style='color:#e0245e; font-size:15px; margin-top:10px; margin-bottom:5px;'>[🎯 가챠 목표 및 필요 횟수] (현재 스택 차감 반영)</h4>
            <ul style='margin-top:0px;'>
              <li><b>총 목표 획득 장수:</b> 캐릭터 {req_c}장 / 무기 {req_w}장</li>
              <li><b>평균 기댓값 기준:</b> 캐릭터 약 {int(avg_c_pulls):,}뽑 + 무기 약 {int(avg_w_pulls):,}뽑</li>
              <li><b>최악 천장 기준:</b> 캐릭터 {int(max_c_pulls):,}뽑 + 무기 {int(max_w_pulls):,}뽑</li>
            </ul>
            </div>
            <h3 style='color:#17a2b8; font-size:18px; font-weight:bold; margin-top:20px; margin-bottom:10px;'>[🔥 최종 달성 판정 결과]</h3>
            """

            def format_result(deficit_pulls):
                if deficit_pulls <= 0:
                    return f"<span style='color:green; font-weight:bold;'>🎉 모든 목표 달성 가능! (재화 여유 있음)</span><br>&nbsp;&nbsp;&nbsp;↳ 💸 예정 패키지 금액 <b>{paid_krw:,}원</b>으로 충분"
                else:
                    req_y = int(math.ceil(deficit_pulls) * 160)
                    req_k = int(math.ceil(deficit_pulls) * 3200)
                    tot_k = paid_krw + req_k
                    return (f"<span style='color:#dc3545; font-weight:bold;'>❌ 약 {math.ceil(deficit_pulls):,} 뽑기 부족</span> (영옥 {req_y:,}개분)<br>"
                            f"&nbsp;&nbsp;&nbsp;↳ 💸 <b>예정 패키지 금액 <span style='color:#0056b3;'>{paid_krw:,}원</span> + 추가 깡영옥 과금 <span style='color:#e0245e;'>{req_k:,}원</span> = 최종 필요 현금 <span style='color:#8b0000;'>{tot_k:,}원</span></b>")

            html += f"<p><b>🔵 평균 기댓값(운이 평범할 때):</b><br> {format_result(def_avg)}</p>"
            html += f"<p><b>🔴 최악의 천장(운이 없을 때):</b><br> {format_result(def_max)}</p>"

            self.p_lbl_result.setText(html)
        except Exception as e:
            self.p_lbl_result.setText(f"<b style='color:red;'>계산 오류 발생:</b> {str(e)}")

    # ==========================================================
    # --- 던전 파밍 계산 로직 ---
    def get_dungeon_run_value(self, dungeon_name, level_key):
        drops = self.dungeon_drops.get(dungeon_name, {}).get(level_key, {})
        val = 0
        for item, amount in drops.items():
            if item == "hwan":
                if "자금 수집" in dungeon_name: val += amount
            elif "char_exp" in item:
                if "legend" in item: val += amount * 20000
                elif "rare" in item: val += amount * 10000
                elif "advanced" in item: val += amount * 3000
                elif "normal" in item: val += amount * 500
            elif "weap_exp" in item:
                if "legend" in item: val += amount * 10000
                elif "rare" in item: val += amount * 5000
                elif "advanced" in item: val += amount * 2000
                elif "normal" in item: val += amount * 500
            elif "ouyi" in item or "yoryung" in item or "hammer" in item:
                if "rare" in item: val += amount * 9
                elif "advanced" in item: val += amount * 3
                elif "normal" in item: val += amount * 1
            elif "omamori" in item: val += amount
            elif "engrave_exp" in item: val += amount
        return val

    def on_dungeon_level_changed(self, dungeon_name, level_key):
        self.selected_dungeon_levels[dungeon_name] = level_key
        self.calculate_resources(is_refresh=False)

    def perform_daehaeng(self, dungeon_name, level_key, count):
        if count <= 0: return
        drops = self.dungeon_drops.get(dungeon_name, {}).get(level_key, {})
        for item_key, amount in drops.items():
            if item_key in self.inv_inputs:
                curr_val = self.inv_inputs[item_key].value()
                self.inv_inputs[item_key].setValue(curr_val + (amount * count))
        self.save_autosave() 
        self.calculate_resources(is_refresh=False) 

    def calculate_resources(self, is_refresh=False):
        if is_refresh:
            self.dungeon_scroll.setAutoFillBackground(True)
            self.dungeon_scroll.viewport().setAutoFillBackground(True)
            self.dungeon_container.setAutoFillBackground(True)
            self.selected_dungeon_levels.clear()

        vbar = self.dungeon_scroll.verticalScrollBar()
        saved_scroll = vbar.value() if vbar else 0
        
        req = { "hwan": 0, "char_exp": 0, "weap_exp": 0, "engrave_exp": 0, "engrave_core": 0 }
        for p in PROPERTIES:
            for g in ["normal", "advanced", "rare"]:
                req[f"ouyi_{p}_{g}"] = 0
                req[f"hammer_{p}_{g}"] = 0
                req[f"yoryung_{p}_{g}"] = 0
        for t in TYPES: req[f"omamori_{t}"] = 0
        req["omamori_universal"] = 0

        for widget in self.char_widgets:
            c = widget.get_data()
            if not c.get("is_active", True): continue
            prop = c["prop"]; ctype = c["type"]
            for lv in LEVELS:
                if lv > 1 and c["char_curr"] < lv <= c["char_targ"]:
                    req["char_exp"] += CHAR_EXP[lv]
                    if lv in CHAR_UNCAP:
                        nor, adv, rar, hw = CHAR_UNCAP[lv]
                        req[f"ouyi_{prop}_normal"] += nor
                        req[f"ouyi_{prop}_advanced"] += adv
                        req[f"ouyi_{prop}_rare"] += rar
                        req["hwan"] += hw
            for lv in LEVELS:
                if lv > 1 and c["weap_curr"] < lv <= c["weap_targ"]:
                    req["weap_exp"] += WEAP_EXP[lv]
                    if lv in WEAP_UNCAP:
                        nor, adv, rar, hw = WEAP_UNCAP[lv]
                        req[f"hammer_{prop}_normal"] += nor
                        req[f"hammer_{prop}_advanced"] += adv
                        req[f"hammer_{prop}_rare"] += rar
                        req["hwan"] += hw
            for start_lv, targ_lv in zip(c["skill_data"]["active_curr"], c["skill_data"]["active_targ"]):
                for lv in range(start_lv + 1, targ_lv + 1):
                    nor, adv, rar, hw = ACTIVE_SKILL[lv]
                    req[f"yoryung_{prop}_normal"] += nor
                    req[f"yoryung_{prop}_advanced"] += adv
                    req[f"yoryung_{prop}_rare"] += rar
                    req["hwan"] += hw
            for idx, (start_lv, targ_lv) in enumerate(zip(c["skill_data"]["passive_curr"], c["skill_data"]["passive_targ"])):
                p_id = idx + 1
                for lv in range(start_lv + 1, targ_lv + 1):
                    req[f"omamori_{ctype}"] += PASSIVE_SKILL[p_id][lv][0]
                    req["hwan"] += PASSIVE_SKILL[p_id][lv][1]
            # 각인 비용 계산 (4개 개별 기준)
            if 'engrave_set1_curr_lv' in c["skill_data"]:
                for set_key, cost_table in [("set1", SET_ENGRAVE_COST), ("set2", SET_ENGRAVE_COST), ("set3", SET_ENGRAVE_COST), ("core", CORE_ENGRAVE_COST)]:
                    curr_elv = c["skill_data"].get(f"engrave_{set_key}_curr_lv", 1)
                    targ_elv = c["skill_data"].get(f"engrave_{set_key}_targ_lv", 1)
                    if curr_elv < targ_elv:
                        for i in range(len(ENGRAVE_LEVELS) - 1):
                            seg_s, seg_e = ENGRAVE_LEVELS[i], ENGRAVE_LEVELS[i+1]
                            if seg_s >= curr_elv and seg_e <= targ_elv:
                                if cost_table is SET_ENGRAVE_COST:
                                    sh, se, sc = SET_ENGRAVE_COST[(seg_s, seg_e)]
                                    req["hwan"] += sh; req["engrave_exp"] += se; req["engrave_core"] += sc
                                else:
                                    ch, ce = CORE_ENGRAVE_COST[(seg_s, seg_e)]
                                    req["hwan"] += ch; req["engrave_exp"] += ce
            elif not c["skill_data"].get("engrave_curr", False) and c["skill_data"].get("engrave_targ", True):
                req["hwan"] += 1485000; req["engrave_exp"] += 1650; req["engrave_core"] += 30

        req["hwan"] += req["char_exp"] // 5; req["hwan"] += req["weap_exp"] // 5

        # --- 전체 필요 재화 HTML (tot_html) ---
        c_leg = "<span style='background-color:#fff3cd; color:#333;'><b>&nbsp;전설&nbsp;</b></span>"
        c_rare_s = "<span style='background-color:#e2d9f3; color:#333;'><b>&nbsp;희귀&nbsp;</b></span>"
        c_adv_s = "<span style='background-color:#d0ebff; color:#333;'><b>&nbsp;고급&nbsp;</b></span>"
        c_nor_s = "<span style='background-color:#d4edda; color:#333;'><b>&nbsp;일반&nbsp;</b></span>"

        tot_html = "<ul>"
        tot_html += f"<li><b>총 필요 환(돈):</b> {req['hwan']:,} 환</li>"
        if req['char_exp'] > 0: tot_html += f"<li><b>캐릭터 경력:</b> {format_item_amount(req['char_exp'], 'char_exp')}</li>"
        if req['weap_exp'] > 0: tot_html += f"<li><b>무기 접쇠:</b> {format_item_amount(req['weap_exp'], 'weap_exp')}</li>"
        if req['engrave_exp'] > 0: tot_html += f"<li><b>각인의 영질:</b> {req['engrave_exp']:,} 개</li>"
        if req['engrave_core'] > 0: tot_html += f"<li><b>각인의 핵심:</b> {req['engrave_core']:,} 개</li>"
        prop_colors = {"참술": "#f8d7da", "백타": "#ffdfba", "돌격": "#fff3cd", "영술": "#d0ebff", "기예": "#e2d9f3"}
        for p in PROPERTIES:
            c_tag = f"<span style='background-color:{prop_colors[p]}; color:#333; padding:2px; border-radius:3px;'><b>&nbsp;{p}&nbsp;</b></span>"
            for prefix, label in [("yoryung", "요령"), ("hammer", "망치"), ("ouyi", "오의")]:
                rn = req[f"{prefix}_{p}_normal"]; ra = req[f"{prefix}_{p}_advanced"]; rr = req[f"{prefix}_{p}_rare"]
                if rn or ra or rr:
                    tot_html += f"<li>{c_tag} <b>{label}:</b> {format_grade_items(rn, ra, rr, c_rare_s, c_adv_s, c_nor_s)}</li>"
        for t in TYPES:
            if req[f"omamori_{t}"] > 0: tot_html += f"<li><b>{t} 오마모리:</b> {req[f'omamori_{t}']:,} 개</li>"
        tot_html += "</ul>"
        self.lbl_total_req.setText(tot_html)

        # --- 보유량 및 부족량 계산 ---
        owned = {
            "hwan": self.inv_inputs["hwan"].value(),
            "engrave_exp": self.inv_inputs["engrave_exp"].value(),
            "engrave_core": self.inv_inputs["engrave_core"].value(),
            "char_exp": (self.inv_inputs["char_exp_normal"].value() * 500 + self.inv_inputs["char_exp_advanced"].value() * 3000 +
                         self.inv_inputs["char_exp_rare"].value() * 10000 + self.inv_inputs["char_exp_legend"].value() * 20000),
            "weap_exp": (self.inv_inputs["weap_exp_normal"].value() * 500 + self.inv_inputs["weap_exp_advanced"].value() * 2000 +
                         self.inv_inputs["weap_exp_rare"].value() * 5000 + self.inv_inputs["weap_exp_legend"].value() * 10000),
        }
        for p in PROPERTIES:
            for prefix in ["ouyi", "hammer", "yoryung"]:
                for g in ["normal", "advanced", "rare"]:
                    owned[f"{prefix}_{p}_{g}"] = self.inv_inputs[f"{prefix}_{p}_{g}"].value()
        for t in TYPES: owned[f"omamori_{t}"] = self.inv_inputs[f"omamori_{t}"].value()
        owned["omamori_universal"] = self.inv_inputs["omamori_universal"].value()
        owned["yoryung_universal"] = self.inv_inputs["yoryung_universal"].value()

        # 부족량: 단순 재화는 직접 차감, 등급 재화는 교환 로직 적용
        missing = {}
        for key in ["hwan", "char_exp", "weap_exp", "engrave_exp", "engrave_core"]:
            missing[key] = max(0, req[key] - owned.get(key, 0))
        universal_omamori = owned["omamori_universal"]
        for t in TYPES:
            direct_missing = max(0, req[f"omamori_{t}"] - owned.get(f"omamori_{t}", 0))
            used = min(universal_omamori, direct_missing)
            universal_omamori -= used; missing[f"omamori_{t}"] = direct_missing - used
        universal_yoryung = owned["yoryung_universal"]
        for p in PROPERTIES:
            for prefix in ["ouyi", "hammer", "yoryung"]:
                normal = owned[f"{prefix}_{p}_normal"]
                if prefix == "yoryung": normal += universal_yoryung
                mn, ma, mr = resolve_material_shortage(
                    req[f"{prefix}_{p}_normal"], req[f"{prefix}_{p}_advanced"], req[f"{prefix}_{p}_rare"],
                    normal, owned[f"{prefix}_{p}_advanced"], owned[f"{prefix}_{p}_rare"]
                )
                if prefix == "yoryung":
                    # Consume only the generic normal material needed by this attribute.
                    base_mn, base_ma, base_mr = resolve_material_shortage(req[f"{prefix}_{p}_normal"], req[f"{prefix}_{p}_advanced"], req[f"{prefix}_{p}_rare"], owned[f"{prefix}_{p}_normal"], owned[f"{prefix}_{p}_advanced"], owned[f"{prefix}_{p}_rare"])
                    universal_yoryung = max(0, universal_yoryung - ((base_mn + base_ma * 3 + base_mr * 9) - (mn + ma * 3 + mr * 9)))
                missing[f"{prefix}_{p}_normal"] = mn
                missing[f"{prefix}_{p}_advanced"] = ma
                missing[f"{prefix}_{p}_rare"] = mr
                missing[f"{prefix}_{p}"] = mn + ma * 3 + mr * 9  # 던전 계산용 normal-equiv

        runs, stamina, hwan_earned = {}, 0, 0
        targets = {"현세 순찰 (캐릭터 경험치)": "char_exp", "호로 토벌 (무기 경험치)": "weap_exp", "혼백의 호위 (각인의 영질)": "engrave_exp"}
        for p in PROPERTIES:
            targets[f"학원 특훈 [{p}] (요령)"] = f"yoryung_{p}"
            targets[f"카라쿠라 수비 [{p}] (오의)"] = f"ouyi_{p}"
            targets[f"호정 연습 [{p}] (망치)"] = f"hammer_{p}"
        for t in TYPES: targets[f"호로 무리 정화 [{t}] (오마모리)"] = f"omamori_{t}"

        for name, missing_key in targets.items():
            missing_amount = missing.get(missing_key, 0)
            if missing_amount > 0:
                if name not in self.dungeon_drops: continue
                level_key = self.selected_dungeon_levels.get(name)
                if not level_key or level_key not in self.dungeon_drops[name]:
                    level_key = sorted(self.dungeon_drops[name].keys(), reverse=True)[0]
                    self.selected_dungeon_levels[name] = level_key
                run_val = max(1, self.get_dungeon_run_value(name, level_key))
                count = math.ceil(missing_amount / run_val)
                runs[name] = count
                is_omamori = "호로 무리 정화" in name
                stamina += count * (40 if is_omamori else 20)
                hwan_drop = self.dungeon_drops[name][level_key].get("hwan", 0)
                hwan_earned += count * hwan_drop

        final_missing_hwan = missing.get("hwan", 0) - hwan_earned
        if final_missing_hwan > 0:
            name = "자금 수집 (환)"
            if name in self.dungeon_drops:
                level_key = self.selected_dungeon_levels.get(name)
                if not level_key or level_key not in self.dungeon_drops[name]:
                    level_key = sorted(self.dungeon_drops[name].keys(), reverse=True)[0]
                    self.selected_dungeon_levels[name] = level_key
                run_val = max(1, self.get_dungeon_run_value(name, level_key))
                count = math.ceil(final_missing_hwan / run_val)
                runs[name] = count; stamina += count * 20

        res_html = "<h2>📊 계산 결과 요약</h2><ul>"
        res_html += f"<li><b>최종 부족한 환(돈):</b> {final_missing_hwan if final_missing_hwan>0 else 0:,} 환</li>"
        if missing['char_exp'] > 0: res_html += f"<li><b>캐릭터 경력 부족:</b> {format_item_amount(missing['char_exp'], 'char_exp')}</li>"
        if missing['weap_exp'] > 0: res_html += f"<li><b>무기 접쇠 부족:</b> {format_item_amount(missing['weap_exp'], 'weap_exp')}</li>"
        if missing['engrave_exp'] > 0: res_html += f"<li><b>각인의 영질:</b> {missing['engrave_exp']:,} 개</li>"
        if missing['engrave_core'] > 0: res_html += f"<li><b>각인의 핵심:</b> {missing['engrave_core']:,} 개 <span style='color:gray;'>(수급처 던전 없음)</span></li>"
        for p in PROPERTIES:
            c_tag = f"<span style='background-color:{prop_colors[p]}; color:#333; padding:2px; border-radius:3px;'><b>&nbsp;{p}&nbsp;</b></span>"
            for prefix, label in [("yoryung", "요령"), ("hammer", "망치"), ("ouyi", "오의")]:
                mn = missing[f"{prefix}_{p}_normal"]; ma = missing[f"{prefix}_{p}_advanced"]; mr = missing[f"{prefix}_{p}_rare"]
                if mn or ma or mr:
                    res_html += f"<li>{c_tag} <b>{label} 부족:</b> {format_grade_items(mn, ma, mr, c_rare_s, c_adv_s, c_nor_s)}</li>"
        for t in TYPES:
            if missing[f"omamori_{t}"] > 0: res_html += f"<li><b>{t} 오마모리:</b> {missing[f'omamori_{t}']:,} 개</li>"
        res_html += f"</ul><h3>⚡ 총 필요 영력: <span style='color:red;'>{stamina:,}</span> 영력</h3><hr>"
        self.result_summary.setText(res_html)

        while self.dungeon_layout.count():
            item = self.dungeon_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()

        if stamina == 0:
            lbl = QLabel("🎉 <b>모든 재화가 충분합니다! 더 이상 파밍할 던전이 없습니다.</b>")
            lbl.setAlignment(Qt.AlignCenter)
            self.dungeon_layout.addWidget(lbl)
            return

        for name, count in runs.items():
            if count > 0:
                is_omamori = "호로 무리 정화" in name
                req_stam = count * (40 if is_omamori else 20)
                display_name = name
                for p, color in prop_colors.items():
                    if f"[{p}]" in name:
                        display_name = name.replace(f"[{p}]", f"<span style='background-color:{color}; color:#333; padding:2px 4px; border-radius:3px;'>[{p}]</span>")
                        break
                row_widget = QFrame()
                row_widget.setFrameShape(QFrame.StyledPanel)
                row_layout = QGridLayout(row_widget)
                row_layout.setColumnStretch(0, 1)
                row_layout.setColumnMinimumWidth(1, 60)
                row_layout.setColumnMinimumWidth(2, 55)
                row_layout.setColumnMinimumWidth(3, 50)
                row_layout.setColumnMinimumWidth(4, 85)
                row_layout.setColumnStretch(5, 1)         # ← 이 줄 추가: 버튼 오른쪽에 빈 공간
                info_lbl = QLabel(f"<span style='font-size:14px;'><b>{display_name}</b></span><br>추천 파밍: <span style='color:#007BFF; font-weight:bold;'>{count:,} 번</span> | 필요 영력: <span style='color:red;'>{req_stam:,}</span>")
                cb_level = QComboBox()
                levels = sorted(list(self.dungeon_drops.get(name, {}).keys()), reverse=True)
                cb_level.blockSignals(True)
                cb_level.addItems(levels)
                current_lvl = self.selected_dungeon_levels.get(name, levels[0] if levels else "")
                cb_level.setCurrentText(current_lvl)
                cb_level.blockSignals(False)
                cb_level.currentTextChanged.connect(lambda txt, n=name: self.on_dungeon_level_changed(n, txt))
                sp = QSpinBox()
                sp.setRange(0, 99999); sp.setValue(1); sp.setFixedWidth(50); sp.setButtonSymbols(QAbstractSpinBox.NoButtons)
                btn = QPushButton("🚀 대행 실행")
                btn.setStyleSheet("background-color: #6c757d; color: white; font-weight: bold; padding: 5px;")
                btn.clicked.connect(lambda checked, n=name, cb=cb_level, s=sp: self.perform_daehaeng(n, cb.currentText(), s.value()))
                row_layout.addWidget(info_lbl, 0, 0)
                row_layout.addWidget(cb_level, 0, 1)
                row_layout.addWidget(QLabel("대행 횟수:"), 0, 2)
                row_layout.addWidget(sp, 0, 3)
                row_layout.addWidget(btn, 0, 4)
                self.dungeon_layout.addWidget(row_widget)
        if vbar: QTimer.singleShot(0, lambda: vbar.setValue(saved_scroll))

if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    font = app.font()
    font.setPointSize(font.pointSize() + 1)
    app.setFont(font)
    calc = BleachCalcApp()
    calc.show()
    sys.exit(app.exec_())
