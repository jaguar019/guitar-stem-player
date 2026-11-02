"""Native Windows stem player. Build on Windows with PyInstaller."""
import os
import queue
import subprocess
import sys
import threading
import traceback
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

NAMES = ['人声', '鼓', '贝斯', '主音吉他（估计）', '节奏吉他（估计）', '其他乐器', '钢琴', '吉他总轨（核对）']
SOURCES = ['vocals', 'drums', 'bass', 'lead', 'rhythm', 'other', 'piano', 'guitar']


def paths():
    root = Path.home() / 'Music' / '吉他分轨播放器'
    root.mkdir(parents=True, exist_ok=True)
    return root


def engine_command(args):
    return ([sys.executable, '--demucs-worker'] if getattr(sys, 'frozen', False)
            else [sys.executable, '-m', 'demucs']) + args


def run_demucs(song, folder):
    env = os.environ.copy()
    if getattr(sys, 'frozen', False):
        env['PATH'] = str(getattr(sys, '_MEIPASS', Path(sys.executable).parent)) + os.pathsep + env.get('PATH', '')
    log = folder / '分轨日志.txt'
    with log.open('w', encoding='utf-8', errors='replace') as output:
        result = subprocess.run(engine_command(['-n', 'htdemucs_6s', '-o', str(folder), str(song)]),
                                stdout=output, stderr=subprocess.STDOUT, env=env)
    if result.returncode:
        detail = log.read_text(encoding='utf-8', errors='replace')
        engine_log = folder / 'engine-error.txt'
        if engine_log.exists(): detail += '\n' + engine_log.read_text(encoding='utf-8', errors='replace')
        raise RuntimeError(detail[-3000:] or f'模型退出码 {result.returncode}')
    base = folder / 'htdemucs_6s' / song.stem
    for item in ('vocals', 'drums', 'bass', 'guitar', 'piano', 'other'):
        if not (base / (item + '.wav')).exists():
            raise RuntimeError(f'缺少 {item}.wav；详情见 {log}')
    return base


def write_mix(tracks, rate, destination, quality='16 bit', ffmpeg_path=None):
    import numpy as np
    import soundfile as sf
    import tempfile
    destination = Path(destination)
    is_mp3 = destination.suffix.lower() == '.mp3'
    if is_mp3 and quality not in ('128 kbps', '192 kbps', '256 kbps', '320 kbps'):
        raise ValueError('无效的 MP3 品质')
    if not is_mp3 and quality not in ('16 bit', '24 bit'):
        raise ValueError('无效的 WAV 品质')
    with tempfile.TemporaryDirectory() as temp_dir:
        wav = Path(temp_dir) / 'mix.wav' if is_mp3 else destination
        subtype = 'PCM_24' if is_mp3 or quality == '24 bit' else 'PCM_16'
        with sf.SoundFile(wav, 'w', samplerate=rate,
                          channels=tracks[0].shape[1], subtype=subtype) as output:
            for pos in range(0, len(tracks[0]), 65536):
                end = min(pos + 65536, len(tracks[0]))
                mixed = np.zeros_like(tracks[0][pos:end])
                for track in tracks:mixed += track[pos:end]
                output.write(np.clip(mixed, -1, 1))
        if is_mp3:
            binary = ffmpeg_path or str(Path(getattr(sys, '_MEIPASS', Path(sys.executable).parent)) / 'ffmpeg.exe')
            result = subprocess.run([binary, '-y', '-hide_banner', '-loglevel', 'error',
                                     '-i', str(wav), '-codec:a', 'libmp3lame',
                                     '-b:a', quality.split()[0] + 'k', str(destination)],
                                    capture_output=True, text=True,
                                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            if result.returncode:
                destination.unlink(missing_ok=True)
                raise RuntimeError(result.stderr.strip() or 'MP3 编码失败')


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('吉他分轨播放器')
        self.geometry('1020x760')
        self.minsize(830, 650)
        self.song = None
        self.stems = []
        self.base = None
        self.rate = 44100
        self.cursor = 0
        self.stream = None
        self.playing = False
        self.muted = [False] * 8
        self.muted[7] = True
        self.solo = -1
        self.events = queue.Queue()
        self.busy = False
        self.dragging = False
        self.metro_enabled = False
        self.metro_stream = None
        self.metro_bpm = 100
        self.metro_beats = 4
        self.metro_volume = 0.3
        self.metro_position = 0
        self.metro_rate = 44100
        self.build_ui()
        self.after(100, self.poll)
        self.protocol('WM_DELETE_WINDOW', self.close)

    def build_ui(self):
        self.configure(bg='#131925')
        top = ttk.Frame(self, padding=16)
        top.pack(fill='x')
        ttk.Label(top, text='吉他分轨播放器', font=('Microsoft YaHei UI', 19, 'bold')).pack(anchor='w')
        ttk.Label(top, text='刘全有大官人出品').pack(anchor='w')
        line = ttk.Frame(top)
        line.pack(fill='x', pady=12)
        ttk.Button(line, text='选择 MP3 / WAV', command=self.choose).pack(side='left')
        self.file_label = ttk.Label(line, text='尚未选择歌曲')
        self.file_label.pack(side='left', padx=12)
        self.separate_button = ttk.Button(line, text='一键分轨', command=self.separate, state='disabled')
        self.separate_button.pack(side='right')
        self.status = tk.StringVar(value='等待导入歌曲')
        ttk.Label(top, textvariable=self.status, wraplength=920).pack(anchor='w')
        transport = ttk.Frame(self, padding=(16, 10))
        transport.pack(fill='x')
        self.play_button = ttk.Button(transport, text='▶ 播放', command=self.toggle, state='disabled')
        self.play_button.pack(side='left')
        self.position = tk.DoubleVar(value=0)
        self.seek = ttk.Scale(transport, from_=0, to=1, variable=self.position)
        self.seek.pack(side='left', fill='x', expand=True, padx=12)
        self.seek.bind('<ButtonPress-1>', lambda e: setattr(self, 'dragging', True))
        self.seek.bind('<ButtonRelease-1>', self.seek_to)
        self.clock = ttk.Label(transport, text='0:00 / 0:00')
        self.clock.pack(side='left')
        self.export_button = ttk.Button(transport, text='打开分轨文件夹', command=self.open_folder, state='disabled')
        self.export_button.pack(side='right', padx=(16, 0))
        self.mix_button = ttk.Button(transport, text='导出当前伴奏', command=self.export_mix, state='disabled')
        self.mix_button.pack(side='right', padx=(16, 0))
        settings = ttk.Frame(self, padding=(16, 0))
        settings.pack(fill='x')
        ttk.Label(settings, text='导出格式').pack(side='left')
        self.format_var = tk.StringVar(value='WAV')
        format_box = ttk.Combobox(settings, textvariable=self.format_var, values=['WAV', 'MP3'],
                                  width=7, state='readonly')
        format_box.pack(side='left', padx=(8, 20))
        format_box.bind('<<ComboboxSelected>>', self.format_changed)
        ttk.Label(settings, text='品质').pack(side='left')
        self.quality_var = tk.StringVar(value='16 bit')
        self.quality_box = ttk.Combobox(settings, textvariable=self.quality_var,
                                        values=['16 bit', '24 bit'], width=12, state='readonly')
        self.quality_box.pack(side='left', padx=8)
        box = ttk.LabelFrame(self, text='音轨（点击波形可定位）', padding=12)
        box.pack(fill='both', expand=True, padx=16, pady=12)
        self.rows = []
        for i, name in enumerate(NAMES):
            row = ttk.Frame(box)
            row.pack(fill='x', pady=2)
            ttk.Label(row, text=name, width=20).pack(side='left')
            mute = ttk.Button(row, text='静音', width=7, command=lambda j=i: self.mute(j))
            mute.pack(side='left', padx=2)
            solo = ttk.Button(row, text='独听', width=7, command=lambda j=i: self.solo_track(j))
            solo.pack(side='left', padx=2)
            canvas = tk.Canvas(row, bg='#222d42', height=38, highlightthickness=0)
            canvas.pack(side='left', fill='x', expand=True, padx=(12, 0))
            canvas.bind('<Button-1>', lambda e, j=i: self.click_wave(e, j))
            canvas.bind('<Configure>', lambda e, j=i: self.draw_wave(j))
            self.rows.append((mute, solo, canvas))
        ttk.Label(self, text='主音／节奏吉他是持续音与拨弦瞬态的估计轨，叠录时可能串音；吉他总轨默认静音以免重复播放。',
                  padding=(16, 3), wraplength=960).pack(anchor='w')
        metro = ttk.LabelFrame(self, text='节拍器（只在试听时播放，不写入导出音频）', padding=(12, 5))
        metro.pack(fill='x', padx=16, pady=(0, 10))
        self.metro_button = ttk.Button(metro, text='▶ 开启', command=self.toggle_metronome)
        self.metro_button.pack(side='left', padx=(0, 15))
        ttk.Label(metro, text='音量').pack(side='left')
        self.metro_volume_var = tk.DoubleVar(value=30)
        ttk.Scale(metro, from_=0, to=100, variable=self.metro_volume_var,
                  command=self.set_metro_volume, length=130).pack(side='left', padx=(5, 16))
        ttk.Label(metro, text='速度 BPM').pack(side='left')
        self.metro_bpm_var = tk.IntVar(value=100)
        bpm = ttk.Spinbox(metro, from_=40, to=240, increment=1, width=5,
                          textvariable=self.metro_bpm_var, command=self.set_metro_bpm)
        bpm.pack(side='left', padx=(5, 15))
        bpm.bind('<FocusOut>', self.set_metro_bpm)
        bpm.bind('<Return>', self.set_metro_bpm)
        ttk.Label(metro, text='拍号').pack(side='left')
        self.metro_beats_var = tk.StringVar(value='4/4')
        beats = ttk.Combobox(metro, values=['2/4', '3/4', '4/4', '6/8'],
                              textvariable=self.metro_beats_var, width=5, state='readonly')
        beats.pack(side='left', padx=5)
        beats.bind('<<ComboboxSelected>>', self.set_metro_beats)

    def choose(self):
        value = filedialog.askopenfilename(filetypes=[('音频', '*.mp3 *.wav *.flac'), ('全部文件', '*.*')])
        if value:
            self.song = Path(value)
            self.file_label.configure(text=self.song.name)
            self.separate_button.configure(state='normal')

    def separate(self):
        if self.busy or not self.song: return
        self.stop()
        self.busy = True
        self.separate_button.configure(state='disabled')
        self.status.set('正在分轨；首次运行需要联网下载模型…')
        def work():
            try:
                from stem_player import guitar_candidates
                folder = paths() / (self.song.stem + '_分轨')
                folder.mkdir(parents=True, exist_ok=True)
                base = run_demucs(self.song, folder)
                self.events.put(('status', '正在处理吉他候选轨…'))
                lead = base / '主音吉他_估计.wav'
                rhythm = base / '节奏吉他_估计.wav'
                guitar_candidates(base / 'guitar.wav', lead, rhythm)
                files = [base/'vocals.wav', base/'drums.wav', base/'bass.wav', lead, rhythm,
                         base/'other.wav', base/'piano.wav', base/'guitar.wav']
                self.events.put(('done', (folder, files)))
            except Exception:
                self.events.put(('error', traceback.format_exc()[-3500:]))
        threading.Thread(target=work, daemon=True).start()

    def load(self, data):
        import numpy as np
        import soundfile as sf
        self.base, files = data
        self.stems = []
        for f in files:
            samples, rate = sf.read(f, dtype='float32', always_2d=True)
            self.stems.append(samples)
            self.rate = rate
        if any(len(a) != len(self.stems[0]) or a.shape[1] != self.stems[0].shape[1] for a in self.stems):
            raise RuntimeError('音轨长度或声道数不一致')
        self.cursor = 0
        self.seek.configure(to=len(self.stems[0])/self.rate)
        self.play_button.configure(state='normal')
        self.export_button.configure(state='normal')
        self.mix_button.configure(state='normal')
        for i in range(8):self.draw_wave(i)
        self.update_buttons()
        self.status.set('分轨完成。选择静音或独听，然后播放。')

    def draw_wave(self, i):
        if not self.stems:return
        import numpy as np
        canvas = self.rows[i][2]
        width = canvas.winfo_width()
        if width < 5:return
        canvas.delete('all')
        arr = self.stems[i]
        points = min(width, 600)
        step = max(1, len(arr)//points)
        # Peak envelope, downsampled to keep the GUI responsive.
        for x in range(points):
            chunk = arr[x*step:min((x+1)*step,len(arr))]
            if not len(chunk):break
            peak = min(1.0, float(np.max(np.abs(chunk))))
            h = max(1, peak*17)
            cx = x*width/points
            canvas.create_line(cx, 19-h, cx, 19+h, fill='#699fe9' if i!=7 else '#77869b')

    def click_wave(self, event, i):
        if self.stems:
            self.cursor = int(event.x / max(1,self.rows[i][2].winfo_width()) * len(self.stems[0]))
            self.position.set(self.cursor / self.rate)

    def mute(self, i):
        self.solo = -1
        self.muted[i] = not self.muted[i]
        self.update_buttons()

    def solo_track(self, i):
        self.solo = -1 if self.solo == i else i
        self.update_buttons()

    def update_buttons(self):
        for i,(mute,solo,_) in enumerate(self.rows):
            mute.configure(text='已静音' if self.muted[i] else '静音')
            solo.configure(text='独听中' if self.solo==i else '独听')

    def set_metro_volume(self, value):
        self.metro_volume = float(value) / 100

    def set_metro_bpm(self, event=None):
        try:
            bpm = max(40, min(240, int(self.metro_bpm_var.get())))
        except (tk.TclError, ValueError):
            bpm = self.metro_bpm
        self.metro_bpm_var.set(bpm)
        self.metro_bpm = bpm
        self.metro_position = 0

    def set_metro_beats(self, event=None):
        self.metro_beats = int(self.metro_beats_var.get().split('/')[0])
        self.metro_position = 0

    def mix_click(self, outdata):
        import numpy as np
        if not self.metro_enabled:return
        rate = self.metro_rate
        period = max(1, round(rate * 60 / self.metro_bpm))
        start = self.metro_position
        end = start + len(outdata)
        click_length = round(rate * 0.055)
        first_beat = max(0, (start - click_length) // period)
        for beat in range(first_beat, (end - 1) // period + 1):
            beat_at = beat * period
            left = max(start, beat_at)
            right = min(end, beat_at + click_length)
            if left >= right:continue
            offset = np.arange(left - beat_at, right - beat_at)
            accent = beat % self.metro_beats == 0
            frequency = 1046 if accent else 784
            gain = self.metro_volume * (0.42 if accent else 0.29)
            wave = gain * np.sin(2 * np.pi * frequency * offset / rate) * np.exp(-85 * offset / rate)
            outdata[left-start:right-start] += wave[:, None]
        self.metro_position = end
        np.clip(outdata, -1, 1, out=outdata)

    def metronome_callback(self, outdata, frames, time_info, status):
        outdata.fill(0)
        self.mix_click(outdata)

    def start_metronome_stream(self):
        if not self.metro_enabled or self.playing or self.metro_stream:return
        import sounddevice as sd
        self.metro_rate = 44100
        self.metro_position = 0
        try:
            self.metro_stream = sd.OutputStream(samplerate=self.metro_rate, channels=2,
                                                dtype='float32', callback=self.metronome_callback,
                                                blocksize=2048)
            self.metro_stream.start()
        except Exception as exc:
            self.metro_stream = None
            self.metro_enabled = False
            self.metro_button.configure(text='▶ 开启')
            messagebox.showerror('节拍器音频设备错误', str(exc))

    def stop_metronome_stream(self):
        if self.metro_stream:
            self.metro_stream.stop()
            self.metro_stream.close()
            self.metro_stream = None

    def toggle_metronome(self):
        self.metro_enabled = not self.metro_enabled
        self.metro_button.configure(text='■ 关闭' if self.metro_enabled else '▶ 开启')
        self.metro_position = 0
        if self.metro_enabled:self.start_metronome_stream()
        else:self.stop_metronome_stream()

    def callback(self, outdata, frames, time_info, status):
        import numpy as np
        outdata.fill(0)
        end = min(len(self.stems[0]), self.cursor + frames)
        count = end - self.cursor
        if count > 0:
            for i, track in enumerate(self.stems):
                if (self.solo < 0 and not self.muted[i]) or self.solo == i:
                    outdata[:count] += track[self.cursor:end]
            self.mix_click(outdata)
            np.clip(outdata, -1, 1, out=outdata)
            self.cursor = end
        if count < frames:
            raise __import__('sounddevice').CallbackStop()

    def toggle(self):
        import sounddevice as sd
        if self.playing:
            self.stop()
            return
        if not self.stems:return
        if self.cursor >= len(self.stems[0]):self.cursor=0
        try:
            self.stop_metronome_stream()
            self.metro_rate = self.rate
            self.metro_position = 0
            self.stream = sd.OutputStream(samplerate=self.rate, channels=self.stems[0].shape[1],
                                          dtype='float32', callback=self.callback, blocksize=2048)
            self.stream.start()
            self.playing = True
            self.play_button.configure(text='⏸ 暂停')
        except Exception as exc:
            self.start_metronome_stream()
            messagebox.showerror('音频设备错误', str(exc))

    def stop(self):
        self.playing = False
        if self.stream:
            self.stream.stop();self.stream.close();self.stream=None
        self.play_button.configure(text='▶ 播放')
        self.start_metronome_stream()

    def seek_to(self, event):
        self.dragging = False
        if self.stems:self.cursor=int(self.position.get()*self.rate)

    def format_changed(self, event=None):
        choices = ['16 bit', '24 bit'] if self.format_var.get() == 'WAV' else [
            '128 kbps', '192 kbps', '256 kbps', '320 kbps']
        self.quality_box.configure(values=choices)
        self.quality_var.set(choices[-1] if self.format_var.get() == 'MP3' else choices[0])

    def export_mix(self):
        if not self.stems:return
        format_name = self.format_var.get()
        quality = self.quality_var.get()
        extension = '.mp3' if format_name == 'MP3' else '.wav'
        destination = filedialog.asksaveasfilename(
            title='导出当前伴奏', defaultextension=extension,
            filetypes=[(format_name + ' 音频', '*' + extension)],
            initialfile=(self.song.stem if self.song else '歌曲') + '_当前伴奏' + extension)
        if not destination:return
        selected = [i for i in range(len(self.stems))
                    if (self.solo == i if self.solo >= 0 else not self.muted[i])]
        if not selected:
            messagebox.showinfo('没有可导出的音轨', '当前所有音轨都已静音。')
            return
        # Snapshot the exact audible tracks; subsequent mute clicks do not change this export.
        tracks = [self.stems[i] for i in selected]
        rate = self.rate
        self.mix_button.configure(state='disabled')
        self.status.set('正在导出当前伴奏…')
        def write():
            try:
                write_mix(tracks, rate, destination, quality)
                self.events.put(('export_done', destination))
            except Exception:
                self.events.put(('export_error', traceback.format_exc()[-2000:]))
        threading.Thread(target=write, daemon=True).start()

    def poll(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == 'status':self.status.set(value)
                elif kind == 'export_done':
                    self.mix_button.configure(state='normal')
                    self.status.set('伴奏已导出：' + value)
                    messagebox.showinfo('导出完成', value)
                elif kind == 'export_error':
                    self.mix_button.configure(state='normal')
                    self.status.set('伴奏导出失败')
                    messagebox.showerror('导出失败', value)
                elif kind == 'done':
                    try:self.load(value)
                    except Exception as exc:messagebox.showerror('载入失败',str(exc));self.status.set(str(exc))
                    self.busy=False;self.separate_button.configure(state='normal')
                else:
                    self.busy=False;self.separate_button.configure(state='normal')
                    self.status.set('分轨失败，详情见弹窗和输出目录的分轨日志.txt')
                    messagebox.showerror('分轨失败', value)
        except queue.Empty:pass
        if self.stems:
            length=len(self.stems[0])/self.rate
            pos=self.cursor/self.rate
            if not self.dragging:self.position.set(pos)
            self.clock.configure(text=f'{int(pos//60)}:{int(pos%60):02d} / {int(length//60)}:{int(length%60):02d}')
            if self.playing and self.stream and not self.stream.active:self.stop()
        self.after(100,self.poll)

    def open_folder(self):
        if self.base:os.startfile(self.base)

    def close(self):
        self.metro_enabled = False
        self.stop()
        self.stop_metronome_stream()
        self.destroy()


if __name__ == '__main__':
    if len(sys.argv)>1 and sys.argv[1]=='--self-test':
        import shutil
        from demucs.separate import main as _engine
        bundled = Path(getattr(sys, '_MEIPASS', Path(sys.executable).parent)) / 'ffmpeg.exe'
        if not bundled.exists() and shutil.which('ffmpeg') is None:
            raise RuntimeError('ffmpeg.exe is missing')
        Path('smoke_result.txt').write_text('engine and ffmpeg available', encoding='utf-8')
        sys.exit(0)
    if len(sys.argv)>1 and sys.argv[1]=='--demucs-worker':
        args = sys.argv[2:]
        output_dir = Path(args[args.index('-o') + 1]) if '-o' in args else Path.cwd()
        output_dir.mkdir(parents=True, exist_ok=True)
        log = (output_dir / 'engine-error.txt').open('w', encoding='utf-8')
        if sys.stdout is None: sys.stdout = log
        if sys.stderr is None: sys.stderr = log
        try:
            from demucs.separate import main
            sys.argv=['demucs']+args
            main()
        except BaseException:
            traceback.print_exc(file=log)
            raise
    else:
        App().mainloop()
