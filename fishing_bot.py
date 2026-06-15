"""
=============================================================
  بوت الصيد - GTA RP  v7.0
  + حفظ الإعدادات تلقائياً
  + تحديث تلقائي من GitHub
=============================================================
  pip install pydirectinput pyautogui pillow requests
=============================================================
"""

import sys, time, threading, json, os, subprocess
import tkinter as tk
from tkinter import scrolledtext, messagebox
import pydirectinput
import pyautogui
import requests

# ─────────────────────────────────────────────────────────────
#  إعداد التحديث التلقائي — عدّل هذا السطر فقط
# ─────────────────────────────────────────────────────────────
GITHUB_USER    = "Tetn5"          # ← اسم حسابك في GitHub
GITHUB_REPO    = "fishbot-gta"            # ← اسم الـ Repository
GITHUB_BRANCH  = "main"                   # ← اسم الـ Branch

CURRENT_VERSION = "1.0"

# رابط الملفات على GitHub (لا تعدّله)
_RAW = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/{GITHUB_BRANCH}"
VERSION_URL = f"{_RAW}/version.txt"
SCRIPT_URL  = f"{_RAW}/fishing_bot.py"

# ─────────────────────────────────────────────────────────────
#  مسار حفظ الإعدادات (جنب الملف نفسه)
# ─────────────────────────────────────────────────────────────
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

DEFAULT_CONFIG = {
    "bait_row":        6,
    "rod_row":         5,
    "delay_key":       0.35,
    "delay_open_bag":  1.4,
    "delay_close_bag": 0.8,
    "delay_use":       1.0,
    "delay_fishing":   14.0,
    "cycles":          0,
}

# ألوان الواجهة
BG     = "#0d1117"
BG2    = "#161b22"
BG3    = "#21262d"
ACCENT = "#58a6ff"
GREEN  = "#3fb950"
RED    = "#f85149"
YELLOW = "#d29922"
PURPLE = "#bc8cff"
TEXT   = "#e6edf3"
TEXT2  = "#8b949e"
BORDER = "#30363d"


# ══════════════════════════════════════════════════════════════
#   حفظ وتحميل الإعدادات
# ══════════════════════════════════════════════════════════════
def load_config() -> dict:
    """يحمّل الإعدادات من config.json — إذا ما وُجد يستخدم الافتراضي"""
    cfg = dict(DEFAULT_CONFIG)
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
            # ندمج المحفوظ مع الافتراضي (لو في مفاتيح جديدة في التحديث)
            cfg.update({k: saved[k] for k in DEFAULT_CONFIG if k in saved})
    except Exception:
        pass
    return cfg

def save_config(cfg: dict):
    """يحفظ الإعدادات في config.json"""
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════
#   التحديث التلقائي من GitHub
# ══════════════════════════════════════════════════════════════
class Updater:
    @staticmethod
    def check() -> tuple[bool, str]:
        """
        يتحقق من version.txt على GitHub.
        يعيد (يوجد_تحديث, الإصدار_الجديد)
        """
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
        """يحمّل الملف الجديد ويعيد تشغيل البرنامج"""
        try:
            log_fn("📥 جاري تحميل التحديث...", "yellow")
            r = requests.get(SCRIPT_URL, timeout=15)
            if r.status_code != 200:
                log_fn(f"❌ فشل التحميل: {r.status_code}", "red")
                return

            # حفظ الإعدادات الحالية قبل التحديث
            script_path = os.path.abspath(__file__)
            backup_path = script_path + ".backup"

            # نسخة احتياطية
            with open(backup_path, "wb") as f:
                f.write(open(script_path, "rb").read())

            # كتابة الملف الجديد
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(r.text)

            log_fn("✅ تم التحديث! إعادة التشغيل...", "green")
            time.sleep(1.5)

            # إعادة التشغيل
            subprocess.Popen([sys.executable, script_path])
            os._exit(0)

        except Exception as e:
            log_fn(f"❌ خطأ في التحديث: {e}", "red")


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
    def __init__(self): self.reset()


# ══════════════════════════════════════════════════════════════
#   البوت
# ══════════════════════════════════════════════════════════════
class FishingBot:
    def __init__(self, cfg, log_fn, status_fn, stats_fn):
        self.cfg          = cfg
        self.log          = log_fn
        self.set_status   = status_fn
        self.update_stats = stats_fn
        self.running      = False
        self.paused       = False
        self.stats        = Stats()
        self.inp          = GameInput()
        self._thread      = None

    def start(self):
        if self._thread and self._thread.is_alive(): return
        self.running = True
        self.paused  = False
        self.stats.reset()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self.running = False
        self.paused  = False

    def toggle_pause(self):
        self.paused = not self.paused

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

    def _step_rod(self):
        row = self.cfg["rod_row"]
        self.log(f"── السنارة  (↓×{row})", "cyan")
        self.inp.press("f2",     self.cfg["delay_open_bag"])
        self.inp.down_arrows(row, self.cfg["delay_key"])
        self.inp.press("enter",  self.cfg["delay_use"])
        self.inp.press("enter",  self.cfg["delay_use"])
        self.inp.press("delete", self.cfg["delay_close_bag"])
        self.log("🎣 السنارة جاهزة", "green")

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

        self.log("✅ انتهى وقت الصيد", "green")

    def _loop(self):
        self.log("🚀 البوت يعمل!", "green")
        self.set_status("🟢 يعمل")
        try:
            while self.running:
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

                max_c = self.cfg.get("cycles", 0)
                if max_c > 0 and self.stats.cycles >= max_c:
                    self.log(f"✅ اكتملت {self.stats.cycles} دورة!", "green")
                    break

                time.sleep(0.3)

        except Exception as e:
            self.log(f"❌ خطأ: {e}", "red")

        self.running = False
        self.set_status("⚫ متوقف")
        elapsed = int(time.time() - self.stats.start_time)
        mm, ss = divmod(elapsed, 60)
        hh, mm = divmod(mm, 60)
        self.log(
            f"⛔ انتهى | دورات: {self.stats.cycles} | "
            f"طعم مستخدم: {self.stats.bait_used} | "
            f"وقت: {hh:02d}:{mm:02d}:{ss:02d}",
            "yellow"
        )


# ══════════════════════════════════════════════════════════════
#   الواجهة
# ══════════════════════════════════════════════════════════════
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"🎣 Fish Bot v{CURRENT_VERSION}  |  GTA RP")
        self.geometry("900x600")
        self.resizable(False, False)
        self.configure(bg=BG)

        # تحميل الإعدادات المحفوظة
        self.cfg        = load_config()
        self.bot        = None
        self._countdown = 0

        self._build_ui()

        # فحص التحديثات عند الفتح (في الخلفية)
        threading.Thread(target=self._check_update_bg, daemon=True).start()

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

        # زر التحديث (مخفي حتى يظهر تحديث)
        self.btn_update = tk.Button(
            hdr, text="🔄 تحديث متاح!",
            bg=YELLOW, fg="black", relief="flat", cursor="hand2",
            font=("Segoe UI", 9, "bold"),
            command=self._do_update
        )
        # لا نعرضه الآن — يظهر فقط لو في تحديث

        # جسم
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=12, pady=8)

        left  = tk.Frame(body, bg=BG)
        left.pack(side="left", fill="both", expand=True)
        right = tk.Frame(body, bg=BG, width=320)
        right.pack(side="right", fill="y", padx=(10, 0))
        right.pack_propagate(False)

        self._build_stats(left)
        self._build_log(left)
        self._build_settings(right)
        self._build_controls(right)

    # ── الإحصائيات ───────────────────────────────────────────
    def _build_stats(self, p):
        f = tk.Frame(p, bg=BG2,
                     highlightthickness=1, highlightbackground=BORDER)
        f.pack(fill="x", pady=(0, 8))
        tk.Label(f, text="📊  إحصائيات الجلسة",
                 bg=BG2, fg=ACCENT, font=("Segoe UI", 10, "bold")
                 ).pack(anchor="w", padx=10, pady=(6, 2))
        row = tk.Frame(f, bg=BG2)
        row.pack(fill="x", padx=10, pady=(0, 8))

        def box(label, attr, color):
            b = tk.Frame(row, bg=BG3, padx=10, pady=6,
                         highlightthickness=1, highlightbackground=BORDER)
            b.pack(side="left", expand=True, fill="x", padx=3)
            tk.Label(b, text=label, bg=BG3, fg=TEXT2,
                     font=("Segoe UI", 8)).pack()
            lbl = tk.Label(b, text="0", bg=BG3, fg=color,
                           font=("Segoe UI", 16, "bold"))
            lbl.pack()
            setattr(self, attr, lbl)

        box("🔄 الدورات",      "lbl_cycles",  PURPLE)
        box("🪱 طعم مستخدم",  "lbl_bused",   YELLOW)
        box("⏱️  وقت الجلسة", "lbl_session", TEXT2)

    # ── السجل ────────────────────────────────────────────────
    def _build_log(self, p):
        f = tk.Frame(p, bg=BG3,
                     highlightthickness=1, highlightbackground=BORDER)
        f.pack(fill="both", expand=True)
        tk.Label(f, text="📋  السجل",
                 bg=BG3, fg=TEXT2, font=("Segoe UI", 9)
                 ).pack(anchor="w", padx=8, pady=3)
        self.log_box = scrolledtext.ScrolledText(
            f, bg=BG, fg=TEXT, font=("Consolas", 9),
            insertbackground=TEXT, bd=0, relief="flat",
            state="disabled", height=14)
        self.log_box.pack(fill="both", expand=True, padx=4, pady=(0, 4))
        for tag, clr in [
            ("green", GREEN), ("red", RED), ("yellow", YELLOW),
            ("cyan",  ACCENT),("accent", PURPLE), ("white", TEXT),
        ]:
            self.log_box.tag_config(tag, foreground=clr)

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
        ]

        self._vars = {}
        for label, key, typ in fields:
            row = tk.Frame(f, bg=BG2)
            row.pack(fill="x", padx=8, pady=2)
            tk.Label(row, text=label, bg=BG2, fg=TEXT2,
                     font=("Segoe UI", 8), width=16, anchor="w"
                     ).pack(side="left")
            var = tk.StringVar(value=str(self.cfg[key]))
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

        self.lbl_countdown = tk.Label(f, text="",
                                       bg=BG2, fg=YELLOW,
                                       font=("Segoe UI", 20, "bold"))
        self.lbl_countdown.pack(pady=4)

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

    # ── التحديث ──────────────────────────────────────────────
    def _check_update_bg(self):
        """يفحص التحديث في الخلفية عند الفتح"""
        has_update, latest = Updater.check()
        if has_update:
            def show():
                self.btn_update.config(
                    text=f"🔄 تحديث v{latest} متاح — اضغط للتحديث"
                )
                self.btn_update.pack(side="right", padx=8, pady=8)
                self._log(f"🔄 يوجد تحديث جديد v{latest}! اضغط الزر في الأعلى.", "yellow")
            self.after(0, show)

    def _do_update(self):
        if not messagebox.askyesno(
            "تحديث", "سيتم تحديث البرنامج وإعادة تشغيله.\nالإعدادات ستُحفظ تلقائياً.\nتكمل؟"
        ):
            return
        self._apply_settings()   # حفظ الإعدادات قبل التحديث
        threading.Thread(
            target=Updater.download_and_restart,
            args=(self._log,),
            daemon=True
        ).start()

    # ── أحداث ────────────────────────────────────────────────
    def _apply_settings(self):
        for key, (var, typ) in self._vars.items():
            try:
                self.cfg[key] = int(var.get()) if typ == "int" else float(var.get())
            except ValueError:
                pass
        save_config(self.cfg)
        self._log("💾 تم حفظ الإعدادات", "green")

    def _on_start(self):
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
            status_fn=self._set_status, stats_fn=self._refresh_stats,
        )
        self.bot.start()
        self.btn_start.config(state="disabled")
        self.btn_pause.config(state="normal")
        self.btn_stop.config(state="normal")
        self._poll()

    def _on_pause(self):
        if not self.bot: return
        self.bot.toggle_pause()
        self.btn_pause.config(
            text="▶  استئناف" if self.bot.paused else "⏸  إيقاف مؤقت"
        )

    def _on_stop(self):
        if self.bot: self.bot.stop()
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


# ══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    for pkg, name in [
        ("pydirectinput", "pydirectinput"),
        ("pyautogui",     "pyautogui"),
        ("requests",      "requests"),
    ]:
        try:
            __import__(pkg)
        except ImportError:
            print(f"❌ مكتبة مفقودة: {name}")
            print("ثبّت: pip install pydirectinput pyautogui requests")
            sys.exit(1)

    App().mainloop()