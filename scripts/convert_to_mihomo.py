#!/usr/bin/env python3
"""Convert free-proxy-singbox live-proxies.json to mihomo (Clash Meta) YAML.

Proxy names are normalized to country flag emojis (e.g. 🇺🇸, 🇩🇪 2).
GLOBAL group only shows proxy groups + DIRECT (no individual proxies)."""

import json
import re
import sys
from pathlib import Path


# Country code -> flag emoji
def cc_to_flag(cc: str) -> str:
    if len(cc) != 2 or not cc.isalpha():
        return cc
    return chr(0x1F1E6 + ord(cc[0]) - 65) + chr(0x1F1E6 + ord(cc[1]) - 65)


# Extract country code from tag like "FREE-XX-NNNN-anything"
_CC_RE = re.compile(r"^FREE-([A-Z]{2})-\d{4}-")


def normalize_name(tag: str, counter: dict) -> str:
    """Convert FREE-XX-NNNN-suffix to flag emoji with index."""
    m = _CC_RE.match(tag)
    if not m:
        return tag
    cc = m.group(1)
    flag = cc_to_flag(cc)
    counter[cc] = counter.get(cc, 0) + 1
    if counter[cc] == 1:
        return flag
    return f"{flag} {counter[cc]}"


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

    # Convert & rename proxies
    proxies = []
    proxy_names = []
    name_counter = {}  # cc -> count for numbering

    for entry in proxies_input:
        ob = entry.get("outbound", entry)
        proxy = convert_outbound(ob)
        if not proxy:
            continue
        tag = ob.get("tag", "")
        name = normalize_name(tag, name_counter)
        proxy["name"] = name
        proxies.append(proxy)
        proxy_names.append(name)

    # Build proxy groups
    proxy_groups = []

    # Country-based url-test groups (prepend)
    for gname, gtags in groups_data.items():
        if not isinstance(gtags, list) or not gtags:
            continue
        matching = []
        for t in gtags:
            m = _CC_RE.match(t)
            if m:
                cc = m.group(1)
                flag = cc_to_flag(cc)
                # find matching renamed proxy
                for pname in proxy_names:
                    if pname == flag or pname.startswith(flag + " "):
                        if pname not in matching:
                            matching.append(pname)
                        break
            elif t in proxy_names:
                matching.append(t)
        if matching:
            proxy_groups.append({
                "name": gname,
                "type": "url-test",
                "proxies": matching,
                "url": "http://www.gstatic.com/generate_204",
                "interval": 300,
            })

    # GLOBAL selector: only groups + DIRECT (no individual proxies)
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
