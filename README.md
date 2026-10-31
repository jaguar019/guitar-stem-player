# 吉他分轨播放器

Windows 原生窗口，选音频、一键分轨、查看各轨波形、统一播放进度、静音和独听。GitHub Actions 的 Windows 构建产生独立 EXE；用户不需安装 Python 或 FFmpeg。模型首次运行联网下载。

开发：`python -m pip install -r desktop_app/requirements-build.txt`，运行 `python desktop_app/app.py`。构建配置在仓库根目录 `.github/workflows/windows.yml`。

鼓、贝斯、人声、吉他总轨等由 Demucs htdemucs_6s 分离。主音和节奏吉他是从吉他总轨用持续音与瞬态粗分，可能有明显串音，不能视为录音棚原轨。

当前仅完成静态检查。必须在 Windows 10/11 的构建结果上，用一段 MP3 验证模型下载、FFmpeg 解码、播放切换和导出后才能发布。
