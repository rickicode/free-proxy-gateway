"""Doctor: comprehensive health check diagnostics."""

from .utils import (
    require_root, service_running, SINGBOX_BIN, SINGBOX_CFG,
    read_json, run, require_cmd, ADGUARD_CFG, ADGUARD_BIN,
    header, ok, fail, warn, info, dim, divider, C,
)
from .config import load_config


def run_doctor():
    """Run all diagnostics and print report."""
    cfg = load_config()
    all_problems = []

    header("═══ singbox-vpn Doctor ═══")

    # ── System prerequisites ───────────────────────────────────────
    divider()
    print(f"  {C.BOLD}System Prerequisites{C.RESET}")

    checks = [
        ("sing-box binary", SINGBOX_BIN.exists()),
        ("wireguard-tools", require_cmd("wg")),
        ("iptables", require_cmd("iptables")),
        ("ip", require_cmd("ip")),
        ("AdGuard Home", ADGUARD_CFG.exists()),
    ]
    for name, ok_status in checks:
        if ok_status:
            ok(name)
        else:
            fail(name)
            all_problems.append(f"{name} tidak tersedia")

    # ── IP Forwarding ──────────────────────────────────────────────
    fwd = run(["sysctl", "-n", "net.ipv4.ip_forward"]).stdout.strip()
    if fwd == "1":
        ok("IP forwarding aktif")
    else:
        fail(f"IP forwarding: {fwd} (harus 1)")
        all_problems.append("IP forwarding belum aktif")

    # ── sing-box ───────────────────────────────────────────────────
    divider()
    print(f"  {C.BOLD}sing-box{C.RESET}")
    from . import singbox
    sb_problems = singbox.doctor()
    if sb_problems:
        for p in sb_problems:
            fail(p)
            all_problems.append(p)
    else:
        ok("sing-box sehat")

    # ── WARP ───────────────────────────────────────────────────────
    divider()
    print(f"  {C.BOLD}WARP{C.RESET}")
    from . import warp
    warp_problems = warp.doctor(cfg)
    if warp_problems:
        for p in warp_problems:
            fail(p)
            all_problems.append(p)
    else:
        ok("WARP sehat")

    # ── NAT ────────────────────────────────────────────────────────
    divider()
    print(f"  {C.BOLD}NAT / TProxy{C.RESET}")
    from . import nat
    nat_problems = nat.doctor(cfg)
    if nat_problems:
        for p in nat_problems:
            fail(p)
            all_problems.append(p)
    else:
        ok("NAT sehat")

    # ── Proxy ──────────────────────────────────────────────────────
    divider()
    print(f"  {C.BOLD}Proxy Pool{C.RESET}")
    from . import proxy
    proxy_problems = proxy.doctor(cfg)
    if proxy_problems:
        for p in proxy_problems:
            fail(p)
            all_problems.append(p)
    else:
        ok("Proxy pool sehat")

    # ── Route rules ────────────────────────────────────────────────
    divider()
    print(f"  {C.BOLD}Route Rules{C.RESET}")
    sb_cfg = read_json(SINGBOX_CFG)
    if sb_cfg:
        rules = sb_cfg.get("route", {}).get("rules", [])
        rule_sets = sb_cfg.get("route", {}).get("rule_set", [])
        info(f"{len(rules)} rules, {len(rule_sets)} rule sets")

        # Check key rules exist
        has_sniff = any(r.get("action") == "sniff" for r in rules)
        has_dns_hijack = any(r.get("action") == "hijack-dns" for r in rules)
        has_private = any(r.get("ip_is_private") for r in rules)

        if has_sniff:
            ok("sniff rule")
        else:
            fail("sniff rule tidak ada")
            all_problems.append("Missing sniff rule")

        if has_dns_hijack:
            ok("DNS hijack rule")
        else:
            fail("DNS hijack rule tidak ada")
            all_problems.append("Missing DNS hijack rule")

        if has_private:
            ok("Private IP bypass")
        else:
            warn("Private IP bypass tidak ada")

        # Check custom rules
        from .singbox import load_custom_rules
        custom = load_custom_rules()
        if custom:
            info(f"{len(custom)} custom rules")
    else:
        fail("Config tidak bisa dibaca")
        all_problems.append("sing-box config unreadable")

    # ── Connectivity tests ─────────────────────────────────────────
    divider()
    print(f"  {C.BOLD}Connectivity{C.RESET}")

    # Test clash API
    clash_ok = run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
                     "http://127.0.0.1:9090"]).stdout.strip()
    if clash_ok == "200":
        ok("Clash API reachable")
    else:
        warn(f"Clash API: HTTP {clash_ok}")

    # Test DNS
    if require_cmd("dig"):
        dns_ok = run(["dig", "+short", "+timeout=3", "@1.1.1.1", "google.com"]).stdout.strip()
        if dns_ok:
            ok(f"DNS resolve: {dns_ok.splitlines()[0]}")
        else:
            fail("DNS resolve gagal")
            all_problems.append("DNS resolution failed")
    else:
        dns_ok = run(["bash", "-c", "getent hosts google.com 2>/dev/null | head -1"]).stdout.strip()
        if dns_ok:
            ok(f"DNS resolve: {dns_ok.split()[0]}")
        else:
            warn("dig tidak tersedia, skip DNS test")

    # ── Summary ────────────────────────────────────────────────────
    divider()
    if all_problems:
        print(f"\n  {C.RED}{C.BOLD}Ditemukan {len(all_problems)} masalah:{C.RESET}")
        for i, p in enumerate(all_problems, 1):
            print(f"    {i}. {p}")
    else:
        print(f"\n  {C.GREEN}{C.BOLD}✓ Semua sehat!{C.RESET}")
    print()
