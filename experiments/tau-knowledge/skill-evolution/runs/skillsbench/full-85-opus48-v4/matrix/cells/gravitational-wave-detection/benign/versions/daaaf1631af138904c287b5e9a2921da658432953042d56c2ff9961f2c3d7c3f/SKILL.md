---
name: gw-matched-filter-detection
description: >
  Detect compact binary (BBH) gravitational-wave signals in noisy LIGO-style
  frame (.gwf) detector data using PyCBC matched filtering. Conditions raw
  strain (highpass, resample, crop transients), estimates a Welch PSD, then runs
  a grid search over integer component masses (m1>=m2) for one or more waveform
  approximants (e.g. SEOBNRv4_opt, IMRPhenomD, TaylorT4), reporting the peak SNR
  and total mass of the best template per approximant and writing a results CSV.
  Use when a task supplies a .gwf file + channel and asks for best-SNR templates
  and total mass per approximant.
---

# Gravitational-Wave Matched-Filter Detection

## When to use
Use this Skill when a task gives you a gravitational-wave frame file (`.gwf`), a
channel name, a mass grid (integer solar masses), and a list of waveform
approximants, and asks you to report the strongest matched-filter detection
(peak SNR + total mass) for each approximant and write a CSV.

The current task:
- data file: `/root/data/PyCBC_T2_2.gwf`, channel `H1:TEST-STRAIN`
- approximants: `SEOBNRv4_opt`, `IMRPhenomD`, `TaylorT4`
- grid: mass1 and mass2 integer 10..40 solar masses, convention m1 >= m2
- output: `/root/detection_results.csv` with header `approximant,snr,total_mass`

Do not hardcode the above as answers; read actual values from the task request
at runtime and pass them to the entrypoint.

## Method (follows the frozen background)
1. **Load** the strain time series with `pycbc.frame.read_frame(path, channel)`.
2. **Condition** (order matters):
   - High-pass filter (default 15 Hz, below the matched-filter f_low) with
     `pycbc.filter.highpass`.
   - Resample to the target rate (default 4096 Hz) via
     `pycbc.filter.resample_to_delta_t` (resample AFTER highpass to avoid
     aliasing).
   - Crop filter transients from each end (default 2 s each side).
3. **PSD**: estimate with Welch (`conditioned.psd(seg_len_s)`, default 4 s),
   `interpolate` to the data `delta_f`, then `inverse_spectrum_truncation`
   with length `int(seg_len_s * sample_rate)` and
   `low_frequency_cutoff` = highpass frequency.
4. **Grid search**: for each approximant and each (m1, m2) with m1 >= m2 over
   the integer grid, generate the template with `get_td_waveform`
   (`f_lower` = low-frequency cutoff, default 20 Hz, `delta_t` of conditioned
   data). **Resize** the template to the conditioned data length and apply a
   **cyclic time shift** by its start time so the merger aligns to the array
   start. Run `pycbc.filter.matched_filter(template, data, psd=psd,
   low_frequency_cutoff=f_low)`.
5. **Crop corrupted SNR edges**: crop the START by (PSD segment length +
   template duration) and the END by (PSD segment length), then take
   `abs(snr)` (modulus maximizes over phase) and record the peak.
6. **Best per approximant**: keep the (m1,m2) with the highest peak |SNR|.
   total_mass = m1 + m2.
7. **Write CSV** `approximant,snr,total_mass` with one row per approximant, in
   the requested approximant order.

Why results differ per approximant: SEOBNRv4_opt and IMRPhenomD model full
inspiral-merger-ringdown and typically recover more SNR for BBH signals whose
merger sits in band, while TaylorT4 is inspiral-only and usually recovers less.

## Entrypoint
`scripts/detect.py` reads a JSON config on **stdin** and writes JSON to
**stdout**; it also writes the results CSV to disk.

Input JSON schema (all keys except `frame_path`/`channel` have defaults):
```json
{
  "frame_path": "/root/data/PyCBC_T2_2.gwf",
  "channel": "H1:TEST-STRAIN",
  "output_csv": "/root/detection_results.csv",
  "approximants": ["SEOBNRv4_opt", "IMRPhenomD", "TaylorT4"],
  "mass_min": 10,
  "mass_max": 40,
  "f_low": 20.0,
  "highpass_freq": 15.0,
  "sample_rate": 4096,
  "psd_segment_s": 4,
  "crop_s": 2
}
```

Output JSON:
```json
{
  "output_csv": "/root/detection_results.csv",
  "results": [
    {"approximant": "SEOBNRv4_opt", "snr": 12.3, "total_mass": 50,
     "mass1": 30, "mass2": 20}
  ],
  "errors": []
}
```

### Run example
```bash
echo '{"frame_path":"/root/data/PyCBC_T2_2.gwf","channel":"H1:TEST-STRAIN","output_csv":"/root/detection_results.csv","approximants":["SEOBNRv4_opt","IMRPhenomD","TaylorT4"],"mass_min":10,"mass_max":40}' \
  | python3 /app/environment/skills/current/scripts/detect.py
```

Then verify the CSV:
```bash
cat /root/detection_results.csv
```
Expect a header line `approximant,snr,total_mass` and one row per approximant,
with positive finite SNR values and integer total masses in
[2*mass_min, 2*mass_max].

## Validation to perform after running
- CSV exists and first line is exactly `approximant,snr,total_mass`.
- One data row per requested approximant, approximant names match exactly.
- Each `snr` parses as a positive finite float; a real BBH detection usually has
  SNR well above the noise floor (double digits), but do not assume a fixed
  value.
- Each `total_mass` is an integer within [2*mass_min, 2*mass_max].
- The `errors` list in stdout JSON is empty; if not, inspect which
  (approximant, mass) combos failed and why.

## Dependencies / environment
Requires PyCBC (and its deps: numpy, scipy, lalsuite) in the runtime. If PyCBC
is not installed and internet is allowed, install it:
```bash
pip install pycbc
```
The script imports PyCBC lazily and reports a clear error if it is missing.

## Failure handling
- Missing/unreadable frame file or wrong channel -> script exits nonzero with an
  error message; verify the path and channel from the task request.
- Individual template generation failures (some approximants reject certain
  parameters) are caught per combo, recorded in `errors`, and skipped; the grid
  search continues.
- If the data is too short to apply the full crop for a given template, the crop
  is clamped to the available length so the peak search still runs.
