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
        self.integral = 0.0
        self.previous_error = None

    def compute(self, error, dt):
        """Return kp*error + ki*integral + kd*derivative for positive dt."""
        if dt <= 0:
            raise ValueError("PID timestep must be positive")
        error = float(error)
        candidate = self.integral + error * dt
        self.integral = max(-self.integral_limit, min(self.integral_limit, candidate))
        derivative = 0.0 if self.previous_error is None else (error - self.previous_error) / dt
        self.previous_error = error
        return self.kp * error + self.ki * self.integral + self.kd * derivative
