"""CLI: command dispatcher for singbox-vpn."""

import sys
from .utils import fail, header, info, ok, warn, require_root


def main():
    """Main CLI entry point."""
    args = sys.argv[1:]

    if not args:
        _usage()
        return

    cmd = args[0]

    # ── Top-level commands ─────────────────────────────────────────
    if cmd == "setup":
        _cmd_setup(args[1:])
    elif cmd == "warp":
        _cmd_warp(args[1:])
    elif cmd == "proxy":
        _cmd_proxy(args[1:])
    elif cmd == "nat":
        _cmd_nat(args[1:])
    elif cmd == "rule":
        _cmd_rule(args[1:])
    elif cmd == "status":
        from .status import show_status
        show_status()
    elif cmd == "doctor":
        from .doctor import run_doctor
        run_doctor()
    elif cmd in ("help", "--help", "-h"):
        _usage()
    elif cmd == "--version":
        from . import __version__
        print(f"singbox-vpn {__version__}")
    else:
        fail(f"Unknown command: {cmd}")
        _usage()
        sys.exit(1)


def _usage():
    print("""
singbox-vpn — Auto WARP + Free Proxy + NAT manager for sing-box

USAGE:
    singbox-vpn <command> [subcommand] [options]

COMMANDS:
    setup                           Full setup (WARP + sing-box + NAT)
    warp setup|remove|status        Manage WARP WireGuard endpoints
    proxy fetch|status              Manage free proxy pool
    nat add|remove|status|list      Manage NAT/TProxy per-interface
    rule add|remove|list|apply      Manage route rules
    status                          Show system status dashboard
    doctor                          Run health check diagnostics

EXAMPLES:
    singbox-vpn setup                       # Full setup
    singbox-vpn warp setup                  # Register 2 WARP endpoints
    singbox-vpn proxy fetch                 # Fetch live proxies from GitHub
    singbox-vpn nat add eth2                # Add NAT for eth2 (TProxy + DHCP)
    singbox-vpn nat add eth3                # Add NAT for eth3
    singbox-vpn rule add --domain .netflix.com --outbound WARP
    singbox-vpn rule add --keyword gambling --outbound BLOCK
    singbox-vpn rule add --ip 10.0.0.0/8 --outbound DIRECT
    singbox-vpn rule remove 3
    singbox-vpn rule list
    singbox-vpn rule apply                  # Re-deploy config with rules
    singbox-vpn status
    singbox-vpn doctor
""")


# ── setup (full) ──────────────────────────────────────────────────────

def _cmd_setup(args):
    require_root()
    from .config import load_config, save_config
    from . import warp, singbox, nat, proxy

    cfg = load_config()

    header("═══ Full Setup ═══")

    # 1. WARP
    if not warp.setup(cfg):
        fail("WARP setup gagal")
        sys.exit(1)

    # 2. Deploy sing-box config
    if not singbox.deploy_config(cfg):
        fail("sing-box deploy gagal")
        sys.exit(1)

    # 3. Install service
    singbox.install_service()

    # 4. Fetch proxies
    proxy.fetch_and_update(cfg)

    # 5. NAT for configured interfaces
    for iface in nat.get_nat_interfaces(cfg):
        nat.setup_interface(iface, cfg)

    # 6. Restart
    singbox.restart()

    save_config(cfg)
    header("✅ Setup selesai!")
    info("Jalankan 'singbox-vpn status' untuk melihat status")


# ── warp ──────────────────────────────────────────────────────────────

def _cmd_warp(args):
    from .config import load_config, save_config
    from . import warp
    cfg = load_config()

    if not args:
        print("Usage: singbox-vpn warp setup|remove|status")
        return

    sub = args[0]
    if sub == "setup":
        require_root()
        if warp.setup(cfg):
            save_config(cfg)
    elif sub == "remove":
        require_root()
        if warp.remove(cfg):
            save_config(cfg)
    elif sub == "status":
        from .status import _print_kv
        for ep in warp.status(cfg):
            _print_kv(ep["name"], f"{'UP' if ep['up'] else 'DOWN'} — {ep['addresses']}")
    else:
        fail(f"Unknown warp subcommand: {sub}")


# ── proxy ─────────────────────────────────────────────────────────────

def _cmd_proxy(args):
    from .config import load_config
    from . import proxy
    cfg = load_config()

    if not args:
        print("Usage: singbox-vpn proxy fetch|status")
        return

    sub = args[0]
    if sub == "fetch":
        require_root()
        proxy.fetch_and_update(cfg)
    elif sub == "status":
        ps = proxy.status(cfg)
        info(f"Total: {ps['total']} proxies")
        for group, tags in sorted(ps["groups"].items()):
            print(f"    {group}: {len(tags)}")
    else:
        fail(f"Unknown proxy subcommand: {sub}")


# ── nat ───────────────────────────────────────────────────────────────

def _cmd_nat(args):
    from .config import load_config, save_config, get_nat_interfaces
    from . import nat
    cfg = load_config()

    if not args:
        print("Usage: singbox-vpn nat add|remove|status|list <interface>")
        return

    sub = args[0]

    if sub == "add":
        require_root()
        if len(args) < 2:
            fail("Usage: singbox-vpn nat add <interface>")
            return
        iface = args[1]
        nat.setup_interface(iface, cfg)
        save_config(cfg)

    elif sub == "remove":
        require_root()
        if len(args) < 2:
            fail("Usage: singbox-vpn nat remove <interface>")
            return
        iface = args[1]
        nat.remove_interface(iface, cfg)
        save_config(cfg)

    elif sub == "status":
        for ns in nat.status(cfg):
            tproxy = "OK" if ns["tproxy_active"] else "OFF"
            dhcp = "OK" if ns["dhcp_active"] else "OFF"
            print(f"  {ns['interface']:12s} {ns['ip']:16s} TProxy: {tproxy}  DHCP: {dhcp}")

    elif sub == "list":
        ifaces = get_nat_interfaces(cfg)
        if ifaces:
            for i in ifaces:
                print(f"  {i}")
        else:
            info("Tidak ada interface NAT dikonfigurasi")

    else:
        fail(f"Unknown nat subcommand: {sub}")


# ── rule ──────────────────────────────────────────────────────────────

def _cmd_rule(args):
    from .config import load_config
    from . import singbox

    if not args:
        _rule_usage()
        return

    sub = args[0]

    if sub == "add":
        _rule_add(args[1:])

    elif sub == "remove":
        if len(args) < 2:
            fail("Usage: singbox-vpn rule remove <index>")
            return
        try:
            idx = int(args[1])
        except ValueError:
            fail(f"Index harus angka: {args[1]}")
            return
        singbox.remove_rule(idx)

    elif sub == "list":
        rules = singbox.list_rules()
        if not rules:
            info("Tidak ada custom rules")
            return
        print(f"\n  {len(rules)} custom rules:")
        for i, r in enumerate(rules, 1):
            print(f"    {i}. {singbox._describe_rule(r)}")
        print()

    elif sub == "apply":
        require_root()
        cfg = load_config()
        if not singbox.deploy_config(cfg):
            fail("Deploy gagal")
            return
        singbox.restart()
        ok("Config deployed + sing-box restarted")

    else:
        fail(f"Unknown rule subcommand: {sub}")


def _rule_add(args):
    """Parse rule flags and add."""
    from . import singbox

    rule = {}
    outbound = None
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--domain" and i + 1 < len(args):
            rule.setdefault("domain_suffix", []).append(args[i + 1]); i += 2
        elif a == "--keyword" and i + 1 < len(args):
            rule.setdefault("domain_keyword", []).append(args[i + 1]); i += 2
        elif a == "--ip" and i + 1 < len(args):
            rule.setdefault("ip_cidr", []).append(args[i + 1]); i += 2
        elif a == "--port" and i + 1 < len(args):
            rule["port"] = int(args[i + 1]); i += 2
        elif a == "--protocol" and i + 1 < len(args):
            rule["protocol"] = args[i + 1]; i += 2
        elif a == "--network" and i + 1 < len(args):
            rule["network"] = args[i + 1]; i += 2
        elif a == "--outbound" and i + 1 < len(args):
            outbound = args[i + 1]; i += 2
        elif a == "--inbound" and i + 1 < len(args):
            rule.setdefault("inbound", []).append(args[i + 1]); i += 2
        else:
            fail(f"Unknown flag: {a}")
            _rule_usage()
            return

    if not outbound:
        fail("--outbound wajib diisi")
        return

    rule["outbound"] = outbound
    singbox.add_rule(rule)


def _rule_usage():
    print("""
Usage: singbox-vpn rule <subcommand> [options]

SUBCOMMANDS:
    add     Add a route rule
    remove  Remove a rule by index
    list    List all custom rules
    apply   Re-deploy config with current rules

RULE FLAGS (for add):
    --domain <suffix>       Match domain suffix (e.g. .netflix.com)
    --keyword <word>        Match domain keyword (e.g. gambling)
    --ip <cidr>             Match IP CIDR (e.g. 10.0.0.0/8)
    --port <number>         Match port number
    --protocol <proto>      Match protocol (dns, tls, http)
    --network <type>        Match network (tcp, udp)
    --inbound <tag>         Match inbound tag
    --outbound <tag>        Target outbound (REQUIRED)

EXAMPLES:
    singbox-vpn rule add --domain .netflix.com --outbound WARP
    singbox-vpn rule add --keyword gambling --outbound BLOCK
    singbox-vpn rule add --ip 10.0.0.0/8 --outbound DIRECT
    singbox-vpn rule add --port 443 --network tcp --outbound WARP
    singbox-vpn rule add --domain .openai.com --outbound OPENAI
    singbox-vpn rule remove 3
    singbox-vpn rule list
    singbox-vpn rule apply
""")
