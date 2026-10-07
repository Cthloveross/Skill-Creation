"""Mode selection and controller logic for adaptive cruise control."""
from pid_controller import PIDController


def _find(mapping, names, default):
    """Recursively find a scalar setting under one of the supplied names."""
    if not isinstance(mapping, dict):
        return default
    names = {name.lower() for name in names}
    for key, value in mapping.items():
        if str(key).lower() in names and not isinstance(value, dict):
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
        self.min_gap = float(_find(config, ("min_gap", "minimum_gap", "min_distance"), 10.0))
        self.ttc_threshold = float(_find(config, ("emergency_ttc_threshold", "ttc_threshold"), 3.0))
        self.max_acceleration = float(_find(config, ("max_acceleration", "max_accel"), 3.0))
        braking = float(_find(config, ("min_acceleration", "max_deceleration", "max_decel"), -8.0))
        self.min_acceleration = -abs(braking) if braking >= 0.0 else braking
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

    def _clamp(self, command):
        return max(self.min_acceleration, min(self.max_acceleration, float(command)))

    def compute(self, ego_speed, lead_speed, distance, dt):
        """Return (bounded acceleration, mode, safe_gap_minus_distance or None)."""
        ego_speed = float(ego_speed)
        if lead_speed is None or distance is None:
            self._transition("cruise")
            return (
                self._clamp(self.speed_controller.compute(self.set_speed - ego_speed, dt)),
                "cruise",
                None,
            )

        lead_speed = float(lead_speed)
        distance = float(distance)
        distance_error = self.time_headway * ego_speed + self.min_gap - distance
        closing_speed = ego_speed - lead_speed
        ttc = distance / closing_speed if closing_speed > 0.0 else None
        if ttc is not None and ttc < self.ttc_threshold:
            self._transition("emergency")
            return self.min_acceleration, "emergency", distance_error

        self._transition("follow")
        # Positive error means too close, so it must produce a negative command.
        command = -self.distance_controller.compute(distance_error, dt)
        # A following controller may not accelerate ego above the speed setpoint.
        command = min(command, 0.5 * (self.set_speed - ego_speed))
        return self._clamp(command), "follow", distance_error
