package com.quanyou.metronome;

/** Pitch detection on a 170 ms PCM window using a downsampled YIN difference curve. */
public final class PitchDetector {
    private PitchDetector() {}

    public static final class Result {
        public final double frequency;
        public final double confidence;

        Result(double frequency, double confidence) {
            this.frequency = frequency;
            this.confidence = confidence;
        }
    }

    public static Result detect(short[] pcm, int length, int sampleRate) {
        int count = Math.min(length / 2, 4096);
        if (count < 2048 || sampleRate <= 0) return null;
        double rate = sampleRate / 2.0;
        double[] values = new double[count];
        double mean = 0;
        for (int i = 0; i < count; i++) {
            values[i] = (pcm[2 * i] + pcm[2 * i + 1]) / 65536.0;
            mean += values[i];
        }
        mean /= count;
        double energy = 0;
        for (int i = 0; i < count; i++) {
            values[i] -= mean;
            energy += values[i] * values[i];
        }
        if (Math.sqrt(energy / count) < 0.008) return null;

        int minLag = Math.max(5, (int) Math.floor(rate / 4200.0));
        int maxLag = Math.min(count / 2, (int) Math.ceil(rate / 27.5));
        double[] difference = new double[maxLag + 1];
        double[] normalized = new double[maxLag + 1];
        double cumulative = 0;
        for (int lag = 1; lag <= maxLag; lag++) {
            double sum = 0;
            int end = count - lag;
            for (int i = 0; i < end; i++) {
                double delta = values[i] - values[i + lag];
                sum += delta * delta;
            }
            difference[lag] = sum;
            cumulative += sum;
            normalized[lag] = cumulative == 0 ? 1 : sum * lag / cumulative;
        }

        int selected = -1;
        for (int lag = minLag; lag < maxLag; lag++) {
            if (normalized[lag] < 0.15) {
                while (lag + 1 < maxLag && normalized[lag + 1] < normalized[lag]) lag++;
                selected = lag;
                break;
            }
        }
        if (selected < 0) return null;

        double refined = selected;
        if (selected > 1 && selected < maxLag) {
            double left = normalized[selected - 1];
            double center = normalized[selected];
            double right = normalized[selected + 1];
            double denominator = left - 2 * center + right;
            if (Math.abs(denominator) > 1e-9) {
                refined += Math.max(-1, Math.min(1, 0.5 * (left - right) / denominator));
            }
        }
        double frequency = rate / refined;
        if (refined < 40) {
            int predicted = (int) Math.round(refined * 2);
            int start = Math.max(3, predicted - 3);
            int end = Math.min(length / 4, predicted + 3);
            double[] fine = new double[end + 2];
            int bestLag = start;
            for (int lag = start; lag <= end; lag++) {
                double sum = 0;
                for (int i = 0; i < length - lag; i++) {
                    double delta = pcm[i] - pcm[i + lag];
                    sum += delta * delta;
                }
                fine[lag] = sum / (length - lag);
                if (fine[lag] < fine[bestLag] || lag == start) bestLag = lag;
            }
            double fullLag = bestLag;
            if (bestLag > start && bestLag < end) {
                double denominator = fine[bestLag - 1] - 2 * fine[bestLag] + fine[bestLag + 1];
                if (Math.abs(denominator) > 1e-9) {
                    fullLag += Math.max(-1, Math.min(1,
                            0.5 * (fine[bestLag - 1] - fine[bestLag + 1]) / denominator));
                }
            }
            frequency = sampleRate / fullLag;
        }
        if (frequency < 26.5 || frequency > 4300) return null;
        return new Result(frequency, 1.0 - normalized[selected]);
    }
}
