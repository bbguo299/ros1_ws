from __future__ import absolute_import

import os
import sys
import unittest

PACKAGE_SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if PACKAGE_SRC not in sys.path:
    sys.path.insert(0, PACKAGE_SRC)

from rm65_lift_gateway.protocol import GatewayDispatcher
from rm65_lift_gateway.read_only import ReadOnlyGateway, ReadOnlyHealthModel


JOINTS = ["joint1", "joint2", "joint3", "joint4", "joint5", "joint6"]


class FakeReadOnlyAdapter(object):
    def health(self):
        return {"mode": "read_only", "read_only": True, "ready": True, "motion_permitted": False,
                "gripper_permitted": False}


class ReadOnlyHealthTest(unittest.TestCase):
    def _healthy_model(self):
        model = ReadOnlyHealthModel(JOINTS, 0.75, 2.0)
        model.record_joint_state(JOINTS, received_at=100.0)
        model.set_action_available(True)
        model.record_arm_error(0)
        model.record_sys_error(0)
        for stream in ("color_image", "depth_image", "color_info", "depth_info"):
            model.record_stream(stream, received_at=100.0)
        return model

    def test_fresh_complete_healthy_inputs_are_ready(self):
        status = self._healthy_model().snapshot(now=100.5)
        self.assertTrue(status["ready"])
        self.assertTrue(status["driver"]["ready"])
        self.assertTrue(status["camera"]["ready"])
        self.assertFalse(status["motion_permitted"])
        self.assertFalse(status["gripper_permitted"])

    def test_stale_or_incomplete_data_is_not_ready(self):
        model = self._healthy_model()
        model.record_joint_state(JOINTS[:-1], received_at=100.0)
        status = model.snapshot(now=100.5)
        self.assertFalse(status["ready"])
        self.assertEqual(["joint6"], status["driver"]["joint_state"]["missing_joint_names"])
        self.assertFalse(model.snapshot(now=103.0)["camera"]["ready"])

    def test_error_codes_and_missing_action_server_are_not_ready(self):
        model = self._healthy_model()
        model.record_arm_error(42)
        status = model.snapshot(now=100.1)
        self.assertFalse(status["driver"]["ready"])
        self.assertTrue(status["driver"]["arm_error"]["active"])
        model.record_arm_error(0)
        model.set_action_available(False)
        self.assertFalse(model.snapshot(now=100.1)["driver"]["ready"])

    def test_observability_reports_windowed_rates_and_intervals(self):
        model = ReadOnlyHealthModel(JOINTS, 0.75, 2.0, observability_window_s=10.0)
        model.record_joint_state(JOINTS, received_at=90.0, received_at_utc="t90")
        model.record_joint_state(JOINTS, received_at=101.0, received_at_utc="t101")
        model.record_joint_state(JOINTS, received_at=103.0, received_at_utc="t103")
        model.record_stream("color_image", received_at=101.0, received_at_utc="color101")
        model.record_stream("color_image", received_at=104.0, received_at_utc="color104")

        observability = model.snapshot(now=105.0)["observability"]
        joint_stats = observability["joint_state"]
        self.assertEqual(2, joint_stats["message_count"])
        self.assertEqual(0.5, joint_stats["mean_rate_hz"])
        self.assertEqual(2.0, joint_stats["last_interval_s"])
        self.assertEqual(2.0, joint_stats["min_interval_s"])
        self.assertEqual(11.0, joint_stats["max_interval_s"])
        self.assertEqual("t103", joint_stats["last_received_at"])
        self.assertEqual(2, observability["camera_streams"]["color_image"]["message_count"])

    def test_observability_tracks_error_samples_and_action_changes(self):
        model = ReadOnlyHealthModel(JOINTS, 0.75, 2.0, observability_window_s=10.0)
        model.set_action_available(True, observed_at=100.0, observed_at_utc="action100")
        model.set_action_available(False, observed_at=101.0, observed_at_utc="action101")
        model.set_action_available(True, observed_at=102.0, observed_at_utc="action102")
        model.record_arm_error(9, received_at=101.0, received_at_utc="arm101")
        model.record_arm_error(0, received_at=102.0, received_at_utc="arm102")
        model.record_sys_error(7, received_at=90.0, received_at_utc="sys90")

        observability = model.snapshot(now=105.0)["observability"]
        self.assertEqual(2, observability["action_server"]["availability_change_count"])
        self.assertEqual("action102", observability["action_server"]["last_change_at"])
        self.assertEqual(1, observability["arm_error"]["nonzero_sample_count"])
        self.assertEqual("arm101", observability["arm_error"]["last_nonzero_at"])
        self.assertEqual(0, observability["sys_error"]["nonzero_sample_count"])
        self.assertIsNone(observability["sys_error"]["last_nonzero_at"])

        expired = model.snapshot(now=113.0)["observability"]
        self.assertEqual(0, expired["action_server"]["availability_change_count"])
        self.assertIsNone(expired["action_server"]["last_change_at"])
        self.assertEqual(0, expired["arm_error"]["nonzero_sample_count"])
        self.assertIsNone(expired["arm_error"]["last_nonzero_at"])

    def test_observability_window_must_be_positive(self):
        with self.assertRaises(ValueError):
            ReadOnlyHealthModel(JOINTS, 0.75, 2.0, observability_window_s=0.0)


class ReadOnlyProtocolTest(unittest.TestCase):
    def setUp(self):
        self.gateway = ReadOnlyGateway(FakeReadOnlyAdapter())
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

    def test_health_is_allowed_and_reports_read_only(self):
        response = self.dispatcher.handle(self._request("health", "HEALTH"))
        self.assertTrue(response["accepted"])
        self.assertEqual("READ_ONLY", response["state"])
        self.assertTrue(response["status"]["health"]["read_only"])

    def test_every_actuator_command_is_rejected(self):
        for index, command in enumerate(("PREPARE", "GRIP", "ARM_LIFT", "HOLD", "ABORT")):
            response = self.dispatcher.handle(self._request("request-%d" % index, command))
            self.assertFalse(response["accepted"])
            self.assertEqual("READ_ONLY_MODE", response["code"])

    def test_read_only_source_has_no_actuator_api(self):
        source_path = os.path.join(PACKAGE_SRC, "rm65_lift_gateway", "read_only.py")
        with open(source_path, encoding="utf-8") as source_file:
            source = source_file.read()
        self.assertNotIn("send_goal", source)
        self.assertNotIn("rm_msgs", source)
        self.assertNotIn("rospy.Publisher", source)


if __name__ == "__main__":
    unittest.main()
