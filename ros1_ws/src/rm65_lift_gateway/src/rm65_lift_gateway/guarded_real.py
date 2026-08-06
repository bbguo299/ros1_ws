"""Disabled real-execution contract for the RM65 gateway.

This module validates future trajectory profiles but deliberately contains no
ROS control clients or publishers. The guarded mode always rejects actuator
commands until a separate, explicitly authorized execution implementation is
available.
"""

from __future__ import absolute_import

from datetime import datetime, timezone
import math


REQUIRED_JOINT_NAMES = ("joint1", "joint2", "joint3", "joint4", "joint5", "joint6")
REQUIRED_TRAJECTORIES = ("prepare", "lift")
REQUIRED_POINT_FIELDS = ("positions", "velocities", "accelerations", "time_from_start_s")


def _utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class GuardedTrajectoryProfiles(object):
    """Validates profile shape without constructing or sending ROS goals."""

    def __init__(self, profiles):
        if not isinstance(profiles, dict):
            raise ValueError("profiles must be a mapping")
        self._valid_names = []
        self._invalid_reasons = {}
        for name, profile in profiles.items():
            error = self._validate_profile(name, profile)
            if error:
                self._invalid_reasons[name] = error
            else:
                self._valid_names.append(name)

    def snapshot(self):
        return {
            "valid_profile_names": sorted(self._valid_names),
            "invalid_profile_reasons": dict(sorted(self._invalid_reasons.items())),
        }

    @classmethod
    def _validate_profile(cls, name, profile):
        if not isinstance(name, str) or not name:
            return "profile name must be a non-empty string"
        if not isinstance(profile, dict):
            return "profile must be a mapping"
        for trajectory_name in REQUIRED_TRAJECTORIES:
            error = cls._validate_trajectory(profile.get(trajectory_name), trajectory_name)
            if error:
                return error
        return ""

    @staticmethod
    def _validate_trajectory(trajectory, name):
        if not isinstance(trajectory, dict):
            return "%s must be a mapping" % name
        if trajectory.get("joint_names") != list(REQUIRED_JOINT_NAMES):
            return "%s.joint_names must be %s" % (name, list(REQUIRED_JOINT_NAMES))
        tolerance = trajectory.get("final_joint_tolerance_rad")
        timeout = trajectory.get("completion_timeout_s")
        if not GuardedTrajectoryProfiles._is_positive_number(tolerance):
            return "%s.final_joint_tolerance_rad must be greater than zero" % name
        if not GuardedTrajectoryProfiles._is_positive_number(timeout):
            return "%s.completion_timeout_s must be greater than zero" % name
        points = trajectory.get("points")
        if not isinstance(points, list) or not points:
            return "%s.points must be a non-empty list" % name
        previous_time = -1.0
        for index, point in enumerate(points):
            if not isinstance(point, dict):
                return "%s.points[%d] must be a mapping" % (name, index)
            missing = [field for field in REQUIRED_POINT_FIELDS if field not in point]
            if missing:
                return "%s.points[%d] missing %s" % (name, index, ", ".join(missing))
            for field in ("positions", "velocities", "accelerations"):
                values = point[field]
                if not isinstance(values, list) or len(values) != len(REQUIRED_JOINT_NAMES):
                    return "%s.points[%d].%s must contain six values" % (name, index, field)
                if not all(GuardedTrajectoryProfiles._is_number(value) for value in values):
                    return "%s.points[%d].%s must contain numbers" % (name, index, field)
            point_time = point["time_from_start_s"]
            if (not GuardedTrajectoryProfiles._is_number(point_time) or point_time < 0.0
                    or point_time <= previous_time):
                return "%s.points[%d].time_from_start_s must be non-negative and strictly increasing" % (
                    name, index)
            previous_time = point_time
        return ""

    @staticmethod
    def _is_number(value):
        return (isinstance(value, (int, float)) and not isinstance(value, bool)
                and math.isfinite(value))

    @classmethod
    def _is_positive_number(cls, value):
        return cls._is_number(value) and value > 0.0


class GuardedExecutionPolicy(object):
    """Reports why execution remains unavailable in the guarded skeleton."""

    def __init__(self, profiles):
        self._profiles = GuardedTrajectoryProfiles(profiles)

    def snapshot(self):
        profile_status = self._profiles.snapshot()
        blocking_reasons = ["REAL_EXECUTION_DISABLED", "GRIP_FEEDBACK_UNAVAILABLE"]
        if not profile_status["valid_profile_names"]:
            blocking_reasons.append("NO_VALIDATED_PROFILES")
        return {
            "mode": "guarded_real",
            "execution_permitted": False,
            "ready": False,
            "blocking_reasons": blocking_reasons,
            "profiles": profile_status,
        }


class GuardedRealGateway(object):
    """Read-only facade for the future real-execution adapter."""

    actuator_commands_enabled = False

    def __init__(self, read_only_adapter, policy):
        self._read_only_adapter = read_only_adapter
        self._policy = policy

    def snapshot(self):
        health = self._read_only_adapter.health()
        health["execution"] = self._policy.snapshot()
        return {
            "state": "GUARDED_REAL",
            "task_id": "",
            "profile": "",
            "fault_code": "",
            "updated_at": _utc_now(),
            "health": health,
        }

    def reset_fault(self):
        return False, "REAL_EXECUTION_DISABLED: reset is unavailable because no local command is issued"

    @staticmethod
    def reject_actuator_command():
        return False, "REAL_EXECUTION_DISABLED: actuator commands are disabled"
