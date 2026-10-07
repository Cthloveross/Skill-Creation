"""Target-language TTS. Prefers Kokoro KPipeline, then kokoro-onnx, then espeak.
Returns (wav_path, sample_rate, engine_name). Raises on total failure so the
caller can surface a dependency warning instead of writing silent audio.
"""
import glob
import os
import subprocess
import numpy as np

import audio_utils as A

# ISO 639-1 -> Kokoro language code
ISO_TO_KOKORO = {
    "en": "a", "en-us": "a", "en-gb": "b",
    "ja": "j", "jp": "j",
    "zh": "z", "cmn": "z",
    "es": "e", "fr": "f", "hi": "h", "it": "i",
    "pt": "p", "pt-br": "p",
}
# default voice per Kokoro language code
KOKORO_VOICE = {
    "a": "af_heart", "b": "bf_emma", "j": "jf_alpha", "z": "zf_xiaobei",
    "e": "ef_dora", "f": "ff_siwis", "h": "hf_alpha", "i": "if_sara",
    "p": "pf_dora",
}
ISO_TO_ESPEAK = {"en": "en", "ja": "ja", "zh": "cmn", "es": "es",
                 "fr": "fr", "hi": "hi", "it": "it", "pt": "pt"}


def _kokoro_lang(iso):
    return ISO_TO_KOKORO.get(iso.lower(), ISO_TO_KOKORO.get(iso.lower().split("-")[0], "a"))


def _try_kpipeline(text, iso, out_wav):
    from kokoro import KPipeline  # noqa
    klang = _kokoro_lang(iso)
    voice = KOKORO_VOICE.get(klang, "af_heart")
    pipe = KPipeline(lang_code=klang)
    chunks = []
    for res in pipe(text, voice=voice):
        audio = res[-1] if isinstance(res, (tuple, list)) else res
        if hasattr(audio, "detach"):
            audio = audio.detach().cpu().numpy()
        chunks.append(np.asarray(audio, dtype=np.float32).reshape(-1))
    if not chunks:
        raise RuntimeError("KPipeline produced no audio")
    wav = np.concatenate(chunks)
    sr = 24000
    A.write_wav(out_wav, wav, sr)
    return out_wav, sr, "kokoro:KPipeline/%s" % voice


def _try_kokoro_onnx(text, iso, out_wav):
    from kokoro_onnx import Kokoro  # noqa
    model = voices = None
    for pat in ("**/kokoro*.onnx", "**/*kokoro*.onnx"):
        hits = glob.glob(os.path.join(os.path.expanduser("~"), pat), recursive=True)
        hits += glob.glob(os.path.join("/", "**", pat.split("/")[-1]), recursive=True)
        if hits:
            model = hits[0]
            break
    for pat in ("voices*.bin", "*voices*.bin", "voices*.json"):
        hits = glob.glob(os.path.join(os.path.dirname(model or ""), pat))
        if hits:
            voices = hits[0]
            break
    if not model or not voices:
        raise RuntimeError("kokoro-onnx model/voices files not found")
    k = Kokoro(model, voices)
    klang = _kokoro_lang(iso)
    voice = KOKORO_VOICE.get(klang, "af_heart")
    lang_long = {"a": "en-us", "b": "en-gb", "j": "ja", "z": "cmn",
                 "e": "es", "f": "fr-fr", "h": "hi", "i": "it", "p": "pt-br"}.get(klang, "en-us")
    samples, sr = k.create(text, voice=voice, speed=1.0, lang=lang_long)
    A.write_wav(out_wav, np.asarray(samples, dtype=np.float32).reshape(-1), int(sr))
    return out_wav, int(sr), "kokoro-onnx/%s" % voice


def _try_espeak(text, iso, out_wav):
    exe = "espeak-ng" if A.have("espeak-ng") else ("espeak" if A.have("espeak") else None)
    if not exe:
        raise RuntimeError("espeak-ng not installed")
    v = ISO_TO_ESPEAK.get(iso.lower().split("-")[0], "en")
    p = subprocess.run([exe, "-v", v, "-w", out_wav, text], capture_output=True, text=True)
    if p.returncode != 0 or not os.path.exists(out_wav):
        raise RuntimeError("espeak failed: %s" % p.stderr)
    _, sr = A.read_wav(out_wav)
    return out_wav, sr, "espeak/%s" % v


def synthesize(text, iso_code, out_wav):
    errs = []
    for fn in (_try_kpipeline, _try_kokoro_onnx, _try_espeak):
        try:
            return fn(text, iso_code, out_wav)
        except Exception as e:  # noqa
            errs.append("%s: %s" % (fn.__name__, e))
    raise RuntimeError("all TTS backends failed -> " + " | ".join(errs))
