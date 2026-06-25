#!/usr/bin/env python3
"""Register 3 WARP accounts via wgcf and output mihomo-format YAML.

Flow:
  1. wgcf generate → keypair
  2. wgcf register --accept-tos → daftar ke Cloudflare
  3. Parse private_key + addresses
  4. Output output/warp.mihomo.yml (WARP proxies in mihomo format)
  5. Save output/warp-creds.json (credentials backup)

Usage:
  python3 scripts/warp-refresh.py [--force]
  python3 scripts/warp-refresh.py --count 3

Schedule: GitHub Actions setiap 2 hari, atau cron lokal."""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

CRED_FILE = "output/warp-creds.json"
OUTPUT_FILE = "output/warp.mihomo.yml"
WGCF = "/usr/local/bin/wgcf"
COUNT = 3
PUBLIC_KEY = "bmXOC+F1FxEMF9dyiK2H5/1SUtzH0JuVo51h2wPfgyo="
ENDPOINT = "engage.cloudflareclient.com"
ENDPOINT_PORT = 2408


def info(msg):
    print(f"  → {msg}")


def ok(msg):
    print(f"  ✓ {msg}")


def fail(msg):
    print(f"  ✗ {msg}")


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def ensure_wgcf():
    if os.path.exists(WGCF):
        return
    info("Downloading wgcf...")
    arch = run(["uname", "-m"]).stdout.strip()
    a = {"x86_64": "amd64", "aarch64": "arm64"}.get(arch, "amd64")
    url = f"https://github.com/ViRb3/wgcf/releases/latest/download/wgcf_{a}"
    try:
        import urllib.request
        req = urllib.request.Request(url, headers={"User-Agent": "curl/8.0"})
        data = urllib.request.urlopen(req, timeout=30).read()
        with open(WGCF, "wb") as f:
            f.write(data)
        os.chmod(WGCF, 0o755)
        ok(f"wgcf installed: {WGCF}")
    except Exception as e:
        fail(f"Download wgcf failed: {e}")
        sys.exit(1)


def register_warp():
    """Register satu akun WARP. Return dict atau (None, error_msg)."""
    work = tempfile.mkdtemp(prefix="warp-")
    try:
        r = run([WGCF, "generate"], cwd=work)
        if r.returncode != 0:
            return None, f"generate failed: {r.stderr.strip()[:100]}"

        r = run([WGCF, "register", "--accept-tos"], cwd=work)
        if r.returncode != 0:
            err = r.stderr.strip()
            if "429" in err:
                return None, "RATE_LIMITED"
            return None, f"register failed: {err[:100]}"

        r = run([WGCF, "generate"], cwd=work)
        if r.returncode != 0:
            return None, f"config generate failed: {r.stderr.strip()[:100]}"

        account = {}
        acct_file = os.path.join(work, "wgcf-account.toml")
        if os.path.exists(acct_file):
            with open(acct_file) as f:
                for line in f:
                    if "device_id" in line:
                        account["id"] = line.split("=")[-1].strip().strip('"')

        conf_file = os.path.join(work, "wgcf-profile.conf")
        if not os.path.exists(conf_file):
            return None, "wgcf-profile.conf not found"

        with open(conf_file) as f:
            conf = f.read()

        priv = re.search(r"PrivateKey\s*=\s*(\S+)", conf)
        addr = re.search(r"Address\s*=\s*(\S+)", conf)
        if not priv or not addr:
            return None, "cannot parse wgcf config"

        addrs = addr.group(1).split(",")
        return {
            "private_key": priv.group(1),
            "address_v4": addrs[0].strip(),
            "address_v6": addrs[1].strip() if len(addrs) > 1 else "",
            "client_id": account.get("id", ""),
        }, None
    finally:
        shutil.rmtree(work, ignore_errors=True)


def load_creds():
    if os.path.exists(CRED_FILE):
        try:
            with open(CRED_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_creds(creds):
    os.makedirs(os.path.dirname(CRED_FILE), exist_ok=True)
    with open(CRED_FILE, "w") as f:
        json.dump(creds, f, indent=2)


def build_warp_yaml(creds):
    """Generate mihomo YAML for WARP proxies + groups."""
    lines = [
        "# Auto-generated WARP proxies",
        "# Source: https://github.com/rickicode/free-proxy-singbox",
        f"# Generated: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}",
        "",
        "proxies:",
    ]

    for i in range(1, COUNT + 1):
        label = f"WARP{i}"
        d = creds.get(label, {})
        if not d.get("private_key"):
            continue
        lines.append(f"  - name: {label}")
        lines.append(f"    type: wireguard")
        lines.append(f"    server: {ENDPOINT}")
        lines.append(f"    port: {ENDPOINT_PORT}")
        lines.append(f"    private-key: {d['private_key']}")
        lines.append(f"    public-key: {PUBLIC_KEY}")
        lines.append(f"    ip: {d.get('address_v4', '172.16.0.2')}")
        if d.get("address_v6"):
            lines.append(f"    ipv6: \"{d['address_v6']}\"")
        lines.append(f"    allowed-ips:")
        lines.append(f"      - 0.0.0.0/0")
        lines.append(f"    udp: true")
        lines.append(f"    mtu: 1280")
        lines.append("")

    # WARP groups
    warp_names = [f"WARP{i}" for i in range(1, COUNT + 1) if creds.get(f"WARP{i}", {}).get("private_key")]
    if not warp_names:
        return ""

    lines.append("proxy-groups:")
    # Load-balance group
    lines.append(f"  - name: WARP-LB")
    lines.append(f"    type: load-balance")
    lines.append(f"    proxies:")
    for name in warp_names:
        lines.append(f"      - {name}")
    lines.append(f"    url: http://www.gstatic.com/generate_204")
    lines.append(f"    interval: 300")
    lines.append("")
    # Select group
    lines.append(f"  - name: PROXY-WARP")
    lines.append(f"    type: select")
    lines.append(f"    proxies:")
    lines.append(f"      - WARP-LB")
    for name in warp_names:
        lines.append(f"      - {name}")
    lines.append(f"      - DIRECT")
    lines.append("")

    return "\n".join(lines)


def main():
    force = "--force" in sys.argv
    print(f"\nWARP Refresh")
    print(f"{time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}")
    print(f"Registering {COUNT} accounts\n")

    ensure_wgcf()

    creds = load_creds()
    need_refresh = []

    for i in range(1, COUNT + 1):
        label = f"WARP{i}"
        if not force:
            last = creds.get(label, {}).get("refreshed_at", "")
            if last:
                try:
                    t = time.mktime(time.strptime(last, "%Y-%m-%dT%H:%M:%SZ"))
                    days = (time.time() - t) / 86400
                    if days < 2:
                        ok(f"{label} masih fresh ({days:.1f} hari)")
                        continue
                except Exception:
                    pass
        need_refresh.append(label)

    if not need_refresh:
        print(f"\nSemua WARP masih fresh. Gunakan --force untuk paksa refresh.\n")
    else:
        rate_limited = False
        for label in need_refresh:
            print()
            info(f"Registering {label}...")
            result, err = register_warp()
            if err == "RATE_LIMITED":
                fail(f"{label}: Rate limited — coba lagi nanti")
                rate_limited = True
                time.sleep(5)
                continue
            if err:
                fail(f"{label}: {err}")
                continue
            if not result:
                fail(f"{label}: Gagal register")
                continue

            ok(f"{label}: {result['address_v4']} / {result['address_v6'][:30]}...")
            creds[label] = {
                "private_key": result["private_key"],
                "address_v4": result["address_v4"],
                "address_v6": result["address_v6"],
                "client_id": result.get("client_id", ""),
                "refreshed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            save_creds(creds)
            time.sleep(2)

        if rate_limited:
            print(f"\n⚠ Beberapa akun kena rate limit. Akan dicoba lagi nanti.\n")

    # Generate mihomo YAML
    yaml_content = build_warp_yaml(creds)
    if yaml_content:
        os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
        with open(OUTPUT_FILE, "w") as f:
            f.write(yaml_content)
        ok(f"Written {OUTPUT_FILE} ({yaml_content.count(chr(10))} lines)")
    else:
        fail("No valid WARP credentials — skip YAML generation")
        sys.exit(1)

    # Summary
    print(f"\nWARP credentials:")
    for i in range(1, COUNT + 1):
        label = f"WARP{i}"
        d = creds.get(label, {})
        if d:
            print(f"  {label}: {d.get('address_v4', '?')} (refreshed: {d.get('refreshed_at', '?')})")
        else:
            print(f"  {label}: not registered")


if __name__ == "__main__":
    main()
