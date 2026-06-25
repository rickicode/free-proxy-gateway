#!/bin/sh
# OpenWrt Gateway Setup — Nikki + Mihomo
# Usage: wget -O setup.sh https://raw.githubusercontent.com/rickicode/free-proxy-singbox/main/openwrt/setup.sh && ash setup.sh
set -e

REPO="https://raw.githubusercontent.com/rickicode/free-proxy-singbox/main"
BASE_URL="$REPO/openwrt/base.yml"
PROXY_URL="$REPO/output/live-proxies.mihomo.yml"
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

echo "[1/5] Download base config (mixin)..."
wget -O /etc/nikki/mixin.yaml "$BASE_URL" 2>/dev/null
if head -1 /etc/nikki/mixin.yaml | grep -q "Base config"; then
  echo "  OK: $(wc -l < /etc/nikki/mixin.yaml) lines"
else
  echo "  FAIL: download base config gagal"
  exit 1
fi

echo "[2/5] Download proxy list..."
mkdir -p /etc/nikki/profiles
wget -O "/etc/nikki/profiles/$PROFILE_NAME" "$PROXY_URL" 2>/dev/null
if head -1 "/etc/nikki/profiles/$PROFILE_NAME" | grep -q "Auto-generated"; then
  echo "  OK: $(wc -l < "/etc/nikki/profiles/$PROFILE_NAME") lines"
else
  echo "  FAIL: download proxy list gagal"
  exit 1
fi

echo "[3/5] Konfigurasi Nikki..."
uci set nikki.config.profile="file:$PROFILE_NAME"
uci set nikki.config.enabled=1
uci set nikki.proxy.tcp_mode=tproxy
uci set nikki.proxy.udp_mode=tproxy
uci set nikki.proxy.ipv4_dns_hijack=1
uci set nikki.proxy.lan_proxy=1
uci set nikki.mixin.api_listen="[::]:9090"
uci set nikki.mixin.api_secret="ganti-password"
uci commit nikki

echo "[4/5] Firewall..."
if ! iptables -t nat -C PREROUTING -p tcp --dport 53 -j REDIRECT --to-ports 1053 2>/dev/null; then
  iptables -t nat -A PREROUTING -p tcp --dport 53 -j REDIRECT --to-ports 1053
  iptables -t nat -A PREROUTING -p udp --dport 53 -j REDIRECT --to-ports 1053
  echo "  OK: DNS redirect ditambahkan"
else
  echo "  OK: DNS redirect sudah ada"
fi

echo "[5/5] Auto-update cron (tiap 12 jam)..."
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

(crontab -l 2>/dev/null | grep -v update-proxy; echo "0 */12 * * * /usr/local/bin/update-proxy.sh") | crontab -
echo "  OK: cron terpasang"

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
if ss -tlnp | grep -q 7890; then
  echo "  Port 7890 (mixed): OK"
fi
if ss -tlnp | grep -q 9090; then
  echo "  Port 9090 (API): OK"
fi

echo ""
echo "=== Selesai ==="
echo "Dashboard: http://$(ip -4 addr show br-lan | grep inet | head -1 | awk '{print $2}' | cut -d/ -f1):9090"
echo "Log: tail -20 /var/log/nikki/app.log"
echo "Update manual: /usr/local/bin/update-proxy.sh"
