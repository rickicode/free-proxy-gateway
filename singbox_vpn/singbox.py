"""sing-box config generation + service control.

Generates full sing-box config matching server exactly, including:
- WireGuard endpoints (WARP)
- TProxy + Mixed inbounds
- Outbounds (DIRECT, WAN, WARP, free proxies, groups)
- Route rules (sniff, DNS hijack, domain routing, custom rules)
"""

import json
from pathlib import Path

from .utils import (
    run, require_root, SINGBOX_BIN, SINGBOX_CFG, SINGBOX_LOG, SINGBOX_UI,
    read_json, write_json, ensure_dir,
    ok, fail, info, warn, header, dim,
    service_running, service_enabled, enable_service, start_service,
    stop_service, restart_service,
)
from .config import get_wan_interfaces, load_config


# ── Rule management ───────────────────────────────────────────────────

RULES_FILE = Path("/etc/singbox-vpn/rules.json")


def load_custom_rules() -> list[dict]:
    """Load custom route rules from rules.json."""
    data = read_json(RULES_FILE)
    return data.get("rules", []) if data else []


def save_custom_rules(rules: list[dict]):
    """Save custom route rules."""
    write_json(RULES_FILE, {"rules": rules})


def add_rule(rule: dict):
    """Add a custom route rule."""
    rules = load_custom_rules()
    rules.append(rule)
    save_custom_rules(rules)
    ok(f"Rule ditambahkan: {_describe_rule(rule)}")


def remove_rule(index: int) -> bool:
    """Remove rule by index (1-based)."""
    rules = load_custom_rules()
    if index < 1 or index > len(rules):
        fail(f"Index {index} tidak valid (1-{len(rules)})")
        return False
    removed = rules.pop(index - 1)
    save_custom_rules(rules)
    ok(f"Rule dihapus: {_describe_rule(removed)}")
    return True


def list_rules() -> list[dict]:
    """List all custom rules."""
    return load_custom_rules()


def _describe_rule(rule: dict) -> str:
    """Human-readable description of a rule."""
    parts = []
    if "domain_suffix" in rule:
        parts.append(f"domain={rule['domain_suffix']}")
    if "domain_keyword" in rule:
        parts.append(f"keyword={rule['domain_keyword']}")
    if "ip_cidr" in rule:
        parts.append(f"ip={rule['ip_cidr']}")
    if "protocol" in rule:
        parts.append(f"proto={rule['protocol']}")
    if "network" in rule:
        parts.append(f"net={rule['network']}")
    if "port" in rule:
        parts.append(f"port={rule['port']}")
    if "inbound" in rule:
        parts.append(f"inbound={rule['inbound']}")
    ob = rule.get("outbound", "?")
    return f"{' ∧ '.join(parts)} → {ob}" if parts else f"→ {ob}"


# ── Config generation ─────────────────────────────────────────────────

def generate_config(cfg: dict, proxy_outbounds: list[dict] | None = None) -> dict:
    """Generate full sing-box config matching server exactly."""
    scfg = cfg.get("singbox", {})
    wans = get_wan_interfaces(cfg)
    warp_ifaces = cfg.get("warp", {}).get("interfaces", ["singtun0", "singtun1"])
    exclude_tun = scfg.get("exclude_from_tun", []) + warp_ifaces
    extra_ports = scfg.get("extra_mixed_ports", [1010, 1011, 1012])
    proxy_aware = cfg.get("proxy", {}).get("proxy_aware_selectors", [])
    target_countries = cfg.get("proxy", {}).get("target_countries", [])
    dns_server = scfg.get("dns_server", "1.1.1.1")

    # ── Endpoints (WARP) ───────────────────────────────────────────
    endpoints = []
    for i, name in enumerate(warp_ifaces):
        tag = "warp-ep" if i == 0 else f"warp{i+1}-ep"
        ep = read_json(SINGBOX_CFG)
        if ep:
            existing_ep = next((e for e in ep.get("endpoints", []) if e.get("name") == name), None)
            if existing_ep:
                endpoints.append(existing_ep)

    # ── Inbounds ───────────────────────────────────────────────────
    inbounds = [
        {
            "type": "tun",
            "tag": "tun-in",
            "address": ["172.19.0.1/30"],
            "auto_route": True,
            "strict_route": True,
            "stack": "system",
            "exclude_interface": exclude_tun,
        },
        {
            "type": "tproxy",
            "tag": "tproxy-in",
            "listen": "0.0.0.0",
            "listen_port": cfg.get("nat", {}).get("tproxy_port", 7893),
            "network": "tcp",
        },
        {
            "type": "tproxy",
            "tag": "tproxy-udp-in",
            "listen": "0.0.0.0",
            "listen_port": cfg.get("nat", {}).get("tproxy_port", 7893),
            "network": "udp",
        },
        {
            "type": "mixed",
            "tag": "mixed-in",
            "listen": "0.0.0.0",
            "listen_port": scfg.get("mixed_port", 7890),
        },
    ]
    for port in extra_ports:
        inbounds.append({
            "type": "mixed",
            "tag": f"mixed-{port}",
            "listen": "0.0.0.0",
            "listen_port": port,
        })

    # ── Outbounds ──────────────────────────────────────────────────
    outbounds = [
        {"type": "direct", "tag": "DIRECT"},
    ]

    # WAN outbounds
    for i, wan in enumerate(wans):
        outbounds.append({
            "type": "direct",
            "tag": f"WAN{i+1}",
            "bind_interface": wan,
        })

    if len(wans) > 1:
        outbounds.append({
            "type": "urltest",
            "tag": "WAN-AUTO",
            "outbounds": [f"WAN{i+1}" for i in range(len(wans))],
            "url": "http://cp.cloudflare.com/generate_204",
            "interval": "30s",
            "tolerance": 50,
        })

    outbounds.append({"type": "block", "tag": "BLOCK"})

    # WARP outbounds
    for i, name in enumerate(warp_ifaces):
        outbounds.append({
            "type": "direct",
            "tag": f"WARP{i+1}",
            "bind_interface": name,
        })
    outbounds.append({
        "type": "urltest",
        "tag": "WARP",
        "outbounds": [f"WARP{i+1}" for i in range(len(warp_ifaces))],
        "url": "http://cp.cloudflare.com/generate_204",
        "interval": "3m",
        "tolerance": 50,
    })

    # Free proxy outbounds (from collector)
    if proxy_outbounds:
        outbounds.extend(proxy_outbounds)

    # ── Selectors ──────────────────────────────────────────────────
    all_proxy_groups = [f"PROXY-{cc}" for cc in target_countries]
    all_proxy_groups.append("PROXY-FREE")
    selector_options = (
        ["DIRECT", "WAN", "WAN-AUTO"] +
        [f"WAN{i+1}" for i in range(len(wans))] +
        ["WARP", "WARP1", "WARP2"] +
        sorted(all_proxy_groups)
    )

    # Per-port selectors with different defaults
    port_defaults = {}
    for port in extra_ports:
        if port == 1010:
            port_defaults[port] = "WARP"
        elif port == 1011:
            port_defaults[port] = "WARP2"
        elif port == 1012:
            port_defaults[port] = "WARP1"
        else:
            port_defaults[port] = "WARP"

    managed_selectors = {
        "GLOBAL": "DIRECT",
        "GOOGLE": "DIRECT",
        "IPCHECK": "WARP",
        "OPENAI": "WARP",
        "WAN": "WAN1",
    }
    for port in extra_ports:
        managed_selectors[f"PORT-{port}"] = port_defaults.get(port, "WARP")

    for tag, default in managed_selectors.items():
        if tag == "WAN":
            options = [f"WAN{i+1}" for i in range(len(wans))]
        else:
            options = list(selector_options)
        outbounds.append({
            "type": "selector",
            "tag": tag,
            "outbounds": options,
            "default": default,
        })

    # Per-country selectors
    for cc in target_countries:
        outbounds.append({
            "type": "selector",
            "tag": f"PROXY-{cc}",
            "outbounds": [],  # populated by proxy collector
            "default": "",
        })

    # ── Route rules ────────────────────────────────────────────────
    route = _build_route(cfg)

    # ── Final config ───────────────────────────────────────────────
    return {
        "log": {
            "level": scfg.get("log_level", "info"),
            "output": str(SINGBOX_LOG),
            "timestamp": True,
        },
        "dns": {
            "servers": [{"type": "udp", "tag": "local", "server": dns_server}],
            "strategy": "ipv4_only",
        },
        "experimental": {
            "clash_api": {
                "external_controller": f"0.0.0.0:{scfg.get('clash_api_port', 9090)}",
                "external_ui": scfg.get("clash_api_ui", str(SINGBOX_UI)),
                "secret": scfg.get("clash_api_secret", ""),
            }
        },
        "endpoints": endpoints,
        "inbounds": inbounds,
        "outbounds": outbounds,
        "route": route,
    }


def _build_route(cfg: dict) -> dict:
    """Build route section with built-in + custom rules."""
    rcfg = cfg.get("route", {})
    extra_ports = cfg.get("singbox", {}).get("extra_mixed_ports", [1010, 1011, 1012])

    # ── Rule sets ──────────────────────────────────────────────────
    rule_sets = []
    for rs in rcfg.get("rule_sets", []):
        entry = {
            "type": rs.get("type", "remote"),
            "tag": rs["tag"],
            "format": "binary",
            "download_detour": "DIRECT",
            "update_interval": "24h",
        }
        if rs["type"] == "remote":
            entry["url"] = rs["url"]
        elif rs["type"] == "local":
            entry["path"] = rs.get("path", f"/opt/rules/compiled/{rs['tag']}.srs")
        rule_sets.append(entry)

    # ── Built-in rules ────────────────────────────────────────────
    rules = [
        {"action": "sniff"},
        {"protocol": "dns", "action": "hijack-dns"},
        # Tailscale bypass
        {"domain_suffix": ["tailscale.com", "tailscale.io", "ts.net"], "outbound": "DIRECT"},
        {"ip_cidr": ["100.64.0.0/10"], "outbound": "DIRECT"},
        {"network": "udp", "port": 41641, "outbound": "DIRECT"},
        # Private IPs → DIRECT
        {"ip_is_private": True, "outbound": "DIRECT"},
    ]

    # Per-port inbound routing
    for port in extra_ports:
        rules.append({
            "inbound": [f"mixed-{port}"],
            "outbound": f"PORT-{port}",
        })

    # Domain-based routing from config
    for tags_str, outbound in rcfg.get("domain_outbound_map", {}).items():
        tags = [t.strip() for t in tags_str.split(",")]
        rules.append({
            "rule_set": tags,
            "outbound": outbound,
        })

    # Custom rules from rules.json
    custom = load_custom_rules()
    if custom:
        info(f"Loading {len(custom)} custom rules")
        rules.extend(custom)

    # Final
    rules.append({"outbound": "GLOBAL"})

    return {
        "auto_detect_interface": True,
        "rule_set": rule_sets,
        "rules": rules,
        "final": "GLOBAL",
    }


# ── Service control ───────────────────────────────────────────────────

def install_service() -> bool:
    """Install sing-box systemd service."""
    require_root()

    # Create singbox user if not exists
    run(["useradd", "--system", "--no-create-home", "--shell", "/usr/sbin/nologin", "singbox"])

    service_content = """[Unit]
Description=sing-box
After=network.target

[Service]
User=singbox
Group=singbox
AmbientCapabilities=CAP_NET_ADMIN CAP_NET_BIND_SERVICE
CapabilityBoundingSet=CAP_NET_ADMIN CAP_NET_BIND_SERVICE
ExecStart=/usr/local/bin/sing-box run -c /etc/sing-box/config.json
Restart=on-failure
RestartSec=5
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
"""
    from .utils import write_file
    write_file(Path("/etc/systemd/system/sing-box.service"), service_content)
    daemon_reload()
    enable_service("sing-box")
    ok("sing-box service installed")
    return True





def deploy_config(cfg: dict, proxy_outbounds: list[dict] | None = None) -> bool:
    """Generate and deploy sing-box config."""
    require_root()

    header("Deploying sing-box config")
    sb_cfg = generate_config(cfg, proxy_outbounds)
    write_json(SINGBOX_CFG, sb_cfg, indent=2)
    ok(f"Config written → {SINGBOX_CFG}")

    # Validate
    r = run([str(SINGBOX_BIN), "check", "-c", str(SINGBOX_CFG)])
    if r.returncode != 0:
        fail(f"Config error: {r.stderr.strip()}")
        return False
    ok("Config valid")

    return True


def restart() -> bool:
    """Restart sing-box service."""
    require_root()
    restart_service("sing-box")
    import time; time.sleep(2)
    if service_running("sing-box"):
        ok("sing-box running")
        return True
    fail("sing-box gagal start")
    return False


def status() -> dict:
    """Return sing-box status."""
    from .utils import read_file as _rf
    sb_cfg = read_json(SINGBOX_CFG) or {}
    outbounds = sb_cfg.get("outbounds", [])
    endpoints = sb_cfg.get("endpoints", [])
    inbounds = sb_cfg.get("inbounds", [])
    rules = sb_cfg.get("route", {}).get("rules", [])

    return {
        "running": service_running("sing-box"),
        "config_exists": SINGBOX_CFG.exists(),
        "endpoints": len(endpoints),
        "inbounds": len(inbounds),
        "outbounds": len(outbounds),
        "route_rules": len(rules),
        "free_proxies": len([o for o in outbounds if o.get("tag", "").startswith("free-")]),
    }


def doctor() -> list[str]:
    """Diagnose sing-box issues."""
    problems = []
    if not SINGBOX_BIN.exists():
        problems.append(f"sing-box binary tidak ditemukan: {SINGBOX_BIN}")
    if not SINGBOX_CFG.exists():
        problems.append(f"sing-box config tidak ditemukan: {SINGBOX_CFG}")
    elif not service_running("sing-box"):
        problems.append("sing-box service tidak jalan")

    r = run([str(SINGBOX_BIN), "check", "-c", str(SINGBOX_CFG)])
    if r.returncode != 0:
        problems.append(f"Config error: {r.stderr.strip()[:100]}")

    return problems
