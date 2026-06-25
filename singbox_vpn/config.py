"""Config loading, saving, defaults — matches exact server setup."""

import yaml
from pathlib import Path
from .utils import CONFIG_DIR, CONFIG_FILE, ensure_dir, info, warn

# ── Default config (matches 192.168.90.78 exactly) ───────────────────
DEFAULT_CONFIG = {
    "warp": {
        "interfaces": ["singtun0", "singtun1"],
        "endpoint": "engage.cloudflareclient.com",
        "port": 2408,
        "public_key": "bmXOC+F1FxEMF9dyiK2H5/1SUtzH0JuVo51h2wPfgyo=",
        "mtu": 1280,
    },
    "proxy": {
        "github_raw": "https://raw.githubusercontent.com/rickicode/free-proxy-gateway/main/output/live-proxies.json",
        "max_free": 40,
        "clash_secret": "hijinet",
        "target_countries": ["US", "SG", "ID", "JP", "KR", "HK", "DE", "FR", "GB", "CA", "AU", "IN", "NL", "BR"],
        "proxy_aware_selectors": ["GLOBAL", "GOOGLE", "OPENAI", "IPCHECK", "PORT-1010", "PORT-1011", "PORT-1012"],
    },
    "nat": {
        "interfaces": [],           # e.g. ["eth2"] — auto-populated by `nat add`
        "tproxy_port": 7893,
        "tproxy_mark": "0x01",
        "dhcp_enabled": True,
        "dhcp_range_start": 100,
        "dhcp_range_end": 200,
        "dhcp_lease": "12h",
        "dhcp_backend": "adguard",
    },
    "singbox": {
        "log_level": "info",
        "log_file": "/var/log/sing-box.log",
        "mixed_port": 7890,
        "extra_mixed_ports": [1010, 1011, 1012],
        "clash_api_port": 9090,
        "clash_api_secret": "hijinet",
        "clash_api_ui": "/etc/sing-box/ui",
        "dns_server": "1.1.1.1",
        "wan_interfaces": [],       # auto-detected, e.g. ["eth0", "eth1"]
        "exclude_from_tun": ["singtun0", "singtun1"],
        "selector_defaults": {
            "GLOBAL": "DIRECT",
            "GOOGLE": "DIRECT",
            "OPENAI": "WARP",
            "IPCHECK": "WARP",
        },
    },
    "route": {
        "rule_sets": [
            {
                "tag": "community-speedtest",
                "type": "remote",
                "url": "https://raw.githubusercontent.com/MetaCubeX/meta-rules-dat/sing/geo/geosite/speedtest.srs",
            },
            {
                "tag": "community-openai",
                "type": "remote",
                "url": "https://raw.githubusercontent.com/MetaCubeX/meta-rules-dat/sing/geo/geosite/openai.srs",
            },
            {
                "tag": "community-anthropic",
                "type": "remote",
                "url": "https://raw.githubusercontent.com/MetaCubeX/meta-rules-dat/sing/geo/geosite/anthropic.srs",
            },
            {
                "tag": "community-google",
                "type": "remote",
                "url": "https://raw.githubusercontent.com/MetaCubeX/meta-rules-dat/sing/geo/geosite/google.srs",
            },
            {
                "tag": "community-google-play",
                "type": "remote",
                "url": "https://raw.githubusercontent.com/MetaCubeX/meta-rules-dat/sing/geo/geosite/google-play.srs",
            },
            {
                "tag": "community-youtube",
                "type": "remote",
                "url": "https://raw.githubusercontent.com/MetaCubeX/meta-rules-dat/sing/geo/geosite/youtube.srs",
            },
        ],
        "domain_outbound_map": {
            "community-openai,community-anthropic": "OPENAI",
            "community-google,community-google-play,community-youtube": "GOOGLE",
            "community-speedtest,local-ip-check": "IPCHECK",
        },
    },
}


def load_config() -> dict:
    """Load config from file, merge with defaults."""
    if not CONFIG_FILE.exists():
        return _deep_copy_dict(DEFAULT_CONFIG)
    with open(CONFIG_FILE) as f:
        user = yaml.safe_load(f) or {}
    return _deep_merge(DEFAULT_CONFIG, user)


def save_config(cfg: dict):
    """Save config to file."""
    ensure_dir(CONFIG_DIR)
    with open(CONFIG_FILE, "w") as f:
        yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    info(f"Config saved → {CONFIG_FILE}")


def _deep_merge(base: dict, override: dict) -> dict:
    result = base.copy()
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def _deep_copy_dict(d: dict) -> dict:
    import copy
    return copy.deepcopy(d)


# ── Accessors ─────────────────────────────────────────────────────────
def get_warp_interfaces(cfg: dict) -> list[str]:
    return cfg.get("warp", {}).get("interfaces", ["singtun0", "singtun1"])

def get_nat_interfaces(cfg: dict) -> list[str]:
    return cfg.get("nat", {}).get("interfaces", [])

def add_nat_interface(cfg: dict, iface: str) -> bool:
    nats = cfg["nat"]["interfaces"]
    if iface in nats:
        return False
    nats.append(iface)
    return True

def remove_nat_interface(cfg: dict, iface: str) -> bool:
    nats = cfg["nat"]["interfaces"]
    if iface not in nats:
        return False
    nats.remove(iface)
    return True

def get_wan_interfaces(cfg: dict) -> list[str]:
    """Get WAN interfaces — auto-detect if not set."""
    wans = cfg.get("singbox", {}).get("wan_interfaces", [])
    if wans:
        return wans
    # Auto-detect: interfaces with default route
    from .utils import run
    result = run(["ip", "route", "show", "default"])
    detected = []
    for line in result.stdout.strip().splitlines():
        parts = line.split()
        if "dev" in parts:
            idx = parts.index("dev") + 1
            if idx < len(parts):
                detected.append(parts[idx])
    return detected or ["eth0"]
