#!/bin/sh
# OpenWrt Proxy Manager — Interactive Installer
# Usage: wget -O installer.sh <url> && ash installer.sh

set -e
REPO="https://raw.githubusercontent.com/rickicode/free-proxy-singbox/refs/heads/main"
GITHUB_API="https://api.github.com/repos/rickicode/free-proxy-singbox/contents"

# Colors
R='\033[0;31m' G='\033[0;32m' Y='\033[1;33m' B='\033[0;34m' C='\033[0;36m' W='\033[1;37m' N='\033[0m'

header() {
  clear
  echo "${B}╔══════════════════════════════════════════════════╗${N}"
  echo "${B}║${W}       OpenWrt Proxy Manager — free-proxy-singbox  ${B}║${N}"
  echo "${B}╚══════════════════════════════════════════════════╝${N}"
  echo ""
}

check_root() {
  [ "$(id -u)" != "0" ] && echo "${R}ERROR: Jalankan sebagai root${N}" && exit 1
}

check_openwrt() {
  [ ! -f /etc/openwrt_release ] && echo "${R}ERROR: Bukan OpenWrt${N}" && exit 1
}

check_nikki() {
  if ! command -v nikki >/dev/null 2>&1 && ! pgrep -x nikki >/dev/null 2>&1; then
    echo "${Y}WARNING: Nikki belum terinstall${N}"
    return 1
  fi
  return 0
}

check_mihomo() {
  if ! pgrep -x mihomo >/dev/null 2>&1; then
    echo "${Y}WARNING: Mihomo tidak berjalan${N}"
    return 1
  fi
  return 0
}

# ── STATUS ──────────────────────────────────────
show_status() {
  header
  echo "${W}═══ STATUS ═══${N}"
  echo ""

  # System
  echo "${C}System:${N}"
  uptime | sed 's/^/  /'
  free -h 2>/dev/null | grep Mem | awk '{printf "  RAM: %s / %s (%.0f%%)\n", $3, $2, $3/$2*100}'
  df -h / | tail -1 | awk '{printf "  Disk: %s / %s (%s)\n", $3, $2, $5}'
  echo ""

  # Network
  echo "${C}Network:${N}"
  ip route show default | awk '{printf "  WAN1 (eth0): %s via %s\n", $5, $3}'
  ip route show dev eth1 2>/dev/null | grep default | awk '{printf "  WAN2 (eth1): via %s\n", $3}' || echo "  WAN2 (eth1): no default route"
  echo ""

  # Nikki/Mihomo
  echo "${C}Nikki/Mihomo:${N}"
  if pgrep -x mihomo >/dev/null 2>&1; then
    echo "  ${G}✓ Mihomo running${N} (PID $(pgrep -x mihomo))"
  else
    echo "  ${R}✗ Mihomo not running${N}"
  fi
  if curl -s --max-time 2 -H "Authorization: Bearer hijinet" http://127.0.0.1:9090/proxies >/dev/null 2>&1; then
    echo "  ${G}✓ API active${N} (port 9090)"
  else
    echo "  ${R}✗ API not responding${N}"
  fi
  echo ""

  # Ports
  echo "${C}Listening Ports:${N}"
  netstat -tlnp 2>/dev/null | grep -E "7890|9090|1053|101[0-3]|22" | awk '{printf "  %s %s\n", $4, $7}' || ss -tlnp | grep -E "7890|9090|1053|101[0-3]|22"
  echo ""

  # Tailscale
  echo "${C}Tailscale:${N}"
  if command -v tailscale >/dev/null 2>&1; then
    ts_status=$(tailscale status 2>/dev/null | head -1)
    if [ -n "$ts_status" ]; then
      ts_ip=$(tailscale ip -4 2>/dev/null)
      echo "  ${G}✓ Connected${N} ($ts_ip)"
    else
      echo "  ${Y}⚠ Not connected${N}"
    fi
  else
    echo "  Not installed"
  fi
  echo ""

  echo "${Y}Tekan Enter untuk kembali...${N}"
  read -r
}

# ── DOCTOR ──────────────────────────────────────
run_doctor() {
  header
  echo "${W}═══ DOCTOR ═══${N}"
  echo ""

  issues=0

  # Check 1: Nikki installed
  echo -n "  Nikki installed: "
  if command -v nikki >/dev/null 2>&1 || [ -f /usr/bin/nikki ]; then
    echo "${G}✓${N}"
  else
    echo "${R}✗ — install: apk add nikki luci-app-nikki${N}"
    issues=$((issues+1))
  fi

  # Check 2: Mihomo running
  echo -n "  Mihomo running: "
  if pgrep -x mihomo >/dev/null 2>&1; then
    echo "${G}✓${N}"
  else
    echo "${R}✗ — jalankan: /etc/init.d/nikki restart${N}"
    issues=$((issues+1))
  fi

  # Check 3: API responding
  echo -n "  API responding: "
  if curl -s --max-time 2 -H "Authorization: Bearer hijinet" http://127.0.0.1:9090/proxies >/dev/null 2>&1; then
    echo "${G}✓${N}"
  else
    echo "${R}✗${N}"
    issues=$((issues+1))
  fi

  # Check 4: Proxy providers loaded
  echo -n "  Proxy providers: "
  free_count=$(curl -s -H "Authorization: Bearer hijinet" http://127.0.0.1:9090/providers/proxies 2>/dev/null | python3 -c "import json,sys; d=json.loads(json.load(sys.stdin)['out-data']); print(len(d.get('providers',{}).get('free',{}).get('proxies',[])))" 2>/dev/null || echo "0")
  if [ "$free_count" -gt 0 ]; then
    echo "${G}✓ ($free_count proxies)${N}"
  else
    echo "${R}✗ — proxy list tidak ter-load${N}"
    issues=$((issues+1))
  fi

  # Check 5: WARP
  echo -n "  WARP proxies: "
  warp_count=$(curl -s -H "Authorization: Bearer hijinet" http://127.0.0.1:9090/providers/proxies 2>/dev/null | python3 -c "import json,sys; d=json.loads(json.load(sys.stdin)['out-data']); print(len(d.get('providers',{}).get('warp',{}).get('proxies',[])))" 2>/dev/null || echo "0")
  if [ "$warp_count" -gt 0 ]; then
    echo "${G}✓ ($warp_count proxies)${N}"
  else
    echo "${Y}⚠ WARP tidak ter-load — jalankan: ash /etc/nikki/warp-setup.sh${N}"
  fi

  # Check 6: WAN1 connectivity
  echo -n "  WAN1 connectivity: "
  if curl -s --max-time 3 http://www.gstatic.com/generate_204 -o /dev/null 2>&1; then
    echo "${G}✓${N}"
  else
    echo "${R}✗ — WAN1 tidak ada internet${N}"
    issues=$((issues+1))
  fi

  # Check 7: DNS hijack
  echo -n "  DNS hijack: "
  if nft list chain inet nikki router_dns_hijack >/dev/null 2>&1; then
    echo "${G}✓${N}"
  else
    echo "${Y}⚠ nftables chain tidak ditemukan${N}"
  fi

  # Check 8: Cron
  echo -n "  Cron jobs: "
  cron_count=$(crontab -l 2>/dev/null | grep -c "update-proxy\|warp-refresh" || echo "0")
  if [ "$cron_count" -gt 0 ]; then
    echo "${G}✓ ($cron_count jobs)${N}"
  else
    echo "${Y}⚠ Tidak ada cron — setup via menu Install${N}"
  fi

  # Check 9: Rules loaded
  echo -n "  Rules loaded: "
  rule_count=$(curl -s -H "Authorization: Bearer hijinet" http://127.0.0.1:9090/rules 2>/dev/null | python3 -c "import json,sys; d=json.loads(json.load(sys.stdin)['out-data']); print(len(d.get('rules',[])))" 2>/dev/null || echo "0")
  if [ "$rule_count" -gt 0 ]; then
    echo "${G}✓ ($rule_count rules)${N}"
  else
    echo "${R}✗ — rules tidak ter-load${N}"
    issues=$((issues+1))
  fi

  echo ""
  if [ "$issues" -eq 0 ]; then
    echo "${G}═══ Semua OK! Tidak ada masalah. ═══${N}"
  else
    echo "${R}═══ $issues masalah ditemukan. ═══${N}"
  fi

  echo ""
  echo "${Y}Tekan Enter untuk kembali...${N}"
  read -r
}

# ── PROXY GROUPS ────────────────────────────────
show_groups() {
  header
  echo "${W}═══ PROXY GROUPS ═══${N}"
  echo ""

  curl -s -H "Authorization: Bearer hijinet" http://127.0.0.1:9090/proxies 2>/dev/null | python3 -c "
import json,sys
d=json.loads(json.load(sys.stdin)['out-data'])
for n,i in d.get('proxies',{}).items():
    t=i.get('type','')
    m=len(i.get('all',[]))
    now=i.get('now','')
    if t in ('Selector','URLTest','LoadBalance'):
        status = '✓' if i.get('alive',True) else '✗'
        print(f'  {status} {n:20s} ({t:10s}) {m:3d} members  → {now}')
" 2>/dev/null

  echo ""
  echo "${Y}Tekan Enter untuk kembali...${N}"
  read -r
}

# ── PROXY TEST ──────────────────────────────────
test_proxies() {
  header
  echo "${W}═══ PROXY TEST ═══${N}"
  echo ""

  echo "Testing koneksi..."
  echo ""

  # Direct
  echo -n "  DIRECT (WAN1): "
  result=$(curl -s --max-time 5 http://ifconfig.me 2>/dev/null)
  [ -n "$result" ] && echo "${G}$result${N}" || echo "${R}timeout${N}"

  # PROXY-FREE
  echo -n "  PROXY-FREE: "
  # Test via first free proxy in group
  echo "${C}(cek di dashboard)${N}"

  # WARP
  echo -n "  WARP: "
  echo "${C}(cek di dashboard)${N}"

  echo ""
  echo "${Y}Tekan Enter untuk kembali...${N}"
  read -r
}

# ── UPDATE ──────────────────────────────────────
update_proxy() {
  header
  echo "${W}═══ UPDATE PROXY ═══${N}"
  echo ""

  echo "1) Update proxy list + config (dari GitHub)"
  echo "2) Update mixin (base config) saja"
  echo "3) Update proxy list saja"
  echo "4) Restart Nikki"
  echo "0) Kembali"
  echo ""
  printf "Pilih: "
  read -r choice

  case "$choice" in
    1)
      echo ""
      echo "Downloading base config..."
      curl -sL "$GITHUB_API/openwrt/base.yml" -o /etc/nikki/mixin.yaml 2>/dev/null
      if head -1 /etc/nikki/mixin.yaml | grep -q "Base config"; then
        echo "${G}  ✓ Base config OK${N}"
      else
        echo "${R}  ✗ Base config gagal${N}"
      fi

      echo "Downloading proxy list..."
      curl -sL "$REPO/output/live-proxies.mihomo.yml" -o /etc/nikki/run/providers/free-proxies.yml 2>/dev/null
      if head -1 /etc/nikki/run/providers/free-proxies.yml | grep -q "Auto-generated"; then
        echo "${G}  ✓ Proxy list OK${N}"
      else
        echo "${R}  ✗ Proxy list gagal${N}"
      fi

      echo "Restarting Nikki..."
      /etc/init.d/nikki restart 2>/dev/null
      sleep 3
      if pgrep -x mihomo >/dev/null 2>&1; then
        echo "${G}  ✓ Nikki running${N}"
      else
        echo "${R}  ✗ Nikki gagal start${N}"
      fi
      ;;
    2)
      echo ""
      curl -sL "$GITHUB_API/openwrt/base.yml" -o /etc/nikki/mixin.yaml 2>/dev/null
      /etc/init.d/nikki restart 2>/dev/null
      echo "${G}✓ Mixin updated & Nikki restarted${N}"
      ;;
    3)
      echo ""
      curl -sL "$REPO/output/live-proxies.mihomo.yml" -o /etc/nikki/run/providers/free-proxies.yml 2>/dev/null
      /etc/init.d/nikki restart 2>/dev/null
      echo "${G}✓ Proxy list updated & Nikki restarted${N}"
      ;;
    4)
      echo ""
      /etc/init.d/nikki restart 2>/dev/null
      echo "${G}✓ Nikki restarted${N}"
      ;;
    0) return ;;
  esac

  echo ""
  echo "${Y}Tekan Enter untuk kembali...${N}"
  read -r
}

# ── WARP ────────────────────────────────────────
manage_warp() {
  header
  echo "${W}═══ WARP MANAGEMENT ═══${N}"
  echo ""

  # Check WARP status
  warp_count=$(curl -s -H "Authorization: Bearer hijinet" http://127.0.0.1:9090/providers/proxies 2>/dev/null | python3 -c "import json,sys; d=json.loads(json.load(sys.stdin)['out-data']); print(len(d.get('providers',{}).get('warp',{}).get('proxies',[])))" 2>/dev/null || echo "0")

  echo "  WARP proxies: $warp_count"
  if [ -f /etc/nikki/warp-creds.json ]; then
    echo "  ${G}✓ warp-creds.json exists${N}"
  else
    echo "  ${Y}⚠ warp-creds.json tidak ada${N}"
  fi
  echo ""

  echo "1) Generate WARP accounts baru (wgcf)"
  echo "2) Lihat WARP credentials"
  echo "3) Restart Nikki"
  echo "0) Kembali"
  echo ""
  printf "Pilih: "
  read -r choice

  case "$choice" in
    1)
      echo ""
      if [ ! -f /etc/nikki/warp-setup.sh ]; then
        echo "Downloading warp-setup.sh..."
        curl -sL "$REPO/openwrt/warp-setup.sh" -o /etc/nikki/warp-setup.sh 2>/dev/null
        chmod +x /etc/nikki/warp-setup.sh
      fi
      ash /etc/nikki/warp-setup.sh
      ;;
    2)
      echo ""
      if [ -f /etc/nikki/warp-creds.json ]; then
        cat /etc/nikki/warp-creds.json
      else
        echo "${Y}Tidak ada credentials${N}"
      fi
      ;;
    3)
      /etc/init.d/nikki restart 2>/dev/null
      echo "${G}✓ Nikki restarted${N}"
      ;;
    0) return ;;
  esac

  echo ""
  echo "${Y}Tekan Enter untuk kembali...${N}"
  read -r
}

# ── CRON ────────────────────────────────────────
manage_cron() {
  header
  echo "${W}═══ CRON / SCHEDULER ═══${N}"
  echo ""

  echo "${C}Current cron jobs:${N}"
  crontab -l 2>/dev/null | grep -v "^#" | sed 's/^/  /'
  echo ""

  echo "1) Setup cron auto-update (proxy + WARP)"
  echo "2) Hapus semua cron"
  echo "3) Update proxy sekarang"
  echo "0) Kembali"
  echo ""
  printf "Pilih: "
  read -r choice

  case "$choice" in
    1)
      echo ""
      # Create update script
      cat > /usr/local/bin/update-proxy.sh << 'EOF'
#!/bin/sh
BASE_URL="https://api.github.com/repos/rickicode/free-proxy-singbox/contents"
CHANGED=0
curl -sL -H "Accept: application/vnd.github.v3.raw" "$BASE_URL/openwrt/base.yml" -o /etc/nikki/mixin.yaml.tmp 2>/dev/null
if head -1 /etc/nikki/mixin.yaml.tmp | grep -q "Base config"; then
  mv /etc/nikki/mixin.yaml.tmp /etc/nikki/mixin.yaml
  CHANGED=1
else rm -f /etc/nikki/mixin.yaml.tmp; fi
curl -sL "https://raw.githubusercontent.com/rickicode/free-proxy-singbox/refs/heads/main/output/live-proxies.mihomo.yml" -o /etc/nikki/run/providers/free-proxies.yml.tmp 2>/dev/null
if head -1 /etc/nikki/run/providers/free-proxies.yml.tmp | grep -q "Auto-generated"; then
  mv /etc/nikki/run/providers/free-proxies.yml.tmp /etc/nikki/run/providers/free-proxies.yml
  CHANGED=1
else rm -f /etc/nikki/run/providers/free-proxies.yml.tmp; fi
[ "$CHANGED" = "1" ] && /etc/init.d/nikki restart 2>/dev/null && echo "[$(date)] Updated" >> /var/log/proxy-update.log
EOF
      chmod +x /usr/local/bin/update-proxy.sh

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
      echo "${G}✓ Cron terpasang${N}"
      ;;
    2)
      crontab -l 2>/dev/null | grep -v update-proxy | grep -v warp-refresh | crontab -
      echo "${G}✓ Cron dihapus${N}"
      ;;
    3)
      echo ""
      /usr/local/bin/update-proxy.sh 2>/dev/null && echo "${G}✓ Updated${N}" || echo "${R}✗ Gagal${N}"
      ;;
    0) return ;;
  esac

  echo ""
  echo "${Y}Tekan Enter untuk kembali...${N}"
  read -r
}

# ── INSTALL ─────────────────────────────────────
full_install() {
  header
  echo "${W}═══ FULL INSTALL ═══${N}"
  echo ""

  check_root
  check_openwrt

  echo "1) Download base config..."
  curl -sL "$GITHUB_API/openwrt/base.yml" -o /etc/nikki/mixin.yaml 2>/dev/null
  echo "${G}  ✓${N}"

  echo "2) Download proxy list..."
  mkdir -p /etc/nikki/run/providers
  curl -sL "$REPO/output/live-proxies.mihomo.yml" -o /etc/nikki/run/providers/free-proxies.yml 2>/dev/null
  echo "${G}  ✓${N}"

  echo "3) Install wgcf + generate WARP..."
  curl -sL "$REPO/openwrt/warp-setup.sh" -o /etc/nikki/warp-setup.sh 2>/dev/null
  chmod +x /etc/nikki/warp-setup.sh
  ash /etc/nikki/warp-setup.sh

  echo "4) Setup cron..."
  cat > /usr/local/bin/update-proxy.sh << 'EOF'
#!/bin/sh
BASE_URL="https://api.github.com/repos/rickicode/free-proxy-singbox/contents"
CHANGED=0
curl -sL -H "Accept: application/vnd.github.v3.raw" "$BASE_URL/openwrt/base.yml" -o /etc/nikki/mixin.yaml.tmp 2>/dev/null
if head -1 /etc/nikki/mixin.yaml.tmp | grep -q "Base config"; then
  mv /etc/nikki/mixin.yaml.tmp /etc/nikki/mixin.yaml
  CHANGED=1
else rm -f /etc/nikki/mixin.yaml.tmp; fi
curl -sL "https://raw.githubusercontent.com/rickicode/free-proxy-singbox/refs/heads/main/output/live-proxies.mihomo.yml" -o /etc/nikki/run/providers/free-proxies.yml.tmp 2>/dev/null
if head -1 /etc/nikki/run/providers/free-proxies.yml.tmp | grep -q "Auto-generated"; then
  mv /etc/nikki/run/providers/free-proxies.yml.tmp /etc/nikki/run/providers/free-proxies.yml
  CHANGED=1
else rm -f /etc/nikki/run/providers/free-proxies.yml.tmp; fi
[ "$CHANGED" = "1" ] && /etc/init.d/nikki restart 2>/dev/null && echo "[$(date)] Updated" >> /var/log/proxy-update.log
EOF
  chmod +x /usr/local/bin/update-proxy.sh
  (crontab -l 2>/dev/null | grep -v update-proxy; echo "0 */12 * * * /usr/local/bin/update-proxy.sh") | crontab -
  echo "${G}  ✓${N}"

  echo "5) Restart Nikki..."
  /etc/init.d/nikki restart 2>/dev/null
  sleep 3
  if pgrep -x mihomo >/dev/null 2>&1; then
    echo "${G}  ✓ Nikki running${N}"
  else
    echo "${R}  ✗ Nikki gagal start${N}"
  fi

  echo ""
  echo "${G}═══ Install selesai! ═══${N}"
  echo ""
  echo "${Y}Tekan Enter untuk kembali...${N}"
  read -r
}

# ── LOGS ────────────────────────────────────────
show_logs() {
  header
  echo "${W}═══ LOGS ═══${N}"
  echo ""
  echo "1) Nikki app log"
  echo "2) Nikki core log"
  echo "3) Proxy update log"
  echo "0) Kembali"
  echo ""
  printf "Pilih: "
  read -r choice

  case "$choice" in
    1) tail -30 /var/log/nikki/app.log ;;
    2) tail -30 /var/log/nikki/core.log ;;
    3) tail -30 /var/log/proxy-update.log 2>/dev/null || echo "Belum ada log" ;;
    0) return ;;
  esac

  echo ""
  echo "${Y}Tekan Enter untuk kembali...${N}"
  read -r
}

# ── SELF INSTALL ─────────────────────────────────
install_command() {
  header
  echo "${W}═══ INSTALL PROX-MENU COMMAND ═══${N}"
  echo ""
  
  echo "Menginstall ke /usr/bin/prox-menu..."
  
  # Download latest version
  curl -sL "$REPO/openwrt/installer.sh" -o /usr/bin/prox-menu 2>/dev/null
  chmod +x /usr/bin/prox-menu
  
  if [ -f /usr/bin/prox-menu ]; then
    echo "${G}✓ prox-menu terinstall!${N}"
    echo ""
    echo "Jalankan dengan: ${W}prox-menu${N}"
  else
    echo "${R}✗ Gagal install${N}"
  fi
  
  echo ""
  echo "${Y}Tekan Enter untuk kembali...${N}"
  read -r
}

# ── MAIN MENU ───────────────────────────────────
main_menu() {
  while true; do
    header
    echo "${W}Menu:${N}"
    echo ""
    echo "  ${G}1)${N} Status      — Lihat status sistem"
    echo "  ${G}2)${N} Doctor      — Diagnosa masalah"
    echo "  ${G}3)${N} Groups      — Lihat proxy groups"
    echo "  ${G}4)${N} Update      — Update proxy/config"
    echo "  ${G}5)${N} WARP        — Kelola WARP"
    echo "  ${G}6)${N} Cron        — Kelola scheduler"
    echo "  ${G}7)${N} Logs        — Lihat log"
    echo "  ${G}8)${N} Install     — Full install"
    echo "  ${G}9)${N} Install CMD — Install prox-menu command"
    echo "  ${R}0)${N} Keluar"
    echo ""
    printf "Pilih: "
    read -r choice

    case "$choice" in
      1) show_status ;;
      2) run_doctor ;;
      3) show_groups ;;
      4) update_proxy ;;
      5) manage_warp ;;
      6) manage_cron ;;
      7) show_logs ;;
      8) full_install ;;
      9) install_command ;;
      0) echo "${G}Bye!${N}"; exit 0 ;;
      *) echo "${R}Pilihan tidak valid${N}"; sleep 1 ;;
    esac
  done
}

# ── RUN ─────────────────────────────────────────
check_root
check_openwrt
main_menu
