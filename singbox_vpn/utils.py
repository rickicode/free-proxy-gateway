"""Shared utilities: colors, shell exec, file ops, service helpers."""

import subprocess
import shutil
import sys
import os
import json
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────
CONFIG_DIR     = Path("/etc/singbox-vpn")
CONFIG_FILE    = CONFIG_DIR / "config.yaml"
SINGBOX_BIN    = Path("/usr/local/bin/sing-box")
SINGBOX_CFG    = Path("/etc/sing-box/config.json")
SINGBOX_LOG    = Path("/var/log/sing-box.log")
SINGBOX_UI     = Path("/etc/sing-box/ui")
TPROXY_SCRIPT  = Path("/usr/local/bin/tproxy-setup")
COLLECTOR_BIN  = Path("/opt/proxy-collector.py")
STATE_FILE     = Path("/opt/.proxy-collector-state.json")
LOG_FILE       = Path("/opt/proxy-collector-last-run.json")
DNSMASQ_DIR    = Path("/etc/dnsmasq.d")
ADGUARD_CFG    = Path("/opt/AdGuardHome/AdGuardHome.yaml")
ADGUARD_BIN    = Path("/opt/AdGuardHome/AdGuardHome")
FIX_NAT_SCRIPT = Path("/usr/local/bin/fix-nat.sh")
RULES_DIR      = Path("/opt/rules/compiled")

GITHUB_RAW     = "https://raw.githubusercontent.com/rickicode/free-proxy-gateway/main/output/live-proxies.json"

# ── Colors ────────────────────────────────────────────────────────────
class C:
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    RED    = "\033[31m"
    GREEN  = "\033[32m"
    YELLOW = "\033[33m"
    CYAN   = "\033[36m"
    DIM    = "\033[2m"

def ok(msg):      print(f"  {C.GREEN}✓{C.RESET} {msg}")
def warn(msg):    print(f"  {C.YELLOW}⚠{C.RESET} {msg}")
def fail(msg):    print(f"  {C.RED}✗{C.RESET} {msg}")
def info(msg):    print(f"  {C.CYAN}→{C.RESET} {msg}")
def header(msg):  print(f"\n{C.BOLD}{msg}{C.RESET}")
def dim(msg):     print(f"  {C.DIM}{msg}{C.RESET}")
def divider():    print(f"  {C.DIM}{'─' * 60}{C.RESET}")

# ── Shell helpers ─────────────────────────────────────────────────────
def run(cmd: list[str] | str, check=False, capture=True, **kw) -> subprocess.CompletedProcess:
    """Run a shell command."""
    if isinstance(cmd, str):
        cmd = ["bash", "-c", cmd]
    return subprocess.run(cmd, capture_output=capture, text=True, check=check, **kw)

def run_ok(cmd: list[str] | str) -> bool:
    """Return True if exit code 0."""
    return run(cmd).returncode == 0

# ── Guards ────────────────────────────────────────────────────────────
def require_root():
    if os.geteuid() != 0:
        fail("Harus dijalankan sebagai root")
        sys.exit(1)

def require_cmd(name: str) -> bool:
    return shutil.which(name) is not None

# ── File helpers ──────────────────────────────────────────────────────
def ensure_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)

def write_file(path: Path, content: str, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    os.chmod(path, mode)

def read_file(path: Path) -> str | None:
    try:
        return path.read_text()
    except FileNotFoundError:
        return None

def read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return None

def write_json(path: Path, data: dict, indent=2):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=indent))

# ── Service helpers ───────────────────────────────────────────────────
def service_running(name: str) -> bool:
    return run(["systemctl", "is-active", "--quiet", name]).returncode == 0

def service_enabled(name: str) -> bool:
    return run(["systemctl", "is-enabled", "--quiet", name]).returncode == 0

def enable_service(name: str):
    run(["systemctl", "enable", name])

def start_service(name: str):
    run(["systemctl", "start", name])

def stop_service(name: str):
    run(["systemctl", "stop", name])

def restart_service(name: str):
    run(["systemctl", "restart", name])

def daemon_reload():
    run(["systemctl", "daemon-reload"])

# ── Network helpers ───────────────────────────────────────────────────
def get_interfaces() -> list[str]:
    """Get list of active network interfaces (excluding lo, virtual)."""
    result = run(["ip", "-br", "link", "show", "up"])
    ifaces = []
    for line in result.stdout.strip().splitlines():
        name = line.split()[0]
        if name in ("lo",):
            continue
        ifaces.append(name)
    return ifaces

def get_interface_cidr(iface: str) -> str | None:
    """Get IPv4 CIDR of an interface, e.g. '192.168.92.1/24'."""
    result = run(["ip", "-4", "-br", "addr", "show", iface])
    parts = result.stdout.strip().split()
    for p in parts:
        if "/" in p and "." in p:
            return p
    return None

def get_subnet(iface: str) -> str | None:
    """Get /24 subnet from interface, e.g. '192.168.92.0/24'."""
    cidr = get_interface_cidr(iface)
    if not cidr:
        return None
    ip = cidr.split("/")[0]
    parts = ip.split(".")
    return f"{parts[0]}.{parts[1]}.{parts[2]}.0/24"

def get_ip(iface: str) -> str | None:
    """Get IPv4 address of interface."""
    cidr = get_interface_cidr(iface)
    return cidr.split("/")[0] if cidr else None
