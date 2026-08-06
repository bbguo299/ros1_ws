# 项目记录

本文件记录已完成的实现、接口核对、验证结果和限制；
`DUAL_ARM_LIFT_PLAN.md` 仅保留方案与部署设计。

## 2026-08-06：ROS2 宿主机到 ROS1 虚拟机只读联调支持

- **完成内容**：为 ROS2 `rm65_health_client` 补齐 `colcon test` 测试发现、参数模板安装和 launch 入口；将默认端口统一为 `28400`。ROS1 网关新增仅允许 `read_only` 模式使用的来源 IP 白名单监听，新增显式私有覆盖配置与启动文件，并拒绝远程使用示例 token、空白来源白名单、通配或回环绑定地址。
- **修改文件或模块**：ROS2 的 `setup.py`、`package.xml`、`node.py`、参数模板和 launch；ROS1 的 `protocol.py`、`node.py`、只读配置、协议测试、白名单配置模板与 launch；新增 `docs/ROS2_ROS1_VM_HEALTH_VALIDATION_ZH.md`，并更新项目上下文与总体方案。
- **原因与效果**：当前 ROS2 宿主机 `172.16.108.1` 与 ROS1 虚拟机 `172.16.108.128` 通过 VMware 专用网段连接。网关可仅监听虚拟机地址并仅接受宿主机来源，而默认只读启动继续保持 `127.0.0.1`。ROS2 仍只构造 `HEALTH`，远程网关仍永久禁止执行命令，因此该联调不会控制 RM65、夹爪或其他硬件。
- **风险、限制与待办**：虚拟机 UFW 当前不活动，本次未启用或修改防火墙；应用层白名单不是实体机防火墙验收的替代。尚未启动虚拟机网关或 ROS2 节点，未验证 10 分钟现场连通性、真实 token、认证失败、断网重连或 VMware 地址变化。实体机部署必须单独确认同一业务网、固定地址、既有规则和 `chrony`，不得修改 RM65 专用 `ens37`。
- **验证**：ROS1 `protocol.py`、`node.py` 和协议测试的 Python 编译、两份 YAML 与两份 launch XML 解析通过；受管沙箱缺少 ROS1 Noetic `actionlib`，无法在当前 Ubuntu 22.04 主机运行 `test_read_only.py`。在允许本地回环 Socket 的环境运行 `python3 test/test_protocol.py`，5 项通过。ROS2 `colcon build --packages-select dual_arm_lift_coordinator` 成功；`colcon test --packages-select dual_arm_lift_coordinator` 发现并通过 5 项测试。未启动网络服务或任何真实硬件。

## 2026-08-06：ROS2 最小只读 HEALTH 客户端完成

- **完成内容**：在 `ros2_ws/src/dual_arm_lift_coordinator` 新增 ROS2 Humble `ament_python` 包。`rm65_health_client` 周期性向 RM65 网关发出唯一的 `HEALTH` TCP 请求，并发布完整健康 JSON、连接状态、最近成功时间和最近错误；客户端使用每次请求独立的短连接，下一周期可自动重连。
- **修改文件或模块**：`dual_arm_lift_coordinator/client.py`、`node.py`、`setup.py`、`setup.cfg`、`package.xml`、`params/local.example.yaml` 及 `test/test_client.py`。
- **原因与效果**：将 ROS2 主控端与 ROS1 网关保持在任务级 TCP 边界内，先验证双机观测链路，不让 ROS2 直接访问 RM65 ROS1 控制接口。客户端仅构造 `HEALTH`，没有 `PREPARE`、`GRIP`、`ARM_LIFT`、`HOLD` 或 `ABORT` 的调用 API，因此不会触发 RM65 运动或夹爪。
- **风险、限制与待办**：当前默认参数仍是回环地址、示例 token 和端口，尚未在两台主机之间构建或联调；未验证真实认证、心跳、断网重连、重复请求和 `chrony` 偏差。该节点不是完整协调器，尚未接入 ECO65 状态、视觉、夹持反馈、力控或任务状态机；这些内容必须在双机只读验收和相关安全条件完成后分阶段实施。
- **验证**：在当前 Ubuntu 22.04 / ROS2 Humble 环境运行 `source /opt/ros/humble/setup.bash && colcon build --packages-select dual_arm_lift_coordinator` 成功。随后 `colcon test --packages-select dual_arm_lift_coordinator` 与 `colcon test-result --verbose` 成功退出但报告 `0 tests`，表明 `test/test_client.py` 尚未接入标准测试发现流程，不能视为单元测试已通过；后续需先补齐测试注册。未启动网络服务或任何真实硬件。

## 2026-08-06：ROS1/ROS2 单仓库协作结构

- **完成内容**：将 Git 协作根目录调整为包含 `ros1_ws`、`ros2_ws`、`shared` 和 `docs` 的单仓库结构；原 RM65 网关源码移动到 `ros1_ws/src`，并保留已发布提交的 Git 历史。新增 ROS2 与共享目录的职责说明。
- **修改文件**：根目录 `.gitignore`、`AGENT.md`、`docs/PROJECT_LOG.md`，新增 `ros2_ws/README.md`、`shared/README.md`；`src/` 在普通迁移提交中重命名为 `ros1_ws/src/`。
- **原因与效果**：Ubuntu 20.04 与 Ubuntu 22.04 可克隆同一仓库、共享协议和文档，但分别在各自工作空间构建，避免手工复制源码或混用 ROS1/ROS2 依赖。
- **风险、限制与待办**：本次仅调整源码管理和文档，不创建 ROS2 节点、不改变网关监听地址，也不执行硬件操作。已发布提交不被改写；原工作区和迁移过程中的 Git 元数据均保留为不受 Git 跟踪的本地备份，确认稳定前不得删除。
- **验证**：临时克隆和新根目录的 `git fsck --no-dangling`、`git diff --check`、追踪文件与忽略规则检查均通过；新旧 `src/`（排除已忽略的 Python 缓存）一致。直接运行状态机、协议分发、只读和 guarded-real 测试共 24 项通过；在新路径执行 `catkin_make` 成功。未运行 ROS 节点或硬件命令。

## 2026-08-06：双机通信与 ArUco-MoveIt 验证路线调整

- **完成内容**：将后续工作调整为先验证 Ubuntu 20.04 与 Ubuntu 22.04 之间的只读 TCP 通信，再开展方框角 ArUco 到本机 MoveIt 预抓取/抓取接近目标的转换和验证；真实夹取与同步抬升仍位于最后阶段。
- **修改文件**：`AGENT.md`、`docs/DUAL_ARM_LIFT_PLAN.md` 和本记录。
- **原因与效果**：当前 RM65 网关仅完成回环 TCP 验证，尚未验收双机连通性。新路线先在执行永久禁用的前提下验证指定局域网 IP、认证、心跳、重连、断网和 `chrony` 时间状态，随后利用 `base -> camera -> aruco -> box -> grasp` 生成两端的 MoveIt 目标。`world` 用于跨机几何一致性，单机规划也必须共享 `box` 坐标系。
- **风险、限制与待办**：当前网关仍仅绑定 `127.0.0.1`，未授权前不得开放局域网监听；尚未创建 ROS2 客户端、修改网络配置、执行 MoveIt 运动或闭合夹爪。在线 MoveIt 仅用于预抓取和抓取接近，不能取代已验证的载荷抬升轨迹；可靠夹持反馈、载荷参数、急停与人工监护仍是实际举升的必要条件。
- **验证**：静态核对 `AGENT.md` 与总体方案的路线、坐标链、任务分工和安全顺序一致；未运行构建、网络连接、ROS 节点或硬件控制命令。

## 2026-08-06：RM65 默认关闭执行适配器骨架

- **完成内容**：新增 `guarded_real` 模式、默认关闭配置和启动文件，以及未来预抓取/抬升关节轨迹的纯 Python 档案校验。该模式复用只读健康数据，`HEALTH` 增加执行阻断原因，所有执行命令固定返回 `REAL_EXECUTION_DISABLED`。
- **修改文件**：`src/rm65_lift_gateway/src/rm65_lift_gateway/guarded_real.py`、`node.py`、`__init__.py`、`config/guarded_real.yaml`、`launch/guarded_real_gateway.launch`、`test/test_guarded_real.py`、`package.xml`、`AGENT.md`、`DUAL_ARM_LIFT_PLAN.md`、`docs/RM65_READ_ONLY_GATEWAY_VALIDATION_ZH.md` 和本记录。
- **原因与效果**：为未来真实执行预先固定档案格式、禁用状态与接口响应，避免在可靠夹持反馈和已验证轨迹缺失时误接入 ROS 控制。骨架不依赖 `rm_msgs`，不发送 ROS 控制消息或 Action goal，且节点继续拒绝 `real_hardware_enabled=true` 或 `execution_enabled=true`。
- **风险、限制与待办**：默认档案为空，`GRIP_FEEDBACK_UNAVAILABLE`、`NO_VALIDATED_PROFILES` 和 `REAL_EXECUTION_DISABLED` 始终阻断执行；未实现轨迹发送、夹爪闭合、完成误差确认或本机停止。后续真实适配器必须在夹持反馈、轨迹、急停、人工监护和用户明确授权全部具备后另行设计。
- **验证**：直接运行状态机、协议、只读和 guarded-real 测试共 24 项通过；`catkin_make` 成功；Python 编译、YAML/launch 解析、控制 API 静态检索和 `git diff --check` 通过。`catkin_make run_tests` 执行 27 项，其中 3 项既有回环 TCP 集成测试仍因受管沙箱禁止创建本地 socket（`PermissionError: [Errno 1] Operation not permitted`）失败，需在正常 Ubuntu 20.04 终端复验；未启动或控制真实硬件。

## 2026-08-06：RM65 错误码话题只读发布行为核对

- **完成内容**：静态核对 RM65 驱动的错误码发布条件，并将现场验证改为有时限的只读订阅，避免 `rostopic echo -n 1` 在正常静默时无限等待。
- **修改文件**：`AGENT.md`、`docs/RM65_READ_ONLY_GATEWAY_VALIDATION_ZH.md` 和本记录。
- **原因与效果**：驱动在解析到包含 `arm_err`、`sys_err` 的 UDP 状态包时，向 `/rm_driver/ArmError`、`/rm_driver/SysError` 发布 `std_msgs/UInt16`。新增步骤先检查发布者和类型，再分别最多等待 60 秒：收到 `0` 记录为正常零值发布，超时记录为现场静默，均不需要也不允许制造故障。
- **风险、限制与待办**：当前基线证明正常状态下两个话题静默，尚不能验证实时 UDP 配置在故障时是否会提供错误字段，或网关对非零值的现场响应时序；非零上报仍必须在厂商书面流程、现场监护和用户明确授权下验证。
- **验证**：静态核对 `/home/fkq/rm_ws/src/rm_65_robot/rm_driver/src/rm_robot.h` 中的解析与发布逻辑，以及 `rm_driver.cpp` 的两个话题声明。用户在实际 Ubuntu 20.04 ROS1 主机执行 `rostopic info`，确认两个话题均为 `std_msgs/UInt16`、发布者为 `/rm_driver`、订阅者为 `/rm65_lift_gateway`；两项 `timeout 60s rostopic echo -n 1` 均无输出且退出码为 `124`，确认当前正常状态下静默。此前受管环境无法连接 ROS master，未发送或安排任何控制命令。

## 2026-08-06：RM65 只读网关连续 10 分钟观测通过

- **完成内容**：在 Ubuntu 20.04 现场让只读网关连续运行 600 秒后读取 `health.observability`，完成关节、四路相机、轨迹 Action server 和驱动错误码的连续性基线验收。
- **涉及模块**：`rm65_lift_gateway` 的 `read_only` 模式、RM65 `/joint_states`、`/rm_65/follow_joint_trajectory` 与 `/camera` 彩色/深度图和 CameraInfo。
- **原因与效果**：确认此前新增的滚动观测统计能反映真实现场数据流。关节状态平均约 `49.02 Hz`、窗口内 `29412` 条、最长间隔约 `0.049 s`；四路相机各平均约 `29.96 Hz`、窗口内各 `17978` 条、最长间隔为约 `0.052..0.083 s`，均低于关节 `0.75 s` 和相机 `2.0 s` 的现有新鲜度阈值。Action server 保持可用且无可用性变化；两个错误码均无非零记录。
- **风险、限制与待办**：`ArmError` 和 `SysError` 在本窗口未收到消息，状态为 `seen=false`、`active=false`，因此只能确认没有报告活动故障，不能验证错误码话题在故障时的发布行为。验收仍为只读：`motion_permitted=false`、`gripper_permitted=false`，不表示允许真实抓取或举升。
- **验证**：用户执行 `date -u`、`sleep 600`、`rostopic echo -n 1 /rm65_lift_gateway/status` 并提供有效状态；`state=READ_ONLY`、`health.ready=true`。未发送轨迹、夹爪或其他控制命令。

## 2026-08-06：RM65 只读网关连续观测基线

- **完成内容**：为只读网关新增最近 600 秒的进程内观测统计。`health.observability` 现在包含关节状态和四路相机数据的消息数、平均频率、最近/最短/最长间隔及最后接收时间，并记录轨迹 Action server 可用性变化、`ArmError`/`SysError` 非零消息次数和最后一次非零时间。
- **修改文件**：`src/rm65_lift_gateway/src/rm65_lift_gateway/read_only.py`、`node.py`、`config/read_only.yaml`、`test/test_read_only.py`、`AGENT.md`、`docs/RM65_READ_ONLY_GATEWAY_VALIDATION_ZH.md` 和本记录。
- **原因与效果**：将已通过的一次性只读健康检查扩展为连续 10 分钟的观测基线，能发现短暂的数据流中断、Action server 断连和错误码变化；统计仅追加到现有状态 JSON，不改变 `ready` 阈值，不写入磁盘，也不增加机械臂、夹爪或相机控制能力。
- **风险、限制与待办**：频率只用于记录现场基线，尚未设置最低 Hz 门限；统计随网关进程重启清空。尚未在真实现场执行新的 10 分钟观测，仍不得进入真实执行适配器或发送控制命令。
- **验证**：`python3 test/test_state_machine.py`、`test_dispatcher.py` 和 `test_read_only.py` 共 17 项非 Socket 测试通过；`catkin_make` 成功；YAML 与 launch XML 解析通过；静态检索确认只读模块不含 `send_goal`、`rm_msgs` 或 ROS 发布器。`catkin_make run_tests` 共执行 20 项，其中 3 项既有回环 TCP 集成测试因受管沙箱禁止创建本地 socket（`PermissionError: [Errno 1] Operation not permitted`）失败，需在正常 Ubuntu 20.04 终端复验；未启动或控制真实硬件。

## 2026-08-06：ROS1 Catkin 工作区 Git 忽略规则

- **完成内容**：新增根目录 `.gitignore`，忽略 Catkin 构建与开发环境生成物。
- **修改文件**：`.gitignore`、本记录。
- **原因与效果**：`build/`、`devel/`、`.catkin_workspace`、Python 字节码、ROS 日志/rosbag、本地虚拟环境、环境变量文件及编辑器临时文件均为本机生成或敏感开发文件，不应提交；`src/` 源码、YAML 配置、launch、测试和 `docs/` 仍保持可追踪。
- **风险、限制与待办**：规则不会删除已有文件，也不会停止追踪未来已提交的同类文件；若后续需将 `.vscode/` 或具体 rosbag 作为共享资产入库，应通过例外规则明确放行。
- **验证**：`git check-ignore -v` 已确认 `.catkin_workspace`、`build/`、`devel/`、包内 `__pycache__/`、`.env`、`*.log`、`*.bag` 和 `.vscode/` 均命中预期规则；`git status --short` 显示源码、配置、测试和 `docs/` 未被误忽略。未运行构建或硬件命令。

## 2026-08-04：RM65-B ROS1 夹爪接口核对

- **完成内容**：确认 Ubuntu 20.04 / ROS1 Noetic 的 RM65-B 使用 `rm_msgs/Gripper_Set` 发布到 `/rm_driver/Gripper_Set`；`position=1..1000` 约对应 `0..70 mm` 开口。
- **涉及模块**：`/home/fkq/rm_ws/src` 的 `rm_driver` 与 `rm_msgs`。
- **原因与效果**：为 RM65 本地网关提供已知夹爪接口边界。
- **风险与待办**：该命令本身不提供可靠的夹持成功反馈，不能单独作为真实举升放行条件。
- **验证**：静态核对 `Gripper_Set.msg` 和驱动订阅实现；未启动硬件。

## 2026-08-04：ROS1/ROS2 接口与部署核对

- **完成内容**：核对 RM65 ROS1 驱动、Orbbec ROS1 相机驱动及既有视觉抓取工程；明确 `ros1_ws` 只作为 Ubuntu 20.04 的 RM65 本地执行网关工作空间。
- **涉及模块**：RM65 Action `/rm_65/follow_joint_trajectory`、`/joint_states`、`/rm_driver/Gripper_Set`、Orbbec `gemini_330_series.launch` 与 `rm65_visual_grasp`。
- **原因与效果**：修正旧观察服务名为 `/rm65_visual_grasp/move_to_observation`，并确认 RM65 Action 要求每个路点包含 6 轴位置、速度、加速度且不读取 `trajectory.header.stamp`。同步开始需由 ROS1 网关本机等待绝对时刻后再发送 goal。
- **风险与待办**：尚未检查真实硬件在线话题、ECO65 夹爪反馈、两机 `chrony` 偏差和真实力控参数。
- **验证**：静态检索源代码和启动文件；未启动节点或连接硬件。

## 2026-08-04：第一阶段模拟 ROS1 网关

- **完成内容**：新增 `src/rm65_lift_gateway` Python 3 catkin 包，实现仅绑定 `127.0.0.1` 的换行 JSON TCP 服务、认证、重复请求拒绝、模拟视觉/夹爪/机械臂适配器、任务状态机、`HOLD`/`ABORT` 和私有 ROS 服务 `~reset_fault`。
- **修改文件或模块**：新增 `protocol.py`、`state_machine.py`、`adapters.py`、ROS 节点脚本、模拟配置、启动文件和 Python 测试；初始化 catkin 工作空间入口并生成 `build/`、`devel/` 构建产物。
- **原因与效果**：先把跨机任务协议与硬件适配隔离。模拟网关强制 `real_hardware_enabled=false` 且拒绝非回环地址，不会发送 RM65 Action、夹爪命令或相机调用。
- **风险与待办**：`simulation.yaml` 中 token 仅用于本地模拟；真实 Action、ArUco、夹持反馈、时间同步和力控未接入。
- **验证**：`catkin_make` 成功；CTest 注册 1 个 nosetests 目标；6 个状态机测试、2 个协议分发测试、Python 编译、YAML/launch XML 解析和真实接口静态检索通过。随后在 Ubuntu 20.04 正常终端运行 `catkin_make run_tests`，11 个 nosetests 全部通过（其中包含 3 个本机 Socket 集成测试），验证了回环 TCP 的 JSON 分帧、认证/重复请求拒绝、计划时刻前不启动、完成、过期时刻拒绝和 `ABORT`。此前仅是 Codex 受管沙箱禁止创建回环 socket，非代码故障。

## 2026-08-04：文档职责与操作系统边界整理

- **完成内容**：将完成记录迁移至本文件，重写协同方案文档为纯方案；明确 Ubuntu 20.04 / ROS1 与 Ubuntu 22.04 / ROS2 的职责、工作空间、接口归属及验证顺序。
- **修改文件**：`DUAL_ARM_LIFT_PLAN.md`、`PROJECT_LOG.md`。
- **原因与效果**：避免将实施历史混入方案，也避免“本机/远端”措辞导致 ROS1 与 ROS2 部署错误。
- **风险与待办**：Ubuntu 22.04 的 `ros2_ws` 协调器尚未创建；共享配置目录和真实双机网络参数仍待现场确定。
- **验证**：在 Ubuntu 20.04.6 当前主机上静态核对已有路径与 ROS1 Noetic 工具；未连接硬件。

## 2026-08-06：RM65 单机只读健康接入

- **完成内容**：为 `rm65_lift_gateway` 新增 `read_only` 模式。该模式只订阅 `/joint_states`、`/rm_driver/ArmError`、`/rm_driver/SysError`、`rm65_cam` 的彩色/深度图及 CameraInfo，并只探测 `/rm_65/follow_joint_trajectory` Action server 是否可用。
- **修改文件或模块**：新增 `read_only.py`、`config/read_only.yaml`、`launch/read_only_gateway.launch` 和 `test_read_only.py`；更新网关节点的模式选择、TCP 分发器和 catkin 依赖声明。
- **原因与效果**：在不发送机械臂、夹爪或相机控制命令的前提下，验证真实 RM65 与 Gemini 驱动状态。只读模式强制 `real_hardware_enabled=false`、仅绑定 `127.0.0.1`，并使 `PREPARE`、`GRIP`、`ARM_LIFT`、`HOLD`、`ABORT` 全部返回 `READ_ONLY_MODE`；`HEALTH` 和状态话题报告六关节完整性、数据新鲜度、Action 可用性及驱动错误码。
- **风险、限制与待办**：只读模式不会启动 `rm_driver`、`rm_control` 或 Orbbec，操作员必须先独立启动它们；也不会代替真实急停或停止已由其他节点发起的机械臂动作。尚未启动真实 RM65/相机，未验证现场话题名、帧率、Action server 和错误码频率。
- **验证**：6 个既有状态机测试、2 个既有协议分发测试和 6 个新增只读测试通过；`catkin_make` 成功；静态检索确认只读适配器不含 `send_goal`、夹爪消息、`rm_msgs` 或 ROS 发布器。未在当前受管沙箱运行完整 Socket 套件，需在正常 Ubuntu 终端运行 `catkin_make run_tests`；未连接或控制真实硬件。

## 2026-08-06：现场 ROS1 话题核对与相机配置修正

- **完成内容**：根据现场 `rostopic list` 核对 RM65 驱动、轨迹 Action 和 Gemini 相机话题；将只读网关相机配置由未启动的 `/rm65_cam/...` 修正为实际运行的 `/camera/...`。
- **修改文件**：`src/rm65_lift_gateway/config/read_only.yaml`、网关节点的相机默认话题、`DUAL_ARM_LIFT_PLAN.md` 和本记录。
- **原因与效果**：现场相机以 Orbbec 默认 `camera_name:=camera` 启动，彩色/深度图和 CameraInfo 位于 `/camera` 命名空间。修正后只读健康检查可读取实际数据，不会因命名空间不一致误报相机故障。
- **风险、限制与待办**：当前相机未按序列号和自定义命名空间启动；未来若改为 `rm65_cam` 或部署同一 ROS 图中的多相机，必须同步修改网关、视觉节点和启动命令。尚未读取实际帧率、错误码或启动只读网关。
- **验证**：用户提供的现场话题清单已确认 `/joint_states`、`/rm_65/follow_joint_trajectory`、`/rm_driver/ArmError`、`/rm_driver/SysError` 和 `/camera` 图像/标定话题存在；未发送控制命令。

## 2026-08-06：只读网关现场验证手册

- **完成内容**：新增终端级验证手册，覆盖 ROS master、RM65 驱动与 MoveIt、`rm_control` Action、Gemini 相机、只读网关、ROS 综合状态和本机 TCP 协议验证。
- **修改文件**：新增 `docs/RM65_READ_ONLY_GATEWAY_VALIDATION_ZH.md`，更新本记录。
- **原因与效果**：将启动顺序、实际 `/camera` 话题、无动作验证命令、JSON 成功判据和故障定位方式固化，避免现场人员误发控制命令或将单个话题存在误判为系统健康。
- **风险、限制与待办**：文档中的 `simulator-token` 仅用于当前回环只读配置；未开始真实抓取、夹爪或举升。相机改名、Action 名称或现场参数变更后必须同步修订手册与配置。
- **验证**：静态核对手册中的节点、话题、端口和阈值均与 `read_only.yaml`、网关实现及现场话题清单一致；未启动或控制硬件。

## 2026-08-06：项目上下文指引

- **完成内容**：新增项目根目录 `AGENT.md`，为后续工程对话汇总部署边界、当前模式、关键接口、安全约束和后续路线，并关联方案、日志和现场验证手册。
- **修改文件**：新增 `AGENT.md`，更新本记录。
- **原因与效果**：让新的协作会话先获得一致的 ROS1/ROS2 分工和真实硬件安全边界，减少重复阅读完整方案或误把 ROS2 职责放到当前 ROS1 工作空间。
- **风险、限制与待办**：该文件是上下文索引，不替代方案、实施记录和现场手册；接口或安全流程发生变化时必须同步更新索引与被链接文档。
- **验证**：静态核对链接目标、工作空间路径、当前网关模式、相机命名空间和后续路线均与现有项目文档及代码一致；未运行硬件或构建命令。

## 2026-08-06：RM65 只读网关现场验收通过

- **完成内容**：在已启动 RM65 驱动、`rm_control`、MoveIt 与 Gemini 相机的现场 ROS1 图中读取 `/rm65_lift_gateway/status`，完成单机只读健康验收。
- **涉及模块**：`rm65_lift_gateway` 的 `read_only` 模式、RM65 `/joint_states` 与 `/rm_65/follow_joint_trajectory`、`/camera` 彩色/深度图和 CameraInfo。
- **原因与效果**：确认网关可在不控制硬件的前提下同时观测真实 RM65 Action、六轴关节状态和实际相机数据流，为后续接入真实执行适配器提供已验证的观测基线。
- **现场结果**：`state=READ_ONLY`；`health.ready=true`；驱动与 Action server 均 `ready=true`；六轴关节无缺失且状态年龄约 `0.020 s`；四路相机数据年龄约 `0.067..0.074 s`；`motion_permitted=false`、`gripper_permitted=false`。错误码话题尚未收到消息，但 `active=false`，未报告活动故障。
- **风险、限制与待办**：本次仅验证只读健康，不表示允许真实运动；夹持成功反馈、ArUco 互锁、已验证轨迹、载荷参数、急停流程、Ubuntu 22.04/ECO65 端和时间同步仍未验收。
- **验证**：用户在 Ubuntu 20.04 ROS1 主机执行 `rostopic echo -n 1 /rm65_lift_gateway/status` 并提供上述有效状态；未发送轨迹、夹爪或其他控制命令。

## 2026-08-06：项目进度文档同步

- **完成内容**：将已完成的 RM65 单机只读现场验收同步到项目上下文指引和只读验证手册，并将后续路线推进到“固化观测基线”和“设计真实执行适配器”。
- **修改文件**：`AGENT.md`、`docs/RM65_READ_ONLY_GATEWAY_VALIDATION_ZH.md`、本记录。
- **原因与效果**：后续对话和现场人员可直接看到只读阶段已经通过，避免重复执行已完成的验收，同时保留真实执行尚未授权的安全边界。
- **风险、限制与待办**：本次只更新文档；真实 RM65 执行适配器、夹持反馈、ECO65/ROS2、时间同步和载荷验收仍未实施。
- **验证**：静态核对更新内容与现场网关状态和上一条验收记录一致；未运行或控制硬件。
