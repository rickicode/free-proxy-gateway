#!/bin/sh
# OpenWrt Gateway Setup — Nikki + Mihomo + WARP
# Usage: wget -O setup.sh https://raw.githubusercontent.com/rickicode/free-proxy-singbox/main/openwrt/setup.sh && ash setup.sh
set -e

REPO="https://raw.githubusercontent.com/rickicode/free-proxy-singbox/main"
BASE_URL="$REPO/openwrt/base.yml"
PROXY_URL="$REPO/output/live-proxies.mihomo.yml"
WARP_SETUP_URL="$REPO/openwrt/warp-setup.sh"
PROFILE_NAME="free-proxy-singbox.yml"

echo "=== OpenWrt Gateway Setup ==="
echo ""

# Cek apakah ini OpenWrt
if [ ! -f /etc/openwrt_release ]; then
  echo "ERROR: Bukan OpenWrt."
  exit 1
fi

# Cek Nikki sudah terinstall
if ! command -v nikki >/dev/null 2>&1; then
  echo "ERROR: Nikki belum terinstall."
  echo "Install dulu:"
  echo "  wget -O - https://github.com/nikkinikki-org/OpenWrt-nikki/raw/refs/heads/main/feed.sh | ash"
  echo "  apk add nikki luci-app-nikki"
  exit 1
fi

echo "[1/6] Download base config (mixin)..."
wget -O /etc/nikki/mixin.yaml "$BASE_URL" 2>/dev/null
if head -1 /etc/nikki/mixin.yaml | grep -q "Base config"; then
  echo "  OK: $(wc -l < /etc/nikki/mixin.yaml) lines"
else
  echo "  FAIL: download base config gagal"
  exit 1
fi

echo "[2/6] Download proxy list..."
mkdir -p /etc/nikki/profiles
wget -O "/etc/nikki/profiles/$PROFILE_NAME" "$PROXY_URL" 2>/dev/null
if head -1 "/etc/nikki/profiles/$PROFILE_NAME" | grep -q "Auto-generated"; then
  echo "  OK: $(wc -l < "/etc/nikki/profiles/$PROFILE_NAME") lines"
else
  echo "  FAIL: download proxy list gagal"
  exit 1
fi

echo "[3/6] Install wgcf (for WARP)..."
if ! command -v wgcf >/dev/null 2>&1; then
  arch=$(uname -m)
  case "$arch" in
    x86_64|amd64) a="amd64" ;;
    aarch64|arm64) a="arm64" ;;
    *) a="amd64" ;;
  esac
  wget -qO /usr/local/bin/wgcf "https://github.com/ViRb3/wgcf/releases/latest/download/wgcf_${a}"
  chmod +x /usr/local/bin/wgcf
  echo "  OK: wgcf ($a)"
else
  echo "  OK: wgcf sudah ada"
fi

echo "[4/6] Generate WARP accounts (per-device)..."
wget -O /etc/nikki/warp-setup.sh "$WARP_SETUP_URL" 2>/dev/null
chmod +x /etc/nikki/warp-setup.sh
ash /etc/nikki/warp-setup.sh

echo "[5/6] Konfigurasi Nikki..."
uci set nikki.config.profile="file:$PROFILE_NAME"
uci set nikki.config.enabled=1
uci set nikki.proxy.tcp_mode=tproxy
uci set nikki.proxy.udp_mode=tproxy
uci set nikki.proxy.ipv4_dns_hijack=1
uci set nikki.proxy.lan_proxy=1
uci set nikki.mixin.api_listen="[::]:9090"
uci set nikki.mixin.api_secret="ganti-password"
uci commit nikki

echo "[6/6] Firewall + Auto-update..."
# DNS redirect
if ! iptables -t nat -C PREROUTING -p tcp --dport 53 -j REDIRECT --to-ports 1053 2>/dev/null; then
  iptables -t nat -A PREROUTING -p tcp --dport 53 -j REDIRECT --to-ports 1053
  iptables -t nat -A PREROUTING -p udp --dport 53 -j REDIRECT --to-ports 1053
  echo "  DNS redirect: OK"
fi

# Auto-update script
cat > /usr/local/bin/update-proxy.sh << 'CRON'
#!/bin/sh
PROXY_URL="https://raw.githubusercontent.com/rickicode/free-proxy-singbox/main/output/live-proxies.mihomo.yml"
BASE_URL="https://raw.githubusercontent.com/rickicode/free-proxy-singbox/main/openwrt/base.yml"
PROFILE="/etc/nikki/profiles/free-proxy-singbox.yml"
MIXIN="/etc/nikki/mixin.yaml"
CHANGED=0

# Update proxy list
curl -sL --max-time 60 "$PROXY_URL" -o "$PROFILE.tmp" 2>/dev/null
if head -1 "$PROFILE.tmp" | grep -q "Auto-generated"; then
  mv "$PROFILE.tmp" "$PROFILE"
  CHANGED=1
else
  rm -f "$PROFILE.tmp"
fi

# Update base config
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
else
  echo "[$(date)] No changes" >> /var/log/proxy-update.log
fi
CRON
chmod +x /usr/local/bin/update-proxy.sh

# WARP refresh cron (tiap 2 hari)
cat > /usr/local/bin/warp-refresh.sh << 'WARPCRON'
#!/bin/sh
WARP_FILE="/etc/nikki/profiles/warp.yml"
CRED_FILE="/etc/nikki/warp-creds.json"
if [ ! -f "$CRED_FILE" ]; then
  ash /etc/nikki/warp-setup.sh
  /etc/init.d/nikki restart 2>/dev/null
  echo "[$(date)] WARP: initial setup" >> /var/log/proxy-update.log
  exit 0
fi

# Check freshness (2 days)
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
WARPCRON
chmod +x /usr/local/bin/warp-refresh.sh

(crontab -l 2>/dev/null | grep -v update-proxy | grep -v warp-refresh; \
 echo "0 */12 * * * /usr/local/bin/update-proxy.sh"; \
 echo "0 3 */2 * * /usr/local/bin/warp-refresh.sh") | crontab -
echo "  Cron: OK"

echo ""
echo "=== Start Nikki ==="
/etc/init.d/nikki restart 2>/dev/null

echo ""
echo "=== Verifikasi ==="
sleep 2
if pgrep -x nikki >/dev/null 2>&1 || pgrep -x mihomo >/dev/null 2>&1; then
  echo "  Nikki: RUNNING"
else
  echo "  Nikki: NOT RUNNING — cek log: tail -20 /var/log/nikki/app.log"
fi
if curl -s --max-time 3 http://127.0.0.1:9090 -o /dev/null -w "%{http_code}" | grep -q "401"; then
  echo "  API: OK (9090)"
fi

echo ""
echo "=== Selesai ==="
echo "Dashboard: http://$(ip -4 addr show br-lan 2>/dev/null | grep inet | head -1 | awk '{print $2}' | cut -d/ -f1):9090"
echo "Log: tail -20 /var/log/nikki/app.log"
echo "Update proxy: /usr/local/bin/update-proxy.sh"
echo "Refresh WARP: /usr/local/bin/warp-refresh.sh"
