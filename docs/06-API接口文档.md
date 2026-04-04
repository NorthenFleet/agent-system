# 📡 API 接口文档

**版本**: 1.0  
**更新**: 2026-03-18

---

## 🌐 基本信息

**基础地址**: `http://192.168.31.41:3020`

---

## 📡 RESTful API

### 1. API 根路径
```http
GET /
```
响应：`{"message": "团队状态看板 API", "version": "1.0"}`

### 2. 智能体列表
```http
GET /api/agents
```
响应：4 个智能体数据

### 3. 任务列表
```http
GET /api/tasks
```
响应：任务列表

### 4. 团队状态
```http
GET /api/team/status
```
响应：团队统计信息

---

## 🔌 WebSocket

```
ws://192.168.31.41:3020/ws/status
```

---

## 🧪 测试示例

```bash
curl http://192.168.31.41:3020/api/agents
```

---

*创建：2026-03-18*
