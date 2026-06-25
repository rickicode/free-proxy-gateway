#!/bin/sh
# OpenWrt Gateway Setup Script
# Prerequisite: Nikki harus sudah terinstall (apk add nikki luci-app-nikki)
# Usage: wget -O setup.sh https://raw.githubusercontent.com/rickicode/free-proxy-singbox/main/openwrt/setup.sh && ash setup.sh

echo "=== OpenWrt Gateway Setup ==="
echo ""

# Cek apakah ini OpenWrt
if [ ! -f /etc/openwrt_release ]; then
  echo "Error: Bukan sistem OpenWrt!"
  exit 1
fi

. /etc/openwrt_release
echo "Detected: $DISTRIB_ID $DISTRIB_RELEASE ($DISTRIB_ARCH)"

# Cek Nikki sudah terinstall
if ! command -v nikki >/dev/null 2>&1; then
  echo ""
  echo "Error: Nikki belum terinstall!"
  echo "Install dulu:"
  echo "  apk add nikki luci-app-nikki"
  exit 1
fi
echo "Nikki: OK"

# Step 1: Download proxy config
echo ""
echo ">>> [1/4] Download proxy config..."

mkdir -p /etc/nikki/profiles
wget -O /etc/nikki/profiles/free-proxy-singbox.yml \
  "https://raw.githubusercontent.com/rickicode/free-proxy-singbox/main/output/live-proxies.mihomo.yml" 2>/dev/null

if head -1 /etc/nikki/profiles/free-proxy-singbox.yml | grep -q "Auto-generated"; then
  echo "OK: $(wc -l < /etc/nikki/profiles/free-proxy-singbox.yml) lines downloaded."
else
  echo "Warning: Download gagal. Cek koneksi internet."
fi

# Step 2: Konfigurasi Nikki via UCI
echo ""
echo ">>> [2/4] Konfigurasi Nikki..."

uci set nikki.config.profile="file:free-proxy-singbox.yml"
uci set nikki.config.enabled=1
uci set nikki.proxy.tcp_mode=tproxy
uci set nikki.proxy.udp_mode=tproxy
uci set nikki.proxy.ipv4_dns_hijack=1
uci set nikki.proxy.ipv6_dns_hijack=1
uci set nikki.proxy.lan_proxy=1
uci set nikki.mixin.api_listen="[::]:9090"
uci set nikki.mixin.api_secret="hijinet"
uci set nikki.mixin.allow_lan=1
uci set nikki.@authentication[0].enabled=0
uci commit nikki
echo "OK: Nikki configured."

# Step 3: Firewall
echo ""
echo ">>> [3/4] Firewall: buka akses WAN..."

uci set firewall.@zone[1].input=ACCEPT
uci commit firewall
/etc/init.d/firewall restart 2>/dev/null
echo "OK: Firewall updated."

# Step 4: Auto-update cron
echo ""
echo ">>> [4/4] Setup auto-update (tiap 12 jam)..."

mkdir -p /usr/local/bin
cat > /usr/local/bin/update-proxy.sh << 'SCRIPT'
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
SCRIPT
chmod +x /usr/local/bin/update-proxy.sh

if ! crontab -l 2>/dev/null | grep -q "update-proxy"; then
  (crontab -l 2>/dev/null; echo "0 */12 * * * /usr/local/bin/update-proxy.sh") | crontab -
fi
echo "OK: Cron set."

# Start Nikki
echo ""
echo ">>> Start Nikki..."
/etc/init.d/nikki restart 2>/dev/null
sleep 10

# Verifikasi
echo ""
echo "=== Verifikasi ==="
if pidof mihomo >/dev/null; then
  echo "✅ Mihomo: RUNNING"
else
  echo "❌ Mihomo: NOT RUNNING (cek /var/log/nikki/app.log)"
fi

if curl -s -H "Authorization: Bearer hijinet" http://127.0.0.1:9090/version >/dev/null 2>&1; then
  echo "✅ API: OK"
else
  echo "❌ API: GAGAL"
fi

LAN_IP=$(ip -4 addr show br-lan 2>/dev/null | grep inet | awk '{print $2}' | cut -d/ -f1)
echo ""
echo "=== Selesai! ==="
echo ""
echo "Dashboard: http://${LAN_IP}:9090/ui/?secret=hijinet"
echo "LuCI:      http://${LAN_IP}/cgi-bin/luci"
echo ""
echo "Ganti password: uci set nikki.mixin.api_secret='password-baru' && uci commit nikki"
echo "Ganti GLOBAL:   buka dashboard → GLOBAL → pilih PROXY-FREE / PROXY-WARP"
