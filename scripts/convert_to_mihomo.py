#!/usr/bin/env python3
"""Convert free-proxy-gateway live-proxies.json to mihomo proxy-provider YAML.

Output: proxies ONLY. Groups defined in openwrt/base.yml via proxy-provider filter.
Proxy names: {flag}{ISP} or {flag}{ISP}-{N}."""

import json
import re
import sys
from collections import defaultdict
from pathlib import Path


def cc_to_flag(cc: str) -> str:
    if len(cc) != 2 or not cc.isalpha():
        return cc
    return chr(0x1F1E6 + ord(cc[0]) - 65) + chr(0x1F1E6 + ord(cc[1]) - 65)


def sanitize_isp(isp: str) -> str:
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
    t = ob.get("type", "")
    server = ob.get("server", "")
    port = ob.get("server_port", 0)
    if not server or not port:
        return None

    if t == "trojan":
        tls = ob.get("tls", {})
        return {"type": "trojan", "server": server, "port": port, "password": ob.get("password", ""), "sni": tls.get("server_name", server), "skip-cert-verify": tls.get("insecure", True), "udp": True}

    if t == "vless":
        tls = ob.get("tls", {})
        transport = ob.get("transport", {})
        proxy = {"type": "vless", "server": server, "port": port, "uuid": ob.get("uuid", ""), "tls": tls.get("enabled", False), "servername": tls.get("server_name", ""), "skip-cert-verify": tls.get("insecure", True), "udp": True}
        if ob.get("flow"):
            proxy["flow"] = ob["flow"]
        if transport:
            tp = transport.get("type", "")
            if tp == "ws":
                proxy["network"] = "ws"
                ws = {"path": transport.get("path", "/")}
                host = transport.get("headers", {}).get("Host")
                if host: ws["headers"] = {"Host": host}
                proxy["ws-opts"] = ws
            elif tp == "grpc":
                proxy["network"] = "grpc"
                proxy["grpc-opts"] = {"grpc-service-name": transport.get("service_name", "")}
        return proxy

    if t == "vmess":
        tls = ob.get("tls", {})
        transport = ob.get("transport", {})
        proxy = {"type": "vmess", "server": server, "port": port, "uuid": ob.get("uuid", ""), "alterId": ob.get("alter_id", 0), "cipher": ob.get("cipher", "auto"), "tls": tls.get("enabled", False), "skip-cert-verify": tls.get("insecure", True), "udp": True}
        if tls.get("server_name"): proxy["servername"] = tls["server_name"]
        if transport:
            tp = transport.get("type", "")
            if tp == "ws":
                proxy["network"] = "ws"
                ws = {"path": transport.get("path", "/")}
                host = transport.get("headers", {}).get("Host")
                if host: ws["headers"] = {"Host": host}
                proxy["ws-opts"] = ws
        return proxy

    if t == "shadowsocks":
        return {"type": "ss", "server": server, "port": port, "cipher": ob.get("method", ob.get("cipher", "auto")), "password": ob.get("password", ""), "udp": True}

    if t == "hysteria2":
        tls = ob.get("tls", {})
        proxy = {"type": "hysteria2", "server": server, "port": port, "password": ob.get("password", ""), "skip-cert-verify": tls.get("insecure", True), "udp": True}
        if tls.get("server_name"): proxy["sni"] = tls["server_name"]
        return proxy

    return None


def build_provider(data: dict) -> str:
    proxies_input = data.get("proxies", [])

    entries = []
    for entry in proxies_input:
        ob = entry.get("outbound", entry)
        tag = ob.get("tag", "")
        m = CC_RE.match(tag)
        if not m: continue
        cc = m.group(1)
        isp = entry.get("isp", "") or ""
        entries.append({"tag": tag, "cc": cc, "isp": isp, "outbound": ob})

    isp_groups = defaultdict(list)
    for e in entries:
        isp_clean = sanitize_isp(e["isp"]) or "Unknown"
        key = (e["cc"], isp_clean)
        isp_groups[key].append(e["tag"])

    tag_to_name = {}
    for (cc, isp_clean), tags in isp_groups.items():
        flag = cc_to_flag(cc)
        if len(tags) == 1:
            tag_to_name[tags[0]] = f"{flag}{isp_clean}"
        else:
            for i, tag in enumerate(tags, 1):
                tag_to_name[tag] = f"{flag}{isp_clean}-{i}"

    proxies = []
    for entry in proxies_input:
        ob = entry.get("outbound", entry)
        proxy = convert_outbound(ob)
        if not proxy: continue
        tag = ob.get("tag", "")
        proxy["name"] = tag_to_name.get(tag, tag)
        proxies.append(proxy)

    lines = [
        "# Auto-generated by free-proxy-gateway",
        "# Source: https://github.com/rickicode/free-proxy-gateway",
        f"# Generated: {data.get('generated_at', 'unknown')}",
        f"# Live proxies: {len(proxies)}",
        "",
        "proxies:",
    ]
    for p in proxies:
        lines.append(f"  - {json.dumps(p, ensure_ascii=False)}")
    lines.append("")
    return "\n".join(lines)


def main():
    if len(sys.argv) < 3:
        print("Usage: convert_to_mihomo.py <input.json> <output.yml>")
        sys.exit(1)
    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])
    data = json.loads(input_path.read_text())
    content = build_provider(data)
    output_path.write_text(content)
    print(f"Written {output_path} ({len(content)} bytes, {len(content.splitlines())} lines)")


if __name__ == "__main__":
    main()
