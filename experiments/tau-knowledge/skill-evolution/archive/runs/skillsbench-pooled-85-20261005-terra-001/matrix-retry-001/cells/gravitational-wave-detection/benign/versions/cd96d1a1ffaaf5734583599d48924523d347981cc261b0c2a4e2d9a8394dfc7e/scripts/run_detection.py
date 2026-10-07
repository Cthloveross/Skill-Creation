#!/usr/bin/env python3
"""Run a conditioned PyCBC matched-filter mass-grid search.

JSON stdin schema is documented in SKILL.md. Successful stdout is a JSON summary;
the requested CSV is written atomically at output_path.
"""
import csv
import json
import math
import os
import sys
import tempfile
from pathlib import Path

import numpy as np


def fail(message):
    raise RuntimeError(message)


def required_string(config, name):
    value = config.get(name)
    if not isinstance(value, str) or not value.strip():
        fail("%s must be a nonempty string" % name)
    return value


def positive_float(config, name):
    value = config.get(name)
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
        fail("%s must be a positive number" % name)
    return float(value)


def positive_int(config, name):
    value = config.get(name)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        fail("%s must be a positive integer" % name)
    return value


def parse_config(raw):
    if not isinstance(raw, dict):
        fail("stdin must contain a JSON object")
    config = {
        "data_path": required_string(raw, "data_path"),
        "channel": required_string(raw, "channel"),
        "output_path": required_string(raw, "output_path"),
        "mass_min": positive_int(raw, "mass_min"),
        "mass_max": positive_int(raw, "mass_max"),
        "low_frequency_cutoff_hz": positive_float(raw, "low_frequency_cutoff_hz"),
        "highpass_hz": positive_float(raw, "highpass_hz"),
        "target_sample_rate_hz": positive_int(raw, "target_sample_rate_hz"),
        "transient_crop_seconds": positive_float(raw, "transient_crop_seconds"),
        "psd_segment_seconds": positive_float(raw, "psd_segment_seconds"),
        "psd_truncation_seconds": positive_float(raw, "psd_truncation_seconds"),
    }
    approximants = raw.get("approximants")
    if (not isinstance(approximants, list) or not approximants or
            any(not isinstance(x, str) or not x for x in approximants)):
        fail("approximants must be a nonempty list of nonempty strings")
    if len(set(approximants)) != len(approximants):
        fail("approximants must not contain duplicates")
    config["approximants"] = approximants
    if config["mass_max"] < config["mass_min"]:
        fail("mass_max must be at least mass_min")
    if config["low_frequency_cutoff_hz"] < config["highpass_hz"]:
        fail("low_frequency_cutoff_hz must be at least highpass_hz")
    if not os.path.isfile(config["data_path"]):
        fail("data_path does not name a regular file: %s" % config["data_path"])
    return config


def condition_and_make_psd(config):
    from pycbc.frame import read_frame
    from pycbc.psd import interpolate, inverse_spectrum_truncation

    strain = read_frame(config["data_path"], config["channel"])
    if len(strain) < 2:
        fail("frame channel contains too few samples")

    # Filtering precedes resampling so low-frequency contamination cannot alias.
    strain = strain.highpass_fir(config["highpass_hz"], 8)
    strain = strain.resample(config["target_sample_rate_hz"])
    crop = config["transient_crop_seconds"]
    if strain.duration <= 2.0 * crop:
        fail("data is shorter than the requested two-sided transient crop")
    strain = strain.crop(crop, crop)

    if strain.duration < 2.0 * config["psd_segment_seconds"]:
        fail("conditioned data is too short for a meaningful Welch PSD")
    psd = strain.psd(config["psd_segment_seconds"])
    psd = interpolate(psd, strain.delta_f)
    truncation_samples = int(round(config["psd_truncation_seconds"] * strain.sample_rate))
    if truncation_samples < 2:
        fail("PSD truncation duration gives fewer than two samples")
    psd = inverse_spectrum_truncation(
        psd, truncation_samples,
        low_frequency_cutoff=config["low_frequency_cutoff_hz"],
    )
    finite = np.isfinite(np.asarray(psd))
    if not np.all(finite):
        fail("PSD contains non-finite values after conditioning")
    return strain, psd


def make_time_domain_template(approximant, mass1, mass2, delta_t, f_low):
    from pycbc.waveform import get_td_waveform, get_td_waveform_from_fd

    args = {
        "approximant": approximant,
        "mass1": mass1,
        "mass2": mass2,
        "delta_t": delta_t,
        "f_lower": f_low,
    }
    # IMRPhenomD is an FD family; this preserves the uniform TD preparation
    # (resize and cyclic shift) used for all templates in this search.
    if approximant == "IMRPhenomD":
        hp, _ = get_td_waveform_from_fd(**args)
    else:
        hp, _ = get_td_waveform(**args)
    if len(hp) < 2 or not math.isfinite(float(hp.duration)):
        fail("waveform generator returned an invalid template for %s" % approximant)
    return hp


def peak_for_template(strain, psd, config, approximant, mass1, mass2):
    from pycbc.filter import matched_filter

    hp = make_time_domain_template(
        approximant, mass1, mass2, strain.delta_t,
        config["low_frequency_cutoff_hz"],
    )
    original_duration = float(hp.duration)
    if original_duration + 2.0 * config["psd_truncation_seconds"] >= strain.duration:
        fail("template duration leaves no valid SNR samples for %s (%d, %d)" %
             (approximant, mass1, mass2))

    # Record the epoch before padding: resize alone is insufficient because an
    # FFT matched filter uses circular convolution and expects merger at index 0.
    original_start = hp.start_time
    hp.resize(len(strain))
    template = hp.cyclic_time_shift(original_start)
    snr = matched_filter(
        template, strain, psd=psd,
        low_frequency_cutoff=config["low_frequency_cutoff_hz"],
    )

    # The leading edge also contains template-filter corruption; both edges
    # contain the inverse-PSD filter corruption.
    leading = config["psd_truncation_seconds"] + original_duration
    trailing = config["psd_truncation_seconds"]
    if leading + trailing >= snr.duration:
        fail("SNR crop would remove all samples for %s (%d, %d)" %
             (approximant, mass1, mass2))
    valid_snr = snr.crop(leading, trailing)
    if len(valid_snr) == 0:
        fail("empty valid SNR series for %s (%d, %d)" %
             (approximant, mass1, mass2))
    peak = float(np.max(np.abs(np.asarray(valid_snr))))
    if not math.isfinite(peak):
        fail("non-finite SNR for %s (%d, %d)" % (approximant, mass1, mass2))
    return peak


def search_approximant(strain, psd, config, approximant):
    best = None
    for mass1 in range(config["mass_min"], config["mass_max"] + 1):
        for mass2 in range(config["mass_min"], mass1 + 1):
            peak = peak_for_template(strain, psd, config, approximant, mass1, mass2)
            candidate = (peak, mass1, mass2)
            if best is None or candidate[0] > best[0]:
                best = candidate
    if best is None or not math.isfinite(best[0]) or best[0] <= 0.0:
        fail("no finite positive SNR found for approximant %s" % approximant)
    return {
        "approximant": approximant,
        "snr": best[0],
        "mass1": best[1],
        "mass2": best[2],
        "total_mass": best[1] + best[2],
    }


def write_csv_atomic(output_path, results):
    destination = Path(output_path)
    parent = destination.parent
    if not parent.exists() or not parent.is_dir():
        fail("output directory does not exist: %s" % parent)
    fd, temporary = tempfile.mkstemp(prefix=".detection-results-", suffix=".csv", dir=str(parent))
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(["approximant", "snr", "total_mass"])
            for result in results:
                writer.writerow([
                    result["approximant"],
                    format(result["snr"], ".12g"),
                    result["total_mass"],
                ])
        os.replace(temporary, output_path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def main():
    try:
        raw = json.load(sys.stdin)
        config = parse_config(raw)
        strain, psd = condition_and_make_psd(config)
        results = [search_approximant(strain, psd, config, name)
                   for name in config["approximants"]]
        for result in results:
            if result["total_mass"] != result["mass1"] + result["mass2"]:
                fail("internal total-mass validation failed")
        write_csv_atomic(config["output_path"], results)
        print(json.dumps({"output_path": config["output_path"], "results": results},
                         allow_nan=False))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
