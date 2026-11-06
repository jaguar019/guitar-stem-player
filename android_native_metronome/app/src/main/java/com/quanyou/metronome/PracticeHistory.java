package com.quanyou.metronome;

import android.content.Context;
import android.content.SharedPreferences;
import android.os.SystemClock;

import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Date;
import java.util.Locale;
import java.util.Map;

/** Foreground practice time, persisted as daily milliseconds and a lifetime total. */
final class PracticeHistory {
    private final SharedPreferences preferences;
    private long lastTick;
    private boolean active;

    PracticeHistory(Context context) {
        preferences = context.getSharedPreferences("practice_history", Context.MODE_PRIVATE);
    }

    void resume() {
        lastTick = SystemClock.elapsedRealtime();
        active = true;
    }

    void pause() {
        tick();
        active = false;
    }

    void tick() {
        if (!active) return;
        long now = SystemClock.elapsedRealtime();
        long elapsed = Math.max(0, Math.min(now - lastTick, 60_000));
        lastTick = now;
        if (elapsed == 0) return;
        String key = "day_" + today();
        preferences.edit()
                .putLong(key, preferences.getLong(key, 0) + elapsed)
                .putLong("total_ms", preferences.getLong("total_ms", 0) + elapsed)
                .apply();
    }

    String today() {
        return new SimpleDateFormat("yyyy-MM-dd", Locale.getDefault()).format(new Date());
    }

    long todayMillis() {
        return preferences.getLong("day_" + today(), 0);
    }

    long totalMillis() {
        return preferences.getLong("total_ms", 0);
    }

    String historyText() {
        Map<String, ?> all = preferences.getAll();
        ArrayList<String> days = new ArrayList<>();
        for (String key : all.keySet()) if (key.startsWith("day_")) days.add(key);
        Collections.sort(days, Collections.reverseOrder());
        if (days.isEmpty()) return "暂时还没有练习记录";
        StringBuilder result = new StringBuilder();
        for (String key : days) {
            result.append(key.substring(4)).append("   ")
                    .append(format((Long) all.get(key))).append('\n');
        }
        result.append("\n累计   ").append(format(totalMillis()));
        return result.toString();
    }

    void clear() {
        preferences.edit().clear().commit();
        lastTick = SystemClock.elapsedRealtime();
    }

    static String format(long millis) {
        long seconds = Math.max(0, millis / 1000);
        return String.format(Locale.CHINA, "%02d:%02d:%02d",
                seconds / 3600, seconds / 60 % 60, seconds % 60);
    }
}
