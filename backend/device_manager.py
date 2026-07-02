#!/usr/bin/env python3
"""
设备管理器 - 设备状态管理、健康检查、自动发现、离线告警
"""

import json
import os
import asyncio
import subprocess
from datetime import datetime
from typing import Dict, List, Any, Optional
from data_manager import DATA_DIR, load_json, save_json, DEFAULT_DEVICES
from unified_data_manager import unified_data_manager

DEVICES_FILE = os.path.join(DATA_DIR, "devices.json")
DEVICE_HEALTH_FILE = os.path.join(DATA_DIR, "device_health.json")
DEVICE_ALERTS_FILE = os.path.join(DATA_DIR, "device_alerts.json")

# 设备健康检查配置
HEALTH_CHECK_INTERVAL = 30  # 秒
OFFLINE_THRESHOLD = 3  # 连续失败次数触发告警
PING_TIMEOUT = 2  # ping 超时时间 (秒)

class DeviceManager:
    def __init__(self):
        self.devices = unified_data_manager.list_devices() or load_json(DEVICES_FILE, DEFAULT_DEVICES)
        if self.devices:
            unified_data_manager.save_devices(self.devices, actor="device_manager:init", audit=False)
        self.health_records = unified_data_manager.load_device_health_records() or load_json(DEVICE_HEALTH_FILE, {})
        if self.health_records:
            unified_data_manager.save_device_health_records(self.health_records, actor="device_manager:init", audit=False)
        self.alerts = load_json(DEVICE_ALERTS_FILE, {"alerts": []})
        self._health_check_task = None
        self._running = False
    
    def get_devices(self) -> List[Dict]:
        """获取所有设备"""
        self.devices = unified_data_manager.list_devices()
        return self.devices
    
    def get_device(self, device_id: str) -> Optional[Dict]:
        """获取单个设备"""
        self.devices = unified_data_manager.list_devices()
        for device in self.devices:
            if device["id"] == device_id:
                return device
        return None
    
    def add_device(self, device: Dict) -> Dict:
        """添加新设备"""
        device["created_at"] = datetime.now().isoformat()
        device["updated_at"] = device["created_at"]
        device["status"] = device.get("status", "unknown")
        saved = unified_data_manager.add_device(device, actor="device_manager")
        self.devices = unified_data_manager.list_devices()
        return saved
    
    def update_device(self, device_id: str, updates: Dict) -> bool:
        """更新设备信息"""
        for device in self.devices:
            if device["id"] == device_id:
                updated = unified_data_manager.update_device(device_id, {**updates, "updated_at": datetime.now().isoformat()}, actor="device_manager")
                if updated:
                    self.devices = unified_data_manager.list_devices()
                    return True
                return False
        return False
    
    def delete_device(self, device_id: str) -> bool:
        """删除设备"""
        for i, device in enumerate(self.devices):
            if device["id"] == device_id:
                deleted = unified_data_manager.delete_device(device_id, actor="device_manager")
                self.devices = unified_data_manager.list_devices()
                return deleted
        return False
    
    async def ping_device(self, ip: str) -> bool:
        """Ping 检查设备是否在线"""
        try:
            # 根据系统选择 ping 命令
            param = "-n" if os.name == "nt" else "-c"
            count = "4" if os.name == "nt" else "3"
            timeout = str(PING_TIMEOUT)
            
            process = await asyncio.create_subprocess_exec(
                "ping", param, count, "-W", timeout, ip,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=PING_TIMEOUT * 5)
            return process.returncode == 0
        except Exception as e:
            print(f"[DeviceManager] Ping {ip} 失败：{e}")
            return False
    
    def check_port(self, ip: str, port: int, timeout: int = 2) -> bool:
        """检查端口是否开放"""
        import socket
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((ip, port))
            sock.close()
            return result == 0
        except Exception:
            return False
    
    async def check_device_health(self, device_id: str) -> Dict:
        """检查单个设备健康状态"""
        device = self.get_device(device_id)
        if not device:
            return {"error": "Device not found", "device_id": device_id}
        
        ip = device.get("ip", "")
        if not ip:
            return {"error": "No IP address", "device_id": device_id}
        
        # Ping 检查
        ping_success = await self.ping_device(ip)
        
        # 端口检查
        ports_status = []
        for port in device.get("ports", []):
            port_open = self.check_port(ip, port)
            ports_status.append({
                "port": port,
                "open": port_open,
                "checked_at": datetime.now().isoformat()
            })
        
        # 更新设备状态
        new_status = "online" if ping_success else "offline"
        self.update_device(device_id, {"status": new_status})
        
        # 记录健康检查历史
        health_record = {
            "device_id": device_id,
            "ip": ip,
            "ping_success": ping_success,
            "ports": ports_status,
            "status": new_status,
            "checked_at": datetime.now().isoformat(),
            "response_time_ms": None
        }
        
        # 保存健康记录
        if device_id not in self.health_records:
            self.health_records[device_id] = []
        self.health_records[device_id].append(health_record)
        
        # 只保留最近 100 条记录
        self.health_records[device_id] = self.health_records[device_id][-100:]
        unified_data_manager.append_device_health_record(health_record, actor="device_manager")
        
        # 检查是否需要告警
        await self._check_offline_alert(device_id, ping_success)
        
        return health_record
    
    async def _check_offline_alert(self, device_id: str, ping_success: bool):
        """检查设备离线并触发告警"""
        if device_id not in self.health_records:
            return
        
        records = self.health_records[device_id]
        if len(records) < OFFLINE_THRESHOLD:
            return
        
        # 检查最近连续失败次数
        recent_records = records[-OFFLINE_THRESHOLD:]
        consecutive_failures = sum(1 for r in recent_records if not r["ping_success"])
        
        device = self.get_device(device_id)
        device_name = device.get("name", device_id) if device else device_id
        
        if consecutive_failures >= OFFLINE_THRESHOLD:
            # 检查是否已有未处理的告警
            existing_alert = any(
                a["device_id"] == device_id and a["status"] == "active"
                for a in self.alerts.get("alerts", [])
            )
            
            if not existing_alert:
                alert = {
                    "id": f"alert_{device_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                    "device_id": device_id,
                    "device_name": device_name,
                    "type": "offline",
                    "message": f"设备 {device_name} ({device.get('ip', 'N/A')}) 已离线",
                    "status": "active",
                    "created_at": datetime.now().isoformat(),
                    "severity": "high"
                }
                self.alerts.setdefault("alerts", []).append(alert)
                save_json(DEVICE_ALERTS_FILE, self.alerts)
                print(f"[DeviceManager] ⚠️ 告警：{alert['message']}")
        else:
            # 设备恢复在线，关闭告警
            for alert in self.alerts.get("alerts", []):
                if alert["device_id"] == device_id and alert["status"] == "active":
                    alert["status"] = "resolved"
                    alert["resolved_at"] = datetime.now().isoformat()
            save_json(DEVICE_ALERTS_FILE, self.alerts)
    
    async def auto_discover_devices(self, ip_range: str = "192.168.31.0/24") -> List[Dict]:
        """自动发现网络中的设备"""
        import ipaddress
        
        discovered = []
        network = ipaddress.ip_network(ip_range, strict=False)
        
        # 扫描网络 (限制扫描数量以避免过载)
        hosts_to_scan = list(network.hosts())[:50]
        
        tasks = []
        for host in hosts_to_scan:
            tasks.append(self._discover_single_host(str(host)))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for result in results:
            if isinstance(result, dict) and result.get("discovered"):
                discovered.append(result)
        
        return discovered
    
    async def _discover_single_host(self, ip: str) -> Dict:
        """发现单个主机"""
        is_online = await self.ping_device(ip)
        
        if is_online:
            try:
                hostname = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: subprocess.getoutput(f"nslookup {ip} 2>/dev/null | grep Name | awk '{{print $2}}'")
                )
            except Exception:
                hostname = ""
            
            return {
                "discovered": True,
                "ip": ip,
                "hostname": hostname.strip() if hostname else "",
                "detected_at": datetime.now().isoformat()
            }
        
        return {"discovered": False, "ip": ip}
    
    def get_health_history(self, device_id: str, limit: int = 10) -> List[Dict]:
        """获取设备健康历史"""
        self.health_records = unified_data_manager.load_device_health_records()
        records = self.health_records.get(device_id, [])
        return records[-limit:]
    
    def get_alerts(self, status: str = "active") -> List[Dict]:
        """获取告警列表"""
        alerts = self.alerts.get("alerts", [])
        if status:
            return [a for a in alerts if a["status"] == status]
        return alerts
    
    def acknowledge_alert(self, alert_id: str) -> bool:
        """确认告警"""
        for alert in self.alerts.get("alerts", []):
            if alert["id"] == alert_id:
                alert["status"] = "acknowledged"
                alert["acknowledged_at"] = datetime.now().isoformat()
                save_json(DEVICE_ALERTS_FILE, self.alerts)
                return True
        return False
    
    async def start_health_monitoring(self, interval: int = HEALTH_CHECK_INTERVAL):
        """启动健康监控任务"""
        if self._health_check_task and not self._health_check_task.done():
            return

        self._running = True
        
        async def monitor_loop():
            print(f"[DeviceManager] 🔄 启动设备健康监控 (间隔：{interval}秒)")
            while self._running:
                try:
                    for device in self.get_devices():
                        await self.check_device_health(device["id"])
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    print(f"[DeviceManager] 健康监控循环异常：{e}")
                await asyncio.sleep(interval)
        
        self._health_check_task = asyncio.create_task(monitor_loop())
    
    def stop_health_monitoring(self):
        """停止健康监控"""
        self._running = False
        if self._health_check_task:
            self._health_check_task.cancel()
            self._health_check_task = None
    
    def get_device_stats(self) -> Dict:
        """获取设备统计信息"""
        self.devices = unified_data_manager.list_devices()
        total = len(self.devices)
        online = sum(1 for d in self.devices if d["status"] == "online")
        offline = sum(1 for d in self.devices if d["status"] == "offline")
        unknown = sum(1 for d in self.devices if d["status"] == "unknown")
        active_alerts = len(self.get_alerts("active"))
        
        return {
            "total": total,
            "online": online,
            "offline": offline,
            "unknown": unknown,
            "active_alerts": active_alerts,
            "health_rate": round(online / total * 100, 2) if total > 0 else 0
        }

# 单例
device_manager = DeviceManager()

if __name__ == "__main__":
    import asyncio
    
    async def test():
        print("设备列表:", len(device_manager.get_devices()))
        print("设备统计:", device_manager.get_device_stats())
        
        for device in device_manager.get_devices():
            health = await device_manager.check_device_health(device["id"])
            print(f"{device['id']}: {health.get('status', 'unknown')}")
    
    asyncio.run(test())
