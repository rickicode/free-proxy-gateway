#!/bin/sh
# OpenWrt Gateway Setup Script
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

# Step 1: Install Nikki
echo ""
echo ">>> [1/5] Install Nikki (Mihomo wrapper)..."

if ! command -v nikki >/dev/null 2>&1; then
  # Tambah feed Nikki
  wget -O - https://github.com/nikkinikki-org/OpenWrt-nikki/raw/refs/heads/main/feed.sh | ash 2>/dev/null
  apk update 2>/dev/null
  apk add nikki luci-app-nikki 2>&1 | tail -3
else
  echo "Nikki sudah terinstall, skip."
fi

# Step 2: Download proxy config
echo ""
echo ">>> [2/5] Download proxy config dari free-proxy-singbox..."

mkdir -p /etc/nikki/profiles
wget -O /etc/nikki/profiles/free-proxy-singbox.yml \
  "https://raw.githubusercontent.com/rickicode/free-proxy-singbox/main/output/live-proxies.mihomo.yml" 2>/dev/null

if head -1 /etc/nikki/profiles/free-proxy-singbox.yml | grep -q "Auto-generated"; then
  echo "OK: $(wc -l < /etc/nikki/profiles/free-proxy-singbox.yml) lines downloaded."
else
  echo "Warning: Download gagal. Cek koneksi internet."
fi

# Step 3: Konfigurasi Nikki via UCI
echo ""
echo ">>> [3/5] Konfigurasi Nikki..."

# Profile
uci set nikki.config.profile="file:free-proxy-singbox.yml"
uci set nikki.config.enabled=1

# Proxy mode: TPROXY
uci set nikki.proxy.tcp_mode=tproxy
uci set nikki.proxy.udp_mode=tproxy
uci set nikki.proxy.ipv4_dns_hijack=1
uci set nikki.proxy.ipv6_dns_hijack=1
uci set nikki.proxy.lan_proxy=1

# API
uci set nikki.mixin.api_listen="[::]:9090"
uci set nikki.mixin.api_secret="hijinet"
uci set nikki.mixin.allow_lan=1

# Disable auth (simple gateway)
uci set nikki.@authentication[0].enabled=0

uci commit nikki
echo "OK: Nikki configured."

# Step 4: Firewall
echo ""
echo ">>> [4/5] Firewall: buka akses WAN..."

uci set firewall.@zone[1].input=ACCEPT
uci commit firewall
/etc/init.d/firewall restart 2>/dev/null
echo "OK: Firewall updated."

# Step 5: Auto-update cron
echo ""
echo ">>> [5/5] Setup auto-update proxy list (tiap 12 jam)..."

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

# Tambah cron kalau belum ada
if ! crontab -l 2>/dev/null | grep -q "update-proxy"; then
  (crontab -l 2>/dev/null; echo "0 */12 * * * /usr/local/bin/update-proxy.sh") | crontab -
fi
echo "OK: Cron set."

# Step 6: Start Nikki
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

echo ""
echo "=== Selesai! ==="
echo ""
echo "Dashboard: http://$(ip -4 addr show br-lan 2>/dev/null | grep inet | awk '{print $2}' | cut -d/ -f1 || echo 'IP-LAN'):9090/ui/?secret=hijinet"
echo "LuCI:      http://$(ip -4 addr show br-lan 2>/dev/null | grep inet | awk '{print $2}' | cut -d/ -f1 || echo 'IP-LAN')/cgi-bin/luci"
echo ""
echo "Ganti password Nikki: uci set nikki.mixin.api_secret='password-baru' && uci commit nikki"
echo "Ganti GLOBAL group: buka dashboard → GLOBAL → pilih PROXY-FREE / PROXY-WARP"
