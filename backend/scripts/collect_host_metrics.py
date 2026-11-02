"""Dependency-free read-only host probe. Executable over SSH stdin, no install.

No files are changed and no services are started. Unsupported/failed metrics stay
null. An empty GPU list does not certify GPU absence; gpu_probe_state qualifies it.
"""
from __future__ import annotations

import csv
import io
import json
import os
import platform
import re
import shutil
import subprocess
import time
from pathlib import Path


def command(args: list[str], timeout: int = 4) -> str | None:
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return result.stdout.strip() if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def collect() -> dict:
    metrics = {
        "hostname": platform.node(), "os_version": platform.platform(),
        "architecture": platform.machine(), "cpu_logical_count": os.cpu_count(),
        "cpu_percent": None, "memory_total_bytes": None,
        "memory_available_bytes": None, "memory_percent": None,
        "disk_total_bytes": None, "disk_free_bytes": None,
        "gpus": [], "gpu_probe_state": "unavailable", "hardware_model": None,
        "docker_state": "unknown", "docker_version": None,
    }
    try:
        usage = shutil.disk_usage(Path.home())
        metrics.update(disk_total_bytes=usage.total, disk_free_bytes=usage.free)
    except OSError:
        pass
    if platform.system() == "Linux":
        try:
            values = {}
            for line in Path("/proc/meminfo").read_text().splitlines():
                name, value = line.split(":", 1)
                values[name] = int(value.strip().split()[0]) * 1024
            total, available = values["MemTotal"], values.get("MemAvailable")
            metrics.update(memory_total_bytes=total, memory_available_bytes=available)
            if available is not None and total:
                metrics["memory_percent"] = round((total - available) / total * 100, 1)
            before = [int(v) for v in Path("/proc/stat").read_text().splitlines()[0].split()[1:9]]
            time.sleep(0.15)
            after = [int(v) for v in Path("/proc/stat").read_text().splitlines()[0].split()[1:9]]
            delta = sum(after) - sum(before)
            idle = after[3] + after[4] - before[3] - before[4]
            if delta > 0:
                metrics["cpu_percent"] = round((1 - idle / delta) * 100, 1)
        except (OSError, ValueError, KeyError, IndexError):
            pass
        try:
            metrics["hardware_model"] = Path("/sys/class/dmi/id/product_name").read_text().strip()[:160]
        except OSError:
            pass
    elif platform.system() == "Darwin":
        total = command(["/usr/sbin/sysctl", "-n", "hw.memsize"])
        if total and total.isdigit():
            metrics["memory_total_bytes"] = int(total)
        # top reports used/unused physical memory, without equating free pages to
        # allocatable memory (which would misrepresent macOS cache/compression).
        top = command(["/usr/bin/top", "-l", "1", "-n", "0"])
        if top:
            cpu = re.search(r"CPU usage:.*?([\d.]+)% idle", top)
            if cpu:
                metrics["cpu_percent"] = round(100 - float(cpu.group(1)), 1)
            memory = re.search(r"PhysMem:\s*([\d.]+)([MG]) used.*?([\d.]+)([MG]) unused", top)
            if memory:
                unit = {"M": 1024 ** 2, "G": 1024 ** 3}
                used = float(memory.group(1)) * unit[memory.group(2)]
                unused = float(memory.group(3)) * unit[memory.group(4)]
                metrics["memory_percent"] = round(used / (used + unused) * 100, 1) if used + unused else None
                # This is physical-unused, not an invented Linux MemAvailable.
                metrics["memory_unused_bytes"] = int(unused)
        metrics["hardware_model"] = command(["/usr/sbin/sysctl", "-n", "hw.model"])
    gpu = command(["nvidia-smi", "--query-gpu=name,memory.total,memory.used,utilization.gpu", "--format=csv,noheader,nounits"])
    if gpu is not None:
        try:
            metrics["gpus"] = [{"name": row[0].strip(), "memory_total_bytes": int(float(row[1])) * 1024 ** 2,
                               "memory_used_bytes": int(float(row[2])) * 1024 ** 2,
                               "utilization_percent": float(row[3])}
                              for row in csv.reader(io.StringIO(gpu)) if len(row) == 4]
            metrics["gpu_probe_state"] = "available"
        except ValueError:
            metrics["gpu_probe_state"] = "error"
    docker = command(["docker", "info", "--format", "{{.ServerVersion}}"])
    if docker:
        metrics.update(docker_state="ready", docker_version=docker[:80])
    return metrics


if __name__ == "__main__":
    print(json.dumps(collect(), ensure_ascii=False, allow_nan=False))
