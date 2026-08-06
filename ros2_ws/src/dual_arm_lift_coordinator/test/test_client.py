"""RM65 TCP 客户端协议测试，不连接真实设备。"""

import json
import socket
import socketserver
import threading
import unittest

from dual_arm_lift_coordinator.client import Rm65HealthClient, Rm65ProtocolError


class _Handler(socketserver.StreamRequestHandler):
    def handle(self):
        self.server.connections += 1
        raw = self.rfile.readline()
        if not raw:
            return
        request = json.loads(raw.decode('utf-8'))
        self.server.commands.append(request['command'])
        request_id = request.get('request_id')
        if self.server.drop_first and self.server.connections == 1:
            return
        if request_id in self.server.seen:
            response = {'request_id': request_id, 'accepted': False,
                        'code': 'DUPLICATE_REQUEST', 'message': 'request_id was already handled'}
        elif request.get('token') != self.server.token:
            response = {'request_id': request_id, 'accepted': False,
                        'code': 'AUTH_FAILED', 'message': 'authentication failed'}
        elif request['command'] == 'HEALTH':
            self.server.seen.add(request_id)
            response = {'version': 1, 'request_id': request_id, 'accepted': True,
                        'code': 'OK', 'message': 'health returned',
                        'timestamp_utc': '2026-08-06T00:00:00Z',
                        'state': 'IDLE', 'task_id': None, 'fault_code': None,
                        'status': {'state': 'IDLE', 'task_id': None, 'fault_code': None}}
        elif request['command'] == 'PREPARE':
            response = {'request_id': request_id, 'accepted': False,
                        'code': 'ACTUATOR_DISABLED', 'message': 'actuator commands disabled'}
        else:
            response = {'request_id': request_id, 'accepted': False,
                        'code': 'UNSUPPORTED', 'message': 'unsupported command'}
        self.wfile.write((json.dumps(response) + '\n').encode('utf-8'))
        self.wfile.flush()


class _Gateway:
    def __init__(self, token='test-token', drop_first=False):
        self.token = token
        self.drop_first = drop_first
        self.seen = set()
        self.commands = []
        self.connections = 0
        self.server = socketserver.ThreadingTCPServer(('127.0.0.1', 0), _Handler)
        self.server.token = token
        self.server.drop_first = drop_first
        self.server.seen = self.seen
        self.server.commands = self.commands
        self.server.connections = 0
        self.server.timeout = 0.1
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self):
        while not getattr(self.server, '_closed', False) and self.server.connections < 3:
            self.server.handle_request()

    @property
    def address(self):
        return self.server.server_address

    def close(self):
        self.server._closed = True
        self.server.server_close()
        self.thread.join(timeout=1)


class TestRm65HealthClient(unittest.TestCase):
    def setUp(self):
        self.gateway = _Gateway()

    def tearDown(self):
        self.gateway.close()

    def test_normal_health_returns_complete_json(self):
        client = Rm65HealthClient(*self.gateway.address, 'test-token')
        response = client.request_health()
        self.assertTrue(response['accepted'])
        self.assertEqual(response['status']['state'], 'IDLE')
        self.assertEqual(self.gateway.commands, ['HEALTH'])

    def test_wrong_token_is_rejected(self):
        client = Rm65HealthClient(*self.gateway.address, 'wrong-token')
        with self.assertRaisesRegex(Rm65ProtocolError, 'AUTH_FAILED'):
            client.request_health()

    def test_duplicate_request_id_is_rejected_by_gateway(self):
        request = Rm65HealthClient.build_health_request('test-token', 'fixed-id')
        with socket.create_connection(self.gateway.address) as sock:
            line = (json.dumps(request) + '\n').encode('utf-8')
            sock.sendall(line)
            first = json.loads(sock.makefile('rb').readline())
        with socket.create_connection(self.gateway.address) as sock:
            sock.sendall((json.dumps(request) + '\n').encode('utf-8'))
            second = json.loads(sock.makefile('rb').readline())
        self.assertTrue(first['accepted'])
        self.assertEqual(second['code'], 'DUPLICATE_REQUEST')

    def test_disconnect_then_next_health_reconnects(self):
        self.gateway.close()
        gateway = _Gateway(drop_first=True)
        self.gateway = gateway
        client = Rm65HealthClient(*gateway.address, 'test-token', connect_timeout_s=0.5)
        with self.assertRaises((ConnectionError, TimeoutError, OSError)):
            client.request_health()
        response = client.request_health()
        self.assertTrue(response['accepted'])
        self.assertGreaterEqual(gateway.server.connections, 2)

    def test_prepare_rejection_is_supported_by_fixture_but_client_has_no_prepare_api(self):
        self.assertFalse(hasattr(Rm65HealthClient, 'request_prepare'))
        request = {
            'version': 1, 'request_id': 'prepare-id',
            'task_id': 'test', 'command': 'PREPARE',
            'token': 'test-token', 'payload': {'profile': 'default'},
        }
        with socket.create_connection(self.gateway.address) as sock:
            sock.sendall((json.dumps(request) + '\n').encode('utf-8'))
            response = json.loads(sock.makefile('rb').readline())
        self.assertFalse(response['accepted'])
        self.assertEqual(response['code'], 'ACTUATOR_DISABLED')
        self.assertEqual(Rm65HealthClient.build_health_request('test-token')['command'], 'HEALTH')


if __name__ == '__main__':
    unittest.main()
