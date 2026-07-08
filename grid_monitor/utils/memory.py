import os
import sys
from typing import Any


def _round_mb(value_bytes: int | None) -> float | None:
    if value_bytes is None:
        return None
    return round(value_bytes / (1024 * 1024), 2)


def _linux_proc_memory() -> dict[str, int] | None:
    try:
        status = {}
        with open("/proc/self/status", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith(("VmRSS:", "VmHWM:")):
                    key, value = line.split(":", 1)
                    status[key] = int(value.strip().split()[0]) * 1024
        if status:
            return {
                "rss_bytes": status.get("VmRSS"),
                "peak_rss_bytes": status.get("VmHWM") or status.get("VmRSS"),
            }
    except OSError:
        return None
    return None


def _windows_process_memory() -> dict[str, int] | None:
    if sys.platform != "win32":
        return None
    try:
        import ctypes

        class ProcessMemoryCounters(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.c_ulong),
                ("PageFaultCount", ctypes.c_ulong),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        get_process_memory_info = ctypes.windll.psapi.GetProcessMemoryInfo
        get_process_memory_info.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ProcessMemoryCounters),
            ctypes.c_ulong,
        ]
        get_process_memory_info.restype = ctypes.c_int
        ok = get_process_memory_info(
            ctypes.windll.kernel32.GetCurrentProcess(),
            ctypes.byref(counters),
            counters.cb,
        )
        if not ok:
            return None
        return {
            "rss_bytes": int(counters.WorkingSetSize),
            "peak_rss_bytes": int(counters.PeakWorkingSetSize),
        }
    except Exception:
        return None


def process_memory_status(limit_mb: int = 512) -> dict[str, Any]:
    raw = _linux_proc_memory() or _windows_process_memory() or {}
    rss_mb = _round_mb(raw.get("rss_bytes"))
    peak_mb = _round_mb(raw.get("peak_rss_bytes"))
    return {
        "rss_mb": rss_mb,
        "peak_rss_mb": peak_mb,
        "limit_mb": limit_mb,
        "rss_percent_of_limit": (
            round((rss_mb / limit_mb) * 100, 1)
            if rss_mb is not None and limit_mb
            else None
        ),
        "peak_percent_of_limit": (
            round((peak_mb / limit_mb) * 100, 1)
            if peak_mb is not None and limit_mb
            else None
        ),
        "pid": os.getpid(),
    }
