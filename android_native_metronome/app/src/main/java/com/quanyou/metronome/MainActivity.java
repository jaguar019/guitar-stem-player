package com.quanyou.metronome;

import android.app.Activity;
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
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.SeekBar;
import android.widget.TextView;
import android.widget.Toast;
import android.util.Log;

import java.util.Locale;

public class MainActivity extends Activity {
    private static final int BG = Color.rgb(16, 21, 34);
    private static final int CARD = Color.rgb(28, 37, 54);
    private static final int BLUE = Color.rgb(82, 143, 247);
    private static final int MUTED = Color.rgb(140, 158, 186);
    private static final int GREEN = Color.rgb(82, 212, 140);
    private static final int ORANGE = Color.rgb(255, 179, 61);

    private final Handler handler = new Handler(Looper.getMainLooper());
    private SoundPool soundPool;
    private int tickSound;
    private int tickAccentSound;
    private int drumSound;
    private int drumAccentSound;
    private final int[] voiceSounds = new int[4];
    private int loadedSounds = 0;
    private int lastStreamId = 0;
    private boolean audioSelfTest;

    private int bpm = 100;
    private int beats = 4;
    private int beat = 0;
    private int minutes = 0;
    private float volume = 0.8f;
    private String mode = "基础打点";
    private boolean running = false;
    private long nextBeatAt = 0L;
    private long finishAt = 0L;

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
                timerLabel.setText(String.format(Locale.CHINA, "%02d:%02d", seconds / 60, seconds % 60));
            } else {
                timerLabel.setText("不限时");
            }
            handler.postDelayed(this, 200);
        }
    };

    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().setStatusBarColor(BG);
        getWindow().setNavigationBarColor(BG);
        audioSelfTest = getIntent().getBooleanExtra("audio_self_test", false);
        buildAudio();
        setContentView(buildInterface());
    }

    private void buildAudio() {
        AudioAttributes attributes = new AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_MEDIA)
                .setContentType(AudioAttributes.CONTENT_TYPE_MUSIC)
                .build();
        soundPool = new SoundPool.Builder().setMaxStreams(12).setAudioAttributes(attributes).build();
        soundPool.setOnLoadCompleteListener((pool, sampleId, result) -> {
            if (result == 0) loadedSounds++;
            else Log.e("QuanyouMetronome", "本地音频加载失败: sample=" + sampleId + " code=" + result);
            if (statusLabel != null && !running) {
                statusLabel.setText(result == 0 ? "本地声音就绪：" + loadedSounds + "/8" : "声音加载失败，请重新启动应用");
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
        ScrollView scroll = new ScrollView(this);
        scroll.setFillViewport(true);
        scroll.setBackgroundColor(BG);

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(22), dp(24), dp(22), dp(24));
        scroll.addView(root, new ScrollView.LayoutParams(-1, -2));

        root.addView(text("全有节拍器", 32, Color.WHITE, 58));
        root.addView(text("刘全有大官人出品", 14, MUTED, 32));
        bpmLabel = text("100 BPM", 46, BLUE, 88);
        root.addView(bpmLabel);

        beatView = new BeatView();
        root.addView(beatView, new LinearLayout.LayoutParams(-1, dp(96)));

        LinearLayout card = new LinearLayout(this);
        card.setOrientation(LinearLayout.VERTICAL);
        card.setPadding(dp(16), dp(14), dp(16), dp(14));
        card.setBackground(roundRect(CARD, 16));
        LinearLayout.LayoutParams cardParams = new LinearLayout.LayoutParams(-1, -2);
        cardParams.setMargins(0, dp(8), 0, dp(14));
        root.addView(card, cardParams);

        card.addView(section("速度  40—240 BPM"));
        SeekBar bpmSlider = new SeekBar(this);
        bpmSlider.setMax(200);
        bpmSlider.setProgress(60);
        bpmSlider.setOnSeekBarChangeListener(new SimpleSeekListener() {
            @Override public void onProgressChanged(SeekBar bar, int value, boolean fromUser) {
                bpm = value + 40;
                bpmLabel.setText(bpm + " BPM");
            }
        });
        card.addView(bpmSlider, new LinearLayout.LayoutParams(-1, dp(48)));

        card.addView(section("声音"));
        LinearLayout soundRow = row();
        drumButton = optionButton("鼓声", v -> selectMode("鼓声"));
        voiceButton = optionButton("人声", v -> selectMode("人声"));
        tickButton = optionButton("基础打点", v -> selectMode("基础打点"));
        addWeighted(soundRow, drumButton);
        addWeighted(soundRow, voiceButton);
        addWeighted(soundRow, tickButton);
        card.addView(soundRow, new LinearLayout.LayoutParams(-1, dp(52)));

        card.addView(section("拍子"));
        LinearLayout beatRow = row();
        beat2Button = optionButton("2/4", v -> selectBeats(2));
        beat3Button = optionButton("3/4", v -> selectBeats(3));
        beat4Button = optionButton("4/4", v -> selectBeats(4));
        addWeighted(beatRow, beat2Button);
        addWeighted(beatRow, beat3Button);
        addWeighted(beatRow, beat4Button);
        card.addView(beatRow, new LinearLayout.LayoutParams(-1, dp(52)));

        card.addView(section("音量"));
        SeekBar volumeSlider = new SeekBar(this);
        volumeSlider.setMax(100);
        volumeSlider.setProgress(80);
        volumeSlider.setOnSeekBarChangeListener(new SimpleSeekListener() {
            @Override public void onProgressChanged(SeekBar bar, int value, boolean fromUser) {
                volume = value / 100f;
            }
        });
        card.addView(volumeSlider, new LinearLayout.LayoutParams(-1, dp(48)));

        card.addView(section("倒计时（分钟，0 为不限时）"));
        LinearLayout timerRow = row();
        Button minus = optionButton("－", v -> changeMinutes(-1));
        Button plus = optionButton("＋", v -> changeMinutes(1));
        timerSetting = text("0 分钟", 22, Color.WHITE, 54);
        addWeighted(timerRow, minus);
        addWeighted(timerRow, timerSetting);
        addWeighted(timerRow, plus);
        card.addView(timerRow, new LinearLayout.LayoutParams(-1, dp(54)));

        timerLabel = text("不限时", 34, Color.WHITE, 68);
        root.addView(timerLabel);

        LinearLayout actions = row();
        startButton = actionButton("▶ 开始", v -> toggleMetronome());
        Button reset = actionButton("归零", v -> resetMetronome());
        addWeighted(actions, startButton);
        addWeighted(actions, reset);
        root.addView(actions, new LinearLayout.LayoutParams(-1, dp(66)));

        Button preview = actionButton("试听当前声音", v -> previewSound());
        LinearLayout.LayoutParams previewParams = new LinearLayout.LayoutParams(-1, dp(54));
        previewParams.setMargins(dp(4), dp(10), dp(4), 0);
        root.addView(preview, previewParams);

        statusLabel = text("正在准备本地声音…", 14, MUTED, 42);
        root.addView(statusLabel);
        selectMode("基础打点");
        selectBeats(4);
        return scroll;
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
            statusLabel.setText("播放失败，请检查媒体音量并重启应用");
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
    }

    @Override protected void onPause() {
        super.onPause();
        if (running) stopMetronome("已暂停");
    }

    @Override protected void onDestroy() {
        handler.removeCallbacksAndMessages(null);
        if (soundPool != null) soundPool.release();
        super.onDestroy();
    }

    private TextView text(String value, int size, int color, int height) {
        TextView view = new TextView(this);
        view.setText(value);
        view.setTextSize(size);
        view.setTextColor(color);
        view.setGravity(Gravity.CENTER);
        view.setLayoutParams(new LinearLayout.LayoutParams(-1, dp(height)));
        return view;
    }

    private TextView section(String value) {
        TextView view = text(value, 17, Color.WHITE, 34);
        view.setGravity(Gravity.CENTER_VERTICAL);
        return view;
    }

    private LinearLayout row() {
        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setGravity(Gravity.CENTER);
        return row;
    }

    private Button optionButton(String value, View.OnClickListener listener) {
        Button button = new Button(this);
        button.setText(value);
        button.setTextSize(16);
        button.setTextColor(Color.WHITE);
        button.setAllCaps(false);
        button.setPadding(dp(4), 0, dp(4), 0);
        button.setOnClickListener(listener);
        styleOption(button, false);
        return button;
    }

    private Button actionButton(String value, View.OnClickListener listener) {
        Button button = optionButton(value, listener);
        button.setTextSize(18);
        button.setBackground(roundRect(BLUE, 12));
        return button;
    }

    private void styleOption(Button button, boolean selected) {
        if (button == null) return;
        button.setBackground(roundRect(selected ? BLUE : Color.rgb(52, 66, 92), 10));
        button.setAlpha(selected ? 1f : 0.82f);
    }

    private void addWeighted(LinearLayout parent, View child) {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(0, -1, 1f);
        params.setMargins(dp(4), 0, dp(4), 0);
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
            float gap = Math.min(getWidth() / 5f, dp(82));
            float radius = Math.min(gap * 0.29f, dp(24));
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
}
