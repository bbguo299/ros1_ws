from __future__ import absolute_import

import os
import sys
import time
import unittest
from datetime import datetime, timedelta, timezone

PACKAGE_SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if PACKAGE_SRC not in sys.path:
    sys.path.insert(0, PACKAGE_SRC)

from rm65_lift_gateway.adapters import SimGripperAdapter, SimRobotAdapter, SimVisionAdapter
from rm65_lift_gateway.state_machine import GatewayState, GatewayStateMachine


def make_machine():
    profiles = {
        "demo": {"prepare_duration_s": 0.0, "lift_duration_s": 0.12, "vision_ok": True, "grip_ok": True},
        "bad_vision": {"prepare_duration_s": 0.0, "lift_duration_s": 0.1, "vision_ok": False, "grip_ok": True},
        "bad_grip": {"prepare_duration_s": 0.0, "lift_duration_s": 0.1, "vision_ok": True, "grip_ok": False},
    }
    adapters = {"robot": SimRobotAdapter(), "vision": SimVisionAdapter(), "gripper": SimGripperAdapter()}
    return GatewayStateMachine(profiles, adapters, past_start_tolerance_s=0.02, max_start_delay_s=1.0)


class GatewayStateMachineTest(unittest.TestCase):
    def test_complete_happy_path_and_local_reset(self):
        machine = make_machine()
        self.assertTrue(machine.prepare("task-1", "demo")[0])
        self.assertEqual(GatewayState.PREPARED, machine.snapshot()["state"])
        self.assertTrue(machine.grip("task-1")[0])
        start_time = datetime.now(timezone.utc) + timedelta(seconds=0.04)
        self.assertTrue(machine.arm_lift("task-1", "demo", start_time)[0])
        self.assertEqual(GatewayState.ARMED, machine.snapshot()["state"])
        time.sleep(0.06)
        self.assertEqual(GatewayState.LIFT, machine.snapshot()["state"])
        time.sleep(0.14)
        self.assertEqual(GatewayState.COMPLETE, machine.snapshot()["state"])
        self.assertTrue(machine.reset_fault()[0])
        self.assertEqual(GatewayState.IDLE, machine.snapshot()["state"])

    def test_invalid_transition_and_profile_mismatch_are_rejected(self):
        machine = make_machine()
        self.assertFalse(machine.grip("task-1")[0])
        self.assertTrue(machine.prepare("task-1", "demo")[0])
        self.assertTrue(machine.grip("task-1")[0])
        start_time = datetime.now(timezone.utc) + timedelta(seconds=0.05)
        accepted, message = machine.arm_lift("task-1", "other", start_time)
        self.assertFalse(accepted)
        self.assertIn("PROFILE_MISMATCH", message)
        accepted, message = machine.arm_lift("task-2", "demo", start_time)
        self.assertFalse(accepted)
        self.assertIn("INVALID_STATE", message)

    def test_vision_and_grip_failures_abort(self):
        machine = make_machine()
        self.assertFalse(machine.prepare("task-vision", "bad_vision")[0])
        self.assertEqual(GatewayState.ABORTED, machine.snapshot()["state"])
        self.assertTrue(machine.reset_fault()[0])
        self.assertTrue(machine.prepare("task-grip", "bad_grip")[0])
        self.assertFalse(machine.grip("task-grip")[0])
        self.assertEqual(GatewayState.ABORTED, machine.snapshot()["state"])

    def test_abort_cancels_armed_lift_and_reset_is_restricted(self):
        machine = make_machine()
        self.assertFalse(machine.reset_fault()[0])
        self.assertTrue(machine.prepare("task-1", "demo")[0])
        self.assertTrue(machine.grip("task-1")[0])
        start_time = datetime.now(timezone.utc) + timedelta(seconds=0.2)
        self.assertTrue(machine.arm_lift("task-1", "demo", start_time)[0])
        self.assertTrue(machine.abort("task-1")[0])
        time.sleep(0.23)
        self.assertEqual(GatewayState.ABORTED, machine.snapshot()["state"])
        self.assertTrue(machine.reset_fault()[0])

    def test_hold_cancels_armed_lift_without_fault_reset(self):
        machine = make_machine()
        self.assertTrue(machine.prepare("task-1", "demo")[0])
        self.assertTrue(machine.grip("task-1")[0])
        start_time = datetime.now(timezone.utc) + timedelta(seconds=0.15)
        self.assertTrue(machine.arm_lift("task-1", "demo", start_time)[0])
        self.assertTrue(machine.hold("task-1")[0])
        self.assertEqual(GatewayState.HOLD, machine.snapshot()["state"])
        time.sleep(0.18)
        self.assertEqual(GatewayState.HOLD, machine.snapshot()["state"])

    def test_expired_and_too_distant_start_times_are_rejected(self):
        machine = make_machine()
        self.assertTrue(machine.prepare("task-1", "demo")[0])
        self.assertTrue(machine.grip("task-1")[0])
        expired = datetime.now(timezone.utc) - timedelta(seconds=0.1)
        self.assertFalse(machine.arm_lift("task-1", "demo", expired)[0])
        distant = datetime.now(timezone.utc) + timedelta(seconds=2.0)
        self.assertFalse(machine.arm_lift("task-1", "demo", distant)[0])


if __name__ == "__main__":
    unittest.main()
