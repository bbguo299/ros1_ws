#!/usr/bin/env python3
from __future__ import absolute_import

import rospy

from rm65_lift_gateway.node import RosGatewayNode


def main():
    rospy.init_node("rm65_lift_gateway")
    try:
        RosGatewayNode()
    except RuntimeError as exc:
        rospy.logfatal("RM65 simulation gateway refused to start: %s", exc)
        raise
    rospy.spin()


if __name__ == "__main__":
    main()
