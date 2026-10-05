"""Mode logic and controllers for a longitudinal adaptive cruise controller."""
from pid_controller import PIDController


def _flatten(mapping):
    result = {}
    if isinstance(mapping, dict):
        for key, value in mapping.items():
            result[str(key)] = value
            if isinstance(value, dict):
                result.update(_flatten(value))
    return result


def _number(values, names, default):
    for name in names:
        if name in values and values[name] is not None:
            return float(values[name])
    return float(default)


class AdaptiveCruiseControl:
    """ACC with mutually exclusive cruise, follow, and emergency control."""

    def __init__(self, config):
        values = _flatten(config)
        self.set_speed = _number(values, ("set_speed", "target_speed", "cruise_speed"), 30.0)
        self.time_headway = _number(values, ("time_headway", "headway"), 1.5)
        self.min_gap = _number(
            values,
            ("min_distance", "min_gap", "minimum_gap", "d_min", "standstill_distance"),
            10.0,
        )
        self.emergency_ttc = _number(values, ("emergency_ttc_threshold", "ttc_threshold", "emergency_ttc"), 3.0)
        self.min_accel = _number(values, ("min_acceleration", "max_deceleration", "min_accel"), -8.0)
        self.max_accel = _number(values, ("max_acceleration", "max_accel"), 3.0)
        if self.min_accel > 0.0:
            self.min_accel = -self.min_accel
        if self.min_accel >= self.max_accel:
            raise ValueError("acceleration limits are invalid")
        gains = config.get("pid_gains", {}) if isinstance(config, dict) else {}
        speed = gains.get("pid_speed", gains.get("speed", {})) if isinstance(gains, dict) else {}
        distance = gains.get("pid_distance", gains.get("distance", {})) if isinstance(gains, dict) else {}
        self.speed_pid = PIDController(speed.get("kp", 1.0), speed.get("ki", 0.1), speed.get("kd", 0.0))
        self.distance_pid = PIDController(distance.get("kp", 0.5), distance.get("ki", 0.05), distance.get("kd", 0.1))
        self.last_mode = None
        self.ttc = None

    def _transition(self, mode):
        if mode == self.last_mode:
            return
        if mode == "cruise":
            self.distance_pid.reset()
        elif mode == "follow":
            self.speed_pid.reset()
        else:
            self.speed_pid.reset()
            self.distance_pid.reset()
        self.last_mode = mode

    def compute(self, ego_speed, lead_speed, distance, dt):
        """Return (bounded_acceleration, mode, distance_error_or_None)."""
        ego_speed = max(0.0, float(ego_speed))
        self.ttc = None
        if lead_speed is None or distance is None:
            mode = "cruise"
            self._transition(mode)
            command = self.speed_pid.compute(self.set_speed - ego_speed, dt)
            return max(self.min_accel, min(self.max_accel, command)), mode, None

        lead_speed = float(lead_speed)
        distance = max(0.0, float(distance))
        closing_speed = ego_speed - lead_speed
        if closing_speed > 0.0:
            self.ttc = distance / closing_speed
        safe_gap = self.time_headway * ego_speed + self.min_gap
        distance_error = safe_gap - distance
        if self.ttc is not None and self.ttc < self.emergency_ttc:
            mode = "emergency"
            self._transition(mode)
            return self.min_accel, mode, distance_error

        mode = "follow"
        self._transition(mode)
        # Positive safe_gap - distance means too close, hence negate PID output.
        distance_command = -self.distance_pid.compute(distance_error, dt)
        # A follow controller may not command more acceleration than cruise would allow.
        speed_ceiling = self.speed_pid.kp * (self.set_speed - ego_speed)
        speed_ceiling = max(self.min_accel, min(self.max_accel, speed_ceiling))
        command = min(distance_command, speed_ceiling)
        return max(self.min_accel, min(self.max_accel, command)), mode, distance_error
