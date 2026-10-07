"""Mode selection and bounded longitudinal ACC command generation."""
from pid_controller import PIDController


def _find(mapping, names, default):
    if not isinstance(mapping, dict):
        return default
    for name in names:
        if name in mapping and mapping[name] is not None:
            return mapping[name]
    for value in mapping.values():
        if isinstance(value, dict):
            found = _find(value, names, None)
            if found is not None:
                return found
    return default


class AdaptiveCruiseControl:
    def __init__(self, config):
        config = config if isinstance(config, dict) else {}
        settings = config.get("acc_settings", config)
        vehicle = config.get("vehicle", {})
        self.set_speed = float(_find(settings, ("set_speed", "target_speed", "cruise_speed"), 30.0))
        self.headway = float(_find(settings, ("time_headway", "headway"), 1.5))
        self.min_gap = float(_find(settings, ("minimum_gap", "min_gap", "standstill_distance"), 10.0))
        self.ttc_threshold = float(_find(settings, ("emergency_ttc_threshold", "ttc_threshold"), 3.0))
        self.max_acc = float(_find(vehicle, ("max_acceleration", "max_acc", "acceleration_max"), _find(config, ("max_acceleration", "max_acc"), 3.0)))
        self.min_acc = float(_find(vehicle, ("max_deceleration", "min_acceleration", "min_acc", "deceleration_max"), _find(config, ("max_deceleration", "min_acc"), -8.0)))
        if self.min_acc > 0:
            self.min_acc = -self.min_acc

        gains = config.get("_pid_gains", {})
        speed_gains = gains.get("pid_speed", {"kp": 2.0, "ki": 0.0, "kd": 0.0})
        distance_gains = gains.get("pid_distance", {"kp": 0.35, "ki": 0.0, "kd": 0.0})
        self.speed_pid = PIDController(speed_gains["kp"], speed_gains["ki"], speed_gains["kd"])
        self.distance_pid = PIDController(distance_gains["kp"], distance_gains["ki"], distance_gains["kd"])
        self.active_mode = None
        self.last_ttc = None

    def _clamp(self, command):
        return max(self.min_acc, min(self.max_acc, command))

    def compute(self, ego_speed, lead_speed, distance, dt):
        ego_speed = float(ego_speed)
        valid_lead = lead_speed is not None and distance is not None
        if valid_lead:
            lead_speed = float(lead_speed)
            distance = float(distance)
            closing_speed = ego_speed - lead_speed
            self.last_ttc = distance / closing_speed if closing_speed > 0.0 else None
            mode = "emergency" if self.last_ttc is not None and self.last_ttc < self.ttc_threshold else "follow"
        else:
            self.last_ttc = None
            mode = "cruise"

        if mode != self.active_mode:
            # Reset both families at a mode boundary to avoid stale I/D state.
            self.speed_pid.reset()
            self.distance_pid.reset()
            self.active_mode = mode

        if mode == "emergency":
            return self.min_acc, mode, self.headway * ego_speed + self.min_gap - distance

        if mode == "cruise":
            command = self.speed_pid.compute(self.set_speed - ego_speed, dt)
            return self._clamp(command), mode, None

        distance_error = self.headway * ego_speed + self.min_gap - distance
        # Positive error means the observed gap is too small, hence braking.
        command = -self.distance_pid.compute(distance_error, dt)
        # Never accelerate more aggressively than a cruise request to set speed.
        cruise_cap = self.speed_pid.preview(self.set_speed - ego_speed, dt)
        command = min(command, cruise_cap)
        return self._clamp(command), mode, distance_error
