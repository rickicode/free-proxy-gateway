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
    ├── mixin.yaml (base config: DNS, rules, ports) ← jarang berubah
    ├── free-proxy-singbox.yml (proxy list + groups)  ← auto-update tiap 12 jam
    └── Nikki merge keduanya → runtime config
    ├── DIRECT (default)
    ├── GLOBAL (catch-all)
    ├── PROXY-FREE (auto-select free proxy)
    ├── PROXY-WARP (Cloudflare WARP, via mixin)
    ├── AI group (OpenAI, Claude, dll)
    ├── GOOGLE group
    ├── CHECK-IP group
    └── SOCIAL group
```

**Split config:**
| File | Isi | Update |
|---|---|---|
| `openwrt/base.yml` → `/etc/nikki/mixin.yaml` | DNS, ports, rules, group definitions | Manual / jarang |
| `output/live-proxies.mihomo.yml` → `/etc/nikki/profiles/free-proxy-singbox.yml` | Proxies + proxy-groups | Auto tiap 12 jam |

## Quick Start (1 Command)

```bash
wget -O setup.sh https://raw.githubusercontent.com/rickicode/free-proxy-singbox/main/openwrt/setup.sh && ash setup.sh
```

Script ini akan:
1. Download `base.yml` → `/etc/nikki/mixin.yaml`
2. Download proxy list → `/etc/nikki/profiles/free-proxy-singbox.yml`
3. Konfigurasi Nikki via UCI
4. Setup firewall DNS redirect
5. Install cron auto-update tiap 12 jam
6. Start Nikki

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

### 4. Konfigurasi Nikki via UCI

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

### 5. Firewall

```bash
iptables -t nat -A PREROUTING -p tcp --dport 53 -j REDIRECT --to-ports 1053
iptables -t nat -A PREROUTING -p udp --dport 53 -j REDIRECT --to-ports 1053
```

### 6. Start

```bash
/etc/init.d/nikki restart
```

### 7. Auto-update (cron)

```bash
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
echo "0 */12 * * * /usr/local/bin/update-proxy.sh" | crontab -
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
| PROXY-WARP | select | Cloudflare WARP (via mixin) |
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

# Update manual
/usr/local/bin/update-proxy.sh
```

## File Structure

```
/etc/nikki/
├── mixin.yaml                          ← base config (DNS, rules, ports)
├── profiles/
│   └── free-proxy-singbox.yml          ← proxy list + groups (auto-update)
└── ...
```
