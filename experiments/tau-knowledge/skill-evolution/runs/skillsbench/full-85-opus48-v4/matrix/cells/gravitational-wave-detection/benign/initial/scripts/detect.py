#!/usr/bin/env python3
"""Gravitational-wave matched-filter grid-search entrypoint.

Reads a JSON config on stdin, conditions LIGO frame strain data, runs a
matched-filter grid search over integer component masses (m1 >= m2) for each
requested waveform approximant, writes a results CSV, and prints a JSON summary
to stdout.

See SKILL.md for the input/output schema.
"""
import sys
import json
import csv
import math


def _fail(msg):
    sys.stderr.write(str(msg) + "\n")
    print(json.dumps({"error": str(msg), "results": [], "errors": [str(msg)]}))
    sys.exit(1)


def main():
    try:
        raw = sys.stdin.read()
        cfg = json.loads(raw) if raw.strip() else {}
    except Exception as e:  # noqa
        _fail("invalid JSON config on stdin: %s" % e)

    frame_path = cfg.get("frame_path")
    channel = cfg.get("channel")
    if not frame_path or not channel:
        _fail("frame_path and channel are required")

    output_csv = cfg.get("output_csv", "/root/detection_results.csv")
    approximants = cfg.get("approximants",
                           ["SEOBNRv4_opt", "IMRPhenomD", "TaylorT4"])
    mass_min = int(cfg.get("mass_min", 10))
    mass_max = int(cfg.get("mass_max", 40))
    f_low = float(cfg.get("f_low", 20.0))
    highpass_freq = float(cfg.get("highpass_freq", 15.0))
    sample_rate = int(cfg.get("sample_rate", 4096))
    psd_segment_s = float(cfg.get("psd_segment_s", 4))
    crop_s = float(cfg.get("crop_s", 2))

    try:
        from pycbc.frame import read_frame
        from pycbc.filter import highpass, resample_to_delta_t, matched_filter
        from pycbc.psd import interpolate, inverse_spectrum_truncation
        from pycbc.waveform import get_td_waveform
        import numpy as np
    except Exception as e:  # noqa
        _fail("PyCBC import failed (install with 'pip install pycbc'): %s" % e)

    # ---- load ----
    try:
        ts = read_frame(frame_path, channel)
    except Exception as e:  # noqa
        _fail("could not read frame %s channel %s: %s" % (frame_path, channel, e))

    # ---- condition ----
    try:
        strain = highpass(ts, highpass_freq)
        strain = resample_to_delta_t(strain, 1.0 / sample_rate)
        conditioned = strain.crop(crop_s, crop_s)
    except Exception as e:  # noqa
        _fail("conditioning failed: %s" % e)

    # ---- PSD ----
    try:
        psd = conditioned.psd(psd_segment_s)
        psd = interpolate(psd, conditioned.delta_f)
        psd = inverse_spectrum_truncation(
            psd,
            int(psd_segment_s * conditioned.sample_rate),
            low_frequency_cutoff=highpass_freq,
        )
    except Exception as e:  # noqa
        _fail("PSD estimation failed: %s" % e)

    data_len = len(conditioned)
    total_duration = data_len * conditioned.delta_t

    errors = []
    results = []

    for approx in approximants:
        best = None  # (snr, m1, m2)
        for m1 in range(mass_min, mass_max + 1):
            for m2 in range(mass_min, m1 + 1):  # m1 >= m2
                try:
                    hp, _ = get_td_waveform(
                        approximant=approx,
                        mass1=m1,
                        mass2=m2,
                        delta_t=conditioned.delta_t,
                        f_lower=f_low,
                    )
                    # template duration (merger at t=0, start_time negative)
                    try:
                        tmpl_dur = abs(float(hp.start_time))
                    except Exception:  # noqa
                        tmpl_dur = len(hp) * conditioned.delta_t

                    hp.resize(data_len)
                    template = hp.cyclic_time_shift(hp.start_time)

                    snr = matched_filter(
                        template,
                        conditioned,
                        psd=psd,
                        low_frequency_cutoff=f_low,
                    )

                    # crop corrupted edges: start by PSD seg + template dur,
                    # end by PSD seg. Clamp so cropping stays valid.
                    crop_start = psd_segment_s + tmpl_dur
                    crop_end = psd_segment_s
                    if crop_start + crop_end >= total_duration:
                        margin = max(total_duration * 0.1, 0.0)
                        crop_start = min(crop_start,
                                         max(total_duration - crop_end - margin, 0.0))
                        if crop_start < 0:
                            crop_start = 0.0
                    try:
                        snr_c = snr.crop(crop_start, crop_end)
                    except Exception:
                        snr_c = snr

                    peak = float(np.abs(snr_c).max())
                    if not math.isfinite(peak):
                        continue
                    if best is None or peak > best[0]:
                        best = (peak, m1, m2)
                except Exception as e:  # noqa
                    errors.append({"approximant": approx, "mass1": m1,
                                   "mass2": m2, "error": str(e)})
                    continue

        if best is not None:
            results.append({
                "approximant": approx,
                "snr": best[0],
                "total_mass": best[1] + best[2],
                "mass1": best[1],
                "mass2": best[2],
            })
        else:
            errors.append({"approximant": approx,
                           "error": "no valid template produced a finite SNR"})

    # ---- write CSV ----
    try:
        with open(output_csv, "w", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(["approximant", "snr", "total_mass"])
            for r in results:
                writer.writerow([r["approximant"], r["snr"], r["total_mass"]])
    except Exception as e:  # noqa
        _fail("could not write CSV %s: %s" % (output_csv, e))

    print(json.dumps({
        "output_csv": output_csv,
        "results": results,
        "errors": errors,
    }))


if __name__ == "__main__":
    main()
