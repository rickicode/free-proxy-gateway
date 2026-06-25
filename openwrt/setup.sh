#!/bin/sh
# OpenWrt Gateway Setup — Nikki + Mihomo + WARP
# Usage: wget -O setup.sh https://raw.githubusercontent.com/rickicode/free-proxy-singbox/main/openwrt/setup.sh && ash setup.sh
set -e

REPO="https://raw.githubusercontent.com/rickicode/free-proxy-singbox/main"

echo "=== OpenWrt Gateway Setup ==="

[ ! -f /etc/openwrt_release ] && echo "ERROR: Bukan OpenWrt." && exit 1
command -v nikki >/dev/null 2>&1 || { echo "ERROR: Nikki belum terinstall."; exit 1; }

echo "[1/5] Base config (mixin)..."
wget -O /etc/nikki/mixin.yaml "$REPO/openwrt/base.yml" 2>/dev/null
head -1 /etc/nikki/mixin.yaml | grep -q "Base config" && echo "  OK" || { echo "  FAIL"; exit 1; }

echo "[2/5] Free proxy list..."
mkdir -p /etc/nikki/profiles
wget -O /etc/nikki/profiles/free-proxies.yml "$REPO/output/live-proxies.mihomo.yml" 2>/dev/null
head -1 /etc/nikki/profiles/free-proxies.yml | grep -q "Auto-generated" && echo "  OK" || { echo "  FAIL"; exit 1; }

echo "[3/5] WARP accounts..."
wget -O /etc/nikki/warp-setup.sh "$REPO/openwrt/warp-setup.sh" 2>/dev/null
chmod +x /etc/nikki/warp-setup.sh
ash /etc/nikki/warp-setup.sh

echo "[4/5] Nikki config..."
uci set nikki.config.profile="file:mihomo.yml"
uci set nikki.config.enabled=1
uci set nikki.proxy.tcp_mode=tproxy
uci set nikki.proxy.udp_mode=tproxy
uci set nikki.proxy.ipv4_dns_hijack=1
uci set nikki.proxy.lan_proxy=1
uci set nikki.mixin.api_listen="[::]:9090"
uci set nikki.mixin.api_secret="ganti-password"
uci commit nikki

echo "[5/5] Firewall + Cron..."
iptables -t nat -C PREROUTING -p tcp --dport 53 -j REDIRECT --to-ports 1053 2>/dev/null || \
  iptables -t nat -A PREROUTING -p tcp --dport 53 -j REDIRECT --to-ports 1053
iptables -t nat -C PREROUTING -p udp --dport 53 -j REDIRECT --to-ports 1053 2>/dev/null || \
  iptables -t nat -A PREROUTING -p udp --dport 53 -j REDIRECT --to-ports 1053

# Update script: download proxy list + base config, restart nikki
cat > /usr/local/bin/update-proxy.sh << 'EOF'
#!/bin/sh
BASE_URL="https://raw.githubusercontent.com/rickicode/free-proxy-singbox/refs/heads/main"
CHANGED=0
curl -sL --max-time 60 "$BASE_URL/output/live-proxies.mihomo.yml" -o /etc/nikki/run/providers/free-proxies.yml.tmp 2>/dev/null
if head -1 /etc/nikki/run/providers/free-proxies.yml.tmp | grep -q "Auto-generated"; then
  mv /etc/nikki/run/providers/free-proxies.yml.tmp /etc/nikki/run/providers/free-proxies.yml
  CHANGED=1
else rm -f /etc/nikki/run/providers/free-proxies.yml.tmp; fi
curl -sL --max-time 60 "$BASE_URL/openwrt/base.yml" -o /etc/nikki/mixin.yaml.tmp 2>/dev/null
if head -1 /etc/nikki/mixin.yaml.tmp | grep -q "Base config"; then
  mv /etc/nikki/mixin.yaml.tmp /etc/nikki/mixin.yaml
  CHANGED=1
else rm -f /etc/nikki/mixin.yaml.tmp; fi
[ "$CHANGED" = "1" ] && /etc/init.d/nikki restart 2>/dev/null && echo "[$(date)] Updated" >> /var/log/proxy-update.log
EOF
chmod +x /usr/local/bin/update-proxy.sh

# WARP refresh: regenerate accounts every 2 days
cat > /usr/local/bin/warp-refresh.sh << 'EOF'
#!/bin/sh
CRED=/etc/nikki/warp-creds.json
[ ! -f "$CRED" ] && ash /etc/nikki/warp-setup.sh && /etc/init.d/nikki restart && exit 0
last=$(python3 -c "import json,time;c=json.load(open('$CRED'));t=[v.get('refreshed_at','') for v in c.values() if v.get('refreshed_at')];print(f'{(time.time()-time.mktime(time.strptime(max(t),\"%Y-%m-%dT%H:%M:%SZ\")))/86400:.1f}')" 2>/dev/null || echo 99)
[ "$(echo "$last < 1.5" | bc -l 2>/dev/null || echo 0)" = "1" ] && exit 0
ash /etc/nikki/warp-setup.sh && /etc/init.d/nikki restart 2>/dev/null
EOF
chmod +x /usr/local/bin/warp-refresh.sh

(crontab -l 2>/dev/null | grep -v update-proxy | grep -v warp-refresh; \
 echo "0 */12 * * * /usr/local/bin/update-proxy.sh"; \
 echo "0 3 */2 * * /usr/local/bin/warp-refresh.sh") | crontab -

echo ""
echo "=== Start Nikki ==="
/etc/init.d/nikki restart 2>/dev/null
sleep 3
pgrep -x mihomo >/dev/null && echo "  Nikki: RUNNING" || echo "  Nikki: NOT RUNNING"
curl -s --max-time 3 http://127.0.0.1:9090 -o /dev/null -w "  API: %{http_code}\n"

echo ""
echo "=== Selesai ==="
echo "Dashboard: http://$(ip -4 addr show br-lan 2>/dev/null | grep inet | head -1 | awk '{print $2}' | cut -d/ -f1):9090"
