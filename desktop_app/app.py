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


def write_mix(tracks, rate, destination):
    import numpy as np
    import soundfile as sf
    with sf.SoundFile(destination, 'w', samplerate=rate,
                      channels=tracks[0].shape[1], subtype='PCM_16') as output:
        for pos in range(0, len(tracks[0]), 65536):
            end = min(pos + 65536, len(tracks[0]))
            mixed = np.zeros_like(tracks[0][pos:end])
            for track in tracks:mixed += track[pos:end]
            output.write(np.clip(mixed, -1, 1))


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('吉他分轨播放器')
        self.geometry('1020x660')
        self.minsize(830, 510)
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
        self.build_ui()
        self.after(100, self.poll)
        self.protocol('WM_DELETE_WINDOW', self.close)

    def build_ui(self):
        self.configure(bg='#131925')
        top = ttk.Frame(self, padding=16)
        top.pack(fill='x')
        ttk.Label(top, text='吉他分轨播放器', font=('Microsoft YaHei UI', 19, 'bold')).pack(anchor='w')
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
        box = ttk.LabelFrame(self, text='音轨（点击波形可定位）', padding=12)
        box.pack(fill='both', expand=True, padx=16, pady=12)
        self.rows = []
        for i, name in enumerate(NAMES):
            row = ttk.Frame(box)
            row.pack(fill='x', pady=4)
            ttk.Label(row, text=name, width=20).pack(side='left')
            mute = ttk.Button(row, text='静音', width=7, command=lambda j=i: self.mute(j))
            mute.pack(side='left', padx=2)
            solo = ttk.Button(row, text='独听', width=7, command=lambda j=i: self.solo_track(j))
            solo.pack(side='left', padx=2)
            canvas = tk.Canvas(row, bg='#222d42', height=48, highlightthickness=0)
            canvas.pack(side='left', fill='x', expand=True, padx=(12, 0))
            canvas.bind('<Button-1>', lambda e, j=i: self.click_wave(e, j))
            canvas.bind('<Configure>', lambda e, j=i: self.draw_wave(j))
            self.rows.append((mute, solo, canvas))
        ttk.Label(self, text='主音／节奏吉他是持续音与拨弦瞬态的估计轨，叠录时可能串音；吉他总轨默认静音以免重复播放。',
                  padding=(16, 3), wraplength=960).pack(anchor='w')

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
            h = max(1, peak*22)
            cx = x*width/points
            canvas.create_line(cx, 24-h, cx, 24+h, fill='#699fe9' if i!=7 else '#77869b')

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

    def callback(self, outdata, frames, time_info, status):
        import numpy as np
        outdata.fill(0)
        end = min(len(self.stems[0]), self.cursor + frames)
        count = end - self.cursor
        if count > 0:
            for i, track in enumerate(self.stems):
                if (self.solo < 0 and not self.muted[i]) or self.solo == i:
                    outdata[:count] += track[self.cursor:end]
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
            self.stream = sd.OutputStream(samplerate=self.rate, channels=self.stems[0].shape[1],
                                          dtype='float32', callback=self.callback, blocksize=2048)
            self.stream.start()
            self.playing = True
            self.play_button.configure(text='⏸ 暂停')
        except Exception as exc:
            messagebox.showerror('音频设备错误', str(exc))

    def stop(self):
        self.playing = False
        if self.stream:
            self.stream.stop();self.stream.close();self.stream=None
        self.play_button.configure(text='▶ 播放')

    def seek_to(self, event):
        self.dragging = False
        if self.stems:self.cursor=int(self.position.get()*self.rate)

    def export_mix(self):
        if not self.stems:return
        destination = filedialog.asksaveasfilename(
            title='导出当前伴奏', defaultextension='.wav', filetypes=[('WAV 音频', '*.wav')],
            initialfile=(self.song.stem if self.song else '歌曲') + '_当前伴奏.wav')
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
                write_mix(tracks, rate, destination)
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
        self.stop();self.destroy()


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
