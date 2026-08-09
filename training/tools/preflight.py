from __future__ import annotations

import argparse
import ctypes
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
TRAINING_ROOT = REPO_ROOT / "training"
WORKSPACE_ROOT = TRAINING_ROOT / "workspace"


def _run(command: list[str]) -> tuple[int, str]:
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, str(exc)
    output = (completed.stdout or completed.stderr or "").strip()
    return completed.returncode, output


def detect_nvidia_gpus() -> list[dict[str, Any]]:
    if shutil.which("nvidia-smi") is None:
        return []

    code, output = _run(
        [
            "nvidia-smi",
            "--query-gpu=name,memory.total,driver_version",
            "--format=csv,noheader,nounits",
        ]
    )
    if code != 0:
        return []

    gpus: list[dict[str, Any]] = []
    for line in output.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 3:
            continue
        try:
            memory_mb = int(float(parts[1]))
        except ValueError:
            memory_mb = 0
        gpus.append(
            {
                "name": parts[0],
                "memory_mb": memory_mb,
                "memory_gb": round(memory_mb / 1024, 2),
                "driver_version": parts[2],
            }
        )
    return gpus


def detect_memory() -> dict[str, float | None]:
    total_bytes: int | None = None
    available_bytes: int | None = None
    if sys.platform == "win32":
        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("length", ctypes.c_ulong),
                ("memory_load", ctypes.c_ulong),
                ("total_physical", ctypes.c_ulonglong),
                ("available_physical", ctypes.c_ulonglong),
                ("total_page_file", ctypes.c_ulonglong),
                ("available_page_file", ctypes.c_ulonglong),
                ("total_virtual", ctypes.c_ulonglong),
                ("available_virtual", ctypes.c_ulonglong),
                ("available_extended_virtual", ctypes.c_ulonglong),
            ]

        status = MemoryStatus()
        status.length = ctypes.sizeof(MemoryStatus)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            total_bytes = int(status.total_physical)
            available_bytes = int(status.available_physical)
    elif hasattr(os, "sysconf"):
        try:
            page_size = int(os.sysconf("SC_PAGE_SIZE"))
            total_bytes = page_size * int(os.sysconf("SC_PHYS_PAGES"))
            available_bytes = page_size * int(os.sysconf("SC_AVPHYS_PAGES"))
        except (OSError, TypeError, ValueError):
            pass

    return {
        "total_gb": round(total_bytes / (1024**3), 2) if total_bytes else None,
        "available_gb": (
            round(available_bytes / (1024**3), 2) if available_bytes else None
        ),
    }


def detect_cuda() -> dict[str, Any]:
    driver_reported_version: str | None = None
    nvidia_smi = shutil.which("nvidia-smi")
    if nvidia_smi:
        code, output = _run([nvidia_smi])
        if code == 0:
            match = re.search(r"CUDA Version:\s*([0-9.]+)", output)
            if match:
                driver_reported_version = match.group(1)

    nvcc_path = shutil.which("nvcc")
    nvcc_version: str | None = None
    if nvcc_path:
        code, output = _run([nvcc_path, "--version"])
        if code == 0:
            nvcc_version = output
    return {
        "driver_reported_version": driver_reported_version,
        "toolkit_available": nvcc_path is not None,
        "nvcc_path": nvcc_path,
        "nvcc_version": nvcc_version,
    }


def recommend_mode(gpus: list[dict[str, Any]]) -> str:
    max_vram = max((int(gpu.get("memory_mb", 0)) for gpu in gpus), default=0)
    if max_vram >= 24 * 1024:
        return "lora_7b_candidate"
    if max_vram >= 12 * 1024:
        return "small_model_or_aggressive_qlora"
    return "pipeline_and_dataset_first"


def build_report() -> dict[str, Any]:
    disk = shutil.disk_usage(REPO_ROOT)
    git_path = shutil.which("git")
    git_version = None
    if git_path:
        code, output = _run([git_path, "--version"])
        if code == 0:
            git_version = output

    gpus = detect_nvidia_gpus()
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repo_root": str(REPO_ROOT),
        "platform": platform.platform(),
        "cpu": {
            "name": platform.processor() or platform.machine() or "unknown",
            "logical_cores": os.cpu_count(),
        },
        "ram": detect_memory(),
        "python": {
            "version": platform.python_version(),
            "executable": sys.executable,
            "supported_for_bootstrap": sys.version_info >= (3, 10),
        },
        "git": {
            "available": git_path is not None,
            "path": git_path,
            "version": git_version,
        },
        "disk": {
            "total_gb": round(disk.total / (1024**3), 2),
            "free_gb": round(disk.free / (1024**3), 2),
        },
        "nvidia_gpus": gpus,
        "cuda": detect_cuda(),
        "recommended_mode": recommend_mode(gpus),
        "notes": [
            "No CUDA GPU is required for dataset/schema/bootstrap work.",
            "Do not choose a PyTorch/CUDA build until the selected upstream requirements are inspected.",
            "Public datasets should be streamed/subsetted before any bulk download.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect training machine readiness.")
    parser.add_argument(
        "--write-report",
        action="store_true",
        help="Write training/workspace/preflight.json.",
    )
    args = parser.parse_args()

    report = build_report()
    print(json.dumps(report, indent=2, ensure_ascii=False))

    if args.write_report:
        WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)
        target = WORKSPACE_ROOT / "preflight.json"
        target.write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"Wrote: {target}")

    return 0 if report["python"]["supported_for_bootstrap"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
