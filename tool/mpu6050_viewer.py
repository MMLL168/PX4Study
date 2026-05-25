#!/usr/bin/env python3
"""
PX4 Flight Monitor  (tkinter + Pillow)
Tab 1: MPU6050 Debug  — direct NSH console serial
Tab 2: MAVLink Monitor — SiK radio ground unit
Windows: pip install pyserial Pillow pymavlink
"""

import re, math, threading, queue, time

_ANSI_RE = re.compile(r'\x1b\[[0-9;]*[A-Za-z]|\x1b[^[]')

import tkinter as tk
from tkinter import ttk

import serial
import serial.tools.list_ports

try:
    from PIL import Image, ImageDraw, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    from pymavlink import mavutil as mav_util
    HAS_MAV = True
except ImportError:
    HAS_MAV = False
    mav_util = None

# ── 色彩主題 ────────────────────────────────────────────────────────────────────
BG      = "#080816"
PANEL   = "#0e0e22"
BORDER  = "#1a1a38"
CYAN    = "#00c8ff"
GREEN   = "#00e080"
RED     = "#ff3355"
AMBER   = "#ffaa00"
TEXT    = "#c0c8e0"
DIM     = "#5060a0"
GOLD    = "#ffd700"
LOG_BG  = "#060614"
LOG_FG  = "#88ffaa"
MAV_FG  = "#88ddff"

# ── PX4 飛行模式解碼 ────────────────────────────────────────────────────────────
_PX4_MAIN = {
    1: "MANUAL", 2: "ALTCTL", 3: "POSCTL", 4: "AUTO",
    5: "ACRO",   6: "OFFBOARD", 7: "STABILIZED", 8: "RATTITUDE",
}
_PX4_AUTO_SUB = {
    1: "READY", 2: "TAKEOFF", 3: "LOITER", 4: "MISSION",
    5: "RTL",   6: "LAND",    9: "PRECLAND",
}

def _decode_px4_mode(custom_mode):
    main = (custom_mode >> 16) & 0xFF
    sub  = (custom_mode >> 24) & 0xFF
    name = _PX4_MAIN.get(main, f"#{main}")
    if main == 4 and sub:
        name = _PX4_AUTO_SUB.get(sub, f"AUTO/{sub}")
    return name


# ── 人工地平線 (PIL 渲染) ────────────────────────────────────────────────────────

def render_horizon(w, h, roll_deg, pitch_deg):
    if not HAS_PIL or w < 20 or h < 20:
        return None
    cx, cy = w // 2, h // 2
    r = min(w, h) // 2 - 4
    rr = math.radians(roll_deg)
    pp = pitch_deg * r / 45.0
    hx = cx - pp * math.sin(rr)
    hy = cy + pp * math.cos(rr)
    hdx, hdy = math.cos(rr), -math.sin(rr)
    gdx, gdy = math.sin(rr),  math.cos(rr)
    ext = max(w, h) * 3

    img = Image.new("RGB", (w, h), (26, 107, 154))
    d = ImageDraw.Draw(img)
    d.polygon([
        (hx + hdx*ext + gdx*ext, hy + hdy*ext + gdy*ext),
        (hx - hdx*ext + gdx*ext, hy - hdy*ext + gdy*ext),
        (hx - hdx*ext,           hy - hdy*ext),
        (hx + hdx*ext,           hy + hdy*ext),
    ], fill=(100, 58, 18))

    for deg in [-30, -20, -10, 10, 20, 30]:
        off = deg * r / 45.0
        lhx = hx - off * math.sin(rr)
        lhy = hy + off * math.cos(rr)
        if math.hypot(lhx - cx, lhy - cy) > r * 0.88:
            continue
        ll = r * 0.40 if abs(deg) % 20 == 0 else r * 0.24
        d.line([(lhx + hdx*ll, lhy + hdy*ll), (lhx - hdx*ll, lhy - hdy*ll)],
               fill=(220, 220, 220), width=1)
        d.text((int(lhx + hdx*ll*1.18 + gdx*3),
                int(lhy + hdy*ll*1.18 + gdy*3 - 6)),
               str(abs(deg)), fill=(190, 190, 190))

    d.line([(hx + hdx*r*.91, hy + hdy*r*.91),
            (hx - hdx*r*.91, hy - hdy*r*.91)], fill=(255,255,255), width=2)

    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).ellipse([(cx-r, cy-r), (cx+r, cy+r)], fill=255)
    out = Image.new("RGB", (w, h), (8, 8, 22))
    out.paste(img, mask=mask)
    d2 = ImageDraw.Draw(out)

    for ang in range(-60, 61, 10):
        if ang == 0:
            continue
        ar = math.radians(ang - 90)
        tl = 10 if ang % 30 == 0 else 5
        d2.line([(cx + (r-2)*math.cos(ar),   cy + (r-2)*math.sin(ar)),
                 (cx + (r-2-tl)*math.cos(ar), cy + (r-2-tl)*math.sin(ar))],
                fill=(170, 170, 170), width=1)
    d2.line([(cx, cy-r+2), (cx, cy-r+14)], fill=(255,215,0), width=2)

    rp = math.radians(roll_deg - 90)
    prx = cx + (r-14)*math.cos(rp)
    pry = cy + (r-14)*math.sin(rp)
    pe  = rp + math.pi/2
    d2.polygon([(cx+(r-2)*math.cos(rp), cy+(r-2)*math.sin(rp)),
                (prx+6*math.cos(pe), pry+6*math.sin(pe)),
                (prx-6*math.cos(pe), pry-6*math.sin(pe))], fill=(255,215,0))

    sw = int(r * 0.32); sh = 8; lc = (255, 215, 0)
    d2.line([(cx-sw, cy),          (cx-int(sw*.40), cy)], fill=lc, width=3)
    d2.line([(cx+int(sw*.40), cy), (cx+sw, cy)],          fill=lc, width=3)
    d2.line([(cx-sw, cy), (cx-sw, cy+sh)],                fill=lc, width=3)
    d2.line([(cx+sw, cy), (cx+sw, cy+sh)],                fill=lc, width=3)
    d2.ellipse([(cx-4, cy-4), (cx+4, cy+4)], fill=lc)
    d2.ellipse([(cx-r, cy-r), (cx+r, cy+r)], outline=(0, 200, 100), width=2)
    return out


def draw_horizon_fallback(canvas, roll_deg, pitch_deg):
    canvas.delete("all")
    w, h = canvas.winfo_width(), canvas.winfo_height()
    if w < 20 or h < 20:
        return
    cx, cy = w//2, h//2
    r = min(w, h)//2 - 4
    canvas.create_oval(cx-r, cy-r, cx+r, cy+r, fill="#1a6b9a", outline="#00c864", width=2)
    rr = math.radians(roll_deg)
    pp = pitch_deg * r / 45.0
    hx = cx - pp*math.sin(rr)
    hy = cy + pp*math.cos(rr)
    hdx, hdy = math.cos(rr), -math.sin(rr)
    hl = r * 0.88
    canvas.create_line(hx+hdx*hl, hy+hdy*hl, hx-hdx*hl, hy-hdy*hl, fill="white", width=2)
    sw = int(r * 0.30)
    canvas.create_line(cx-sw, cy, cx-int(sw*.4), cy, fill=GOLD, width=3)
    canvas.create_line(cx+int(sw*.4), cy, cx+sw, cy, fill=GOLD, width=3)
    canvas.create_oval(cx-4, cy-4, cx+4, cy+4, fill=GOLD, outline=GOLD)


# ── 資料解析器 (NSH serial) ────────────────────────────────────────────────────

ACCEL_RE = re.compile(
    r'sensor_accel.*?x:([-+]?\d+\.?\d*).*?y:([-+]?\d+\.?\d*).*?z:([-+]?\d+\.?\d*)', re.I)
GYRO_RE  = re.compile(
    r'sensor_gyro.*?x:([-+]?\d+\.?\d*).*?y:([-+]?\d+\.?\d*).*?z:([-+]?\d+\.?\d*)', re.I)


class Parser:
    def __init__(self, cb):
        self._cb = cb
        self._gx = self._gy = self._gz = 0.0
        self._blk = None
        self._bx = self._by = self._bz = 0.0

    def feed(self, line):
        line = line.strip()
        m = ACCEL_RE.search(line)
        if m:
            ax, ay, az = float(m[1]), float(m[2]), float(m[3])
            roll  = math.degrees(math.atan2(ay, az))
            pitch = math.degrees(math.atan2(-ax, math.sqrt(ay*ay + az*az)))
            self._cb(roll, pitch, ax, ay, az, self._gx, self._gy, self._gz)
            return
        m = GYRO_RE.search(line)
        if m:
            self._gx, self._gy, self._gz = float(m[1]), float(m[2]), float(m[3])
            return
        ll = line.lower()
        if 'sensor_accel' in ll:
            self._blk = 'a'; self._bx = self._by = self._bz = 0.0; return
        if 'sensor_gyro'  in ll:
            self._blk = 'g'; self._bx = self._by = self._bz = 0.0; return
        m2 = re.match(r'([xyz]):\s*([-+]?\d+\.?\d*)', line)
        if m2 and self._blk:
            v = float(m2[2])
            if   m2[1] == 'x': self._bx = v
            elif m2[1] == 'y': self._by = v
            elif m2[1] == 'z':
                self._bz = v
                if self._blk == 'a':
                    roll  = math.degrees(math.atan2(self._by, self._bz))
                    pitch = math.degrees(math.atan2(-self._bx,
                            math.sqrt(self._by**2 + self._bz**2)))
                    self._cb(roll, pitch, self._bx, self._by, self._bz,
                             self._gx, self._gy, self._gz)
                elif self._blk == 'g':
                    self._gx, self._gy, self._gz = self._bx, self._by, self._bz
                self._blk = None


# ── 主程式 ─────────────────────────────────────────────────────────────────────

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("PX4 Flight Monitor")
        self.configure(bg=BG)
        self.geometry("1100x740")
        self.minsize(850, 580)

        # ── MPU6050 / NSH 狀態 ────────────────────────────────────────────────
        self._ser             = None
        self._running         = False
        self._q               = queue.Queue()
        self._roll            = 0.0
        self._pitch           = 0.0
        self._vals            = {k: 0.0 for k in ("ax","ay","az","gx","gy","gz")}
        self._parser          = Parser(self._on_att)
        self._tk_img          = None
        self._imu_on          = False
        self._led_on          = False
        self._blink           = False
        self._listener_up     = False
        self._last_listener_t = 0.0
        self._poll_topic      = 'accel'
        self._interval_var    = tk.StringVar(value="300")

        # ── MAVLink 狀態 ───────────────────────────────────────────────────────
        self._mav_conn        = None
        self._mav_running     = False
        self._mav_q           = queue.Queue()
        self._mav_roll        = 0.0
        self._mav_pitch       = 0.0
        self._mav_yaw         = 0.0
        self._mav_armed       = False
        self._mav_mode        = '---'
        self._mav_hb_count    = 0
        self._mav_msg_count   = 0
        self._mav_last_count  = 0
        self._mav_last_ts     = time.monotonic()
        self._mav_tk_img      = None
        self._mav_dvars       = {}
        self._mav_blink       = False

        self._build_ui()
        self._refresh_ports()
        self._poll()
        self._mav_poll()

    # ── UI 建構 ────────────────────────────────────────────────────────────────

    def _build_ui(self):
        style = ttk.Style()
        style.theme_use("default")
        style.configure("TNotebook",     background=BG,    borderwidth=0)
        style.configure("TNotebook.Tab", background=PANEL, foreground=DIM,
                        font=("Consolas", 12, "bold"), padding=[14, 6])
        style.map("TNotebook.Tab",
                  background=[("selected", BORDER)],
                  foreground=[("selected", CYAN)])

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True)

        self._tab1 = tk.Frame(nb, bg=BG)
        self._tab2 = tk.Frame(nb, bg=BG)
        nb.add(self._tab1, text="  MPU6050 Debug  ")
        nb.add(self._tab2, text="  MAVLink Monitor  ")

        self._build_conn_bar(self._tab1)
        self._build_main(self._tab1)
        self._build_ctrl_bar(self._tab1)
        self._build_log(self._tab1)
        self._build_mavlink_tab(self._tab2)

    def _build_conn_bar(self, parent):
        f = tk.Frame(parent, bg=PANEL, pady=7, padx=12)
        f.pack(fill="x")

        tk.Label(f, text="Port:", bg=PANEL, fg=DIM,
                 font=("Consolas", 11)).pack(side="left", padx=(0, 4))

        self._port_var = tk.StringVar()
        self._pcb = ttk.Combobox(f, textvariable=self._port_var,
                                  width=46, state="readonly", font=("Consolas", 11))
        self._pcb.pack(side="left", padx=2)

        self._baud_var = tk.StringVar(value="115200")
        ttk.Combobox(f, textvariable=self._baud_var, width=9, state="readonly",
                     values=["9600","19200","38400","57600",
                             "115200","230400","921600"],
                     font=("Consolas", 11)).pack(side="left", padx=2)

        tk.Button(f, text="⟳", width=3, bg=PANEL, fg=TEXT,
                  activebackground=BORDER, relief="flat", bd=0,
                  font=("Consolas", 14), cursor="hand2",
                  command=self._refresh_ports).pack(side="left", padx=2)

        self._cbtn = tk.Button(f, text="Connect", width=12,
                               bg="#003322", fg=GREEN,
                               activebackground="#005533", activeforeground=GREEN,
                               relief="flat", bd=0, font=("Consolas", 13, "bold"),
                               padx=8, pady=3, cursor="hand2",
                               command=self._toggle)
        self._cbtn.pack(side="left", padx=10)

        self._dot = tk.Canvas(f, width=10, height=10, bg=PANEL, highlightthickness=0)
        self._dot.create_oval(1, 1, 9, 9, fill="#440000", outline="#cc0000",
                              width=1, tags="d")
        self._dot.pack(side="left", padx=(0, 4))

        self._slbl = tk.Label(f, text="Disconnected", bg=PANEL, fg=RED,
                              font=("Consolas", 11))
        self._slbl.pack(side="left")

    def _build_main(self, parent):
        f = tk.Frame(parent, bg=BG)
        f.pack(fill="both", expand=True, padx=6, pady=(4, 0))
        f.columnconfigure(0, weight=5)
        f.columnconfigure(1, weight=3)
        f.rowconfigure(0, weight=1)

        self._hcanvas = tk.Canvas(f, bg=BG, highlightthickness=0)
        self._hcanvas.grid(row=0, column=0, sticky="nsew", padx=(0, 4), pady=2)
        self._hcanvas.bind("<Configure>", lambda _: self._redraw_horizon())

        rp = tk.Frame(f, bg=PANEL, padx=12, pady=10)
        rp.grid(row=0, column=1, sticky="nsew", pady=2)

        self._dvars = {}
        rows = [
            ("ATTITUDE",    None,    None),
            ("Roll",        "roll",  "°"),
            ("Pitch",       "pitch", "°"),
            ("",            None,    None),
            ("ACCEL m/s²",  None,    None),
            ("X",           "ax",    ""),
            ("Y",           "ay",    ""),
            ("Z",           "az",    ""),
            ("",            None,    None),
            ("GYRO rad/s",  None,    None),
            ("X",           "gx",    ""),
            ("Y",           "gy",    ""),
            ("Z",           "gz",    ""),
        ]
        for lbl, key, unit in rows:
            if key is None:
                if lbl == "":
                    tk.Frame(rp, bg=PANEL, height=4).pack()
                    continue
                tk.Label(rp, text=lbl, bg=PANEL, fg=CYAN,
                         font=("Consolas", 13, "bold")).pack(anchor="w", pady=(8, 1))
                continue
            row = tk.Frame(rp, bg=PANEL)
            row.pack(fill="x", pady=1)
            tk.Label(row, text=f"  {lbl}:", bg=PANEL, fg=DIM,
                     font=("Consolas", 11), width=7).pack(side="left")
            var = tk.StringVar(value="---")
            tk.Label(row, textvariable=var, bg=PANEL, fg=GOLD,
                     font=("Consolas", 19, "bold"), width=10).pack(side="left")
            if unit:
                tk.Label(row, text=unit, bg=PANEL, fg=DIM,
                         font=("Consolas", 11)).pack(side="left")
            self._dvars[key] = var

        tk.Label(rp, text="* Yaw 需磁力計，MPU6050 不支援",
                 bg=PANEL, fg=DIM, font=("Consolas", 14),
                 wraplength=180, justify="left").pack(anchor="w", pady=(6, 0))

    def _btn(self, parent, text, bg, fg, cmd, hover_bg=None, width=14):
        return tk.Button(parent, text=text,
                         bg=bg, fg=fg,
                         activebackground=hover_bg or bg,
                         activeforeground=fg,
                         relief="flat", bd=0,
                         font=("Consolas", 13, "bold"),
                         width=width, padx=4, pady=7,
                         cursor="hand2",
                         command=cmd)

    def _status_dot(self, parent, off_fill, off_outline):
        c = tk.Canvas(parent, width=12, height=12, bg=PANEL, highlightthickness=0)
        c.create_oval(1, 1, 11, 11, fill=off_fill, outline=off_outline,
                      width=1, tags="d")
        return c

    def _build_ctrl_bar(self, parent):
        f = tk.Frame(parent, bg=PANEL, pady=8, padx=12)
        f.pack(fill="x", padx=6, pady=4)

        imu = tk.Frame(f, bg=PANEL)
        imu.pack(side="left")

        hdr_imu = tk.Frame(imu, bg=PANEL)
        hdr_imu.pack(anchor="w", pady=(0, 4))
        self._imu_dot = self._status_dot(hdr_imu, "#003300", "#006600")
        self._imu_dot.pack(side="left", padx=(0, 5))
        tk.Label(hdr_imu, text="IMU CONTROL", bg=PANEL, fg=CYAN,
                 font=("Consolas", 11, "bold")).pack(side="left")

        btns_imu = tk.Frame(imu, bg=PANEL)
        btns_imu.pack()
        self._btn(btns_imu, "▶  START IMU",
                  "#003322", GREEN, self._start_imu, "#005533").pack(side="left", padx=(0, 3))
        self._btn(btns_imu, "■  STOP IMU",
                  "#330011", RED, self._stop_imu,  "#550022").pack(side="left")

        ivl = tk.Frame(imu, bg=PANEL)
        ivl.pack(anchor="w", pady=(5, 0))
        tk.Label(ivl, text="更新間隔", bg=PANEL, fg=DIM,
                 font=("Consolas", 11)).pack(side="left")
        tk.Entry(ivl, textvariable=self._interval_var, width=6,
                 bg=LOG_BG, fg=GOLD, font=("Consolas", 11),
                 relief="flat", insertbackground=GOLD,
                 justify="center").pack(side="left", padx=4)
        tk.Label(ivl, text="ms", bg=PANEL, fg=DIM,
                 font=("Consolas", 11)).pack(side="left")

        tk.Frame(f, bg=BORDER, width=2).pack(side="left", fill="y", padx=18, pady=2)

        led = tk.Frame(f, bg=PANEL)
        led.pack(side="left")

        hdr_led = tk.Frame(led, bg=PANEL)
        hdr_led.pack(anchor="w", pady=(0, 4))
        self._led_dot = self._status_dot(hdr_led, "#332200", "#886600")
        self._led_dot.pack(side="left", padx=(0, 5))
        tk.Label(hdr_led, text="LED CONTROL", bg=PANEL, fg=AMBER,
                 font=("Consolas", 11, "bold")).pack(side="left")

        btns_led = tk.Frame(led, bg=PANEL)
        btns_led.pack()
        self._btn(btns_led, "✦  START LED",
                  "#332200", AMBER, self._start_led, "#554400").pack(side="left", padx=(0, 3))
        self._btn(btns_led, "✕  STOP LED",
                  "#221100", "#cc7700", self._stop_led, "#442200").pack(side="left")

    def _build_log(self, parent):
        f = tk.Frame(parent, bg=PANEL, padx=6, pady=4)
        f.pack(fill="x", padx=6, pady=(0, 6))
        f.columnconfigure(0, weight=1)

        hdr = tk.Frame(f, bg=PANEL)
        hdr.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 2))
        tk.Label(hdr, text="Serial Log", bg=PANEL, fg=CYAN,
                 font=("Consolas", 13, "bold")).pack(side="left")

        for txt, cmd in (("Clear", self._clear_log), ("Copy", self._copy_log)):
            tk.Button(hdr, text=txt, bg=BORDER, fg=TEXT,
                      activebackground="#252548", relief="flat", bd=0,
                      font=("Consolas", 11), padx=8, pady=2, cursor="hand2",
                      command=cmd).pack(side="right", padx=2)

        self._log = tk.Text(f, height=7, bg=LOG_BG, fg=LOG_FG,
                            font=("Consolas", 11), state="disabled",
                            wrap="char", relief="flat", bd=0,
                            insertbackground=LOG_FG)
        self._log.grid(row=1, column=0, sticky="ew")

        sb = ttk.Scrollbar(f, command=self._log.yview)
        sb.grid(row=1, column=1, sticky="ns")
        self._log["yscrollcommand"] = sb.set

        ir = tk.Frame(f, bg=LOG_BG)
        ir.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(2, 0))
        self._inp = tk.Entry(ir, bg=LOG_BG, fg=LOG_FG, font=("Consolas", 11),
                             relief="flat", insertbackground=LOG_FG)
        self._inp.pack(side="left", fill="x", expand=True, padx=4, pady=2)
        self._inp.bind("<Return>", self._send)
        tk.Button(ir, text="Send", bg=BORDER, fg=TEXT,
                  activebackground="#252548", relief="flat", bd=0,
                  font=("Consolas", 11), padx=10, cursor="hand2",
                  command=self._send).pack(side="left")

    # ── MAVLink Monitor 分頁 ────────────────────────────────────────────────────

    def _build_mavlink_tab(self, parent):
        # 連線工具列
        cb = tk.Frame(parent, bg=PANEL, pady=7, padx=12)
        cb.pack(fill="x")

        tk.Label(cb, text="Port:", bg=PANEL, fg=DIM,
                 font=("Consolas", 11)).pack(side="left", padx=(0, 4))
        self._mav_port_var = tk.StringVar()
        self._mav_pcb = ttk.Combobox(cb, textvariable=self._mav_port_var,
                                      width=46, state="readonly",
                                      font=("Consolas", 11))
        self._mav_pcb.pack(side="left", padx=2)

        self._mav_baud_var = tk.StringVar(value="57600")
        ttk.Combobox(cb, textvariable=self._mav_baud_var, width=9, state="readonly",
                     values=["57600", "115200", "9600"],
                     font=("Consolas", 11)).pack(side="left", padx=2)

        tk.Button(cb, text="⟳", width=3, bg=PANEL, fg=TEXT,
                  activebackground=BORDER, relief="flat", bd=0,
                  font=("Consolas", 14), cursor="hand2",
                  command=self._mav_refresh_ports).pack(side="left", padx=2)

        self._mav_cbtn = tk.Button(cb, text="Connect", width=12,
                                    bg="#003322", fg=GREEN,
                                    activebackground="#005533", activeforeground=GREEN,
                                    relief="flat", bd=0, font=("Consolas", 13, "bold"),
                                    padx=8, pady=3, cursor="hand2",
                                    command=self._mav_toggle)
        self._mav_cbtn.pack(side="left", padx=10)

        self._mav_dot = tk.Canvas(cb, width=10, height=10,
                                   bg=PANEL, highlightthickness=0)
        self._mav_dot.create_oval(1, 1, 9, 9, fill="#440000",
                                   outline="#cc0000", width=1, tags="d")
        self._mav_dot.pack(side="left", padx=(0, 4))

        self._mav_slbl = tk.Label(cb, text="Disconnected", bg=PANEL, fg=RED,
                                   font=("Consolas", 11))
        self._mav_slbl.pack(side="left", padx=(0, 20))

        self._mav_rate_lbl = tk.Label(cb, text="0 msg/s", bg=PANEL, fg=DIM,
                                       font=("Consolas", 11))
        self._mav_rate_lbl.pack(side="right")

        if not HAS_MAV:
            tk.Label(parent,
                     text="pymavlink 未安裝\n\npip install pymavlink",
                     bg=BG, fg=RED,
                     font=("Consolas", 14), justify="center").pack(expand=True)
            self._mav_refresh_ports()
            return

        # 主區域
        main = tk.Frame(parent, bg=BG)
        main.pack(fill="both", expand=True, padx=6, pady=(4, 0))
        main.columnconfigure(0, weight=6)
        main.columnconfigure(1, weight=4)
        main.rowconfigure(0, weight=1)

        # 左側：地平線
        left = tk.Frame(main, bg=BG)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 4), pady=2)
        left.rowconfigure(0, weight=1)
        left.rowconfigure(1, weight=0)
        left.columnconfigure(0, weight=1)

        self._mav_hcanvas = tk.Canvas(left, bg=BG, highlightthickness=0)
        self._mav_hcanvas.grid(row=0, column=0, sticky="nsew")
        self._mav_hcanvas.bind("<Configure>", lambda _: self._mav_redraw_horizon())

        # 羅盤列（地平線下方）
        comp_strip = tk.Frame(left, bg=PANEL, pady=6)
        comp_strip.grid(row=1, column=0, sticky="ew")

        tk.Label(comp_strip, text="YAW", bg=PANEL, fg=DIM,
                 font=("Consolas", 11)).pack(side="left", padx=(10, 6))

        self._mav_compass = tk.Canvas(comp_strip, width=90, height=90,
                                       bg=PANEL, highlightthickness=0)
        self._mav_compass.pack(side="left", padx=(0, 8))
        self._mav_compass.bind("<Configure>", lambda _: self._mav_draw_compass(self._mav_yaw))

        self._mav_yaw_lbl = tk.Label(comp_strip, text="---°",
                                      bg=PANEL, fg=GOLD,
                                      font=("Consolas", 24, "bold"))
        self._mav_yaw_lbl.pack(side="left")

        # 右側：數值面板
        rp = tk.Frame(main, bg=PANEL, padx=12, pady=8)
        rp.grid(row=0, column=1, sticky="nsew", pady=2)

        # (title, [(label, key, color, unit), ...])
        sections = [
            ("SYSTEM", [
                ("Armed",  "armed",   GREEN, ""),
                ("Mode",   "mode",    AMBER, ""),
                ("HB",     "hb",      DIM,   ""),
            ]),
            # attitude_estimator_q (quaternion complementary filter, no EKF/GPS)
            # Yaw initialises to 0 at boot — drifts without magnetometer
            ("ATTITUDE  (Q estimator)", [
                ("Roll",   "roll",    GOLD, "°"),
                ("Pitch",  "pitch",   GOLD, "°"),
                ("Yaw *",  "yaw",     GOLD, "°"),
            ]),
            ("SCALED IMU", [
                ("Ax",     "imu_ax",  CYAN, "m/s²"),
                ("Ay",     "imu_ay",  CYAN, "m/s²"),
                ("Az",     "imu_az",  CYAN, "m/s²"),
                ("Gx",     "imu_gx",  TEXT, "r/s"),
                ("Gy",     "imu_gy",  TEXT, "r/s"),
                ("Gz",     "imu_gz",  TEXT, "r/s"),
            ]),
        ]

        for sect_title, fields in sections:
            tk.Label(rp, text=sect_title, bg=PANEL, fg=CYAN,
                     font=("Consolas", 12, "bold")).pack(anchor="w", pady=(10, 2))
            for lbl, key, color, unit in fields:
                row = tk.Frame(rp, bg=PANEL)
                row.pack(fill="x", pady=1)
                tk.Label(row, text=f"  {lbl}:", bg=PANEL, fg=DIM,
                         font=("Consolas", 11), width=8).pack(side="left")
                var = tk.StringVar(value="---")
                tk.Label(row, textvariable=var, bg=PANEL, fg=color,
                         font=("Consolas", 16, "bold"), width=10).pack(side="left")
                if unit:
                    tk.Label(row, text=unit, bg=PANEL, fg=DIM,
                             font=("Consolas", 10)).pack(side="left")
                self._mav_dvars[key] = var
            tk.Frame(rp, bg=BORDER, height=1).pack(fill="x", pady=(4, 0))

        tk.Label(rp, text="* Yaw 從 0° 開機，無磁力計會漂移",
                 bg=PANEL, fg=DIM, font=("Consolas", 9),
                 wraplength=200, justify="left").pack(anchor="w", pady=(2, 0))

        # MAVLink log
        lf = tk.Frame(parent, bg=PANEL, padx=6, pady=4)
        lf.pack(fill="x", padx=6, pady=(4, 6))
        lf.columnconfigure(0, weight=1)

        hdr = tk.Frame(lf, bg=PANEL)
        hdr.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 2))
        tk.Label(hdr, text="MAVLink Log", bg=PANEL, fg=CYAN,
                 font=("Consolas", 13, "bold")).pack(side="left")
        tk.Button(hdr, text="Clear", bg=BORDER, fg=TEXT,
                  activebackground="#252548", relief="flat", bd=0,
                  font=("Consolas", 11), padx=8, pady=2, cursor="hand2",
                  command=self._mav_clear_log).pack(side="right", padx=2)

        self._mav_log = tk.Text(lf, height=5, bg=LOG_BG, fg=MAV_FG,
                                 font=("Consolas", 11), state="disabled",
                                 wrap="char", relief="flat", bd=0)
        self._mav_log.grid(row=1, column=0, sticky="ew")
        mav_sb = ttk.Scrollbar(lf, command=self._mav_log.yview)
        mav_sb.grid(row=1, column=1, sticky="ns")
        self._mav_log["yscrollcommand"] = mav_sb.set

        self._mav_refresh_ports()

    # ── MAVLink 串列埠 ─────────────────────────────────────────────────────────

    def _mav_refresh_ports(self):
        ports = sorted(serial.tools.list_ports.comports(), key=lambda p: p.device)
        vals = []
        for p in ports:
            desc = re.sub(r'\s*\(COM\d+\)\s*$', '', p.description or '',
                          flags=re.I).strip()
            if desc and desc.lower() != p.device.lower():
                vals.append(f"{p.device}  ─  {desc}")
            else:
                vals.append(p.device)
        self._mav_pcb["values"] = vals
        if vals and not self._mav_port_var.get():
            self._mav_pcb.current(0)

    def _mav_sel_port(self):
        t = self._mav_port_var.get()
        return t.split()[0] if t else None

    def _mav_toggle(self):
        if self._mav_conn and self._mav_running:
            self._mav_disconnect()
        else:
            self._mav_connect()

    def _mav_connect(self):
        if not HAS_MAV:
            return
        port = self._mav_sel_port()
        if not port:
            return
        try:
            baud = int(self._mav_baud_var.get())
            self._mav_conn = mav_util.mavlink_connection(
                port, baud=baud, source_system=255, dialect='common')
            self._mav_running = True
            self._mav_hb_count = 0
            self._mav_msg_count = 0
            threading.Thread(target=self._mav_rx_loop, daemon=True).start()
            self._mav_cbtn.configure(text="Disconnect")
            self._mav_dot.itemconfig("d", fill="#00aa44", outline=GREEN)
            self._mav_slbl.configure(text=f"{port} @ {baud}", fg=GREEN)
            self._mav_log_add(f"[Connected {port} @ {baud} bps]\n")
        except Exception as e:
            self._mav_log_add(f"[Connect error: {e}]\n")

    def _mav_disconnect(self):
        self._mav_running = False
        if self._mav_conn:
            try:
                self._mav_conn.close()
            except Exception:
                pass
        self._mav_conn = None
        self._mav_cbtn.configure(text="Connect")
        self._mav_dot.itemconfig("d", fill="#440000", outline="#cc0000")
        self._mav_slbl.configure(text="Disconnected", fg=RED)
        self._mav_log_add("[Disconnected]\n")

    # ── MAVLink 接收執行緒 ─────────────────────────────────────────────────────

    def _mav_rx_loop(self):
        while self._mav_running and self._mav_conn:
            try:
                msg = self._mav_conn.recv_match(blocking=True, timeout=1.0)
                if msg is None:
                    continue
                mt = msg.get_type()
                if mt == 'BAD_DATA':
                    continue
                self._mav_msg_count += 1
                if mt in ('HEARTBEAT', 'ATTITUDE', 'SCALED_IMU', 'SCALED_IMU2'):
                    self._mav_q.put((mt, msg))
            except Exception as e:
                if self._mav_running:
                    self._mav_q.put(('_ERR', str(e)))
                break

    # ── MAVLink UI 輪詢 ────────────────────────────────────────────────────────

    def _mav_poll(self):
        try:
            while True:
                mt, msg = self._mav_q.get_nowait()
                if mt == '_ERR':
                    self._mav_log_add(f"[Error: {msg}]\n")
                    self._mav_running = False
                    break

                elif mt == 'HEARTBEAT':
                    self._mav_hb_count += 1
                    armed = bool(msg.base_mode & 128)
                    mode  = _decode_px4_mode(msg.custom_mode)
                    # 只在狀態變化時寫 log，避免每秒洗版
                    state_changed = (armed != self._mav_armed or mode != self._mav_mode)
                    self._mav_armed = armed
                    self._mav_mode  = mode
                    if self._mav_dvars:
                        self._mav_dvars['armed'].set("ARMED" if armed else "DISARM")
                        self._mav_dvars['mode'].set(mode)
                        self._mav_dvars['hb'].set(f"#{self._mav_hb_count}")
                    if state_changed:
                        self._mav_log_add(
                            f"[HB #{self._mav_hb_count}] armed={armed}  mode={mode}\n")

                elif mt == 'ATTITUDE':
                    self._mav_roll  = math.degrees(msg.roll)
                    self._mav_pitch = math.degrees(msg.pitch)
                    self._mav_yaw   = math.degrees(msg.yaw)
                    if self._mav_dvars:
                        self._mav_dvars['roll'].set(f"{self._mav_roll:+.1f}°")
                        self._mav_dvars['pitch'].set(f"{self._mav_pitch:+.1f}°")
                        self._mav_dvars['yaw'].set(f"{self._mav_yaw:+.1f}°")

                elif mt in ('SCALED_IMU', 'SCALED_IMU2'):
                    # mG → m/s²,  mrad/s → rad/s
                    ax = msg.xacc  / 1000.0 * 9.81
                    ay = msg.yacc  / 1000.0 * 9.81
                    az = msg.zacc  / 1000.0 * 9.81
                    gx = msg.xgyro / 1000.0
                    gy = msg.ygyro / 1000.0
                    gz = msg.zgyro / 1000.0
                    if self._mav_dvars:
                        self._mav_dvars['imu_ax'].set(f"{ax:+.3f}")
                        self._mav_dvars['imu_ay'].set(f"{ay:+.3f}")
                        self._mav_dvars['imu_az'].set(f"{az:+.3f}")
                        self._mav_dvars['imu_gx'].set(f"{gx:+.4f}")
                        self._mav_dvars['imu_gy'].set(f"{gy:+.4f}")
                        self._mav_dvars['imu_gz'].set(f"{gz:+.4f}")
        except queue.Empty:
            pass

        # 更新 msg/s 計數
        now = time.monotonic()
        dt = now - self._mav_last_ts
        if dt >= 1.0:
            rate = (self._mav_msg_count - self._mav_last_count) / dt
            self._mav_rate_lbl.configure(text=f"{rate:.0f} msg/s")
            self._mav_last_count = self._mav_msg_count
            self._mav_last_ts    = now

        # 更新羅盤 & 地平線
        if HAS_MAV and hasattr(self, '_mav_yaw_lbl'):
            self._mav_yaw_lbl.configure(text=f"{self._mav_yaw:+.1f}°")
            self._mav_draw_compass(self._mav_yaw)
            self._mav_redraw_horizon()

        # 狀態點閃爍
        self._mav_blink = not self._mav_blink
        if self._mav_running:
            self._mav_dot.itemconfig("d",
                fill=(GREEN if self._mav_blink else "#004400"))

        self.after(100, self._mav_poll)

    def _mav_redraw_horizon(self):
        if not hasattr(self, '_mav_hcanvas'):
            return
        w = self._mav_hcanvas.winfo_width()
        h = self._mav_hcanvas.winfo_height()
        img = render_horizon(w, h, self._mav_roll, self._mav_pitch)
        if img:
            self._mav_tk_img = ImageTk.PhotoImage(img)
            self._mav_hcanvas.delete("all")
            self._mav_hcanvas.create_image(0, 0, anchor="nw", image=self._mav_tk_img)
        else:
            draw_horizon_fallback(self._mav_hcanvas, self._mav_roll, self._mav_pitch)

    def _mav_draw_compass(self, yaw_deg):
        if not hasattr(self, '_mav_compass'):
            return
        c = self._mav_compass
        c.delete("all")
        w = c.winfo_width()
        h = c.winfo_height()
        if w < 20 or h < 20:
            return
        cx, cy = w // 2, h // 2
        r = min(cx, cy) - 4
        # 外圈
        c.create_oval(cx-r, cy-r, cx+r, cy+r, outline=CYAN, width=1, fill="#0a0a1e")
        # 刻度線
        for ang in range(0, 360, 30):
            ar = math.radians(ang - 90)
            tl = 9 if ang % 90 == 0 else 5
            c.create_line(cx + (r-tl)*math.cos(ar), cy + (r-tl)*math.sin(ar),
                          cx + r*math.cos(ar),       cy + r*math.sin(ar),
                          fill=(CYAN if ang % 90 == 0 else DIM), width=1)
        # NSEW 標籤
        for ang, label in [(0,'N'), (90,'E'), (180,'S'), (270,'W')]:
            ar  = math.radians(ang - 90)
            col = RED if ang == 0 else DIM
            c.create_text(cx + (r - 14)*math.cos(ar),
                          cy + (r - 14)*math.sin(ar),
                          text=label, fill=col,
                          font=("Consolas", 8, "bold"))
        # 航向箭頭
        yr = math.radians(yaw_deg - 90)
        tip_x = cx + (r - 4)*math.cos(yr)
        tip_y = cy + (r - 4)*math.sin(yr)
        c.create_line(cx, cy, tip_x, tip_y, fill=AMBER, width=3, arrow="last")
        # 中心點
        c.create_oval(cx-3, cy-3, cx+3, cy+3, fill=AMBER, outline=AMBER)

    def _mav_log_add(self, text):
        if not hasattr(self, '_mav_log'):
            return
        self._mav_log.configure(state="normal")
        self._mav_log.insert("end", text)
        self._mav_log.see("end")
        n = int(self._mav_log.index("end").split(".")[0])
        if n > 2000:
            self._mav_log.delete("1.0", f"{n - 1500}.0")
        self._mav_log.configure(state="disabled")

    def _mav_clear_log(self):
        if not hasattr(self, '_mav_log'):
            return
        self._mav_log.configure(state="normal")
        self._mav_log.delete("1.0", "end")
        self._mav_log.configure(state="disabled")

    # ── NSH 串列埠 ─────────────────────────────────────────────────────────────

    def _refresh_ports(self):
        ports = sorted(serial.tools.list_ports.comports(), key=lambda p: p.device)
        vals = []
        for p in ports:
            desc = re.sub(r'\s*\(COM\d+\)\s*$', '', p.description or '',
                          flags=re.I).strip()
            if desc and desc.lower() != p.device.lower():
                vals.append(f"{p.device}  ─  {desc}")
            else:
                vals.append(p.device)
        self._pcb["values"] = vals
        if vals and not self._port_var.get():
            self._pcb.current(0)

    def _sel_port(self):
        t = self._port_var.get()
        return t.split()[0] if t else None

    def _toggle(self):
        if self._ser and self._ser.is_open:
            self._disconnect()
        else:
            self._connect()

    def _connect(self):
        port = self._sel_port()
        if not port:
            return
        try:
            baud = int(self._baud_var.get())
            self._ser = serial.Serial(port, baud, timeout=0.1)
            self._running = True
            threading.Thread(target=self._rx_loop, daemon=True).start()
            self._cbtn.configure(text="Disconnect")
            self._dot.itemconfig("d", fill="#00aa44", outline=GREEN)
            self._slbl.configure(text=port, fg=GREEN)
            self._log_add(f"[Connected  {port} @ {baud} bps]\n")
        except Exception as e:
            self._log_add(f"[Error: {e}]\n")

    def _disconnect(self):
        self._running = False
        try:
            if self._ser:
                self._ser.close()
        except Exception:
            pass
        self._ser = None
        self._imu_on = self._led_on = False
        self._cbtn.configure(text="Connect")
        self._dot.itemconfig("d", fill="#440000", outline="#cc0000")
        self._slbl.configure(text="Disconnected", fg=RED)
        self._imu_dot.itemconfig("d", fill="#003300", outline="#006600")
        self._led_dot.itemconfig("d", fill="#332200", outline="#886600")
        self._log_add("[Disconnected]\n")

    # ── NSH 接收執行緒 ─────────────────────────────────────────────────────────

    def _rx_loop(self):
        while self._running and self._ser and self._ser.is_open:
            try:
                data = self._ser.read(512)
                if data:
                    self._q.put(data.decode("utf-8", errors="replace"))
            except Exception:
                if self._running:
                    self._q.put("\n[Serial read error]\n")
                break

    def _send(self, _=None):
        cmd = self._inp.get().strip()
        self._inp.delete(0, "end")
        if not cmd:
            return
        self._log_add(f"> {cmd}\n")
        if self._ser and self._ser.is_open:
            try:
                self._ser.write((cmd + "\r\n").encode())
            except Exception as e:
                self._log_add(f"[Send error: {e}]\n")

    def _send_cmd(self, cmd):
        self._log_add(f"> {cmd}\n")
        if self._ser and self._ser.is_open:
            try:
                self._ser.write((cmd + "\r\n").encode())
            except Exception as e:
                self._log_add(f"[Send error: {e}]\n")
        else:
            self._log_add("[請先連線]\n")

    # ── 姿態更新 ───────────────────────────────────────────────────────────────

    def _on_att(self, roll, pitch, ax, ay, az, gx, gy, gz):
        self._roll  = roll
        self._pitch = pitch
        self._vals  = dict(ax=ax, ay=ay, az=az, gx=gx, gy=gy, gz=gz)

    def _poll(self):
        try:
            while True:
                text = self._q.get_nowait()
                self._log_add(text)
                clean = _ANSI_RE.sub('', text)
                for ln in clean.splitlines():
                    self._parser.feed(ln)
                    if ln.strip() == 'nsh>' and self._imu_on and self._listener_up:
                        self._listener_up = False
                        if self._poll_topic == 'accel':
                            self._poll_topic = 'gyro'
                            self.after(50, self._start_listener)
                        else:
                            self._poll_topic = 'accel'
                            try:
                                interval = max(50, int(self._interval_var.get()))
                            except ValueError:
                                interval = 300
                            self.after(interval, self._start_listener)
        except queue.Empty:
            pass

        self._redraw_horizon()
        self._dvars["roll"].set(f"{self._roll:+.1f}")
        self._dvars["pitch"].set(f"{self._pitch:+.1f}")
        for k in ("ax", "ay", "az", "gx", "gy", "gz"):
            self._dvars[k].set(f"{self._vals[k]:+.4f}")

        self._blink = not self._blink
        if self._imu_on:
            self._imu_dot.itemconfig("d", fill=(GREEN if self._blink else "#004400"))
        if self._led_on:
            self._led_dot.itemconfig("d", fill=(AMBER if self._blink else "#442200"))

        self.after(50, self._poll)

    def _redraw_horizon(self):
        w = self._hcanvas.winfo_width()
        h = self._hcanvas.winfo_height()
        img = render_horizon(w, h, self._roll, self._pitch)
        if img:
            self._tk_img = ImageTk.PhotoImage(img)
            self._hcanvas.delete("all")
            self._hcanvas.create_image(0, 0, anchor="nw", image=self._tk_img)
        else:
            draw_horizon_fallback(self._hcanvas, self._roll, self._pitch)

    # ── IMU 控制 ───────────────────────────────────────────────────────────────

    def _start_imu(self):
        if not (self._ser and self._ser.is_open):
            self._log_add("[請先連線]\n"); return
        self._imu_on = True
        self._listener_up = False
        self._poll_topic = 'accel'
        # rc.board_sensors 開機已啟動 driver，直接跑 listener 即可
        self.after(100, self._start_listener)

    def _imu_start2(self):
        pass  # 不再使用

    def _start_listener(self):
        if not (self._imu_on and self._ser and self._ser.is_open):
            return
        if time.monotonic() - self._last_listener_t < 0.1:
            return
        self._last_listener_t = time.monotonic()
        self._listener_up = True
        if self._poll_topic == 'accel':
            self._send_cmd("listener sensor_accel -n 1")
        else:
            self._send_cmd("listener sensor_gyro -n 1")

    def _stop_imu(self):
        self._imu_on = False
        self._listener_up = False
        self._poll_topic = 'accel'
        if self._ser and self._ser.is_open:
            try:
                self._ser.write(b'\x03')   # Ctrl+C 中斷 listener（不停 driver）
            except Exception:
                pass
        self._log_add("[Ctrl+C: listener stopped, driver still running]\n")
        self._imu_dot.itemconfig("d", fill="#003300", outline="#006600")

    # ── LED 控制 ───────────────────────────────────────────────────────────────

    def _start_led(self):
        if not (self._ser and self._ser.is_open):
            self._log_add("[請先連線]\n"); return
        self._send_cmd("led_chaser start")
        self._led_on = True

    def _stop_led(self):
        self._send_cmd("led_chaser stop")
        self._led_on = False
        self._led_dot.itemconfig("d", fill="#332200", outline="#886600")

    # ── 記錄區 ─────────────────────────────────────────────────────────────────

    def _log_add(self, text):
        text = _ANSI_RE.sub('', text)
        self._log.configure(state="normal")
        self._log.insert("end", text)
        self._log.see("end")
        n = int(self._log.index("end").split(".")[0])
        if n > 3000:
            self._log.delete("1.0", f"{n - 2000}.0")
        self._log.configure(state="disabled")

    def _copy_log(self):
        self.clipboard_clear()
        self.clipboard_append(self._log.get("1.0", "end"))

    def _clear_log(self):
        self._log.configure(state="normal")
        self._log.delete("1.0", "end")
        self._log.configure(state="disabled")

    def on_close(self):
        self._disconnect()
        self._mav_disconnect()
        self.destroy()


if __name__ == "__main__":
    if not HAS_PIL:
        print("提示：未安裝 Pillow，地平線使用簡化模式。pip install Pillow")
    if not HAS_MAV:
        print("提示：未安裝 pymavlink，MAVLink 分頁無法使用。pip install pymavlink")
    app = App()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()
