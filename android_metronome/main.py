import math
import os
import time

from kivy.app import App
from kivy.clock import Clock
from kivy.core.audio import SoundLoader
from kivy.core.window import Window
from kivy.graphics import Color, Ellipse
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.slider import Slider
from kivy.uix.widget import Widget

BG = (0.063, 0.082, 0.133, 1)
CARD = (0.11, 0.145, 0.21, 1)
BLUE = (0.32, 0.56, 0.97, 1)
MUTED = (0.55, 0.62, 0.73, 1)


class BeatLights(Widget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.count = 4
        self.active = -1
        self.bind(pos=self.redraw, size=self.redraw)

    def redraw(self, *_args):
        self.canvas.clear()
        gap = min(self.width / 5, dp(82))
        radius = min(gap * 0.58, dp(47))
        center = self.center_x
        with self.canvas:
            for i in range(4):
                if i >= self.count:
                    rgba = (0.10, 0.13, 0.19, 1)
                elif i == self.active:
                    rgba = (1, 0.70, 0.24, 1) if i == 0 else (0.32, 0.83, 0.55, 1)
                else:
                    rgba = (0.18, 0.23, 0.33, 1)
                Color(*rgba)
                Ellipse(pos=(center + (i - 1.5) * gap - radius / 2, self.center_y - radius / 2),
                        size=(radius, radius))


class MetronomeApp(App):
    def build(self):
        self.title = "全有节拍器"
        Window.clearcolor = BG
        self.bpm = 100
        self.beats = 4
        self.volume = 0.8
        self.minutes = 0
        self.mode = "基础打点"
        self.running = False
        self.beat = 0
        self.next_beat = 0
        self.deadline = None
        self.sounds = {}
        self.audio_ready = False

        root = BoxLayout(orientation="vertical", padding=[dp(22), dp(25), dp(22), dp(25)], spacing=dp(16))
        root.add_widget(self.label("全有节拍器", 32, (1, 1, 1, 1), 65))
        root.add_widget(self.label("刘全有大官人出品", 14, MUTED, 32))
        self.bpm_label = self.label("100 BPM", 48, BLUE, 100)
        root.add_widget(self.bpm_label)
        self.lights = BeatLights(size_hint_y=None, height=dp(105))
        root.add_widget(self.lights)

        card = BoxLayout(orientation="vertical", padding=dp(17), spacing=dp(9))
        root.add_widget(card)
        card.add_widget(self.label("速度  40—240 BPM", 18, (1, 1, 1, 1), 30))
        self.bpm_slider = Slider(min=40, max=240, value=100, step=1)
        self.bpm_slider.bind(value=self.on_bpm)
        card.add_widget(self.bpm_slider)
        card.add_widget(self.label("声音", 18, (1, 1, 1, 1), 34))
        modes = BoxLayout(spacing=dp(8), size_hint_y=None, height=dp(52))
        for name in ("鼓声", "人声", "基础打点"):
            btn = self.button(name, lambda _b, value=name: self.set_mode(value))
            modes.add_widget(btn)
        card.add_widget(modes)
        card.add_widget(self.label("拍子", 18, (1, 1, 1, 1), 34))
        beats_row = BoxLayout(spacing=dp(9), size_hint_y=None, height=dp(52))
        for number in (2, 3, 4):
            beats_row.add_widget(self.button(f"{number}/4", lambda _b, value=number: self.set_beats(value)))
        card.add_widget(beats_row)
        card.add_widget(self.label("音量", 18, (1, 1, 1, 1), 34))
        volume_slider = Slider(min=0, max=100, value=80, step=1)
        volume_slider.bind(value=lambda _s, value: setattr(self, "volume", value / 100))
        card.add_widget(volume_slider)
        card.add_widget(self.label("倒计时（分钟，0 为不限时）", 18, (1, 1, 1, 1), 34))
        timer_row = BoxLayout(spacing=dp(10), size_hint_y=None, height=dp(54))
        timer_row.add_widget(self.button("－", lambda _b: self.adjust_timer(-1)))
        self.timer_setting = self.label("0 分钟", 23, (1, 1, 1, 1), 54)
        timer_row.add_widget(self.timer_setting)
        timer_row.add_widget(self.button("＋", lambda _b: self.adjust_timer(1)))
        card.add_widget(timer_row)

        self.timer_label = self.label("不限时", 35, (1, 1, 1, 1), 73)
        root.add_widget(self.timer_label)
        actions = BoxLayout(spacing=dp(14), size_hint_y=None, height=dp(68))
        self.start_button = self.button("▶ 开始", lambda _b: self.toggle())
        actions.add_widget(self.start_button)
        actions.add_widget(self.button("归零", lambda _b: self.reset()))
        root.add_widget(actions)
        self.status = self.label("准备就绪", 15, MUTED, 38)
        root.add_widget(self.status)
        Clock.schedule_once(self.prepare_audio, 0.2)
        Clock.schedule_interval(self.update, 0.02)
        return root

    @staticmethod
    def label(text, size, color, height):
        return Label(text=text, font_size=sp(size), color=color, size_hint_y=None,
                     height=dp(height), halign="center", valign="middle")

    @staticmethod
    def button(text, callback):
        btn = Button(text=text, font_size=sp(17), background_normal="",
                     background_color=BLUE, color=(1, 1, 1, 1))
        btn.bind(on_release=callback)
        return btn

    def prepare_audio(self, _dt=0):
        try:
            audio_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "audio")
            packaged = {
                ("tick", False): "tick.wav",
                ("tick", True): "tick_accent.wav",
                ("drum", False): "drum.wav",
                ("drum", True): "drum_accent.wav",
                ("voice", 1): "voice_1.wav",
                ("voice", 2): "voice_2.wav",
                ("voice", 3): "voice_3.wav",
                ("voice", 4): "voice_4.wav",
            }
            for key, filename in packaged.items():
                path = os.path.join(audio_dir, filename)
                if not os.path.isfile(path):
                    raise FileNotFoundError(filename)
                loaded = [SoundLoader.load(path) for _ in range(4)]
                self.sounds[key] = [sound for sound in loaded if sound]
            self.sound_index = {key: 0 for key in self.sounds}
            self.audio_ready = len(self.sounds) == len(packaged) and all(self.sounds.values())
            self.status.text = "准备就绪（全部声音已内置）" if self.audio_ready else "手机音频设备无法打开"
        except Exception as error:
            self.audio_ready = False
            self.status.text = f"音频初始化失败：{type(error).__name__}"

    def on_bpm(self, _slider, value):
        self.bpm = int(value)
        self.bpm_label.text = f"{self.bpm} BPM"

    def set_mode(self, mode):
        self.mode = mode
        self.status.text = f"当前声音：{mode}（本地内置）"

    def set_beats(self, beats):
        self.beats = beats
        self.beat %= beats
        self.lights.count = beats
        self.lights.active = -1
        self.lights.redraw()
        self.status.text = f"当前拍子：{beats}/4"

    def adjust_timer(self, step):
        self.minutes = max(0, min(180, self.minutes + step))
        self.timer_setting.text = f"{self.minutes} 分钟"
        if not self.running:
            self.timer_label.text = f"{self.minutes:02d}:00" if self.minutes else "不限时"

    def toggle(self):
        if self.running:
            self.stop("已停止")
            return
        if not self.audio_ready:
            self.status.text = "音频尚未准备完成"
            return
        self.running = True
        self.beat = 0
        self.next_beat = time.monotonic()
        self.deadline = self.next_beat + self.minutes * 60 if self.minutes else None
        self.start_button.text = "■ 停止"
        self.status.text = "播放中"
        self.update(0)

    def stop(self, message="已停止"):
        self.running = False
        self.start_button.text = "▶ 开始"
        self.status.text = message
        self.lights.active = -1
        self.lights.redraw()
        for voices in self.sounds.values():
            for sound in voices:
                if sound:
                    sound.stop()

    def reset(self):
        self.stop("已归零")
        self.timer_label.text = f"{self.minutes:02d}:00" if self.minutes else "不限时"

    def play_beat(self, beat):
        if self.mode == "人声":
            key = ("voice", beat + 1)
        else:
            key = ("drum" if self.mode == "鼓声" else "tick", beat == 0)
        if key not in self.sounds or not self.sounds[key]:
            self.status.text = "音频尚未准备完成"
            return
        index = self.sound_index[key]
        self.sound_index[key] = (index + 1) % len(self.sounds[key])
        sound = self.sounds[key][index]
        if sound:
            sound.volume = self.volume
            sound.play()

    def update(self, _dt):
        if not self.running:
            return
        now = time.monotonic()
        if self.deadline is not None:
            remaining = self.deadline - now
            if remaining <= 0:
                self.timer_label.text = "00:00"
                self.stop("倒计时结束")
                return
            seconds = math.ceil(remaining)
            self.timer_label.text = f"{seconds // 60:02d}:{seconds % 60:02d}"
        if now >= self.next_beat:
            current = self.beat % self.beats
            self.lights.active = current
            self.lights.redraw()
            self.play_beat(current)
            self.beat = (current + 1) % self.beats
            interval = 60 / self.bpm
            self.next_beat += interval
            if self.next_beat < now:
                self.next_beat = now + interval

    def on_pause(self):
        if self.running:
            self.stop("已暂停")
        return True

if __name__ == "__main__":
    MetronomeApp().run()
