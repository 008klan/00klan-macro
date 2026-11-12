"""00klan macro - mouse + keyboard macro recorder/player."""
import ctypes
import json
import sys
import threading
import time
from tkinter import filedialog, messagebox

import customtkinter as ctk
from pynput import keyboard, mouse

APP_NAME = "00klan macro"
VERSION = "0.3.0"

# Dark / blue gaming palette
BG, PANEL, CARD = "#070b14", "#0e1626", "#131d33"
BLUE, BLUE_H = "#2f81ff", "#1f63c9"
TEXT, MUTED = "#e6edf7", "#7d8aa5"
RED, GREEN = "#ff4d6d", "#2ee6a6"

HOTKEYS = {keyboard.Key.f6, keyboard.Key.f7, keyboard.Key.f8}
MOVE_THROTTLE = 0.02  # seconds between recorded mouse moves
RESERVED = {"f6", "f7", "f8"}  # used by the recorder hotkeys

try:  # 1 ms timer resolution on Windows so high click rates are accurate
    ctypes.windll.winmm.timeBeginPeriod(1)
except Exception:
    pass


MOUSE_NAMES = {"left": "LEFT CLICK", "right": "RIGHT CLICK", "middle": "MIDDLE CLICK",
               "x1": "MOUSE 4 (BACK)", "x2": "MOUSE 5 (FORWARD)",
               "button8": "MOUSE 4 (BACK)", "button9": "MOUSE 5 (FORWARD)"}


def kid(e):
    """Stable identity of an encoded key or mouse button, for comparing."""
    if "m" in e:
        return ("m", e["m"])
    if "s" in e:
        return ("s", e["s"])
    if e.get("vk") is not None:
        return ("vk", e["vk"])
    return ("c", (e.get("c") or "").lower())


def key_name(e):
    if "m" in e:
        return MOUSE_NAMES.get(e["m"], e["m"].upper())
    if "s" in e:
        return e["s"].upper()
    return (e.get("c") or f"VK{e.get('vk')}").upper()


def enc_key(k):
    if isinstance(k, keyboard.Key):
        return {"s": k.name}
    return {"vk": getattr(k, "vk", None), "c": getattr(k, "char", None)}


def dec_key(d):
    if "s" in d:
        return keyboard.Key[d["s"]]
    if d.get("vk") is not None:
        return keyboard.KeyCode.from_vk(d["vk"])
    return d["c"]


def label(ev):
    t = ev["type"]
    if t == "move":
        return f"move   ({ev['x']}, {ev['y']})"
    if t == "click":
        return f"{'down' if ev['pressed'] else 'up  '}   {ev['button']} @ ({ev['x']}, {ev['y']})"
    if t == "scroll":
        return f"scroll ({ev['dx']}, {ev['dy']})"
    k = ev["key"]
    name = k.get("s") or k.get("c") or f"vk{k.get('vk')}"
    return f"key {'down' if ev['pressed'] else 'up  '} {name}"


class App(ctk.CTk):
    def __init__(self):
        super().__init__(fg_color=BG)
        ctk.set_appearance_mode("dark")
        self.title(f"{APP_NAME}  v{VERSION}")
        self.geometry("900x620")
        self.minsize(820, 580)

        self.events = []
        self.recording = False
        self.playing = False
        self.stop_flag = threading.Event()
        self.t_last = 0.0
        self.t_last_move = 0.0
        self.m_listener = self.k_listener = None

        # auto clicker state
        self.kc, self.mc = keyboard.Controller(), mouse.Controller()
        self.cps = 10
        self.action = "Keyboard key"
        self.mode = "Toggle"
        self.bind = {"s": "f9"}
        self.target = {"vk": None, "c": "e"}
        self.capturing = None
        self.bind_down = False
        self.armed = True
        self.spamming = False
        self.spam_stop = threading.Event()

        self._build_ui()
        self.k_all = keyboard.Listener(on_press=self._gp, on_release=self._gr)
        self.k_all.start()
        kw = {"win32_event_filter": self._m_filter} if sys.platform == "win32" else {}
        self.m_all = mouse.Listener(on_click=self._gc, **kw)
        self.m_all.start()

        self.hotkeys = keyboard.GlobalHotKeys({
            "<f6>": lambda: self.after(0, self.toggle_record),
            "<f7>": lambda: self.after(0, self.toggle_play),
            "<f8>": lambda: self.after(0, self.stop_all),
        })
        self.hotkeys.start()
        self.protocol("WM_DELETE_WINDOW", self._close)

    # ---------- UI ----------
    def _build_ui(self):
        head = ctk.CTkFrame(self, fg_color=PANEL, corner_radius=0, height=64)
        head.pack(fill="x")
        ctk.CTkLabel(head, text="00KLAN", font=("Segoe UI Black", 26), text_color=BLUE).pack(side="left", padx=(22, 6), pady=14)
        ctk.CTkLabel(head, text="MACRO", font=("Segoe UI Light", 26), text_color=TEXT).pack(side="left")
        self.status = ctk.CTkLabel(head, text="● IDLE", font=("Segoe UI Semibold", 14), text_color=MUTED)
        self.status.pack(side="right", padx=24)

        tabs = ctk.CTkTabview(self, fg_color=BG, segmented_button_fg_color=PANEL,
                              segmented_button_selected_color=BLUE, segmented_button_selected_hover_color=BLUE_H,
                              segmented_button_unselected_color=PANEL, segmented_button_unselected_hover_color=CARD,
                              text_color=TEXT)
        tabs.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        t_rec, t_clk = tabs.add("Macro Recorder"), tabs.add("Auto Clicker")
        self._build_clicker(t_clk)

        body = ctk.CTkFrame(t_rec, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=6, pady=6)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        # Controls
        left = ctk.CTkFrame(body, fg_color=CARD, corner_radius=14, width=270)
        left.grid(row=0, column=0, sticky="ns", padx=(0, 14))
        left.grid_propagate(False)

        def btn(text, cmd, color=BLUE, hover=BLUE_H):
            b = ctk.CTkButton(left, text=text, command=cmd, fg_color=color, hover_color=hover,
                              height=42, corner_radius=10, font=("Segoe UI Semibold", 14))
            b.pack(fill="x", padx=18, pady=(10, 0))
            return b

        self.b_rec = btn("●  Record   [F6]", self.toggle_record, "#c9304f", "#a32541")
        self.b_play = btn("▶  Play   [F7]", self.toggle_play)
        btn("■  Stop   [F8]", self.stop_all, "#1b2a47", "#24375c")

        ctk.CTkLabel(left, text="REPEAT  (0 = infinite)", text_color=MUTED, font=("Segoe UI", 11)).pack(anchor="w", padx=18, pady=(18, 2))
        self.repeat = ctk.CTkEntry(left, fg_color=BG, border_color=BLUE, height=34)
        self.repeat.insert(0, "1")
        self.repeat.pack(fill="x", padx=18)

        self.speed_lbl = ctk.CTkLabel(left, text="SPEED  1.00x", text_color=MUTED, font=("Segoe UI", 11))
        self.speed_lbl.pack(anchor="w", padx=18, pady=(14, 2))
        self.speed = ctk.CTkSlider(left, from_=0.25, to=4, number_of_steps=15, progress_color=BLUE,
                                   button_color=BLUE, button_hover_color=BLUE_H, command=self._speed_changed)
        self.speed.set(1)
        self.speed.pack(fill="x", padx=18)

        row = ctk.CTkFrame(left, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=(22, 0))
        for t, c in (("Save", self.save), ("Load", self.load), ("Clear", self.clear)):
            ctk.CTkButton(row, text=t, command=c, width=70, height=34, fg_color="#1b2a47",
                          hover_color="#24375c", corner_radius=8).pack(side="left", expand=True, padx=3)

        # Event log
        right = ctk.CTkFrame(body, fg_color=CARD, corner_radius=14)
        right.grid(row=0, column=1, sticky="nsew")
        top = ctk.CTkFrame(right, fg_color="transparent")
        top.pack(fill="x", padx=18, pady=(14, 4))
        ctk.CTkLabel(top, text="MACRO EVENTS", text_color=BLUE, font=("Segoe UI Semibold", 13)).pack(side="left")
        self.count = ctk.CTkLabel(top, text="0 events", text_color=MUTED)
        self.count.pack(side="right")
        self.log = ctk.CTkTextbox(right, fg_color=BG, text_color=TEXT, font=("Consolas", 12),
                                  corner_radius=10, border_width=1, border_color="#1b2a47")
        self.log.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        self.log.configure(state="disabled")

    def _speed_changed(self, v):
        self.speed_lbl.configure(text=f"SPEED  {v:.2f}x")

    def _set_status(self, text, color):
        self.status.configure(text=f"● {text}", text_color=color)

    def _log(self, ev):
        self.log.configure(state="normal")
        self.log.insert("end", label(ev) + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")
        self.count.configure(text=f"{len(self.events)} events")

    def _refresh_log(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.insert("end", "\n".join(label(e) for e in self.events) + ("\n" if self.events else ""))
        self.log.configure(state="disabled")
        self.count.configure(text=f"{len(self.events)} events")

    # ---------- Recording ----------
    def toggle_record(self):
        self.stop_record() if self.recording else self.start_record()

    def start_record(self):
        if self.playing:
            return
        self.events = []
        self._refresh_log()
        self.t_last = self.t_last_move = time.perf_counter()
        self.recording = True
        self.m_listener = mouse.Listener(on_move=self._on_move, on_click=self._on_click, on_scroll=self._on_scroll)
        self.k_listener = keyboard.Listener(on_press=lambda k: self._on_key(k, True),
                                            on_release=lambda k: self._on_key(k, False))
        self.m_listener.start()
        self.k_listener.start()
        self.b_rec.configure(text="■  Stop recording   [F6]")
        self._set_status("RECORDING", RED)

    def stop_record(self):
        self.recording = False
        for l in (self.m_listener, self.k_listener):
            if l:
                l.stop()
        self.b_rec.configure(text="●  Record   [F6]")
        self._set_status(f"IDLE  ({len(self.events)} events)", MUTED)

    def _add(self, ev):
        if not self.recording:
            return
        now = time.perf_counter()
        ev["dt"] = round(now - self.t_last, 4)
        self.t_last = now
        self.events.append(ev)
        self.after(0, self._log, ev)

    def _on_move(self, x, y):
        if time.perf_counter() - self.t_last_move < MOVE_THROTTLE:
            return
        self.t_last_move = time.perf_counter()
        self._add({"type": "move", "x": x, "y": y})

    def _on_click(self, x, y, button, pressed):
        self._add({"type": "click", "x": x, "y": y, "button": button.name, "pressed": pressed})

    def _on_scroll(self, x, y, dx, dy):
        self._add({"type": "scroll", "x": x, "y": y, "dx": dx, "dy": dy})

    def _on_key(self, key, pressed):
        if key in HOTKEYS:
            return
        self._add({"type": "key", "key": enc_key(key), "pressed": pressed})

    # ---------- Playback ----------
    def toggle_play(self):
        self.stop_all() if self.playing else self.start_play()

    def start_play(self):
        if self.recording:
            self.stop_record()
        if not self.events:
            self._set_status("NOTHING TO PLAY", MUTED)
            return
        try:
            repeat = max(0, int(self.repeat.get()))
        except ValueError:
            repeat = 1
        self.stop_flag.clear()
        self.playing = True
        self.b_play.configure(text="■  Stop playback   [F7]")
        self._set_status("PLAYING", GREEN)
        threading.Thread(target=self._run, args=(repeat, float(self.speed.get())), daemon=True).start()

    def _run(self, repeat, speed):
        mc, kc = mouse.Controller(), keyboard.Controller()
        held_keys, held_btns = set(), set()
        if self.stop_flag.wait(0.5):  # short grace period to switch windows
            repeat = -1
        n = 0
        try:
            while not self.stop_flag.is_set() and (repeat == 0 or n < repeat):
                for ev in self.events:
                    if self.stop_flag.wait(ev["dt"] / speed):
                        return
                    t = ev["type"]
                    if t == "move":
                        mc.position = (ev["x"], ev["y"])
                    elif t == "click":
                        mc.position = (ev["x"], ev["y"])
                        b = mouse.Button[ev["button"]]
                        if ev["pressed"]:
                            mc.press(b); held_btns.add(b)
                        else:
                            mc.release(b); held_btns.discard(b)
                    elif t == "scroll":
                        mc.position = (ev["x"], ev["y"])
                        mc.scroll(ev["dx"], ev["dy"])
                    else:
                        k = dec_key(ev["key"])
                        if ev["pressed"]:
                            kc.press(k); held_keys.add(k)
                        else:
                            kc.release(k); held_keys.discard(k)
                n += 1
        finally:
            for b in held_btns:
                mc.release(b)
            for k in held_keys:
                kc.release(k)
            self.after(0, self._play_done)

    def _play_done(self):
        self.playing = False
        self.b_play.configure(text="▶  Play   [F7]")
        self._set_status("IDLE", MUTED)

    def stop_all(self):
        if self.recording:
            self.stop_record()
        self.stop_flag.set()
        self._spam_set(False)

    # ---------- Auto clicker / key presser ----------
    def _build_clicker(self, parent):
        card = ctk.CTkFrame(parent, fg_color=CARD, corner_radius=14)
        card.pack(fill="both", expand=True, padx=6, pady=6)

        def sec(text):
            ctk.CTkLabel(card, text=text, text_color=BLUE, font=("Segoe UI Semibold", 12)).pack(anchor="w", padx=24, pady=(16, 4))

        sec("ACTION")
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=24)
        self.act_menu = ctk.CTkOptionMenu(row, values=["Keyboard key", "Left click", "Right click"], width=150,
                                          fg_color=BG, button_color=BLUE, button_hover_color=BLUE_H,
                                          command=self._action_changed)
        self.act_menu.pack(side="left")
        self.key_btn = ctk.CTkButton(row, text="", height=34, fg_color="#1b2a47", hover_color="#24375c",
                                     command=lambda: self._start_capture("target"))
        self.key_btn.pack(side="left", padx=12)

        sec("CLICKS PER SECOND   (1 - 2000)")
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=24)
        self.cps_slider = ctk.CTkSlider(row, from_=1, to=2000, number_of_steps=1999, progress_color=BLUE,
                                        button_color=BLUE, button_hover_color=BLUE_H, command=self._cps_slider)
        self.cps_slider.set(self.cps)
        self.cps_slider.pack(side="left", fill="x", expand=True)
        self.cps_entry = ctk.CTkEntry(row, width=70, fg_color=BG, border_color=BLUE, justify="center")
        self.cps_entry.insert(0, str(self.cps))
        self.cps_entry.pack(side="left", padx=(14, 0))
        self.cps_entry.bind("<Return>", self._cps_entry)
        self.cps_entry.bind("<FocusOut>", self._cps_entry)

        sec("ACTIVATION")
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=24)
        self.bind_btn = ctk.CTkButton(row, text="", height=34, fg_color="#1b2a47", hover_color="#24375c",
                                      command=lambda: self._start_capture("bind"))
        self.bind_btn.pack(side="left")
        self.mode_btn = ctk.CTkSegmentedButton(row, values=["Toggle", "Hold", "Once"], command=self._mode_changed,
                                               selected_color=BLUE, selected_hover_color=BLUE_H,
                                               unselected_color=BG, fg_color=BG)
        self.mode_btn.set(self.mode)
        self.mode_btn.pack(side="left", padx=12)
        ctk.CTkSwitch(row, text="Armed", progress_color=BLUE, command=self._armed_changed,
                      onvalue=True, offvalue=False).pack(side="left", padx=8)
        self.armed_sw = row.winfo_children()[-1]
        self.armed_sw.select()

        self.cl_status = ctk.CTkLabel(card, text="", font=("Segoe UI Semibold", 16), text_color=MUTED)
        self.cl_status.pack(anchor="w", padx=24, pady=(22, 2))
        self.cl_hint = ctk.CTkLabel(card, text="", text_color=MUTED, justify="left", wraplength=700)
        self.cl_hint.pack(anchor="w", padx=24)
        self._refresh_clicker()

    def _refresh_clicker(self, hint=None):
        self.key_btn.configure(text=f"Key to press:  {key_name(self.target)}   (click to record)",
                               state="normal" if self.action == "Keyboard key" else "disabled")
        self.bind_btn.configure(text=f"Activation:  {key_name(self.bind)}   (click to change)")
        if self.spamming:
            self.cl_status.configure(text=f"● ACTIVE  @ {self.cps} per second", text_color=GREEN)
        else:
            self.cl_status.configure(text=f"● READY  -  press {key_name(self.bind)} ({self.mode.lower()})"
                                     if self.armed else "● DISARMED", text_color=MUTED)
        modes = {"Toggle": "press once to start, press again to stop",
                 "Hold": "runs only while you hold the activation key",
                 "Once": "one single press/click each time you hit the activation key"}
        self.cl_hint.configure(text=hint or f"{self.mode}: {modes[self.mode]}.  F8 always stops everything. "
                               "Real speed depends on your PC and the app/game receiving the input.")

    def _action_changed(self, v):
        self.action = v
        self._refresh_clicker()

    def _mode_changed(self, v):
        self._spam_set(False)
        self.mode = v
        self._refresh_clicker()

    def _armed_changed(self):
        self.armed = bool(self.armed_sw.get())
        if not self.armed:
            self._spam_set(False)
        self._refresh_clicker()

    def _cps_slider(self, v):
        self.cps = int(round(v))
        self.cps_entry.delete(0, "end")
        self.cps_entry.insert(0, str(self.cps))
        self._refresh_clicker()

    def _cps_entry(self, _=None):
        try:
            v = int(self.cps_entry.get())
        except ValueError:
            v = self.cps
        self.cps = max(1, min(2000, v))
        self.cps_slider.set(self.cps)
        self.cps_entry.delete(0, "end")
        self.cps_entry.insert(0, str(self.cps))
        self._refresh_clicker()

    def _start_capture(self, kind):
        self._spam_set(False)
        self.capturing = kind
        if kind == "target":
            self.key_btn.configure(text="Press any key...   (Esc to cancel)")
        else:
            self.bind_btn.configure(text="Press a key or mouse button...   (Esc to cancel)")

    def _cap_done(self, kind, e):
        hint = None
        if e is not None:
            other = self.bind if kind == "target" else self.target
            if "s" in e and e["s"] in RESERVED:
                hint = "F6, F7 and F8 are reserved for the recorder. Pick another key."
            elif e.get("m") in ("left", "right"):
                hint = ("Left and right click can't be the activation button, they'd fire on every normal click. "
                        "Use the middle button or a side button (Mouse 4/5).")
            elif kid(e) == kid(other):
                hint = "The activation key and the key to press can't be the same."
            elif kind == "target":
                self.target = e
            else:
                self.bind = e
        self._refresh_clicker(hint)

    # activation (shared by keyboard keys and mouse buttons)
    def _bind_press(self):
        if self.bind_down:
            return
        self.bind_down = True
        if self.mode == "Toggle":
            self._spam_set(not self.spamming)
        elif self.mode == "Hold":
            self._spam_set(True)
        else:
            self._tap()

    def _bind_release(self):
        self.bind_down = False
        if self.mode == "Hold":
            self._spam_set(False)

    def _gp(self, key):  # global key press
        e = enc_key(key)
        if self.capturing:
            kind, self.capturing = self.capturing, None
            self.after(0, self._cap_done, kind, None if e.get("s") == "esc" else e)
            return
        if self.armed and kid(e) == kid(self.bind):
            self._bind_press()

    def _gr(self, key):  # global key release
        if kid(enc_key(key)) == kid(self.bind):
            self._bind_release()

    def _gc(self, x, y, button, pressed):  # global mouse click
        name = button.name
        if self.capturing == "bind":
            if pressed:  # ignore the release of the click that opened the capture
                self.capturing = None
                self.after(0, self._cap_done, "bind", {"m": name})
            return
        if self.capturing or not self.armed or self.bind.get("m") != name:
            return
        self._bind_press() if pressed else self._bind_release()

    def _m_filter(self, msg, data):
        """Windows: swallow the bound middle/side button so it doesn't also go back/forward in apps."""
        suppress = False
        try:
            if self.armed and not self.capturing and "m" in self.bind:
                name = None
                if msg in (0x20B, 0x20C):  # WM_XBUTTONDOWN / UP
                    name = {1: "x1", 2: "x2"}.get((data.mouseData >> 16) & 0xFFFF)
                elif msg in (0x207, 0x208):  # WM_MBUTTONDOWN / UP
                    name = "middle"
                if name and name == self.bind["m"]:
                    self._bind_press() if msg in (0x20B, 0x207) else self._bind_release()
                    suppress = True
        except Exception:
            pass
        if suppress:
            self.m_all.suppress_event()
        return True

    def _tap(self):
        if self.action == "Keyboard key":
            k = dec_key(self.target)
            self.kc.press(k)
            self.kc.release(k)
        else:
            self.mc.click(mouse.Button.left if self.action == "Left click" else mouse.Button.right)

    def _spam_set(self, on):
        if on and not self.spamming:
            self.spam_stop = threading.Event()
            self.spamming = True
            threading.Thread(target=self._spam_loop, args=(self.spam_stop,), daemon=True).start()
        elif not on and self.spamming:
            self.spam_stop.set()
            self.spamming = False
        self.after(0, self._refresh_clicker)

    def _spam_loop(self, stop):
        nxt = time.perf_counter()
        while not stop.is_set():
            now = time.perf_counter()
            if now < nxt:
                if nxt - now > 0.002 and stop.wait(nxt - now - 0.0015):
                    break
                continue
            sent = 0
            while now >= nxt and sent < 25 and not stop.is_set():  # catch up in small batches at high rates
                self._tap()
                nxt += 1.0 / self.cps
                sent += 1
                now = time.perf_counter()
            if now - nxt > 0.25:  # fell too far behind: resync instead of bursting
                nxt = now

    # ---------- Files ----------
    def save(self):
        if not self.events:
            return
        p = filedialog.asksaveasfilename(defaultextension=".klan", filetypes=[("00klan macro", "*.klan")])
        if p:
            with open(p, "w", encoding="utf-8") as f:
                json.dump({"app": APP_NAME, "version": VERSION, "events": self.events}, f)

    def load(self):
        p = filedialog.askopenfilename(filetypes=[("00klan macro", "*.klan"), ("All", "*.*")])
        if not p:
            return
        try:
            with open(p, encoding="utf-8") as f:
                self.events = json.load(f)["events"]
            self._refresh_log()
            self._set_status(f"LOADED  ({len(self.events)} events)", MUTED)
        except Exception as e:
            messagebox.showerror(APP_NAME, f"Could not load macro:\n{e}")

    def clear(self):
        self.stop_all()
        self.events = []
        self._refresh_log()

    def _close(self):
        self.stop_all()
        self.hotkeys.stop()
        self.k_all.stop()
        self.m_all.stop()
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
