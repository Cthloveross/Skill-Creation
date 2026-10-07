"""Discrete PID controller used by the generated ACC project."""

class PIDController:
    def __init__(self, kp, ki, kd):
        self.kp, self.ki, self.kd = float(kp), float(ki), float(kd)
        self.reset()

    def reset(self):
        self.integral = 0.0
        self.previous_error = None

    def compute(self, error, dt):
        if dt <= 0:
            raise ValueError("dt must be positive")
        error = float(error)
        derivative = 0.0 if self.previous_error is None else (error - self.previous_error) / dt
        self.integral += error * dt
        # A finite clamp prevents a saturated actuator from accumulating unbounded windup.
        self.integral = max(-200.0, min(200.0, self.integral))
        self.previous_error = error
        return self.kp * error + self.ki * self.integral + self.kd * derivative

    def preview(self, error, dt):
        """Return the next PID output without changing controller state."""
        derivative = 0.0 if self.previous_error is None else (float(error) - self.previous_error) / dt
        integral = max(-200.0, min(200.0, self.integral + float(error) * dt))
        return self.kp * float(error) + self.ki * integral + self.kd * derivative
