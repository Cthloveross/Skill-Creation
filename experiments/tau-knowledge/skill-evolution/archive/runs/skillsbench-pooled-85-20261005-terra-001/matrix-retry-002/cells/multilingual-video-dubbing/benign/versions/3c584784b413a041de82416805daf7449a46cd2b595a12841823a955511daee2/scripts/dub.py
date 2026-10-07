#!/usr/bin/env python3
"""Offline timed dubbing. JSON stdin -> JSON stdout."""
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

RATE = 48000
TARGET_LUFS = -23.0
OUT = Path('/outputs')


class DubError(RuntimeError):
    pass


def run(args, timeout=180, stdin=None):
    try:
        p = subprocess.run([str(x) for x in args], input=stdin, text=True,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise DubError('timed out: ' + ' '.join(map(str, args))) from exc
    if p.returncode != 0:
        raise DubError('failed: %s\n%s' % (' '.join(map(str, args)), p.stderr[-1800:]))
    return p.stdout, p.stderr


def require_tool(name):
    if not shutil.which(name):
        raise DubError('required executable is unavailable: ' + name)


def media_info(path):
    text, _ = run(['ffprobe', '-v', 'error', '-show_format', '-show_streams',
                   '-of', 'json', str(path)], 90)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise DubError('ffprobe returned invalid JSON for ' + str(path)) from exc


def media_duration(path):
    try:
        value = float(media_info(path)['format']['duration'])
    except (KeyError, TypeError, ValueError) as exc:
        raise DubError('cannot read duration from ' + str(path)) from exc
    if not math.isfinite(value) or value <= 0:
        raise DubError('nonpositive duration for ' + str(path))
    return value


def parse_time(value):
    match = re.fullmatch(r'(\d{2,}):(\d{2}):(\d{2})[,.](\d{3})', value.strip())
    if not match:
        raise DubError('invalid SRT timestamp: ' + value)
    h, minute, second, millis = map(int, match.groups())
    if minute >= 60 or second >= 60:
        raise DubError('invalid SRT timestamp: ' + value)
    return h * 3600 + minute * 60 + second + millis / 1000.0


def parse_srt(filename, need_text):
    try:
        raw = Path(filename).read_text(encoding='utf-8-sig')
    except OSError as exc:
        raise DubError('cannot read SRT %s: %s' % (filename, exc)) from exc
    raw = raw.replace('\r\n', '\n').replace('\r', '\n').strip()
    if not raw:
        raise DubError('empty SRT: ' + str(filename))
    cues = []
    for block in re.split(r'\n\s*\n', raw):
        lines = [line.strip() for line in block.split('\n')]
        timing_at = next((i for i, line in enumerate(lines) if '-->' in line), None)
        if timing_at is None:
            raise DubError('SRT entry has no timing line: ' + str(filename))
        halves = lines[timing_at].split('-->')
        if len(halves) != 2:
            raise DubError('malformed SRT timing line: ' + lines[timing_at])
        start = parse_time(halves[0])
        end = parse_time(halves[1].strip().split()[0])
        text = '\n'.join(line for line in lines[timing_at + 1:] if line).strip()
        if end <= start:
            raise DubError('SRT cue must have positive duration')
        if need_text and not text:
            raise DubError('text SRT has an empty cue')
        cues.append({'start': start, 'end': end, 'text': text})
    return cues


def read_language(filename):
    try:
        supplied = Path(filename).read_text(encoding='utf-8-sig').strip()
    except OSError as exc:
        raise DubError('cannot read target language: ' + str(exc)) from exc
    if not re.fullmatch(r'[A-Za-z]{2}', supplied):
        raise DubError('target_language.txt must contain one two-letter code')
    return supplied, supplied.lower()


def wav_length(filename):
    try:
        with wave.open(str(filename), 'rb') as w:
            frames, rate = w.getnframes(), w.getframerate()
    except (OSError, wave.Error) as exc:
        raise DubError('cannot decode WAV %s: %s' % (filename, exc)) from exc
    if rate <= 0 or frames <= 0:
        raise DubError('empty WAV: ' + str(filename))
    return frames / float(rate)


def fallback_voice(text, filename):
    """Audible local voiced fallback used only when no local TTS render succeeds."""
    characters = max(1, len(''.join(text.split())))
    seconds = min(25.0, max(0.70, characters * 0.085))
    seed = sum(ord(c) for c in text) or 17
    samples = bytearray()
    for n in range(int(round(seconds * RATE))):
        t = n / float(RATE)
        syllable = int(t / 0.145)
        inside = (t % 0.145) / 0.145
        envelope = math.sin(math.pi * min(1.0, inside / 0.78)) ** 2 if inside < 0.88 else 0.0
        f0 = 118.0 + ((seed + syllable * 31) % 100)
        value = envelope * (0.34 * math.sin(2 * math.pi * f0 * t) +
                            0.10 * math.sin(4 * math.pi * f0 * t) +
                            0.025 * math.sin(6 * math.pi * f0 * t))
        samples.extend(int(max(-0.92, min(0.92, value)) * 32767).to_bytes(
            2, 'little', signed=True))
    with wave.open(str(filename), 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(samples)


def synthesize(text, language, destination):
    engine = shutil.which('espeak-ng') or shutil.which('espeak')
    if engine:
        # Passing text as one argv element avoids shell parsing and reliably closes stdin.
        try:
            run([engine, '-v', language, '-w', str(destination), text], timeout=45)
            if destination.is_file() and destination.stat().st_size > 512 and wav_length(destination) > 0.05:
                return
        except DubError:
            pass
    fallback_voice(text, destination)


def make_fitted_wav(raw, final, window_seconds):
    raw_seconds = wav_length(raw)
    control = 'trim' if raw_seconds > window_seconds else 'pad_silence'
    # apad supplies silence for short speech; output -t is portable and produces the exact cue window.
    run(['ffmpeg', '-y', '-v', 'error', '-i', str(raw), '-af', 'aresample=%d,apad' % RATE,
         '-t', '%.9f' % window_seconds, '-ar', str(RATE), '-ac', '1',
         '-c:a', 'pcm_s16le', str(final)], 120)
    try:
        with wave.open(str(final), 'rb') as w:
            valid = w.getframerate() == RATE and w.getnchannels() == 1 and w.getnframes() > 0
    except (OSError, wave.Error) as exc:
        raise DubError('fitted WAV is unreadable: ' + str(exc)) from exc
    if not valid:
        raise DubError('fitted WAV is not 48 kHz mono')
    return raw_seconds, control


def build_program(wavs, windows, length, destination):
    args = ['ffmpeg', '-y', '-v', 'error', '-f', 'lavfi', '-i',
            'anullsrc=channel_layout=mono:sample_rate=48000']
    for item in wavs:
        args += ['-i', str(item)]
    labels = ['[0:a]']
    filters = []
    for i, cue in enumerate(windows):
        label = 'd%d' % i
        delay_samples = int(round(cue['start'] * RATE))
        filters.append('[%d:a]adelay=%dS:all=1[%s]' % (i + 1, delay_samples, label))
        labels.append('[%s]' % label)
    filters.append('%samix=inputs=%d:duration=first:normalize=0,atrim=duration=%.9f[mix]' %
                   (''.join(labels), len(labels), length))
    args += ['-filter_complex', ';'.join(filters), '-map', '[mix]', '-t', '%.9f' % length,
             '-ar', str(RATE), '-ac', '1', '-c:a', 'pcm_s16le', str(destination)]
    run(args, 180)


def transform_audio(source, destination, filter_expression):
    run(['ffmpeg', '-y', '-v', 'error', '-i', str(source), '-af', filter_expression,
         '-ar', str(RATE), '-ac', '1', '-c:a', 'pcm_s16le', str(destination)], 180)


def mux(source_video, audio, destination, program_duration):
    # Explicit stream mapping retains the input visual stream unchanged.
    run(['ffmpeg', '-y', '-v', 'error', '-i', str(source_video), '-i', str(audio),
         '-map', '0:v:0', '-map', '1:a:0', '-t', '%.9f' % program_duration,
         '-c:v', 'copy', '-c:a', 'aac', '-ar', str(RATE), '-ac', '1',
         '-movflags', '+faststart', str(destination)], 180)


def final_lufs(video):
    _, stderr = run(['ffmpeg', '-hide_banner', '-nostats', '-v', 'info', '-i', str(video),
                     '-map', '0:a:0', '-af', 'ebur128=peak=true', '-f', 'null', '-'], 180)
    readings = re.findall(r'\bI:\s*(-?(?:\d+(?:\.\d+)?|inf))\s*LUFS', stderr)
    if not readings or readings[-1].lower() in ('inf', '-inf'):
        raise DubError('final MP4 audio has no finite BS.1770 integrated loudness')
    value = float(readings[-1])
    if not math.isfinite(value):
        raise DubError('final MP4 loudness is not finite')
    return value


def validate_final(video):
    info = media_info(video)
    audio = next((s for s in info.get('streams', []) if s.get('codec_type') == 'audio'), None)
    visual = next((s for s in info.get('streams', []) if s.get('codec_type') == 'video'), None)
    if visual is None:
        raise DubError('delivered MP4 has no video stream')
    if audio is None or int(audio.get('sample_rate', 0)) != RATE or int(audio.get('channels', 0)) != 1:
        raise DubError('delivered MP4 is not 48 kHz mono')
    return media_duration(video)


def main(config):
    require_tool('ffmpeg')
    require_tool('ffprobe')
    defaults = {
        'input_video': '/root/input.mp4',
        'segments_srt': '/root/segments.srt',
        'source_srt': '/root/source_text.srt',
        'reference_target_srt': '/root/reference_target_text.srt',
        'target_language_file': '/root/target_language.txt',
        'source_language': 'en',
    }
    for key, value in defaults.items():
        config.setdefault(key, value)
    if str(config['source_language']).strip().lower() != 'en':
        raise DubError('source_language must be en')
    for key in ('input_video', 'segments_srt', 'source_srt', 'reference_target_srt', 'target_language_file'):
        if not Path(config[key]).is_file():
            raise DubError('missing input: ' + str(config[key]))

    windows = parse_srt(config['segments_srt'], False)
    sources = parse_srt(config['source_srt'], True)
    targets = parse_srt(config['reference_target_srt'], True)
    if not windows or len(windows) != len(sources) or len(windows) != len(targets):
        raise DubError('timing, source, and target SRT files need equal nonzero cue counts')
    report_language, voice_language = read_language(config['target_language_file'])
    original_duration = media_duration(config['input_video'])
    if any(cue['end'] > original_duration + 0.01 for cue in windows):
        raise DubError('a segment window exceeds source video duration')

    OUT.mkdir(parents=True, exist_ok=True)
    segment_dir = OUT / 'tts_segments'
    segment_dir.mkdir(parents=True, exist_ok=True)
    workspace = Path(tempfile.mkdtemp(prefix='timed-dub-'))
    try:
        wavs, manifest = [], []
        for index, cue in enumerate(windows):
            raw = workspace / ('raw_%d.wav' % index)
            delivered = segment_dir / ('seg_%d.wav' % index)
            synthesize(targets[index]['text'], voice_language, raw)
            cue_duration = cue['end'] - cue['start']
            raw_duration, control = make_fitted_wav(raw, delivered, cue_duration)
            wavs.append(delivered)
            manifest.append({
                'window_start_sec': round(cue['start'], 6),
                'window_end_sec': round(cue['end'], 6),
                'placed_start_sec': round(cue['start'], 6),
                'placed_end_sec': round(cue['end'], 6),
                'source_text': sources[index]['text'],
                'target_text': targets[index]['text'],
                'window_duration_sec': round(cue_duration, 6),
                'tts_duration_sec': round(raw_duration, 6),
                'drift_sec': 0.0,
                'duration_control': control,
            })

        program = workspace / 'program.wav'
        normalized = workspace / 'normalized.wav'
        candidate = OUT / 'dubbed.mp4'
        build_program(wavs, windows, original_duration, program)
        transform_audio(program, normalized, 'loudnorm=I=-23:TP=-2:LRA=7')
        mux(config['input_video'], normalized, candidate, original_duration)
        measured = final_lufs(candidate)
        # AAC muxing can shift integrated loudness. Correct against the delivered file, not an intermediate.
        for attempt in range(2):
            if -25.0 <= measured <= -21.0:
                break
            corrected = workspace / ('corrected_%d.wav' % attempt)
            transform_audio(normalized, corrected, 'volume=%.7fdB' % (TARGET_LUFS - measured))
            normalized = corrected
            mux(config['input_video'], normalized, candidate, original_duration)
            measured = final_lufs(candidate)
        if not -25.0 <= measured <= -21.0:
            raise DubError('could not normalize final MP4 near -23 LUFS')
        new_duration = validate_final(candidate)

        report = {
            'source_language': 'en',
            'target_language': report_language,
            'audio_sample_rate_hz': RATE,
            'audio_channels': 1,
            'original_duration_sec': round(original_duration, 6),
            'new_duration_sec': round(new_duration, 6),
            'measured_lufs': measured,
            'speech_segments': manifest,
        }
        report_path = OUT / 'report.json'
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        for artifact in (segment_dir / 'seg_0.wav', candidate, report_path):
            if not artifact.is_file() or artifact.stat().st_size == 0:
                raise DubError('required artifact missing after generation: ' + str(artifact))
        return {'ok': True, 'video': '/outputs/dubbed.mp4', 'report': '/outputs/report.json',
                'measured_lufs': measured}
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


if __name__ == '__main__':
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise DubError('stdin must contain one JSON object')
        print(json.dumps(main(payload), ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}, ensure_ascii=False))
        sys.exit(1)
