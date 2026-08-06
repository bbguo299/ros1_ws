"""ROS wrapper for simulation and read-only RM65 gateway modes."""

from __future__ import absolute_import

import json
import ipaddress

import rospy
from std_msgs.msg import String
from std_srvs.srv import Trigger, TriggerResponse

from rm65_lift_gateway.adapters import SimGripperAdapter, SimRobotAdapter, SimVisionAdapter
from rm65_lift_gateway.guarded_real import GuardedExecutionPolicy, GuardedRealGateway
from rm65_lift_gateway.protocol import GatewayDispatcher, GatewayTcpServer
from rm65_lift_gateway.read_only import ReadOnlyGateway, ReadOnlyRosAdapter
from rm65_lift_gateway.state_machine import GatewayStateMachine


class RosGatewayNode(object):
    def __init__(self):
        if bool(rospy.get_param("~real_hardware_enabled", False)):
            raise RuntimeError("real_hardware_enabled must remain false; this gateway cannot command hardware")
        if bool(rospy.get_param("~execution_enabled", False)):
            raise RuntimeError("execution_enabled must remain false; this gateway cannot command hardware")
        mode = rospy.get_param("~mode", "simulation")
        bind_address = rospy.get_param("~bind_address", "127.0.0.1")
        allowed_client_ips = self._allowed_client_ips(mode, bind_address)
        auth_token = rospy.get_param("~auth_token")
        if bind_address != "127.0.0.1" and auth_token in ("CHANGE_ME", "simulator-token"):
            raise RuntimeError("remote read_only mode requires a non-example auth_token")
        if mode == "simulation":
            profiles = rospy.get_param("~profiles", {})
            adapters = {
                "robot": SimRobotAdapter(),
                "vision": SimVisionAdapter(),
                "gripper": SimGripperAdapter(),
            }
            self._machine = GatewayStateMachine(
                profiles, adapters,
                rospy.get_param("~past_start_tolerance_s", 0.1),
                rospy.get_param("~max_start_delay_s", 30.0))
        elif mode == "read_only":
            self._machine = ReadOnlyGateway(ReadOnlyRosAdapter(self._read_only_config()))
        elif mode == "guarded_real":
            self._machine = GuardedRealGateway(
                ReadOnlyRosAdapter(self._read_only_config()),
                GuardedExecutionPolicy(rospy.get_param("~profiles", {})))
        else:
            raise RuntimeError("unsupported gateway mode: %s" % mode)
        dispatcher = GatewayDispatcher(
            self._machine,
            auth_token,
            rospy.get_param("~max_seen_request_ids", 1024))
        self._server = GatewayTcpServer(
            bind_address,
            rospy.get_param("~tcp_port", 28400),
            dispatcher,
            rospy.get_param("~maximum_message_bytes", 8192),
            allowed_client_ips)
        self._status_pub = rospy.Publisher("~status", String, queue_size=1, latch=True)
        self._reset_service = rospy.Service("~reset_fault", Trigger, self._reset_fault)
        frequency = float(rospy.get_param("~status_publish_rate_hz", 5.0))
        self._status_timer = rospy.Timer(rospy.Duration(1.0 / max(0.1, frequency)), self._publish_status)
        self._server.start()
        rospy.on_shutdown(self._server.stop)
        rospy.loginfo("RM65 %s gateway listening on %s:%d", mode, bind_address, self._server.address["port"])
        self._publish_status(None)

    @staticmethod
    def _allowed_client_ips(mode, bind_address):
        if bind_address == "127.0.0.1":
            return None
        if mode != "read_only":
            raise RuntimeError("only read_only mode may bind a non-loopback address")
        try:
            parsed_bind_address = ipaddress.IPv4Address(bind_address)
        except ipaddress.AddressValueError:
            raise RuntimeError("remote read_only bind_address must be an IPv4 address")
        if parsed_bind_address.is_loopback or parsed_bind_address.is_unspecified:
            raise RuntimeError("remote read_only bind_address must be a specific non-loopback IPv4 address")
        configured_ips = rospy.get_param("~allowed_client_ips", [])
        if not isinstance(configured_ips, list) or not configured_ips:
            raise RuntimeError("remote read_only mode requires a non-empty allowed_client_ips list")
        allowed_client_ips = []
        for client_ip in configured_ips:
            try:
                parsed_client_ip = ipaddress.IPv4Address(client_ip)
            except ipaddress.AddressValueError:
                raise RuntimeError("allowed_client_ips must contain IPv4 addresses")
            if parsed_client_ip.is_unspecified or parsed_client_ip.is_multicast:
                raise RuntimeError("allowed_client_ips must contain unicast IPv4 addresses")
            allowed_client_ips.append(str(parsed_client_ip))
        return allowed_client_ips

    @staticmethod
    def _read_only_config():
        return {
            "required_joint_names": rospy.get_param("~required_joint_names"),
            "joint_state_fresh_timeout_s": rospy.get_param("~joint_state_fresh_timeout_s", 0.75),
            "camera_fresh_timeout_s": rospy.get_param("~camera_fresh_timeout_s", 2.0),
            "observability_window_s": rospy.get_param("~observability_window_s", 600.0),
            "action_server_wait_s": rospy.get_param("~action_server_wait_s", 3.0),
            "joint_states_topic": rospy.get_param("~joint_states_topic", "/joint_states"),
            "trajectory_action": rospy.get_param("~trajectory_action", "/rm_65/follow_joint_trajectory"),
            "arm_error_topic": rospy.get_param("~arm_error_topic", "/rm_driver/ArmError"),
            "sys_error_topic": rospy.get_param("~sys_error_topic", "/rm_driver/SysError"),
            "color_image_topic": rospy.get_param("~color_image_topic", "/camera/color/image_raw"),
            "depth_image_topic": rospy.get_param("~depth_image_topic", "/camera/depth/image_raw"),
            "color_info_topic": rospy.get_param("~color_info_topic", "/camera/color/camera_info"),
            "depth_info_topic": rospy.get_param("~depth_info_topic", "/camera/depth/camera_info"),
        }

    def _reset_fault(self, _request):
        ok, message = self._machine.reset_fault()
        self._publish_status(None)
        return TriggerResponse(ok, message)

    def _publish_status(self, _event):
        self._status_pub.publish(String(data=json.dumps(self._machine.snapshot(), sort_keys=True)))
