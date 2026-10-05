---
name: gravitational-wave-matched-filter-grid-search
description: Condition gravitational-wave frame strain data and run a PyCBC matched-filter mass grid search for requested binary-black-hole waveform approximants, producing one peak-SNR result per approximant in CSV form.
---

# Gravitational-wave matched-filter grid search

Use this Skill when a local GWF frame and strain channel must be searched for compact-binary signals with a discrete component-mass template bank.

## Prerequisites

- Python must have `pycbc` (including its LALSuite waveform support) and NumPy available.
- The requested GWF file must be readable by `pycbc.frame.read_frame` and contain the requested channel.
- There must be enough usable conditioned data to estimate a PSD and to crop both PSD/template edge-corruption regions. The script fails explicitly rather than reporting an edge artifact if this is not true.

## Method

`scripts/run_detection.py` performs the complete search:

1. Reads the supplied frame/channel, high-pass filters it, resamples it, and removes filter-transient samples from both ends.
2. Estimates a Welch PSD, interpolates it to the conditioned strain frequency spacing, and applies inverse-spectrum truncation.
3. Searches all integer masses in the inclusive supplied range, retaining only `mass1 >= mass2` combinations.
4. Generates a time-domain template at a consistent low-frequency cutoff. `IMRPhenomD`, which is normally frequency-domain, is converted to a time-domain waveform through PyCBC's FD-to-TD interface.
5. Records each template's original duration, resizes it to the strain length, cyclically shifts it by its original start time, filters it against the conditioned strain, and searches `abs(complex_snr)` only after cropping PSD and template-corrupted boundaries.
6. Selects the largest valid peak separately for each requested approximant and writes exactly the requested CSV columns.

The total mass in every result is `mass1 + mass2`; the component pair itself is retained only in the JSON execution summary for auditability.

## Run

Provide a JSON object on stdin. All paths are supplied by the caller; no input data or output values are embedded in the Skill.

```bash
python scripts/run_detection.py <<'JSON'
{
  "data_path": "/root/data/PyCBC_T2_2.gwf",
  "channel": "H1:TEST-STRAIN",
  "output_path": "/root/detection_results.csv",
  "approximants": ["SEOBNRv4_opt", "IMRPhenomD", "TaylorT4"],
  "mass_min": 10,
  "mass_max": 40,
  "low_frequency_cutoff_hz": 20.0,
  "highpass_hz": 15.0,
  "target_sample_rate_hz": 4096,
  "transient_crop_seconds": 4.0,
  "psd_segment_seconds": 4.0,
  "psd_truncation_seconds": 4.0
}
JSON
```

### Input schema

- `data_path`, `channel`, `output_path`: required strings.
- `approximants`: nonempty list of PyCBC approximant names.
- `mass_min`, `mass_max`: inclusive integer solar-mass bounds, with `mass_min > 0` and `mass_max >= mass_min`.
- Frequency, sample-rate, and duration fields shown above are positive numeric configuration values. The low-frequency cutoff must be at least the high-pass frequency.

### Output and validation

On success, stdout is JSON containing `output_path` and a result object for each approximant. The output file is atomically written as UTF-8 CSV with this exact header:

```csv
approximant,snr,total_mass
```

It has one row per input approximant, in input order. Before writing, the script validates that every approximant has a finite positive SNR, that total mass agrees with its winning mass pair, and that the output contains no duplicate approximant names. A missing waveform implementation, unreadable frame/channel, invalid configuration, non-finite PSD, or insufficient uncorrupted SNR samples is a failure and must be corrected rather than replaced with a guessed result.
