"""Mode selection and controller logic for adaptive cruise control."""
from pid_controller import PIDController


def _find(mapping, names, default):
    """Find a scalar setting recursively, accepting common configuration names."""
    if not isinstance(mapping, dict):
        return default
    wanted = {n.lower() for n in names}
    for key, value in mapping.items():
        if str(key).lower() in wanted and not isinstance(value, dict):
            return value
    for value in mapping.values():
        if isinstance(value, dict):
            found = _find(value, names, None)
            if found is not None:
                return found
    return default


class AdaptiveCruiseControl:
    def __init__(self, config):
        self.config = config
        self.set_speed = float(_find(config, ("set_speed", "target_speed", "cruise_speed"), 30.0))
        self.time_headway = float(_find(config, ("time_headway", "headway"), 1.5))
        self.min_gap = float(_find(config, ("min_gap", "min_distance", "standstill_distance"), 10.0))
        self.ttc_threshold = float(_find(config, ("emergency_ttc_threshold", "ttc_threshold", "emergency_ttc"), 3.0))
        self.max_acceleration = float(_find(config, ("max_acceleration", "max_accel"), 3.0))
        # A configuration may state maximum deceleration as a positive magnitude.
        min_value = _find(config, ("min_acceleration", "max_deceleration", "max_decel"), -8.0)
        self.min_acceleration = -abs(float(min_value)) if float(min_value) >= 0 else float(min_value)
        speed = config.get("pid_speed", {}) if isinstance(config, dict) else {}
        distance = config.get("pid_distance", {}) if isinstance(config, dict) else {}
        self.speed_controller = PIDController(speed.get("kp", 0.5), speed.get("ki", 0.08), speed.get("kd", 0.05))
        self.distance_controller = PIDController(distance.get("kp", 0.25), distance.get("ki", 0.02), distance.get("kd", 0.12))
        self.mode = None

    def _transition(self, new_mode):
        if new_mode != self.mode:
            self.speed_controller.reset()
            self.distance_controller.reset()
            self.mode = new_mode

    def compute(self, ego_speed, lead_speed, distance, dt):
        """Return (bounded_acceleration, mode, safe_gap_minus_distance_or_None)."""
        ego_speed = float(ego_speed)
        if lead_speed is None or distance is None:
            self._transition("cruise")
            command = self.speed_controller.compute(self.set_speed - ego_speed, dt)
            return self._clamp(command), "cruise", None

        lead_speed = float(lead_speed)
        distance = float(distance)
        closing = ego_speed - lead_speed
        ttc = distance / closing if closing > 0.0 else None
        if ttc is not None and ttc < self.ttc_threshold:
            self._transition("emergency")
            return self.min_acceleration, "emergency", self.time_headway * ego_speed + self.min_gap - distance

        self._transition("follow")
        distance_error = self.time_headway * ego_speed + self.min_gap - distance
        # Positive distance_error means too close, hence negate positive PID output.
        command = -self.distance_controller.compute(distance_error, dt)
        # This non-integrating ceiling preserves distance-loop exclusivity in follow mode.
        speed_ceiling = 0.5 * (self.set_speed - ego_speed)
        command = min(command, speed_ceiling)
        return self._clamp(command), "follow", distance_error

    def _clamp(self, command):
        return max(self.min_acceleration, min(self.max_acceleration, float(command)))
