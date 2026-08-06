"""Simulation adapters.  They deliberately contain no real ROS hardware calls."""

from __future__ import absolute_import

import threading


class SimVisionAdapter(object):
    def validate(self, profile):
        if profile.get("vision_ok", True):
            return True, "simulated vision accepted"
        return False, "SIM_VISION_REJECTED"

    def health(self):
        return {"mode": "simulated", "ready": True}


class SimGripperAdapter(object):
    def close(self, profile):
        if profile.get("grip_ok", True):
            return True, "simulated grip accepted"
        return False, "SIM_GRIP_REJECTED"

    def health(self):
        return {"mode": "simulated", "ready": True}


class SimRobotAdapter(object):
    """Time-based robot stand-in used for prepare, lift, hold, and cancellation."""

    def __init__(self):
        self._lock = threading.Lock()
        self._lift_timer = None

    def prepare(self, duration_s, cancel_event):
        """Wait for a simulated prepare motion; return false if it was cancelled."""
        return not cancel_event.wait(max(0.0, float(duration_s)))

    def start_lift(self, duration_s, on_complete):
        with self._lock:
            self._cancel_lift_locked()
            self._lift_timer = threading.Timer(max(0.0, float(duration_s)), on_complete)
            self._lift_timer.daemon = True
            self._lift_timer.start()

    def hold(self):
        self.cancel_lift()

    def cancel_lift(self):
        with self._lock:
            self._cancel_lift_locked()

    def _cancel_lift_locked(self):
        if self._lift_timer is not None:
            self._lift_timer.cancel()
            self._lift_timer = None

    def health(self):
        return {"mode": "simulated", "ready": True}
