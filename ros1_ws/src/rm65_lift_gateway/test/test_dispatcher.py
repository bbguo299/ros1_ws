from __future__ import absolute_import

import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

PACKAGE_SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if PACKAGE_SRC not in sys.path:
    sys.path.insert(0, PACKAGE_SRC)

from rm65_lift_gateway.adapters import SimGripperAdapter, SimRobotAdapter, SimVisionAdapter
from rm65_lift_gateway.protocol import GatewayDispatcher
from rm65_lift_gateway.state_machine import GatewayStateMachine


class DispatcherTest(unittest.TestCase):
    def setUp(self):
        profiles = {
            "demo": {"prepare_duration_s": 0.0, "lift_duration_s": 0.1, "vision_ok": True, "grip_ok": True},
        }
        machine = GatewayStateMachine(profiles, {
            "robot": SimRobotAdapter(), "vision": SimVisionAdapter(), "gripper": SimGripperAdapter(),
        })
        self.dispatcher = GatewayDispatcher(machine, "test-token")

    def _request(self, request_id, command, payload=None, token="test-token"):
        return {
            "version": 1,
            "request_id": request_id,
            "task_id": "task-1",
            "command": command,
            "token": token,
            "payload": payload or {},
        }

    def test_authentication_duplicate_and_invalid_payload(self):
        denied = self.dispatcher.handle(self._request("denied", "HEALTH", token="bad"))
        self.assertEqual("AUTH_FAILED", denied["code"])
        health = self.dispatcher.handle(self._request("health", "HEALTH"))
        self.assertTrue(health["accepted"])
        duplicate = self.dispatcher.handle(self._request("health", "HEALTH"))
        self.assertEqual("DUPLICATE_REQUEST", duplicate["code"])
        invalid = self.dispatcher.handle(self._request("prepare", "PREPARE"))
        self.assertEqual("INVALID_PAYLOAD", invalid["code"])

    def test_full_dispatcher_path_and_expired_time(self):
        self.assertTrue(self.dispatcher.handle(self._request("p", "PREPARE", {"profile": "demo"}))["accepted"])
        self.assertTrue(self.dispatcher.handle(self._request("g", "GRIP"))["accepted"])
        expired = datetime.now(timezone.utc) - timedelta(seconds=1)
        expired_response = self.dispatcher.handle(self._request("old", "ARM_LIFT", {
            "profile": "demo",
            "start_time_utc": expired.isoformat().replace("+00:00", "Z"),
        }))
        self.assertEqual("START_TIME_EXPIRED", expired_response["code"])


if __name__ == "__main__":
    unittest.main()
