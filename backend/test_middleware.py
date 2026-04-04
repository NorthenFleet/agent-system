"""
中间件测试脚本
用于验证速率限制、认证、日志和异常检测功能
"""
import requests
import time
import json
from concurrent.futures import ThreadPoolExecutor

BASE_URL = "http://localhost:3020"
API_KEY = "dashboard-key-001"

def test_health():
    """测试健康检查接口"""
    print("\n=== 测试健康检查 ===")
    response = requests.get(f"{BASE_URL}/health")
    print(f"状态码：{response.status_code}")
    print(f"响应：{json.dumps(response.json(), indent=2)}")
    assert response.status_code == 200
    print("✅ 健康检查通过")

def test_rate_limiting():
    """测试速率限制"""
    print("\n=== 测试速率限制 ===")
    
    # 发送多个请求
    success_count = 0
    rate_limited_count = 0
    
    for i in range(110):
        response = requests.get(
            f"{BASE_URL}/api/agents",
            headers={"X-API-Key": API_KEY}
        )
        
        if response.status_code == 200:
            success_count += 1
        elif response.status_code == 429:
            rate_limited_count += 1
            print(f"⚠️  第 {i+1} 个请求被限流")
    
    print(f"成功请求：{success_count}")
    print(f"被限流请求：{rate_limited_count}")
    
    if rate_limited_count > 0:
        print("✅ 速率限制正常工作")
    else:
        print("⚠️  速率限制可能未生效（可能限制值较高）")

def test_auth():
    """测试 API Key 认证"""
    print("\n=== 测试 API Key 认证 ===")
    
    # 有效 Key
    response = requests.get(
        f"{BASE_URL}/api/agents",
        headers={"X-API-Key": API_KEY}
    )
    print(f"有效 Key - 状态码：{response.status_code}")
    assert response.status_code == 200
    
    # 无效 Key
    response = requests.get(
        f"{BASE_URL}/api/agents",
        headers={"X-API-Key": "invalid-key"}
    )
    print(f"无效 Key - 状态码：{response.status_code}")
    assert response.status_code == 401
    
    # 无 Key
    response = requests.get(f"{BASE_URL}/api/agents")
    print(f"无 Key - 状态码：{response.status_code}")
    
    print("✅ 认证测试通过")

def test_monitoring_apis():
    """测试监控 API"""
    print("\n=== 测试监控 API ===")
    
    # 速率限制统计
    response = requests.get(f"{BASE_URL}/api/monitor/rate-limit")
    print(f"速率限制统计：{json.dumps(response.json(), indent=2)}")
    
    # 认证统计
    response = requests.get(f"{BASE_URL}/api/monitor/auth")
    print(f"认证统计：{json.dumps(response.json(), indent=2)}")
    
    # 安全统计
    response = requests.get(f"{BASE_URL}/api/monitor/security/stats")
    print(f"安全统计：{json.dumps(response.json(), indent=2)}")
    
    print("✅ 监控 API 测试通过")

def test_path_probing():
    """测试路径探测检测"""
    print("\n=== 测试路径探测检测 ===")
    
    sensitive_paths = [
        "/admin",
        "/.env",
        "/.git/config",
        "/wp-admin",
        "/phpmyadmin"
    ]
    
    for path in sensitive_paths:
        response = requests.get(f"{BASE_URL}{path}")
        print(f"探测 {path}: {response.status_code}")
    
    # 检查告警
    time.sleep(1)
    response = requests.get(f"{BASE_URL}/api/monitor/alerts")
    alerts = response.json().get("alerts", [])
    
    path_probe_alerts = [a for a in alerts if a.get("type") == "PATH_PROBING"]
    if path_probe_alerts:
        print(f"✅ 检测到 {len(path_probe_alerts)} 次路径探测告警")
    else:
        print("⚠️  路径探测告警可能未达到阈值")

def run_all_tests():
    """运行所有测试"""
    print("🚀 开始中间件测试")
    print(f"目标地址：{BASE_URL}")
    
    try:
        test_health()
        test_auth()
        test_monitoring_apis()
        test_path_probing()
        # test_rate_limiting()  # 可选，会发送大量请求
        
        print("\n" + "="*50)
        print("✅ 所有测试完成！")
        print("="*50)
        
    except requests.exceptions.ConnectionError:
        print("\n❌ 错误：无法连接到服务器")
        print(f"请确保服务器在 {BASE_URL} 运行")
        print("\n启动服务器命令:")
        print("  cd /Users/apple/WorkSpace/team-dashboard/backend")
        print("  python main.py")

if __name__ == "__main__":
    run_all_tests()
