# 共享接口目录

`shared/` 用于两端共同维护跨机 TCP 协议说明、无凭据配置模板、ArUco/方框参数模板和测试向量。当前 JSON 请求与响应的实现依据是 `ros1_ws/src/rm65_lift_gateway/src/rm65_lift_gateway/protocol.py`，ROS2 客户端必须与其兼容。

不得在此目录提交真实 IP 地址、认证 token、密码、相机序列号或硬件密钥。协议改动必须同步更新 `docs/`、两端实现和兼容性测试。

ok