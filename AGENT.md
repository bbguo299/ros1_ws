# 双臂协同搬运项目上下文

## 项目定位

本目录是双臂协同搬运项目的 Git 协作根目录。`ros1_ws` 是 **Ubuntu 20.04 / ROS1 Noetic RM65-B 执行工作空间**，`ros2_ws` 是 **Ubuntu 22.04 / ROS2 Humble ECO65 协调工作空间**；两者分别构建，绝不互相 overlay。
当前工作重点是以只读方式验证 RM65 网关与 ROS2 协调器之间的双机通信；ROS2 不直接操作 RM65 的 ROS1 话题或 Action。

完整方案见 [DUAL_ARM_LIFT_PLAN.md](docs/DUAL_ARM_LIFT_PLAN.md)，实施历史见
[PROJECT_LOG.md](docs/PROJECT_LOG.md)，现场只读验收步骤见
[docs/RM65_READ_ONLY_GATEWAY_VALIDATION_ZH.md](docs/RM65_READ_ONLY_GATEWAY_VALIDATION_ZH.md)。

## 部署边界

| 位置 | 系统与职责 |
|---|---|
| `ros1_ws` 及 `/home/fkq/rm_ws`、`/home/fkq/cam_ws`、`/home/fkq/rm_grasp_ws` | Ubuntu 20.04 / ROS1：RM65 驱动、Gemini 相机、既有视觉抓取、RM65 网关。 |
| `ros2_ws`、`/home/fkq/ros2_rm_ws`、`/home/fkq/Orbbec_ws` | Ubuntu 22.04 / ROS2：ECO65 驱动、六维力控、相机与双臂协调器。 |

不要在 `ros1_ws` catkin 工作空间混入 ROS2 包；不要在 `ros2_ws` 直接发布 RM65 的 ROS1 轨迹、夹爪或高频控制命令。

## 目录职责

- `ros1_ws/`：仅由 Ubuntu 20.04 使用 `catkin_make` 构建。
- `ros2_ws/`：仅由 Ubuntu 22.04 使用 `colcon build` 构建。
- `shared/`：两端共同维护的协议说明、无凭据配置模板和测试向量；不得存放真实 IP、token 或硬件密钥。
- `docs/`：跨机方案、验收手册和实施记录。

## 当前实现状态

`ros1_ws/src/rm65_lift_gateway` 已实现三种模式：

- `simulation`：回环 TCP 的模拟状态机与协议测试。
- `read_only`：连接已由操作员启动的 ROS1 节点，仅观测 RM65、Action server 和 Gemini 数据流。
- `guarded_real`：校验未来轨迹档案并复用只读健康状态；固定禁用执行，所有执行命令返回 `REAL_EXECUTION_DISABLED`。

**已完成现场基线**：Ubuntu 20.04 上的 `read_only` 验收已通过。RM65 六轴关节状态、`/rm_65/follow_joint_trajectory` Action server 与 `/camera` 的四路相机/标定数据均为健康状态；网关保持 `READ_ONLY`，不具备运动或夹爪权限。具体数值和证据见项目记录的“RM65 只读网关现场验收通过”条目。

**已完成 ROS2 最小客户端**：`ros2_ws/src/dual_arm_lift_coordinator` 提供 `rm65_health_client` 节点和仅含 `HEALTH` 的 TCP 客户端。节点周期发布 `rm65/health`、`rm65/connection_status`、`rm65/recent_success_time` 和 `rm65/recent_error`，每次轮询使用短连接，因此可在下一个周期自动重连。测试已接入 `colcon test` 并通过 5 项本地回环测试。该包没有执行类命令构造或调用接口；它只是双机只读联调的基础，不是完整的双臂任务协调器。

**虚拟机只读联调支持已实现**：ROS1 网关新增仅适用于 `read_only` 模式的来源 IP 白名单远程监听。当前 VMware 验收固定为宿主机 `172.16.108.1` 访问虚拟机 `172.16.108.128:28400`；远程启动必须使用未跟踪的随机 token 配置，示例 token 会被拒绝。UFW 当前不活动，本阶段不启用；完整步骤见 [ROS2_ROS1_VM_HEALTH_VALIDATION_ZH.md](docs/ROS2_ROS1_VM_HEALTH_VALIDATION_ZH.md)。

只读网关现已提供默认 `600 s` 的 `health.observability` 滚动基线：关节/相机消息频率和间隔、Action server 可用性变化及驱动错误码非零记录均只读输出，不写入磁盘且不改变健康阈值。现场连续 10 分钟观测已通过：关节约 `49.02 Hz`、四路相机各约 `29.96 Hz`，Action server 无可用性变化，错误码无非零记录；步骤、判据与限制见只读验证手册。

RM65 驱动源码已确认仅在解析到含 `arm_err`、`sys_err` 的 UDP 状态包时发布错误码话题。现场已确认 `/rm_driver` 发布两个 `std_msgs/UInt16` 话题、网关订阅它们，且正常状态下各观察 60 秒均静默；不得为此制造硬件故障。非零错误的真实上报行为仍未经验证。

只读模式的硬性限制：

- 固定 `real_hardware_enabled: false`；
- 固定绑定 `127.0.0.1`；
- 不启动 RM 驱动、MoveIt、`rm_control` 或相机；
- 不发布 ROS 控制话题，不发送 Action goal；
- TCP 仅允许 `HEALTH`，其余任务命令返回 `READ_ONLY_MODE`。

`guarded_real` 同样固定 `real_hardware_enabled: false` 与 `execution_enabled: false`，且默认没有任何已验证档案和可靠夹持反馈；它不发送 ROS 控制消息或 Action goal，不能因修改 YAML 参数而发送真实命令。

当前现场相机使用 Orbbec 默认命名空间 `/camera`，不是 `/rm65_cam`。如改变 `camera_name`，必须同步修改 `ros1_ws/src/rm65_lift_gateway/config/read_only.yaml`、视觉配置和验证文档。

## 关键接口

- RM65 关节状态：`/joint_states`。
- RM65 标准轨迹 Action：`/rm_65/follow_joint_trajectory`；现有驱动不会按轨迹 `header.stamp` 延迟启动，真实同步应由 RM65 本机网关等待绝对时刻后再发 goal。
- RM65 驱动错误码：`/rm_driver/ArmError`、`/rm_driver/SysError`。
- RM65 夹爪：`/rm_driver/Gripper_Set`，但闭合命令不等于夹持成功，真实举升前必须有可靠夹持反馈。
- 当前 Gemini 数据流：`/camera/color/*`、`/camera/depth/*`。
- 旧视觉工程观察位服务：`/rm65_visual_grasp/move_to_observation`；旧名称已废弃。

## 操作约束

- 未经用户明确授权，不启动、停止、重启真实硬件节点，不发送轨迹、夹爪、急停、IO、示教或力控命令。
- 修改真实硬件逻辑前，先阅读驱动实现、现有配置与上述方案文档；优先增加独立配置和测试，不改动 `/home/fkq/rm_ws`、`cam_ws`、`rm_grasp_ws` 的驱动源码。
- 真实模式必须保持“本机执行、跨机仅任务级通信”。网络中断、认证失败、状态过期和同步异常均应拒绝执行。
- 每次完成任务后，必须同步更新 `PROJECT_LOG.md` 与所有受变更影响的说明文档、操作手册和项目上下文；`DUAL_ARM_LIFT_PLAN.md` 仅在方案本身变化时更新，不写实施完成日志。

## 后续路线

1. 按虚拟机只读联调手册完成 10 分钟 `HEALTH`、认证失败、断网重连和来源白名单现场验收；UFW 保持不活动。
2. 实体机部署前，单独确认同一业务网、固定地址、既有防火墙规则和 RM65 专用网口边界，不能直接修改 `ens37` 或启用 UFW。
3. 以方框角上的 ArUco 为输入，完成相机外参、`aruco -> box` 和两端 `box -> grasp` 变换；在各自本机 MoveIt 中先验证预抓取与抓取接近的规划和无夹持到位。抬升阶段仍使用经示教和离线验证的本机轨迹，不使用在线规划生成载荷轨迹。
4. 在可靠夹持反馈、已验证抬升轨迹、轨迹末端误差确认、载荷参数、现场急停与用户明确授权齐备后，设计真实 ROS 控制适配器和本机安全中止，并按空夹具、轻质假件、真实方框的顺序进行双臂测试。

任何真实举升均依赖：急停与人工监护、夹持成功反馈、相机/ArUco 标定、已验证轨迹、载荷参数、时间同步与 ECO65 力控参数全部就绪。
