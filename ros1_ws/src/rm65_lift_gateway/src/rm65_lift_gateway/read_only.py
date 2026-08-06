"""Read-only ROS1 health adapter for the RM65 execution host.

This module never creates ROS publishers for robot commands and never sends an
Action goal.  It only subscribes to status topics and probes Action server
availability.
"""

from __future__ import absolute_import

from collections import deque
import threading
import time
from datetime import datetime, timezone

import actionlib
import rospy
from control_msgs.msg import FollowJointTrajectoryAction
from sensor_msgs.msg import CameraInfo, Image, JointState
from std_msgs.msg import UInt16


def _utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class _WindowedArrivalStats(object):
    """Tracks message arrival statistics without persisting data to disk."""

    def __init__(self, window_s):
        self._window_s = float(window_s)
        self._events = deque()
        self._last_received_at = None

    def record(self, received_at, received_at_utc):
        self._events.append((float(received_at), received_at_utc))
        self._last_received_at = received_at_utc

    def snapshot(self, now):
        cutoff = float(now) - self._window_s
        # Retain one predecessor so an interval ending inside the window is kept.
        while len(self._events) > 1 and self._events[1][0] < cutoff:
            self._events.popleft()

        events_in_window = [event for event in self._events if event[0] >= cutoff]
        intervals = [
            current[0] - previous[0]
            for previous, current in zip(self._events, list(self._events)[1:])
            if current[0] >= cutoff
        ]
        rate_hz = None
        if len(events_in_window) >= 2:
            span_s = events_in_window[-1][0] - events_in_window[0][0]
            rate_hz = (len(events_in_window) - 1) / span_s if span_s > 0.0 else None
        return {
            "message_count": len(events_in_window),
            "mean_rate_hz": rate_hz,
            "last_interval_s": intervals[-1] if intervals else None,
            "min_interval_s": min(intervals) if intervals else None,
            "max_interval_s": max(intervals) if intervals else None,
            "last_received_at": self._last_received_at,
        }


class ReadOnlyHealthModel(object):
    """ROS-independent freshness and error evaluator used by the adapter."""

    def __init__(self, required_joint_names, joint_timeout_s, image_timeout_s,
                 observability_window_s=600.0):
        self._required_joint_names = set(required_joint_names)
        self._joint_timeout_s = float(joint_timeout_s)
        self._image_timeout_s = float(image_timeout_s)
        self._observability_window_s = float(observability_window_s)
        if self._observability_window_s <= 0.0:
            raise ValueError("observability_window_s must be greater than zero")
        self._lock = threading.RLock()
        self._joint_received_at = None
        self._joint_names = set()
        self._action_available = False
        self._action_observed = False
        self._action_changes = deque()
        self._arm_error = None
        self._sys_error = None
        self._error_nonzero_samples = {"arm_error": deque(), "sys_error": deque()}
        self._joint_stats = _WindowedArrivalStats(self._observability_window_s)
        self._stream_stats = {
            "color_image": _WindowedArrivalStats(self._observability_window_s),
            "depth_image": _WindowedArrivalStats(self._observability_window_s),
            "color_info": _WindowedArrivalStats(self._observability_window_s),
            "depth_info": _WindowedArrivalStats(self._observability_window_s),
        }
        self._streams = {
            "color_image": None,
            "depth_image": None,
            "color_info": None,
            "depth_info": None,
        }

    def record_joint_state(self, names, received_at=None, received_at_utc=None):
        received_at = time.monotonic() if received_at is None else received_at
        received_at_utc = _utc_now() if received_at_utc is None else received_at_utc
        with self._lock:
            self._joint_names = set(names)
            self._joint_received_at = received_at
            self._joint_stats.record(received_at, received_at_utc)

    def set_action_available(self, available, observed_at=None, observed_at_utc=None):
        observed_at = time.monotonic() if observed_at is None else observed_at
        observed_at_utc = _utc_now() if observed_at_utc is None else observed_at_utc
        available = bool(available)
        with self._lock:
            if self._action_observed and available != self._action_available:
                self._action_changes.append((observed_at, observed_at_utc))
            self._action_available = available
            self._action_observed = True

    def record_arm_error(self, value, received_at=None, received_at_utc=None):
        self._record_error("arm_error", value, received_at, received_at_utc)

    def record_sys_error(self, value, received_at=None, received_at_utc=None):
        self._record_error("sys_error", value, received_at, received_at_utc)

    def record_stream(self, name, received_at=None, received_at_utc=None):
        if name not in self._streams:
            raise ValueError("unknown stream: %s" % name)
        received_at = time.monotonic() if received_at is None else received_at
        received_at_utc = _utc_now() if received_at_utc is None else received_at_utc
        with self._lock:
            self._streams[name] = received_at
            self._stream_stats[name].record(received_at, received_at_utc)

    def snapshot(self, now=None):
        now = time.monotonic() if now is None else now
        with self._lock:
            joint_age = self._age(self._joint_received_at, now)
            missing_joints = sorted(self._required_joint_names - self._joint_names)
            joint_ready = joint_age is not None and joint_age <= self._joint_timeout_s and not missing_joints
            stream_status = {}
            camera_ready = True
            for name, received_at in self._streams.items():
                age = self._age(received_at, now)
                ready = age is not None and age <= self._image_timeout_s
                stream_status[name] = {"ready": ready, "age_s": age}
                camera_ready = camera_ready and ready
            arm_error_active = self._arm_error not in (None, 0)
            sys_error_active = self._sys_error not in (None, 0)
            driver_ready = joint_ready and self._action_available and not arm_error_active and not sys_error_active
            return {
                "mode": "read_only",
                "read_only": True,
                "motion_permitted": False,
                "gripper_permitted": False,
                "ready": driver_ready and camera_ready,
                "driver": {
                    "ready": driver_ready,
                    "joint_state": {
                        "ready": joint_ready,
                        "age_s": joint_age,
                        "missing_joint_names": missing_joints,
                    },
                    "action_server": {"ready": self._action_available},
                    "arm_error": {"seen": self._arm_error is not None, "value": self._arm_error,
                                  "active": arm_error_active},
                    "sys_error": {"seen": self._sys_error is not None, "value": self._sys_error,
                                  "active": sys_error_active},
                },
                "camera": {"ready": camera_ready, "streams": stream_status},
                "observability": self._observability_snapshot(now),
                "time": {"mode": "system_utc", "ready": True},
                "updated_at": _utc_now(),
            }

    def _record_error(self, name, value, received_at, received_at_utc):
        received_at = time.monotonic() if received_at is None else received_at
        received_at_utc = _utc_now() if received_at_utc is None else received_at_utc
        value = int(value)
        with self._lock:
            if name == "arm_error":
                self._arm_error = value
            else:
                self._sys_error = value
            if value != 0:
                self._error_nonzero_samples[name].append((received_at, received_at_utc))

    def _observability_snapshot(self, now):
        cutoff = now - self._observability_window_s
        for changes in (self._action_changes,) + tuple(self._error_nonzero_samples.values()):
            while changes and changes[0][0] < cutoff:
                changes.popleft()
        return {
            "window_s": self._observability_window_s,
            "joint_state": self._joint_stats.snapshot(now),
            "camera_streams": {
                name: self._stream_stats[name].snapshot(now) for name in self._streams
            },
            "action_server": {
                "available": self._action_available,
                "availability_change_count": len(self._action_changes),
                "last_change_at": self._last_event_at(self._action_changes),
            },
            "arm_error": self._error_observability("arm_error"),
            "sys_error": self._error_observability("sys_error"),
        }

    def _error_observability(self, name):
        return {
            "nonzero_sample_count": len(self._error_nonzero_samples[name]),
            "last_nonzero_at": self._last_event_at(self._error_nonzero_samples[name]),
        }

    @staticmethod
    def _last_event_at(events):
        return events[-1][1] if events else None

    @staticmethod
    def _age(received_at, now):
        return None if received_at is None else max(0.0, now - received_at)


class ReadOnlyRosAdapter(object):
    """Subscribes to existing ROS1 nodes and exposes their health only."""

    def __init__(self, config):
        self._config = config
        self._model = ReadOnlyHealthModel(
            config["required_joint_names"], config["joint_state_fresh_timeout_s"],
            config["camera_fresh_timeout_s"], config.get("observability_window_s", 600.0))
        self._action_client = actionlib.SimpleActionClient(
            config["trajectory_action"], FollowJointTrajectoryAction)
        self._joint_sub = rospy.Subscriber(
            config["joint_states_topic"], JointState, self._joint_state_cb, queue_size=10)
        self._arm_error_sub = rospy.Subscriber(
            config["arm_error_topic"], UInt16, self._arm_error_cb, queue_size=10)
        self._sys_error_sub = rospy.Subscriber(
            config["sys_error_topic"], UInt16, self._sys_error_cb, queue_size=10)
        self._color_image_sub = rospy.Subscriber(
            config["color_image_topic"], Image, self._color_image_cb, queue_size=1)
        self._depth_image_sub = rospy.Subscriber(
            config["depth_image_topic"], Image, self._depth_image_cb, queue_size=1)
        self._color_info_sub = rospy.Subscriber(
            config["color_info_topic"], CameraInfo, self._color_info_cb, queue_size=1)
        self._depth_info_sub = rospy.Subscriber(
            config["depth_info_topic"], CameraInfo, self._depth_info_cb, queue_size=1)
        self._probe_action_server(config["action_server_wait_s"])

    def health(self):
        self._probe_action_server(0.0)
        return self._model.snapshot()

    def _probe_action_server(self, timeout_s):
        available = self._action_client.wait_for_server(rospy.Duration(max(0.0, float(timeout_s))))
        self._model.set_action_available(available)

    def _joint_state_cb(self, message):
        self._model.record_joint_state(message.name)

    def _arm_error_cb(self, message):
        self._model.record_arm_error(message.data)

    def _sys_error_cb(self, message):
        self._model.record_sys_error(message.data)

    def _color_image_cb(self, _message):
        self._model.record_stream("color_image")

    def _depth_image_cb(self, _message):
        self._model.record_stream("depth_image")

    def _color_info_cb(self, _message):
        self._model.record_stream("color_info")

    def _depth_info_cb(self, _message):
        self._model.record_stream("depth_info")


class ReadOnlyGateway(object):
    """Gateway facade that intentionally rejects every actuator command."""

    actuator_commands_enabled = False

    def __init__(self, adapter):
        self._adapter = adapter

    def snapshot(self):
        return {
            "state": "READ_ONLY",
            "task_id": "",
            "profile": "",
            "fault_code": "",
            "updated_at": _utc_now(),
            "health": self._adapter.health(),
        }

    def prepare(self, _task_id, _profile_name):
        return self.reject_actuator_command()

    def grip(self, _task_id):
        return self.reject_actuator_command()

    def arm_lift(self, _task_id, _profile_name, _start_time):
        return self.reject_actuator_command()

    def hold(self, _task_id):
        return self.reject_actuator_command()

    def abort(self, _task_id):
        return self.reject_actuator_command()

    def reset_fault(self):
        return False, "READ_ONLY_MODE: reset is unavailable because no local command is issued"

    @staticmethod
    def reject_actuator_command():
        return False, "READ_ONLY_MODE: actuator commands are disabled"
