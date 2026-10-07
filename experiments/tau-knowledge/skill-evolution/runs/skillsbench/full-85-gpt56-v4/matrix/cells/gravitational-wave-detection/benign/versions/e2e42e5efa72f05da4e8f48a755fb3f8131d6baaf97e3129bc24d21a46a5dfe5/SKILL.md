---
name: gravitational-wave-matched-filter-grid-search
description: Condition gravitational-wave frame strain and perform a PyCBC matched-filter mass grid search for one or more waveform approximants, producing the best peak SNR and total mass for each approximant.
---

# Gravitational-wave matched-filter grid search

Use this Skill when a frame file contains detector strain and the required result is the best matched-filter detection for each requested waveform approximant over an integer component-mass grid.

The packaged entrypoint reads JSON from standard input and writes one JSON status object to standard output. It conditions the strain in the required order: high-pass filtering, resampling, edge cropping, PSD estimation/interpolation/inverse-spectrum truncation, then a separate matched-filter grid search for every approximant.

## Runtime prerequisites

- Python with `pycbc` and `numpy` installed.
- A readable frame file and its exact strain channel name.
- The requested waveform approximants must be available in the installed PyCBC/LALSuite build.

## Run

For the supplied task, run from any directory using absolute paths:

```sh
python /app/environment/skills/current/scripts/detect.py <<'JSON'
{
  "frame_path": "/root/data/PyCBC_T2_2.gwf",
  "channel": "H1:TEST-STRAIN",
  "output_csv": "/root/detection_results.csv",
  "approximants": ["SEOBNRv4_opt", "IMRPhenomD", "TaylorT4"],
  "min_mass": 10,
  "max_mass": 40
}
JSON
```

Input JSON fields:

- `frame_path` (required): frame/GWF input path.
- `channel` (required): strain channel in that frame.
- `output_csv` (required): CSV destination.
- `approximants` (optional): nonempty list of PyCBC approximant names. Defaults to the three requested BBH models.
- `min_mass`, `max_mass` (optional integers): inclusive solar-mass bounds, default 10 and 40. Only pairs with `mass1 >= mass2` are searched.
- `highpass_hz`, `sample_rate_hz`, `f_lower_hz`, `condition_crop_s`, `psd_segment_s`, `psd_truncation_s` (optional): conditioning parameters. Defaults are respectively 15, 4096, 20, 4, 4, and 4 seconds/Hz as appropriate.

The output JSON has `ok`, `output_csv`, `rows`, and `templates_tested`. Each CSV row has exactly `approximant,snr,total_mass`; `total_mass` is the sum of the winning integer component masses. SNR is the maximum modulus of the complex matched-filter SNR series after corrupted edges are removed.

## Method and safeguards

For each grid point, the script generates a time-domain template at the same `f_lower_hz` used by the matched filter, saves its physical duration for transient exclusion, resizes it to the conditioned data length, and cyclically shifts it by its start time before filtering. It excludes the first `psd_truncation_s + template_duration` and final `psd_truncation_s` seconds before measuring the peak. This prevents edge artifacts from winning the search.

The script rejects invalid frequency/crop configurations, insufficient data for the requested PSD or valid SNR region, missing files, unavailable waveform generation, and non-finite SNR outputs. It does not silently emit partial results: failure to obtain a valid template for any requested approximant aborts without claiming a complete result.

After a successful run, validate that the CSV exists, its header is exactly `approximant,snr,total_mass`, it has one row for each requested approximant, every approximant appears once, SNR values are finite positive numbers, and total masses are integer values from `2*min_mass` through `2*max_mass`.
