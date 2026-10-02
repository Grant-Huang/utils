# @antv/mcp-server-chart：27 个图表工具。
# ⚠ 默认会把图表数据发到蚂蚁的公网渲染服务并返回公网图片 URL（已实测）。必须显式设置 VIS_REQUEST_SERVER：
#   指向你自己部署的渲染服务（保证数据不出内网），或明确填公网地址表示接受。compose 里该变量是必填。
FROM node:22-slim
RUN npm install -g --omit=dev @antv/mcp-server-chart@0.9.10
USER node
EXPOSE 1122
# 入口校验：没设置 VIS_REQUEST_SERVER 就拒绝启动，避免"不知不觉把数据发到公网服务"
CMD ["sh", "-c", "[ -n \"$VIS_REQUEST_SERVER\" ] || { echo 'refusing to start: set VIS_REQUEST_SERVER (private renderer URL, or the public service if you knowingly accept data leaving)' >&2; exit 1; }; exec mcp-server-chart --transport streamable --host 0.0.0.0 --port 1122"]
