#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试新闻模块 API
"""
import requests
import json

BASE_URL = "http://localhost:3020"

def test_api(endpoint, method="GET", data=None):
    """测试 API 端点"""
    url = f"{BASE_URL}{endpoint}"
    try:
        if method == "GET":
            resp = requests.get(url, timeout=10)
        elif method == "POST":
            resp = requests.post(url, json=data, timeout=10)
        
        print(f"\n{'='*60}")
        print(f"测试：{method} {endpoint}")
        print(f"状态码：{resp.status_code}")
        
        if resp.status_code == 200:
            result = resp.json()
            print(f"响应：{json.dumps(result, ensure_ascii=False, indent=2)[:500]}")
            return True
        else:
            print(f"错误：{resp.text}")
            return False
    except Exception as e:
        print(f"异常：{e}")
        return False

def main():
    print("🧪 开始测试新闻模块 API...")
    
    tests = [
        ("/api/news/locations", "GET", None),
        ("/api/news/categories", "GET", None),
        ("/api/news", "GET", None),
        ("/api/news/stats", "GET", None),
    ]
    
    passed = 0
    failed = 0
    
    for endpoint, method, data in tests:
        if test_api(endpoint, method, data):
            passed += 1
        else:
            failed += 1
    
    print(f"\n{'='*60}")
    print(f"✅ 测试完成：{passed} 通过，{failed} 失败")
    
    if failed == 0:
        print("\n🎉 所有测试通过！新闻模块运行正常。")
        print(f"\n📰 访问新闻页面：{BASE_URL}/news")
    else:
        print("\n⚠️  部分测试失败，请检查后端服务是否启动。")

if __name__ == "__main__":
    main()
