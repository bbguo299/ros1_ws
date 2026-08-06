"""ROS2 节点：周期读取 RM65 HEALTH 并发布状态。"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Optional

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from .client import Rm65HealthClient


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


class Rm65HealthNode(Node):
    """只发布 HEALTH JSON 及连接元数据，不发布任何 RM65 ROS1 话题。"""

    def __init__(self) -> None:
        super().__init__('rm65_health_client')
        self.declare_parameter('rm65_host', '127.0.0.1')
        self.declare_parameter('tcp_port', 5000)
        self.declare_parameter('auth_token', 'CHANGE_ME')
        self.declare_parameter('connect_timeout_s', 2.0)
        self.declare_parameter('health_period_s', 5.0)
        host = str(self.get_parameter('rm65_host').value)
        port = int(self.get_parameter('tcp_port').value)
        token = str(self.get_parameter('auth_token').value)
        self._client = Rm65HealthClient(
            host, port, token, float(self.get_parameter('connect_timeout_s').value))
        self._health_pub = self.create_publisher(String, 'rm65/health', 10)
        self._connection_pub = self.create_publisher(String, 'rm65/connection_status', 10)
        self._success_pub = self.create_publisher(String, 'rm65/recent_success_time', 10)
        self._error_pub = self.create_publisher(String, 'rm65/recent_error', 10)
        self._publish(self._connection_pub, 'disconnected')
        self._publish(self._success_pub, '')
        self._publish(self._error_pub, '')
        period = float(self.get_parameter('health_period_s').value)
        if period <= 0:
            raise ValueError('health_period_s 必须大于 0')
        self._timer = self.create_timer(period, self._poll_health)

    @staticmethod
    def _publish(publisher, value: str) -> None:
        message = String()
        message.data = value
        publisher.publish(message)

    def _poll_health(self) -> None:
        try:
            response = self._client.request_health()
        except Exception as exc:  # 网络、认证和协议错误都反馈给 ROS2
            self._publish(self._connection_pub, 'disconnected')
            self._publish(self._error_pub, '{}: {}'.format(type(exc).__name__, exc))
            return
        self._publish(self._health_pub, json.dumps(response, sort_keys=True, separators=(',', ':')))
        self._publish(self._connection_pub, 'connected')
        self._publish(self._success_pub, response.get('timestamp_utc', _utc_now()))
        self._publish(self._error_pub, '')


def main(args: Optional[list[str]] = None) -> None:
    rclpy.init(args=args)
    node = Rm65HealthNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
