"""Status dashboard: overview of all components."""

from .utils import (
    service_running, SINGBOX_CFG, read_json, header, ok, fail, warn, info, dim, divider, C,
)
from .config import load_config


def show_status():
    """Print full system status dashboard."""
    cfg = load_config()

    header("═══ singbox-vpn Status ═══")

    # ── sing-box ───────────────────────────────────────────────────
    divider()
    print(f"  {C.BOLD}sing-box{C.RESET}")
    from . import singbox
    sb = singbox.status()
    _print_kv("Running", sb["running"])
    _print_kv("Config", sb["config_exists"])
    _print_kv("Endpoints", sb["endpoints"])
    _print_kv("Inbounds", sb["inbounds"])
    _print_kv("Outbounds", sb["outbounds"])
    _print_kv("Route Rules", sb["route_rules"])
    _print_kv("Free Proxies", sb["free_proxies"])

    # ── WARP ───────────────────────────────────────────────────────
    divider()
    print(f"  {C.BOLD}WARP Endpoints{C.RESET}")
    from . import warp
    for ep in warp.status(cfg):
        status_icon = f"{C.GREEN}UP{C.RESET}" if ep["up"] else f"{C.RED}DOWN{C.RESET}"
        addrs = ep["addresses"]
        addr_str = addrs[0] if addrs else "N/A"
        print(f"  {ep['name']:12s} {status_icon}  {addr_str}")

    # ── NAT interfaces ────────────────────────────────────────────
    divider()
    print(f"  {C.BOLD}NAT Interfaces{C.RESET}")
    from . import nat
    nat_status = nat.status(cfg)
    if not nat_status:
        dim("Tidak ada interface NAT dikonfigurasi")
    for ns in nat_status:
        tproxy = f"{C.GREEN}OK{C.RESET}" if ns.get("routing_active", ns.get("tproxy_active")) else f"{C.RED}OFF{C.RESET}"
        dhcp = f"{C.GREEN}OK{C.RESET}" if ns["dhcp_active"] else f"{C.DIM}OFF{C.RESET}"
        print(f"  {ns['interface']:12s} {ns['ip']:16s} TProxy: {tproxy}  DHCP: {dhcp}")

    # ── Proxy pool ────────────────────────────────────────────────
    divider()
    print(f"  {C.BOLD}Proxy Pool{C.RESET}")
    from . import proxy
    ps = proxy.status(cfg)
    _print_kv("Total", ps["total"])
    if ps["groups"]:
        for group, tags in sorted(ps["groups"].items()):
            print(f"    {group:16s} {len(tags)} proxies")
    if ps["state"].get("last_generated_at"):
        _print_kv("Last Update", ps["state"]["last_generated_at"])

    # ── DHCP ───────────────────────────────────────────────────────
    divider()
    print(f"  {C.BOLD}DHCP (AdGuard Home){C.RESET}")
    from .utils import ADGUARD_CFG, ADGUARD_BIN
    adguard_running = service_running("AdGuardHome") or run(["bash", "-c", f"{ADGUARD_BIN} -s status 2>&1 | grep -q running"]).returncode == 0
    _print_kv("AdGuard Home", adguard_running)
    
    # Show DHCP config from AdGuard
    if ADGUARD_CFG.exists():
        import yaml
        try:
            with open(ADGUARD_CFG) as f:
                adg = yaml.safe_load(f)
            dhcp = adg.get("dhcp", {})
            if dhcp.get("enabled"):
                v4 = dhcp.get("dhcpv4", {})
                info(f"Interface: {dhcp.get('interface_name', '?')}")
                info(f"Range: {v4.get('range_start', '?')} - {v4.get('range_end', '?')}")
                info(f"Gateway: {v4.get('gateway_ip', '?')}")
                info(f"Lease: {v4.get('lease_duration', '?')}s")
            else:
                dim("DHCP disabled")
        except Exception:
            warn("Gagal baca AdGuard config")
    
    # Show DHCP leases (AdGuard stores in data/leases.json)
    from pathlib import Path
    lease_file = Path("/opt/AdGuardHome/data/leases.json")
    if lease_file.exists():
        import json
        try:
            leases = json.loads(lease_file.read_text())
            if leases:
                print(f"    {C.DIM}Connected clients:{C.RESET}")
                for lease in leases:
                    ip = lease.get("ip", "?")
                    mac = lease.get("mac", "?")
                    hostname = lease.get("hostname", "?")
                    print(f"      {ip:16s} {mac:18s} {hostname}")
        except Exception:
            pass
    
    print()


def _print_kv(key, value):
    if isinstance(value, bool):
        icon = f"{C.GREEN}✓{C.RESET}" if value else f"{C.RED}✗{C.RESET}"
        print(f"  {key:16s} {icon}")
    else:
        print(f"  {key:16s} {value}")
