#!/bin/sh
# prox-menu — OpenWrt Proxy Manager
# Interactive menu for managing free-proxy-singbox
# Install: ash installer.sh (auto-installs to /usr/bin/prox-menu)

REPO="https://raw.githubusercontent.com/rickicode/free-proxy-singbox/refs/heads/main"
GITHUB_API="https://api.github.com/repos/rickicode/free-proxy-singbox/contents"

# Colors
R='\033[0;31m' G='\033[0;32m' Y='\033[1;33m' B='\033[0;34m' C='\033[0;36m' W='\033[1;37m' N='\033[0m'

header() {
  clear
  echo "${B}╔══════════════════════════════════════════════════╗${N}"
  echo "${B}║${W}       prox-menu — Proxy Manager                   ${B}║${N}"
  echo "${B}╚══════════════════════════════════════════════════╝${N}"
  echo ""
}

# ── STATUS ──────────────────────────────────────
show_status() {
  header
  echo "${W}═══ STATUS ═══${N}"
  echo ""

  echo "${C}System:${N}"
  uptime | sed 's/^/  /'
  free -h 2>/dev/null | grep Mem | awk '{printf "  RAM: %s / %s (%.0f%%)\n", $3, $2, $3/$2*100}'
  df -h / | tail -1 | awk '{printf "  Disk: %s / %s (%s)\n", $3, $2, $5}'
  echo ""

  echo "${C}Network:${N}"
  ip route show default | awk '{printf "  WAN1 (%s): via %s\n", $5, $3}'
  ip route show dev eth1 2>/dev/null | grep default | awk '{printf "  WAN2 (eth1): via %s\n", $3}' || echo "  WAN2 (eth1): no default route"
  echo ""

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

  echo "${C}Ports:${N}"
  netstat -tlnp 2>/dev/null | grep -E "7890|9090|1053|101[0-3]|22" | awk '{printf "  %-20s %s\n", $4, $7}' || ss -tlnp | grep -E "7890|9090|1053|101[0-3]|22"
  echo ""

  echo "${C}Tailscale:${N}"
  if command -v tailscale >/dev/null 2>&1; then
    ts_ip=$(tailscale ip -4 2>/dev/null)
    [ -n "$ts_ip" ] && echo "  ${G}✓ Connected${N} ($ts_ip)" || echo "  ${Y}⚠ Not connected${N}"
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

  echo -n "  Nikki installed: "
  command -v nikki >/dev/null 2>&1 || [ -f /usr/bin/nikki ] && echo "${G}✓${N}" || { echo "${R}✗${N}"; issues=$((issues+1)); }

  echo -n "  Mihomo running: "
  pgrep -x mihomo >/dev/null 2>&1 && echo "${G}✓${N}" || { echo "${R}✗${N}"; issues=$((issues+1)); }

  echo -n "  API responding: "
  curl -s --max-time 2 -H "Authorization: Bearer hijinet" http://127.0.0.1:9090/proxies >/dev/null 2>&1 && echo "${G}✓${N}" || { echo "${R}✗${N}"; issues=$((issues+1)); }

  echo -n "  Proxy providers: "
  free_count=$(curl -s -H "Authorization: Bearer hijinet" http://127.0.0.1:9090/providers/proxies 2>/dev/null | python3 -c "import json,sys; d=json.loads(json.load(sys.stdin)['out-data']); print(len(d.get('providers',{}).get('free',{}).get('proxies',[])))" 2>/dev/null || echo "0")
  [ "$free_count" -gt 0 ] && echo "${G}✓ ($free_count proxies)${N}" || { echo "${R}✗${N}"; issues=$((issues+1)); }

  echo -n "  WARP proxies: "
  warp_count=$(curl -s -H "Authorization: Bearer hijinet" http://127.0.0.1:9090/providers/proxies 2>/dev/null | python3 -c "import json,sys; d=json.loads(json.load(sys.stdin)['out-data']); print(len(d.get('providers',{}).get('warp',{}).get('proxies',[])))" 2>/dev/null || echo "0")
  [ "$warp_count" -gt 0 ] && echo "${G}✓ ($warp_count proxies)${N}" || echo "${Y}⚠ WARP tidak ter-load${N}"

  echo -n "  WAN1 connectivity: "
  curl -s --max-time 3 http://www.gstatic.com/generate_204 -o /dev/null 2>&1 && echo "${G}✓${N}" || { echo "${R}✗${N}"; issues=$((issues+1)); }

  echo -n "  Rules loaded: "
  rule_count=$(curl -s -H "Authorization: Bearer hijinet" http://127.0.0.1:9090/rules 2>/dev/null | python3 -c "import json,sys; d=json.loads(json.load(sys.stdin)['out-data']); print(len(d.get('rules',[])))" 2>/dev/null || echo "0")
  [ "$rule_count" -gt 0 ] && echo "${G}✓ ($rule_count rules)${N}" || { echo "${R}✗${N}"; issues=$((issues+1)); }

  echo -n "  Cron jobs: "
  cron_count=$(crontab -l 2>/dev/null | grep -c "update-proxy\|warp-refresh" || echo "0")
  [ "$cron_count" -gt 0 ] && echo "${G}✓ ($cron_count jobs)${N}" || echo "${Y}⚠ Tidak ada cron${N}"

  echo ""
  [ "$issues" -eq 0 ] && echo "${G}═══ Semua OK! ═══${N}" || echo "${R}═══ $issues masalah ditemukan ═══${N}"

  echo ""
  echo "${Y}Tekan Enter untuk kembali...${N}"
  read -r
}

# ── GROUPS ──────────────────────────────────────
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
        alive = '✓' if i.get('alive',True) else '✗'
        print(f'  {alive} {n:20s} {t:12s} {m:4d} members  → {now}')
" 2>/dev/null

  echo ""
  echo "${Y}Tekan Enter untuk kembali...${N}"
  read -r
}

# ── UPDATE ──────────────────────────────────────
update_proxy() {
  header
  echo "${W}═══ UPDATE ═══${N}"
  echo ""

  echo "  1) Update semua (base config + proxy list)"
  echo "  2) Update base config saja"
  echo "  3) Update proxy list saja"
  echo "  4) Restart Nikki"
  echo "  0) Kembali"
  echo ""
  printf "  Pilih: "
  read -r choice

  case "$choice" in
    1)
      echo ""
      info "Downloading base config..."
      curl -sL "$GITHUB_API/openwrt/base.yml" -o /etc/nikki/mixin.yaml 2>/dev/null
      head -1 /etc/nikki/mixin.yaml | grep -q "Base config" && echo "  ${G}✓${N} Base config" || echo "  ${R}✗${N} Base config gagal"

      info "Downloading proxy list..."
      curl -sL "$REPO/output/live-proxies.mihomo.yml" -o /etc/nikki/run/providers/free-proxies.yml 2>/dev/null
      head -1 /etc/nikki/run/providers/free-proxies.yml | grep -q "Auto-generated" && echo "  ${G}✓${N} Proxy list" || echo "  ${R}✗${N} Proxy list gagal"

      info "Restarting Nikki..."
      /etc/init.d/nikki restart 2>/dev/null
      sleep 3
      pgrep -x mihomo >/dev/null 2>&1 && echo "  ${G}✓${N} Nikki running" || echo "  ${R}✗${N} Nikki gagal start"
      ;;
    2)
      curl -sL "$GITHUB_API/openwrt/base.yml" -o /etc/nikki/mixin.yaml 2>/dev/null
      /etc/init.d/nikki restart 2>/dev/null
      echo "  ${G}✓${N} Mixin updated"
      ;;
    3)
      curl -sL "$REPO/output/live-proxies.mihomo.yml" -o /etc/nikki/run/providers/free-proxies.yml 2>/dev/null
      /etc/init.d/nikki restart 2>/dev/null
      echo "  ${G}✓${N} Proxy list updated"
      ;;
    4)
      /etc/init.d/nikki restart 2>/dev/null
      echo "  ${G}✓${N} Nikki restarted"
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
  echo "${W}═══ WARP ═══${N}"
  echo ""

  warp_count=$(curl -s -H "Authorization: Bearer hijinet" http://127.0.0.1:9090/providers/proxies 2>/dev/null | python3 -c "import json,sys; d=json.loads(json.load(sys.stdin)['out-data']); print(len(d.get('providers',{}).get('warp',{}).get('proxies',[])))" 2>/dev/null || echo "0")
  echo "  WARP proxies: $warp_count"
  [ -f /etc/nikki/warp-creds.json ] && echo "  ${G}✓${N} warp-creds.json exists" || echo "  ${Y}⚠${N} warp-creds.json tidak ada"
  echo ""

  echo "  1) Generate WARP accounts baru"
  echo "  2) Lihat WARP credentials"
  echo "  3) Restart Nikki"
  echo "  0) Kembali"
  echo ""
  printf "  Pilih: "
  read -r choice

  case "$choice" in
    1)
      [ ! -f /etc/nikki/warp-setup.sh ] && curl -sL "$REPO/openwrt/warp-setup.sh" -o /etc/nikki/warp-setup.sh 2>/dev/null && chmod +x /etc/nikki/warp-setup.sh
      ash /etc/nikki/warp-setup.sh
      [ -f /etc/nikki/profiles/warp.yml ] && cp /etc/nikki/profiles/warp.yml /etc/nikki/run/providers/warp.yml
      /etc/init.d/nikki restart 2>/dev/null
      ;;
    2)
      [ -f /etc/nikki/warp-creds.json ] && cat /etc/nikki/warp-creds.json || echo "  Tidak ada credentials"
      ;;
    3)
      /etc/init.d/nikki restart 2>/dev/null
      echo "  ${G}✓${N} Nikki restarted"
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
  echo "${W}═══ CRON ═══${N}"
  echo ""

  echo "${C}Current cron jobs:${N}"
  crontab -l 2>/dev/null | grep -v "^#" | sed 's/^/  /' || echo "  (kosong)"
  echo ""

  echo "  1) Setup cron (proxy 12 jam, WARP 2 hari)"
  echo "  2) Hapus semua cron"
  echo "  3) Update proxy sekarang"
  echo "  0) Kembali"
  echo ""
  printf "  Pilih: "
  read -r choice

  case "$choice" in
    1)
      (crontab -l 2>/dev/null | grep -v update-proxy | grep -v warp-refresh; \
       echo "0 */12 * * * /usr/local/bin/update-proxy.sh"; \
       echo "0 3 */2 * * /usr/local/bin/warp-refresh.sh") | crontab -
      echo "  ${G}✓${N} Cron terpasang"
      ;;
    2)
      crontab -l 2>/dev/null | grep -v update-proxy | grep -v warp-refresh | crontab -
      echo "  ${G}✓${N} Cron dihapus"
      ;;
    3)
      /usr/local/bin/update-proxy.sh 2>/dev/null && echo "  ${G}✓${N} Updated" || echo "  ${R}✗${N} Gagal"
      ;;
    0) return ;;
  esac

  echo ""
  echo "${Y}Tekan Enter untuk kembali...${N}"
  read -r
}

# ── LOGS ────────────────────────────────────────
show_logs() {
  header
  echo "${W}═══ LOGS ═══${N}"
  echo ""

  echo "  1) Nikki app log"
  echo "  2) Nikki core log"
  echo "  3) Proxy update log"
  echo "  0) Kembali"
  echo ""
  printf "  Pilih: "
  read -r choice

  case "$choice" in
    1) tail -30 /var/log/nikki/app.log ;;
    2) tail -30 /var/log/nikki/core.log ;;
    3) tail -30 /var/log/proxy-update.log 2>/dev/null || echo "  Belum ada log" ;;
    0) return ;;
  esac

  echo ""
  echo "${Y}Tekan Enter untuk kembali...${N}"
  read -r
}

# ── PROXY TEST ──────────────────────────────────
test_proxies() {
  header
  echo "${W}═══ PROXY TEST ═══${N}"
  echo ""

  echo "  Testing koneksi..."
  echo ""

  echo -n "  DIRECT (WAN1): "
  result=$(curl -s --max-time 5 http://ifconfig.me 2>/dev/null)
  [ -n "$result" ] && echo "${G}$result${N}" || echo "${R}timeout${N}"

  echo -n "  WAN2 (eth1): "
  result=$(curl -s --max-time 5 --interface eth1 http://ifconfig.me 2>/dev/null)
  [ -n "$result" ] && echo "${G}$result${N}" || echo "${R}timeout${N}"

  echo ""
  echo "  Proxy groups (cek di dashboard):"
  echo "  http://$(ip -4 addr show br-lan 2>/dev/null | grep inet | head -1 | awk '{print $2}' | cut -d/ -f1):9090/ui"
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
    echo "  ${G}1)${N} Status      — Sistem, jaringan, nikki"
    echo "  ${G}2)${N} Doctor      — Diagnosa masalah"
    echo "  ${G}3)${N} Groups      — Proxy groups & members"
    echo "  ${G}4)${N} Test        — Test koneksi proxy"
    echo "  ${G}5)${N} Update      — Update proxy/config"
    echo "  ${G}6)${N} WARP        — Kelola WARP"
    echo "  ${G}7)${N} Cron        — Scheduler"
    echo "  ${G}8)${N} Logs        — Lihat log"
    echo "  ${R}0)${N} Keluar"
    echo ""
    printf "  Pilih: "
    read -r choice

    case "$choice" in
      1) show_status ;;
      2) run_doctor ;;
      3) show_groups ;;
      4) test_proxies ;;
      5) update_proxy ;;
      6) manage_warp ;;
      7) manage_cron ;;
      8) show_logs ;;
      0) echo "${G}Bye!${N}"; exit 0 ;;
      *) echo "${R}Pilihan tidak valid${N}"; sleep 1 ;;
    esac
  done
}

# ── RUN ─────────────────────────────────────────
[ "$(id -u)" != "0" ] && echo "${R}ERROR: Jalankan sebagai root${N}" && exit 1
main_menu
