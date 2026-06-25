# free-proxy-singbox

Proxy scanner + OpenWrt gateway manager. Mengumpulkan proxy publik yang live dan menyediakan config siap pakai untuk Nikki/Mihomo di OpenWrt.

## Quick Start

### Install (OpenWrt)

```bash
ash <(curl -sL https://raw.githubusercontent.com/rickicode/free-proxy-singbox/refs/heads/main/openwrt/installer.sh)
```

Installer otomatis:
- Install Nikki + Mihomo
- Install wgcf + wireguard-tools
- Download config + proxy list
- Generate 3 WARP accounts (per-device)
- Setup cron auto-update
- Install `prox-menu` command

### Menu

```bash
prox-menu
```

```
╔══════════════════════════════════════════════════╗
║       prox-menu — Proxy Manager                   ║
╚══════════════════════════════════════════════════╝

  1) Status      — Sistem, jaringan, nikki
  2) Doctor      — Diagnosa masalah
  3) Groups      — Proxy groups & members
  4) Test        — Test koneksi proxy
  5) Update      — Update proxy/config
  6) WARP        — Kelola WARP
  7) Cron        — Scheduler
  8) Logs        — Lihat log
  0) Keluar
```

### Force Reinstall

```bash
ash installer.sh --force
```

## Arsitektur

```
┌─────────────────────────────────────────────────────┐
│  GitHub Repo (free-proxy-singbox)                    │
│  ├── freeproxy.py — scanner (tiap 12 jam)           │
│  ├── output/live-proxies.mihomo.yml — proxy list    │
│  ├── openwrt/base.yml — mixin config                │
│  └── openwrt/rules/*.yml — rule providers           │
└─────────────────────────────────────────────────────┘
          ↓ download
┌─────────────────────────────────────────────────────┐
│  OpenWrt Router                                      │
│  ├── /etc/nikki/mixin.yaml — base config             │
│  ├── /etc/nikki/run/providers/                       │
│  │   ├── free-proxies.yml — free proxies (auto)      │
│  │   └── warp.yml — WARP proxies (per-device)        │
│  └── /usr/bin/prox-menu — interactive menu           │
└─────────────────────────────────────────────────────┘
```

## Proxy Endpoints

| Port | Group | Default | Description |
|------|-------|---------|-------------|
| 1010 | PROXY-1010 | WAN2 | WAN selector |
| 1011 | PROXY-1011 | PROXY-FREE | Free proxy selector |
| 1012 | PROXY-1012 | PROXY-ASIA | Asia proxy selector |
| 1013 | PROXY-1013 | WARP-LB | WARP selector |
| 7890 | mixed | GLOBAL | Default mixed proxy |
| 9090 | API | — | Mihomo dashboard |
| 1053 | DNS | — | Mihomo DNS (fake-ip) |

### Proxy Groups

| Group | Type | Description |
|-------|------|-------------|
| GLOBAL | Selector | Catch-all |
| WAN | Selector | WAN1/WAN2 |
| WAN-AUTO | LoadBalance | Auto-select WAN |
| PROXY-FREE | URLTest | All free proxies |
| PROXY-ID | URLTest | Indonesia |
| PROXY-SG | URLTest | Singapore |
| PROXY-US | URLTest | US |
| PROXY-ASIA | URLTest | Asia region |
| PROXY-EU | URLTest | Europe region |
| WARP-LB | LoadBalance | WARP load balance |
| PROXY-WARP | Selector | WARP group |
| BLOCKED | Selector | Ad blocking |
| GOOGLE | Selector | Google services |
| AI | Selector | AI services |
| CHECK-IP | Selector | IP check sites |
| SOCIAL | Selector | Social media |

### Rules

| Rule | Target |
|------|--------|
| Ads (GEOSITE) | BLOCKED |
| STUN ports (3478, 5349, 19302) | BLOCKED |
| IP check domains | CHECK-IP |
| Private/CN | DIRECT |
| Google | GOOGLE |
| AI services | AI |
| Social media | SOCIAL |
| Catch-all | GLOBAL |

## Auto Update

| Job | Frequency | Description |
|-----|-----------|-------------|
| `update-proxy.sh` | Tiap 12 jam | Update proxy list + base config |
| `warp-refresh.sh` | Tiap 2 hari | Refresh WARP accounts jika expired |

## File Structure

```
openwrt/
├── installer.sh    — Auto-install deps + prox-menu
├── prox-menu.sh    — Interactive menu (prox-menu command)
├── base.yml        — Mihomo mixin config (rules, groups, providers)
├── warp-setup.sh   — WARP account generator (per-device)
├── rules/          — Rule provider files
│   ├── private.yml
│   ├── google.yml
│   ├── ai.yml
│   ├── check-ip.yml
│   └── social.yml
└── README.md
```

## Commands

```bash
# Install
ash installer.sh

# Menu
prox-menu

# Force reinstall deps
ash installer.sh --force

# Manual update
/usr/local/bin/update-proxy.sh

# Manual WARP refresh
/usr/local/bin/warp-refresh.sh

# Check status
prox-menu  # → pilih 1

# Diagnose issues
prox-menu  # → pilih 2
```

## Output Files

- `output/live-proxies.json` — Raw scan results
- `output/live-proxies.mihomo.yml` — Mihomo proxy-provider format
- `output/live-proxies.singbox.json` — Sing-box config format
- `output/latest-summary.json` — Scan summary

## GitHub Actions

- Scan tiap 12 jam (4 shard paralel)
- Merge hasil → commit ke repo
- Proxy list auto-update
