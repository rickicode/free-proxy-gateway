# OpenWrt Gateway Setup

Panduan lengkap setup OpenWrt sebagai VPN gateway dengan proxy otomatis dari free-proxy-singbox.

## Prerequisites

**Nikki harus sudah terinstall di OpenWrt sebelum menjalankan setup.**

```bash
# Install Nikki + LuCI (kalau belum)
apk add nikki luci-app-nikki
```

## Arsitektur

```
Client (192.168.x.x)
    ↓
OpenWrt Gateway (Nikki + Mihomo)
    ├── DIRECT (default)
    ├── PROXY-FREE (auto-select free proxy)
    ├── PROXY-WARP (Cloudflare WARP)
    ├── AI group (OpenAI, Claude, dll)
    ├── GOOGLE group
    ├── CHECK-IP group
    └── SOCIAL group
```

## Quick Start (1 Command)

**Pastikan Nikki sudah terinstall dulu!**

```bash
wget -O setup.sh https://raw.githubusercontent.com/rickicode/free-proxy-singbox/main/openwrt/setup.sh && ash setup.sh
```

Script ini akan:
1. Download proxy config dari repo ini (auto-update tiap 12 jam)
2. Konfigurasi Nikki via UCI (TPROXY, DNS hijack)
3. Buka firewall WAN
4. Setup cron auto-update

## Manual Install

### 1. Install Nikki

```bash
wget -O - https://github.com/nikkinikki-org/OpenWrt-nikki/raw/refs/heads/main/feed.sh | ash
apk add nikki luci-app-nikki
```

### 2. Download proxy config

```bash
mkdir -p /etc/nikki/profiles
wget -O /etc/nikki/profiles/free-proxy-singbox.yml \
  https://raw.githubusercontent.com/rickicode/free-proxy-singbox/main/output/live-proxies.mihomo.yml
```

### 3. Setup WARP WireGuard (opsional)

Lihat [warp-setup.md](warp-setup.md)

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
uci set firewall.@zone[1].input=ACCEPT
uci commit firewall
```

### 6. Start

```bash
/etc/init.d/nikki restart
```

### 7. Auto-update (cron)

```bash
cat > /usr/local/bin/update-proxy.sh << 'EOF'
#!/bin/sh
URL="https://raw.githubusercontent.com/rickicode/free-proxy-singbox/main/output/live-proxies.mihomo.yml"
PROFILE="/etc/nikki/profiles/free-proxy-singbox.yml"
curl -sL --max-time 60 "$URL" -o "$PROFILE.tmp"
if head -1 "$PROFILE.tmp" | grep -q "Auto-generated"; then
  mv "$PROFILE.tmp" "$PROFILE"
  /etc/init.d/nikki restart
  echo "[$(date)] Updated OK" >> /var/log/proxy-update.log
else
  rm -f "$PROFILE.tmp"
  echo "[$(date)] Download failed" >> /var/log/proxy-update.log
fi
EOF
chmod +x /usr/local/bin/update-proxy.sh
echo "0 */12 * * * /usr/local/bin/update-proxy.sh" >> /etc/crontabs/root
```

## Dashboard

```
http://<IP-OpenWrt>:9090/ui/?secret=<password>
```

## Proxy Groups

| Group | Fungsi | Default |
|-------|--------|---------|
| **GLOBAL** | Catch-all, user kontrol | DIRECT |
| **PROXY-FREE** | Auto-select free proxy | 🇸🇬 auto |
| **PROXY-ID** | Indonesia | 🇮🇩 |
| **PROXY-SG** | Singapore | 🇸🇬 |
| **PROXY-US** | US | 🇺🇸 |
| **PROXY-WARP** | Cloudflare WARP | WARP-LB |
| **AI** | OpenAI, Claude, dll | DIRECT |
| **GOOGLE** | Google services | DIRECT |
| **CHECK-IP** | IP check sites | PROXY-FREE |
| **SOCIAL** | Telegram, Twitter, dll | DIRECT |

## Rules

```
AI domains       → AI group
Google domains   → GOOGLE group
CHECK-IP domains → CHECK-IP group
Social domains   → SOCIAL group
MATCH            → GLOBAL (catch-all)
```

## Troubleshooting

```bash
# Nikki gak jalan
tail -20 /var/log/nikki/app.log

# DNS gak jalan
uci show nikki.proxy | grep dns

# Proxy gak ke-deteksi
curl -s -H "Authorization: Bearer <secret>" http://127.0.0.1:9090/proxies | python3 -m json.tool
```

## File Structure

```
openwrt/
├── README.md          # Panduan ini
├── setup.sh           # Quick install script
└── warp-setup.md      # Panduan setup WARP
```
