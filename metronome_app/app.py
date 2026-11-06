import io
import math
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
import wave
import tkinter as tk
from tkinter import ttk

try:
    import pygame
except ImportError:
    pygame = None


APP_TITLE = "全有节拍器"
SAMPLE_RATE = 44100


def wav_bytes(samples):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(struct.pack("<%dh" % len(samples), *samples))
    return buf.getvalue()


def tick_sound(accent=False):
    duration = 0.075 if accent else 0.05
    frequency = 1550 if accent else 1050
    result = []
    for i in range(int(SAMPLE_RATE * duration)):
        t = i / SAMPLE_RATE
        env = math.exp(-48 * t)
        value = math.sin(2 * math.pi * frequency * t)
        value += 0.30 * math.sin(2 * math.pi * frequency * 2.1 * t)
        result.append(int(max(-1, min(1, value * env)) * 25000))
    return wav_bytes(result)


def drum_sound(accent=False):
    duration = 0.24 if accent else 0.15
    result = []
    seed = 0x12345
    for i in range(int(SAMPLE_RATE * duration)):
        t = i / SAMPLE_RATE
        if accent:
            freq = 105 - 65 * min(1, t / duration)
            tone = math.sin(2 * math.pi * freq * t) * math.exp(-17 * t)
            click = math.sin(2 * math.pi * 1800 * t) * math.exp(-75 * t) * 0.25
            value = tone + click
        else:
            seed = (1103515245 * seed + 12345) & 0x7FFFFFFF
            noise = (seed / 0x7FFFFFFF) * 2 - 1
            value = noise * math.exp(-30 * t) * 0.72
            value += math.sin(2 * math.pi * 210 * t) * math.exp(-24 * t) * 0.25
        result.append(int(max(-1, min(1, value)) * 28000))
    return wav_bytes(result)


class MetronomeApp:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("620x570")
        self.root.minsize(580, 540)
        self.root.configure(bg="#101522")
        self.running = False
        self.beat = 0
        self.next_beat = 0.0
        self.deadline = None
        self.after_id = None
        self.temp_dir = tempfile.mkdtemp(prefix="quanyou_metronome_")
        self.sound_paths = {}
        self.loaded_sounds = {}
        self.voice_ready = False
        self.audio_ready = False

        self.bpm = tk.IntVar(value=100)
        self.beats = tk.IntVar(value=4)
        self.volume = tk.IntVar(value=80)
        self.sound_mode = tk.StringVar(value="基础打点")
        self.timer_minutes = tk.IntVar(value=0)
        self.timer_text = tk.StringVar(value="不限时")
        self.status_text = tk.StringVar(value="准备就绪")

        self._make_sounds()
        self._init_audio()
        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(100, lambda: threading.Thread(target=self._prepare_voice, daemon=True).start())

    def _make_sounds(self):
        sounds = {
            "tick_normal": tick_sound(False),
            "tick_accent": tick_sound(True),
            "drum_normal": drum_sound(False),
            "drum_accent": drum_sound(True),
        }
        for name, data in sounds.items():
            path = os.path.join(self.temp_dir, name + ".wav")
            with open(path, "wb") as file:
                file.write(data)
            self.sound_paths[name] = path

    def _init_audio(self):
        if pygame is None:
            return
        try:
            pygame.mixer.pre_init(SAMPLE_RATE, -16, 2, 256)
            pygame.mixer.init()
            pygame.mixer.set_num_channels(32)
            for key, path in self.sound_paths.items():
                self.loaded_sounds[key] = pygame.mixer.Sound(path)
            self.audio_ready = True
        except Exception:
            self.audio_ready = False

    def _prepare_voice(self):
        if sys.platform != "win32":
            return
        script_path = os.path.join(self.temp_dir, "make_voice.ps1")
        script = """param([string]$Out, [string]$Text)
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$zh = $s.GetInstalledVoices() | Where-Object { $_.Enabled -and $_.VoiceInfo.Culture.Name -like 'zh-*' } | Select-Object -First 1
if ($zh) { $s.SelectVoice($zh.VoiceInfo.Name) }
$s.Rate = 3
$s.Volume = 100
$s.SetOutputToWaveFile($Out)
$s.Speak($Text)
$s.Dispose()
"""
        try:
            with open(script_path, "w", encoding="utf-8-sig") as file:
                file.write(script)
            for index, text in enumerate(("一", "二", "三", "四", "五", "六"), 1):
                path = os.path.join(self.temp_dir, f"voice_{index}.wav")
                subprocess.run(
                    ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                     "-File", script_path, "-Out", path, "-Text", text],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    timeout=15,
                )
                self.sound_paths[f"voice_{index}"] = path
                if pygame and self.audio_ready:
                    self.loaded_sounds[f"voice_{index}"] = pygame.mixer.Sound(path)
            self.voice_ready = True
            self.root.after(0, lambda: self.status_text.set("人声准备完成"))
        except Exception:
            self.root.after(0, lambda: self.status_text.set("人声不可用，鼓声和基础打点可正常使用"))

    def _build_ui(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TScale", background="#101522", troughcolor="#273147")
        style.configure("TCombobox", padding=7)
        style.configure("TSpinbox", padding=7)

        tk.Label(self.root, text=APP_TITLE, bg="#101522", fg="white",
                 font=("Microsoft YaHei UI", 24, "bold")).pack(pady=(22, 3))
        tk.Label(self.root, text="刘全有大官人出品", bg="#101522", fg="#8692a8",
                 font=("Microsoft YaHei UI", 10)).pack()

        self.bpm_label = tk.Label(self.root, text="100 BPM", bg="#101522", fg="#63a3ff",
                                  font=("Microsoft YaHei UI", 30, "bold"))
        self.bpm_label.pack(pady=(16, 2))

        dots = tk.Frame(self.root, bg="#101522")
        dots.pack(pady=12)
        self.dot_canvases = []
        for _ in range(4):
            canvas = tk.Canvas(dots, width=64, height=64, bg="#101522", highlightthickness=0)
            canvas.create_oval(9, 9, 55, 55, fill="#263148", outline="#3d4a66", width=2, tags="dot")
            canvas.pack(side="left", padx=10)
            self.dot_canvases.append(canvas)

        controls = tk.Frame(self.root, bg="#1b2333", padx=20, pady=18)
        controls.pack(fill="x", padx=28)

        self._row_label(controls, "速度")
        bpm_scale = ttk.Scale(controls, from_=40, to=240, variable=self.bpm,
                              command=self._bpm_changed)
        bpm_scale.pack(fill="x", pady=(2, 12))

        grid = tk.Frame(controls, bg="#1b2333")
        grid.pack(fill="x")
        self._compact_control(grid, "声音", ttk.Combobox, self.sound_mode,
                              values=("鼓声", "人声", "基础打点"), state="readonly")
        self._compact_control(grid, "拍子", ttk.Spinbox, self.beats,
                              from_=2, to=4, width=8, command=self._beats_changed)
        self._compact_control(grid, "倒计时（分钟）", ttk.Spinbox, self.timer_minutes,
                              from_=0, to=180, width=10)

        self._row_label(controls, "音量")
        ttk.Scale(controls, from_=10, to=100, variable=self.volume).pack(fill="x", pady=(2, 0))

        tk.Label(self.root, textvariable=self.timer_text, bg="#101522", fg="white",
                 font=("Microsoft YaHei UI", 22, "bold")).pack(pady=(15, 8))

        buttons = tk.Frame(self.root, bg="#101522")
        buttons.pack()
        self.start_button = tk.Button(buttons, text="▶ 开始", command=self.toggle,
                                      bg="#4f8ff7", fg="white", activebackground="#3978dc",
                                      relief="flat", padx=34, pady=10,
                                      font=("Microsoft YaHei UI", 13, "bold"))
        self.start_button.pack(side="left", padx=6)
        tk.Button(buttons, text="归零", command=self.reset, bg="#2a3448", fg="white",
                  activebackground="#3b4962", relief="flat", padx=25, pady=10,
                  font=("Microsoft YaHei UI", 13)).pack(side="left", padx=6)

        tk.Label(self.root, textvariable=self.status_text, bg="#101522", fg="#98a5bb",
                 font=("Microsoft YaHei UI", 10)).pack(pady=10)

    def _row_label(self, parent, text):
        tk.Label(parent, text=text, bg="#1b2333", fg="#cbd3e2",
                 font=("Microsoft YaHei UI", 10)).pack(anchor="w")

    def _compact_control(self, parent, title, widget_type, variable, **kwargs):
        box = tk.Frame(parent, bg="#1b2333")
        box.pack(side="left", expand=True, fill="x", padx=5)
        tk.Label(box, text=title, bg="#1b2333", fg="#cbd3e2",
                 font=("Microsoft YaHei UI", 10)).pack(anchor="w")
        widget = widget_type(box, textvariable=variable, **kwargs)
        widget.pack(fill="x", pady=(3, 13))
        if title == "拍子":
            widget.bind("<KeyRelease>", lambda _event: self._beats_changed())

    def _bpm_changed(self, _value=None):
        self.bpm.set(round(self.bpm.get()))
        self.bpm_label.config(text=f"{self.bpm.get()} BPM")

    def _beats_changed(self):
        try:
            count = max(2, min(4, int(self.beats.get())))
        except (ValueError, tk.TclError):
            count = 4
        self.beats.set(count)
        self.beat %= count
        self._show_beat(-1)

    def toggle(self):
        if self.running:
            self.stop("已暂停")
        else:
            self.start()

    def start(self):
        if not self.audio_ready:
            self.status_text.set("音频设备无法打开，请检查 Windows 输出设备")
            return
        if self.sound_mode.get() == "人声" and not self.voice_ready:
            self.status_text.set("人声正在准备，请稍后再试")
            return
        self._beats_changed()
        self.running = True
        self.beat = 0
        self.next_beat = time.monotonic()
        minutes = max(0, int(self.timer_minutes.get()))
        self.deadline = time.monotonic() + minutes * 60 if minutes else None
        self.start_button.config(text="■ 停止", bg="#e25b63")
        self.status_text.set("播放中")
        self._schedule()

    def stop(self, message="已停止"):
        self.running = False
        if self.after_id:
            self.root.after_cancel(self.after_id)
            self.after_id = None
        if pygame and self.audio_ready:
            pygame.mixer.stop()
        self.start_button.config(text="▶ 开始", bg="#4f8ff7")
        self.status_text.set(message)
        self._show_beat(-1)

    def reset(self):
        self.stop("已归零")
        self.deadline = None
        self.timer_text.set("不限时" if self.timer_minutes.get() == 0 else f"{self.timer_minutes.get():02d}:00")

    def _schedule(self):
        if not self.running:
            return
        now = time.monotonic()
        if self.deadline is not None:
            remaining = self.deadline - now
            if remaining <= 0:
                self.timer_text.set("00:00")
                self.stop("倒计时结束，节拍器已自动停止")
                return
            seconds = math.ceil(remaining)
            self.timer_text.set(f"{seconds // 60:02d}:{seconds % 60:02d}")
        else:
            self.timer_text.set("不限时")

        if now + 0.004 >= self.next_beat:
            count = self.beats.get()
            current = self.beat % count
            self._show_beat(current)
            self._play(current)
            self.beat = (current + 1) % count
            interval = 60.0 / max(40, self.bpm.get())
            self.next_beat += interval
            if self.next_beat < now:
                self.next_beat = now + interval
        delay = max(5, min(25, int((self.next_beat - time.monotonic()) * 1000)))
        self.after_id = self.root.after(delay, self._schedule)

    def _show_beat(self, active):
        count = self.beats.get()
        for index, canvas in enumerate(self.dot_canvases):
            if index >= count:
                fill, outline = "#151b29", "#20293b"
            elif index == active:
                fill = "#ffb43c" if index == 0 else "#58d68d"
                outline = "#ffe0a3" if index == 0 else "#b7f5d1"
            else:
                fill, outline = "#263148", "#3d4a66"
            canvas.itemconfig("dot", fill=fill, outline=outline)

    def _play(self, beat):
        if not self.audio_ready:
            return
        mode = self.sound_mode.get()
        if mode == "人声":
            key = f"voice_{beat + 1}"
        elif mode == "鼓声":
            key = "drum_accent" if beat == 0 else "drum_normal"
        else:
            key = "tick_accent" if beat == 0 else "tick_normal"
        sound = self.loaded_sounds.get(key)
        if sound:
            sound.set_volume(max(0.0, min(1.0, self.volume.get() / 100)))
            sound.play()

    def close(self):
        self.stop()
        if pygame and self.audio_ready:
            pygame.mixer.quit()
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        self.root.destroy()


def self_test():
    assert len(tick_sound(False)) > 100
    assert len(drum_sound(True)) > 100
    print("metronome self-test passed")


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        self_test()
    else:
        root = tk.Tk()
        MetronomeApp(root)
        root.mainloop()
