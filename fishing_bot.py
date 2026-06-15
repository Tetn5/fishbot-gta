"""
=============================================================
  بوت الصيد - GTA RP  v2.0
  + قراءة الشاشة بصرياً (OCR عربي عبر EasyOCR)
  + إيقاف تلقائي عند امتلاء الحقيبة / نفاد الطعم
  + عدّ الأسماك المصطادة
  + إصلاح منطق الصوت (يطلع عند انتهاء عمل البوت فعلاً)
  + حفظ الإعدادات تلقائياً & تحديث تلقائي
  + تنبيهات صوتية & مفتاح اختصار (Hotkey)
=============================================================
  pip install pydirectinput keyboard requests easyocr pillow mss numpy
  (EasyOCR كبير الحجم أول مرة لأنه يحمّل موديل العربية ~64MB)
=============================================================
"""

import sys, time, threading, json, os, subprocess, re
import tkinter as tk
from tkinter import scrolledtext, messagebox
import pydirectinput
import keyboard
import winsound
import requests

# مكتبات قراءة الشاشة (تُحمّل بكسل عند الحاجة لتسريع الإقلاع)
try:
    import numpy as np
    from mss import mss
    from PIL import Image
    _VISION_LIBS = True
except Exception:
    _VISION_LIBS = False

# ─────────────────────────────────────────────────────────────
GITHUB_USER    = "Tetn5"          # ← اسم حسابك في GitHub
GITHUB_REPO    = "fishbot-gta"    # ← اسم الـ Repository
GITHUB_BRANCH  = "main"           # ← اسم الـ Branch
CURRENT_VERSION = "2.0"

_RAW = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/{GITHUB_BRANCH}"
VERSION_URL = f"{_RAW}/version.txt"
SCRIPT_URL  = f"{_RAW}/fishing_bot.py"

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
    "bait_limit":      0,
    "hotkey":          "f6",

    # ── إعدادات الرؤية (OCR) ──────────────────────────────
    "vision_enabled":  False,   # تفعيل قراءة الشاشة
    # مناطق الشاشة: [left, top, width, height] بالبكسل
    # تُعلّم بالماوس عبر زر "تحديد المنطقة" — لا حاجة لكتابتها يدوياً
    "region_fish":     None,    # منطقة عدّاد الأسماك في الحقيبة
    "region_capacity": None,    # منطقة مساحة الحقيبة (مثل 45/50)
    "region_bait":     None,    # منطقة عدد الطعم المتبقي
    "ocr_interval":    1,       # كل كم دورة نقرأ الشاشة (1 = كل دورة)
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
#   نظام الأصوات (Sound System)
# ══════════════════════════════════════════════════════════════
class Sound:
    @staticmethod
    def _beep_async(seq):
        """seq = قائمة (تردد, مدة, صمت بعدها)"""
        def _run():
            for freq, dur, gap in seq:
                try:
                    winsound.Beep(freq, dur)
                except Exception:
                    pass
                if gap:
                    time.sleep(gap)
        threading.Thread(target=_run, daemon=True).start()

    @staticmethod
    def play_start():
        """نغمة صاعدة قصيرة عند بدء البوت"""
        Sound._beep_async([(900, 120, 0.04), (1200, 160, 0)])

    @staticmethod
    def play_catch():
        """نغمة خفيفة عند اصطياد سمكة (اختياري لكل دورة)"""
        Sound._beep_async([(1000, 90, 0)])

    @staticmethod
    def play_finished():
        """🔊 النغمة الرئيسية: تطلع عند انتهاء عمل البوت فعلاً
        (انتهاء الدورات / امتلاء الحقيبة / نفاد الطعم / إيقاف يدوي)"""
        Sound._beep_async([
            (700, 180, 0.05),
            (900, 180, 0.05),
            (1100, 320, 0),
        ])

    @staticmethod
    def play_warning():
        """صوت تحذيري منخفض للأخطاء"""
        Sound._beep_async([(400, 700, 0)])


# ══════════════════════════════════════════════════════════════
#   نظام الرؤية (Vision / OCR عربي)
# ══════════════════════════════════════════════════════════════
class Vision:
    """قارئ شاشة كسول التحميل — يحمّل EasyOCR أول مرة فقط."""
    _reader = None
    _loading = False
    _load_error = None

    @classmethod
    def available(cls) -> bool:
        return _VISION_LIBS

    @classmethod
    def ensure_reader(cls, log_fn=None):
        """تحميل موديل EasyOCR مرة واحدة (عربي + إنجليزي للأرقام)."""
        if cls._reader is not None:
            return cls._reader
        if cls._load_error:
            return None
        try:
            if log_fn:
                log_fn("🧠 تحميل موديل قراءة النص العربي (أول مرة قد يطول)...", "yellow")
            import easyocr
            # العربية + الإنجليزية: الإنجليزية ضرورية لقراءة الأرقام واللاتيني
            cls._reader = easyocr.Reader(['ar', 'en'], gpu=False, verbose=False)
            if log_fn:
                log_fn("✅ تم تحميل موديل القراءة", "green")
        except Exception as e:
            cls._load_error = str(e)
            if log_fn:
                log_fn(f"❌ فشل تحميل OCR: {e}", "red")
            cls._reader = None
        return cls._reader

    @staticmethod
    def grab(region):
        """التقاط منطقة [left, top, width, height] وإرجاع مصفوفة numpy."""
        l, t, w, h = region
        with mss() as sct:
            shot = sct.grab({"left": l, "top": t, "width": w, "height": h})
        img = np.array(shot)[:, :, :3]  # BGRA → BGR
        return img

    @classmethod
    def read_region(cls, region, log_fn=None) -> str:
        """قراءة النص الخام من منطقة شاشة. يرجّع نص (قد يحتوي عربي وأرقام)."""
        reader = cls.ensure_reader(log_fn)
        if reader is None or not region:
            return ""
        try:
            img = cls.grab(region)
            # تكبير الصورة 2x يحسّن دقة OCR للنصوص الصغيرة في الواجهة
            pil = Image.fromarray(img[:, :, ::-1])  # BGR → RGB
            pil = pil.resize((pil.width * 2, pil.height * 2), Image.LANCZOS)
            arr = np.array(pil)
            results = reader.readtext(arr, detail=0, paragraph=True)
            return " ".join(results).strip()
        except Exception as e:
            if log_fn:
                log_fn(f"⚠️ خطأ قراءة المنطقة: {e}", "yellow")
            return ""

    @staticmethod
    def extract_numbers(text):
        """استخراج كل الأرقام من نص (يحوّل الأرقام العربية ٠١٢ إلى لاتينية)."""
        if not text:
            return []
        # تحويل الأرقام العربية الهندية إلى لاتينية
        arabic_digits = "٠١٢٣٤٥٦٧٨٩"
        trans = {ord(a): str(i) for i, a in enumerate(arabic_digits)}
        text = text.translate(trans)
        return [int(n) for n in re.findall(r"\d+", text)]

    @classmethod
    def read_count(cls, region, log_fn=None):
        """يرجّع أول رقم في المنطقة، أو None إن لم يُقرأ شيء."""
        nums = cls.extract_numbers(cls.read_region(region, log_fn))
        return nums[0] if nums else None

    @classmethod
    def read_fraction(cls, region, log_fn=None):
        """يقرأ صيغة مثل '45/50' ويرجّع (current, max)، أو (None, None)."""
        nums = cls.extract_numbers(cls.read_region(region, log_fn))
        if len(nums) >= 2:
            return nums[0], nums[1]
        if len(nums) == 1:
            return nums[0], None
        return None, None


# ══════════════════════════════════════════════════════════════
#   حفظ وتحميل الإعدادات
# ══════════════════════════════════════════════════════════════
def load_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
            cfg.update({k: saved[k] for k in DEFAULT_CONFIG if k in saved})
    except Exception:
        pass
    return cfg

def save_config(cfg: dict):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════
#   التحديث التلقائي
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
                log_fn(f"❌ فشل التحميل: {r.status_code}", "red")
                return
            script_path = os.path.abspath(__file__)
            backup_path = script_path + ".backup"
            with open(backup_path, "wb") as f:
                f.write(open(script_path, "rb").read())
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(r.text)
            log_fn("✅ تم التحديث! إعادة التشغيل...", "green")
            time.sleep(1.5)
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
        self.fish_caught = 0     # عدد الأسماك المصطادة (من OCR)
        self.bait_left  = None   # آخر قراءة للطعم
        self.bag_cur    = None   # سعة الحقيبة الحالية
        self.bag_max    = None   # سعة الحقيبة القصوى
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
        self.stop_reason  = "إيقاف يدوي"   # سبب التوقف لمنطق الصوت
        self.stats        = Stats()
        self.inp          = GameInput()
        self._thread      = None

    def start(self):
        if self._thread and self._thread.is_alive(): return
        self.running = True
        self.paused  = False
        self.stop_reason = "إيقاف يدوي"
        self.stats.reset()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self.stop_reason = "إيقاف يدوي"
        self.running = False
        self.paused  = False

    def toggle_pause(self):
        self.paused = not self.paused

    # ── خطوات اللعب ─────────────────────────────────────────
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

    # ── الرؤية: فحص الحقيبة/الطعم/السمك ──────────────────────
    def _vision_scan(self):
        """يقرأ الشاشة ويحدّث الإحصائيات. يرجّع سبب توقف أو None."""
        if not self.cfg.get("vision_enabled"):
            return None
        if not Vision.available():
            return None

        # الطعم
        rb = self.cfg.get("region_bait")
        if rb:
            n = Vision.read_count(rb, self.log)
            if n is not None:
                self.stats.bait_left = n
                self.log(f"👁️ الطعم المتبقي: {n}", "cyan")
                if n <= 0:
                    return "نفاد الطعم"

        # سعة الحقيبة (current/max)
        rc = self.cfg.get("region_capacity")
        if rc:
            cur, mx = Vision.read_fraction(rc, self.log)
            if cur is not None:
                self.stats.bag_cur, self.stats.bag_max = cur, mx
                if mx:
                    self.log(f"👁️ الحقيبة: {cur}/{mx}", "cyan")
                    if cur >= mx:
                        return "امتلاء الحقيبة"

        # عدّاد الأسماك
        rf = self.cfg.get("region_fish")
        if rf:
            n = Vision.read_count(rf, self.log)
            if n is not None:
                self.stats.fish_caught = n
                self.log(f"👁️ الأسماك: {n}", "cyan")

        self.update_stats()
        return None

    # ── الحلقة الرئيسية ──────────────────────────────────────
    def _loop(self):
        self.log("🚀 البوت يعمل!", "green")
        self.set_status("🟢 يعمل")
        Sound.play_start()

        # تحميل موديل OCR مبكراً إن كانت الرؤية مفعّلة
        if self.cfg.get("vision_enabled") and Vision.available():
            Vision.ensure_reader(self.log)

        try:
            scan_counter = 0
            while self.running:
                while self.paused and self.running:
                    self.set_status("⏸️  إيقاف مؤقت")
                    time.sleep(0.2)
                if not self.running: break

                # 🛑 حد الطعم اليدوي (احتياطي إذا OCR غير مفعّل)
                limit = self.cfg.get("bait_limit", 0)
                if limit > 0 and self.stats.bait_used >= limit:
                    self.stop_reason = f"الوصول لحد الطعم ({limit})"
                    self.log(f"🛑 {self.stop_reason}!", "red")
                    break

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

                # 👁️ فحص بصري بعد كل دورة (أو كل N دورات)
                scan_counter += 1
                interval = max(1, int(self.cfg.get("ocr_interval", 1)))
                if scan_counter % interval == 0:
                    reason = self._vision_scan()
                    if reason:
                        self.stop_reason = reason
                        self.log(f"🛑 توقف ذكي: {reason}", "red")
                        break

                max_c = self.cfg.get("cycles", 0)
                if max_c > 0 and self.stats.cycles >= max_c:
                    self.stop_reason = f"اكتمال {self.stats.cycles} دورة"
                    self.log(f"✅ {self.stop_reason}!", "green")
                    break

                time.sleep(0.3)

        except Exception as e:
            self.stop_reason = f"خطأ: {e}"
            self.log(f"❌ خطأ أو تم إغلاق اللعبة: {e}", "red")
            Sound.play_warning()

        self.running = False
        self.set_status("⚫ متوقف")

        # 🔊 منطق الصوت الصحيح: صوت "الانتهاء" يطلع لأن البوت خلص عمله فعلاً
        # (سواء أكمل الدورات، امتلأت الحقيبة، نفد الطعم، أو أوقفته أنت)
        if not self.stop_reason.startswith("خطأ"):
            Sound.play_finished()

        elapsed = int(time.time() - self.stats.start_time)
        mm, ss = divmod(elapsed, 60)
        hh, mm = divmod(mm, 60)
        fish_txt = f" | أسماك: {self.stats.fish_caught}" if self.stats.fish_caught else ""
        self.log(
            f"⛔ انتهى ({self.stop_reason}) | دورات: {self.stats.cycles} | "
            f"طعم مستخدم: {self.stats.bait_used}{fish_txt} | "
            f"وقت: {hh:02d}:{mm:02d}:{ss:02d}",
            "yellow"
        )


# ══════════════════════════════════════════════════════════════
#   نافذة تحديد منطقة الشاشة (Region Selector)
# ══════════════════════════════════════════════════════════════
class RegionSelector(tk.Toplevel):
    """نافذة شفافة ملء الشاشة — تسحب بالماوس لتحديد مستطيل القراءة."""
    def __init__(self, master, on_select):
        super().__init__(master)
        self.on_select = on_select
        self.attributes("-fullscreen", True)
        self.attributes("-alpha", 0.30)
        self.configure(bg="black", cursor="cross")
        self.canvas = tk.Canvas(self, bg="black", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.start = None
        self.rect = None
        self.canvas.bind("<ButtonPress-1>", self._down)
        self.canvas.bind("<B1-Motion>", self._move)
        self.canvas.bind("<ButtonRelease-1>", self._up)
        self.bind("<Escape>", lambda e: self.destroy())
        self.canvas.create_text(
            self.winfo_screenwidth() // 2, 40,
            text="اسحب لتحديد المنطقة • Esc للإلغاء",
            fill="white", font=("Segoe UI", 16, "bold"))

    def _down(self, e):
        self.start = (e.x_root, e.y_root)
        self.rect = self.canvas.create_rectangle(e.x, e.y, e.x, e.y,
                                                  outline="#58a6ff", width=2)
        self._ox, self._oy = e.x, e.y

    def _move(self, e):
        if self.rect:
            self.canvas.coords(self.rect, self._ox, self._oy, e.x, e.y)

    def _up(self, e):
        if not self.start:
            self.destroy(); return
        x1, y1 = self.start
        x2, y2 = e.x_root, e.y_root
        left, top = int(min(x1, x2)), int(min(y1, y2))
        w, h = int(abs(x2 - x1)), int(abs(y2 - y1))
        self.destroy()
        if w > 4 and h > 4:
            self.on_select([left, top, w, h])


# ══════════════════════════════════════════════════════════════
#   الواجهة
# ══════════════════════════════════════════════════════════════
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"🎣 Fish Bot v{CURRENT_VERSION}  |  GTA RP")
        self.geometry("960x720")
        self.resizable(False, False)
        self.configure(bg=BG)

        self.cfg        = load_config()
        self.bot        = None
        self._countdown = 0

        self._build_ui()
        self._setup_hotkey()
        self._refresh_region_labels()

        threading.Thread(target=self._check_update_bg, daemon=True).start()

    def _build_ui(self):
        hdr = tk.Frame(self, bg=BG2, height=48)
        hdr.pack(fill="x")
        tk.Label(hdr, text=f"🎣  Fish Bot v{CURRENT_VERSION}  |  GTA RP",
                 bg=BG2, fg=ACCENT, font=("Segoe UI", 14, "bold")
                 ).pack(side="left", padx=16, pady=10)
        self.lbl_status = tk.Label(hdr, text="⚫ متوقف",
                                    bg=BG2, fg=TEXT2, font=("Segoe UI", 11))
        self.lbl_status.pack(side="right", padx=16)

        self.btn_update = tk.Button(
            hdr, text="🔄 تحديث متاح!", bg=YELLOW, fg="black", relief="flat",
            cursor="hand2", font=("Segoe UI", 9, "bold"), command=self._do_update)

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=12, pady=8)

        left  = tk.Frame(body, bg=BG)
        left.pack(side="left", fill="both", expand=True)
        right = tk.Frame(body, bg=BG, width=340)
        right.pack(side="right", fill="y", padx=(10, 0))
        right.pack_propagate(False)

        self._build_stats(left)
        self._build_log(left)
        self._build_settings(right)
        self._build_vision(right)
        self._build_controls(right)

    def _build_stats(self, p):
        f = tk.Frame(p, bg=BG2, highlightthickness=1, highlightbackground=BORDER)
        f.pack(fill="x", pady=(0, 8))
        tk.Label(f, text="📊  إحصائيات الجلسة", bg=BG2, fg=ACCENT,
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=10, pady=(6, 2))
        row = tk.Frame(f, bg=BG2)
        row.pack(fill="x", padx=10, pady=(0, 8))

        def box(label, attr, color):
            b = tk.Frame(row, bg=BG3, padx=8, pady=6,
                         highlightthickness=1, highlightbackground=BORDER)
            b.pack(side="left", expand=True, fill="x", padx=3)
            tk.Label(b, text=label, bg=BG3, fg=TEXT2, font=("Segoe UI", 8)).pack()
            lbl = tk.Label(b, text="0", bg=BG3, fg=color, font=("Segoe UI", 15, "bold"))
            lbl.pack()
            setattr(self, attr, lbl)

        box("🔄 الدورات",     "lbl_cycles",  PURPLE)
        box("🐟 أسماك",       "lbl_fish",    GREEN)
        box("🪱 طعم متبقي",   "lbl_bait",    YELLOW)
        box("🎒 الحقيبة",     "lbl_bag",     ACCENT)
        box("⏱️ الوقت",      "lbl_session", TEXT2)

    def _build_log(self, p):
        f = tk.Frame(p, bg=BG3, highlightthickness=1, highlightbackground=BORDER)
        f.pack(fill="both", expand=True)
        tk.Label(f, text="📋  السجل", bg=BG3, fg=TEXT2,
                 font=("Segoe UI", 9)).pack(anchor="w", padx=8, pady=3)
        self.log_box = scrolledtext.ScrolledText(
            f, bg=BG, fg=TEXT, font=("Consolas", 9),
            insertbackground=TEXT, bd=0, relief="flat", state="disabled", height=14)
        self.log_box.pack(fill="both", expand=True, padx=4, pady=(0, 4))
        for tag, clr in [
            ("green", GREEN), ("red", RED), ("yellow", YELLOW),
            ("cyan",  ACCENT),("accent", PURPLE), ("white", TEXT),
        ]:
            self.log_box.tag_config(tag, foreground=clr)

    def _build_settings(self, p):
        f = tk.LabelFrame(p, text=" ⚙️ الإعدادات ", bg=BG2, fg=ACCENT,
                          font=("Segoe UI", 9, "bold"), bd=1, relief="solid",
                          labelanchor="n")
        f.pack(fill="x", pady=(0, 8))

        fields = [
            ("طعم سمك  (↓ مرات)",   "bait_row",        "int"),
            ("سنارة صيد (↓ مرات)",  "rod_row",         "int"),
            ("تأخير المفاتيح (s)",  "delay_key",       "float"),
            ("فتح الحقيبة (s)",     "delay_open_bag",  "float"),
            ("إغلاق الحقيبة (s)",   "delay_close_bag", "float"),
            ("انتظار Enter (s)",     "delay_use",       "float"),
            ("⏱ وقت الصيد (s)",    "delay_fishing",   "float"),
            ("الدورات  (0=∞)",      "cycles",          "int"),
            ("🪱 حد الطعم (0=∞)",   "bait_limit",      "int"),
            ("⌨️ اختصار التشغيل",   "hotkey",          "str"),
        ]
        self._vars = {}
        for label, key, typ in fields:
            row = tk.Frame(f, bg=BG2)
            row.pack(fill="x", padx=8, pady=1)
            tk.Label(row, text=label, bg=BG2, fg=TEXT2, font=("Segoe UI", 8),
                     width=16, anchor="w").pack(side="left")
            var = tk.StringVar(value=str(self.cfg.get(key, "")))
            self._vars[key] = (var, typ)
            tk.Entry(row, textvariable=var, bg=BG3, fg=TEXT, insertbackground=TEXT,
                     relief="flat", font=("Segoe UI", 9), width=7).pack(side="right")

        tk.Button(f, text="💾  حفظ وتفعيل", bg=BG3, fg=ACCENT, relief="flat",
                  cursor="hand2", font=("Segoe UI", 9),
                  command=self._apply_settings).pack(fill="x", padx=8, pady=6)

    def _build_vision(self, p):
        f = tk.LabelFrame(p, text=" 👁️ النظام الذكي (قراءة الشاشة) ", bg=BG2,
                          fg=GREEN, font=("Segoe UI", 9, "bold"), bd=1,
                          relief="solid", labelanchor="n")
        f.pack(fill="x", pady=(0, 8))

        # مفتاح التفعيل
        self.var_vision = tk.BooleanVar(value=bool(self.cfg.get("vision_enabled")))
        tk.Checkbutton(f, text="تفعيل القراءة الذكية للشاشة",
                       variable=self.var_vision, bg=BG2, fg=TEXT,
                       selectcolor=BG3, activebackground=BG2, activeforeground=TEXT,
                       font=("Segoe UI", 9), command=self._toggle_vision
                       ).pack(anchor="w", padx=8, pady=(4, 2))

        if not Vision.available():
            tk.Label(f, text="⚠️ مكتبات الرؤية غير مثبّتة:\npip install easyocr pillow mss numpy",
                     bg=BG2, fg=RED, font=("Segoe UI", 8), justify="right"
                     ).pack(anchor="w", padx=8, pady=2)

        # أزرار تحديد المناطق
        self._region_labels = {}
        for key, title in [
            ("region_bait",     "🪱 منطقة عدّاد الطعم"),
            ("region_capacity", "🎒 منطقة سعة الحقيبة (45/50)"),
            ("region_fish",     "🐟 منطقة عدّاد الأسماك"),
        ]:
            row = tk.Frame(f, bg=BG2)
            row.pack(fill="x", padx=8, pady=2)
            tk.Button(row, text="🎯 تحديد", bg=BG3, fg=ACCENT, relief="flat",
                      cursor="hand2", font=("Segoe UI", 8), width=8,
                      command=lambda k=key: self._select_region(k)
                      ).pack(side="left")
            lbl = tk.Label(row, text=title, bg=BG2, fg=TEXT2,
                           font=("Segoe UI", 8), anchor="e", justify="right")
            lbl.pack(side="right", fill="x", expand=True)
            self._region_labels[key] = (lbl, title)

        # زر اختبار القراءة
        tk.Button(f, text="🔍 اختبار القراءة الآن", bg=BG3, fg=GREEN, relief="flat",
                  cursor="hand2", font=("Segoe UI", 9),
                  command=self._test_vision).pack(fill="x", padx=8, pady=(4, 6))

    def _build_controls(self, p):
        f = tk.LabelFrame(p, text=" 🎮 التحكم ", bg=BG2, fg=ACCENT,
                          font=("Segoe UI", 9, "bold"), bd=1, relief="solid",
                          labelanchor="n")
        f.pack(fill="x")

        self.lbl_countdown = tk.Label(f, text="", bg=BG2, fg=YELLOW,
                                      font=("Segoe UI", 20, "bold"))
        self.lbl_countdown.pack(pady=4)

        self.btn_start = tk.Button(f, text="▶  تشغيل", bg=GREEN, fg="black",
                                   activebackground="#2ea043",
                                   font=("Segoe UI", 12, "bold"), relief="flat",
                                   cursor="hand2", height=2, command=self._on_start)
        self.btn_start.pack(fill="x", padx=8, pady=4)

        self.btn_pause = tk.Button(f, text="⏸  إيقاف مؤقت", bg=YELLOW, fg="black",
                                   font=("Segoe UI", 10), relief="flat",
                                   cursor="hand2", state="disabled",
                                   command=self._on_pause)
        self.btn_pause.pack(fill="x", padx=8, pady=2)

        self.btn_stop = tk.Button(f, text="⛔  إيقاف", bg=RED, fg="white",
                                  font=("Segoe UI", 10), relief="flat",
                                  cursor="hand2", state="disabled",
                                  command=self._on_stop)
        self.btn_stop.pack(fill="x", padx=8, pady=(2, 8))

    # ── الرؤية: تحديد/اختبار المناطق ─────────────────────────
    def _toggle_vision(self):
        self.cfg["vision_enabled"] = self.var_vision.get()
        save_config(self.cfg)
        state = "مفعّلة" if self.cfg["vision_enabled"] else "متوقفة"
        self._log(f"👁️ القراءة الذكية: {state}", "cyan")

    def _select_region(self, key):
        self._log("🎯 اسحب بالماوس لتحديد المنطقة على شاشة اللعبة...", "yellow")
        def done(region):
            self.cfg[key] = region
            save_config(self.cfg)
            self._refresh_region_labels()
            self._log(f"✅ تم حفظ المنطقة {key}: {region}", "green")
        RegionSelector(self, done)

    def _refresh_region_labels(self):
        if not hasattr(self, "_region_labels"):
            return
        for key, (lbl, title) in self._region_labels.items():
            reg = self.cfg.get(key)
            if reg:
                lbl.config(text=f"{title}  ✓", fg=GREEN)
            else:
                lbl.config(text=f"{title}  (غير محددة)", fg=TEXT2)

    def _test_vision(self):
        if not Vision.available():
            self._log("⚠️ مكتبات الرؤية غير مثبتة", "red")
            return
        def run():
            self._log("🔍 جاري اختبار القراءة...", "yellow")
            Vision.ensure_reader(self._log)
            for key, name in [("region_bait", "الطعم"),
                              ("region_capacity", "الحقيبة"),
                              ("region_fish", "الأسماك")]:
                reg = self.cfg.get(key)
                if not reg:
                    continue
                raw = Vision.read_region(reg, self._log)
                nums = Vision.extract_numbers(raw)
                self._log(f"🔍 {name}: نص='{raw}' أرقام={nums}", "cyan")
            self._log("✅ انتهى الاختبار", "green")
        threading.Thread(target=run, daemon=True).start()

    # ── الاختصارات ───────────────────────────────────────────
    def _setup_hotkey(self):
        try:
            keyboard.unhook_all()
        except Exception:
            pass
        hk = self.cfg.get("hotkey", "f6").lower()
        if not hk: return
        try:
            keyboard.add_hotkey(hk, self._handle_hotkey)
            self._log(f"⌨️ تم تفعيل الاختصار: [{hk.upper()}] للتشغيل/الإيقاف", "cyan")
        except Exception as e:
            self._log(f"❌ فشل تفعيل الاختصار: {e}", "red")

    def _handle_hotkey(self):
        if not self.bot or not self.bot.running:
            if self.btn_start['state'] == 'normal':
                self.after(0, self._on_start)
        else:
            self.after(0, self._on_pause)

    # ── أحداث ────────────────────────────────────────────────
    def _check_update_bg(self):
        has_update, latest = Updater.check()
        if has_update:
            def show():
                self.btn_update.config(text=f"🔄 تحديث v{latest} متاح — اضغط للتحديث")
                self.btn_update.pack(side="right", padx=8, pady=8)
                self._log(f"🔄 يوجد تحديث جديد v{latest}! اضغط الزر في الأعلى.", "yellow")
            self.after(0, show)

    def _do_update(self):
        if not messagebox.askyesno("تحديث",
            "سيتم تحديث البرنامج وإعادة تشغيله.\nالإعدادات ستُحفظ تلقائياً.\nتكمل؟"):
            return
        self._apply_settings()
        threading.Thread(target=Updater.download_and_restart,
                         args=(self._log,), daemon=True).start()

    def _apply_settings(self):
        for key, (var, typ) in self._vars.items():
            try:
                if typ == "int": self.cfg[key] = int(var.get())
                elif typ == "float": self.cfg[key] = float(var.get())
                else: self.cfg[key] = str(var.get())
            except ValueError:
                pass
        self.cfg["vision_enabled"] = self.var_vision.get()
        save_config(self.cfg)
        self._setup_hotkey()
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
        self.bot = FishingBot(cfg=self.cfg, log_fn=self._log,
                              status_fn=self._set_status, stats_fn=self._refresh_stats)
        self.bot.start()
        self.btn_start.config(state="disabled")
        self.btn_pause.config(state="normal")
        self.btn_stop.config(state="normal")
        self._poll()

    def _on_pause(self):
        if not self.bot: return
        self.bot.toggle_pause()
        self.btn_pause.config(text="▶  استئناف" if self.bot.paused else "⏸  إيقاف مؤقت")
        if self.bot.paused:
            self._log("⏸️ تم الإيقاف المؤقت", "yellow")
        else:
            self._log("▶️ تم الاستئناف", "green")

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
            self.lbl_fish.config(text=str(s.fish_caught))
            self.lbl_bait.config(text="-" if s.bait_left is None else str(s.bait_left))
            if s.bag_cur is not None and s.bag_max:
                self.lbl_bag.config(text=f"{s.bag_cur}/{s.bag_max}")
            elif s.bag_cur is not None:
                self.lbl_bag.config(text=str(s.bag_cur))
            else:
                self.lbl_bag.config(text="-")
            el = int(time.time() - s.start_time)
            mm, ss = divmod(el, 60)
            hh, mm = divmod(mm, 60)
            self.lbl_session.config(text=f"{hh:02d}:{mm:02d}:{ss:02d}")
        self.after(0, upd)

    def _log(self, msg: str, color: str = "white"):
        def _do():
            self.log_box.config(state="normal")
            self.log_box.insert("end", f"[{time.strftime('%H:%M:%S')}] {msg}\n", color)
            self.log_box.see("end")
            self.log_box.config(state="disabled")
        self.after(0, _do)

    def _set_status(self, text: str):
        self.after(0, lambda: self.lbl_status.config(text=text))


# ══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    missing = []
    for pkg in ["pydirectinput", "keyboard", "requests"]:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        print(f"❌ مكتبات أساسية مفقودة: {', '.join(missing)}")
        print("ثبّت: pip install pydirectinput keyboard requests")
        sys.exit(1)

    if not _VISION_LIBS:
        print("⚠️ مكتبات القراءة الذكية غير مثبتة (النظام سيعمل بدون OCR).")
        print("للقراءة الذكية: pip install easyocr pillow mss numpy")

    App().mainloop()
