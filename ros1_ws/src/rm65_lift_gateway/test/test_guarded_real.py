from __future__ import absolute_import

import os
import sys
import unittest

PACKAGE_SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if PACKAGE_SRC not in sys.path:
    sys.path.insert(0, PACKAGE_SRC)

from rm65_lift_gateway.guarded_real import (
    GuardedExecutionPolicy,
    GuardedRealGateway,
    GuardedTrajectoryProfiles,
)
from rm65_lift_gateway.protocol import GatewayDispatcher


JOINTS = ["joint1", "joint2", "joint3", "joint4", "joint5", "joint6"]


class FakeReadOnlyAdapter(object):
    def health(self):
        return {"mode": "read_only", "ready": True, "motion_permitted": False}


def valid_trajectory():
    return {
        "joint_names": JOINTS,
        "final_joint_tolerance_rad": 0.03,
        "completion_timeout_s": 8.0,
        "points": [{
            "positions": [0.0] * 6,
            "velocities": [0.0] * 6,
            "accelerations": [0.0] * 6,
            "time_from_start_s": 0.1,
        }],
    }


class GuardedTrajectoryProfilesTest(unittest.TestCase):
    def test_empty_profiles_are_valid_but_not_executable(self):
        status = GuardedTrajectoryProfiles({}).snapshot()
        self.assertEqual([], status["valid_profile_names"])
        self.assertEqual({}, status["invalid_profile_reasons"])

    def test_valid_profile_requires_prepare_and_lift_trajectories(self):
        profiles = {"demo": {"prepare": valid_trajectory(), "lift": valid_trajectory()}}
        self.assertEqual(["demo"], GuardedTrajectoryProfiles(profiles).snapshot()["valid_profile_names"])

    def test_invalid_trajectory_is_rejected(self):
        profile = {"prepare": valid_trajectory(), "lift": valid_trajectory()}
        profile["lift"]["points"][0]["velocities"] = [0.0] * 5
        status = GuardedTrajectoryProfiles({"bad": profile}).snapshot()
        self.assertEqual([], status["valid_profile_names"])
        self.assertIn("must contain six values", status["invalid_profile_reasons"]["bad"])

    def test_negative_trajectory_time_is_rejected(self):
        profile = {"prepare": valid_trajectory(), "lift": valid_trajectory()}
        profile["prepare"]["points"][0]["time_from_start_s"] = -0.1
        status = GuardedTrajectoryProfiles({"bad-time": profile}).snapshot()
        self.assertEqual([], status["valid_profile_names"])
        self.assertIn("must be non-negative", status["invalid_profile_reasons"]["bad-time"])


class GuardedRealGatewayTest(unittest.TestCase):
    def setUp(self):
        self.gateway = GuardedRealGateway(FakeReadOnlyAdapter(), GuardedExecutionPolicy({}))
        self.dispatcher = GatewayDispatcher(self.gateway, "test-token")

    def _request(self, request_id, command):
        return {
            "version": 1,
            "request_id": request_id,
            "task_id": "task-1",
            "command": command,
            "token": "test-token",
            "payload": {"profile": "demo"},
        }

    def test_health_reports_execution_blocks_without_hiding_read_only_health(self):
        health = self.gateway.snapshot()["health"]
        self.assertTrue(health["ready"])
        self.assertFalse(health["execution"]["execution_permitted"])
        self.assertIn("REAL_EXECUTION_DISABLED", health["execution"]["blocking_reasons"])
        self.assertIn("NO_VALIDATED_PROFILES", health["execution"]["blocking_reasons"])
        self.assertIn("GRIP_FEEDBACK_UNAVAILABLE", health["execution"]["blocking_reasons"])

    def test_actuator_commands_are_rejected_with_guarded_real_code(self):
        for index, command in enumerate(("PREPARE", "GRIP", "ARM_LIFT", "HOLD", "ABORT")):
            response = self.dispatcher.handle(self._request("request-%d" % index, command))
            self.assertFalse(response["accepted"])
            self.assertEqual("REAL_EXECUTION_DISABLED", response["code"])

    def test_guarded_real_source_has_no_ros_control_api(self):
        source_path = os.path.join(PACKAGE_SRC, "rm65_lift_gateway", "guarded_real.py")
        with open(source_path, encoding="utf-8") as source_file:
            source = source_file.read()
        self.assertNotIn("send_goal", source)
        self.assertNotIn("rm_msgs", source)
        self.assertNotIn("rospy", source)


if __name__ == "__main__":
    unittest.main()
