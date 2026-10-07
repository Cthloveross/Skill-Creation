"""Discrete PID controller used by the ACC project."""


class PIDController:
    def __init__(self, kp, ki, kd):
        self.kp = float(kp)
        self.ki = float(ki)
        self.kd = float(kd)
        self.integral = 0.0
        self.previous_error = None
        self.integral_limit = 200.0

    def reset(self):
        """Restore the controller to its initial state."""
        self.integral = 0.0
        self.previous_error = None

    def compute(self, error, dt):
        """Return P + I + D for a positive discrete timestep."""
        if float(dt) <= 0.0:
            raise ValueError("PID timestep must be positive")
        error = float(error)
        dt = float(dt)
        self.integral = max(
            -self.integral_limit,
            min(self.integral_limit, self.integral + error * dt),
        )
        derivative = 0.0 if self.previous_error is None else (error - self.previous_error) / dt
        self.previous_error = error
        return self.kp * error + self.ki * self.integral + self.kd * derivative
