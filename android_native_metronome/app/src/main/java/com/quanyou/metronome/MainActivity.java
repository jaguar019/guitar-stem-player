package com.quanyou.metronome;

import android.Manifest;
import android.app.Activity;
import android.app.AlertDialog;
import android.content.pm.PackageManager;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.drawable.GradientDrawable;
import android.media.AudioAttributes;
import android.media.AudioManager;
import android.media.SoundPool;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.util.Log;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.SeekBar;
import android.widget.TextView;
import android.widget.Toast;

import java.util.Locale;

public class MainActivity extends Activity {
    private static final int BG = Color.rgb(16, 21, 34);
    private static final int CARD = Color.rgb(28, 37, 54);
    private static final int BLUE = Color.rgb(82, 143, 247);
    private static final int MUTED = Color.rgb(140, 158, 186);
    private static final int GREEN = Color.rgb(82, 212, 140);
    private static final int ORANGE = Color.rgb(255, 179, 61);
    private static final int MICROPHONE_REQUEST = 74;
    private static final String[] NOTES = {
            "C", "C♯", "D", "D♯", "E", "F", "F♯", "G", "G♯", "A", "A♯", "B"
    };

    private final Handler handler = new Handler(Looper.getMainLooper());
    private SoundPool soundPool;
    private int tickSound;
    private int tickAccentSound;
    private int drumSound;
    private int drumAccentSound;
    private final int[] voiceSounds = new int[4];
    private int loadedSounds;
    private int lastStreamId;
    private boolean audioSelfTest;

    private int bpm = 100;
    private int beats = 4;
    private int beat;
    private int minutes;
    private float volume = 0.8f;
    private String mode = "基础打点";
    private boolean running;
    private long nextBeatAt;
    private long finishAt;

    private float scale;
    private boolean foreground;
    private boolean tunerPageVisible;
    private PracticeHistory practice;
    private TunerEngine tuner;
    private TextView dateLabel;
    private TextView practiceLabel;
    private TextView bpmLabel;
    private TextView timerSetting;
    private TextView timerLabel;
    private TextView statusLabel;
    private Button startButton;
    private BeatView beatView;
    private Button drumButton;
    private Button voiceButton;
    private Button tickButton;
    private Button beat2Button;
    private Button beat3Button;
    private Button beat4Button;
    private Button metronomeTab;
    private Button tunerTab;
    private LinearLayout metronomePage;
    private LinearLayout tunerPage;
    private TextView tunerNote;
    private TextView tunerFrequency;
    private TextView tunerCents;
    private TextView tunerStatus;
    private TextView referenceLabel;
    private TextView targetOctaveLabel;
    private Button targetNoteButton;
    private Button automaticButton;
    private TunerMeterView tunerMeter;
    private int referenceHz = 440;
    private int targetNoteIndex = 4;
    private int targetOctave = 2;
    private boolean automatic = true;
    private double stableFrequency;
    private int missingFrames;

    private final Runnable beatRunnable = new Runnable() {
        @Override public void run() {
            if (!running) return;
            long now = SystemClock.uptimeMillis();
            if (finishAt > 0 && now >= finishAt) {
                timerLabel.setText("00:00");
                stopMetronome("倒计时结束");
                return;
            }
            playBeat(beat);
            beatView.setActive(beat);
            beat = (beat + 1) % beats;
            long interval = Math.round(60000.0 / bpm);
            nextBeatAt += interval;
            if (nextBeatAt <= now) nextBeatAt = now + interval;
            handler.postAtTime(this, nextBeatAt);
        }
    };

    private final Runnable timerRunnable = new Runnable() {
        @Override public void run() {
            if (!running) return;
            if (finishAt > 0) {
                long left = Math.max(0, finishAt - SystemClock.uptimeMillis());
                long seconds = (left + 999) / 1000;
                timerLabel.setText(String.format(Locale.CHINA, "%02d:%02d",
                        seconds / 60, seconds % 60));
            } else {
                timerLabel.setText("不限时");
            }
            handler.postDelayed(this, 200);
        }
    };

    private final Runnable practiceRunnable = new Runnable() {
        @Override public void run() {
            if (!foreground) return;
            practice.tick();
            updatePractice();
            handler.postDelayed(this, 1000);
        }
    };

    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().getDecorView().setSystemUiVisibility(
                View.SYSTEM_UI_FLAG_FULLSCREEN | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                        | View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY);
        getWindow().setStatusBarColor(BG);
        getWindow().setNavigationBarColor(BG);
        float heightDp = getResources().getDisplayMetrics().heightPixels
                / getResources().getDisplayMetrics().density;
        scale = Math.max(0.68f, Math.min(1f, heightDp / 700f));
        practice = new PracticeHistory(this);
        audioSelfTest = getIntent().getBooleanExtra("audio_self_test", false);
        tuner = new TunerEngine(this, new TunerEngine.Listener() {
            @Override public void onPitch(PitchDetector.Result result) {
                updatePitch(result);
            }
            @Override public void onError(String message) {
                tunerStatus.setText(message);
            }
        });
        buildAudio();
        setContentView(buildInterface());
    }

    private void buildAudio() {
        AudioAttributes attributes = new AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_MEDIA)
                .setContentType(AudioAttributes.CONTENT_TYPE_MUSIC).build();
        soundPool = new SoundPool.Builder().setMaxStreams(12).setAudioAttributes(attributes).build();
        soundPool.setOnLoadCompleteListener((pool, sampleId, result) -> {
            if (result == 0) loadedSounds++;
            else Log.e("QuanyouMetronome", "本地音频加载失败: sample=" + sampleId + " code=" + result);
            if (statusLabel != null && !running) {
                statusLabel.setText(result == 0 ? "本地声音就绪：" + loadedSounds + "/8"
                        : "声音加载失败，请重新启动应用");
            }
            if (loadedSounds == 8 && audioSelfTest) {
                playBeat(0);
                Log.i("QuanyouMetronome", "内置音频自检完成: stream=" + lastStreamId);
            }
        });
        tickSound = soundPool.load(this, R.raw.tick, 1);
        tickAccentSound = soundPool.load(this, R.raw.tick_accent, 1);
        drumSound = soundPool.load(this, R.raw.drum, 1);
        drumAccentSound = soundPool.load(this, R.raw.drum_accent, 1);
        voiceSounds[0] = soundPool.load(this, R.raw.voice_1, 1);
        voiceSounds[1] = soundPool.load(this, R.raw.voice_2, 1);
        voiceSounds[2] = soundPool.load(this, R.raw.voice_3, 1);
        voiceSounds[3] = soundPool.load(this, R.raw.voice_4, 1);
    }

    private View buildInterface() {
        LinearLayout root = column();
        root.setBackgroundColor(BG);
        root.setPadding(dp(10), h(5), dp(10), h(5));

        root.addView(label("全有节拍器", 26, Color.WHITE, 38));
        root.addView(label("刘全有大官人出品", 12, MUTED, 20));
        dateLabel = label("", 14, MUTED, 22);
        root.addView(dateLabel);

        LinearLayout tabs = row();
        metronomeTab = optionButton("节拍器", v -> showPage(false));
        tunerTab = optionButton("调音器", v -> showPage(true));
        addWeighted(tabs, metronomeTab);
        addWeighted(tabs, tunerTab);
        root.addView(tabs, new LinearLayout.LayoutParams(-1, h(40)));

        LinearLayout pages = column();
        metronomePage = buildMetronomePage();
        tunerPage = buildTunerPage();
        pages.addView(metronomePage, new LinearLayout.LayoutParams(-1, -1));
        pages.addView(tunerPage, new LinearLayout.LayoutParams(-1, -1));
        tunerPage.setVisibility(View.GONE);
        root.addView(pages, new LinearLayout.LayoutParams(-1, 0, 1));

        practiceLabel = label("", 13, Color.WHITE, 26);
        root.addView(practiceLabel);
        LinearLayout historyRow = row();
        addWeighted(historyRow, optionButton("查看每日记录", v -> showHistory()));
        addWeighted(historyRow, optionButton("清理记录缓存", v -> confirmClearHistory()));
        root.addView(historyRow, new LinearLayout.LayoutParams(-1, h(32)));
        styleOption(metronomeTab, true);
        styleOption(tunerTab, false);
        updatePractice();
        return root;
    }

    private LinearLayout buildMetronomePage() {
        LinearLayout page = column();
        bpmLabel = label("100 BPM", 38, BLUE, 46);
        page.addView(bpmLabel);
        beatView = new BeatView();
        page.addView(beatView, new LinearLayout.LayoutParams(-1, h(42)));

        LinearLayout card = column();
        card.setPadding(h(6), h(5), h(6), h(5));
        card.setBackground(roundRect(CARD, 13));
        page.addView(card);

        LinearLayout speedRow = row();
        speedRow.addView(label("速度", 14, Color.WHITE, 34),
                new LinearLayout.LayoutParams(h(44), -1));
        SeekBar bpmSlider = new SeekBar(this);
        bpmSlider.setMax(200);
        bpmSlider.setProgress(60);
        bpmSlider.setOnSeekBarChangeListener(new SimpleSeekListener() {
            @Override public void onProgressChanged(SeekBar bar, int value, boolean fromUser) {
                bpm = value + 40;
                bpmLabel.setText(bpm + " BPM");
            }
        });
        speedRow.addView(bpmSlider, new LinearLayout.LayoutParams(0, -1, 1));
        card.addView(speedRow, new LinearLayout.LayoutParams(-1, h(36)));

        LinearLayout soundRow = row();
        drumButton = optionButton("鼓声", v -> selectMode("鼓声"));
        voiceButton = optionButton("人声", v -> selectMode("人声"));
        tickButton = optionButton("打点", v -> selectMode("基础打点"));
        addWeighted(soundRow, drumButton);
        addWeighted(soundRow, voiceButton);
        addWeighted(soundRow, tickButton);
        card.addView(soundRow, new LinearLayout.LayoutParams(-1, h(42)));

        LinearLayout beatRow = row();
        beat2Button = optionButton("2/4", v -> selectBeats(2));
        beat3Button = optionButton("3/4", v -> selectBeats(3));
        beat4Button = optionButton("4/4", v -> selectBeats(4));
        addWeighted(beatRow, beat2Button);
        addWeighted(beatRow, beat3Button);
        addWeighted(beatRow, beat4Button);
        card.addView(beatRow, new LinearLayout.LayoutParams(-1, h(42)));

        LinearLayout volumeRow = row();
        volumeRow.addView(label("音量", 14, Color.WHITE, 34),
                new LinearLayout.LayoutParams(h(44), -1));
        SeekBar volumeSlider = new SeekBar(this);
        volumeSlider.setMax(100);
        volumeSlider.setProgress(80);
        volumeSlider.setOnSeekBarChangeListener(new SimpleSeekListener() {
            @Override public void onProgressChanged(SeekBar bar, int value, boolean fromUser) {
                volume = value / 100f;
            }
        });
        volumeRow.addView(volumeSlider, new LinearLayout.LayoutParams(0, -1, 1));
        card.addView(volumeRow, new LinearLayout.LayoutParams(-1, h(36)));

        LinearLayout timerRow = row();
        addWeighted(timerRow, optionButton("－", v -> changeMinutes(-1)));
        timerSetting = label("0 分钟", 16, Color.WHITE, 40);
        addWeighted(timerRow, timerSetting);
        addWeighted(timerRow, optionButton("＋", v -> changeMinutes(1)));
        card.addView(timerRow, new LinearLayout.LayoutParams(-1, h(40)));

        timerLabel = label("不限时", 25, Color.WHITE, 38);
        page.addView(timerLabel);
        LinearLayout actions = row();
        startButton = actionButton("▶ 开始", v -> toggleMetronome());
        addWeighted(actions, startButton);
        addWeighted(actions, actionButton("归零", v -> resetMetronome()));
        page.addView(actions, new LinearLayout.LayoutParams(-1, h(48)));
        Button preview = actionButton("试听当前声音", v -> previewSound());
        LinearLayout.LayoutParams previewParams = new LinearLayout.LayoutParams(-1, h(38));
        previewParams.setMargins(h(3), h(3), h(3), 0);
        page.addView(preview, previewParams);
        statusLabel = label("正在准备本地声音…", 12, MUTED, 24);
        page.addView(statusLabel);
        selectMode("基础打点");
        selectBeats(4);
        return page;
    }

    private LinearLayout buildTunerPage() {
        LinearLayout page = column();
        tunerStatus = label("进入调音器后开启麦克风", 14, MUTED, 32);
        page.addView(tunerStatus);
        tunerNote = label("—", 58, BLUE, 86);
        page.addView(tunerNote);
        tunerFrequency = label("等待音符…", 20, Color.WHITE, 38);
        page.addView(tunerFrequency);
        tunerMeter = new TunerMeterView();
        page.addView(tunerMeter, new LinearLayout.LayoutParams(-1, h(100)));
        tunerCents = label("弹一根弦开始调音", 20, Color.WHITE, 44);
        page.addView(tunerCents);

        LinearLayout referenceRow = row();
        addWeighted(referenceRow, optionButton("－", v -> changeReference(-1)));
        referenceLabel = label("标准音 A4 = 440 Hz", 14, Color.WHITE, 42);
        referenceRow.addView(referenceLabel, new LinearLayout.LayoutParams(0, -1, 3));
        addWeighted(referenceRow, optionButton("＋", v -> changeReference(1)));
        page.addView(referenceRow, new LinearLayout.LayoutParams(-1, h(42)));

        automaticButton = optionButton("自动识别音名与八度 · 点击选择目标音", v -> {
            automatic = !automatic;
            updateTargetControls();
        });
        page.addView(automaticButton, new LinearLayout.LayoutParams(-1, h(38)));
        LinearLayout targetRow = row();
        targetRow.addView(label("目标", 14, MUTED, 42),
                new LinearLayout.LayoutParams(h(40), -1));
        targetNoteButton = optionButton("E", v -> new AlertDialog.Builder(this)
                .setTitle("选择目标音")
                .setItems(NOTES, (dialog, index) -> {
                    targetNoteIndex = index;
                    updateTargetControls();
                }).show());
        addWeighted(targetRow, targetNoteButton);
        addWeighted(targetRow, optionButton("－", v -> changeTargetOctave(-1)));
        targetOctaveLabel = label("2", 18, Color.WHITE, 42);
        addWeighted(targetRow, targetOctaveLabel);
        addWeighted(targetRow, optionButton("＋", v -> changeTargetOctave(1)));
        page.addView(targetRow, new LinearLayout.LayoutParams(-1, h(44)));
        page.addView(label("自动模式识别 A0—C8；目标模式可选音名与八度", 12, MUTED, 38));
        updateTargetControls();
        return page;
    }

    private void showPage(boolean showTuner) {
        if (tunerPageVisible == showTuner) return;
        tunerPageVisible = showTuner;
        metronomePage.setVisibility(showTuner ? View.GONE : View.VISIBLE);
        tunerPage.setVisibility(showTuner ? View.VISIBLE : View.GONE);
        styleOption(metronomeTab, !showTuner);
        styleOption(tunerTab, showTuner);
        if (showTuner) {
            if (running) stopMetronome("已切换到调音器");
            startTuner();
        } else {
            tuner.stop();
        }
    }

    private void startTuner() {
        if (!foreground || !tunerPageVisible) return;
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            tunerStatus.setText("请允许麦克风权限");
            requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO}, MICROPHONE_REQUEST);
            return;
        }
        tunerStatus.setText("正在听音…请单独弹响一根弦");
        tuner.start();
    }

    @Override public void onRequestPermissionsResult(int requestCode, String[] permissions,
                                                        int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode == MICROPHONE_REQUEST && tunerPageVisible) {
            if (grantResults.length > 0 && grantResults[0] == PackageManager.PERMISSION_GRANTED) {
                startTuner();
            } else {
                tunerStatus.setText("未授予麦克风权限，请到系统设置中开启");
            }
        }
    }

    private void updatePitch(PitchDetector.Result result) {
        if (result == null) {
            if (++missingFrames > 5) {
                stableFrequency = 0;
                tunerNote.setText("—");
                tunerFrequency.setText("等待音符…");
                tunerCents.setText("弹一根弦开始调音");
                tunerMeter.setCents(Double.NaN);
            }
            return;
        }
        missingFrames = 0;
        double frequency = result.frequency;
        if (stableFrequency > 0
                && Math.abs(1200 * log2(frequency / stableFrequency)) < 70) {
            stableFrequency = stableFrequency * 0.65 + frequency * 0.35;
        } else {
            stableFrequency = frequency;
        }
        double midi = 69 + 12 * log2(stableFrequency / referenceHz);
        int rounded = (int) Math.round(midi);
        String note = NOTES[Math.floorMod(rounded, 12)] + (Math.floorDiv(rounded, 12) - 1);
        tunerNote.setText(note);
        tunerFrequency.setText(String.format(Locale.CHINA, "%.1f Hz  ·  可信度 %.0f%%",
                stableFrequency, result.confidence * 100));
        int targetMidi = automatic ? rounded : (targetOctave + 1) * 12 + targetNoteIndex;
        double target = referenceHz * Math.pow(2, (targetMidi - 69) / 12.0);
        double cents = 1200 * log2(stableFrequency / target);
        tunerMeter.setCents(cents);
        if (!automatic && Math.abs(cents) > 50) {
            tunerCents.setText(String.format(Locale.CHINA, "距目标 %s%d  %+.0f 音分",
                    NOTES[targetNoteIndex], targetOctave, cents));
        } else if (Math.abs(cents) < 3) {
            tunerCents.setText(String.format(Locale.CHINA, "音准到位  %+.1f 音分", cents));
        } else {
            tunerCents.setText(String.format(Locale.CHINA, "%+.1f 音分  ·  %s",
                    cents, cents < 0 ? "偏低，拧紧琴弦" : "偏高，放松琴弦"));
        }
        tunerStatus.setText(automatic ? "自动识别 · " + note
                : "目标音 · " + NOTES[targetNoteIndex] + targetOctave);
    }

    private double log2(double value) {
        return Math.log(value) / Math.log(2);
    }

    private void changeReference(int amount) {
        referenceHz = Math.max(430, Math.min(450, referenceHz + amount));
        referenceLabel.setText("标准音 A4 = " + referenceHz + " Hz");
        stableFrequency = 0;
    }

    private void changeTargetOctave(int amount) {
        targetOctave = Math.max(0, Math.min(8, targetOctave + amount));
        updateTargetControls();
    }

    private void updateTargetControls() {
        automaticButton.setText(automatic ? "自动识别音名与八度 · 点击选择目标音"
                : "按目标音调弦 · 点击返回自动识别");
        styleOption(automaticButton, automatic);
        targetNoteButton.setText(NOTES[targetNoteIndex]);
        targetOctaveLabel.setText(Integer.toString(targetOctave));
    }

    private void updatePractice() {
        if (dateLabel == null || practiceLabel == null) return;
        dateLabel.setText(practice.today());
        practiceLabel.setText("今日练习  " + PracticeHistory.format(practice.todayMillis())
                + "   累计  " + PracticeHistory.format(practice.totalMillis()));
    }

    private void showHistory() {
        practice.tick();
        updatePractice();
        new AlertDialog.Builder(this).setTitle("每日练习记录")
                .setMessage(practice.historyText())
                .setPositiveButton("关闭", null).show();
    }

    private void confirmClearHistory() {
        new AlertDialog.Builder(this).setTitle("清理练习记录缓存")
                .setMessage("将清除所有日期的使用时长和累计时长。清理后无法恢复，确定要继续吗？")
                .setPositiveButton("确认清理", (dialog, which) -> {
                    practice.clear();
                    updatePractice();
                    Toast.makeText(this, "练习记录已清理", Toast.LENGTH_SHORT).show();
                })
                .setNegativeButton("取消", null).show();
    }

    private void selectMode(String selected) {
        mode = selected;
        styleOption(drumButton, selected.equals("鼓声"));
        styleOption(voiceButton, selected.equals("人声"));
        styleOption(tickButton, selected.equals("基础打点"));
        if (statusLabel != null) statusLabel.setText("当前声音：" + selected + "（本地内置）");
    }

    private void selectBeats(int selected) {
        beats = selected;
        beat = 0;
        beatView.setBeats(selected);
        styleOption(beat2Button, selected == 2);
        styleOption(beat3Button, selected == 3);
        styleOption(beat4Button, selected == 4);
        if (statusLabel != null) statusLabel.setText("当前拍子：" + selected + "/4");
    }

    private void changeMinutes(int delta) {
        if (running) return;
        minutes = Math.max(0, Math.min(180, minutes + delta));
        timerSetting.setText(minutes + " 分钟");
        timerLabel.setText(minutes == 0 ? "不限时" : String.format(Locale.CHINA, "%02d:00", minutes));
    }

    private void toggleMetronome() {
        if (running) {
            stopMetronome("已停止");
            return;
        }
        if (loadedSounds < 8) {
            Toast.makeText(this, "声音正在准备，请稍候", Toast.LENGTH_SHORT).show();
            return;
        }
        running = true;
        beat = 0;
        nextBeatAt = SystemClock.uptimeMillis();
        finishAt = minutes == 0 ? 0 : nextBeatAt + minutes * 60_000L;
        startButton.setText("■ 停止");
        statusLabel.setText("播放中");
        handler.postAtTime(beatRunnable, nextBeatAt);
        handler.post(timerRunnable);
    }

    private void stopMetronome(String message) {
        running = false;
        handler.removeCallbacks(beatRunnable);
        handler.removeCallbacks(timerRunnable);
        if (lastStreamId != 0) {
            soundPool.stop(lastStreamId);
            lastStreamId = 0;
        }
        startButton.setText("▶ 开始");
        statusLabel.setText(message);
        beatView.setActive(-1);
    }

    private void resetMetronome() {
        stopMetronome("已归零");
        timerLabel.setText(minutes == 0 ? "不限时" : String.format(Locale.CHINA, "%02d:00", minutes));
    }

    private void playBeat(int currentBeat) {
        int sound;
        if (mode.equals("人声")) sound = voiceSounds[currentBeat];
        else if (mode.equals("鼓声")) sound = currentBeat == 0 ? drumAccentSound : drumSound;
        else sound = currentBeat == 0 ? tickAccentSound : tickSound;
        int streamId = soundPool.play(sound, volume, volume, 1, 0, 1f);
        if (streamId == 0) {
            if (statusLabel != null) statusLabel.setText("播放失败，请检查媒体音量并重启应用");
            Log.e("QuanyouMetronome", "SoundPool.play 失败: sound=" + sound);
        } else {
            lastStreamId = streamId;
        }
    }

    private void previewSound() {
        if (loadedSounds < 8) {
            Toast.makeText(this, "声音正在准备，请稍候", Toast.LENGTH_SHORT).show();
            return;
        }
        AudioManager audioManager = (AudioManager) getSystemService(AUDIO_SERVICE);
        if (audioManager != null && audioManager.getStreamVolume(AudioManager.STREAM_MUSIC) == 0) {
            statusLabel.setText("手机媒体音量为 0，请按音量加键");
            Toast.makeText(this, "请把手机媒体音量调高", Toast.LENGTH_LONG).show();
        } else {
            statusLabel.setText("正在试听：" + mode);
        }
        playBeat(0);
    }

    @Override protected void onResume() {
        super.onResume();
        setVolumeControlStream(AudioManager.STREAM_MUSIC);
        foreground = true;
        practice.resume();
        handler.removeCallbacks(practiceRunnable);
        handler.post(practiceRunnable);
        if (tunerPageVisible) startTuner();
    }

    @Override protected void onPause() {
        foreground = false;
        handler.removeCallbacks(practiceRunnable);
        practice.pause();
        tuner.stop();
        if (running) stopMetronome("已暂停");
        super.onPause();
    }

    @Override protected void onDestroy() {
        handler.removeCallbacksAndMessages(null);
        tuner.stop();
        if (soundPool != null) soundPool.release();
        super.onDestroy();
    }

    private LinearLayout column() {
        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        return layout;
    }

    private LinearLayout row() {
        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.HORIZONTAL);
        layout.setGravity(Gravity.CENTER);
        return layout;
    }

    private TextView label(String value, int size, int color, int height) {
        TextView view = new TextView(this);
        view.setText(value);
        view.setTextSize(size * scale);
        view.setTextColor(color);
        view.setGravity(Gravity.CENTER);
        view.setIncludeFontPadding(false);
        view.setSingleLine(true);
        view.setLayoutParams(new LinearLayout.LayoutParams(-1, h(height)));
        return view;
    }

    private Button optionButton(String value, View.OnClickListener listener) {
        Button button = new Button(this);
        button.setText(value);
        button.setTextSize(16 * scale);
        button.setTextColor(Color.WHITE);
        button.setAllCaps(false);
        button.setMinHeight(0);
        button.setMinimumHeight(0);
        button.setMinWidth(0);
        button.setMinimumWidth(0);
        button.setSingleLine(true);
        button.setPadding(dp(2), 0, dp(2), 0);
        button.setOnClickListener(listener);
        styleOption(button, false);
        return button;
    }

    private Button actionButton(String value, View.OnClickListener listener) {
        Button button = optionButton(value, listener);
        button.setTextSize(18 * scale);
        button.setBackground(roundRect(BLUE, 10));
        return button;
    }

    private void styleOption(Button button, boolean selected) {
        if (button == null) return;
        button.setBackground(roundRect(selected ? BLUE : Color.rgb(52, 66, 92), 9));
        button.setAlpha(selected ? 1f : 0.82f);
    }

    private void addWeighted(LinearLayout parent, View child) {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(0, -1, 1);
        params.setMargins(h(2), 0, h(2), 0);
        parent.addView(child, params);
    }

    private GradientDrawable roundRect(int color, int radiusDp) {
        GradientDrawable drawable = new GradientDrawable();
        drawable.setColor(color);
        drawable.setCornerRadius(dp(radiusDp));
        return drawable;
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    private int h(int value) {
        return Math.max(1, Math.round(dp(value) * scale));
    }

    private abstract static class SimpleSeekListener implements SeekBar.OnSeekBarChangeListener {
        @Override public void onStartTrackingTouch(SeekBar seekBar) {}
        @Override public void onStopTrackingTouch(SeekBar seekBar) {}
    }

    private class BeatView extends View {
        private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
        private int visibleBeats = 4;
        private int active = -1;

        BeatView() { super(MainActivity.this); }
        void setBeats(int value) { visibleBeats = value; active = -1; invalidate(); }
        void setActive(int value) { active = value; invalidate(); }

        @Override protected void onDraw(Canvas canvas) {
            super.onDraw(canvas);
            float gap = Math.min(getWidth() / 5f, h(82));
            float radius = Math.min(gap * 0.29f, h(24));
            float centerX = getWidth() / 2f;
            float centerY = getHeight() / 2f;
            for (int index = 0; index < 4; index++) {
                if (index >= visibleBeats) paint.setColor(Color.rgb(25, 33, 48));
                else if (index == active) paint.setColor(index == 0 ? ORANGE : GREEN);
                else paint.setColor(Color.rgb(46, 59, 84));
                canvas.drawCircle(centerX + (index - 1.5f) * gap, centerY, radius, paint);
            }
        }
    }

    private class TunerMeterView extends View {
        private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
        private double cents = Double.NaN;

        TunerMeterView() { super(MainActivity.this); }
        void setCents(double value) { cents = value; invalidate(); }

        @Override protected void onDraw(Canvas canvas) {
            super.onDraw(canvas);
            float left = h(20);
            float right = getWidth() - h(20);
            float center = getWidth() / 2f;
            float y = getHeight() * 0.55f;
            paint.setStrokeWidth(h(2));
            paint.setColor(MUTED);
            canvas.drawLine(left, y, right, y, paint);
            for (int step = -5; step <= 5; step++) {
                float x = center + step * (right - left) / 10f;
                paint.setColor(step == 0 ? GREEN : MUTED);
                paint.setStrokeWidth(h(step == 0 ? 3 : 1));
                canvas.drawLine(x, y - h(step == 0 ? 16 : 8),
                        x, y + h(step == 0 ? 16 : 8), paint);
            }
            paint.setTextSize(13 * scale * getResources().getDisplayMetrics().scaledDensity);
            paint.setColor(MUTED);
            paint.setTextAlign(Paint.Align.LEFT);
            canvas.drawText("-50", left, y + h(35), paint);
            paint.setTextAlign(Paint.Align.CENTER);
            canvas.drawText("0", center, y + h(35), paint);
            paint.setTextAlign(Paint.Align.RIGHT);
            canvas.drawText("+50", right, y + h(35), paint);
            if (!Double.isNaN(cents)) {
                float x = (float) (center + Math.max(-50, Math.min(50, cents))
                        * (right - left) / 100.0);
                paint.setColor(Math.abs(cents) < 3 ? GREEN : ORANGE);
                canvas.drawCircle(x, y - h(20), h(8), paint);
            }
        }
    }
}
