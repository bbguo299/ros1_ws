# ROS2 宿主机到 ROS1 虚拟机只读 HEALTH 联调手册

## 1. 目的与边界

本手册仅验证 Ubuntu 22.04 ROS2 宿主机的 `rm65_health_client` 能否通过
VMware 虚拟网络访问 Ubuntu 20.04 ROS1 虚拟机中的 RM65 只读网关。

- 宿主机地址：`172.16.108.1`；
- 虚拟机地址：`172.16.108.128`；
- 网关端口：`28400/tcp`；
- 虚拟机 UFW 当前不活动，本阶段不启用 UFW；网关使用来源 IP 白名单；
- 不修改 Wi-Fi、默认路由或 RM65 专用 `ens37` 接口。

本验证不允许发送轨迹、夹爪、急停、IO、示教或力控命令。远程网关固定
`mode: read_only`、`real_hardware_enabled: false` 和 `execution_enabled: false`；
除 `HEALTH` 外的全部任务命令仍返回 `READ_ONLY_MODE`。

## 2. 事前检查

在宿主机与虚拟机分别执行：

```bash
ip -br addr
ip route
```

继续前确认宿主机 `vmnet8` 为 `172.16.108.1/24`，虚拟机 `ens33` 为
`172.16.108.128/24`。VMware 地址发生变化时，只更新本机未跟踪的参数文件，
不得提交真实地址或 token。

虚拟机中现有的 RM65 驱动、`rm_control` 和相机仍按
[RM65_READ_ONLY_GATEWAY_VALIDATION_ZH.md](RM65_READ_ONLY_GATEWAY_VALIDATION_ZH.md)
启动。本手册不启动这些硬件节点。

## 3. 虚拟机网关配置与启动

在 ROS1 虚拟机创建本机私有配置：

```bash
cd /home/fkq/dual_arm_lift/ros1_ws/src/rm65_lift_gateway
cp config/read_only_allowlisted.example.yaml config/read_only_allowlisted.local.yaml
chmod 600 config/read_only_allowlisted.local.yaml
openssl rand -hex 32
```

将生成的随机值写入 `auth_token`，并确认私有配置中的地址保持如下形式：

```yaml
mode: read_only
real_hardware_enabled: false
execution_enabled: false
bind_address: 172.16.108.128
allowed_client_ips: [172.16.108.1]
tcp_port: 28400
auth_token: 随机且非示例值
```

`read_only_allowlisted.local.yaml` 已被包内 `.gitignore` 忽略。远程启动会拒绝
空白来源白名单、`0.0.0.0`、回环监听地址、非单播来源地址，以及 `CHANGE_ME`
或 `simulator-token` 这两个示例 token。

在虚拟机启动只读网关：

```bash
source /opt/ros/noetic/setup.bash
source /home/fkq/rm_ws/devel/setup.bash --extend
source /home/fkq/cam_ws/devel/setup.bash --extend
source /home/fkq/dual_arm_lift/ros1_ws/devel/setup.bash --extend
roslaunch rm65_lift_gateway read_only_allowlisted_gateway.launch \
  config_file:=/home/fkq/dual_arm_lift/ros1_ws/src/rm65_lift_gateway/config/read_only_allowlisted.local.yaml
```

成功标志：日志显示监听 `172.16.108.128:28400`，且 ROS 状态保持 `READ_ONLY`。
若来源不是 `172.16.108.1`，TCP 响应应返回 `CLIENT_IP_NOT_ALLOWED`。

## 4. 宿主机客户端配置与启动

在 ROS2 宿主机创建或更新已忽略的本机参数文件：

```yaml
rm65_health_client:
  ros__parameters:
    rm65_host: 172.16.108.128
    tcp_port: 28400
    auth_token: 与虚拟机相同的随机值
    connect_timeout_s: 2.0
    health_period_s: 5.0
```

然后构建并启动客户端：

```bash
cd /home/fkq/dual_arm_lift/ros2_ws
source /opt/ros/humble/setup.bash
colcon build --packages-select dual_arm_lift_coordinator
source install/setup.bash
ros2 launch dual_arm_lift_coordinator rm65_health_client.launch.py \
  params_file:=/home/fkq/dual_arm_lift/ros2_ws/src/dual_arm_lift_coordinator/params/local.yaml
```

在另一个终端观察：

```bash
source /opt/ros/humble/setup.bash
source /home/fkq/dual_arm_lift/ros2_ws/install/setup.bash
ros2 topic echo /rm65/connection_status
ros2 topic echo /rm65/recent_error
ros2 topic echo /rm65/health
```

## 5. 验收与故障定位

连续运行 10 分钟。通过判据：

- `/rm65/connection_status` 保持 `connected`；
- `/rm65/recent_error` 为空；
- `/rm65/health` 周期更新，且其中 RM65 网关状态为 `READ_ONLY`；
- 网关状态中的 `motion_permitted=false`、`gripper_permitted=false`；
- 关闭网关后客户端转为 `disconnected`，恢复网关后下一轮轮询自动恢复 `connected`。

若状态为 `disconnected`，先核对 VMware 地址、端口 `28400`、两端 token 和
`allowed_client_ips`。若返回 `AUTH_FAILED`，只检查 token 是否一致；若返回
`CLIENT_IP_NOT_ALLOWED`，只检查虚拟机看到的宿主机来源地址。任何错误均停留在
只读排查阶段，不得改变执行开关或发送执行命令。

本阶段不启用 UFW。实体机部署前，必须先盘点现有 SSH、ROS 与网络规则，再单独
设计防火墙放行策略，不能直接复用本虚拟机验收结果。
