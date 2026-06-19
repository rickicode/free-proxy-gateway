"""WARP WireGuard setup via sing-box endpoints.

Generates sing-box WireGuard endpoint configs matching the server exactly.
No wg-quick — sing-box manages the tunnel natively.
"""

import json
import time
import urllib.request
import urllib.error
from pathlib import Path

from .utils import (
    run, run_ok, require_root, require_cmd, SINGBOX_CFG, read_json, write_json,
    ok, fail, info, warn, header, dim,
)

WARP_API     = "https://api.cloudflareclient.com/v0a2158/reg"
WARP_PUBKEY  = "bmXOC+F1FxEMF9dyiK2H5/1SUtzH0JuVo51h2wPfgyo="
WARP_EP      = "engage.cloudflareclient.com"
WARP_PORT    = 2408


def gen_keypair() -> tuple[str, str]:
    """Generate WireGuard keypair."""
    require_root()
    if not require_cmd("wg"):
        fail("wireguard-tools tidak terpasang. Install: apt install wireguard")
        raise SystemExit(1)
    priv = run(["wg", "genkey"], check=True).stdout.strip()
    pub  = run(["wg", "pubkey"], input=priv, check=True).stdout.strip()
    return priv, pub


def register_warp(pubkey: str) -> dict:
    """Register public key with Cloudflare WARP, return account info."""
    data = json.dumps({
        "key": pubkey,
        "install_id": "",
        "fcm_token": "",
        "tos": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
        "model": "Linux",
    }).encode()

    req = urllib.request.Request(
        WARP_API, data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.URLError as e:
        fail(f"WARP registration gagal: {e}")
        raise SystemExit(1)


def register_one() -> dict:
    """Register one WARP key, return {private_key, addresses, peer_endpoint}."""
    info("Generating WireGuard keys...")
    priv, pub = gen_keypair()

    info("Registering with Cloudflare WARP...")
    reg = register_warp(pub)

    config = reg.get("config", {})
    addrs  = config.get("interface", {}).get("addresses", {})
    peers  = config.get("peers", [{}])
    peer_host = peers[0].get("endpoint", {}).get("host", WARP_EP) if peers else WARP_EP

    return {
        "private_key": priv,
        "address_v4":  addrs.get("v4", ""),
        "address_v6":  addrs.get("v6", ""),
        "peer_endpoint": peer_host,
    }


def build_endpoint_dict(tag: str, name: str, warp_info: dict, cfg: dict) -> dict:
    """Build sing-box WireGuard endpoint dict (matches server config exactly)."""
    wcfg = cfg.get("warp", {})
    return {
        "type": "wireguard",
        "tag": tag,
        "system": True,
        "name": name,
        "mtu": wcfg.get("mtu", 1280),
        "address": [
            f"{warp_info['address_v4']}/32",
            f"{warp_info['address_v6']}/128",
        ],
        "private_key": warp_info["private_key"],
        "peers": [{
            "address": warp_info.get("peer_endpoint", wcfg.get("endpoint", WARP_EP)),
            "port": wcfg.get("port", WARP_PORT),
            "public_key": wcfg.get("public_key", WARP_PUBKEY),
            "allowed_ips": ["0.0.0.0/0", "::/0"],
            "persistent_keepalive_interval": 25,
        }],
    }


# ── Public API ────────────────────────────────────────────────────────

def setup(cfg: dict) -> bool:
    """Setup WARP endpoints: register keys, update sing-box config."""
    require_root()
    if not require_cmd("wg"):
        fail("wireguard-tools tidak terpasang")
        return False

    names = cfg.get("warp", {}).get("interfaces", ["singtun0", "singtun1"])
    header(f"WARP Setup — {len(names)} endpoints")

    # Load existing sing-box config
    sb_cfg = read_json(SINGBOX_CFG)
    if not sb_cfg:
        fail(f"sing-box config tidak ditemukan: {SINGBOX_CFG}")
        return False

    # Remove existing WARP endpoints
    sb_cfg["endpoints"] = [
        ep for ep in sb_cfg.get("endpoints", [])
        if ep.get("type") != "wireguard"
    ]

    # Register and add new endpoints
    for i, name in enumerate(names):
        tag = f"warp-ep" if i == 0 else f"warp{i+1}-ep"
        info(f"Registering {name} ({tag})...")
        warp_info = register_one()
        ep = build_endpoint_dict(tag, name, warp_info, cfg)
        sb_cfg["endpoints"].append(ep)
        ok(f"{name} — IPv4: {warp_info['address_v4']}, IPv6: {warp_info['address_v6'][:24]}...")

    # Update outbounds: remove old WARP outbounds, add new ones
    outbounds = sb_cfg.get("outbounds", [])
    outbounds = [o for o in outbounds if o.get("tag") not in ("WARP1", "WARP2", "WARP")]

    # Insert WARP direct outbounds after BLOCK
    warp_outbounds = []
    for i, name in enumerate(names):
        tag = f"WARP{i+1}"
        ep_tag = f"warp-ep" if i == 0 else f"warp{i+1}-ep"
        warp_outbounds.append({
            "type": "direct",
            "tag": tag,
            "bind_interface": name,
        })

    # WARP urltest group
    warp_group = {
        "type": "urltest",
        "tag": "WARP",
        "outbounds": [w["tag"] for w in warp_outbounds],
        "url": "http://cp.cloudflare.com/generate_204",
        "interval": "3m",
        "tolerance": 50,
    }

    # Insert after BLOCK
    block_idx = next((i for i, o in enumerate(outbounds) if o.get("tag") == "BLOCK"), len(outbounds))
    for j, wo in enumerate(warp_outbounds):
        outbounds.insert(block_idx + 1 + j, wo)
    outbounds.insert(block_idx + 1 + len(warp_outbounds), warp_group)

    sb_cfg["outbounds"] = outbounds

    # Update selectors to include WARP options
    _update_selectors_for_warp(sb_cfg)

    write_json(SINGBOX_CFG, sb_cfg)
    ok(f"sing-box config updated → {SINGBOX_CFG}")

    # Validate
    r = run([str(SINGBOX_BIN), "check", "-c", str(SINGBOX_CFG)])
    if r.returncode != 0:
        fail(f"Config error: {r.stderr.strip()}")
        return False
    ok("sing-box config valid")

    # Restart
    run(["systemctl", "restart", "sing-box"])
    info("sing-box restarting...")
    import time; time.sleep(2)
    from .utils import service_running
    if service_running("sing-box"):
        ok("sing-box running")
    else:
        fail("sing-box gagal start")
        return False

    return True


def _update_selectors_for_warp(sb_cfg: dict):
    """Add WARP options to all proxy-aware selectors."""
    from .config import DEFAULT_CONFIG
    proxy_aware = set(DEFAULT_CONFIG["proxy"]["proxy_aware_selectors"])
    warp_options = ["WARP", "WARP1", "WARP2"]

    for ob in sb_cfg.get("outbounds", []):
        if ob.get("type") == "selector" and ob.get("tag") in proxy_aware:
            existing = ob.get("outbounds", [])
            for wo in warp_options:
                if wo not in existing:
                    existing.append(wo)
            ob["outbounds"] = existing


def remove(cfg: dict) -> bool:
    """Remove WARP endpoints from sing-box config."""
    require_root()
    sb_cfg = read_json(SINGBOX_CFG)
    if not sb_cfg:
        fail("sing-box config tidak ditemukan")
        return False

    header("WARP Remove")

    # Remove endpoints
    before = len(sb_cfg.get("endpoints", []))
    sb_cfg["endpoints"] = [ep for ep in sb_cfg.get("endpoints", []) if ep.get("type") != "wireguard"]
    after = len(sb_cfg["endpoints"])
    ok(f"Removed {before - after} WireGuard endpoints")

    # Remove WARP outbounds
    for tag in ("WARP", "WARP1", "WARP2"):
        sb_cfg["outbounds"] = [o for o in sb_cfg["outbounds"] if o.get("tag") != tag]
    ok("Removed WARP outbounds")

    write_json(SINGBOX_CFG, sb_cfg)
    return True


def status(cfg: dict) -> list[dict]:
    """Return status of WARP endpoints."""
    sb_cfg = read_json(SINGBOX_CFG)
    if not sb_cfg:
        return []

    results = []
    for ep in sb_cfg.get("endpoints", []):
        if ep.get("type") != "wireguard":
            continue
        name = ep.get("name", ep.get("tag"))
        addrs = ep.get("address", [])
        results.append({
            "name": name,
            "tag": ep.get("tag"),
            "addresses": addrs,
        })

    # Check if interfaces are up
    from .utils import run
    for r in results:
        iface_check = run(["ip", "link", "show", r["name"]])
        r["up"] = iface_check.returncode == 0 and "UP" in iface_check.stdout

    return results


def doctor(cfg: dict) -> list[str]:
    """Diagnose WARP issues."""
    problems = []
    if not require_cmd("wg"):
        problems.append("wireguard-tools tidak terpasang")

    sb_cfg = read_json(SINGBOX_CFG)
    if not sb_cfg:
        problems.append("sing-box config tidak ditemukan")
        return problems

    warp_eps = [ep for ep in sb_cfg.get("endpoints", []) if ep.get("type") == "wireguard"]
    if len(warp_eps) == 0:
        problems.append("Tidak ada WARP endpoints di sing-box config")
    elif len(warp_eps) < 2:
        problems.append(f"Hanya {len(warp_eps)} WARP endpoint (idealnya 2)")

    for ep in warp_eps:
        name = ep.get("name", ep.get("tag"))
        if not ep.get("private_key"):
            problems.append(f"{name}: private_key kosong")

    return problems
