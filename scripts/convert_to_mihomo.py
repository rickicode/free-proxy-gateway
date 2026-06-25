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


def build_mihomo(data: dict) -> str:
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

    isp_groups = defaultdict(list)
    for e in entries:
        isp_clean = sanitize_isp(e["isp"]) or "Unknown"
        key = (e["cc"], isp_clean)
        isp_groups[key].append(e["tag"])

    tag_to_name = {}
    for (cc, isp_clean), tags in isp_groups.items():
        flag = cc_to_flag(cc)
        if len(tags) == 1:
            tag_to_name[tags[0]] = f"{flag}-{isp_clean}"
        else:
            for i, tag in enumerate(tags, 1):
                tag_to_name[tag] = f"{flag}-{isp_clean}-{i}"

    proxies = []
    proxy_names = []
    for entry in proxies_input:
        ob = entry.get("outbound", entry)
        proxy = convert_outbound(ob)
        if not proxy: continue
        tag = ob.get("tag", "")
        proxy["name"] = tag_to_name.get(tag, tag)
        proxies.append(proxy)
        proxy_names.append(proxy["name"])

    # Build proxy groups
    proxy_groups = []
    for gname, gtags in groups_data.items():
        if not isinstance(gtags, list) or not gtags: continue
        matching = [tag_to_name[t] for t in gtags if t in tag_to_name]
        if matching:
            proxy_groups.append({"name": gname, "type": "url-test", "proxies": matching, "url": "http://www.gstatic.com/generate_204", "interval": 300})

    # Dedicated groups
    proxy_groups.append({"name": "GOOGLE", "type": "select", "proxies": ["DIRECT"] + [g["name"] for g in proxy_groups]})
    proxy_groups.append({"name": "AI", "type": "select", "proxies": ["DIRECT"] + [g["name"] for g in proxy_groups]})
    proxy_groups.append({"name": "CHECK-IP", "type": "select", "proxies": ["DIRECT"] + [g["name"] for g in proxy_groups]})
    proxy_groups.append({"name": "SPEEDTEST", "type": "select", "proxies": ["DIRECT"] + [g["name"] for g in proxy_groups]})
    proxy_groups.append({"name": "SOCIAL", "type": "select", "proxies": ["DIRECT"] + [g["name"] for g in proxy_groups]})

    # GLOBAL: all groups + DIRECT
    group_names = [g["name"] for g in proxy_groups]
    proxy_groups.insert(0, {"name": "GLOBAL", "type": "select", "proxies": ["DIRECT"] + group_names})

    # Build YAML
    lines = [
        "# Auto-generated by free-proxy-singbox",
        "# Source: https://github.com/rickicode/free-proxy-singbox",
        f"# Generated: {data.get('generated_at', 'unknown')}",
        f"# Live proxies: {data.get('live_count', len(proxy_names))}",
        "", "mixed-port: 7890", "allow-lan: true", "bind-address: '*'", "mode: rule", "log-level: warning", "ipv6: false", "",
        "dns:", "  enable: true", "  listen: :1053", "  enhanced-mode: fake-ip", "  fake-ip-range: 198.18.0.1/16",
        "  default-nameserver:", "    - 223.5.5.5", "    - 8.8.8.8",
        "  nameserver:", "    - https://223.5.5.5/dns-query", "    - https://1.1.1.1/dns-query",
        "  nameserver-policy:", "    'geosite:private,cn': 223.5.5.5", "    'geosite:geolocation-!cn': https://1.1.1.1/dns-query",
        "", "proxies:",
    ]

    for p in proxies:
        lines.append(f"  - {json.dumps(p, ensure_ascii=False)}")

    lines.extend(["", "proxy-groups:"])
    for g in proxy_groups:
        lines.append(f"  - {json.dumps(g, ensure_ascii=False)}")

    lines.extend(["", "rules:"])

    # Block ads
    lines.append("  - GEOSITE,category-ads-all,REJECT")

    # Private / LAN
    lines.append("  - GEOSITE,private,DIRECT")
    lines.append("  - GEOIP,private,DIRECT,no-resolve")

    # China direct
    lines.append("  - GEOSITE,cn,DIRECT")
    lines.append("  - GEOIP,cn,DIRECT,no-resolve")

    # Google services → GOOGLE group
    lines.append("  - GEOSITE,google,GOOGLE")
    lines.append("  - GEOSITE,googlefcm,GOOGLE")
    lines.append("  - DOMAIN-SUFFIX,google.com,GOOGLE")
    lines.append("  - DOMAIN-SUFFIX,googleapis.com,GOOGLE")
    lines.append("  - DOMAIN-SUFFIX,googlevideo.com,GOOGLE")
    lines.append("  - DOMAIN-SUFFIX,gstatic.com,GOOGLE")
    lines.append("  - DOMAIN-SUFFIX,ggpht.com,GOOGLE")
    lines.append("  - DOMAIN-SUFFIX,youtube.com,GOOGLE")
    lines.append("  - DOMAIN-SUFFIX,ytimg.com,GOOGLE")
    lines.append("  - DOMAIN-SUFFIX,googleusercontent.com,GOOGLE")
    lines.append("  - DOMAIN-SUFFIX,googleadservices.com,GOOGLE")
    lines.append("  - DOMAIN-SUFFIX,googlesyndication.com,GOOGLE")

    # AI Services → AI group
    lines.append("  - GEOSITE,openai,AI")
    lines.append("  - DOMAIN-SUFFIX,openai.com,AI")
    lines.append("  - DOMAIN-SUFFIX,chatgpt.com,AI")
    lines.append("  - DOMAIN-SUFFIX,oaiusercontent.com,AI")
    lines.append("  - DOMAIN-SUFFIX,ai.azure.com,AI")
    lines.append("  - DOMAIN-SUFFIX,anthropic.com,AI")
    lines.append("  - DOMAIN-SUFFIX,claude.ai,AI")
    lines.append("  - DOMAIN-SUFFIX,perplexity.ai,AI")
    lines.append("  - DOMAIN-SUFFIX,copilot.microsoft.com,AI")
    lines.append("  - DOMAIN-SUFFIX,groq.com,AI")
    lines.append("  - DOMAIN-SUFFIX,mistral.ai,AI")
    lines.append("  - DOMAIN-SUFFIX,gemini.google.com,AI")
    lines.append("  - DOMAIN-SUFFIX,bard.google.com,AI")
    lines.append("  - DOMAIN-SUFFIX,deepseek.com,AI")
    lines.append("  - DOMAIN-SUFFIX,kimi.ai,AI")
    lines.append("  - DOMAIN-SUFFIX,doubao.com,AI")
    lines.append("  - DOMAIN-SUFFIX,zhipu.ai,AI")
    lines.append("  - DOMAIN-SUFFIX,moonshot.cn,AI")
    lines.append("  - DOMAIN-SUFFIX,minimaxi.com,AI")
    lines.append("  - DOMAIN-SUFFIX,baichuan-ai.com,AI")
    lines.append("  - DOMAIN-SUFFIX,qwen.ai,AI")
    lines.append("  - DOMAIN-SUFFIX,tongyi.aliyun.com,AI")
    lines.append("  - DOMAIN-SUFFIX,huggingface.co,AI")
    lines.append("  - DOMAIN-SUFFIX,replicate.com,AI")
    lines.append("  - DOMAIN-SUFFIX,together.ai,AI")

    # Check IP → CHECK-IP group (comprehensive list)
    lines.append("  - DOMAIN-SUFFIX,ifconfig.me,CHECK-IP")
    lines.append("  - DOMAIN-SUFFIX,ifconfig.co,CHECK-IP")
    lines.append("  - DOMAIN,api.ipify.org,CHECK-IP")
    lines.append("  - DOMAIN,icanhazip.com,CHECK-IP")
    lines.append("  - DOMAIN-SUFFIX,ipinfo.io,CHECK-IP")
    lines.append("  - DOMAIN-SUFFIX,ip.sb,CHECK-IP")
    lines.append("  - DOMAIN-SUFFIX,ip-api.com,CHECK-IP")
    lines.append("  - DOMAIN,whatismyipaddress.com,CHECK-IP")
    lines.append("  - DOMAIN,myip.com,CHECK-IP")
    lines.append("  - DOMAIN-SUFFIX,ipleak.net,CHECK-IP")
    lines.append("  - DOMAIN,ip.me,CHECK-IP")
    lines.append("  - DOMAIN-SUFFIX,ipchicken.com,CHECK-IP")
    lines.append("  - DOMAIN,checkip.amazonaws.com,CHECK-IP")
    lines.append("  - DOMAIN-SUFFIX,ipinfo.io,CHECK-IP")
    lines.append("  - DOMAIN,api.ip.sb,CHECK-IP")
    lines.append("  - DOMAIN,ip.3322.net,CHECK-IP")
    lines.append("  - DOMAIN,ip.cip.cc,CHECK-IP")
    lines.append("  - DOMAIN-SUFFIX,ipapi.co,CHECK-IP")
    lines.append("  - DOMAIN-SUFFIX,ipwhois.io,CHECK-IP")
    lines.append("  - DOMAIN-SUFFIX,ipstack.com,CHECK-IP")
    lines.append("  - DOMAIN-SUFFIX,ipgeolocation.io,CHECK-IP")
    lines.append("  - DOMAIN-SUFFIX,db-ip.com,CHECK-IP")
    lines.append("  - DOMAIN-SUFFIX,ip2location.com,CHECK-IP")
    lines.append("  - DOMAIN-SUFFIX,ip2c.org,CHECK-IP")
    lines.append("  - DOMAIN-SUFFIX,extreme-ip-lookup.com,CHECK-IP")
    lines.append("  - DOMAIN-SUFFIX,ipapi.is,CHECK-IP")
    lines.append("  - DOMAIN-SUFFIX,bigdatacloud.com,CHECK-IP")
    lines.append("  - DOMAIN-SUFFIX,abstractapi.com,CHECK-IP")
    lines.append("  - DOMAIN-SUFFIX,ipwhois.app,CHECK-IP")
    lines.append("  - DOMAIN,myip.opendns.com,CHECK-IP")
    lines.append("  - DOMAIN-SUFFIX,seeip.org,CHECK-IP")
    lines.append("  - DOMAIN-SUFFIX,ipify.org,CHECK-IP")
    lines.append("  - DOMAIN,ip.anysrc.com,CHECK-IP")
    lines.append("  - DOMAIN,whatismyip.akamai.com,CHECK-IP")
    lines.append("  - DOMAIN,ip.echo.qq.com,CHECK-IP")
    lines.append("  - DOMAIN,ip.taobao.com,CHECK-IP")
    lines.append("  - DOMAIN-SUFFIX,ip.cn,CHECK-IP")
    lines.append("  - DOMAIN-SUFFIX,ipip.net,CHECK-IP")

    # Speedtest → SPEEDTEST group
    lines.append("  - DOMAIN-SUFFIX,speedtest.net,SPEEDTEST")
    lines.append("  - DOMAIN-SUFFIX,speedtest.cn,SPEEDTEST")
    lines.append("  - DOMAIN,fast.com,SPEEDTEST")
    lines.append("  - DOMAIN-SUFFIX,fast.com,SPEEDTEST")
    lines.append("  - DOMAIN,speed.cloudflare.com,SPEEDTEST")
    lines.append("  - DOMAIN-SUFFIX,nperf.com,SPEEDTEST")
    lines.append("  - DOMAIN-SUFFIX,speedof.me,SPEEDTEST")
    lines.append("  - DOMAIN-SUFFIX,testmy.net,SPEEDTEST")
    lines.append("  - DOMAIN-SUFFIX,speedtestcustom.com,SPEEDTEST")
    lines.append("  - DOMAIN-SUFFIX,bandwidthplace.com,SPEEDTEST")

    # Social Media → SOCIAL group
    lines.append("  - GEOSITE,telegram,SOCIAL")
    lines.append("  - GEOSITE,twitter,SOCIAL")
    lines.append("  - GEOSITE,facebook,SOCIAL")
    lines.append("  - GEOSITE,instagram,SOCIAL")
    lines.append("  - GEOSITE,reddit,SOCIAL")
    lines.append("  - GEOSITE,whatsapp,SOCIAL")
    lines.append("  - GEOSITE,spotify,SOCIAL")
    lines.append("  - GEOSITE,line,SOCIAL")
    lines.append("  - GEOSITE,signal,SOCIAL")
    lines.append("  - GEOSITE,clubhouse,SOCIAL")
    lines.append("  - DOMAIN-SUFFIX,threads.net,SOCIAL")
    lines.append("  - DOMAIN-SUFFIX,mastodon.social,SOCIAL")
    lines.append("  - DOMAIN-SUFFIX,bsky.app,SOCIAL")

    # Other services
    lines.append("  - GEOSITE,github,PROXY-FREE")
    lines.append("  - GEOSITE,netflix,PROXY-FREE")

    # Fallback
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
    content = build_mihomo(data)
    output_path.write_text(content)
    print(f"Written {output_path} ({len(content)} bytes, {content.count(chr(10))} lines)")


if __name__ == "__main__":
    main()
