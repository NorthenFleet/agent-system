# OpenClaw 团队信息看板

🤖 基于 Vue 3 + FastAPI 的智能体团队信息看板

## 功能特性

- 📊 **仪表盘** - 团队统计概览
- 📋 **任务看板** - 任务管理和进度跟踪
- 👥 **智能体团队** - 汽车人和忍者神龟团队展示
- 🖥️ **设备清单** - 集群设备状态监控
- 🟣 **团队架构** - 震荡波团队优化中心

## 技术栈

### 前端
- Vue 3 (Composition API)
- Element Plus UI
- Font Awesome 图标
- ECharts 图表

### 后端
- FastAPI
- Python 3.14+
- Uvicorn

## 快速开始

### 1. 安装依赖

```bash
# 后端依赖
cd backend
pip3 install -r requirements.txt

# 前端依赖（可选，使用 CDN）
cd frontend
npm install
```

### 2. 启动服务

```bash
# 方式 1: 使用启动脚本
./start.sh

# 方式 2: 手动启动
cd backend
python3 main.py
```

### 3. 访问看板

打开浏览器访问：http://localhost:3020/

## 项目结构

```
team-dashboard/
├── backend/           # 后端 API
│   ├── main.py       # FastAPI 应用入口
│   ├── data_manager.py
│   ├── device_manager.py
│   └── task_queue.py
├── frontend/         # 前端页面
│   ├── complete-full.html  # 主页面
│   ├── css/          # 样式文件
│   └── js/           # JavaScript 模块
├── data/             # 数据文件
├── docs/             # 文档
└── start.sh          # 启动脚本
```

## API 接口

| 接口 | 说明 |
|------|------|
| GET /api/agents | 获取智能体列表 |
| GET /api/devices | 获取设备列表 |
| GET /api/tasks | 获取任务列表 |
| GET /api/email/stats | 获取邮件统计 |

## 开发说明

### 添加新视图

1. 在 `frontend/complete-full.html` 中添加视图模板
2. 在 Vue 应用的 `data` 中添加路由
3. 在侧边栏添加导航项

### 添加新 API

1. 在 `backend/main.py` 中添加路由
2. 实现数据处理逻辑
3. 测试 API 接口

## 配置

### 环境变量

在 `backend/` 目录下创建 `.env` 文件：

```bash
API_PORT=3020
DEBUG=false
```

## 贡献

欢迎提交 Issue 和 Pull Request！

## 许可证

MIT License

---

*最后更新：2026-04-04*
