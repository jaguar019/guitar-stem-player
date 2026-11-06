package com.quanyou.metronome;

import android.content.Context;
import android.media.AudioFormat;
import android.media.AudioRecord;
import android.media.MediaRecorder;
import android.os.Handler;
import android.os.Looper;
import android.os.Process;
import android.util.Log;

final class TunerEngine {
    interface Listener {
        void onPitch(PitchDetector.Result result);
        void onLevel(double level, String sourceName);
        void onError(String message);
    }

    private final Handler main = new Handler(Looper.getMainLooper());
    private final Context context;
    private final Listener listener;
    private volatile boolean running;
    private volatile int generation;
    private volatile AudioRecord recorder;

    TunerEngine(Context context, Listener listener) {
        this.context = context.getApplicationContext();
        this.listener = listener;
    }

    void start() {
        stop();
        running = true;
        final int token = ++generation;
        Thread worker = new Thread(() -> recordLoop(token), "metronome-tuner");
        worker.start();
    }

    void stop() {
        running = false;
        ++generation;
        AudioRecord old = recorder;
        recorder = null;
        if (old != null) {
            try { old.stop(); } catch (IllegalStateException ignored) {}
        }
    }

    private void recordLoop(int token) {
        try {
            Process.setThreadPriority(Process.THREAD_PRIORITY_AUDIO);
            int rate = 48000;
            int minimum = AudioRecord.getMinBufferSize(rate,
                    AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT);
            if (minimum <= 0) {
                rate = 44100;
                minimum = AudioRecord.getMinBufferSize(rate,
                        AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT);
            }
            if (minimum <= 0) throw new IllegalStateException("麦克风不支持录音格式");
            int[] sources = {MediaRecorder.AudioSource.UNPROCESSED,
                    MediaRecorder.AudioSource.VOICE_RECOGNITION, MediaRecorder.AudioSource.MIC};
            String[] names = {"原始麦克风", "语音麦克风", "普通麦克风"};
            Exception lastError = null;
            for (int index = 0; index < sources.length && running && token == generation; index++) {
                try {
                    boolean completed = captureWithSource(token, rate, minimum,
                            sources[index], names[index], index == sources.length - 1);
                    if (completed || !running || token != generation) return;
                } catch (Exception error) {
                    lastError = error;
                    Log.w("QuanyouMetronome", names[index] + "不可用，尝试下一通道", error);
                }
            }
            if (lastError != null) throw lastError;
            throw new IllegalStateException("麦克风没有返回音频，请关闭其他录音应用后重试");
        } catch (SecurityException error) {
            fail(token, "需要麦克风权限才能调音");
        } catch (Exception error) {
            Log.e("QuanyouMetronome", "调音器录音失败", error);
            fail(token, error.getMessage() == null ? "麦克风启动失败" : error.getMessage());
        }
    }

    private boolean captureWithSource(int token, int rate, int minimum, int source,
                                      String sourceName, boolean finalSource) {
        AudioRecord input = new AudioRecord(source, rate, AudioFormat.CHANNEL_IN_MONO,
                AudioFormat.ENCODING_PCM_16BIT, Math.max(minimum * 2, 8192 * 2));
        if (input.getState() != AudioRecord.STATE_INITIALIZED) {
            input.release();
            throw new IllegalStateException(sourceName + "初始化失败");
        }
        try {
            if (!running || token != generation) return true;
            recorder = input;
            input.startRecording();
            if (input.getRecordingState() != AudioRecord.RECORDSTATE_RECORDING) {
                throw new IllegalStateException(sourceName + "启动失败");
            }
            short[] samples = new short[8192];
            int filled = 0;
            int silentWindows = 0;
            while (running && token == generation) {
                int received = input.read(samples, filled, samples.length - filled,
                        AudioRecord.READ_BLOCKING);
                if (received <= 0) throw new IllegalStateException(sourceName + "读取失败：" + received);
                int peak = 0;
                double energy = 0;
                for (int i = filled; i < filled + received; i++) {
                    int value = Math.abs((int) samples[i]);
                    peak = Math.max(peak, value);
                    energy += (double) value * value;
                }
                double level = Math.min(1.0, Math.sqrt(energy / received) / 5000.0);
                main.post(() -> {
                    if (running && token == generation) listener.onLevel(level, sourceName);
                });
                if (peak <= 2) silentWindows++; else silentWindows = 0;
                if (!finalSource && silentWindows >= 6) {
                    Log.w("QuanyouMetronome", sourceName + "持续返回数字静音，自动切换");
                    return false;
                }
                filled += received;
                if (filled == samples.length) {
                    PitchDetector.Result pitch = PitchDetector.detect(samples, filled, rate);
                    main.post(() -> {
                        if (running && token == generation) listener.onPitch(pitch);
                    });
                    System.arraycopy(samples, 4096, samples, 0, 4096);
                    filled = 4096;
                }
            }
            return true;
        } finally {
            if (recorder == input) recorder = null;
            try { input.stop(); } catch (IllegalStateException ignored) {}
            input.release();
        }
    }

    private void fail(int token, String message) {
        main.post(() -> {
            if (running && token == generation) listener.onError(message);
        });
    }
}
