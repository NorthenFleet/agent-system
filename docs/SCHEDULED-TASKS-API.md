# 定时任务 API 接口文档

**版本**: 1.0  
**创建**: 2026-04-07  
**管理者**: 🟣 震荡波 (团队优化师)

---

## 📋 概述

本 API 提供定时任务状态查询接口，供前端看板展示定时任务执行情况。

**所有定时任务由震荡波统一管理**。

---

## 🔌 API 接口

### GET /api/scheduled-tasks

获取所有定时任务的状态信息。

**请求**:
```http
GET /api/scheduled-tasks
Content-Type: application/json
```

**响应**:
```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: max-age=60
```

**响应数据**:
```json
{
  "managed_by": "震荡波",
  "last_updated": "2026-04-07T16:15:00+08:00",
  "total_tasks": 5,
  "active_tasks": 5,
  "tasks": [
    {
      "id": "SCHED-001",
      "name": "团队工作看板汇报",
      "owner": "擎天柱",
      "schedule": "每 3 小时",
      "time_slot": "09:00/12:00/15:00/18:00/21:00",
      "status": "active",
      "priority": "medium",
      "last_run": "2026-04-07T15:10:00+08:00",
      "next_run": "2026-04-07T18:10:00+08:00",
      "success_rate": 100,
      "avg_duration_seconds": 120,
      "execution_count": 15
    }
    // ... 更多任务
  ]
}
```

---

## 📊 数据模型

### ScheduledTask 对象

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| id | string | ✅ | 任务 ID (格式：SCHED-XXX) |
| name | string | ✅ | 任务名称 |
| owner | string | ✅ | 负责人 (智能体名称) |
| schedule | string | ✅ | 执行频率 (如"每 30 分钟") |
| time_slot | string | ✅ | 执行时间片 (如":00/:30") |
| status | string | ✅ | 状态 (active/inactive/suspended) |
| priority | string | ✅ | 优先级 (high/medium/low) |
| last_run | string | ✅ | 上次执行时间 (ISO 8601) |
| next_run | string | ✅ | 下次执行时间 (ISO 8601) |
| success_rate | number | ✅ | 成功率 (0-100) |
| avg_duration_seconds | number | ✅ | 平均执行时长 (秒) |
| execution_count | number | ✅ | 执行次数 |

### 响应对象

| 字段 | 类型 | 说明 |
|------|------|------|
| managed_by | string | 管理者 (固定为"震荡波") |
| last_updated | string | 最后更新时间 (ISO 8601) |
| total_tasks | number | 总任务数 |
| active_tasks | number | 活跃任务数 |
| tasks | array | 任务列表 (ScheduledTask[]) |

---

## 💻 后端实现示例

### Python Flask

```python
from flask import Flask, jsonify
import json
from datetime import datetime
from pathlib import Path

app = Flask(__name__)

@app.route('/api/scheduled-tasks', methods=['GET'])
def get_scheduled_tasks():
    """获取所有定时任务状态"""
    data_file = Path('~/WorkSpace/team-dashboard/data/scheduled-tasks.json').expanduser()
    
    try:
        with open(data_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 更新最后访问时间
        data['last_updated'] = datetime.now().astimezone().isoformat()
        
        response = jsonify(data)
        response.headers['Cache-Control'] = 'max-age=60'  # 缓存 1 分钟
        return response
    
    except FileNotFoundError:
        return jsonify({
            "error": "数据文件不存在",
            "managed_by": "震荡波"
        }), 404
    except Exception as e:
        return jsonify({
            "error": str(e),
            "managed_by": "震荡波"
        }), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3010)
```

---

## 🎨 前端使用示例

### React

```jsx
import React, { useState, useEffect } from 'react';

function ScheduledTasksList() {
    const [tasks, setTasks] = useState([]);
    const [managedBy, setManagedBy] = useState('');
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        fetch('/api/scheduled-tasks')
            .then(response => response.json())
            .then(data => {
                setTasks(data.tasks);
                setManagedBy(data.managed_by);
                setLoading(false);
            })
            .catch(error => {
                console.error('获取定时任务失败:', error);
                setLoading(false);
            });
    }, []);

    if (loading) {
        return <div>加载中...</div>;
    }

    return (
        <div className="scheduled-tasks">
            <h3>定时任务 (管理者：{managedBy})</h3>
            <table>
                <thead>
                    <tr>
                        <th>任务名称</th>
                        <th>负责人</th>
                        <th>频率</th>
                        <th>下次执行</th>
                        <th>成功率</th>
                    </tr>
                </thead>
                <tbody>
                    {tasks.map(task => (
                        <tr key={task.id}>
                            <td>{task.name}</td>
                            <td>{task.owner}</td>
                            <td>{task.schedule}</td>
                            <td>{new Date(task.next_run).toLocaleString()}</td>
                            <td>{task.success_rate}%</td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}

export default ScheduledTasksList;
```

---

## 📝 更新日志

### v1.0 (2026-04-07)

- ✅ 创建 API 接口文档
- ✅ 提供 Python Flask 实现示例
- ✅ 提供 React 前端使用示例

---

## 📞 联系方式

**API 负责人**: 🟣 震荡波 (团队优化师)

**文档位置**: `~/WorkSpace/team-dashboard/docs/SCHEDULED-TASKS-API.md`

**数据文件**: `~/WorkSpace/team-dashboard/data/scheduled-tasks.json`

---

*最后更新：2026-04-07 16:15*
