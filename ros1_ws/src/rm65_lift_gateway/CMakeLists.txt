cmake_minimum_required(VERSION 3.0.2)
project(rm65_lift_gateway)

find_package(catkin REQUIRED COMPONENTS
  actionlib
  control_msgs
  rospy
  sensor_msgs
  std_msgs
  std_srvs
)

catkin_python_setup()
catkin_package()

catkin_install_python(
  PROGRAMS scripts/rm65_lift_gateway_node.py
  DESTINATION ${CATKIN_PACKAGE_BIN_DESTINATION}
)

install(DIRECTORY config launch
  DESTINATION ${CATKIN_PACKAGE_SHARE_DESTINATION}
)

if(CATKIN_ENABLE_TESTING)
  catkin_add_nosetests(test)
endif()
