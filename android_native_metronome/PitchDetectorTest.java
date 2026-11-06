import com.quanyou.metronome.PitchDetector;

public final class PitchDetectorTest {
    private static void verify(String label, double frequency, double toleranceCents,
                               double secondHarmonic) {
        short[] signal = new short[8192];
        for (int i = 0; i < signal.length; i++) {
            double phase = 2 * Math.PI * frequency * i / 48000.0;
            double value = Math.sin(phase) + secondHarmonic * Math.sin(2 * phase);
            signal[i] = (short) Math.round(19000 * value / (1 + secondHarmonic));
        }
        PitchDetector.Result result = PitchDetector.detect(signal, signal.length, 48000);
        if (result == null) throw new AssertionError(label + ": no pitch");
        double cents = 1200 * Math.log(result.frequency / frequency) / Math.log(2);
        if (Math.abs(cents) > toleranceCents) {
            throw new AssertionError(label + ": " + result.frequency + " Hz, error " + cents + " cents");
        }
        System.out.println(label + ": " + result.frequency + " Hz (" + cents + " cents)");
    }

    public static void main(String[] args) {
        verify("A0", 27.5, 5, 0);
        verify("E1", 41.20344, 5, 0.4);
        verify("E2", 82.40689, 3, 0.6);
        verify("A4", 440, 3, 0.5);
        verify("E6", 1318.51, 3, 0.3);
        verify("C8", 4186.009, 4, 0);
        short[] silent = new short[8192];
        if (PitchDetector.detect(silent, silent.length, 48000) != null) {
            throw new AssertionError("Silence should not register as a pitch");
        }
    }
}
