#!/usr/bin/env python3
"""
JARVIS HUD Overlay — always-on-top floating window
Polls localhost:7474 for state from jarvis.py
"""

import tkinter as tk
import urllib.request
import json
import time
import threading
import math

HUD_PORT = 7474
POLL_MS  = 500
WIDTH    = 340
HEIGHT   = 580

class JarvisHUD:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("JARVIS")
        self.root.geometry(f"{WIDTH}x{HEIGHT}+40+40")
        self.root.configure(bg="#000000")
        self.root.wm_attributes("-topmost", True)
        self.root.wm_attributes("-alpha", 0.92)
        self.root.overrideredirect(True)  # no window chrome

        # Allow dragging
        self.root.bind("<ButtonPress-1>", self._drag_start)
        self.root.bind("<B1-Motion>", self._drag_motion)
        self._drag_x = 0
        self._drag_y = 0

        self.state = {}
        self.start_time = time.time()
        self.transcript = []

        self._build_ui()
        self._poll()
        self._tick()

    def _drag_start(self, e):
        self._drag_x = e.x
        self._drag_y = e.y

    def _drag_motion(self, e):
        x = self.root.winfo_x() + e.x - self._drag_x
        y = self.root.winfo_y() + e.y - self._drag_y
        self.root.geometry(f"+{x}+{y}")

    def _build_ui(self):
        C = "#00d4ff"
        DIM = "#005566"
        BG = "#000000"
        PANEL = "#001118"

        pad = dict(padx=10, pady=4)

        # ── Header ────────────────────────────────────────────────────────
        hdr = tk.Frame(self.root, bg=BG)
        hdr.pack(fill="x", padx=10, pady=(8,4))

        tk.Label(hdr, text="J.A.R.V.I.S", bg=BG, fg=C,
                 font=("Courier", 13, "bold")).pack(side="left")

        close_btn = tk.Label(hdr, text="✕", bg=BG, fg=DIM,
                              font=("Courier", 11), cursor="hand2")
        close_btn.pack(side="right")
        close_btn.bind("<Button-1>", lambda e: self.root.destroy())

        tk.Frame(self.root, bg=C, height=1).pack(fill="x", padx=10)

        # ── Status ────────────────────────────────────────────────────────
        status_frame = tk.Frame(self.root, bg=PANEL, padx=10, pady=8)
        status_frame.pack(fill="x", padx=10, pady=6)

        top_row = tk.Frame(status_frame, bg=PANEL)
        top_row.pack(fill="x")

        self.dot = tk.Canvas(top_row, width=12, height=12, bg=PANEL,
                              highlightthickness=0)
        self.dot.pack(side="left", padx=(0,6))
        self.dot_circle = self.dot.create_oval(2,2,10,10, fill="#004455", outline="")

        self.status_label = tk.Label(top_row, text="IDLE", bg=PANEL, fg=C,
                                      font=("Courier", 10, "bold"))
        self.status_label.pack(side="left")

        self.clock_label = tk.Label(top_row, text="--:-- --", bg=PANEL, fg=DIM,
                                     font=("Courier", 9))
        self.clock_label.pack(side="right")

        # Arc reactor canvas
        self.arc = tk.Canvas(status_frame, width=60, height=60, bg=PANEL,
                              highlightthickness=0)
        self.arc.pack(pady=4)
        self._draw_arc()

        # ── Info row ──────────────────────────────────────────────────────
        info = tk.Frame(self.root, bg=BG)
        info.pack(fill="x", padx=10, pady=2)

        self.weather_label = tk.Label(info, text="WEATHER: --", bg=BG, fg=DIM,
                                       font=("Courier", 8))
        self.weather_label.pack(side="left")

        self.wake_label = tk.Label(info, text="WAKES: 0", bg=BG, fg=DIM,
                                    font=("Courier", 8))
        self.wake_label.pack(side="right")

        tk.Frame(self.root, bg="#002233", height=1).pack(fill="x", padx=10)

        # ── Transcript ────────────────────────────────────────────────────
        tk.Label(self.root, text="CONVERSATION LOG", bg=BG, fg=DIM,
                 font=("Courier", 7), anchor="w").pack(fill="x", padx=12, pady=(6,2))

        transcript_frame = tk.Frame(self.root, bg=BG)
        transcript_frame.pack(fill="both", expand=True, padx=10)

        self.transcript_text = tk.Text(
            transcript_frame,
            bg="#000a0f", fg=C,
            font=("Courier", 9),
            relief="flat",
            borderwidth=0,
            wrap="word",
            state="disabled",
            cursor="arrow",
            highlightthickness=1,
            highlightbackground="#002233",
        )
        self.transcript_text.pack(fill="both", expand=True)
        self.transcript_text.tag_config("user", foreground="#00ff88")
        self.transcript_text.tag_config("user_label", foreground="#00ff88",
                                         font=("Courier", 7, "bold"))
        self.transcript_text.tag_config("jarvis_label", foreground="#00d4ff",
                                         font=("Courier", 7, "bold"))
        self.transcript_text.tag_config("jarvis", foreground="#00aacc")

        # ── Footer ────────────────────────────────────────────────────────
        tk.Frame(self.root, bg="#002233", height=1).pack(fill="x", padx=10)
        footer = tk.Frame(self.root, bg=BG)
        footer.pack(fill="x", padx=10, pady=4)

        self.query_label = tk.Label(footer, text="QUERIES: 0", bg=BG, fg=DIM,
                                     font=("Courier", 7))
        self.query_label.pack(side="left")

        self.uptime_label = tk.Label(footer, text="UP: 00:00:00", bg=BG, fg=DIM,
                                      font=("Courier", 7))
        self.uptime_label.pack(side="right")

    def _draw_arc(self):
        c = self.arc
        c.delete("all")
        cx, cy, r = 30, 30, 26
        c.create_oval(cx-r, cy-r, cx+r, cy+r, outline="#002233", width=1)
        r2 = 20
        c.create_oval(cx-r2, cy-r2, cx+r2, cy+r2, outline="#004455", width=1)
        r3 = 13
        c.create_oval(cx-r3, cy-r3, cx+r3, cy+r3, outline="#00d4ff", width=1)
        r4 = 6
        c.create_oval(cx-r4, cy-r4, cx+r4, cy+r4, fill="#003344", outline="#00d4ff", width=1)
        c.create_oval(cx-3, cy-3, cx+3, cy+3, fill="#00d4ff", outline="")
        for angle in [0, 90, 180, 270]:
            rad = math.radians(angle)
            x1 = cx + math.cos(rad) * (r3+1)
            y1 = cy + math.sin(rad) * (r3+1)
            x2 = cx + math.cos(rad) * (r+0)
            y2 = cy + math.sin(rad) * (r+0)
            c.create_line(x1, y1, x2, y2, fill="#00d4ff", width=1)

    def _set_status(self, s):
        colors = {
            "idle":      "#003344",
            "listening": "#00ff88",
            "thinking":  "#ffaa00",
            "speaking":  "#00d4ff",
        }
        labels = {
            "idle": "IDLE", "listening": "LISTENING",
            "thinking": "PROCESSING", "speaking": "SPEAKING",
        }
        color = colors.get(s, "#003344")
        self.dot.itemconfig(self.dot_circle, fill=color)
        self.status_label.config(text=labels.get(s, "IDLE"),
                                  fg=color if s != "idle" else "#00d4ff")

    def _add_transcript(self, role, text):
        t = self.transcript_text
        t.config(state="normal")
        if role == "user":
            t.insert("end", "BOSS\n", "user_label")
            t.insert("end", text + "\n\n", "user")
        else:
            t.insert("end", "JARVIS\n", "jarvis_label")
            t.insert("end", text + "\n\n", "jarvis")
        t.see("end")
        # Keep last 40 lines
        lines = int(t.index("end-1c").split(".")[0])
        if lines > 80:
            t.delete("1.0", f"{lines-80}.0")
        t.config(state="disabled")

    def _poll(self):
        def fetch():
            try:
                req = urllib.request.Request(f"http://localhost:{HUD_PORT}/state")
                with urllib.request.urlopen(req, timeout=1) as r:
                    data = json.loads(r.read().decode())
                self.root.after(0, lambda: self._update(data))
            except:
                pass
            self.root.after(POLL_MS, self._poll)
        threading.Thread(target=fetch, daemon=True).start()

    def _update(self, data):
        self._set_status(data.get("status", "idle"))

        user_said = data.get("user_said")
        jarvis_said = data.get("jarvis_said")

        if user_said and user_said != self.state.get("user_said"):
            self._add_transcript("user", user_said)
        if jarvis_said and jarvis_said != self.state.get("jarvis_said"):
            self._add_transcript("jarvis", jarvis_said)

        if data.get("weather_temp"):
            self.weather_label.config(
                text=f"{data['weather_temp']} · {data.get('weather_desc','')[:12]}")

        self.wake_label.config(text=f"WAKES: {data.get('wake_count', 0)}")
        self.query_label.config(text=f"QUERIES: {data.get('query_count', 0)}")
        self.state = data

    def _tick(self):
        elapsed = int(time.time() - self.start_time)
        hh, mm, ss = elapsed//3600, (elapsed%3600)//60, elapsed%60
        self.uptime_label.config(
            text=f"UP: {hh:02d}:{mm:02d}:{ss:02d}")
        now = time.localtime()
        h = now.tm_hour % 12 or 12
        ampm = "AM" if now.tm_hour < 12 else "PM"
        self.clock_label.config(
            text=f"{h:02d}:{now.tm_min:02d} {ampm}")
        self.root.after(1000, self._tick)

    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    JarvisHUD().run()