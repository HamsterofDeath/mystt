# ElevenLabs narration traps

## Diagnose before regenerating

Keep four layers distinct:

1. raw provider audio and timestamp alignment;
2. cleaned sentence audio;
3. combined narration;
4. audio muxed into the rendered video.

An artifact can exist in only one layer. Compare the same boundary at each
layer before deciding that ElevenLabs must be called again.

## Provider tail can be shorter than requested

ElevenLabs may return only about 80 ms after the final aligned character. A
cleanup routine that requests 120 or 200 ms and returns early when the source
is shorter can accidentally skip its fade. Clamp the fade to the tail that
actually exists.

Bad control flow:

```text
if requested_end >= source_end:
    return source_without_fade
```

Required control flow:

```text
retained_end = min(requested_end, source_end)
available_tail = retained_end - lexical_content_end
fade_duration = min(requested_fade, available_tail)
fade_to_zero()
append_exact_silence()
```

## Alignment zero does not prove a clean head

A provider alignment can place the first character at `0.0` while the waveform
starts with a click or breath, falls silent, and only then begins the word. A
short broadband transient followed by a silence pocket is a strong head-artifact
signature. Inspect the waveform and spectrogram; do not trust alignment alone.

When trimming a reviewed head artifact:

- trim decoded PCM, not MP3 bytes;
- quantize the trim to whole frames;
- subtract the actual frame duration from content, word, caption, beat, and
  sentence timestamps;
- clamp shifted timestamps at zero;
- leave a small natural lead-in before the real speech attack.

## Terminal punctuation is not the spoken boundary

Timestamp APIs may assign duration to quotes, periods, or ellipses. Use the last
lexical character as the content boundary while retaining spoken terminal
symbols such as `%`, `+`, or other symbols that are actually verbalized.

## Silence after a clip is not enough

Adding silence after an abruptly ending waveform preserves the click. Fade the
retained waveform to digital zero first, then append silence. Keep this internal
sentence silence distinct from an editorial `holdAfter` gap.

## MP3 is a delivery format, not an editing format

MP3 introduces encoder delay, decoder padding, and possible pre-echo. Never
concatenate MP3 bytes or infer sample-accurate timing from container duration.
Decode to a common PCM format, join PCM, then encode once. A reported MP3 start
offset such as roughly 20–25 ms can be encoder metadata rather than authored
silence.

## Do not compound cleanup

Always reconstruct a cleaned sentence from the immutable provider cache.
Repeatedly trimming or fading the public clip will shorten consonants and
accumulate timing drift.

Local cleanup fields should not invalidate the provider cache. Changes to text,
voice ID, model, voice settings, language, or seed should.

## Continuity can change on regeneration

Sentence-level generation makes repair cheap but a new generation may alter
pace, emphasis, pronunciation, or character. If the raw performance is good
except for a removable boundary artifact, prefer a measured local repair.
Otherwise regenerate only that sentence and compare it in context.

## Recommended evidence

Use FFmpeg to distinguish silence and transients:

```bash
ffmpeg -hide_banner -i narration.mp3 \
  -af silencedetect=noise=-50dB:d=0.005 -f null -
```

Render a narrow transition waveform:

```bash
ffmpeg -y -ss START -t DURATION -i narration.mp3 \
  -filter_complex "showwavespic=s=1800x500:colors=0x44ddff:scale=lin" \
  -frames:v 1 waveform.png
```

Render a spectrogram to identify a broadband click:

```bash
ffmpeg -y -ss START -t DURATION -i narration.mp3 \
  -lavfi "showspectrumpic=s=1800x700:legend=1:color=viridis:scale=log" \
  -frames:v 1 spectrum.png
```

Decode the final video without hiding errors:

```bash
ffmpeg -v error -i final-video.mp4 -f null -
```

Inspect, listen, and measure. A 60 fps video can still contain low-update-rate
visuals, and a valid audio container can still contain a perceptible click.

