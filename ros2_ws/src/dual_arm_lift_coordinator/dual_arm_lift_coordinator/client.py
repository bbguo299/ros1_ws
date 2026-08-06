"""RM65 网关的最小只读 TCP 客户端。

协议是每行一个 JSON 对象。此模块故意只暴露 HEALTH，避免调用执行器命令。
"""

from __future__ import annotations

import json
import socket
import uuid
from typing import Any, Dict, Optional


class Rm65ProtocolError(RuntimeError):
    """网关返回协议错误或非预期响应。"""


class Rm65HealthClient:
    """每次 HEALTH 请求使用一个短连接，连接失败时下次请求自动重连。"""

    def __init__(self, host: str, port: int, token: str, connect_timeout_s: float = 2.0,
                 max_message_bytes: int = 1024 * 1024) -> None:
        if not host:
            raise ValueError('host 不能为空')
        if not token:
            raise ValueError('auth_token 不能为空')
        if not 1 <= int(port) <= 65535:
            raise ValueError('tcp_port 必须在 1 到 65535 之间')
        if float(connect_timeout_s) <= 0:
            raise ValueError('connect_timeout_s 必须大于 0')
        self.host = host
        self.port = int(port)
        self.token = token
        self.connect_timeout_s = float(connect_timeout_s)
        self.max_message_bytes = int(max_message_bytes)

    @staticmethod
    def build_health_request(token: str, request_id: Optional[str] = None) -> Dict[str, Any]:
        """构造请求；不提供其它 command 的构造接口。"""
        return {
            'version': 1,
            'request_id': request_id or str(uuid.uuid4()),
            'task_id': 'dual_arm_lift_coordinator-health',
            'command': 'HEALTH',
            'token': token,
            'payload': {},
        }

    def request_health(self) -> Dict[str, Any]:
        """发送一次 HEALTH 并返回网关返回的完整 JSON。"""
        request = self.build_health_request(self.token)
        encoded = (json.dumps(request, separators=(',', ':')) + '\n').encode('utf-8')
        with socket.create_connection((self.host, self.port), self.connect_timeout_s) as sock:
            sock.settimeout(self.connect_timeout_s)
            sock.sendall(encoded)
            response_bytes = self._readline(sock)
        try:
            response = json.loads(response_bytes.decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise Rm65ProtocolError('网关返回了无效 JSON') from exc
        if not isinstance(response, dict):
            raise Rm65ProtocolError('网关返回值不是 JSON 对象')
        if response.get('request_id') != request['request_id']:
            raise Rm65ProtocolError('响应 request_id 不匹配')
        if response.get('accepted') is not True:
            raise Rm65ProtocolError(
                '{}: {}'.format(response.get('code', 'REJECTED'), response.get('message', '')))
        return response

    def _readline(self, sock: socket.socket) -> bytes:
        chunks = bytearray()
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                raise ConnectionError('网关在返回响应前断开连接')
            chunks.extend(chunk)
            if len(chunks) > self.max_message_bytes:
                raise Rm65ProtocolError('网关响应超过大小限制')
            if b'\n' in chunk:
                return bytes(chunks).split(b'\n', 1)[0]

