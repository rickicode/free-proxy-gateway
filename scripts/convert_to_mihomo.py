#!/usr/bin/env python3
"""Convert free-proxy-singbox live-proxies.json to mihomo proxy-provider YAML.

Output: proxies + proxy-groups (PROXY-FREE, PROXY-ID, PROXY-SG, PROXY-US, PROXY-ASIA, PROXY-EU).
Groups/rules/DNS config live in openwrt/base.yml (proxy-providers reference this file).

Proxy names: {flag}{ISP} or {flag}{ISP}-{N} (no dash between flag and ISP)."""

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

REGIONS = {
    "ASIA": ["ID", "SG", "MY", "TH", "VN", "PH", "JP", "KR", "TW", "HK", "IN", "BD", "PK", "LK", "NP", "MM", "KH", "LA", "BN", "TL", "CN", "MN", "UZ", "KZ"],
    "EU": ["DE", "FR", "NL", "GB", "SE", "NO", "FI", "DK", "PL", "CZ", "AT", "CH", "BE", "ES", "PT", "IT", "RO", "HU", "BG", "HR", "SK", "SI", "LT", "LV", "EE", "IE", "GR", "CY", "MT", "LU", "UA", "RU"],
    "US": ["US", "CA"],
    "SA": ["BR", "AR", "CL", "CO", "PE", "MX", "EC", "VE", "UY", "PY", "BO", "PA", "CR", "DO", "GT", "HN", "SV", "NI"],
    "AF": ["ZA", "NG", "EG", "KE", "GH", "TN", "MA", "DZ", "ET", "TZ", "UG"],
    "OC": ["AU", "NZ", "FJ"],
    "ME": ["AE", "SA", "IL", "TR", "QA", "KW", "BH", "OM", "JO", "LB", "IQ", "IR"],
}


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


def cc_to_region(cc: str) -> str | None:
    for region, codes in REGIONS.items():
        if cc in codes:
            return region
    return None


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
    groups_data = data.get("groups", {})

    entries = []
    for entry in proxies_input:
        ob = entry.get("outbound", entry)
        tag = ob.get("tag", "")
        m = CC_RE.match(tag)
        if not m: continue
        cc = m.group(1)
        isp = entry.get("isp", "") or ""
        entries.append({"tag": tag, "cc": cc, "isp": isp, "outbound": ob})

    # tag -> display name (flag + ISP, no dash)
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

    # Build proxies
    proxies = []
    tag_to_cc = {}
    for entry in proxies_input:
        ob = entry.get("outbound", entry)
        proxy = convert_outbound(ob)
        if not proxy: continue
        tag = ob.get("tag", "")
        proxy["name"] = tag_to_name.get(tag, tag)
        proxies.append(proxy)
        m = CC_RE.match(tag)
        if m:
            tag_to_cc[tag] = m.group(1)

    # Build proxy-groups from groups data (country groups)
    lines = [
        "# Auto-generated by free-proxy-singbox",
        "# Source: https://github.com/rickicode/free-proxy-singbox",
        f"# Generated: {data.get('generated_at', 'unknown')}",
        f"# Live proxies: {len(proxies)}",
        "",
        "proxies:",
    ]

    for p in proxies:
        lines.append(f"  - {json.dumps(p, ensure_ascii=False)}")

    # Country groups from scan data
    lines.extend(["", "proxy-groups:"])
    for gname, gtags in groups_data.items():
        if not isinstance(gtags, list) or not gtags:
            continue
        matching = [tag_to_name[t] for t in gtags if t in tag_to_name]
        if not matching:
            continue
        lines.append(f"  - name: {gname}")
        lines.append(f"    type: url-test")
        lines.append(f"    proxies:")
        for name in matching:
            lines.append(f"      - {name}")
        lines.append(f"    url: http://www.gstatic.com/generate_204")
        lines.append(f"    interval: 300")
        lines.append("")

    # Regional groups
    country_group_names = set(groups_data.keys())
    for region, codes in REGIONS.items():
        gname = f"PROXY-{region}"
        if gname in country_group_names:
            continue  # skip if country group with same name exists
        region_names = []
        for entry in proxies_input:
            ob = entry.get("outbound", entry)
            tag = ob.get("tag", "")
            m = CC_RE.match(tag)
            if not m: continue
            if m.group(1) in codes and tag in tag_to_name:
                name = tag_to_name[tag]
                if name not in region_names:
                    region_names.append(name)
        if not region_names:
            continue
        lines.append(f"  - name: PROXY-{region}")
        lines.append(f"    type: url-test")
        lines.append(f"    proxies:")
        for name in region_names:
            lines.append(f"      - {name}")
        lines.append(f"    url: http://www.gstatic.com/generate_204")
        lines.append(f"    interval: 300")
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
    groups = data.get("groups", {})
    region_groups = [r for r in REGIONS if any(
        cc in REGIONS[r] for entry in data.get("proxies", [])
        for ob in [entry.get("outbound", entry)]
        for m in [CC_RE.match(ob.get("tag", ""))]
        if m
    )]
    print(f"Written {output_path} ({len(content)} bytes)")
    print(f"  Country groups: {', '.join(groups.keys())}")
    print(f"  Regional groups: {', '.join(f'PROXY-{r}' for r in region_groups)}")


if __name__ == "__main__":
    main()
