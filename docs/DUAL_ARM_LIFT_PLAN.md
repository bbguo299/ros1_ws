# 双机械臂协同夹取方框并同步举升方案

## 1. 目标与边界

目标是在固定机械臂底座的工位内，让 RM65-B 与 ECO65-6F 分别夹住约
`500 mm × 500 mm` 方框的两端，以低速、近同步方式抬升到配置的目标高度。

- RM65-B 使用 ArUco 驱动的本机 MoveIt 完成预抓取与抓取接近；同步抬升执行经示教、离线验证的固定关节轨迹。
- ECO65-6F 执行对应的本地轨迹与六维力位混合，用于抑制夹持引入的侧向力、拉力和扭矩。
- V1 范围为观察/校验、预抓取、抓取、同步抬升、保持与中止。
- 不包含移动底盘、使用在线 MoveIt 生成载荷抬升轨迹、未经标定的真实载荷执行或跨机高频控制。

> 网络只传递任务级指令、状态与故障；高频关节控制和力控闭环必须留在各自机械臂所连接的本机。

## 2. 部署边界

| 部署端 | 操作系统与中间件 | 工作空间/软件 | 本机职责 | 不应部署或执行 |
|---|---|---|---|---|
| RM65-B 执行端 | **Ubuntu 20.04 + ROS1 Noetic** | `/home/fkq/rm_ws`、`/home/fkq/cam_ws`、`/home/fkq/rm_grasp_ws`、`/home/fkq/dual_arm_lift/ros1_ws` | RM65-B 驱动、Gemini 相机、RM65 本地视觉校验、TCP 服务端、RM65 本地轨迹与夹爪执行 | ROS2 Humble 包、ECO65 力控闭环、ROS2 协调器 |
| ECO65-6F 主控端 | **Ubuntu 22.04 + ROS2 Humble** | `/home/fkq/ros2_rm_ws`、`/home/fkq/Orbbec_ws`、`/home/fkq/dual_arm_lift/ros2_ws` | ECO65 驱动、六维力位混合、Gemini 相机、本地视觉校验、双臂任务协调器、TCP 客户端 | ROS1 Noetic 包、RM65 高频轨迹或夹爪控制 |
| 共享配置 | 两机均可读取，不作为 ROS 工作空间 | `/home/fkq/dual_arm_lift/shared` | TCP 协议说明、任务模板、标定与已验证轨迹的版本化副本 | ROS1/ROS2 源码混编或跨机控制节点 |

`ros1_ws` 只在 Ubuntu 20.04 主机编译和运行；`ros2_ws` 只在 Ubuntu 22.04 主机编译和运行。两者不得互相 overlay，也不得把 ROS1 Noetic 与 ROS2 Humble 包放进同一 catkin/colcon 工作空间。

## 3. 已确认接口

### 3.1 Ubuntu 20.04：RM65-B ROS1 执行端

| 模块 | 路径或接口 | 约束 |
|---|---|---|
| RM65-B 驱动 | `/home/fkq/rm_ws/src` | `rm_control` 提供 `/rm_65/follow_joint_trajectory`（`control_msgs/FollowJointTrajectory`）。 |
| RM65 Action 轨迹 | `/rm_65/follow_joint_trajectory` | 每个路点必须提供 6 轴 `positions`、`velocities`、`accelerations`；现有实现不以 `trajectory.header.stamp` 延迟调度。网关必须在本机等待 `ARM_LIFT` 的绝对时刻后再发送完整 goal。 |
| 关节与夹爪 | `/joint_states`、`/rm_driver/Gripper_Set` | `Gripper_Set.position` 为 `1..1000`，约对应 `0..70 mm` 开口；真实举升必须另有夹持成功反馈，单纯闭合命令不构成放行条件。 |
| 既有视觉抓取 | `/home/fkq/rm_grasp_ws/src/rm65_visual_grasp` | 当前观察位服务为 `/rm65_visual_grasp/move_to_observation`；旧的 `/rm_65_observation/move_to_observation` 已移除。可复用标定、观察位和 ArUco 感知，并在本机 MoveIt 中用于预抓取与抓取接近；载荷抬升阶段不使用在线 MoveIt 轨迹。 |
| Gemini 相机 | `/home/fkq/cam_ws/src` | 当前现场以默认 `camera_name:=camera` 启动，实测话题为 `/camera/color/image_raw`、`/camera/color/camera_info`、`/camera/depth/image_raw`、`/camera/depth/camera_info`。如改用 `camera_name:=rm65_cam`，必须同时修改本机视觉和网关配置，且始终按实际序列号绑定设备。 |
| RM65 网关 | `/home/fkq/dual_arm_lift/ros1_ws/src/rm65_lift_gateway` | 当前提供模拟、只读及 `guarded_real` 档案校验骨架，均仅绑定 `127.0.0.1`；`guarded_real` 不含控制 ROS 接口，后续仍须在安全前置条件齐备后才接入真实执行。 |

### 3.2 Ubuntu 22.04：ECO65-6F ROS2 主控端

| 模块 | 路径或接口 | 约束 |
|---|---|---|
| ECO65-6F 驱动 | `/home/fkq/ros2_rm_ws/src/ros2_rm_robot-humble` | `rm_control` 提供 `/rm_group_controller/follow_joint_trajectory`。所有 ECO65 轨迹仅由本机 ROS2 节点发送。 |
| 六维力位混合 | ROS2 `rm_ros_interfaces` 的 `Forcepositionmove` | 以方框/工具坐标系定义六方向模式、期望力/力矩和速度上限；先完成传感器零点、工具质量/重心与载荷重力补偿。 |
| Gemini 相机 | `/home/fkq/Orbbec_ws/src/OrbbecSDK_ROS2` | 使用 `ros2 launch orbbec_camera gemini_330_series.launch.py camera_name:=eco65_cam serial_number:=<序列号>`。 |
| 双臂协调器 | `/home/fkq/dual_arm_lift/ros2_ws` | 管理任务状态机、ECO65 本地执行、时间同步检查与对 ROS1 网关的 TCP 客户端连接；不直接发布 RM65 ROS1 话题。 |
| ECO65 夹爪 | 待确认 | 未获得可靠的夹持成功反馈前，真实模式必须拒绝进入 `ARM_LIFT`。 |

两台相机必须按序列号绑定。当前 Ubuntu 20.04 端使用默认 `/camera` 命名空间；若未来需要在同一 ROS 图中区分设备，可改为 `rm65_cam` 与 `eco65_cam`，并同步修改各自配置中的话题名称。

## 4. 总体结构与跨机协议

```text
Ubuntu 22.04 / ROS2 Humble                         Ubuntu 20.04 / ROS1 Noetic
ECO65 驱动、力控、视觉、协调器、TCP 客户端  ───►  RM65 驱动、视觉、TCP 服务端
        仅发送任务、状态、视觉摘要、故障            仅执行本地 RM65 动作
```

跨机 TCP 使用换行分隔 UTF-8 JSON。每条请求必须包含：

```json
{
  "version": 1,
  "request_id": "uuid",
  "task_id": "string",
  "command": "HEALTH|PREPARE|GRIP|ARM_LIFT|HOLD|ABORT",
  "token": "configured-token",
  "payload": {}
}
```

- `HEALTH` 返回驱动、视觉、夹爪、时间同步及当前状态摘要。
- `PREPARE` 选择已验证的预抓取档案，执行本机预抓取。
- `GRIP` 执行本机夹爪闭合并等待可靠的本机夹持结果。
- `ARM_LIFT` 携带档案名与 RFC3339 `start_time_utc`；两端确认 `ARMED` 后，在各自本机绝对时刻开始。
- `HOLD` 保持当前位置；`ABORT` 取消或停止本机当前任务并报告故障。
- 网络断开、认证失败、重复 `request_id`、状态跳变、档案不匹配、过期启动时刻均必须拒绝执行。

## 5. 坐标、视觉和轨迹配置

固定底座阶段统一使用 `world`：

```text
world
├─ eco65_base → eco65_tool → eco65_gripper
├─ rm65_base  → rm65_tool  → rm65_gripper
├─ eco65_camera
├─ rm65_camera
└─ frame_center
```

在共享配置中维护并经现场标定：

1. `world → eco65_base`、`world → rm65_base`；
2. 相机相对所属底座的外参；
3. ArUco 字典、ID、边长和标记相对方框中心的变换；
4. 方框初始位姿允许范围；
5. 两端抓取/预抓取/抬升路点，及速度、加速度、位置误差限制；
6. 方框质量、重心、夹持力和允许力/力矩阈值。

V1 的 ArUco 同时提供抓取目标和安全互锁：每台机械臂根据 `base -> camera -> aruco -> box -> grasp` 计算本机 MoveIt 的预抓取和抓取接近目标；两端均检测到新鲜标记且位姿满足容差，才能进入抓取。`world` 用于固定工位中的跨机几何一致性校验；若先以各自 `base` 完成单机规划，仍必须维护共同的 `box` 坐标系。ArUco 不在线生成载荷抬升轨迹。

## 6. 任务状态机与控制分工

```text
IDLE → VALIDATE_VISION → PREPARE → GRIP → ARM_LIFT → LIFT → HOLD → COMPLETE
任意阶段异常 → ABORT
```

| 阶段 | Ubuntu 22.04 / ROS2 责任 | Ubuntu 20.04 / ROS1 责任 | 放行条件 |
|---|---|---|---|
| `VALIDATE_VISION` | 本机 ECO65 相机校验 | 本机 RM65 相机校验并经 TCP 摘要上报 | 两端标记新鲜、位姿合格、无视觉故障。 |
| `PREPARE` | 依据本机 ArUco 目标由 MoveIt 到预抓取位 | 依据本机 ArUco 目标由 MoveIt 到观察/预抓取位 | 两端目标位姿合格、规划成功、动作成功，关节状态新鲜。 |
| `GRIP` | ECO65 本机夹爪与反馈 | RM65 本机夹爪与反馈 | 两端均确认夹持成功。 |
| `ARM_LIFT` | 生成未来绝对启动时刻并预装载 ECO65 任务 | 校验档案与时间并返回 `ARMED` | 时间同步已验证，配置匹配。 |
| `LIFT` | 本机轨迹与力位混合 | 本机等待到时后发送完整 RM65 Action goal | 速度/误差/力矩未超限。 |
| `HOLD` / `ABORT` | 停止或保持 ECO65，并上报故障 | 停止或保持 RM65，并上报故障 | 任一端故障即两端保持或中止。 |

两台电脑必须由 `chrony` 或等效 NTP 服务同步；未测量并满足启动误差阈值时，禁止真实同步举升。

## 7. 安全限制与验证顺序

方框夹取与载荷抬升的真实执行开关默认关闭。夹持成功反馈、视觉标定、已验证的抓取/抬升轨迹、载荷参数、时间同步验证、急停和人工监护任一项缺失时，不得夹取方框或执行载荷抬升，只允许模拟、规划可视化或经用户明确授权的空夹具无载荷验证。

1. **Ubuntu 20.04**：维持当前模拟、只读和 `guarded_real` 的执行禁用状态，完成状态机和 `ABORT` 测试。
2. **Ubuntu 22.04**：最小 ROS2 `HEALTH` TCP 客户端与 ROS1 `read_only` 来源 IP 白名单监听已实现；先在宿主机到虚拟机的专用网络完成无控制命令的 `HEALTH`、认证、心跳、重连、重复请求和断网验收，再在实体机部署前单独确认业务网与 `chrony` 时间状态。不得以虚拟机结果替代实体机网络或时间同步验收。
3. 两端分别完成 ArUco 字典/ID/角点安装位姿、相机外参和 `box -> grasp` 标定；先在 MoveIt 规划可视化中验证预抓取与抓取接近目标，再经用户明确授权，在急停与人工监护下以空夹具、低速、短距离验证到位，不闭合夹爪。
4. 补齐可靠夹持反馈、已验证抬升轨迹、载荷参数、误差/力矩阈值、急停与人工监护后，验证两臂同步启动、保持和中止。
5. 以轻质假件验证夹爪与视觉互锁；填入真实载荷参数后再逐步测试真实方框。

移动底盘协同不属于本方案。固定工位稳定后如需实施，必须持续估计两底盘和两夹爪的相对位姿；六维力控只能补偿小误差，不能替代底盘定位或编队控制。
