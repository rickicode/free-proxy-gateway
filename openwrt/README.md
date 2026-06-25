# OpenWrt Gateway Setup

Setup OpenWrt router sebagai proxy gateway pakai **Nikki** (mihomo engine).

## Prerequisites

- OpenWrt dengan `apk` (Alpine package manager)
- Nikki terinstall:
  ```bash
  wget -O - https://github.com/nikkinikki-org/OpenWrt-nikki/raw/refs/heads/main/feed.sh | ash
  apk add nikki luci-app-nikki
  ```

## Arsitektur

```
Client (192.168.x.x)
    ↓
OpenWrt Gateway (Nikki + Mihomo)
    ├── mixin.yaml (base config: DNS, rules, ports) ← dari repo
    ├── warp.yml (WARP proxies, per-device)          ← generate lokal
    ├── free-proxy-singbox.yml (free proxies)         ← dari repo
    └── Nikki merge ketiganya → runtime config
    ├── DIRECT (default)
    ├── GLOBAL (catch-all)
    ├── PROXY-FREE (auto-select free proxy)
    ├── PROXY-WARP (Cloudflare WARP, per-device keys)
    ├── AI group (OpenAI, Claude, dll)
    ├── GOOGLE group
    ├── CHECK-IP group
    └── SOCIAL group
```

**Split config:**
| File | Isi | Source | Update |
|---|---|---|---|
| `mixin.yaml` | DNS, ports, rules, group definitions | Repo | Auto tiap 12 jam |
| `warp.yml` | 3 WARP accounts (WireGuard keys) | **Per-device** | Auto tiap 2 hari |
| `free-proxy-singbox.yml` | Free proxy list + groups | Repo | Auto tiap 12 jam |

**Privasi:** WARP keys di-generate per-device via wgcf, tidak pernah di-commit ke repo.

## Quick Start (1 Command)

```bash
wget -O setup.sh https://raw.githubusercontent.com/rickicode/free-proxy-singbox/main/openwrt/setup.sh && ash setup.sh
```

Script ini akan:
1. Download `base.yml` → `/etc/nikki/mixin.yaml`
2. Download proxy list → `/etc/nikki/profiles/free-proxy-singbox.yml`
3. Install wgcf + generate 3 WARP accounts → `/etc/nikki/profiles/warp.yml`
4. Konfigurasi Nikki via UCI
5. Setup firewall DNS redirect
6. Install cron auto-update (proxy tiap 12 jam, WARP tiap 2 hari)
7. Start Nikki

## Manual Install

### 1. Install Nikki

```bash
wget -O - https://github.com/nikkinikki-org/OpenWrt-nikki/raw/refs/heads/main/feed.sh | ash
apk add nikki luci-app-nikki
```

### 2. Download base config (mixin)

```bash
wget -O /etc/nikki/mixin.yaml \
  https://raw.githubusercontent.com/rickicode/free-proxy-singbox/main/openwrt/base.yml
```

### 3. Download proxy list

```bash
mkdir -p /etc/nikki/profiles
wget -O /etc/nikki/profiles/free-proxy-singbox.yml \
  https://raw.githubusercontent.com/rickicode/free-proxy-singbox/main/output/live-proxies.mihomo.yml
```

### 4. Generate WARP accounts (per-device)

```bash
wget -O /etc/nikki/warp-setup.sh \
  https://raw.githubusercontent.com/rickicode/free-proxy-singbox/main/openwrt/warp-setup.sh
ash /etc/nikki/warp-setup.sh
```

Ini generate 3 akun WARP via wgcf. Keys disimpan lokal di `/etc/nikki/warp-creds.json`, tidak pernah di-commit ke repo.

### 5. Konfigurasi Nikki via UCI

```bash
uci set nikki.config.profile="file:free-proxy-singbox.yml"
uci set nikki.config.enabled=1
uci set nikki.proxy.tcp_mode=tproxy
uci set nikki.proxy.udp_mode=tproxy
uci set nikki.proxy.ipv4_dns_hijack=1
uci set nikki.proxy.lan_proxy=1
uci set nikki.mixin.api_listen="[::]:9090"
uci set nikki.mixin.api_secret="ganti-password"
uci commit nikki
```

### 6. Firewall

```bash
iptables -t nat -A PREROUTING -p tcp --dport 53 -j REDIRECT --to-ports 1053
iptables -t nat -A PREROUTING -p udp --dport 53 -j REDIRECT --to-ports 1053
```

### 7. Start

```bash
/etc/init.d/nikki restart
```

### 8. Auto-update (cron)

```bash
# Proxy list update (tiap 12 jam)
cat > /usr/local/bin/update-proxy.sh << 'EOF'
#!/bin/sh
PROXY_URL="https://raw.githubusercontent.com/rickicode/free-proxy-singbox/main/output/live-proxies.mihomo.yml"
BASE_URL="https://raw.githubusercontent.com/rickicode/free-proxy-singbox/main/openwrt/base.yml"
PROFILE="/etc/nikki/profiles/free-proxy-singbox.yml"
MIXIN="/etc/nikki/mixin.yaml"
CHANGED=0

curl -sL --max-time 60 "$PROXY_URL" -o "$PROFILE.tmp" 2>/dev/null
if head -1 "$PROFILE.tmp" | grep -q "Auto-generated"; then
  mv "$PROFILE.tmp" "$PROFILE"
  CHANGED=1
else
  rm -f "$PROFILE.tmp"
fi

curl -sL --max-time 60 "$BASE_URL" -o "$MIXIN.tmp" 2>/dev/null
if head -1 "$MIXIN.tmp" | grep -q "Base config"; then
  mv "$MIXIN.tmp" "$MIXIN"
  CHANGED=1
else
  rm -f "$MIXIN.tmp"
fi

if [ "$CHANGED" = "1" ]; then
  /etc/init.d/nikki restart 2>/dev/null
  echo "[$(date)] Updated + restarted" >> /var/log/proxy-update.log
fi
EOF
chmod +x /usr/local/bin/update-proxy.sh

# WARP refresh (tiap 2 hari)
cat > /usr/local/bin/warp-refresh.sh << 'EOF'
#!/bin/sh
WARP_FILE="/etc/nikki/profiles/warp.yml"
CRED_FILE="/etc/nikki/warp-creds.json"
if [ ! -f "$CRED_FILE" ]; then
  ash /etc/nikki/warp-setup.sh
  /etc/init.d/nikki restart 2>/dev/null
  echo "[$(date)] WARP: initial setup" >> /var/log/proxy-update.log
  exit 0
fi

last=$(python3 -c "
import json, time
creds = json.load(open('$CRED_FILE'))
times = [v.get('refreshed_at','') for v in creds.values() if v.get('refreshed_at')]
if times:
    t = time.mktime(time.strptime(max(times), '%Y-%m-%dT%H:%M:%SZ'))
    print(f'{(time.time()-t)/86400:.1f}')
else:
    print('99')
" 2>/dev/null || echo "99")

if [ "$(echo "$last < 1.5" | bc -l 2>/dev/null || echo 0)" = "1" ]; then
  echo "[$(date)] WARP: still fresh ($last days)" >> /var/log/proxy-update.log
  exit 0
fi

ash /etc/nikki/warp-setup.sh
/etc/init.d/nikki restart 2>/dev/null
echo "[$(date)] WARP: refreshed" >> /var/log/proxy-update.log
EOF
chmod +x /usr/local/bin/warp-refresh.sh

(crontab -l 2>/dev/null | grep -v update-proxy | grep -v warp-refresh; \
 echo "0 */12 * * * /usr/local/bin/update-proxy.sh"; \
 echo "0 3 */2 * * /usr/local/bin/warp-refresh.sh") | crontab -
```

## Dashboard

```
http://<router-ip>:9090
```

## Proxy Groups

| Group | Type | Isi |
|---|---|---|
| GLOBAL | select | catch-all: DIRECT + semua group |
| PROXY-FREE | url-test | semua proxy free |
| PROXY-ID | url-test | proxy Indonesia |
| PROXY-SG | url-test | proxy Singapore |
| PROXY-US | url-test | proxy US |
| PROXY-WARP | select | Cloudflare WARP (per-device) |
| WARP-LB | load-balance | 3 WARP accounts (auto-select fastest) |
| GOOGLE | select | DIRECT + semua group |
| AI | select | DIRECT + semua group |
| CHECK-IP | select | DIRECT + semua group |
| SOCIAL | select | DIRECT + semua group |

## Rules

- Ads → REJECT
- Private IP → DIRECT
- CN sites/IP → DIRECT
- Google → GOOGLE group
- AI sites → AI group
- IP check → CHECK-IP group
- Social media → SOCIAL group
- GitHub/Netflix → PROXY-FREE
- Catch-all → GLOBAL

## Troubleshooting

```bash
# Status
/etc/init.d/nikki status

# Log
tail -20 /var/log/nikki/app.log

# Cek DNS hijack
uci show nikki.proxy | grep dns

# Restart
/etc/init.d/nikki restart

# Update proxy manual
/usr/local/bin/update-proxy.sh

# Refresh WARP manual
/usr/local/bin/warp-refresh.sh
```

## File Structure

```
/etc/nikki/
├── mixin.yaml                          ← base config (DNS, rules, ports)
├── warp-setup.sh                       ← WARP account generator
├── warp-creds.json                     ← WARP keys (local only, never committed)
├── profiles/
│   ├── free-proxy-singbox.yml          ← proxy list + groups (auto-update)
│   └── warp.yml                        ← WARP proxies (per-device, auto-refresh)
└── ...

/usr/local/bin/
├── update-proxy.sh                     ← update proxy list + base config
└── warp-refresh.sh                     ← refresh WARP accounts (tiap 2 hari)
```
