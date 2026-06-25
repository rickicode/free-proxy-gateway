#!/usr/bin/env python3
"""Convert free-proxy-singbox live-proxies.json to mihomo (Clash Meta) YAML.

Proxy names format: {flag}-{ISP} or {flag}-{ISP}-{N} if multiple from same ISP.
Example: 🇺🇸-Cloudflare, 🇩🇪-Hetzner-2
GLOBAL group only shows proxy groups + DIRECT (no individual proxies).
Group names keep PROXY-FREE/PROXY-ID/PROXY-SG/PROXY-US format."""

import json
import re
import sys
from collections import defaultdict
from pathlib import Path


def cc_to_flag(cc: str) -> str:
    """Country code to flag emoji."""
    if len(cc) != 2 or not cc.isalpha():
        return cc
    return chr(0x1F1E6 + ord(cc[0]) - 65) + chr(0x1F1E6 + ord(cc[1]) - 65)


def sanitize_isp(isp: str) -> str:
    """Clean ISP name for display: remove Inc., Ltd., etc, truncate."""
    if not isp or isp == "Unknown":
        return ""
    for suffix in [" Inc.", " Inc", " Ltd.", " Ltd", " LLC", " Co.,", " Co.", " S.A.",
                   " GmbH", " AG", " B.V.", " SARL", " S.L.", " AB", " AS", " ApS",
                   " Limited", " Corporation", " Holdings", " Group", " Networks",
                   " Communications", " Technologies", " Solutions", " Services",
                   " International", " Global", " Worldwide"]:
        isp = isp.replace(suffix, "")
    isp = isp.strip(" ,.-")
    if len(isp) > 25:
        isp = isp[:25].rsplit(" ", 1)[0]
    return isp


CC_RE = re.compile(r"^FREE-([A-Z]{2})-\d{4}-")


def convert_outbound(ob: dict) -> dict | None:
    """Convert sing-box outbound to mihomo proxy dict."""
    t = ob.get("type", "")
    server = ob.get("server", "")
    port = ob.get("server_port", 0)

    if not server or not port:
        return None

    if t == "trojan":
        tls = ob.get("tls", {})
        return {
            "type": "trojan",
            "server": server,
            "port": port,
            "password": ob.get("password", ""),
            "sni": tls.get("server_name", server),
            "skip-cert-verify": tls.get("insecure", True),
            "udp": True,
        }

    if t == "vless":
        tls = ob.get("tls", {})
        transport = ob.get("transport", {})
        proxy = {
            "type": "vless",
            "server": server,
            "port": port,
            "uuid": ob.get("uuid", ""),
            "tls": tls.get("enabled", False),
            "servername": tls.get("server_name", ""),
            "skip-cert-verify": tls.get("insecure", True),
            "udp": True,
        }
        if ob.get("flow"):
            proxy["flow"] = ob["flow"]
        if transport:
            tp = transport.get("type", "")
            if tp == "ws":
                proxy["network"] = "ws"
                ws = {"path": transport.get("path", "/")}
                host = transport.get("headers", {}).get("Host")
                if host:
                    ws["headers"] = {"Host": host}
                proxy["ws-opts"] = ws
            elif tp == "grpc":
                proxy["network"] = "grpc"
                proxy["grpc-opts"] = {
                    "grpc-service-name": transport.get("service_name", "")
                }
        return proxy

    if t == "vmess":
        tls = ob.get("tls", {})
        transport = ob.get("transport", {})
        proxy = {
            "type": "vmess",
            "server": server,
            "port": port,
            "uuid": ob.get("uuid", ""),
            "alterId": ob.get("alter_id", 0),
            "cipher": ob.get("cipher", "auto"),
            "tls": tls.get("enabled", False),
            "skip-cert-verify": tls.get("insecure", True),
            "udp": True,
        }
        if tls.get("server_name"):
            proxy["servername"] = tls["server_name"]
        if transport:
            tp = transport.get("type", "")
            if tp == "ws":
                proxy["network"] = "ws"
                ws = {"path": transport.get("path", "/")}
                host = transport.get("headers", {}).get("Host")
                if host:
                    ws["headers"] = {"Host": host}
                proxy["ws-opts"] = ws
        return proxy

    if t == "shadowsocks":
        return {
            "type": "ss",
            "server": server,
            "port": port,
            "cipher": ob.get("method", ob.get("cipher", "auto")),
            "password": ob.get("password", ""),
            "udp": True,
        }

    if t == "hysteria2":
        tls = ob.get("tls", {})
        proxy = {
            "type": "hysteria2",
            "server": server,
            "port": port,
            "password": ob.get("password", ""),
            "skip-cert-verify": tls.get("insecure", True),
            "udp": True,
        }
        if tls.get("server_name"):
            proxy["sni"] = tls["server_name"]
        return proxy

    return None


def build_mihomo(data: dict) -> str:
    proxies_input = data.get("proxies", [])
    groups_data = data.get("groups", {})

    # Pass 1: collect entries with tag, country, ISP
    entries = []
    for entry in proxies_input:
        ob = entry.get("outbound", entry)
        tag = ob.get("tag", "")
        m = CC_RE.match(tag)
        if not m:
            continue
        cc = m.group(1)
        isp = entry.get("isp", "") or ""
        entries.append({"tag": tag, "cc": cc, "isp": isp, "outbound": ob})

    # Pass 2: group by (cc, isp) for numbering
    isp_groups = defaultdict(list)
    for e in entries:
        isp_clean = sanitize_isp(e["isp"]) or "Unknown"
        key = (e["cc"], isp_clean)
        isp_groups[key].append(e["tag"])

    # Pass 3: build tag -> display name mapping
    tag_to_name = {}
    for (cc, isp_clean), tags in isp_groups.items():
        flag = cc_to_flag(cc)
        if len(tags) == 1:
            tag_to_name[tags[0]] = f"{flag}-{isp_clean}"
        else:
            for i, tag in enumerate(tags, 1):
                tag_to_name[tag] = f"{flag}-{isp_clean}-{i}"

    # Convert proxies with display names
    proxies = []
    proxy_names = []
    for entry in proxies_input:
        ob = entry.get("outbound", entry)
        proxy = convert_outbound(ob)
        if not proxy:
            continue
        tag = ob.get("tag", "")
        proxy["name"] = tag_to_name.get(tag, tag)
        proxies.append(proxy)
        proxy_names.append(proxy["name"])

    # Build proxy groups using tag->name mapping
    proxy_groups = []
    for gname, gtags in groups_data.items():
        if not isinstance(gtags, list) or not gtags:
            continue
        matching = [tag_to_name[t] for t in gtags if t in tag_to_name]
        if matching:
            proxy_groups.append({
                "name": gname,
                "type": "url-test",
                "proxies": matching,
                "url": "http://www.gstatic.com/generate_204",
                "interval": 300,
            })

    # GLOBAL selector: only groups + DIRECT
    group_names = [g["name"] for g in proxy_groups]
    proxy_groups.insert(0, {
        "name": "GLOBAL",
        "type": "select",
        "proxies": ["DIRECT"] + group_names,
    })

    # Build YAML
    lines = [
        "# Auto-generated by free-proxy-singbox",
        "# Source: https://github.com/rickicode/free-proxy-singbox",
        f"# Generated: {data.get('generated_at', 'unknown')}",
        f"# Live proxies: {data.get('live_count', len(proxy_names))}",
        "",
        "mixed-port: 7890",
        "allow-lan: true",
        "bind-address: '*'",
        "mode: rule",
        "log-level: warning",
        "ipv6: false",
        "",
        "dns:",
        "  enable: true",
        "  listen: :1053",
        "  enhanced-mode: fake-ip",
        "  fake-ip-range: 198.18.0.1/16",
        "  default-nameserver:",
        "    - 223.5.5.5",
        "    - 8.8.8.8",
        "  nameserver:",
        "    - https://223.5.5.5/dns-query",
        "    - https://1.1.1.1/dns-query",
        "  nameserver-policy:",
        "    'geosite:private,cn': 223.5.5.5",
        "    'geosite:geolocation-!cn': https://1.1.1.1/dns-query",
        "",
        "proxies:",
    ]

    for p in proxies:
        lines.append(f"  - {json.dumps(p, ensure_ascii=False)}")

    lines.append("")
    lines.append("proxy-groups:")
    for g in proxy_groups:
        lines.append(f"  - {json.dumps(g, ensure_ascii=False)}")

    lines.append("")
    lines.append("rules:")
    for r in [
        "GEOSITE,category-ads-all,REJECT",
        "GEOSITE,private,DIRECT",
        "GEOIP,private,DIRECT,no-resolve",
        "GEOSITE,cn,DIRECT",
        "GEOIP,cn,DIRECT,no-resolve",
        "GEOSITE,google,PROXY-FREE",
        "GEOSITE,github,PROXY-FREE",
        "GEOSITE,telegram,PROXY-FREE",
        "GEOSITE,youtube,PROXY-FREE",
        "GEOSITE,netflix,PROXY-FREE",
        "GEOSITE,openai,PROXY-FREE",
        "MATCH,PROXY-FREE",
    ]:
        lines.append(f"  - {r}")

    lines.append("")
    return "\n".join(lines)


def main():
    if len(sys.argv) < 3:
        print("Usage: convert_to_mihomo.py <input.json> <output.yml>")
        sys.exit(1)

    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])

    data = json.loads(input_path.read_text())
    content = build_mihomo(data)
    output_path.write_text(content)
    print(f"Written {output_path} ({len(content)} bytes, {content.count(chr(10))} lines)")


if __name__ == "__main__":
    main()
