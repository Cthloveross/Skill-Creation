# Simulator adapter protocol

Use an adapter only when `r2r_mpc.py` cannot safely discover the simulator API.
The adapter is a Python file supplied at runtime, not a modification of the
simulator. Pass its path as `adapter_module`.

It must define:

```python
def make_adapter(config: dict, simulator_module):
    return Adapter()
```

The returned object must implement:

```python
class Adapter:
    def build(self):
        """Return a newly initialized simulator instance."""

    def reset(self, sim):
        """Reset sim to the initial operating condition."""

    def get_state(self, sim):
        """Return [T1..T6, v1..v6] as 12 finite numeric values."""

    def set_state(self, sim, state):
        """Set precisely that 12-element physical state for local model probes."""

    def step(self, sim, control):
        """Apply six torques for exactly one simulator interval and advance sim."""

    def dt(self, sim):
        """Return positive sample interval in seconds."""

    def bounds(self, sim):
        """Return (lower, upper), each a six-element numeric sequence."""
```

`step` may return any simulator-native value; the driver always calls
`get_state` after it. `reset` and `step` must not silently reorder sections.
`set_state` is used only on fresh reset instances during numerical
linearization, never to overwrite the delivered closed-loop trajectory.

A useful adapter also makes the nominal initial torque available through an
optional `nominal_control(sim)` method. Otherwise the driver uses
`initial_control_inputs`/`nominal_control` in system configuration or zero.
