# First-order thermal ID and PI control: derivations

## Plant model
A room with heat loss under constant heater power `u` (percent) behaves as a
stable first-order lag:

    tau * dT/dt = -(T - T_ambient) + K_phys * u

Step response from an initial temperature `T0` to the asymptote `T_ss`:

    T(t) = T_ss - (T_ss - T0) * exp(-t / tau)
    T_ss = T_ambient + K * u,  with steady-state gain K = (T_ss - T_ambient)/u

`K` has units degrees-C per percent-power; `tau` is the time constant in seconds.

## Identification from a step test
For a fixed `tau`, `T(t) = a + b*exp(-t/tau)` is linear in `(a,b)`, so for each
candidate `tau` we solve a 2x2 least-squares problem in closed form and keep the
`tau` with the smallest sum of squared residuals (coarse grid then local
refinement). Then `T_ss = a`, `T0 = a + b`. The pre-heat baseline reading is the
ambient temperature, giving `K = (T_ss - ambient)/u`. `r_squared = 1 - SSE/SST`;
`fitting_error` is the RMS residual. A good fit on a well-excited response has
`r_squared` near 1; if it is low, excite longer or at a different power.

## Lambda / IMC PI tuning
For a first-order plant G(s) = K/(tau*s + 1) with no appreciable delay, the IMC
(internal model control) PI tuning with closed-loop time constant `lambda` is:

    Kc = tau / (K * lambda)      -> Kp
    Ti = tau                      -> Ki = Kc / Ti = 1 / (K * lambda)
    Kd = 0

The nominal closed loop is first-order with time constant `lambda`, so a 2%/5%
settling time is roughly 4*lambda..5*lambda with essentially no overshoot in the
linear (unsaturated) regime. We default `lambda` so ~5*lambda stays under the
120 s settling target, clamped to a sensible range. Because the heater saturates
at 0-100%, an aggressive (small) `lambda` can still produce overshoot from a
saturated start; increase `lambda` to trade speed for a smoother, lower-overshoot
response.

## Anti-windup
When the command saturates, continuing to integrate error inflates the integral
and causes large overshoot once saturation lifts. We use conditional
integration: the integral is only advanced when the unsaturated output is within
[0,100], or when integrating would move the output back toward the feasible
range. Output is always clamped to [0,100]%.

## Metrics (as computed, relative to control start)
- rise_time: first time temperature reaches 90% of the commanded step
  `initial + 0.9*(setpoint - initial)`.
- overshoot: `max(0, (max_temp - setpoint)) / (setpoint - initial)` (fraction;
  target < 0.10).
- settling_time: earliest time after which `|T - setpoint| <= band` holds for
  all later samples; `band` defaults to the 0.5 C steady-state target.
- steady_state_error: `|mean(last 20% of samples) - setpoint|`.
- max_temp: maximum temperature over the control trace.

## Tuning loop
If a target fails after `run_hvac.py`:
- overshoot too high  -> increase `lambda` (or add small `Kd`).
- settling too slow   -> decrease `lambda` (watch overshoot/saturation).
- steady-state error  -> ensure `Ki > 0` and the run is long enough to settle.
- poor fit (low R^2)  -> longer `calib_duration` or different `calib_power`
  (keep the heated steady state below 30 C).
Re-run and re-validate; the controlled trace, not assumed dynamics, is
authoritative.
