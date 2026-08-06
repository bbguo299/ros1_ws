"""启动只读 RM65 HEALTH 客户端。"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory


def generate_launch_description():
    default_params = get_package_share_directory('dual_arm_lift_coordinator')
    default_params += '/params/local.example.yaml'
    return LaunchDescription([
        DeclareLaunchArgument('params_file', default_value=default_params),
        Node(
            package='dual_arm_lift_coordinator',
            executable='rm65_health_client',
            name='rm65_health_client',
            output='screen',
            parameters=[LaunchConfiguration('params_file')],
        ),
    ])
