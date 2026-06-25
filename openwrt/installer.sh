#!/bin/sh
# free-proxy-singbox — Installer
# Auto-install: Nikki, wgcf, wireguard-tools, prox-menu, config, WARP, cron
#
# Usage:
#   ash installer.sh          — install (skip existing)
#   ash installer.sh --force  — force reinstall dependencies
set -e

REPO="https://raw.githubusercontent.com/rickicode/free-proxy-singbox/refs/heads/main"
FORCE=0

[ "$1" = "--force" ] && FORCE=1

# Colors (busybox ash compatible)
ESC=$(printf '\33')
R="${ESC}[0;31m"
G="${ESC}[0;32m"
Y="${ESC}[1;33m"
B="${ESC}[0;34m"
C="${ESC}[0;36m"
W="${ESC}[1;37m"
N="${ESC}[0m"

ok()   { echo "  ${G}✓${N} $1"; }
skip() { echo "  ${Y}⏭${N} $1 (sudah ada)"; }
fail() { echo "  ${R}✗${N} $1"; }
info() { echo "  ${C}→${N} $1"; }

echo ""
echo "${B}╔══════════════════════════════════════════════════╗${N}"
echo "${B}║${W}       free-proxy-singbox — Installer              ${B}║${N}"
echo "${B}╚══════════════════════════════════════════════════╝${N}"
echo ""

# ── CHECK ROOT ──────────────────────────────────
[ "$(id -u)" != "0" ] && echo "${R}ERROR: Jalankan sebagai root${N}" && exit 1

# ── CHECK OPENWRT ───────────────────────────────
if [ ! -f /etc/openwrt_release ]; then
  echo "${R}ERROR: Bukan OpenWrt${N}"
  exit 1
fi

ARCH=$(uname -m)
case "$ARCH" in
  x86_64|amd64) ARCH_NAME="amd64" ;;
  aarch64|arm64) ARCH_NAME="arm64" ;;
  armv7l|armhf) ARCH_NAME="armv7" ;;
  *) ARCH_NAME="amd64" ;;
esac

echo "${W}[1/7] Dependencies${N}"
echo ""

# ── NIKKI ───────────────────────────────────────
echo -n "  Nikki: "
if [ -f /etc/init.d/nikki ]; then
  if [ "$FORCE" = "1" ]; then
    info "Force reinstall..."
    wget -qO - https://github.com/nikkinikki-org/OpenWrt-nikki/raw/refs/heads/main/feed.sh | ash 2>/dev/null
    apk add nikki luci-app-nikki 2>/dev/null || opkg install nikki luci-app-nikki 2>/dev/null
    ok "Nikki reinstalled"
  else
    skip "Nikki"
  fi
else
  info "Installing Nikki..."
  wget -qO - https://github.com/nikkinikki-org/OpenWrt-nikki/raw/refs/heads/main/feed.sh | ash 2>/dev/null
  apk add nikki luci-app-nikki 2>/dev/null || opkg install nikki luci-app-nikki 2>/dev/null
  ok "Nikki installed"
fi

# ── WGCF ────────────────────────────────────────
echo -n "  wgcf: "
if command -v wgcf >/dev/null 2>&1; then
  if [ "$FORCE" = "1" ]; then
    info "Force reinstall..."
    wget -qO /usr/local/bin/wgcf "https://github.com/ViRb3/wgcf/releases/latest/download/wgcf_${ARCH_NAME}"
    chmod +x /usr/local/bin/wgcf
    ok "wgcf reinstalled"
  else
    skip "wgcf"
  fi
else
  info "Downloading wgcf..."
  wget -qO /usr/local/bin/wgcf "https://github.com/ViRb3/wgcf/releases/latest/download/wgcf_${ARCH_NAME}"
  chmod +x /usr/local/bin/wgcf
  ok "wgcf installed"
fi

# ── WIREGUARD TOOLS ─────────────────────────────
echo -n "  wireguard-tools: "
if command -v wg >/dev/null 2>&1; then
  skip "wireguard-tools"
else
  info "Installing wireguard-tools..."
  apk add wireguard-tools 2>/dev/null || apt-get install -y -qq wireguard-tools 2>/dev/null
  ok "wireguard-tools installed"
fi

# ── PYTHON3 ─────────────────────────────────────
echo -n "  python3: "
if command -v python3 >/dev/null 2>&1; then
  skip "python3"
else
  info "Installing python3..."
  apk add python3 2>/dev/null || apt-get install -y -qq python3 2>/dev/null
  ok "python3 installed"
fi

echo ""
echo "${W}[2/7] Config${N}"
echo ""

# ── BASE CONFIG ─────────────────────────────────
echo -n "  Base config (mixin): "
mkdir -p /etc/nikki
curl -sL "$REPO/openwrt/base.yml" -o /etc/nikki/mixin.yaml 2>/dev/null
if head -1 /etc/nikki/mixin.yaml | grep -q "Base config"; then
  ok "mixin.yaml ($(wc -l < /etc/nikki/mixin.yaml) lines)"
else
  fail "Download base config gagal"
  exit 1
fi

# ── PROXY LIST ──────────────────────────────────
echo -n "  Proxy list: "
mkdir -p /etc/nikki/run/providers
curl -sL "$REPO/output/live-proxies.mihomo.yml" -o /etc/nikki/run/providers/free-proxies.yml 2>/dev/null
if head -1 /etc/nikki/run/providers/free-proxies.yml | grep -q "Auto-generated"; then
  ok "free-proxies.yml ($(wc -l < /etc/nikki/run/providers/free-proxies.yml) lines)"
else
  fail "Download proxy list gagal"
  exit 1
fi

echo ""
echo "${W}[3/7] WARP${N}"
echo ""

# ── WARP SETUP ──────────────────────────────────
echo -n "  WARP accounts: "
if [ -f /etc/nikki/warp-creds.json ] && [ "$FORCE" != "1" ]; then
  skip "WARP credentials"
  # Ensure warp.yml exists in providers
  if [ ! -f /etc/nikki/run/providers/warp.yml ] && [ -f /etc/nikki/profiles/warp.yml ]; then
    cp /etc/nikki/profiles/warp.yml /etc/nikki/run/providers/warp.yml
    ok "warp.yml copied to providers"
  fi
else
  info "Generating WARP accounts..."
  curl -sL "$REPO/openwrt/warp-setup.sh" -o /etc/nikki/warp-setup.sh 2>/dev/null
  chmod +x /etc/nikki/warp-setup.sh
  ash /etc/nikki/warp-setup.sh
  # Copy to providers
  [ -f /etc/nikki/profiles/warp.yml ] && cp /etc/nikki/profiles/warp.yml /etc/nikki/run/providers/warp.yml
  ok "WARP accounts generated"
fi

echo ""
echo "${W}[4/7] Cron${N}"
echo ""

# ── UPDATE SCRIPT ───────────────────────────────
echo -n "  update-proxy.sh: "
cat > /usr/local/bin/update-proxy.sh << 'EOF'
#!/bin/sh
BASE_URL="https://api.github.com/repos/rickicode/free-proxy-singbox/contents"
RAW_URL="https://raw.githubusercontent.com/rickicode/free-proxy-singbox/refs/heads/main"
CHANGED=0
curl -sL -H "Accept: application/vnd.github.v3.raw" "$BASE_URL/openwrt/base.yml" -o /etc/nikki/mixin.yaml.tmp 2>/dev/null
if head -1 /etc/nikki/mixin.yaml.tmp | grep -q "Base config"; then
  mv /etc/nikki/mixin.yaml.tmp /etc/nikki/mixin.yaml
  CHANGED=1
else rm -f /etc/nikki/mixin.yaml.tmp; fi
curl -sL "$RAW_URL/output/live-proxies.mihomo.yml" -o /etc/nikki/run/providers/free-proxies.yml.tmp 2>/dev/null
if head -1 /etc/nikki/run/providers/free-proxies.yml.tmp | grep -q "Auto-generated"; then
  mv /etc/nikki/run/providers/free-proxies.yml.tmp /etc/nikki/run/providers/free-proxies.yml
  CHANGED=1
else rm -f /etc/nikki/run/providers/free-proxies.yml.tmp; fi
[ "$CHANGED" = "1" ] && /etc/init.d/nikki restart 2>/dev/null && echo "[$(date)] Updated" >> /var/log/proxy-update.log
EOF
chmod +x /usr/local/bin/update-proxy.sh
ok "update-proxy.sh"

# ── WARP REFRESH SCRIPT ────────────────────────
echo -n "  warp-refresh.sh: "
cat > /usr/local/bin/warp-refresh.sh << 'EOF'
#!/bin/sh
CRED=/etc/nikki/warp-creds.json
[ ! -f "$CRED" ] && ash /etc/nikki/warp-setup.sh && cp /etc/nikki/profiles/warp.yml /etc/nikki/run/providers/warp.yml && /etc/init.d/nikki restart && exit 0
last=$(python3 -c "import json,time;c=json.load(open('$CRED'));t=[v.get('refreshed_at','') for v in c.values() if v.get('refreshed_at')];print(f'{(time.time()-time.mktime(time.strptime(max(t),\"%Y-%m-%dT%H:%M:%SZ\")))/86400:.1f}')" 2>/dev/null || echo 99)
[ "$(echo "$last < 1.5" | bc -l 2>/dev/null || echo 0)" = "1" ] && exit 0
ash /etc/nikki/warp-setup.sh && cp /etc/nikki/profiles/warp.yml /etc/nikki/run/providers/warp.yml && /etc/init.d/nikki restart 2>/dev/null
EOF
chmod +x /usr/local/bin/warp-refresh.sh
ok "warp-refresh.sh"

# ── CRONTAB ─────────────────────────────────────
echo -n "  Crontab: "
(crontab -l 2>/dev/null | grep -v update-proxy | grep -v warp-refresh; \
 echo "0 */12 * * * /usr/local/bin/update-proxy.sh"; \
 echo "0 3 */2 * * /usr/local/bin/warp-refresh.sh") | crontab -
ok "Cron terpasang (proxy 12 jam, WARP 2 hari)"

echo ""
echo "${W}[5/7] Prox-Menu${N}"
echo ""

# ── INSTALL PROX-MENU ───────────────────────────
echo -n "  prox-menu: "
curl -sL "$REPO/openwrt/installer.sh" -o /usr/bin/prox-menu 2>/dev/null
chmod +x /usr/bin/prox-menu
if [ -f /usr/bin/prox-menu ]; then
  ok "prox-menu installed (/usr/bin/prox-menu)"
else
  fail "Gagal install prox-menu"
fi

echo ""
echo "${W}[6/7] Nikki${N}"
echo ""

# ── NIKKI CONFIG ────────────────────────────────
echo -n "  UCI config: "
uci set nikki.config.enabled=1 2>/dev/null
uci set nikki.proxy.tcp_mode=tproxy 2>/dev/null
uci set nikki.proxy.udp_mode=tproxy 2>/dev/null
uci set nikki.proxy.ipv4_dns_hijack=1 2>/dev/null
uci set nikki.proxy.lan_proxy=1 2>/dev/null
uci set nikki.mixin.api_listen="[::]:9090" 2>/dev/null
uci set nikki.mixin.api_secret="hijinet" 2>/dev/null
uci commit nikki 2>/dev/null
ok "UCI configured"

# ── FIREWALL ────────────────────────────────────
echo -n "  DNS redirect: "
if iptables -t nat -C PREROUTING -p tcp --dport 53 -j REDIRECT --to-ports 1053 2>/dev/null; then
  skip "DNS redirect"
else
  iptables -t nat -A PREROUTING -p tcp --dport 53 -j REDIRECT --to-ports 1053 2>/dev/null
  iptables -t nat -A PREROUTING -p udp --dport 53 -j REDIRECT --to-ports 1053 2>/dev/null
  ok "DNS redirect added"
fi

# ── START NIKKI ─────────────────────────────────
echo -n "  Start Nikki: "
/etc/init.d/nikki restart 2>/dev/null
sleep 3
if pgrep -x mihomo >/dev/null 2>&1; then
  ok "Mihomo running (PID $(pgrep -x mihomo))"
else
  fail "Mihomo gagal start — cek: tail /var/log/nikki/core.log"
fi

echo ""
echo "${W}[7/7] Verifikasi${N}"
echo ""

# ── VERIFY ──────────────────────────────────────
echo -n "  API: "
if curl -s --max-time 2 -H "Authorization: Bearer hijinet" http://127.0.0.1:9090/proxies >/dev/null 2>&1; then
  ok "API active (port 9090)"
else
  fail "API not responding"
fi

echo -n "  WAN1: "
if curl -s --max-time 3 http://www.gstatic.com/generate_204 -o /dev/null 2>&1; then
  ok "WAN1 connected"
else
  fail "WAN1 no internet"
fi

echo -n "  Proxies: "
proxy_count=$(curl -s -H "Authorization: Bearer hijinet" http://127.0.0.1:9090/providers/proxies 2>/dev/null | python3 -c "import json,sys; d=json.loads(json.load(sys.stdin)['out-data']); print(len(d.get('providers',{}).get('free',{}).get('proxies',[])))" 2>/dev/null || echo "0")
if [ "$proxy_count" -gt 0 ]; then
  ok "$proxy_count proxies loaded"
else
  fail "No proxies loaded"
fi

echo -n "  WARP: "
warp_count=$(curl -s -H "Authorization: Bearer hijinet" http://127.0.0.1:9090/providers/proxies 2>/dev/null | python3 -c "import json,sys; d=json.loads(json.load(sys.stdin)['out-data']); print(len(d.get('providers',{}).get('warp',{}).get('proxies',[])))" 2>/dev/null || echo "0")
if [ "$warp_count" -gt 0 ]; then
  ok "$warp_count WARP proxies"
else
  echo "${Y}⚠ WARP belum ter-load${N}"
fi

echo ""
echo "${B}╔══════════════════════════════════════════════════╗${N}"
echo "${B}║${G}       Install selesai!                             ${B}║${N}"
echo "${B}╚══════════════════════════════════════════════════╝${N}"
echo ""
echo "  Jalankan: ${W}prox-menu${N} untuk membuka menu"
echo ""
echo "  Proxy endpoints:"
echo "    1010 — WAN (default WAN2)"
echo "    1011 — FREE proxy"
echo "    1012 — ASIA proxy"
echo "    1013 — WARP"
echo ""
echo "  Dashboard: http://$(ip -4 addr show br-lan 2>/dev/null | grep inet | head -1 | awk '{print $2}' | cut -d/ -f1):9090"
echo ""
