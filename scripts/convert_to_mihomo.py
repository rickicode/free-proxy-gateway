#!/usr/bin/env python3
"""Convert sing-box output to mihomo (Clash Meta) YAML format."""

import json
import sys
from pathlib import Path


def convert_outbound(outbound: dict) -> dict | None:
    """Convert sing-box outbound to mihomo proxy dict."""
    t = outbound.get("type")
    tag = outbound.get("tag", "")
    server = outbound.get("server", "")
    port = outbound.get("server_port", 0)

    if not server or not port:
        return None

    if t == "trojan":
        tls = outbound.get("tls", {})
        return {
            "name": tag,
            "type": "trojan",
            "server": server,
            "port": port,
            "password": outbound.get("password", ""),
            "sni": tls.get("server_name", server),
            "skip-cert-verify": tls.get("insecure", True),
            "udp": True,
        }

    if t == "vless":
        tls = outbound.get("tls", {})
        transport = outbound.get("transport", {})
        proxy = {
            "name": tag,
            "type": "vless",
            "server": server,
            "port": port,
            "uuid": outbound.get("uuid", ""),
            "tls": tls.get("enabled", False),
            "servername": tls.get("server_name", ""),
            "skip-cert-verify": tls.get("insecure", True),
            "udp": True,
        }
        if outbound.get("flow"):
            proxy["flow"] = outbound["flow"]
        if transport:
            tp = transport.get("type", "")
            if tp == "ws":
                proxy["network"] = "ws"
                proxy["ws-opts"] = {
                    "path": transport.get("path", "/"),
                }
                if transport.get("headers", {}).get("Host"):
                    proxy["ws-opts"]["headers"] = {
                        "Host": transport["headers"]["Host"]
                    }
            elif tp == "grpc":
                proxy["network"] = "grpc"
                proxy["grpc-opts"] = {
                    "grpc-service-name": transport.get("service_name", ""),
                }
        return proxy

    if t == "vmess":
        tls = outbound.get("tls", {})
        transport = outbound.get("transport", {})
        proxy = {
            "name": tag,
            "type": "vmess",
            "server": server,
            "port": port,
            "uuid": outbound.get("uuid", ""),
            "alterId": outbound.get("alter_id", 0),
            "cipher": outbound.get("cipher", "auto"),
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
                proxy["ws-opts"] = {
                    "path": transport.get("path", "/"),
                }
                if transport.get("headers", {}).get("Host"):
                    proxy["ws-opts"]["headers"] = {
                        "Host": transport["headers"]["Host"]
                    }
        return proxy

    if t == "shadowsocks":
        return {
            "name": tag,
            "type": "ss",
            "server": server,
            "port": port,
            "cipher": outbound.get("method", outbound.get("cipher", "auto")),
            "password": outbound.get("password", ""),
            "udp": True,
        }

    if t == "hysteria2":
        tls = outbound.get("tls", {})
        proxy = {
            "name": tag,
            "type": "hysteria2",
            "server": server,
            "port": port,
            "password": outbound.get("password", ""),
            "skip-cert-verify": tls.get("insecure", True),
            "udp": True,
        }
        if tls.get("server_name"):
            proxy["sni"] = tls["server_name"]
        if outbound.get("bandwidth", {}).get("up"):
            proxy["up"] = outbound["bandwidth"]["up"]
        if outbound.get("bandwidth", {}).get("down"):
            proxy["down"] = outbound["bandwidth"]["down"]
        return proxy

    # Unknown type, skip
    return None


def build_mihomo_config(data: dict) -> str:
    """Build mihomo YAML config from singbox data."""
    outbounds = data.get("outbounds", [])

    # Convert proxies
    proxies = []
    proxy_names = []
    group_map = {}  # tag -> list of proxy names

    for ob in outbounds:
        tag = ob.get("tag", "")
        t = ob.get("type")

        # Skip non-proxy outbounds
        if t in ("direct", "block", "dns", "selector", "urltest"):
            continue

        proxy = convert_outbound(ob)
        if proxy:
            proxies.append(proxy)
            proxy_names.append(proxy["name"])

    # Build groups from data.groups
    groups_data = data.get("groups", {})
    proxy_groups = []

    # Main selector group
    if proxy_names:
        proxy_groups.append({
            "name": "PROXY-FREE",
            "type": "select",
            "proxies": proxy_names[:100],  # Limit to 100 for usability
        })

    # Country-based groups
    for group_name, group_tags in groups_data.items():
        if isinstance(group_tags, list) and group_tags:
            # Map tags to proxy names
            matching = [t for t in group_tags if t in proxy_names]
            if matching:
                proxy_groups.append({
                    "name": group_name,
                    "type": "url-test",
                    "proxies": matching[:50],
                    "url": "http://www.gstatic.com/generate_204",
                    "interval": 300,
                })

    # Build YAML manually (avoid PyYAML dependency)
    lines = []
    lines.append("# Auto-generated by free-proxy-singbox")
    lines.append("# Source: https://github.com/rickicode/free-proxy-singbox")
    lines.append(f"# Generated: {data.get('generated_at', 'unknown')}")
    lines.append(f"# Live proxies: {data.get('live_count', len(proxy_names))}")
    lines.append("")
    lines.append("mixed-port: 7890")
    lines.append("allow-lan: true")
    lines.append("bind-address: '*'")
    lines.append("mode: rule")
    lines.append("log-level: warning")
    lines.append("ipv6: false")
    lines.append("")
    lines.append("dns:")
    lines.append("  enable: true")
    lines.append("  listen: :1053")
    lines.append("  enhanced-mode: fake-ip")
    lines.append("  fake-ip-range: 198.18.0.1/16")
    lines.append("  default-nameserver:")
    lines.append("    - 223.5.5.5")
    lines.append("    - 8.8.8.8")
    lines.append("  nameserver:")
    lines.append("    - https://223.5.5.5/dns-query")
    lines.append("    - https://1.1.1.1/dns-query")
    lines.append("  nameserver-policy:")
    lines.append("    'geosite:private,cn': 223.5.5.5")
    lines.append("    'geosite:geolocation-!cn': https://1.1.1.1/dns-query")
    lines.append("")

    # Proxies
    lines.append("proxies:")
    for p in proxies:
        lines.append(f"  - {json.dumps(p, ensure_ascii=False)}")
    lines.append("")

    # Proxy groups
    lines.append("proxy-groups:")
    for g in proxy_groups:
        lines.append(f"  - {json.dumps(g, ensure_ascii=False)}")
    lines.append("")

    # Rules
    lines.append("rules:")
    lines.append("  - GEOSITE,category-ads-all,REJECT")
    lines.append("  - GEOSITE,private,DIRECT")
    lines.append("  - GEOIP,private,DIRECT,no-resolve")
    lines.append("  - GEOSITE,cn,DIRECT")
    lines.append("  - GEOIP,cn,DIRECT,no-resolve")
    lines.append("  - GEOSITE,google,PROXY-FREE")
    lines.append("  - GEOSITE,github,PROXY-FREE")
    lines.append("  - GEOSITE,telegram,PROXY-FREE")
    lines.append("  - GEOSITE,youtube,PROXY-FREE")
    lines.append("  - GEOSITE,netflix,PROXY-FREE")
    lines.append("  - GEOSITE,openai,PROXY-FREE")
    lines.append("  - MATCH,PROXY-FREE")
    lines.append("")

    return "\n".join(lines)


def main():
    if len(sys.argv) < 3:
        print("Usage: convert_to_mihomo.py <input.json> <output.yml>")
        sys.exit(1)

    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])

    data = json.loads(input_path.read_text())
    yaml_content = build_mihomo_config(data)
    output_path.write_text(yaml_content)
    print(f"Written {output_path} ({len(yaml_content)} bytes)")


if __name__ == "__main__":
    main()
