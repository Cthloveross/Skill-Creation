"""Small discrete-time PID controller used by the ACC project."""


class PIDController:
    """PID with bounded integral state to limit windup under output saturation."""

    def __init__(self, kp, ki, kd, integral_limit=100.0):
        self.kp = float(kp)
        self.ki = float(ki)
        self.kd = float(kd)
        self.integral_limit = abs(float(integral_limit))
        self.reset()

    def reset(self):
        self.integral = 0.0
        self.previous_error = None

    def compute(self, error, dt):
        """Advance PID state and return the unconstrained controller output."""
        error = float(error)
        dt = float(dt)
        if dt <= 0.0:
            raise ValueError("PID dt must be positive")
        self.integral += error * dt
        self.integral = max(-self.integral_limit, min(self.integral_limit, self.integral))
        derivative = 0.0 if self.previous_error is None else (error - self.previous_error) / dt
        self.previous_error = error
        return self.kp * error + self.ki * self.integral + self.kd * derivative
