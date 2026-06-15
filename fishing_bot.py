"""
=============================================================
  بوت الصيد - GTA RP  v8.0
  + صوت تنبيه
  + Hotkey تشغيل/إيقاف
  + إيقاف تلقائي لو اللعبة أُغلقت
  + حد أقصى للطعم
  + سجل الجلسات السابقة
  + حفظ الإعدادات
  + تحديث تلقائي من GitHub
=============================================================
  pip install pydirectinput pyautogui requests keyboard psutil
=============================================================
"""

import sys, time, threading, json, os, subprocess, winsound
import tkinter as tk
from tkinter import scrolledtext, messagebox, ttk
import pydirectinput
import pyautogui
import requests
import keyboard
import psutil

# ─────────────────────────────────────────────────────────────
#  GitHub — عدّل هذين السطرين فقط
# ─────────────────────────────────────────────────────────────
GITHUB_USER   = "Tetn5"
GITHUB_REPO   = "fishbot-gta"
GITHUB_BRANCH = "main"

CURRENT_VERSION = "1.0"
_RAW        = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/{GITHUB_BRANCH}"
VERSION_URL = f"{_RAW}/version.txt"
SCRIPT_URL  = f"{_RAW}/fishing_bot.py"

# ─────────────────────────────────────────────────────────────
#  مسارات الملفات
# ─────────────────────────────────────────────────────────────
_DIR         = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH  = os.path.join(_DIR, "config.json")
HISTORY_PATH = os.path.join(_DIR, "sessions.json")

# ─────────────────────────────────────────────────────────────
#  اسم نافذة اللعبة (جزء منه يكفي)
# ─────────────────────────────────────────────────────────────
GAME_WINDOW_NAME = "GTA"   # ← عدّله لو الاسم مختلف

# ─────────────────────────────────────────────────────────────
DEFAULT_CONFIG = {
    "bait_row":        6,
    "rod_row":         5,
    "delay_key":       0.35,
    "delay_open_bag":  1.4,
    "delay_close_bag": 0.8,
    "delay_use":       1.0,
    "delay_fishing":   14.0,
    "cycles":          0,      # 0 = لانهائي
    "max_bait":        0,      # 0 = بلا حد
    "hotkey_start":    "f6",   # مفتاح تشغيل/إيقاف
}

# ألوان
BG     = "#0d1117"
BG2    = "#161b22"
BG3    = "#21262d"
ACCENT = "#58a6ff"
GREEN  = "#3fb950"
RED    = "#f85149"
YELLOW = "#d29922"
PURPLE = "#bc8cff"
TEAL   = "#39d353"
TEXT   = "#e6edf3"
TEXT2  = "#8b949e"
BORDER = "#30363d"


# ══════════════════════════════════════════════════════════════
#   الإعدادات
# ══════════════════════════════════════════════════════════════
def load_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    try:
        if os.path.exists(CONFIG_PATH):
            saved = json.loads(open(CONFIG_PATH, encoding="utf-8").read())
            cfg.update({k: saved[k] for k in DEFAULT_CONFIG if k in saved})
    except Exception:
        pass
    return cfg

def save_config(cfg: dict):
    try:
        open(CONFIG_PATH, "w", encoding="utf-8").write(
            json.dumps(cfg, indent=2, ensure_ascii=False)
        )
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════
#   سجل الجلسات
# ══════════════════════════════════════════════════════════════
def load_history() -> list:
    try:
        if os.path.exists(HISTORY_PATH):
            return json.loads(open(HISTORY_PATH, encoding="utf-8").read())
    except Exception:
        pass
    return []

def save_session(session: dict):
    """يضيف جلسة جديدة للسجل ويحتفظ بآخر 50 جلسة"""
    try:
        history = load_history()
        history.insert(0, session)
        history = history[:50]
        open(HISTORY_PATH, "w", encoding="utf-8").write(
            json.dumps(history, indent=2, ensure_ascii=False)
        )
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════
#   الصوت
# ══════════════════════════════════════════════════════════════
class Sound:
    @staticmethod
    def beep_done():
        """صوت انتهاء الصيد — نغمتان"""
        threading.Thread(target=lambda: (
            winsound.Beep(800, 150),
            time.sleep(0.05),
            winsound.Beep(1000, 200),
        ), daemon=True).start()

    @staticmethod
    def beep_warn():
        """صوت تحذير (طعم قليل أو لعبة مغلقة)"""
        threading.Thread(target=lambda: (
            winsound.Beep(400, 300),
            time.sleep(0.1),
            winsound.Beep(300, 500),
        ), daemon=True).start()

    @staticmethod
    def beep_start():
        """صوت بدء"""
        threading.Thread(target=lambda: winsound.Beep(600, 100),
                         daemon=True).start()


# ══════════════════════════════════════════════════════════════
#   مراقب اللعبة
# ══════════════════════════════════════════════════════════════
class GameWatcher:
    @staticmethod
    def is_running() -> bool:
        """هل اللعبة شغّالة؟ (يبحث في العمليات)"""
        name_lower = GAME_WINDOW_NAME.lower()
        for proc in psutil.process_iter(["name"]):
            try:
                if name_lower in proc.info["name"].lower():
                    return True
            except Exception:
                pass
        return False


# ══════════════════════════════════════════════════════════════
#   التحديث
# ══════════════════════════════════════════════════════════════
class Updater:
    @staticmethod
    def check():
        try:
            r = requests.get(VERSION_URL, timeout=5)
            if r.status_code == 200:
                latest = r.text.strip()
                if latest != CURRENT_VERSION:
                    return True, latest
        except Exception:
            pass
        return False, CURRENT_VERSION

    @staticmethod
    def download_and_restart(log_fn):
        try:
            log_fn("📥 جاري تحميل التحديث...", "yellow")
            r = requests.get(SCRIPT_URL, timeout=15)
            if r.status_code != 200:
                log_fn(f"❌ فشل: {r.status_code}", "red")
                return
            script = os.path.abspath(__file__)
            open(script + ".backup", "wb").write(open(script, "rb").read())
            open(script, "w", encoding="utf-8").write(r.text)
            log_fn("✅ تم! إعادة التشغيل...", "green")
            time.sleep(1.5)
            subprocess.Popen([sys.executable, script])
            os._exit(0)
        except Exception as e:
            log_fn(f"❌ خطأ: {e}", "red")


# ══════════════════════════════════════════════════════════════
#   محرك الأوامر
# ══════════════════════════════════════════════════════════════
class GameInput:
    @staticmethod
    def press(key: str, delay: float = 0.35):
        k = key.lower()
        if k == "enter": k = "return"
        if k == "esc":   k = "escape"
        pydirectinput.press(k)
        time.sleep(delay)

    @staticmethod
    def down_arrows(n: int, delay: float = 0.35):
        for _ in range(n):
            pydirectinput.press("down")
            time.sleep(delay)


# ══════════════════════════════════════════════════════════════
#   الإحصائيات
# ══════════════════════════════════════════════════════════════
class Stats:
    def reset(self):
        self.cycles     = 0
        self.bait_used  = 0
        self.start_time = time.time()
        self.stop_reason = ""
    def __init__(self): self.reset()


# ══════════════════════════════════════════════════════════════
#   البوت
# ══════════════════════════════════════════════════════════════
class FishingBot:
    def __init__(self, cfg, log_fn, status_fn, stats_fn, stop_fn):
        self.cfg         = cfg
        self.log         = log_fn
        self.set_status  = status_fn
        self.update_stats = stats_fn
        self.on_stop     = stop_fn      # callback لما يتوقف
        self.running     = False
        self.paused      = False
        self.stats       = Stats()
        self.inp         = GameInput()
        self._thread     = None

    def start(self):
        if self._thread and self._thread.is_alive(): return
        self.running = True
        self.paused  = False
        self.stats.reset()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self, reason="يدوي"):
        self.stats.stop_reason = reason
        self.running = False
        self.paused  = False

    def toggle_pause(self):
        self.paused = not self.paused

    # ── وضع الطعم ────────────────────────────────────────────
    def _step_bait(self):
        row = self.cfg["bait_row"]
        self.log(f"── وضع الطعم  (↓×{row})", "cyan")
        self.inp.press("f2",     self.cfg["delay_open_bag"])
        self.inp.down_arrows(row, self.cfg["delay_key"])
        self.inp.press("enter",  self.cfg["delay_use"])
        self.inp.press("enter",  self.cfg["delay_use"])
        self.inp.press("delete", self.cfg["delay_close_bag"])
        self.stats.bait_used += 1
        self.update_stats()
        self.log("✔️  الطعم جاهز", "green")

    # ── تجهيز السنارة ────────────────────────────────────────
    def _step_rod(self):
        row = self.cfg["rod_row"]
        self.log(f"── السنارة  (↓×{row})", "cyan")
        self.inp.press("f2",     self.cfg["delay_open_bag"])
        self.inp.down_arrows(row, self.cfg["delay_key"])
        self.inp.press("enter",  self.cfg["delay_use"])
        self.inp.press("enter",  self.cfg["delay_use"])
        self.inp.press("delete", self.cfg["delay_close_bag"])
        self.log("🎣 السنارة جاهزة", "green")

    # ── انتظار الصيد ─────────────────────────────────────────
    def _wait_fishing(self):
        total = float(self.cfg["delay_fishing"])
        CHECK = 0.5
        steps = int(total / CHECK)
        start = time.time()
        self.log(f"⏳ صيد: {total:.0f}s", "cyan")

        for _ in range(steps):
            if not self.running: return
            while self.paused and self.running:
                self.set_status("⏸️  إيقاف مؤقت")
                time.sleep(0.1)
            elapsed   = time.time() - start
            remaining = max(0.0, total - elapsed)
            pct       = min(100, int((elapsed / total) * 100))
            bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
            self.set_status(f"🎣 [{bar}] {pct}%  ({remaining:.0f}s)")
            time.sleep(CHECK)

        Sound.beep_done()
        self.log("✅ انتهى وقت الصيد", "green")

    # ── الحلقة الرئيسية ──────────────────────────────────────
    def _loop(self):
        Sound.beep_start()
        self.log("🚀 البوت يعمل!", "green")
        self.set_status("🟢 يعمل")

        try:
            while self.running:
                # ── فحص اللعبة كل دورة ──
                if not GameWatcher.is_running():
                    self.log("⚠️  اللعبة مغلقة! توقف تلقائي.", "red")
                    Sound.beep_warn()
                    self.stop("اللعبة مغلقة")
                    break

                # ── فحص حد الطعم ──
                max_bait = self.cfg.get("max_bait", 0)
                if max_bait > 0 and self.stats.bait_used >= max_bait:
                    self.log(f"🛑 وصلت لحد الطعم ({max_bait})! توقف.", "yellow")
                    Sound.beep_warn()
                    self.stop("حد الطعم")
                    break

                while self.paused and self.running:
                    self.set_status("⏸️  إيقاف مؤقت")
                    time.sleep(0.2)
                if not self.running: break

                self.stats.cycles += 1
                self.update_stats()
                self.log(f"━━━ دورة {self.stats.cycles} ━━━", "accent")

                self._step_bait()
                if not self.running: break
                time.sleep(0.3)

                self._step_rod()
                if not self.running: break
                time.sleep(0.3)

                self._wait_fishing()
                if not self.running: break

                # ── فحص عدد الدورات ──
                max_c = self.cfg.get("cycles", 0)
                if max_c > 0 and self.stats.cycles >= max_c:
                    self.log(f"✅ اكتملت {self.stats.cycles} دورة!", "green")
                    self.stop("اكتملت الدورات")
                    break

                time.sleep(0.3)

        except Exception as e:
            self.log(f"❌ خطأ: {e}", "red")
            self.stop("خطأ")

        # ── حفظ الجلسة ──
        elapsed = int(time.time() - self.stats.start_time)
        mm, ss  = divmod(elapsed, 60)
        hh, mm  = divmod(mm, 60)
        duration = f"{hh:02d}:{mm:02d}:{ss:02d}"

        session = {
            "date":       time.strftime("%Y-%m-%d %H:%M"),
            "cycles":     self.stats.cycles,
            "bait_used":  self.stats.bait_used,
            "duration":   duration,
            "stop_reason": self.stats.stop_reason or "يدوي",
        }
        save_session(session)

        self.running = False
        self.set_status("⚫ متوقف")
        self.log(
            f"⛔ انتهى | دورات:{self.stats.cycles} | "
            f"طعم:{self.stats.bait_used} | وقت:{duration} | "
            f"سبب:{self.stats.stop_reason or 'يدوي'}",
            "yellow"
        )
        self.on_stop()


# ══════════════════════════════════════════════════════════════
#   الواجهة
# ══════════════════════════════════════════════════════════════
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"🎣 Fish Bot v{CURRENT_VERSION}  |  GTA RP")
        self.geometry("980x640")
        self.resizable(False, False)
        self.configure(bg=BG)

        self.cfg        = load_config()
        self.bot        = None
        self._countdown = 0
        self._hotkey_id = None

        self._build_ui()
        self._register_hotkey()

        # فحص تحديث في الخلفية
        threading.Thread(target=self._check_update_bg, daemon=True).start()

        # تنظيف عند الإغلاق
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── بناء الواجهة ─────────────────────────────────────────
    def _build_ui(self):
        # شريط العنوان
        hdr = tk.Frame(self, bg=BG2, height=48)
        hdr.pack(fill="x")
        tk.Label(hdr, text=f"🎣  Fish Bot v{CURRENT_VERSION}  |  GTA RP",
                 bg=BG2, fg=ACCENT, font=("Segoe UI", 14, "bold")
                 ).pack(side="left", padx=16, pady=10)
        self.lbl_status = tk.Label(hdr, text="⚫ متوقف",
                                    bg=BG2, fg=TEXT2, font=("Segoe UI", 11))
        self.lbl_status.pack(side="right", padx=16)
        self.btn_update = tk.Button(
            hdr, text="", bg=YELLOW, fg="black",
            relief="flat", cursor="hand2",
            font=("Segoe UI", 9, "bold"),
            command=self._do_update)

        # Notebook (تبويبات)
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=10, pady=8)

        left  = tk.Frame(body, bg=BG)
        left.pack(side="left", fill="both", expand=True)
        right = tk.Frame(body, bg=BG, width=330)
        right.pack(side="right", fill="y", padx=(10, 0))
        right.pack_propagate(False)

        # تبويبات يسار
        nb = ttk.Notebook(left)
        nb.pack(fill="both", expand=True)
        style = ttk.Style()
        style.theme_use("default")
        style.configure("TNotebook",        background=BG,  borderwidth=0)
        style.configure("TNotebook.Tab",    background=BG3, foreground=TEXT2,
                         padding=[12,4], font=("Segoe UI",9))
        style.map("TNotebook.Tab",
                  background=[("selected", BG2)],
                  foreground=[("selected", ACCENT)])

        tab_main    = tk.Frame(nb, bg=BG)
        tab_history = tk.Frame(nb, bg=BG)
        nb.add(tab_main,    text="📊  الجلسة الحالية")
        nb.add(tab_history, text="📁  سجل الجلسات")

        self._build_stats(tab_main)
        self._build_log(tab_main)
        self._build_history(tab_history)

        self._build_settings(right)
        self._build_controls(right)

    # ── إحصائيات الجلسة ──────────────────────────────────────
    def _build_stats(self, p):
        f = tk.Frame(p, bg=BG2,
                     highlightthickness=1, highlightbackground=BORDER)
        f.pack(fill="x", pady=(4, 6))
        tk.Label(f, text="📊  إحصائيات الجلسة",
                 bg=BG2, fg=ACCENT, font=("Segoe UI", 10, "bold")
                 ).pack(anchor="w", padx=10, pady=(6, 2))
        row = tk.Frame(f, bg=BG2)
        row.pack(fill="x", padx=10, pady=(0, 8))

        def box(label, attr, color):
            b = tk.Frame(row, bg=BG3, padx=8, pady=6,
                         highlightthickness=1, highlightbackground=BORDER)
            b.pack(side="left", expand=True, fill="x", padx=3)
            tk.Label(b, text=label, bg=BG3, fg=TEXT2,
                     font=("Segoe UI", 8)).pack()
            lbl = tk.Label(b, text="0", bg=BG3, fg=color,
                           font=("Segoe UI", 15, "bold"))
            lbl.pack()
            setattr(self, attr, lbl)

        box("🔄 الدورات",      "lbl_cycles",  PURPLE)
        box("🪱 طعم مستخدم",  "lbl_bused",   YELLOW)
        box("⏱️  وقت الجلسة", "lbl_session", TEXT2)

    # ── السجل ────────────────────────────────────────────────
    def _build_log(self, p):
        f = tk.Frame(p, bg=BG3,
                     highlightthickness=1, highlightbackground=BORDER)
        f.pack(fill="both", expand=True, pady=(0, 4))
        tk.Label(f, text="📋  السجل",
                 bg=BG3, fg=TEXT2, font=("Segoe UI", 9)
                 ).pack(anchor="w", padx=8, pady=3)
        self.log_box = scrolledtext.ScrolledText(
            f, bg=BG, fg=TEXT, font=("Consolas", 9),
            insertbackground=TEXT, bd=0, relief="flat",
            state="disabled", height=12)
        self.log_box.pack(fill="both", expand=True, padx=4, pady=(0, 4))
        for tag, clr in [
            ("green", GREEN), ("red", RED), ("yellow", YELLOW),
            ("cyan",  ACCENT), ("accent", PURPLE), ("white", TEXT),
        ]:
            self.log_box.tag_config(tag, foreground=clr)

    # ── سجل الجلسات ──────────────────────────────────────────
    def _build_history(self, p):
        f = tk.Frame(p, bg=BG)
        f.pack(fill="both", expand=True, padx=4, pady=4)

        # جدول
        cols = ("التاريخ", "الدورات", "الطعم", "المدة", "السبب")
        self.hist_tree = ttk.Treeview(f, columns=cols, show="headings", height=18)

        style = ttk.Style()
        style.configure("Treeview",
                         background=BG2, foreground=TEXT,
                         fieldbackground=BG2, rowheight=24,
                         font=("Segoe UI", 9))
        style.configure("Treeview.Heading",
                         background=BG3, foreground=ACCENT,
                         font=("Segoe UI", 9, "bold"))
        style.map("Treeview", background=[("selected", BG3)])

        widths = [130, 70, 70, 80, 90]
        for col, w in zip(cols, widths):
            self.hist_tree.heading(col, text=col)
            self.hist_tree.column(col, width=w, anchor="center")

        sb = ttk.Scrollbar(f, orient="vertical", command=self.hist_tree.yview)
        self.hist_tree.configure(yscrollcommand=sb.set)
        self.hist_tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        tk.Button(p, text="🗑️  مسح السجل",
                  bg=BG3, fg=RED, relief="flat", cursor="hand2",
                  font=("Segoe UI", 9),
                  command=self._clear_history
                  ).pack(pady=4)

        self._load_history_ui()

    def _load_history_ui(self):
        """يحمّل الجلسات في الجدول"""
        for item in self.hist_tree.get_children():
            self.hist_tree.delete(item)
        for s in load_history():
            self.hist_tree.insert("", "end", values=(
                s.get("date", "—"),
                s.get("cycles", 0),
                s.get("bait_used", 0),
                s.get("duration", "—"),
                s.get("stop_reason", "—"),
            ))

    def _clear_history(self):
        if messagebox.askyesno("مسح", "تحذف كل سجل الجلسات؟"):
            try:
                open(HISTORY_PATH, "w").write("[]")
            except Exception:
                pass
            self._load_history_ui()

    # ── الإعدادات ─────────────────────────────────────────────
    def _build_settings(self, p):
        f = tk.LabelFrame(p, text=" ⚙️ الإعدادات ",
                          bg=BG2, fg=ACCENT, font=("Segoe UI", 9, "bold"),
                          bd=1, relief="solid", labelanchor="n")
        f.pack(fill="x", pady=(0, 8))

        fields = [
            ("طعم سمك  (↓ مرات)",    "bait_row",        "int"),
            ("سنارة صيد (↓ مرات)",   "rod_row",         "int"),
            ("تأخير المفاتيح (s)",   "delay_key",       "float"),
            ("فتح الحقيبة (s)",      "delay_open_bag",  "float"),
            ("إغلاق الحقيبة (s)",    "delay_close_bag", "float"),
            ("انتظار Enter (s)",      "delay_use",       "float"),
            ("⏱ وقت الصيد (s)",     "delay_fishing",   "float"),
            ("الدورات  (0=∞)",       "cycles",          "int"),
            ("حد الطعم  (0=∞)",      "max_bait",        "int"),
            ("Hotkey تشغيل",          "hotkey_start",    "str"),
        ]

        self._vars = {}
        for label, key, typ in fields:
            row = tk.Frame(f, bg=BG2)
            row.pack(fill="x", padx=8, pady=1)
            tk.Label(row, text=label, bg=BG2, fg=TEXT2,
                     font=("Segoe UI", 8), width=17, anchor="w"
                     ).pack(side="left")
            var = tk.StringVar(value=str(self.cfg.get(key, DEFAULT_CONFIG.get(key, ""))))
            self._vars[key] = (var, typ)
            tk.Entry(row, textvariable=var, bg=BG3, fg=TEXT,
                     insertbackground=TEXT, relief="flat",
                     font=("Segoe UI", 9), width=7
                     ).pack(side="right")

        tk.Button(f, text="💾  حفظ الإعدادات",
                  bg=BG3, fg=ACCENT, relief="flat", cursor="hand2",
                  font=("Segoe UI", 9),
                  command=self._apply_settings
                  ).pack(fill="x", padx=8, pady=6)

    # ── التحكم ───────────────────────────────────────────────
    def _build_controls(self, p):
        f = tk.LabelFrame(p, text=" 🎮 التحكم ",
                          bg=BG2, fg=ACCENT, font=("Segoe UI", 9, "bold"),
                          bd=1, relief="solid", labelanchor="n")
        f.pack(fill="x")

        # عرض الـ Hotkey الحالي
        self.lbl_hotkey = tk.Label(f,
            text=f"⌨️  Hotkey: {self.cfg.get('hotkey_start','f6').upper()}",
            bg=BG2, fg=TEXT2, font=("Segoe UI", 9))
        self.lbl_hotkey.pack(pady=(6, 0))

        self.lbl_countdown = tk.Label(f, text="",
                                       bg=BG2, fg=YELLOW,
                                       font=("Segoe UI", 20, "bold"))
        self.lbl_countdown.pack(pady=2)

        self.btn_start = tk.Button(f, text="▶  تشغيل",
            bg=GREEN, fg="black", activebackground="#2ea043",
            font=("Segoe UI", 12, "bold"), relief="flat",
            cursor="hand2", height=2, command=self._on_start)
        self.btn_start.pack(fill="x", padx=8, pady=4)

        self.btn_pause = tk.Button(f, text="⏸  إيقاف مؤقت",
            bg=YELLOW, fg="black", font=("Segoe UI", 10),
            relief="flat", cursor="hand2", state="disabled",
            command=self._on_pause)
        self.btn_pause.pack(fill="x", padx=8, pady=2)

        self.btn_stop = tk.Button(f, text="⛔  إيقاف",
            bg=RED, fg="white", font=("Segoe UI", 10),
            relief="flat", cursor="hand2", state="disabled",
            command=self._on_stop)
        self.btn_stop.pack(fill="x", padx=8, pady=(2, 8))

    # ── Hotkey ────────────────────────────────────────────────
    def _register_hotkey(self):
        """تسجيل مفتاح التشغيل/الإيقاف"""
        try:
            if self._hotkey_id:
                keyboard.remove_hotkey(self._hotkey_id)
        except Exception:
            pass
        hk = self.cfg.get("hotkey_start", "f6")
        try:
            self._hotkey_id = keyboard.add_hotkey(hk, self._hotkey_pressed)
        except Exception:
            pass

    def _hotkey_pressed(self):
        """يُستدعى من أي مكان عند الضغط على Hotkey"""
        if not self.bot or not self.bot.running:
            self.after(0, self._on_start)
        elif self.bot.running and not self.bot.paused:
            self.after(0, self._on_pause)
        else:
            self.after(0, self._on_pause)  # استئناف

    # ── التحديث ──────────────────────────────────────────────
    def _check_update_bg(self):
        has, latest = Updater.check()
        if has:
            def show():
                self.btn_update.config(text=f"🔄 تحديث v{latest} متاح!")
                self.btn_update.pack(side="right", padx=8, pady=8)
                self._log(f"🔄 تحديث v{latest} متاح! اضغط الزر.", "yellow")
            self.after(0, show)

    def _do_update(self):
        if not messagebox.askyesno("تحديث",
            "سيتم تحديث البرنامج وإعادة تشغيله.\nالإعدادات ستُحفظ.\nتكمل؟"):
            return
        self._apply_settings()
        threading.Thread(
            target=Updater.download_and_restart,
            args=(self._log,), daemon=True
        ).start()

    # ── أحداث ────────────────────────────────────────────────
    def _apply_settings(self):
        for key, (var, typ) in self._vars.items():
            try:
                v = var.get()
                if typ == "int":   self.cfg[key] = int(v)
                elif typ == "float": self.cfg[key] = float(v)
                else:              self.cfg[key] = v.strip()
            except ValueError:
                pass
        save_config(self.cfg)
        self._register_hotkey()
        hk = self.cfg.get("hotkey_start", "f6").upper()
        self.lbl_hotkey.config(text=f"⌨️  Hotkey: {hk}")
        self._log("💾 تم حفظ الإعدادات", "green")

    def _on_start(self):
        if self.bot and self.bot.running: return
        self._apply_settings()
        self._countdown = 5
        self._do_countdown()

    def _do_countdown(self):
        if self._countdown > 0:
            self.lbl_countdown.config(text=f"{self._countdown}")
            self.btn_start.config(state="disabled")
            self._countdown -= 1
            self.after(1000, self._do_countdown)
        else:
            self.lbl_countdown.config(text="")
            self._start_bot()

    def _start_bot(self):
        self.bot = FishingBot(
            cfg=self.cfg, log_fn=self._log,
            status_fn=self._set_status,
            stats_fn=self._refresh_stats,
            stop_fn=self._on_bot_stopped,
        )
        self.bot.start()
        self.btn_start.config(state="disabled")
        self.btn_pause.config(state="normal")
        self.btn_stop.config(state="normal")
        self._poll()

    def _on_bot_stopped(self):
        """يُستدعى من البوت لما يتوقف"""
        self.after(0, self._load_history_ui)  # تحديث سجل الجلسات

    def _on_pause(self):
        if not self.bot: return
        self.bot.toggle_pause()
        self.btn_pause.config(
            text="▶  استئناف" if self.bot.paused else "⏸  إيقاف مؤقت"
        )

    def _on_stop(self):
        if self.bot: self.bot.stop("يدوي")
        self.btn_start.config(state="normal")
        self.btn_pause.config(state="disabled", text="⏸  إيقاف مؤقت")
        self.btn_stop.config(state="disabled")

    def _poll(self):
        if not self.bot: return
        self._refresh_stats()
        if self.bot.running:
            self.after(500, self._poll)
        else:
            self.btn_start.config(state="normal")
            self.btn_pause.config(state="disabled")
            self.btn_stop.config(state="disabled")

    def _refresh_stats(self):
        if not self.bot: return
        s = self.bot.stats
        def upd():
            self.lbl_cycles.config(text=str(s.cycles))
            self.lbl_bused .config(text=str(s.bait_used))
            el = int(time.time() - s.start_time)
            mm, ss = divmod(el, 60)
            hh, mm = divmod(mm, 60)
            self.lbl_session.config(text=f"{hh:02d}:{mm:02d}:{ss:02d}")
        self.after(0, upd)

    def _log(self, msg: str, color: str = "white"):
        def _do():
            self.log_box.config(state="normal")
            self.log_box.insert("end",
                f"[{time.strftime('%H:%M:%S')}] {msg}\n", color)
            self.log_box.see("end")
            self.log_box.config(state="disabled")
        self.after(0, _do)

    def _set_status(self, text: str):
        self.after(0, lambda: self.lbl_status.config(text=text))

    def _on_close(self):
        try:
            keyboard.unhook_all()
        except Exception:
            pass
        if self.bot: self.bot.stop("إغلاق البرنامج")
        self.destroy()


# ══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    for pkg, name in [
        ("pydirectinput", "pydirectinput"),
        ("pyautogui",     "pyautogui"),
        ("requests",      "requests"),
        ("keyboard",      "keyboard"),
        ("psutil",        "psutil"),
    ]:
        try:
            __import__(pkg)
        except ImportError:
            print(f"❌ مكتبة مفقودة: {name}")
            print("ثبّت: pip install pydirectinput pyautogui requests keyboard psutil")
            sys.exit(1)

    App().mainloop()
