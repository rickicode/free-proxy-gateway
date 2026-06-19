"""Proxy management: fetch live proxies from GitHub, update sing-box config.

Replicates exact proxy-collector.py logic from the server.
"""

import json
import time
import urllib.request
import urllib.error
import random
from collections import OrderedDict, Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .utils import (
    run, require_root, SINGBOX_BIN, SINGBOX_CFG, STATE_FILE, LOG_FILE,
    read_json, write_json, GITHUB_RAW,
    ok, fail, info, warn, header, dim,
)


def fetch_github_proxies(github_raw: str) -> tuple[list[dict], str | None]:
    """Fetch live-proxies.json from GitHub. Return (proxies, generated_at)."""
    info(f"Fetching from GitHub...")
    try:
        req = urllib.request.Request(github_raw, headers={"User-Agent": "singbox-vpn/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        fail(f"Fetch gagal: {e}")
        return [], None

    proxies = data.get("proxies", [])
    generated_at = data.get("generated_at")
    info(f"Got {len(proxies)} proxies (generated: {generated_at})")
    return proxies, generated_at


def clash_delay(tag: str, secret: str, timeout_ms: int = 3000) -> int | None:
    """Query clash API for proxy delay. Returns ms or None."""
    try:
        url = f"http://127.0.0.1:9090/proxies/{tag}/delay?timeout={timeout_ms}&url=http://cp.cloudflare.com/generate_204"
        req = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {secret}",
        })
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            return data.get("delay")
    except Exception:
        return None


def keep_existing(sb_cfg: dict, secret: str) -> tuple[list[dict], set[str], dict[str, list[str]]]:
    """Keep existing free-* proxies with good clash delay."""
    kept = []
    kept_servers = set()
    kept_cc = {}

    free_outbounds = [
        o for o in sb_cfg.get("outbounds", [])
        if o.get("tag", "").startswith("free-")
    ]

    info(f"Checking {len(free_outbounds)} existing free proxies via clash API...")

    def check_one(ob):
        tag = ob["tag"]
        delay = clash_delay(tag, secret)
        if delay is not None and delay < 500:
            return (ob, delay)
        return None

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(check_one, ob): ob for ob in free_outbounds}
        for fut in as_completed(futures):
            result = fut.result()
            if result:
                ob, delay = result
                kept.append(ob)
                kept_servers.add(ob.get("server", ""))
                parts = ob["tag"].split("-")
                if len(parts) >= 2:
                    cc = parts[1]
                    kept_cc.setdefault(cc, []).append(ob["tag"])

    info(f"Kept {len(kept)} existing proxies (delay <500ms)")
    return kept, kept_servers, kept_cc


def pick_fresh(all_proxies: list[dict], kept_servers: set[str], slots: int, target_countries: list[str]) -> list[dict]:
    """Pick fresh proxies from GitHub data, avoiding duplicates."""
    fresh = []
    seen = kept_servers.copy()

    # Prioritize target countries
    prioritized = []
    others = []
    for p in all_proxies:
        if p.get("server") in seen:
            continue
        if p.get("country_code") in target_countries:
            prioritized.append(p)
        else:
            others.append(p)

    random.shuffle(prioritized)
    random.shuffle(others)

    for p in prioritized + others:
        if len(fresh) >= slots:
            break
        srv = p.get("server", "")
        if srv not in seen:
            seen.add(srv)
            fresh.append(p)

    return fresh


def build_outbounds(kept_obs: list[dict], fresh: list[dict], kept_cc: dict[str, list[str]]) -> list[dict]:
    """Build outbound dicts for free proxies."""
    outbounds = list(kept_obs)
    cc_counter = Counter()

    for cc, tags in kept_cc.items():
        cc_counter[cc] = len(tags)

    for p in fresh:
        cc = p.get("country_code", "XX")
        cc_counter[cc] += 1
        idx = cc_counter[cc]
        suffix = p.get("tag", "proxy").split("-", 3)[-1] if "-" in p.get("tag", "") else "proxy"
        tag = f"free-{cc}-{idx}"

        ob = dict(p.get("outbound", {}))
        ob["tag"] = tag
        ob["bind_interface"] = "eth0"
        outbounds.append(ob)

    return outbounds


def update_config(sb_cfg: dict, free_obs: list[dict], target_countries: list[str], proxy_aware_selectors: list[str]):
    """Update sing-box config with new free proxy outbounds + groups."""
    # Remove old free-* outbounds
    sb_cfg["outbounds"] = [
        o for o in sb_cfg["outbounds"]
        if not o.get("tag", "").startswith("free-")
        and o.get("tag") != "PROXY-FREE"
        and not o.get("tag", "").startswith("PROXY-")
    ]

    # Add free outbounds
    sb_cfg["outbounds"].extend(free_obs)

    # Build country groups
    cc_groups = {}
    for ob in free_obs:
        parts = ob["tag"].split("-")
        if len(parts) >= 2:
            cc = parts[1]
            cc_groups.setdefault(cc, []).append(ob["tag"])

    # PROXY-FREE loadbalance
    free_tags = [ob["tag"] for ob in free_obs]
    if free_tags:
        sb_cfg["outbounds"].append({
            "type": "loadbalance",
            "tag": "PROXY-FREE",
            "outbounds": free_tags,
            "url": "http://cp.cloudflare.com/generate_204",
            "interval": "10m",
            "strategy": "sticky-sessions",
            "ttl": "2m",
        })

    # Per-country selectors
    for cc in target_countries:
        tags = cc_groups.get(cc, [])
        if tags:
            sb_cfg["outbounds"].append({
                "type": "selector",
                "tag": f"PROXY-{cc}",
                "outbounds": tags,
                "default": tags[0],
            })

    # Update managed selectors with PROXY-* groups
    managed_tags = set(proxy_aware_selectors) | {"WAN"}
    built_groups = sorted(f"PROXY-{cc}" for cc in target_countries if cc in cc_groups)

    for ob in sb_cfg["outbounds"]:
        if ob.get("type") != "selector" or ob.get("tag") not in managed_tags:
            continue
        base = [c for c in ob.get("outbounds", []) if not c.startswith("PROXY-")]
        if ob["tag"] in proxy_aware_selectors:
            proxy_groups = sorted(g for g in built_groups if g != ob["tag"])
        else:
            proxy_groups = []
        ob["outbounds"] = base + proxy_groups


# ── Public API ────────────────────────────────────────────────────────

def fetch_and_update(cfg: dict) -> bool:
    """Fetch proxies from GitHub and update sing-box config."""
    require_root()
    sb_cfg = read_json(SINGBOX_CFG)
    if not sb_cfg:
        fail("sing-box config tidak ditemukan")
        return False

    pcfg = cfg.get("proxy", {})
    github_raw = pcfg.get("github_raw", GITHUB_RAW)
    max_free = pcfg.get("max_free", 40)
    secret = pcfg.get("clash_secret", "hijinet")
    target_countries = pcfg.get("target_countries", ["US", "SG", "ID"])
    proxy_aware_selectors = pcfg.get("proxy_aware_selectors", ["GLOBAL", "GOOGLE", "OPENAI", "IPCHECK"])

    header("Proxy Fetch & Update")

    # Freshness check
    state = read_json(STATE_FILE) or {}
    all_proxies, generated_at = fetch_github_proxies(github_raw)
    if not all_proxies:
        fail("Tidak ada data dari GitHub")
        return False

    if generated_at and generated_at == state.get("last_generated_at"):
        info(f"Data masih fresh ({generated_at}), skip update")
        return True

    # Keep existing good proxies
    kept_obs, kept_servers, kept_cc = keep_existing(sb_cfg, secret)
    slots_needed = max_free - len(kept_obs)

    if slots_needed <= 0:
        info(f"Pool penuh ({len(kept_obs)} >= {max_free})")
        free_obs = build_outbounds(kept_obs, [], kept_cc)
    else:
        fresh = pick_fresh(all_proxies, kept_servers, slots_needed, target_countries)
        free_obs = build_outbounds(kept_obs, fresh, kept_cc)

    # Update config
    info("Updating sing-box config...")
    update_config(sb_cfg, free_obs, target_countries, proxy_aware_selectors)
    write_json(SINGBOX_CFG, sb_cfg)

    # Validate
    r = run([str(SINGBOX_BIN), "check", "-c", str(SINGBOX_CFG)])
    if r.returncode != 0:
        fail(f"Config error: {r.stderr.strip()}")
        return False
    ok("Config valid")

    # Save state
    write_json(STATE_FILE, {"last_generated_at": generated_at})

    # Restart sing-box
    run(["systemctl", "restart", "sing-box"])
    time.sleep(2)
    from .utils import service_running
    if service_running("sing-box"):
        ok(f"sing-box restarted — {len(free_obs)} free proxies active")
    else:
        fail("sing-box gagal start")
        return False

    # Count per country
    cc_counts = Counter()
    for ob in free_obs:
        parts = ob["tag"].split("-")
        if len(parts) >= 2:
            cc_counts[parts[1]] += 1
    groups_str = ", ".join(f"PROXY-{k}({v})" for k, v in sorted(cc_counts.items()))
    info(f"Groups: {groups_str}")

    return True


def status(cfg: dict) -> dict:
    """Return proxy pool status."""
    sb_cfg = read_json(SINGBOX_CFG)
    if not sb_cfg:
        return {"total": 0, "groups": {}}

    free_obs = [o for o in sb_cfg.get("outbounds", []) if o.get("tag", "").startswith("free-")]
    groups = {}
    for ob in free_obs:
        parts = ob["tag"].split("-")
        if len(parts) >= 2:
            cc = parts[1]
            groups.setdefault(f"PROXY-{cc}", []).append(ob["tag"])

    return {
        "total": len(free_obs),
        "groups": groups,
        "state": read_json(STATE_FILE) or {},
    }


def doctor(cfg: dict) -> list[str]:
    """Diagnose proxy issues."""
    problems = []
    sb_cfg = read_json(SINGBOX_CFG)
    if not sb_cfg:
        problems.append("sing-box config tidak ditemukan")
        return problems

    free_obs = [o for o in sb_cfg.get("outbounds", []) if o.get("tag", "").startswith("free-")]
    if len(free_obs) == 0:
        problems.append("Tidak ada free proxies di config")

    proxy_free = next((o for o in sb_cfg["outbounds"] if o.get("tag") == "PROXY-FREE"), None)
    if not proxy_free:
        problems.append("PROXY-FREE group tidak ada")
    elif proxy_free.get("type") != "loadbalance":
        problems.append(f"PROXY-FREE type={proxy_free.get('type')}, seharusnya loadbalance")

    return problems
