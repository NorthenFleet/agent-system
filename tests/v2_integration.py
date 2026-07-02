#!/usr/bin/env python3
"""
看板 V2 集成测试 + 回归测试
测试 Phase 2-5 全部功能

API 响应格式:
- 多数 POST/PUT/DELETE 返回 {"success": true, "task"/"comment"/"user": {...}}
- GET 列表/详情直接返回数据对象
"""
import requests
import json
import sys
import socket
import subprocess
from datetime import datetime

BASE_URL = "http://localhost:3020"
RESULTS = {"passed": [], "failed": [], "skipped": []}


def record(test_name, passed, detail=""):
    entry = {"name": test_name, "passed": passed, "detail": detail}
    if passed:
        RESULTS["passed"].append(entry)
        print(f"  ✅ PASS: {test_name}")
    else:
        RESULTS["failed"].append(entry)
        print(f"  ❌ FAIL: {test_name} — {detail}")


def api(method, path, headers=None, json_body=None):
    url = f"{BASE_URL}{path}"
    try:
        return requests.request(method, url, headers=headers, json=json_body, timeout=10)
    except Exception as e:
        return type("FakeResponse", (), {"status_code": 0, "text": str(e), "json": lambda: {}})()


# ============================================================
# 1. 认证 API
# ============================================================
def test_auth_no_token():
    r = api("GET", "/api/v2/tasks")
    record("无 Token 访问 /api/v2/tasks → 401", r.status_code == 401,
           f"期望 401，实际 {r.status_code}" if r.status_code != 401 else "")


def test_auth_invalid_token():
    r = api("GET", "/api/v2/tasks", headers={"Authorization": "Bearer invalid-token"})
    record("无效 Token → 401", r.status_code == 401,
           f"期望 401，实际 {r.status_code}" if r.status_code != 401 else "")


def test_auth_init_admin():
    r = api("POST", "/api/v2/auth/init-admin")
    record("POST /api/v2/auth/init-admin", r.status_code == 200,
           f"状态码 {r.status_code}" if r.status_code != 200 else "")


def test_auth_login():
    r = api("POST", "/api/v2/auth/login", json_body={
        "username": "admin", "password": "admin123"
    })
    ok = r.status_code == 200
    token = refresh = None
    if ok:
        body = r.json()
        token = body.get("access_token")
        refresh = body.get("refresh_token")
        if not token:
            ok = False
    record("POST /api/v2/auth/login", ok, f"状态码 {r.status_code}" if not ok else "")
    return token, refresh


def test_auth_me(token):
    h = {"Authorization": f"Bearer {token}"}
    r = api("GET", "/api/v2/auth/me", headers=h)
    ok = r.status_code == 200
    if ok:
        body = r.json()
        if body.get("username") != "admin":
            ok = False
    record("GET /api/v2/auth/me", ok, f"状态码 {r.status_code}" if not ok else "")


def test_auth_refresh(refresh_token):
    r = api("POST", "/api/v2/auth/refresh", json_body={"refresh_token": refresh_token})
    ok = r.status_code == 200
    if ok:
        body = r.json()
        if not body.get("access_token"):
            ok = False
    record("POST /api/v2/auth/refresh", ok, f"状态码 {r.status_code}" if not ok else "")


def test_auth_logout(token):
    h = {"Authorization": f"Bearer {token}"}
    r = api("POST", "/api/v2/auth/logout", headers=h)
    record("POST /api/v2/auth/logout", r.status_code == 200,
           f"状态码 {r.status_code}" if r.status_code != 200 else "")


# ============================================================
# 2. 任务 CRUD
# ============================================================
def test_tasks_list(token):
    h = {"Authorization": f"Bearer {token}"}
    r = api("GET", "/api/v2/tasks", headers=h)
    ok = r.status_code == 200
    if ok:
        body = r.json()
        if "tasks" not in body:
            ok = False
    record("GET /api/v2/tasks", ok, f"状态码 {r.status_code}" if not ok else "")


def _create_task(token, data):
    """Helper: 创建任务并返回 task_id 或 None"""
    h = {"Authorization": f"Bearer {token}"}
    r = api("POST", "/api/v2/tasks", headers=h, json_body=data)
    if r.status_code == 200:
        body = r.json()
        if body.get("success"):
            return body.get("task", {}).get("task_id")
    return None


def test_tasks_create(token):
    tid = _create_task(token, {
        "title": "集成测试任务-001",
        "description": "自动化测试创建",
        "type": "test",
        "priority": "high",
        "assignee": "michelangelo",
    })
    ok = tid is not None
    record("POST /api/v2/tasks — 创建任务", ok,
           f"task_id: {tid}" if ok else "创建失败")
    return tid


def test_tasks_get(token, task_id):
    if not task_id:
        record("GET /api/v2/tasks/{id}", False, "task_id 为空")
        return
    h = {"Authorization": f"Bearer {token}"}
    r = api("GET", f"/api/v2/tasks/{task_id}", headers=h)
    ok = r.status_code == 200
    if ok:
        body = r.json()
        if body.get("task_id") != task_id:
            ok = False
    record(f"GET /api/v2/tasks/{task_id}", ok,
           f"状态码 {r.status_code}" if not ok else "")


def test_tasks_update(token, task_id):
    if not task_id:
        record("PUT /api/v2/tasks/{id}", False, "task_id 为空")
        return
    h = {"Authorization": f"Bearer {token}"}
    r = api("PUT", f"/api/v2/tasks/{task_id}", headers=h, json_body={
        "status": "in_progress", "progress": 50
    })
    ok = r.status_code == 200
    if ok:
        body = r.json()
        if not body.get("success") or body.get("task", {}).get("progress") != 50:
            ok = False
    record(f"PUT /api/v2/tasks/{task_id} — 更新", ok,
           f"状态码 {r.status_code}" if not ok else "")


def test_tasks_done(token, task_id):
    if not task_id:
        record("PUT /api/v2/tasks/{id} — 完成", False, "task_id 为空")
        return
    h = {"Authorization": f"Bearer {token}"}
    r = api("PUT", f"/api/v2/tasks/{task_id}", headers=h, json_body={
        "status": "done"
    })
    ok = r.status_code == 200
    if ok:
        body = r.json()
        if not body.get("success"):
            ok = False
        else:
            task = body.get("task", {})
            if task.get("status") != "done":
                ok = False
            elif not task.get("completed_at"):
                ok = False
    record(f"PUT /api/v2/tasks/{task_id} — 完成", ok,
           f"状态码 {r.status_code}" if not ok else "")


def test_tasks_filter(token):
    h = {"Authorization": f"Bearer {token}"}
    r = api("GET", "/api/v2/tasks?status=done", headers=h)
    ok = r.status_code == 200
    if ok:
        for t in r.json().get("tasks", []):
            if t.get("status") != "done":
                ok = False
                break
    record("GET /api/v2/tasks?status=done — 过滤", ok,
           f"状态码 {r.status_code}" if not ok else "")

    r = api("GET", "/api/v2/tasks?page=1&page_size=5", headers=h)
    ok = r.status_code == 200
    if ok:
        body = r.json()
        if "page" not in body or "total_pages" not in body:
            ok = False
    record("GET /api/v2/tasks — 分页", ok,
           f"状态码 {r.status_code}" if not ok else "")


def test_tasks_delete(token):
    tid = _create_task(token, {"title": "待删除任务", "description": "测试删除"})
    if not tid:
        record("DELETE /api/v2/tasks/{id}", False, "创建前置任务失败")
        return
    h = {"Authorization": f"Bearer {token}"}
    r = api("DELETE", f"/api/v2/tasks/{tid}", headers=h)
    ok = r.status_code == 200
    if ok:
        r2 = api("GET", f"/api/v2/tasks/{tid}", headers=h)
        if r2.status_code != 404:
            ok = False
    record(f"DELETE /api/v2/tasks/{tid}", ok,
           f"状态码 {r.status_code}" if not ok else "")


def test_tasks_404(token):
    h = {"Authorization": f"Bearer {token}"}
    r = api("GET", "/api/v2/tasks/notexist-999", headers=h)
    record("GET /api/v2/tasks/notexist → 404", r.status_code == 404,
           f"期望 404，实际 {r.status_code}" if r.status_code != 404 else "")


# ============================================================
# 3. 评论 & 统计
# ============================================================
def test_task_comments(token, task_id):
    if not task_id:
        record("评论功能", False, "task_id 为空")
        return
    h = {"Authorization": f"Bearer {token}"}

    r = api("POST", f"/api/v2/tasks/{task_id}/comments", headers=h, json_body={
        "content": "自动化测试评论"
    })
    ok = r.status_code == 200 and r.json().get("success")
    record(f"POST /api/v2/tasks/{task_id}/comments", ok,
           f"状态码 {r.status_code}" if not ok else "")

    r = api("GET", f"/api/v2/tasks/{task_id}/comments", headers=h)
    ok = r.status_code == 200 and r.json().get("total", 0) >= 1
    record(f"GET /api/v2/tasks/{task_id}/comments", ok,
           f"状态码 {r.status_code}" if not ok else "")


def test_task_stats(token):
    h = {"Authorization": f"Bearer {token}"}
    r = api("GET", "/api/v2/tasks/stats", headers=h)
    ok = r.status_code == 200
    if ok:
        body = r.json()
        if "total" not in body or "by_status" not in body:
            ok = False
    record("GET /api/v2/tasks/stats", ok,
           f"状态码 {r.status_code}" if not ok else "")


# ============================================================
# 4. Agent 心跳 & 状态
# ============================================================
def test_agent_heartbeat(token):
    h = {"Authorization": f"Bearer {token}"}
    r = api("POST", "/api/v2/agents/michelangelo/heartbeat", headers=h, json_body={
        "agent_id": "michelangelo",
        "agent_name": "米开朗基罗",
        "status": "busy",
        "team": "ninja-turtles",
        "current_task": "v2-integration-test",
        "cpu_usage": 45.5,
        "memory_usage": 62.3,
    })
    ok = r.status_code == 200 and r.json().get("success")
    record("POST /api/v2/agents/michelangelo/heartbeat", ok,
           f"状态码 {r.status_code}" if not ok else "")


def test_agent_live(token):
    h = {"Authorization": f"Bearer {token}"}
    r = api("GET", "/api/v2/agents/live", headers=h)
    ok = r.status_code == 200
    if ok:
        agents = r.json().get("agents", [])
        if not any(a.get("agent_id") == "michelangelo" for a in agents):
            ok = False
    record("GET /api/v2/agents/live", ok,
           f"状态码 {r.status_code}" if not ok else "")


def test_agent_history(token):
    h = {"Authorization": f"Bearer {token}"}
    r = api("GET", "/api/v2/agents/michelangelo/history", headers=h)
    record("GET /api/v2/agents/michelangelo/history", r.status_code == 200,
           f"状态码 {r.status_code}" if r.status_code != 200 else "")


# ============================================================
# 5. 用户管理
# ============================================================
def test_users_list(token):
    h = {"Authorization": f"Bearer {token}"}
    r = api("GET", "/api/v2/users", headers=h)
    ok = r.status_code == 200 and "users" in r.json()
    record("GET /api/v2/users", ok,
           f"状态码 {r.status_code}" if not ok else "")


def test_users_create(token):
    h = {"Authorization": f"Bearer {token}"}
    import time
    suffix = str(int(time.time()))[-4:]
    username = f"test_user_{suffix}"
    r = api("POST", "/api/v2/users", headers=h, json_body={
        "username": username,
        "password": "TestPass123!",
        "display_name": "测试用户",
        "role": "viewer",
    })
    ok = r.status_code == 200 and r.json().get("success")
    if ok:
        # Store for RBAC test
        test_users_create._username = username
    record("POST /api/v2/users — 创建用户", ok,
           f"状态码 {r.status_code}" if not ok else f"用户名: {username}")

test_users_create._username = "test_user_001"  # default fallback


def test_users_rbac(token):
    """viewer 角色权限测试"""
    username = getattr(test_users_create, '_username', 'test_user_001')
    # 登录 viewer
    r = api("POST", "/api/v2/auth/login", json_body={
        "username": username, "password": "TestPass123!"
    })
    if r.status_code != 200:
        record("新用户登录", False, f"状态码 {r.status_code}")
        return
    body = r.json()
    if body.get("user", {}).get("role") != "viewer":
        record("新用户登录", False, f"role={body.get('user',{}).get('role')}")
        return
    record("新用户登录 (viewer)", True, "")
    vh = {"Authorization": f"Bearer {body.get('access_token')}"}

    # viewer 可读取
    r = api("GET", "/api/v2/tasks", headers=vh)
    record("viewer GET /api/v2/tasks → 200", r.status_code == 200,
           f"实际 {r.status_code}" if r.status_code != 200 else "")

    # viewer 不可创建任务
    r = api("POST", "/api/v2/tasks", headers=vh, json_body={"title": "越权"})
    record("viewer POST /api/v2/tasks → 403", r.status_code == 403,
           f"期望 403，实际 {r.status_code}" if r.status_code != 403 else "")

    # viewer 不可管理用户
    r = api("POST", "/api/v2/users", headers=vh, json_body={
        "username": "x", "password": "x", "display_name": "x"
    })
    record("viewer POST /api/v2/users → 403", r.status_code == 403,
           f"期望 403，实际 {r.status_code}" if r.status_code != 403 else "")


def test_users_delete_self(token):
    """不能删除自己 (admin id=1)"""
    h = {"Authorization": f"Bearer {token}"}
    r = api("DELETE", "/api/v2/users/1", headers=h)
    if r.status_code == 400:
        body = r.json()
        if "不能删除自己" in body.get("detail", ""):
            record("DELETE /api/v2/users/1 (自己) → 拒绝", True, "")
            return
    record("DELETE /api/v2/users/1 (自己) → 拒绝", False,
           f"状态码 {r.status_code}")


# ============================================================
# 6. 集成场景
# ============================================================
def test_scenario_full_workflow(token):
    """创建→更新→评论→完成→验证"""
    tid = _create_task(token, {
        "title": "完整工作流测试", "description": "端到端",
        "type": "feature", "priority": "high",
    })
    if not tid:
        record("场景: 完整工作流", False, "创建失败")
        return
    h = {"Authorization": f"Bearer {token}"}

    r = api("PUT", f"/api/v2/tasks/{tid}", headers=h, json_body={
        "status": "in_progress", "progress": 30
    })
    if r.status_code != 200 or not r.json().get("success"):
        record("场景: 完整工作流", False, f"更新失败: {r.status_code}")
        return

    r = api("POST", f"/api/v2/tasks/{tid}/comments", headers=h, json_body={
        "content": "进度正常"
    })
    if r.status_code != 200 or not r.json().get("success"):
        record("场景: 完整工作流", False, f"评论失败: {r.status_code}")
        return

    r = api("PUT", f"/api/v2/tasks/{tid}", headers=h, json_body={"status": "done"})
    if r.status_code != 200 or not r.json().get("success"):
        record("场景: 完整工作流", False, f"完成失败: {r.status_code}")
        return

    r = api("GET", f"/api/v2/tasks/{tid}", headers=h)
    ok = r.status_code == 200
    if ok:
        b = r.json()
        if b.get("status") != "done":
            ok = False
        elif not b.get("completed_at"):
            ok = False
        elif b.get("comment_count", 0) < 1:
            ok = False
    record("场景: 完整工作流", ok,
           f"最终状态异常" if not ok else "")
    api("DELETE", f"/api/v2/tasks/{tid}", headers=h)


def test_scenario_heartbeat(token):
    """上报→查询→验证"""
    h = {"Authorization": f"Bearer {token}"}
    r = api("POST", "/api/v2/agents/test-agent-001/heartbeat", headers=h, json_body={
        "agent_id": "test-agent-001", "agent_name": "测试Agent",
        "status": "busy", "cpu_usage": 80.0,
    })
    if r.status_code != 200:
        record("场景: 心跳生命周期", False, f"上报失败: {r.status_code}")
        return
    r = api("GET", "/api/v2/agents/live", headers=h)
    if r.status_code != 200:
        record("场景: 心跳生命周期", False, f"查询失败: {r.status_code}")
        return
    found = any(a.get("agent_id") == "test-agent-001" for a in r.json().get("agents", []))
    record("场景: 心跳生命周期", found, "未找到" if not found else "")


def test_scenario_token_refresh(token, refresh_token):
    r = api("POST", "/api/v2/auth/refresh", json_body={"refresh_token": refresh_token})
    if r.status_code != 200:
        record("场景: Token 刷新", False, f"刷新失败: {r.status_code}")
        return
    new_token = r.json().get("access_token")
    if not new_token:
        record("场景: Token 刷新", False, "新 token 缺失")
        return
    r2 = api("GET", "/api/v2/tasks", headers={"Authorization": f"Bearer {new_token}"})
    record("场景: Token 刷新→访问", r2.status_code == 200,
           f"状态码 {r2.status_code}" if r2.status_code != 200 else "")


# ============================================================
# 7. 回归测试
# ============================================================
def test_regression_v1():
    """非 /api/v2/ 端点不受破坏"""
    for path, name in [
        ("/api/tasks", "GET /api/tasks"),
        ("/api/plans", "GET /api/plans"),
        ("/api/loop/queue", "GET /api/loop/queue"),
        ("/api/workflow/status", "GET /api/workflow/status"),
    ]:
        r = api("GET", path)
        ok = r.status_code < 500
        record(f"回归: {name}", ok, f"状态码 {r.status_code}" if not ok else "")


def test_regression_openclaw():
    r = api("GET", "/api/openclaw/status")
    ok = r.status_code < 500
    record("回归: GET /api/openclaw/status", ok,
           f"状态码 {r.status_code}" if not ok else "")


# ============================================================
# Frontend
# ============================================================
def test_frontend_build():
    try:
        result = subprocess.run(
            ["npm", "run", "build"],
            cwd="/Users/apple/.openclaw/workspace/team-dashboard/frontend-v2",
            capture_output=True, text=True, timeout=120
        )
        ok = result.returncode == 0
        record("frontend-v2 npm run build", ok,
               result.stderr[-500:] if not ok and result.stderr else "build 返回非零")
    except FileNotFoundError:
        record("frontend-v2 npm run build", False, "npm 未找到")
    except subprocess.TimeoutExpired:
        record("frontend-v2 npm run build", False, "超时 (120s)")


def test_frontend_dev():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(3)
    try:
        result = sock.connect_ex(('127.0.0.1', 5173))
        ok = result == 0
        record("frontend-v2 dev server (:5173)", ok,
               "dev server 未运行" if not ok else "")
    except:
        record("frontend-v2 dev server (:5173)", False, "连接检查异常")
    finally:
        sock.close()


# ============================================================
# Main
# ============================================================
def main():
    print("=" * 60)
    print("🟧 看板 V2 集成测试 + 回归测试")
    print(f"⏰ {datetime.now().isoformat()}")
    print(f"📡 Backend: {BASE_URL}")
    print("=" * 60)

    r = api("GET", "/")
    if r.status_code == 0:
        print(f"\n❌ 后端不可达 ({BASE_URL})，测试中止")
        sys.exit(1)
    print(f"✅ 后端可达\n")

    # Auth
    print("📋 1. 认证 API")
    test_auth_no_token()
    test_auth_invalid_token()
    test_auth_init_admin()
    token, refresh = test_auth_login()
    if not token:
        print("\n❌ 登录失败"); print_report(); sys.exit(1)
    test_auth_me(token)
    test_auth_refresh(refresh)

    # Tasks CRUD
    print("\n📋 2. 任务管理 API")
    test_tasks_list(token)
    task_id = test_tasks_create(token)
    test_tasks_get(token, task_id)
    test_tasks_update(token, task_id)
    test_tasks_done(token, task_id)
    test_tasks_filter(token)
    test_tasks_delete(token)
    test_tasks_404(token)

    # Comments & Stats
    print("\n📋 3. 评论 & 统计")
    ctid = _create_task(token, {"title": "评论测试", "description": "评论"})
    test_task_comments(token, ctid)
    test_task_stats(token)

    # Agent
    print("\n📋 4. Agent 监控")
    test_agent_heartbeat(token)
    test_agent_live(token)
    test_agent_history(token)

    # Users
    print("\n📋 5. 用户管理")
    test_users_list(token)
    test_users_create(token)
    test_users_rbac(token)
    test_users_delete_self(token)

    # Scenarios
    print("\n📋 6. 集成场景")
    test_scenario_full_workflow(token)
    test_scenario_heartbeat(token)
    test_scenario_token_refresh(token, refresh)

    # Regression
    print("\n📋 7. 回归测试")
    test_regression_v1()
    test_regression_openclaw()

    # Frontend
    print("\n📋 Frontend")
    test_frontend_build()
    test_frontend_dev()

    # Logout
    test_auth_logout(token)

    print_report()


def print_report():
    total = len(RESULTS["passed"]) + len(RESULTS["failed"])
    passed = len(RESULTS["passed"])
    failed = len(RESULTS["failed"])
    print("\n" + "=" * 60)
    print("📊 测试报告")
    print("=" * 60)
    print(f"  总计: {total}")
    print(f"  ✅ 通过: {passed}")
    print(f"  ❌ 失败: {failed}")
    rate = round(passed / total * 100, 1) if total else 0
    print(f"  通过率: {passed}/{total} = {rate}%")

    if RESULTS["failed"]:
        print("\n❌ 失败详情:")
        for f in RESULTS["failed"]:
            print(f"  • {f['name']}: {f['detail']}")

    print("=" * 60)
    if failed == 0:
        print("🟧 全部通过！V2 集成测试通过 ✅")
    else:
        print(f"🟧 有 {failed} 项失败，需要修复")


if __name__ == "__main__":
    main()
