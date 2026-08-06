from __future__ import absolute_import

import json
import os
import socket
import sys
import time
import unittest
from datetime import datetime, timedelta, timezone

PACKAGE_SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if PACKAGE_SRC not in sys.path:
    sys.path.insert(0, PACKAGE_SRC)

from rm65_lift_gateway.adapters import SimGripperAdapter, SimRobotAdapter, SimVisionAdapter
from rm65_lift_gateway.protocol import GatewayDispatcher, GatewayTcpServer
from rm65_lift_gateway.state_machine import GatewayStateMachine


TOKEN = "test-token"


def make_server():
    profiles = {
        "demo": {"prepare_duration_s": 0.0, "lift_duration_s": 0.25, "vision_ok": True, "grip_ok": True},
    }
    adapters = {"robot": SimRobotAdapter(), "vision": SimVisionAdapter(), "gripper": SimGripperAdapter()}
    machine = GatewayStateMachine(profiles, adapters, past_start_tolerance_s=0.02, max_start_delay_s=1.0)
    server = GatewayTcpServer("127.0.0.1", 0, GatewayDispatcher(machine, TOKEN), 2048)
    server.start()
    return server


def request(request_data, server, fragments=None):
    address = (server.address["host"], server.address["port"])
    encoded = (json.dumps(request_data) + "\n").encode("utf-8")
    with socket.create_connection(address, timeout=1.0) as sock:
        if fragments:
            offset = 0
            for size in fragments:
                sock.sendall(encoded[offset:offset + size])
                offset += size
            sock.sendall(encoded[offset:])
        else:
            sock.sendall(encoded)
        received = b""
        while not received.endswith(b"\n"):
            received += sock.recv(4096)
    return json.loads(received.decode("utf-8"))


def command(request_id, command_name, task_id="task-1", payload=None, token=TOKEN):
    return {
        "version": 1,
        "request_id": request_id,
        "task_id": task_id,
        "command": command_name,
        "token": token,
        "payload": payload or {},
    }


class GatewayProtocolTest(unittest.TestCase):
    def setUp(self):
        self.server = make_server()

    def tearDown(self):
        self.server.stop()

    def test_fragmented_json_authentication_and_duplicate_request(self):
        health = command("health-1", "HEALTH")
        response = request(health, self.server, fragments=[2, 5, 11])
        self.assertTrue(response["accepted"])
        self.assertEqual("IDLE", response["state"])
        duplicate = request(health, self.server)
        self.assertFalse(duplicate["accepted"])
        self.assertEqual("DUPLICATE_REQUEST", duplicate["code"])
        denied = request(command("health-2", "HEALTH", token="wrong"), self.server)
        self.assertFalse(denied["accepted"])
        self.assertEqual("AUTH_FAILED", denied["code"])

    def test_socket_happy_path_does_not_start_before_scheduled_time(self):
        self.assertTrue(request(command("p-1", "PREPARE", payload={"profile": "demo"}), self.server)["accepted"])
        self.assertTrue(request(command("g-1", "GRIP"), self.server)["accepted"])
        start_time = datetime.now(timezone.utc) + timedelta(seconds=0.16)
        armed = request(command("a-1", "ARM_LIFT", payload={
            "profile": "demo",
            "start_time_utc": start_time.isoformat().replace("+00:00", "Z"),
        }), self.server)
        self.assertTrue(armed["accepted"])
        time.sleep(0.04)
        before_start = request(command("h-1", "HEALTH"), self.server)
        self.assertEqual("ARMED", before_start["state"])
        time.sleep(0.16)
        after_start = request(command("h-2", "HEALTH"), self.server)
        self.assertEqual("LIFT", after_start["state"])
        time.sleep(0.28)
        completed = request(command("h-3", "HEALTH"), self.server)
        self.assertEqual("COMPLETE", completed["state"])

    def test_abort_after_arming_and_expired_start_time(self):
        self.assertTrue(request(command("p-1", "PREPARE", payload={"profile": "demo"}), self.server)["accepted"])
        self.assertTrue(request(command("g-1", "GRIP"), self.server)["accepted"])
        expired = datetime.now(timezone.utc) - timedelta(seconds=0.2)
        rejected = request(command("a-expired", "ARM_LIFT", payload={
            "profile": "demo",
            "start_time_utc": expired.isoformat().replace("+00:00", "Z"),
        }), self.server)
        self.assertFalse(rejected["accepted"])
        self.assertEqual("START_TIME_EXPIRED", rejected["code"])
        start_time = datetime.now(timezone.utc) + timedelta(seconds=0.25)
        self.assertTrue(request(command("a-1", "ARM_LIFT", payload={
            "profile": "demo",
            "start_time_utc": start_time.isoformat().replace("+00:00", "Z"),
        }), self.server)["accepted"])
        aborted = request(command("x-1", "ABORT"), self.server)
        self.assertTrue(aborted["accepted"])
        self.assertEqual("ABORTED", aborted["state"])
        time.sleep(0.28)
        self.assertEqual("ABORTED", request(command("h-1", "HEALTH"), self.server)["state"])


if __name__ == "__main__":
    unittest.main()
