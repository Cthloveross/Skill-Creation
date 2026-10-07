#!/usr/bin/env python3
"""Run a conditioned PyCBC matched-filter integer-mass grid search.

JSON is read from stdin and one JSON completion object is emitted on stdout.
Diagnostic errors are written to stderr and result in a nonzero exit status.
"""
from __future__ import annotations

import csv
import json
import math
import os
import sys
from pathlib import Path
from typing import Any

import numpy as np


def fail(message: str) -> None:
    print(json.dumps({"ok": False, "error": message}), file=sys.stderr)
    raise SystemExit(2)


def load_config() -> dict[str, Any]:
    try:
        value = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        fail(f"stdin must contain one JSON object: {exc}")
    if not isinstance(value, dict):
        fail("stdin JSON must be an object")
    return value


def integer_option(cfg: dict[str, Any], name: str, default: int) -> int:
    value = cfg.get(name, default)
    if isinstance(value, bool) or not isinstance(value, int):
        fail(f"{name} must be an integer")
    return value


def number_option(cfg: dict[str, Any], name: str, default: float) -> float:
    value = cfg.get(name, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        fail(f"{name} must be a finite number")
    value = float(value)
    if not math.isfinite(value):
        fail(f"{name} must be finite")
    return value


def parse_config(cfg: dict[str, Any]) -> dict[str, Any]:
    for key in ("frame_path", "channel", "output_csv"):
        if not isinstance(cfg.get(key), str) or not cfg[key]:
            fail(f"{key} is required and must be a nonempty string")

    approximants = cfg.get(
        "approximants", ["SEOBNRv4_opt", "IMRPhenomD", "TaylorT4"]
    )
    if (not isinstance(approximants, list) or not approximants or
            any(not isinstance(x, str) or not x for x in approximants)):
        fail("approximants must be a nonempty list of nonempty strings")
    if len(set(approximants)) != len(approximants):
        fail("approximants must not contain duplicates")

    out = {
        "frame_path": cfg["frame_path"],
        "channel": cfg["channel"],
        "output_csv": cfg["output_csv"],
        "approximants": approximants,
        "min_mass": integer_option(cfg, "min_mass", 10),
        "max_mass": integer_option(cfg, "max_mass", 40),
        "highpass_hz": number_option(cfg, "highpass_hz", 15.0),
        "sample_rate_hz": number_option(cfg, "sample_rate_hz", 4096.0),
        "f_lower_hz": number_option(cfg, "f_lower_hz", 20.0),
        "condition_crop_s": number_option(cfg, "condition_crop_s", 4.0),
        "psd_segment_s": number_option(cfg, "psd_segment_s", 4.0),
        "psd_truncation_s": number_option(cfg, "psd_truncation_s", 4.0),
    }
    if out["min_mass"] <= 0 or out["max_mass"] < out["min_mass"]:
        fail("mass bounds must be positive integers with max_mass >= min_mass")
    if min(out["highpass_hz"], out["sample_rate_hz"], out["f_lower_hz"],
           out["condition_crop_s"], out["psd_segment_s"], out["psd_truncation_s"]) <= 0:
        fail("frequency and duration settings must be positive")
    if out["highpass_hz"] > out["f_lower_hz"]:
        fail("highpass_hz must not exceed f_lower_hz")
    if out["sample_rate_hz"] <= 2.0 * out["f_lower_hz"]:
        fail("sample_rate_hz Nyquist frequency must exceed f_lower_hz")
    return out


def condition_strain(c: dict[str, Any]):
    """Read frame strain and return conditioned strain plus matching PSD."""
    from pycbc.frame import read_frame
    from pycbc.filter import highpass, resample_to_delta_t
    from pycbc.psd import interpolate, inverse_spectrum_truncation

    if not Path(c["frame_path"]).is_file():
        fail(f"frame file does not exist: {c['frame_path']}")
    try:
        raw = read_frame(c["frame_path"], c["channel"])
    except Exception as exc:
        fail(f"could not read channel {c['channel']!r} from frame: {exc}")

    try:
        filtered = highpass(raw, c["highpass_hz"])
        conditioned = resample_to_delta_t(filtered, 1.0 / c["sample_rate_hz"])
        conditioned = conditioned.crop(c["condition_crop_s"], c["condition_crop_s"])
    except Exception as exc:
        fail(f"strain conditioning failed: {exc}")

    sample_rate = float(conditioned.sample_rate)
    segment_samples = int(round(c["psd_segment_s"] * sample_rate))
    truncation_samples = int(round(c["psd_truncation_s"] * sample_rate))
    if segment_samples < 2 or len(conditioned) < segment_samples:
        fail("conditioned strain is too short for the requested PSD segment")
    if truncation_samples < 2:
        fail("PSD truncation length is too short")
    try:
        # TimeSeries.psd uses Welch estimation. Interpolation aligns delta_f
        # with the full conditioned data before inverse-spectrum truncation.
        psd = conditioned.psd(c["psd_segment_s"])
        psd = interpolate(psd, conditioned.delta_f)
        psd = inverse_spectrum_truncation(
            psd, truncation_samples, low_frequency_cutoff=c["f_lower_hz"]
        )
    except Exception as exc:
        fail(f"PSD estimation/conditioning failed: {exc}")
    return conditioned, psd


def best_for_approximant(approximant: str, c: dict[str, Any], strain, psd):
    """Return (peak_snr, mass1, mass2, tested_count) for one model."""
    from pycbc.filter import matched_filter
    from pycbc.waveform import get_td_waveform

    best: tuple[float, int, int] | None = None
    tested = 0
    errors: list[str] = []
    for mass1 in range(c["min_mass"], c["max_mass"] + 1):
        for mass2 in range(c["min_mass"], mass1 + 1):
            try:
                template, _ = get_td_waveform(
                    approximant=approximant,
                    mass1=mass1,
                    mass2=mass2,
                    delta_t=strain.delta_t,
                    f_lower=c["f_lower_hz"],
                )
                physical_duration = float(template.duration)
                # The pre-resize duration is deliberately retained for crop size.
                template.resize(len(strain))
                template = template.cyclic_time_shift(template.start_time)
                snr = matched_filter(
                    template, strain, psd=psd, low_frequency_cutoff=c["f_lower_hz"]
                )
                left = c["psd_truncation_s"] + physical_duration
                right = c["psd_truncation_s"]
                if left + right >= float(snr.duration):
                    raise ValueError("template and transient crops leave no valid SNR samples")
                valid = snr.crop(left, right)
                values = np.abs(np.asarray(valid))
                finite = values[np.isfinite(values)]
                if finite.size == 0:
                    raise ValueError("valid SNR region contains no finite values")
                peak = float(np.max(finite))
                tested += 1
                if best is None or peak > best[0]:
                    best = (peak, mass1, mass2)
            except Exception as exc:
                errors.append(f"({mass1},{mass2}): {exc}")

    if best is None:
        detail = "; ".join(errors[:3])
        fail(f"no valid templates for approximant {approximant}: {detail}")
    return best[0], best[1], best[2], tested


def write_csv(path: str, rows: list[dict[str, Any]]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".tmp")
    try:
        with temporary.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["approximant", "snr", "total_mass"])
            writer.writeheader()
            writer.writerows(rows)
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()


def main() -> None:
    config = parse_config(load_config())
    strain, psd = condition_strain(config)
    rows: list[dict[str, Any]] = []
    tested_total = 0
    for approximant in config["approximants"]:
        peak, mass1, mass2, tested = best_for_approximant(
            approximant, config, strain, psd
        )
        tested_total += tested
        rows.append({
            "approximant": approximant,
            "snr": format(peak, ".12g"),
            "total_mass": mass1 + mass2,
        })
    write_csv(config["output_csv"], rows)
    print(json.dumps({
        "ok": True,
        "output_csv": config["output_csv"],
        "rows": rows,
        "templates_tested": tested_total,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
