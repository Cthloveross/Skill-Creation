"""Public discrete PID controller for the generated ACC project."""


class PIDController:
    """PID with integral clamping and the standard zero-initial-error update."""

    def __init__(self, kp, ki, kd):
        self.kp = float(kp)
        self.ki = float(ki)
        self.kd = float(kd)
        self.reset()

    def reset(self):
        self.integral = 0.0
        # Zero is the discrete initial condition: first derivative is error/dt.
        self.previous_error = 0.0

    def compute(self, error, dt):
        if dt <= 0:
            raise ValueError("dt must be positive")
        error = float(error)
        self.integral += error * dt
        # Bound stored state so a saturated actuator cannot wind up indefinitely.
        self.integral = max(-200.0, min(200.0, self.integral))
        derivative = (error - self.previous_error) / dt
        self.previous_error = error
        return self.kp * error + self.ki * self.integral + self.kd * derivative

    def preview(self, error, dt):
        """Calculate the next output without mutating PID state."""
        if dt <= 0:
            raise ValueError("dt must be positive")
        error = float(error)
        integral = max(-200.0, min(200.0, self.integral + error * dt))
        derivative = (error - self.previous_error) / dt
        return self.kp * error + self.ki * integral + self.kd * derivative
