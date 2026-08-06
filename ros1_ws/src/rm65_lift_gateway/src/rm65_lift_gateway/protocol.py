"""Newline-delimited JSON protocol and loopback TCP server."""

from __future__ import absolute_import

import hmac
import json
import socketserver
import threading
from datetime import datetime, timezone


COMMANDS = frozenset(("HEALTH", "PREPARE", "GRIP", "ARM_LIFT", "HOLD", "ABORT"))


def utc_now_string():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_utc_timestamp(value):
    if not isinstance(value, str) or not value:
        raise ValueError("start_time_utc must be a non-empty RFC3339 string")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError("start_time_utc must include a UTC offset or Z")
    return parsed.astimezone(timezone.utc)


class GatewayDispatcher(object):
    def __init__(self, state_machine, token, max_seen_request_ids=1024):
        if not isinstance(token, str) or not token:
            raise ValueError("auth token must be a non-empty string")
        self._machine = state_machine
        self._token = token
        self._max_seen_request_ids = int(max_seen_request_ids)
        self._seen_request_ids = []
        self._seen_lookup = set()
        self._lock = threading.Lock()

    def handle(self, request):
        request_id = request.get("request_id") if isinstance(request, dict) else None
        error = self._validate_base_request(request)
        if error:
            return self._response(request_id, False, "INVALID_REQUEST", error)
        if not hmac.compare_digest(request["token"], self._token):
            return self._response(request_id, False, "AUTH_FAILED", "authentication failed")
        if not self._remember_request(request_id):
            return self._response(request_id, False, "DUPLICATE_REQUEST", "request_id was already handled")

        command = request["command"]
        task_id = request["task_id"]
        payload = request["payload"]
        try:
            if command == "HEALTH":
                return self._response(request_id, True, "OK", "health returned")
            if not getattr(self._machine, "actuator_commands_enabled", True):
                accepted, message = self._machine.reject_actuator_command()
                return self._response(request_id, accepted, message.split(":", 1)[0], message)
            if command == "PREPARE":
                profile = self._profile_from_payload(payload)
                accepted, message = self._machine.prepare(task_id, profile)
            elif command == "GRIP":
                accepted, message = self._machine.grip(task_id)
            elif command == "ARM_LIFT":
                profile = self._profile_from_payload(payload)
                start_time = parse_utc_timestamp(payload.get("start_time_utc"))
                accepted, message = self._machine.arm_lift(task_id, profile, start_time)
            elif command == "HOLD":
                accepted, message = self._machine.hold(task_id)
            else:  # ABORT
                accepted, message = self._machine.abort(task_id)
        except (KeyError, TypeError, ValueError) as exc:
            return self._response(request_id, False, "INVALID_PAYLOAD", str(exc))
        code = "OK" if accepted else message.split(":", 1)[0]
        return self._response(request_id, accepted, code, message)

    def _validate_base_request(self, request):
        if not isinstance(request, dict):
            return "request must be a JSON object"
        required = ("version", "request_id", "task_id", "command", "token", "payload")
        missing = [key for key in required if key not in request]
        if missing:
            return "missing required field(s): " + ", ".join(missing)
        if request["version"] != 1:
            return "unsupported protocol version"
        for key in ("request_id", "task_id", "command", "token"):
            if not isinstance(request[key], str) or not request[key]:
                return "%s must be a non-empty string" % key
        if request["command"] not in COMMANDS:
            return "unsupported command"
        if not isinstance(request["payload"], dict):
            return "payload must be an object"
        return ""

    def _profile_from_payload(self, payload):
        profile = payload.get("profile")
        if not isinstance(profile, str) or not profile:
            raise ValueError("payload.profile must be a non-empty string")
        return profile

    def _remember_request(self, request_id):
        with self._lock:
            if request_id in self._seen_lookup:
                return False
            self._seen_lookup.add(request_id)
            self._seen_request_ids.append(request_id)
            while len(self._seen_request_ids) > self._max_seen_request_ids:
                expired = self._seen_request_ids.pop(0)
                self._seen_lookup.remove(expired)
            return True

    def _response(self, request_id, accepted, code, message):
        status = self._machine.snapshot()
        return {
            "version": 1,
            "request_id": request_id,
            "accepted": bool(accepted),
            "code": code,
            "message": message,
            "timestamp_utc": utc_now_string(),
            "state": status["state"],
            "task_id": status["task_id"],
            "fault_code": status["fault_code"],
            "status": status,
        }


class _GatewayRequestHandler(socketserver.StreamRequestHandler):
    def handle(self):
        while True:
            raw = self.rfile.readline(self.server.maximum_message_bytes + 1)
            if not raw:
                return
            if len(raw) > self.server.maximum_message_bytes:
                response = self.server.dispatcher._response(
                    None, False, "MESSAGE_TOO_LARGE", "message exceeds configured limit")
                self._write(response)
                return
            try:
                request = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
                response = self.server.dispatcher._response(None, False, "INVALID_JSON", "invalid UTF-8 JSON line")
            else:
                response = self.server.dispatcher.handle(request)
            self._write(response)

    def _write(self, response):
        self.wfile.write((json.dumps(response, sort_keys=True) + "\n").encode("utf-8"))
        self.wfile.flush()


class _ThreadedGatewayServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, address, dispatcher, maximum_message_bytes):
        self.dispatcher = dispatcher
        self.maximum_message_bytes = int(maximum_message_bytes)
        socketserver.ThreadingTCPServer.__init__(self, address, _GatewayRequestHandler)


class GatewayTcpServer(object):
    def __init__(self, bind_address, port, dispatcher, maximum_message_bytes=8192):
        self._server = _ThreadedGatewayServer(
            (bind_address, int(port)), dispatcher, maximum_message_bytes)
        self._thread = None

    @property
    def address(self):
        host, port = self._server.server_address
        return {"host": host, "port": port}

    def start(self):
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._server.serve_forever, name="rm65_gateway_tcp")
        self._thread.daemon = True
        self._thread.start()

    def stop(self):
        if self._thread is None:
            return
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=2.0)
        self._thread = None
