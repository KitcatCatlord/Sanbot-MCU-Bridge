from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SafetyLimits:
    """Configurable motion limits for sanity/safety checks.

    These limits are intentionally conservative. Adjust if you know your
    environment and hardware constraints. All values are inclusive bounds.
    """

    # Wheels
    wheel_speed_min: int = 0
    wheel_speed_max: int = 200           # device max is 255; keep some headroom
    wheel_time_ms_min: int = 1
    wheel_time_ms_max: int = 5000        # 5s default cap for time-based moves
    wheel_distance_mm_min: int = 0
    wheel_distance_mm_max: int = 3000    # 3m cap to avoid long runs
    wheel_spin_deg_min: int = 0
    wheel_spin_deg_max: int = 360        # limit to one full rotation by default

    # Head
    head_speed_min: int = 0
    head_speed_max: int = 200            # device max is 255; keep headroom
    head_abs_h_min: int = -180
    head_abs_h_max: int = 180
    head_abs_v_min: int = -90
    head_abs_v_max: int = 90
    head_axis_deg_min: int = 0
    head_axis_deg_max: int = 90
    head_time_ms_min: int = 1
    head_time_ms_max: int = 600000       # matches existing upper bound

    # Hands/Arms
    hand_speed_min: int = 0
    hand_speed_max: int = 200            # device max is 255; keep headroom
    hand_deg_min: int = 0
    hand_deg_max: int = 90
    hand_time_ms_min: int = 1
    hand_time_ms_max: int = 600000


class SafetyError(ValueError):
    pass


class SafetyValidator:
    """Validator enforcing motion constraints. Raise SafetyError on violation.

    Set unsafe=True to bypass checks (not recommended).
    """

    def __init__(self, limits: SafetyLimits | None = None, unsafe: bool = False):
        self.limits = limits or SafetyLimits()
        self.unsafe = unsafe

    def set_unsafe(self, unsafe: bool):
        self.unsafe = unsafe

    # Wheels
    def wheels_angle(self, speed: int, deg: int):
        if self.unsafe:
            return
        self._in_range('wheel speed', speed, self.limits.wheel_speed_min, self.limits.wheel_speed_max)
        self._in_range('wheel spin deg', deg, self.limits.wheel_spin_deg_min, self.limits.wheel_spin_deg_max)

    def wheels_time(self, ms: int):
        if self.unsafe:
            return
        self._in_range('wheel time ms', ms, self.limits.wheel_time_ms_min, self.limits.wheel_time_ms_max)

    def wheels_distance(self, speed: int, mm: int):
        if self.unsafe:
            return
        self._in_range('wheel speed', speed, self.limits.wheel_speed_min, self.limits.wheel_speed_max)
        self._in_range('wheel distance mm', mm, self.limits.wheel_distance_mm_min, self.limits.wheel_distance_mm_max)

    # Head
    def head_absolute(self, hdeg: int, vdeg: int):
        if self.unsafe:
            return
        self._in_range('head hdeg', hdeg, self.limits.head_abs_h_min, self.limits.head_abs_h_max)
        self._in_range('head vdeg', vdeg, self.limits.head_abs_v_min, self.limits.head_abs_v_max)

    def head_axis(self, speed: int, deg: int):
        if self.unsafe:
            return
        self._in_range('head speed', speed, self.limits.head_speed_min, self.limits.head_speed_max)
        self._in_range('head deg', deg, self.limits.head_axis_deg_min, self.limits.head_axis_deg_max)

    def head_time(self, ms: int):
        if self.unsafe:
            return
        self._in_range('head time ms', ms, self.limits.head_time_ms_min, self.limits.head_time_ms_max)

    def head_noangle(self, speed: int):
        if self.unsafe:
            return
        self._in_range('head speed', speed, self.limits.head_speed_min, self.limits.head_speed_max)

    # Hands
    def hand_angle(self, speed: int, deg: int):
        if self.unsafe:
            return
        self._in_range('hand speed', speed, self.limits.hand_speed_min, self.limits.hand_speed_max)
        self._in_range('hand deg', deg, self.limits.hand_deg_min, self.limits.hand_deg_max)

    def hand_time(self, ms: int, deg: int):
        if self.unsafe:
            return
        self._in_range('hand time ms', ms, self.limits.hand_time_ms_min, self.limits.hand_time_ms_max)
        self._in_range('hand deg', deg, self.limits.hand_deg_min, self.limits.hand_deg_max)

    def hand_noangle(self, speed: int):
        if self.unsafe:
            return
        self._in_range('hand speed', speed, self.limits.hand_speed_min, self.limits.hand_speed_max)

    # Internal helper
    def _in_range(self, name: str, val: int, min_v: int, max_v: int):
        if val < min_v or val > max_v:
            raise SafetyError(f"{name} out of range [{min_v}..{max_v}]: {val}")

