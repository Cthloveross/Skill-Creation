"""Mode selection and bounded longitudinal ACC command generation."""
from pid_controller import PIDController

def _find(mapping, names, default):
    if not isinstance(mapping, dict): return default
    for name in names:
        if name in mapping and mapping[name] is not None: return mapping[name]
    for value in mapping.values():
        if isinstance(value, dict):
            got = _find(value, names, None)
            if got is not None: return got
    return default

class AdaptiveCruiseControl:
    def __init__(self, config):
        settings = config.get("acc_settings", config) if isinstance(config, dict) else {}
        vehicle = config.get("vehicle", {}) if isinstance(config, dict) else {}
        self.set_speed = float(_find(settings, ("set_speed", "target_speed", "cruise_speed"), 30.0))
        self.headway = float(_find(settings, ("time_headway", "headway"), 1.5))
        self.min_gap = float(_find(settings, ("minimum_gap", "min_gap", "standstill_distance"), 10.0))
        self.ttc_threshold = float(_find(settings, ("emergency_ttc_threshold", "ttc_threshold"), 3.0))
        self.max_acc = float(_find(vehicle, ("max_acceleration", "max_acc", "acceleration_max"), _find(config, ("max_acceleration", "max_acc"), 3.0)))
        self.min_acc = float(_find(vehicle, ("max_deceleration", "min_acceleration", "min_acc", "deceleration_max"), _find(config, ("max_deceleration", "min_acc"), -8.0)))
        if self.min_acc > 0: self.min_acc = -self.min_acc
        gains = config.get("_pid_gains", {}) if isinstance(config, dict) else {}
        sg = gains.get("pid_speed", {"kp": 0.8, "ki": 0.08, "kd": 0.05})
        dg = gains.get("pid_distance", {"kp": 0.3, "ki": 0.02, "kd": 0.2})
        self.speed_pid = PIDController(sg["kp"], sg["ki"], sg["kd"])
        self.distance_pid = PIDController(dg["kp"], dg["ki"], dg["kd"])
        self.active_mode = None
        self.last_ttc = None

    def compute(self, ego_speed, lead_speed, distance, dt):
        ego_speed = float(ego_speed)
        valid_lead = lead_speed is not None and distance is not None
        if valid_lead:
            lead_speed, distance = float(lead_speed), float(distance)
            closing = ego_speed - lead_speed
            self.last_ttc = distance / closing if closing > 0 else None
            emergency = self.last_ttc is not None and self.last_ttc < self.ttc_threshold
            mode = "emergency" if emergency else "follow"
        else:
            mode, self.last_ttc = "cruise", None
        if mode != self.active_mode:
            # Reset on every control-family transition to avoid stale integral/derivative state.
            self.speed_pid.reset(); self.distance_pid.reset(); self.active_mode = mode
        if mode == "emergency":
            return self.min_acc, mode, self.headway * ego_speed + self.min_gap - distance
        if mode == "cruise":
            command = self.speed_pid.compute(self.set_speed - ego_speed, dt)
            return max(self.min_acc, min(self.max_acc, command)), mode, None
        distance_error = self.headway * ego_speed + self.min_gap - distance
        # Positive distance error means too close, so negate the distance PID command.
        command = -self.distance_pid.compute(distance_error, dt)
        # A non-mutating speed PID preview caps follow acceleration below cruise demand.
        cruise_cap = self.speed_pid.preview(self.set_speed - ego_speed, dt)
        command = min(command, cruise_cap)
        return max(self.min_acc, min(self.max_acc, command)), mode, distance_error
