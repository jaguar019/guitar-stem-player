package com.quanyou.metronome;

import android.content.Context;
import android.media.AudioFormat;
import android.media.AudioManager;
import android.media.AudioRecord;
import android.media.MediaRecorder;
import android.os.Handler;
import android.os.Looper;
import android.os.Process;
import android.util.Log;

final class TunerEngine {
    interface Listener {
        void onPitch(PitchDetector.Result result);
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
        AudioRecord input = null;
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
            AudioManager manager = (AudioManager) context.getSystemService(Context.AUDIO_SERVICE);
            boolean raw = manager != null && "true".equals(manager.getProperty(
                    AudioManager.PROPERTY_SUPPORT_AUDIO_SOURCE_UNPROCESSED));
            int source = raw ? MediaRecorder.AudioSource.UNPROCESSED : MediaRecorder.AudioSource.MIC;
            input = new AudioRecord(source, rate, AudioFormat.CHANNEL_IN_MONO,
                    AudioFormat.ENCODING_PCM_16BIT, Math.max(minimum * 2, 8192 * 2));
            if (input.getState() != AudioRecord.STATE_INITIALIZED) {
                input.release();
                input = new AudioRecord(MediaRecorder.AudioSource.MIC, rate,
                        AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT,
                        Math.max(minimum * 2, 8192 * 2));
            }
            if (input.getState() != AudioRecord.STATE_INITIALIZED) {
                throw new IllegalStateException("麦克风未能启动");
            }
            if (!running || token != generation) return;
            recorder = input;
            input.startRecording();
            short[] samples = new short[8192];
            int filled = 0;
            while (running && token == generation) {
                int received = input.read(samples, filled, samples.length - filled,
                        AudioRecord.READ_BLOCKING);
                if (received <= 0) {
                    if (running && token == generation) throw new IllegalStateException("麦克风读取失败：" + received);
                    break;
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
        } catch (SecurityException error) {
            fail(token, "需要麦克风权限才能调音");
        } catch (Exception error) {
            Log.e("QuanyouMetronome", "调音器录音失败", error);
            fail(token, error.getMessage() == null ? "麦克风启动失败" : error.getMessage());
        } finally {
            if (recorder == input) recorder = null;
            if (input != null) {
                try { input.stop(); } catch (IllegalStateException ignored) {}
                input.release();
            }
        }
    }

    private void fail(int token, String message) {
        main.post(() -> {
            if (running && token == generation) listener.onError(message);
        });
    }
}
