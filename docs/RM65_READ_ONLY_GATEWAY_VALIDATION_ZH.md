# RM65 只读网关验证手册

## 1. 目的与安全边界

本手册验证 Ubuntu 20.04 / ROS1 上的 RM65 单机只读网关是否能看见：

- RM65 驱动的六轴关节状态和错误码；
- `/rm_65/follow_joint_trajectory` Action server；
- Gemini 相机的彩色/深度图和 CameraInfo；
- 网关本地 TCP `HEALTH` 接口。

本验证**不允许**发送轨迹、夹爪、急停、示教、IO 或力控命令。网关启动后也会拒绝 `PREPARE`、`GRIP`、`ARM_LIFT`、`HOLD`、`ABORT`，返回 `READ_ONLY_MODE`。

开始前确认机械臂工作区安全、急停可用，并由现场人员监护。已运行的节点不要重复启动。

### 当前现场基线（2026-08-06）

本手册已在当前 Ubuntu 20.04 现场通过一次只读健康验收、一次连续 10 分钟观测和错误码话题只读核对：网关状态为 `READ_ONLY` 和 `health.ready=true`；RM65 Action server、六轴关节状态、彩色/深度图与两个 CameraInfo 均健康。连续观测中，关节状态平均约 `49.02 Hz`、最长间隔约 `0.049 s`；四路相机各平均约 `29.96 Hz`、最长间隔约 `0.052..0.083 s`；Action server 无可用性变化，两个错误码无非零记录。`/rm_driver` 已确认是两个 `std_msgs/UInt16` 错误码话题的发布者，网关为订阅者；正常状态下分别观察 60 秒均无消息且超时。该结果表示话题在正常状态下静默，并不验证非零错误的上报行为。这只证明观测通路稳定，不改变本手册的“禁止控制命令”边界；完整证据见 [PROJECT_LOG.md](PROJECT_LOG.md)。

## 2. 终端与启动顺序

以下命令均在 Ubuntu 20.04 / ROS1 主机执行。每个 `roslaunch` 占用一个终端并持续运行。

### 终端 0：构建工作空间

```bash
cd /home/fkq/dual_arm_lift/ros1_ws
source /opt/ros/noetic/setup.bash
catkin_make
```

成功标志：命令退出码为 `0`，末尾没有 CMake 或 Python 错误。

### 终端 1：ROS master

仅在 `rosnode list` 报“Unable to communicate with master”且没有其他 ROS master 时执行：

```bash
source /opt/ros/noetic/setup.bash
roscore
```

成功标志：终端显示 `started core service [/rosout]`。若 RM65 栈已启动，不要再启动第二个 `roscore`。

### 终端 2：RM65 驱动与 MoveIt 实机配置

```bash
source /opt/ros/noetic/setup.bash
source /home/fkq/rm_ws/devel/setup.bash --extend
roslaunch rm_bringup rm_robot.launch
```

该 launch 启动 `rm_driver`、`robot_state_publisher` 和 MoveIt `move_group`。它本身不提供 RM65 轨迹 Action server。

成功标志：没有驱动连接错误，后续能看到 `/joint_states`、`/rm_driver/ArmError`、`/rm_driver/SysError`、`/move_group/status`。

### 终端 3：RM65 轨迹 Action server

```bash
source /opt/ros/noetic/setup.bash
source /home/fkq/rm_ws/devel/setup.bash --extend
roslaunch rm_control rm_control.launch
```

成功标志：后续能看到：

```text
/rm_65/follow_joint_trajectory/goal
/rm_65/follow_joint_trajectory/cancel
/rm_65/follow_joint_trajectory/status
/rm_65/follow_joint_trajectory/feedback
/rm_65/follow_joint_trajectory/result
```

只读网关只检查该 Action server 是否存在，绝不发送 goal。

### 终端 4：Gemini 相机

当前现场使用 Orbbec 默认 `camera_name:=camera`，网关配置对应 `/camera/...` 话题：

```bash
source /opt/ros/noetic/setup.bash
source /home/fkq/cam_ws/devel/setup.bash --extend
roslaunch orbbec_camera gemini_330_series.launch camera_name:=camera
```

若现场已知相机序列号，应额外指定，避免接错设备：

```bash
roslaunch orbbec_camera gemini_330_series.launch \
  camera_name:=camera serial_number:=实际相机序列号
```

成功标志：后续能看到：

```text
/camera/color/image_raw
/camera/color/camera_info
/camera/depth/image_raw
/camera/depth/camera_info
```

### 终端 5：只读网关

```bash
source /opt/ros/noetic/setup.bash
source /home/fkq/rm_ws/devel/setup.bash --extend
source /home/fkq/cam_ws/devel/setup.bash --extend
source /home/fkq/dual_arm_lift/ros1_ws/devel/setup.bash --extend
roslaunch rm65_lift_gateway read_only_gateway.launch
```

成功标志：网关日志包含类似内容：

```text
RM65 read_only gateway listening on 127.0.0.1:28400
```

启动时最多等待 3 秒探测 Action server；即使未探测到，网关也会启动并在状态中报告未就绪原因。

## 3. ROS 健康验证

### 终端 6：检查节点与接口归属

```bash
source /opt/ros/noetic/setup.bash
source /home/fkq/rm_ws/devel/setup.bash --extend
rosnode list

rosnode info /rm_driver
rosnode info /rm_control
rosnode info /move_group

rostopic info /joint_states
rostopic info /rm_65/follow_joint_trajectory/status
rostopic info /move_group/status
```

成功判据：

- `/rm_driver` 存在，并发布 `/joint_states`；
- `/rm_control` 存在，并发布轨迹 Action 的 `status`，订阅 `goal` 与 `cancel`；
- `/move_group` 存在，并发布 `/move_group/status`；
- `/joint_states` 至少有一个发布者；
- 不执行 `rostopic pub`、`rosservice call` 或任何 Action goal。

### 终端 7：检查实际数据是否持续更新

以下命令可逐个运行，使用 `Ctrl-C` 结束每个速率统计：

```bash
rostopic hz /joint_states
rostopic hz /camera/color/image_raw
rostopic hz /camera/depth/image_raw

rostopic info /rm_driver/ArmError
rostopic info /rm_driver/SysError

timeout 60s rostopic echo -n 1 /rm_driver/ArmError
echo "ArmError exit code: $?"

timeout 60s rostopic echo -n 1 /rm_driver/SysError
echo "SysError exit code: $?"
```

成功判据：

- 三个 `hz` 命令均持续输出非零速率；
- 两个 `rostopic info` 命令均显示 `/rm_driver` 为发布者、消息类型为 `std_msgs/UInt16`；
- 在 60 秒内收到 `data: 0` 时，记录为正常零值发布，网关应显示 `seen=true`、`active=false`；超时（退出码 `124`）时记录为当前现场静默，不将其误判为故障；
- `ArmError` 与 `SysError` 的值为 `0`，或网关状态中其 `active` 为 `false`；
- 若错误码非零，不得继续进入真实控制阶段，应先按 RM65 厂商流程排除故障。

驱动源码的静态结论是：`/rm_driver` 会在解析到包含 `arm_err`、`sys_err` 的 UDP 状态包时发布两个错误码话题。正常运行下未收到消息，可能表示当前 UDP 推送没有该字段或该发布路径未触发；验证非零上报需要厂商书面流程和现场监护，本手册不要求也不允许人为制造故障。

### 终端 8：查看网关综合状态

```bash
source /opt/ros/noetic/setup.bash
source /home/fkq/dual_arm_lift/ros1_ws/devel/setup.bash --extend
rostopic echo -n 1 /rm65_lift_gateway/status
```

成功时 JSON 中必须同时满足：

```json
{
  "state": "READ_ONLY",
  "health": {
    "read_only": true,
    "motion_permitted": false,
    "gripper_permitted": false,
    "ready": true,
    "driver": {
      "ready": true,
      "joint_state": {
        "ready": true,
        "missing_joint_names": []
      },
      "action_server": {"ready": true}
    },
    "camera": {"ready": true}
  }
}
```

其中 `joint_state.age_s` 必须不大于 `0.75`，四个 `camera.streams.*.age_s` 必须不大于 `2.0`。`ArmError` 或 `SysError` 尚未收到过消息时，`seen` 可为 `false`，但 `active` 必须为 `false`。

### 连续 10 分钟观测基线

在网关持续运行且没有发送任何控制命令的条件下，等待完整 10 分钟后再读取一次状态：

```bash
date -u
sleep 600
rostopic echo -n 1 /rm65_lift_gateway/status
date -u
```

读取 `health.observability`。该对象仅保留网关进程内最近 `600 s` 的观测数据，不写入 rosbag、日志或磁盘，也不参与 `health.ready` 判定：

- `joint_state` 与 `camera_streams.*`：记录窗口内消息数、平均频率、最近/最短/最长消息间隔和最后接收 UTC 时间；
- `action_server`：记录当前可用性、窗口内可用性变化次数和最后变化 UTC 时间；
- `arm_error`、`sys_error`：记录窗口内非零消息次数和最后一次非零 UTC 时间。

通过判据：`health.ready=true`；五个数据流的 `message_count` 均大于 `0`；各流的 `max_interval_s` 不超过相应现有新鲜度阈值（关节 `0.75 s`，相机 `2.0 s`）；`action_server.availability_change_count=0`；两个错误码的 `nonzero_sample_count=0`。频率仅作为现场基线记录，不设置未经验证的最低 Hz 门限。若任一项不满足，只记录现象并停留在只读排查阶段，不得进入真实控制。

## 4. TCP 协议验证

网关只监听本机 `127.0.0.1:28400`。以下命令仅发送 `HEALTH` 与一个应被拒绝的 `PREPARE` 测试请求，不会控制硬件：

```bash
python3 - <<'PY'
import json
import socket

requests = [
    {
        "version": 1,
        "request_id": "read-only-health-001",
        "task_id": "read-only-check",
        "command": "HEALTH",
        "token": "simulator-token",
        "payload": {},
    },
    {
        "version": 1,
        "request_id": "read-only-prepare-001",
        "task_id": "read-only-check",
        "command": "PREPARE",
        "token": "simulator-token",
        "payload": {"profile": "demo"},
    },
]

with socket.create_connection(("127.0.0.1", 28400), timeout=3.0) as connection:
    stream = connection.makefile("rwb")
    for request in requests:
        stream.write((json.dumps(request) + "\n").encode("utf-8"))
        stream.flush()
        print(json.loads(stream.readline().decode("utf-8")))
PY
```

成功判据：

- `HEALTH` 响应的 `accepted` 为 `true`，`state` 为 `READ_ONLY`；
- `PREPARE` 响应的 `accepted` 为 `false`，`code` 为 `READ_ONLY_MODE`；
- 不应出现任何机械臂、夹爪或相机动作。

## 5. 常见失败与处理

| 网关状态或现象 | 原因 | 只读处理方式 |
|---|---|---|
| `driver.joint_state.ready=false` | 驱动未启动、状态更新过慢或关节名不完整 | 检查 `/joint_states` 发布者和 `rostopic hz /joint_states`。 |
| `driver.action_server.ready=false` | `rm_control` 未启动或 Action 名称不一致 | 检查终端 3 和 `/rm_65/follow_joint_trajectory/status`。 |
| `camera.ready=false` | 相机未启动、帧流停止或命名空间不是 `/camera` | 检查相机 launch 与四个 `/camera` 话题；改名后同步修改 `read_only.yaml`。 |
| `arm_error.active=true` 或 `sys_error.active=true` | RM65 控制器报告故障 | 停止验证，按厂商流程和现场安全规范排除故障。 |
| 无 `/rm65_lift_gateway/status` | 网关未启动、环境未 source 或 ROS master 不一致 | 检查终端 5、`ROS_MASTER_URI` 和 `rosnode list`。 |
| TCP 连接被拒绝 | 网关未运行或端口被占用 | 检查网关终端日志；只读模式只允许本机 `127.0.0.1`。 |

## 6. 通过后的边界

本手册通过只表示“Ubuntu 20.04 主机可只读观测 RM65、Action server 与相机”。它不表示允许执行抓取或举升。进入下一阶段前仍需要：夹持成功反馈、ArUco 标定和视觉互锁、已验证轨迹、真实载荷参数、急停流程，以及 Ubuntu 22.04 / ECO65 端的独立验收。

`guarded_real_gateway.launch` 仅用于检查未来轨迹档案格式和复用只读健康状态，启动后状态为 `GUARDED_REAL`，且所有执行命令返回 `REAL_EXECUTION_DISABLED`。它不能替代上述前置条件，不得与同端口的 `read_only_gateway.launch` 同时启动，也不得作为真实执行授权依据。
