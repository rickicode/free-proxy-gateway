"""Installer: install sing-box, AdGuard Home, dependencies on fresh OS."""

import os
import platform
from pathlib import Path

from .utils import (
    run, run_ok, require_root, require_cmd,
    SINGBOX_BIN, ADGUARD_BIN, ADGUARD_CFG, SINGBOX_UI,
    ensure_dir, write_file,
    ok, fail, info, warn, header, dim,
)


def install_singbox() -> bool:
    """Install sing-box binary if not present."""
    if SINGBOX_BIN.exists():
        ok(f"sing-box sudah terinstall: {SINGBOX_BIN}")
        return True

    header("Install sing-box")

    # Detect architecture
    arch = platform.machine()
    arch_map = {"x86_64": "amd64", "aarch64": "arm64", "armv7l": "armv7"}
    go_arch = arch_map.get(arch, "amd64")

    info(f"Architecture: {arch} → {go_arch}")

    # Get latest version
    info("Fetching latest version...")
    r = run(["bash", "-c", "curl -s https://api.github.com/repos/SagerNet/sing-box/releases/latest | grep tag_name | head -1 | cut -d'\"' -f4"])
    version = r.stdout.strip().lstrip("v")
    if not version:
        warn("Gagal detect versi, pakai default")
        version = "1.11.4"
    info(f"Version: {version}")

    # Download
    url = f"https://github.com/SagerNet/sing-box/releases/download/v{version}/sing-box-{version}-linux-{go_arch}.tar.gz"
    info(f"Downloading: {url}")

    r = run(["bash", "-c", f"curl -sL {url} | tar xz -C /tmp/ && mv /tmp/sing-box-{version}-linux-{go_arch}/sing-box {SINGBOX_BIN} && chmod +x {SINGBOX_BIN}"])
    if r.returncode != 0:
        fail("Download gagal")
        return False

    ok(f"sing-box installed: {SINGBOX_BIN}")
    r = run([str(SINGBOX_BIN), "version"])
    info(f"Version: {r.stdout.strip()}")
    return True


def install_adguard() -> bool:
    """Install AdGuard Home if not present."""
    if ADGUARD_BIN.exists():
        ok(f"AdGuard Home sudah terinstall: {ADGUARD_BIN}")
        return True

    header("Install AdGuard Home")
    info("Downloading installer...")

    r = run(["bash", "-c", "curl -s -S -L https://raw.githubusercontent.com/AdguardTeam/AdGuardHome/master/scripts/install.sh | sh -s -- -v"], capture=False)
    if r.returncode != 0:
        fail("AdGuard Home install gagal")
        return False

    ok(f"AdGuard Home installed: {ADGUARD_BIN}")
    return True


def install_dependencies() -> bool:
    """Install system dependencies."""
    header("Install Dependencies")

    packages = ["wireguard", "iptables", "curl", "python3-yaml"]
    missing = []

    for pkg in packages:
        if not run_ok(["dpkg", "-s", pkg]):
            missing.append(pkg)

    if missing:
        info(f"Installing: {', '.join(missing)}")
        run(["apt-get", "update", "-qq"], capture=False)
        run(["apt-get", "install", "-y", "-qq"] + missing, capture=False)
        ok(f"Installed: {', '.join(missing)}")
    else:
        ok("Semua dependencies sudah terinstall")

    return True


def setup_ip_forwarding():
    """Enable IP forwarding."""
    sysctl_conf = Path("/etc/sysctl.d/99-singbox.conf")
    write_file(sysctl_conf, "net.ipv4.ip_forward = 1\n")
    run(["sysctl", "-p", str(sysctl_conf)])
    ok("IP forwarding enabled")


def setup_directories():
    """Create required directories and ip-check rule set."""
    dirs = [
        Path("/etc/singbox-vpn"),
        Path("/etc/sing-box"),
        SINGBOX_UI,
        Path("/opt/rules/compiled"),
    ]
    for d in dirs:
        ensure_dir(d)

    # Create ip-check rule set source (used by route rules)
    ip_check_json = Path("/opt/rules/ip-check.json")
    if not ip_check_json.exists():
        write_file(ip_check_json, '{\n  "version": 2,\n  "rules": [\n    {\n      "domain": [\n        "ifconfig.co",\n        "ifconfig.me",\n        "icanhazip.com",\n        "wtfismyip.com",\n        "checkip.amazonaws.com"\n      ],\n      "domain_suffix": [\n        ".ipinfo.io",\n        ".ip-api.com",\n        ".ipify.org",\n        ".ipwho.is",\n        ".browserleaks.com",\n        ".dnsleaktest.com",\n        ".ipleak.net",\n        ".whoer.net",\n        ".whatismyip.com"\n      ]\n    }\n  ]\n}\n')
        # Compile rule set
        if SINGBOX_BIN.exists():
            compiled = Path("/opt/rules/compiled/ip-check.srs")
            run([str(SINGBOX_BIN), "rule-set", "compile", "-o", str(compiled), str(ip_check_json)])
            ok("ip-check rule set compiled")

    ok("Directories created")


def install_all() -> bool:
    """Full installation for fresh OS."""
    require_root()

    header("═══ singbox-vpn Full Install ═══")

    # 1. Dependencies
    install_dependencies()

    # 2. IP forwarding
    setup_ip_forwarding()

    # 3. Directories
    setup_directories()

    # 4. sing-box
    if not install_singbox():
        return False

    # 5. AdGuard Home
    if not install_adguard():
        return False

    # 6. Python yaml
    try:
        import yaml
    except ImportError:
        info("Installing PyYAML...")
        run(["apt-get", "install", "-y", "-qq", "python3-yaml"], capture=False)

    header("✅ Dependencies terinstall!")
    return True


def check_install_status() -> dict:
    """Check what's installed."""
    return {
        "singbox": SINGBOX_BIN.exists(),
        "adguard": ADGUARD_BIN.exists(),
        "wireguard": require_cmd("wg"),
        "iptables": require_cmd("iptables"),
        "ip_forward": Path("/proc/sys/net/ipv4/ip_forward").read_text().strip() == "1",
    }
