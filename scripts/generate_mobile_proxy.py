#!/usr/bin/env python3
"""
Generate optimized, production-ready sing-box configuration for Android mobile proxy.
Zero Python dependency on Android: output is pre-compiled, minified (~37KB), and directly runnable.
"""
import sys
import os
import json
import argparse
from collections import defaultdict
from pathlib import Path

AMERICA_CC = ["US", "CA", "MX", "BR", "AR", "CL", "CO", "PE", "VE", "EC", "UY", "PY", "BO"]
ASIA_CC = ["SG", "ID", "JP", "KR", "HK", "TW", "MY", "TH", "VN", "IN", "CN",
           "KZ", "UZ", "AE", "SA", "QA", "KW", "BH", "OM", "IL", "JO",
           "PH", "KH", "LA", "MM", "BD", "LK", "NP", "MN"]
EUROPE_CC = ["DE", "NL", "FR", "GB", "PL", "IT", "LT", "SE", "LU", "LV", "FI",
             "NO", "RO", "AT", "CH", "BE", "EE", "ES", "IE", "RU", "AL", "BG",
             "CZ", "DK", "GR", "TR", "UA", "HU", "PT", "SK", "SI", "HR", "RS",
             "BA", "MD", "IS"]

DEFAULT_TEMPLATE = {
    "log": {
        "level": "info",
        "output": "/data/adb/mobile_proxy_tailscale/logs/singbox.log",
        "timestamp": True
    },
    "dns": {
        "servers": [
            {"type": "udp", "tag": "dns-direct", "server": "1.1.1.1"},
            {"type": "udp", "tag": "dns-direct2", "server": "8.8.8.8"}
        ],
        "strategy": "prefer_ipv4"
    },
    "experimental": {
        "clash_api": {
            "external_controller": "0.0.0.0:9090",
            "external_ui": "/data/adb/modules/mobile_proxy_tailscale/dashboard",
            "secret": "singbox",
            "default_mode": "rule"
        }
    },
    "inbounds": [
        {"type": "http", "tag": "proxy-1080", "listen": "0.0.0.0", "listen_port": 1080, "domain_resolver": "dns-direct"},
        {"type": "mixed", "tag": "mixed-1011", "listen": "0.0.0.0", "listen_port": 1011, "domain_resolver": "dns-direct"},
        {"type": "mixed", "tag": "mixed-1012", "listen": "0.0.0.0", "listen_port": 1012, "domain_resolver": "dns-direct"},
        {"type": "mixed", "tag": "mixed-1013", "listen": "0.0.0.0", "listen_port": 1013, "domain_resolver": "dns-direct"},
        {"type": "mixed", "tag": "mixed-1014", "listen": "0.0.0.0", "listen_port": 1014, "domain_resolver": "dns-direct"}
    ],
    "outbounds": [
        {"type": "direct", "tag": "DIRECT", "domain_resolver": "dns-direct"}
    ],
    "route": {
        "rules": [
            {"inbound": ["proxy-1080"], "outbound": "DIRECT"},
            {"inbound": ["mixed-1011"], "outbound": "PROXY-FREE"},
            {"inbound": ["mixed-1012"], "outbound": "PROXY-AMERICA"},
            {"inbound": ["mixed-1013"], "outbound": "PROXY-ASIA"},
            {"inbound": ["mixed-1014"], "outbound": "PROXY-EUROPE"}
        ],
        "auto_detect_interface": False
    }
}


def pick_region(proxies, allowed, total, per_cc, prefix):
    """Fair round-robin selection across countries in region."""
    allowed_set = set(allowed)
    buckets = defaultdict(list)
    for p in proxies:
        cc = p.get("country_code")
        if cc not in allowed_set:
            continue
        ob = p.get("outbound")
        if not ob or not isinstance(ob, dict):
            continue
        buckets[cc].append(p)

    out = []
    out_cc = []
    seen = set()
    taken = defaultdict(int)
    cursor = defaultdict(int)

    while len(out) < total:
        progress = False
        for cc in sorted(buckets.keys()):
            if len(out) >= total:
                break
            if taken[cc] >= per_cc:
                continue
            bucket = buckets[cc]
            while cursor[cc] < len(bucket):
                p = bucket[cursor[cc]]
                cursor[cc] += 1
                ob = p.get("outbound")
                base = (ob.get("tag") if isinstance(ob, dict) else None) or p.get("tag") or f"{cc}-{cursor[cc]}"
                tag = f"{prefix}-{base}"
                if tag in seen:
                    continue
                ob = dict(ob)
                ob["tag"] = tag
                ob.setdefault("domain_resolver", "dns-direct")
                seen.add(tag)
                out.append(ob)
                out_cc.append(cc)
                taken[cc] += 1
                progress = True
                break
        if not progress:
            break
    return out, out_cc


def build_mobile_config(proxies_data, template=None, minified=True):
    cfg = dict(template or DEFAULT_TEMPLATE)
    proxies = proxies_data.get("proxies", [])
    if not proxies:
        raise ValueError("live-proxies.json contains no proxies")

    # FREE: global diverse 30 (max 2 per country)
    free_outbounds = []
    free_per_cc = {}
    for i, p in enumerate(proxies):
        if len(free_outbounds) >= 30:
            break
        ob = p.get("outbound")
        if not ob or not isinstance(ob, dict):
            continue
        cc = p.get("country_code") or "XX"
        if free_per_cc.get(cc, 0) >= 2:
            continue
        ob = dict(ob)
        tag = f"free-{cc}-{i}"
        if any(o.get("tag") == tag for o in free_outbounds):
            continue
        ob["tag"] = tag
        ob.setdefault("domain_resolver", "dns-direct")
        free_outbounds.append(ob)
        free_per_cc[cc] = free_per_cc.get(cc, 0) + 1

    america_outbounds, _ = pick_region(proxies, AMERICA_CC, 30, 15, "am")
    asia_outbounds, _ = pick_region(proxies, ASIA_CC, 30, 8, "asia")
    europe_outbounds, _ = pick_region(proxies, EUROPE_CC, 30, 8, "eu")

    if not free_outbounds:
        raise ValueError("No valid free outbounds extracted from proxies")

    cfg.setdefault("outbounds", [])
    cfg["outbounds"].extend(free_outbounds)
    if america_outbounds:
        cfg["outbounds"].extend(america_outbounds)
    if asia_outbounds:
        cfg["outbounds"].extend(asia_outbounds)
    if europe_outbounds:
        cfg["outbounds"].extend(europe_outbounds)

    free_tags = [o["tag"] for o in free_outbounds]
    america_tags = [o["tag"] for o in america_outbounds]
    asia_tags = [o["tag"] for o in asia_outbounds]
    europe_tags = [o["tag"] for o in europe_outbounds]

    cfg["outbounds"].append({
        "type": "urltest",
        "tag": "PROXY-FREE",
        "outbounds": free_tags,
        "url": "https://www.gstatic.com/generate_204",
        "interval": "10m",
        "tolerance": 50
    })

    if america_tags:
        cfg["outbounds"].append({
            "type": "urltest",
            "tag": "PROXY-AMERICA",
            "outbounds": america_tags,
            "url": "https://www.gstatic.com/generate_204",
            "interval": "10m",
            "tolerance": 50
        })
    else:
        cfg["outbounds"].append({
            "type": "selector",
            "tag": "PROXY-AMERICA",
            "outbounds": ["PROXY-FREE"]
        })

    if asia_tags:
        cfg["outbounds"].append({
            "type": "urltest",
            "tag": "PROXY-ASIA",
            "outbounds": asia_tags,
            "url": "https://www.gstatic.com/generate_204",
            "interval": "10m",
            "tolerance": 50
        })
    else:
        cfg["outbounds"].append({
            "type": "selector",
            "tag": "PROXY-ASIA",
            "outbounds": ["PROXY-FREE"]
        })

    if europe_tags:
        cfg["outbounds"].append({
            "type": "urltest",
            "tag": "PROXY-EUROPE",
            "outbounds": europe_tags,
            "url": "https://www.gstatic.com/generate_204",
            "interval": "10m",
            "tolerance": 50
        })
    else:
        cfg["outbounds"].append({
            "type": "selector",
            "tag": "PROXY-EUROPE",
            "outbounds": ["PROXY-FREE"]
        })

    all_group_tags = [t for t in ["PROXY-FREE", "PROXY-AMERICA", "PROXY-ASIA", "PROXY-EUROPE"]
                      if any(o.get("tag") == t for o in cfg["outbounds"])]
    if all_group_tags and not any(o.get("tag") == "GLOBAL" for o in cfg["outbounds"]):
        cfg["outbounds"].append({
            "type": "selector",
            "tag": "GLOBAL",
            "outbounds": all_group_tags
        })

    return cfg


def main():
    parser = argparse.ArgumentParser(description="Generate mobile proxy sing-box JSON")
    parser.add_argument("--input", default="output/live-proxies.json", help="Path to live-proxies.json")
    parser.add_argument("--template", default=None, help="Optional path to custom template JSON")
    parser.add_argument("--output", default="output/mobile-proxy-singbox.json", help="Destination path")
    parser.add_argument("--pretty", action="store_true", help="Indent JSON output (default minified)")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: input file {input_path} not found", file=sys.stderr)
        sys.exit(1)

    template = None
    if args.template and Path(args.template).exists():
        template = json.loads(Path(args.template).read_text())

    try:
        proxies_data = json.loads(input_path.read_text())
        cfg = build_mobile_config(proxies_data, template=template)
    except Exception as e:
        print(f"Error generating config: {e}", file=sys.stderr)
        sys.exit(2)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if args.pretty:
        rendered = json.dumps(cfg, indent=2)
    else:
        rendered = json.dumps(cfg, separators=(',', ':'))

    out_path.write_text(rendered)
    ob_count = len(cfg.get("outbounds", []))
    groups = [o["tag"] for o in cfg.get("outbounds", []) if o.get("type") in ("urltest", "selector")]
    print(f"[OK] Generated {out_path} ({len(rendered)} bytes, {len(rendered)/1024:.1f} KB)")
    print(f"     Outbounds: {ob_count} | Groups: {', '.join(groups)}")


if __name__ == "__main__":
    main()
