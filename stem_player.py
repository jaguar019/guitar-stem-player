#!/usr/bin/env python3
"""Local MP3 stem player. Demucs six-stem model; guitar role split is an estimate."""
import json
import os
import shutil
import subprocess
import sys
import threading
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse, unquote

ROOT = Path.home() / 'Music' / '吉他分轨播放器'
ROOT.mkdir(parents=True, exist_ok=True)
JOBS = {}
LOCK = threading.Lock()
HTML = r'''<!doctype html><html lang="zh"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>吉他分轨播放器</title>
<style>body{margin:0;background:#121621;color:#f0f3fa;font:16px system-ui,'Microsoft YaHei';}main{max-width:1040px;margin:35px auto;padding:22px}h1{font-size:28px}p,small{color:#aeb9c9}.card{background:#202736;border:1px solid #394153;border-radius:14px;padding:20px;margin:14px 0}button,label.pick{cursor:pointer;border:0;border-radius:9px;padding:10px 15px;background:#5688ed;color:white;font:inherit}button:disabled{opacity:.45}input[type=file]{display:none}.row{display:grid;grid-template-columns:125px 65px 65px 1fr;align-items:center;gap:12px;margin:12px 0}.row canvas{width:100%;height:48px;background:#151b27;border-radius:6px}button.mute{background:#38445a}button.mute.off{background:#df745d}button.solo{background:#38445a}button.solo.on{background:#82a745;color:#111}.controls{display:flex;align-items:center;gap:15px;flex-wrap:wrap}.note{font-size:13px}#status{white-space:pre-wrap}</style>
<main><h1>吉他分轨播放器</h1><p>导入 MP3 → 一键分轨 → 点「静音」关掉任一轨；点「独听」只听这一轨。</p>
<div class="card"><label class="pick">选择 MP3 / WAV<input id="file" type="file" accept=".mp3,.wav,.flac,audio/*"></label> <span id="filename">尚未选择歌曲</span> <button id="run" disabled>一键分轨</button><p id="status"></p></div>
<div class="card"><div class="controls"><button id="play" disabled>▶ 播放</button><input id="seek" type="range" min="0" max="1000" value="0" style="flex:1;min-width:180px"><span id="clock">0:00 / 0:00</span><button id="download" disabled>打开导出文件夹</button></div><div id="tracks"></div></div>
<p class="note">鼓、贝斯、人声、吉他总轨来自 AI 模型。主音／节奏吉他是依据吉他轨持续音与拨弦瞬态做的粗略估计，同一时间叠录的两把琴可能无法准确分开；想准确还原，请使用原始分轨。首次使用需联网下载模型，CPU 处理可能较慢。试听使用主音与节奏候选轨，吉他总轨仅用于核对，不会重复叠加。</p></main>
<script>
let job='',audios=[],rows=[],duration=0,playing=false,solo=-1;
const $=id=>document.getElementById(id);const names=['人声','鼓','贝斯','主音吉他（估计）','节奏吉他（估计）','其他乐器','钢琴','吉他总轨（核对）'];
$('file').onchange=()=>{$('filename').textContent=$('file').files[0]?.name||'尚未选择歌曲';$('run').disabled=!$('file').files.length};
$('run').onclick=async()=>{let file=$('file').files[0];if(!file)return;stop();$('run').disabled=true;$('status').textContent='上传中…';try{let r=await fetch('/upload?name='+encodeURIComponent(file.name),{method:'POST',body:file});if(!r.ok)throw Error(await r.text());job=(await r.json()).id;poll()}catch(e){$('status').textContent=e.message;$('run').disabled=false}};
async function poll(){let r=await fetch('/status?id='+job),s=await r.json();$('status').textContent=s.message;if(s.state==='done'){setup();$('run').disabled=false}else if(s.state==='error'){$('run').disabled=false}else setTimeout(poll,1200)}
function stop(){for(let a of audios){a.pause();a.src=''}audios=[];rows=[];playing=false;$('play').textContent='▶ 播放';$('play').disabled=true;$('tracks').innerHTML=''}
function fmt(t){if(!isFinite(t))t=0;return Math.floor(t/60)+':'+String(Math.floor(t%60)).padStart(2,'0')}
function sync(){audios.forEach((a,i)=>{a.muted=solo>=0?i!==solo:(i===7||rows[i].muted)});rows.forEach((r,i)=>{r.m.classList.toggle('off',r.muted);r.s.classList.toggle('on',i===solo);r.m.textContent=r.muted?'已静音':'静音'})}
async function setup(){stop();solo=-1;for(let i=0;i<names.length;i++){let div=document.createElement('div');div.className='row';div.innerHTML='<strong></strong><button class="mute">静音</button><button class="solo">独听</button><canvas width="600" height="48"></canvas>';div.querySelector('strong').textContent=names[i];$('tracks').append(div);let a=new Audio('/audio?id='+job+'&stem='+i);a.preload='metadata';audios.push(a);let r={muted:false,m:div.querySelector('.mute'),s:div.querySelector('.solo')};rows.push(r);r.m.onclick=()=>{r.muted=!r.muted;solo=-1;sync()};r.s.onclick=()=>{solo=solo===i?-1:i;sync()};let peaks=await (await fetch('/peaks?id='+job+'&stem='+i)).json();let c=div.querySelector('canvas'),x=c.getContext('2d');x.fillStyle=i===7?'#8a91a0':'#72adf1';peaks.forEach((v,j)=>{let h=Math.max(1,v*46);x.fillRect(j*c.width/peaks.length,(48-h)/2,Math.max(1,c.width/peaks.length),h)});c.onclick=e=>{let t=e.offsetX/c.getBoundingClientRect().width*duration;audios.forEach(a=>a.currentTime=t)}}duration=await new Promise(resolve=>{let a=audios[0];if(a.readyState>=1)resolve(a.duration);else a.onloadedmetadata=()=>resolve(a.duration)});sync();$('play').disabled=false;$('download').disabled=false;$('clock').textContent='0:00 / '+fmt(duration)}
$('play').onclick=async()=>{if(playing){audios.forEach(a=>a.pause());playing=false;$('play').textContent='▶ 播放'}else{let t=audios[0].currentTime;await Promise.all(audios.map(async a=>{if(Math.abs(a.currentTime-t)>.08)a.currentTime=t;try{await a.play()}catch(e){}}));playing=true;$('play').textContent='⏸ 暂停'}};
$('seek').oninput=()=>{let t=duration*Number($('seek').value)/1000;audios.forEach(a=>a.currentTime=t)};
$('download').onclick=()=>{location.href='/download?id='+job};
setInterval(()=>{if(audios.length){let t=audios[0].currentTime;$('clock').textContent=fmt(t)+' / '+fmt(duration);$('seek').value=duration?Math.round(t/duration*1000):0;if(playing&&t>=duration-.05){playing=false;$('play').textContent='▶ 播放'}}},250);
</script></html>'''


def guitar_candidates(path, lead, rhythm):
    import numpy as np
    from scipy.io import wavfile
    from scipy.signal import stft, istft
    from scipy.ndimage import median_filter
    rate, audio = wavfile.read(path)
    dtype = audio.dtype
    scale = 32768 if dtype == np.int16 else 1
    audio = audio.astype(np.float32) / scale
    if audio.ndim == 1: audio = audio[:, None]
    outputs = [[], []]
    for ch in range(audio.shape[1]):
        _, _, z = stft(audio[:, ch], fs=rate, nperseg=2048, noverlap=1536)
        mag = np.abs(z)
        sustained = median_filter(mag, size=(1, 17))
        attacks = median_filter(mag, size=(17, 1))
        mask = sustained ** 2 / (sustained ** 2 + attacks ** 2 + 1e-12)
        _, a = istft(z * mask, fs=rate, nperseg=2048, noverlap=1536)
        _, b = istft(z * (1-mask), fs=rate, nperseg=2048, noverlap=1536)
        outputs[0].append(a[:len(audio)])
        outputs[1].append(b[:len(audio)])
    for dest, channels in zip((lead, rhythm), outputs):
        data = np.stack(channels, axis=1)
        if dtype == np.int16: data = (np.clip(data, -1, 1) * 32767).astype(np.int16)
        wavfile.write(dest, rate, data)


def worker_env():
    env = os.environ.copy()
    if getattr(sys, 'frozen', False):
        env['PATH'] = str(getattr(sys, '_MEIPASS', Path(sys.executable).parent)) + os.pathsep + env.get('PATH', '')
    return env

def process(jid, path):
    job = JOBS[jid]; out = Path(job['dir'])
    try:
        job['message'] = 'AI 分轨中；首次运行会下载模型，请稍候…'
        cmd = ([sys.executable, '--worker-demucs'] if getattr(sys, 'frozen', False) else [sys.executable, '-m', 'demucs']) + ['-n','htdemucs_6s','--out',str(out / 'model'),str(path)]
        with (out / '分轨日志.txt').open('w', encoding='utf-8', errors='replace') as log:
            result = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, env=worker_env())
        if result.returncode:
            details = (out / '分轨日志.txt').read_text(encoding='utf-8', errors='replace')[-2500:]
            raise RuntimeError(f'模型退出码 {result.returncode}。错误详情：\n{details or "无日志输出"}')
        base = out / 'model' / 'htdemucs_6s' / path.stem
        for stem in ('vocals','drums','bass','other','piano','guitar'):
            if not (base / (stem+'.wav')).exists(): raise RuntimeError('模型未生成 '+stem)
        job['message']='正在生成主音／节奏吉他候选轨…'
        guitar_candidates(base/'guitar.wav',out/'主音吉他_估计.wav',out/'节奏吉他_估计.wav')
        files=['vocals.wav','drums.wav','bass.wav','主音吉他_估计.wav','节奏吉他_估计.wav','other.wav','piano.wav','guitar.wav']
        job['files']=[str((base/f) if f.endswith('.wav') and f in ('vocals.wav','drums.wav','bass.wav','other.wav','piano.wav','guitar.wav') else (out/f)) for f in files]
        job['state']='done';job['message']='分轨完成。点播放试听，点静音屏蔽轨道。'
    except Exception as exc: job['state']='error';job['message']=f'分轨失败：{exc}。请确认 Python 依赖和 FFmpeg 已安装。'


def peaks(path):
    import numpy as np
    from scipy.io import wavfile
    from scipy.signal import resample_poly
    rate, data=wavfile.read(path, mmap=True)
    n=len(data); block=max(1,n//300)
    values=[]
    for p in range(0,n,block):
        x=np.asarray(data[p:p+block],dtype=np.float32)
        values.append(float(np.max(np.abs(x))) if x.size else 0)
    top=max(values) or 1
    return [round(v/top,3) for v in values]

class Handler(BaseHTTPRequestHandler):
    def send(self, body, content='application/json', code=200, attachment=None):
        body=body if isinstance(body,bytes) else body.encode()
        self.send_response(code);self.send_header('Content-Type',content);self.send_header('Content-Length',str(len(body)))
        if attachment:self.send_header('Content-Disposition','attachment; filename="'+attachment+'"')
        self.end_headers();self.wfile.write(body)
    def do_POST(self):
        q=urlparse(self.path);name=Path(unquote(parse_qs(q.query).get('name',[''])[0])).name
        if q.path!='/upload' or Path(name).suffix.lower() not in ('.mp3','.wav','.flac'):
            return self.send('请选择 MP3、WAV 或 FLAC',code=400)
        length=int(self.headers.get('Content-Length','0'))
        if length<1 or length>300*1024*1024:return self.send('文件大小需在 300 MB 内',code=400)
        jid=uuid.uuid4().hex;out=ROOT/jid;out.mkdir();path=out/name
        with path.open('wb') as f:
            remaining=length
            while remaining:
                chunk=self.rfile.read(min(1024*1024,remaining))
                if not chunk:break
                f.write(chunk);remaining-=len(chunk)
        if remaining:return self.send('上传不完整',code=400)
        JOBS[jid]={'state':'working','message':'准备处理…','dir':str(out)}
        threading.Thread(target=process,args=(jid,path),daemon=True).start()
        self.send(json.dumps({'id':jid}))
    def do_GET(self):
        q=urlparse(self.path);p=parse_qs(q.query);jid=p.get('id',[''])[0]
        if q.path=='/':return self.send(HTML,'text/html; charset=utf-8')
        job=JOBS.get(jid)
        if not job:return self.send('任务不存在',code=404)
        if q.path=='/status':return self.send(json.dumps({'state':job['state'],'message':job['message']},ensure_ascii=False))
        if job['state']!='done':return self.send('尚未完成',code=409)
        if q.path=='/download':
            import zipfile, io
            b=io.BytesIO()
            labels=['人声','鼓','贝斯','主音吉他_估计','节奏吉他_估计','其他','钢琴','吉他总轨']
            with zipfile.ZipFile(b,'w',zipfile.ZIP_DEFLATED) as z:
                for name,src in zip(labels,job['files']):z.write(src,name+'.wav')
            return self.send(b.getvalue(),'application/zip',attachment='stems.zip')
        try:i=int(p.get('stem',['-1'])[0]);assert 0<=i<8
        except (ValueError,AssertionError):return self.send('轨道错误',code=400)
        src=Path(job['files'][i])
        if q.path=='/peaks':return self.send(json.dumps(peaks(src)))
        if q.path=='/audio':
            size=src.stat().st_size;start=0;end=size-1;header=self.headers.get('Range','')
            if header.startswith('bytes='):
                a,_,b=header[6:].partition('-');start=int(a or 0);end=min(int(b),end) if b else end
            if start> end:return self.send('无效范围',code=416)
            self.send_response(206 if header else 200);self.send_header('Content-Type','audio/wav');self.send_header('Accept-Ranges','bytes');self.send_header('Content-Length',str(end-start+1))
            if header:self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
            self.end_headers()
            with src.open('rb') as f:
                f.seek(start);remaining=end-start+1
                while remaining:
                    chunk=f.read(min(1024*1024,remaining))
                    if not chunk:break
                    self.wfile.write(chunk);remaining-=len(chunk)
            return
        self.send('未知请求',code=404)
    def log_message(self,*args):pass

if __name__=='__main__':
    if not getattr(sys, 'frozen', False) and sys.version_info[:2] != (3, 11):
        print('请用 Python 3.11 运行。当前版本：' + sys.version.split()[0], flush=True)
        sys.exit(2)
    if len(sys.argv)>1 and sys.argv[1]=='--worker-demucs':
        from demucs.separate import main as demucs_main
        sys.argv = ['demucs'] + sys.argv[2:]
        demucs_main()
        sys.exit(0)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    url=f'http://127.0.0.1:{server.server_port}/'
    print('在浏览器打开：',url,flush=True)
    webbrowser.open(url)
    server.serve_forever()
