"""Thread-safe task state machine for the simulation gateway."""

from __future__ import absolute_import

import threading
from datetime import datetime, timezone


class GatewayState(object):
    IDLE = "IDLE"
    PREPARING = "PREPARING"
    PREPARED = "PREPARED"
    GRIPPED = "GRIPPED"
    ARMED = "ARMED"
    LIFT = "LIFT"
    HOLD = "HOLD"
    COMPLETE = "COMPLETE"
    ABORTED = "ABORTED"


class GatewayStateMachine(object):
    def __init__(self, profiles, adapters, past_start_tolerance_s=0.1,
                 max_start_delay_s=30.0):
        self._profiles = profiles
        self._robot = adapters["robot"]
        self._vision = adapters["vision"]
        self._gripper = adapters["gripper"]
        self._past_start_tolerance_s = float(past_start_tolerance_s)
        self._max_start_delay_s = float(max_start_delay_s)
        self._lock = threading.RLock()
        self._state = GatewayState.IDLE
        self._task_id = ""
        self._profile_name = ""
        self._fault_code = ""
        self._updated_at = datetime.now(timezone.utc)
        self._arm_timer = None
        self._prepare_cancel = None

    def snapshot(self):
        with self._lock:
            return {
                "state": self._state,
                "task_id": self._task_id,
                "profile": self._profile_name,
                "fault_code": self._fault_code,
                "updated_at": self._updated_at.isoformat().replace("+00:00", "Z"),
                "health": {
                    "driver": self._robot.health(),
                    "vision": self._vision.health(),
                    "gripper": self._gripper.health(),
                    "time": {"mode": "system_utc", "ready": True},
                },
            }

    def prepare(self, task_id, profile_name):
        with self._lock:
            if self._state != GatewayState.IDLE:
                return self._reject("INVALID_STATE", "PREPARE requires IDLE")
            profile, error = self._profile(profile_name)
            if error:
                return self._reject("UNKNOWN_PROFILE", error)
            vision_ok, message = self._vision.validate(profile)
            if not vision_ok:
                self._set_state(GatewayState.ABORTED, task_id, profile_name, message)
                return False, message
            self._set_state(GatewayState.PREPARING, task_id, profile_name, "")
            self._prepare_cancel = threading.Event()

        completed = self._robot.prepare(profile["prepare_duration_s"], self._prepare_cancel)
        with self._lock:
            if self._state == GatewayState.ABORTED:
                return False, "ABORTED_DURING_PREPARE"
            if not completed:
                self._set_state(GatewayState.ABORTED, task_id, profile_name, "PREPARE_CANCELLED")
                return False, "PREPARE_CANCELLED"
            self._prepare_cancel = None
            self._set_state(GatewayState.PREPARED, task_id, profile_name, "")
            return True, "PREPARED"

    def grip(self, task_id):
        with self._lock:
            if self._state != GatewayState.PREPARED or task_id != self._task_id:
                return self._reject("INVALID_STATE", "GRIP requires matching PREPARED task")
            profile = self._profiles[self._profile_name]
            grip_ok, message = self._gripper.close(profile)
            if not grip_ok:
                self._set_state(GatewayState.ABORTED, task_id, self._profile_name, message)
                return False, message
            self._set_state(GatewayState.GRIPPED, task_id, self._profile_name, "")
            return True, "GRIPPED"

    def arm_lift(self, task_id, profile_name, start_time):
        with self._lock:
            if self._state != GatewayState.GRIPPED or task_id != self._task_id:
                return self._reject("INVALID_STATE", "ARM_LIFT requires matching GRIPPED task")
            if profile_name != self._profile_name:
                return self._reject("PROFILE_MISMATCH", "ARM_LIFT profile must match PREPARE")
            profile, error = self._profile(profile_name)
            if error:
                return self._reject("UNKNOWN_PROFILE", error)
            now = datetime.now(timezone.utc)
            delay = (start_time - now).total_seconds()
            if delay < -self._past_start_tolerance_s:
                return self._reject("START_TIME_EXPIRED", "start_time_utc is too far in the past")
            if delay > self._max_start_delay_s:
                return self._reject("START_TIME_TOO_FAR", "start_time_utc exceeds configured arm window")
            self._set_state(GatewayState.ARMED, task_id, profile_name, "")
            self._cancel_arm_timer_locked()
            self._arm_timer = threading.Timer(max(0.0, delay), self._start_lift, args=(task_id, profile_name, profile))
            self._arm_timer.daemon = True
            self._arm_timer.start()
            return True, "ARMED"

    def hold(self, task_id):
        with self._lock:
            if self._state not in (GatewayState.ARMED, GatewayState.LIFT) or task_id != self._task_id:
                return self._reject("INVALID_STATE", "HOLD requires matching ARMED or LIFT task")
            self._cancel_arm_timer_locked()
            self._robot.hold()
            self._set_state(GatewayState.HOLD, task_id, self._profile_name, "")
            return True, "HOLD"

    def abort(self, task_id):
        with self._lock:
            self._cancel_arm_timer_locked()
            if self._prepare_cancel is not None:
                self._prepare_cancel.set()
            self._robot.cancel_lift()
            active_task = self._task_id or task_id
            self._set_state(GatewayState.ABORTED, active_task, self._profile_name, "ABORT_REQUESTED")
            return True, "ABORTED"

    def reset_fault(self):
        with self._lock:
            if self._state not in (GatewayState.ABORTED, GatewayState.COMPLETE):
                return False, "RESET_REQUIRES_ABORTED_OR_COMPLETE"
            self._cancel_arm_timer_locked()
            self._robot.cancel_lift()
            self._set_state(GatewayState.IDLE, "", "", "")
            return True, "IDLE"

    def _start_lift(self, task_id, profile_name, profile):
        with self._lock:
            if self._state != GatewayState.ARMED or self._task_id != task_id:
                return
            self._arm_timer = None
            self._set_state(GatewayState.LIFT, task_id, profile_name, "")
            self._robot.start_lift(profile["lift_duration_s"], lambda: self._complete_lift(task_id))

    def _complete_lift(self, task_id):
        with self._lock:
            if self._state == GatewayState.LIFT and self._task_id == task_id:
                self._set_state(GatewayState.COMPLETE, task_id, self._profile_name, "")

    def _profile(self, profile_name):
        profile = self._profiles.get(profile_name)
        if not isinstance(profile, dict):
            return None, "profile '%s' is not configured" % profile_name
        for key in ("prepare_duration_s", "lift_duration_s"):
            if key not in profile:
                return None, "profile '%s' has no %s" % (profile_name, key)
        return profile, ""

    def _cancel_arm_timer_locked(self):
        if self._arm_timer is not None:
            self._arm_timer.cancel()
            self._arm_timer = None

    def _set_state(self, state, task_id, profile_name, fault_code):
        self._state = state
        self._task_id = task_id
        self._profile_name = profile_name
        self._fault_code = fault_code
        self._updated_at = datetime.now(timezone.utc)

    def _reject(self, code, message):
        return False, "%s: %s" % (code, message)
