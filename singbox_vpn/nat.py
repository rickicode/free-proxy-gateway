"""NAT management per-interface.

Uses policy routing + MASQUERADE (simpler and more reliable than TProxy).
Handles all protocols: TCP, UDP, ICMP.
"""

import os
from pathlib import Path

from .utils import (
    run, run_ok, require_root,
    write_file, read_file, read_json, write_json,
    ADGUARD_CFG, ADGUARD_BIN,
    get_subnet, get_ip, get_interface_cidr,
    ok, fail, info, warn, header, dim,
    service_running, enable_service, start_service, stop_service,
    daemon_reload,
)


def _get_route_table_id(iface: str) -> int:
    """Get route table ID for interface. ponytail: fixed mapping, add dynamic if needed."""
    table_map = {"eth2": 2022, "eth3": 2023, "eth4": 2024}
    return table_map.get(iface, 2022)


# ── Policy routing setup ─────────────────────────────────────────────

def setup_routing(iface: str, cfg: dict) -> bool:
    """Setup policy routing for interface subnet via tun0/singtun."""
    require_root()
    subnet = get_subnet(iface)
    if not subnet:
        fail(f"Subnet tidak ditemukan untuk {iface}")
        return False

    table_id = _get_route_table_id(iface)

    header(f"Policy Routing — {iface}")

    # Local subnet rule FIRST (higher priority = lower number)
    run(["ip", "rule", "del", "to", subnet])
    run(["ip", "rule", "add", "to", subnet, "lookup", "main", "pref", "8998"])
    ok(f"ip rule: to {subnet} → main (local)")

    # Then policy routing for outbound traffic
    run(["ip", "rule", "del", "from", subnet])
    run(["ip", "rule", "add", "from", subnet, "lookup", str(table_id), "pref", "8999"])
    ok(f"ip rule: from {subnet} → table {table_id}")

    # MASQUERADE for return traffic via singtun/tun interfaces
    for tun_iface in ["singtun0", "singtun1", "tun0"]:
        run(["iptables", "-t", "nat", "-A", "POSTROUTING",
             "-s", subnet, "-o", tun_iface, "-j", "MASQUERADE"])
    ok(f"MASQUERADE: {subnet} → singtun/tun")

    return True


def flush_routing(iface: str, cfg: dict, quiet=False) -> bool:
    """Remove policy routing for interface."""
    require_root()
    subnet = get_subnet(iface)
    if not subnet:
        return False

    run(["ip", "rule", "del", "from", subnet])

    for tun_iface in ["singtun0", "singtun1", "tun0"]:
        run(["iptables", "-t", "nat", "-D", "POSTROUTING",
             "-s", subnet, "-o", tun_iface, "-j", "MASQUERADE"])

    if not quiet:
        ok(f"Routing removed untuk {iface}")
    return True


def setup_routing_persistent(iface: str, cfg: dict) -> bool:
    """Create systemd service to setup routing on boot."""
    require_root()
    subnet = get_subnet(iface)
    if not subnet:
        return False

    table_id = _get_route_table_id(iface)

    script_content = f"""#!/bin/bash
# Policy routing for {iface} → sing-box
sleep 3
# Local subnet rule FIRST (higher priority = lower number)
ip rule del to {subnet} 2>/dev/null
ip rule add to {subnet} lookup main pref 8998
# Then policy routing for outbound traffic
ip rule del from {subnet} 2>/dev/null
ip rule add from {subnet} lookup {table_id} pref 8999
# MASQUERADE for return traffic
for tun in singtun0 singtun1 tun0; do
  iptables -t nat -A POSTROUTING -s {subnet} -o $tun -j MASQUERADE 2>/dev/null
done
# Cleanup TProxy chains
iptables -t mangle -D PREROUTING -i {iface} -j SING_BOX 2>/dev/null
iptables -t mangle -F SING_BOX 2>/dev/null
iptables -t mangle -X SING_BOX 2>/dev/null
echo "Policy routing applied for {iface}"
"""

    script_path = Path(f"/usr/local/bin/fix-nat-{iface}.sh")
    write_file(script_path, script_content, mode=0o755)

    service_content = f"""[Unit]
Description=Policy routing for {iface} (sing-box mode)
After=network-online.target sing-box.service
Wants=network-online.target

[Service]
Type=oneshot
ExecStart={script_path}
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
"""
    service_path = Path(f"/etc/systemd/system/fix-nat-{iface}.service")
    write_file(service_path, service_content)

    daemon_reload()
    enable_service(f"fix-nat-{iface}")
    ok(f"Persistent routing: {service_path}")
    return True


# ── DHCP via AdGuard Home ────────────────────────────────────────────

def setup_dhcp(iface: str, cfg: dict) -> bool:
    """Setup AdGuard Home DHCP for interface (direct YAML, bypass API validation)."""
    require_root()
    import yaml

    ip_addr = get_ip(iface)
    if not ip_addr:
        fail(f"IP tidak ditemukan untuk {iface}")
        return False

    if not ADGUARD_CFG.exists():
        fail(f"AdGuard Home config tidak ditemukan: {ADGUARD_CFG}")
        fail("Install: curl -s -S -L https://raw.githubusercontent.com/AdguardTeam/AdGuardHome/master/scripts/install.sh | sh")
        return False

    nat_cfg = cfg.get("nat", {})
    base = ".".join(ip_addr.split(".")[:3])
    range_start = nat_cfg.get("dhcp_range_start", 100)
    range_end = nat_cfg.get("dhcp_range_end", 200)
    lease = nat_cfg.get("dhcp_lease", "12h")
    lease_secs = _lease_to_seconds(lease)

    with open(ADGUARD_CFG) as f:
        adg = yaml.safe_load(f)

    adg["dhcp"]["enabled"] = True
    adg["dhcp"]["interface_name"] = iface
    adg["dhcp"]["local_domain_name"] = "lan"
    adg["dhcp"]["dhcpv4"]["gateway_ip"] = ip_addr
    adg["dhcp"]["dhcpv4"]["subnet_mask"] = "255.255.255.0"
    adg["dhcp"]["dhcpv4"]["range_start"] = f"{base}.{range_start}"
    adg["dhcp"]["dhcpv4"]["range_end"] = f"{base}.{range_end}"
    adg["dhcp"]["dhcpv4"]["lease_duration"] = lease_secs
    adg["dns"]["upstream_dns"] = ["1.1.1.1", "8.8.8.8"]
    adg["dns"]["bootstrap_dns"] = ["1.1.1.1:53", "8.8.8.8:53"]

    with open(ADGUARD_CFG, "w") as f:
        yaml.dump(adg, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    ok(f"AdGuard DHCP: {base}.{range_start}-{range_end}")

    run([str(ADGUARD_BIN), "-s", "restart"])
    import time; time.sleep(3)

    dhcp_ok = run(["bash", "-c", "ss -ulnp | grep -q 'AdGuardHome.*:67'"]).returncode == 0
    if dhcp_ok:
        ok("AdGuard DHCP running (port 67)")
    else:
        warn("AdGuard DHCP port 67 tidak terdeteksi")

    return True


def remove_dhcp(iface: str) -> bool:
    """Disable DHCP in AdGuard Home."""
    require_root()
    import yaml

    if not ADGUARD_CFG.exists():
        return False

    with open(ADGUARD_CFG) as f:
        adg = yaml.safe_load(f)

    adg["dhcp"]["enabled"] = False
    adg["dhcp"]["interface_name"] = ""

    with open(ADGUARD_CFG, "w") as f:
        yaml.dump(adg, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    run([str(ADGUARD_BIN), "-s", "restart"])
    ok(f"AdGuard DHCP disabled untuk {iface}")
    return True


def _lease_to_seconds(lease: str) -> int:
    lease = lease.strip().lower()
    if lease.endswith("h"):
        return int(lease[:-1]) * 3600
    elif lease.endswith("m"):
        return int(lease[:-1]) * 60
    elif lease.endswith("d"):
        return int(lease[:-1]) * 86400
    return int(lease)


# ── Public API ────────────────────────────────────────────────────────

def setup_interface(iface: str, cfg: dict) -> bool:
    """Full NAT setup for one interface: routing + DHCP."""
    require_root()

    cidr = get_interface_cidr(iface)
    if not cidr:
        fail(f"Interface {iface} tidak ditemukan atau tidak punya IP")
        return False
    info(f"{iface}: {cidr}")

    # Policy routing + MASQUERADE
    setup_routing(iface, cfg)
    setup_routing_persistent(iface, cfg)

    # DHCP via AdGuard Home
    if cfg.get("nat", {}).get("dhcp_enabled", True):
        setup_dhcp(iface, cfg)

    # Update config
    from .config import add_nat_interface, save_config
    add_nat_interface(cfg, iface)
    save_config(cfg)

    header(f"✅ {iface} siap — semua traffic client lewat sing-box")
    return True


def remove_interface(iface: str, cfg: dict) -> bool:
    """Remove all NAT config for one interface."""
    require_root()
    header(f"Removing NAT untuk {iface}")

    flush_routing(iface, cfg)
    remove_dhcp(iface)

    svc = Path(f"/etc/systemd/system/fix-nat-{iface}.service")
    if svc.exists():
        svc.unlink()
        daemon_reload()

    from .config import remove_nat_interface, save_config
    remove_nat_interface(cfg, iface)
    save_config(cfg)

    ok(f"{iface} removed dari NAT config")
    return True


def status(cfg: dict) -> list[dict]:
    """Return status of all NAT interfaces."""
    from .utils import run as _run
    results = []
    for iface in cfg.get("nat", {}).get("interfaces", []):
        ip_addr = get_ip(iface)
        subnet = get_subnet(iface)

        # Check ip rule
        rule_check = _run(["ip", "rule", "list", "from", subnet or ""])
        routing_active = subnet and subnet.split("/")[0] in rule_check.stdout

        # Check MASQUERADE
        nat_check = _run(["iptables", "-t", "nat", "-L", "POSTROUTING", "-n"])
        masq_active = bool(nat_check.stdout.count(subnet or "NONE"))

        # Check DHCP
        adguard_ok = ADGUARD_CFG.exists()
        dhcp_active = False
        if adguard_ok:
            import yaml
            try:
                with open(ADGUARD_CFG) as f:
                    adg = yaml.safe_load(f)
                dhcp_active = adg.get("dhcp", {}).get("enabled", False)
            except Exception:
                pass

        results.append({
            "interface": iface,
            "ip": ip_addr,
            "routing_active": routing_active or masq_active,
            "dhcp_active": dhcp_active,
            "dhcp_backend": "AdGuard Home",
        })
    return results


def doctor(cfg: dict) -> list[str]:
    """Diagnose NAT issues."""
    problems = []

    for iface in cfg.get("nat", {}).get("interfaces", []):
        if not get_ip(iface):
            problems.append(f"{iface}: tidak punya IP")

    if not ADGUARD_CFG.exists():
        problems.append("AdGuard Home tidak terinstall")
    elif not ADGUARD_BIN.exists():
        problems.append("AdGuard Home binary tidak ditemukan")

    fwd = read_file(Path("/proc/sys/net/ipv4/ip_forward"))
    if fwd and fwd.strip() != "1":
        problems.append("IP forwarding belum aktif")

    return problems
