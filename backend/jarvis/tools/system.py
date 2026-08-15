"""Host telemetry, read straight from the OS with no extra dependencies."""

from __future__ import annotations

import os
import platform
import shutil
import time
from collections.abc import Mapping
from pathlib import Path

from .base import JsonSchema

_MEMINFO = Path("/proc/meminfo")
_UPTIME = Path("/proc/uptime")


def _gib(kib: float) -> str:
    return f"{kib / (1024 * 1024):.1f} GiB"


def memory_summary() -> str | None:
    """Total/available memory from ``/proc/meminfo`` (Linux only)."""
    try:
        raw = _MEMINFO.read_text(encoding="utf-8")
    except OSError:
        return None
    values: dict[str, float] = {}
    for line in raw.splitlines():
        key, _, rest = line.partition(":")
        parts = rest.split()
        if parts:
            try:
                values[key] = float(parts[0])
            except ValueError:
                continue
    total = values.get("MemTotal")
    available = values.get("MemAvailable")
    if total is None or available is None:
        return None
    used_pct = (1 - available / total) * 100
    return f"memory {_gib(total - available)} of {_gib(total)} used ({used_pct:.0f}%)"


def uptime_summary() -> str | None:
    try:
        seconds = float(_UPTIME.read_text(encoding="utf-8").split()[0])
    except (OSError, IndexError, ValueError):
        return None
    hours, minutes = divmod(int(seconds) // 60, 60)
    days, hours = divmod(hours, 24)
    if days:
        return f"up {days}d {hours}h"
    return f"up {hours}h {minutes}m"


def load_summary() -> str | None:
    try:
        one, five, fifteen = os.getloadavg()
    except (OSError, AttributeError):
        return None
    return f"load {one:.2f} / {five:.2f} / {fifteen:.2f}"


def disk_summary(path: str = "/") -> str | None:
    try:
        usage = shutil.disk_usage(path)
    except OSError:
        return None
    used_pct = usage.used / usage.total * 100 if usage.total else 0
    return (
        f"disk {usage.used / 1024**3:.0f}G of {usage.total / 1024**3:.0f}G used "
        f"({used_pct:.0f}%), {usage.free / 1024**3:.0f}G free"
    )


class SystemInfoTool:
    name = "system_info"
    description = (
        "Report the host machine's status: platform, CPU count, load average, "
        "memory use, disk use and uptime."
    )
    parameters: JsonSchema = {"type": "object", "properties": {}}

    async def run(self, arguments: Mapping[str, object]) -> str:
        facts = [
            f"{platform.system()} {platform.release()} on {platform.machine()}",
            f"{os.cpu_count() or 'unknown'} CPUs",
            load_summary(),
            memory_summary(),
            disk_summary(),
            uptime_summary(),
            f"local time {time.strftime('%H:%M')}",
        ]
        return ", ".join(fact for fact in facts if fact)
