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


# ============================================================
# Comprehensive Check-IP domain list
# ============================================================
CHECK_IP_RULES = [
    # --- Plain text IP services ---
    "DOMAIN,ifconfig.me,CHECK-IP",
    "DOMAIN-SUFFIX,ifconfig.me,CHECK-IP",
    "DOMAIN,ifconfig.co,CHECK-IP",
    "DOMAIN-SUFFIX,ifconfig.co,CHECK-IP",
    "DOMAIN,icanhazip.com,CHECK-IP",
    "DOMAIN-SUFFIX,icanhazip.com,CHECK-IP",
    "DOMAIN,ip.me,CHECK-IP",
    "DOMAIN,ip.sb,CHECK-IP",
    "DOMAIN-SUFFIX,ip.sb,CHECK-IP",
    "DOMAIN,api.ip.sb,CHECK-IP",
    "DOMAIN,whatismyip.akamai.com,CHECK-IP",
    "DOMAIN,checkip.amazonaws.com,CHECK-IP",
    "DOMAIN,myip.opendns.com,CHECK-IP",
    "DOMAIN,whoami.akamai.net,CHECK-IP",
    "DOMAIN,echo.irc.wtf,CHECK-IP",
    "DOMAIN,tnx.nl,CHECK-IP",
    "DOMAIN,l2.io,CHECK-IP",
    "DOMAIN,ipecho.net,CHECK-IP",
    "DOMAIN-SUFFIX,ipecho.net,CHECK-IP",
    "DOMAIN,wtfismyip.com,CHECK-IP",
    "DOMAIN-SUFFIX,wtfismyip.com,CHECK-IP",
    "DOMAIN,ipinfo.io,CHECK-IP",
    "DOMAIN-SUFFIX,ipinfo.io,CHECK-IP",
    "DOMAIN,myip.dnsomatic.com,CHECK-IP",
    "DOMAIN,traceip.net,CHECK-IP",
    "DOMAIN-SUFFIX,traceip.net,CHECK-IP",

    # --- JSON API IP services ---
    "DOMAIN,api.ipify.org,CHECK-IP",
    "DOMAIN-SUFFIX,ipify.org,CHECK-IP",
    "DOMAIN,api.ip.sb,CHECK-IP",
    "DOMAIN,ip.3322.net,CHECK-IP",
    "DOMAIN,ip.cip.cc,CHECK-IP",
    "DOMAIN-SUFFIX,ipapi.co,CHECK-IP",
    "DOMAIN,api.ipapi.com,CHECK-IP",
    "DOMAIN-SUFFIX,ipwhois.io,CHECK-IP",
    "DOMAIN,ipwho.is,CHECK-IP",
    "DOMAIN-SUFFIX,ipwhois.app,CHECK-IP",
    "DOMAIN-SUFFIX,ipstack.com,CHECK-IP",
    "DOMAIN-SUFFIX,ipgeolocation.io,CHECK-IP",
    "DOMAIN-SUFFIX,db-ip.com,CHECK-IP",
    "DOMAIN-SUFFIX,ip2location.com,CHECK-IP",
    "DOMAIN-SUFFIX,ip2c.org,CHECK-IP",
    "DOMAIN-SUFFIX,extreme-ip-lookup.com,CHECK-IP",
    "DOMAIN-SUFFIX,ipapi.is,CHECK-IP",
    "DOMAIN-SUFFIX,bigdatacloud.com,CHECK-IP",
    "DOMAIN-SUFFIX,abstractapi.com,CHECK-IP",
    "DOMAIN-SUFFIX,seeip.org,CHECK-IP",
    "DOMAIN,api.seeip.org,CHECK-IP",
    "DOMAIN,ip.anysrc.com,CHECK-IP",
    "DOMAIN,ip-api.com,CHECK-IP",
    "DOMAIN-SUFFIX,ip-api.com,CHECK-IP",
    "DOMAIN-SUFFIX,ipapi.com,CHECK-IP",
    "DOMAIN,ip.taobao.com,CHECK-IP",
    "DOMAIN,ip.qq.com,CHECK-IP",
    "DOMAIN,ip.echo.qq.com,CHECK-IP",
    "DOMAIN-SUFFIX,ip.cn,CHECK-IP",
    "DOMAIN-SUFFIX,ipip.net,CHECK-IP",
    "DOMAIN,myip.ipip.net,CHECK-IP",
    "DOMAIN,ip.dnsexit.com,CHECK-IP",
    "DOMAIN,ip.smart-ip.net,CHECK-IP",
    "DOMAIN,ip4.me,CHECK-IP",
    "DOMAIN-SUFFIX,ip4.me,CHECK-IP",
    "DOMAIN,api64.ipify.org,CHECK-IP",
    "DOMAIN,api.bigdatacloud.net,CHECK-IP",
    "DOMAIN,geolocation-db.com,CHECK-IP",
    "DOMAIN-SUFFIX,geolocation-db.com,CHECK-IP",
    "DOMAIN,ipwhois.app,CHECK-IP",
    "DOMAIN,ip-api.io,CHECK-IP",
    "DOMAIN-SUFFIX,ip-api.io,CHECK-IP",
    "DOMAIN,ipfind.co,CHECK-IP",
    "DOMAIN-SUFFIX,ipfind.co,CHECK-IP",
    "DOMAIN,ipapi.com,CHECK-IP",
    "DOMAIN,ipgeolocation.abstractapi.com,CHECK-IP",
    "DOMAIN,ipapi.co,CHECK-IP",
    "DOMAIN,ip.520114.xyz,CHECK-IP",
    "DOMAIN,ip.bsc.cool,CHECK-IP",
    "DOMAIN,ip.900cha.com,CHECK-IP",
    "DOMAIN,ip.useragentinfo.com,CHECK-IP",

    # --- Web-based IP checker sites ---
    "DOMAIN,whatismyipaddress.com,CHECK-IP",
    "DOMAIN-SUFFIX,whatismyipaddress.com,CHECK-IP",
    "DOMAIN,myip.com,CHECK-IP",
    "DOMAIN-SUFFIX,myip.com,CHECK-IP",
    "DOMAIN-SUFFIX,ipchicken.com,CHECK-IP",
    "DOMAIN-SUFFIX,ipleak.net,CHECK-IP",
    "DOMAIN,ipleak.net,CHECK-IP",
    "DOMAIN-SUFFIX,iplocation.net,CHECK-IP",
    "DOMAIN,iplocation.net,CHECK-IP",
    "DOMAIN-SUFFIX,ip2location.com,CHECK-IP",
    "DOMAIN,ip2location.com,CHECK-IP",
    "DOMAIN-SUFFIX,ipfingerprints.com,CHECK-IP",
    "DOMAIN,ipfingerprints.com,CHECK-IP",
    "DOMAIN-SUFFIX,whatismyip.com,CHECK-IP",
    "DOMAIN,whatismyip.com,CHECK-IP",
    "DOMAIN-SUFFIX,ipchecking.com,CHECK-IP",
    "DOMAIN,ipchecking.com,CHECK-IP",
    "DOMAIN-SUFFIX,ipaddress.sh,CHECK-IP",
    "DOMAIN,ipaddress.sh,CHECK-IP",
    "DOMAIN-SUFFIX,myipaddress.com,CHECK-IP",
    "DOMAIN,myipaddress.com,CHECK-IP",
    "DOMAIN-SUFFIX,showip.net,CHECK-IP",
    "DOMAIN,showip.net,CHECK-IP",
    "DOMAIN-SUFFIX,my-ip.io,CHECK-IP",
    "DOMAIN,my-ip.io,CHECK-IP",
    "DOMAIN-SUFFIX,ipinfo.io,CHECK-IP",
    "DOMAIN,ipinfo.io,CHECK-IP",
    "DOMAIN-SUFFIX,ipapi.is,CHECK-IP",
    "DOMAIN,ipapi.is,CHECK-IP",
    "DOMAIN-SUFFIX,whoer.net,CHECK-IP",
    "DOMAIN,whoer.net,CHECK-IP",
    "DOMAIN-SUFFIX,browserleaks.com,CHECK-IP",
    "DOMAIN,browserleaks.com,CHECK-IP",
    "DOMAIN-SUFFIX,coveryourip.com,CHECK-IP",
    "DOMAIN,coveryourip.com,CHECK-IP",
    "DOMAIN-SUFFIX,hide-my-ip.com,CHECK-IP",
    "DOMAIN-SUFFIX,ipvoid.com,CHECK-IP",
    "DOMAIN,ipvoid.com,CHECK-IP",
    "DOMAIN-SUFFIX,iptracker.io,CHECK-IP",
    "DOMAIN,iptracker.io,CHECK-IP",
    "DOMAIN-SUFFIX,ip-tracker.org,CHECK-IP",
    "DOMAIN,ip-tracker.org,CHECK-IP",
    "DOMAIN-SUFFIX,iplogger.org,CHECK-IP",
    "DOMAIN-SUFFIX,grabify.link,CHECK-IP",
    "DOMAIN,iplogger.com,CHECK-IP",
    "DOMAIN,whatismyip.live,CHECK-IP",
    "DOMAIN-SUFFIX,whatismyip.live,CHECK-IP",
    "DOMAIN,ipinfo.telstra.com,CHECK-IP",
    "DOMAIN,check-my-ip.net,CHECK-IP",
    "DOMAIN-SUFFIX,check-my-ip.net,CHECK-IP",
    "DOMAIN,ipcheck.me,CHECK-IP",
    "DOMAIN-SUFFIX,ipcheck.me,CHECK-IP",
    "DOMAIN,showmyip.com,CHECK-IP",
    "DOMAIN-SUFFIX,showmyip.com,CHECK-IP",
    "DOMAIN,whatismyip.host,CHECK-IP",
    "DOMAIN-SUFFIX,whatismyip.host,CHECK-IP",
    "DOMAIN,ipmonkey.com,CHECK-IP",
    "DOMAIN-SUFFIX,ipmonkey.com,CHECK-IP",
    "DOMAIN,ipinfo.nu,CHECK-IP",
    "DOMAIN-SUFFIX,ipinfo.nu,CHECK-IP",
    "DOMAIN,ipaddress.com,CHECK-IP",
    "DOMAIN-SUFFIX,ipaddress.com,CHECK-IP",
    "DOMAIN,ipaddress.my,CHECK-IP",
    "DOMAIN-SUFFIX,ipaddress.my,CHECK-IP",
    "DOMAIN,checkip.net,CHECK-IP",
    "DOMAIN-SUFFIX,checkip.net,CHECK-IP",
    "DOMAIN,ip-checker.net,CHECK-IP",
    "DOMAIN-SUFFIX,ip-checker.net,CHECK-IP",
    "DOMAIN,ip-lookup.net,CHECK-IP",
    "DOMAIN-SUFFIX,ip-lookup.net,CHECK-IP",
    "DOMAIN,ipaddress.world,CHECK-IP",
    "DOMAIN-SUFFIX,ipaddress.world,CHECK-IP",
    "DOMAIN,ip-details.com,CHECK-IP",
    "DOMAIN-SUFFIX,ip-details.com,CHECK-IP",
    "DOMAIN,ip-api.com,CHECK-IP",
    "DOMAIN,mylocation.org,CHECK-IP",
    "DOMAIN-SUFFIX,mylocation.org,CHECK-IP",
    "DOMAIN,iplocation.com,CHECK-IP",
    "DOMAIN-SUFFIX,iplocation.com,CHECK-IP",
    "DOMAIN,ipgeolocation.com,CHECK-IP",
    "DOMAIN-SUFFIX,ipgeolocation.com,CHECK-IP",
    "DOMAIN,whatismyip.lantronanetworks.com,CHECK-IP",
    "DOMAIN,ip-ping.com,CHECK-IP",
    "DOMAIN-SUFFIX,ip-ping.com,CHECK-IP",
    "DOMAIN,ipaddress.is,CHECK-IP",
    "DOMAIN-SUFFIX,ipaddress.is,CHECK-IP",
    "DOMAIN,ipaddress.fyi,CHECK-IP",
    "DOMAIN-SUFFIX,ipaddress.fyi,CHECK-IP",
    "DOMAIN,myip.ipadressen.se,CHECK-IP",
    "DOMAIN,ipinfo.io,CHECK-IP",
    "DOMAIN,ip.me,CHECK-IP",
    "DOMAIN,ipinfo.io,CHECK-IP",
    "DOMAIN-SUFFIX,dnsleaktest.com,CHECK-IP",
]


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
    proxy_groups.append({"name": "CHECK-IP", "type": "select", "proxies": ["DIRECT", "PROXY-FREE"] + [g["name"] for g in proxy_groups]})
    proxy_groups.append({"name": "SOCIAL", "type": "select", "proxies": ["DIRECT"] + [g["name"] for g in proxy_groups]})

    # HIJINETWORK = catch-all group for traffic not matched by rules
    proxy_groups.append({"name": "HIJINETWORK", "type": "select", "proxies": ["DIRECT"] + [g["name"] for g in proxy_groups]})

    # GLOBAL
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

    # Google → GOOGLE group
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

    # AI → AI group
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
    lines.append("  - DOMAIN-SUFFIX,cohere.com,AI")
    lines.append("  - DOMAIN-SUFFIX,ai21.com,AI")
    lines.append("  - DOMAIN-SUFFIX,stability.ai,AI")
    lines.append("  - DOMAIN-SUFFIX,midjourney.com,AI")
    lines.append("  - DOMAIN-SUFFIX,character.ai,AI")
    lines.append("  - DOMAIN-SUFFIX,poe.com,AI")
    lines.append("  - DOMAIN-SUFFIX,you.com,AI")
    lines.append("  - DOMAIN-SUFFIX,phind.com,AI")
    lines.append("  - DOMAIN-SUFFIX,cursor.sh,AI")
    lines.append("  - DOMAIN-SUFFIX,codeium.com,AI")
    lines.append("  - DOMAIN-SUFFIX,githubcopilot.com,AI")
    lines.append("  - DOMAIN-SUFFIX,codestral.com,AI")
    lines.append("  - DOMAIN-SUFFIX,fireworks.ai,AI")
    lines.append("  - DOMAIN-SUFFIX,anyscale.com,AI")
    lines.append("  - DOMAIN-SUFFIX,openrouter.ai,AI")
    lines.append("  - DOMAIN-SUFFIX,aimlapi.com,AI")
    lines.append("  - DOMAIN-SUFFIX,elevenlabs.io,AI")
    lines.append("  - DOMAIN-SUFFIX,suno.ai,AI")
    lines.append("  - DOMAIN-SUFFIX,runwayml.com,AI")
    lines.append("  - DOMAIN-SUFFIX,synthesia.io,AI")
    lines.append("  - DOMAIN-SUFFIX,perplexity.ai,AI")
    lines.append("  - DOMAIN-SUFFIX,search.brave.com,AI")
    lines.append("  - DOMAIN-SUFFIX,claude.com,AI")

    # Check IP → CHECK-IP group (comprehensive, 100+ domains)
    for rule in CHECK_IP_RULES:
        lines.append(f"  - {rule}")


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

    # Other
    lines.append("  - GEOSITE,github,PROXY-FREE")
    lines.append("  - GEOSITE,netflix,PROXY-FREE")

    # Fallback
    lines.append("  - MATCH,HIJINETWORK")

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
