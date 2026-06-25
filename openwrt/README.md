# OpenWrt Gateway Setup

Setup OpenWrt router sebagai proxy gateway pakai **Nikki** (mihomo engine).

## Quick Start (1 Command)

```bash
ash <(curl -sL https://raw.githubusercontent.com/rickicode/free-proxy-gateway/refs/heads/main/openwrt/installer.sh)
```

**Installer otomatis install:**

| Step | Action | Skip jika sudah ada |
|------|--------|---------------------|
| 1 | Nikki + Mihomo | ✓ |
| 2 | wgcf (WARP generator) | ✓ |
| 3 | wireguard-tools | ✓ |
| 4 | python3 | ✓ |
| 5 | Base config (mixin.yaml) | — |
| 6 | Proxy list (free-proxies.yml) | — |
| 7 | 3 WARP accounts (per-device) | ✓ |
| 8 | Cron auto-update | — |
| 9 | `prox-menu` command | — |
| 10 | Start Nikki + verifikasi | — |

**Force reinstall dependencies:**

```bash
ash <(curl -sL https://raw.githubusercontent.com/rickicode/free-proxy-gateway/refs/heads/main/openwrt/installer.sh) --force
```

## Menu (Setelah Install)

```bash
prox-menu
```

```
╔══════════════════════════════════════════════════╗
║       prox-menu — Proxy Manager                   ║
╚══════════════════════════════════════════════════╝

  1) Status      — Sistem, jaringan, nikki
  2) Doctor      — Diagnosa masalah (9 checks)
  3) Groups      — Proxy groups & members
  4) Test        — Test koneksi proxy
  5) Update      — Update proxy/config
  6) WARP        — Kelola WARP
  7) Cron        — Scheduler
  8) Logs        — Lihat log
  0) Keluar
```

## Arsitektur

```
┌─────────────────────────────────────────────────────┐
│  GitHub Repo (free-proxy-gateway)                    │
│  ├── output/live-proxies.mihomo.yml — proxy list    │
│  ├── openwrt/base.yml — mixin config                │
│  └── openwrt/rules/*.yml — rule providers           │
└─────────────────────────────────────────────────────┘
          ↓ download (tiap 12 jam)
┌─────────────────────────────────────────────────────┐
│  OpenWrt Router                                      │
│  ├── /etc/nikki/mixin.yaml — base config             │
│  ├── /etc/nikki/run/providers/                       │
│  │   ├── free-proxies.yml — free proxies (auto)      │
│  │   └── warp.yml — WARP proxies (per-device)        │
│  └── /usr/bin/prox-menu — interactive menu           │
└─────────────────────────────────────────────────────┘
```

**Split config:**
| File | Isi | Source | Update |
|---|---|---|---|
| `mixin.yaml` | DNS, rules, ports, groups, proxy-providers | Repo | Auto tiap 12 jam |
| `free-proxies.yml` | Free proxy list | Repo | Auto tiap 12 jam |
| `warp.yml` | 3 WARP accounts (WireGuard keys) | **Per-device** | Auto tiap 2 hari |

**Privasi:** WARP keys di-generate per-device via wgcf, tidak pernah di-commit ke repo.

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

## Proxy Groups

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

## Rules

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
```

## File Structure

```
openwrt/
├── installer.sh    — Auto-install deps + prox-menu
├── prox-menu.sh    — Interactive menu command
├── base.yml        — Mihomo mixin config (rules, groups, providers)
├── warp-setup.sh   — WARP account generator (per-device)
├── rules/          — Rule provider files
│   ├── private.yml
│   ├── google.yml
│   ├── ai.yml
│   ├── check-ip.yml
│   └── social.yml
└── README.md       — This file
```

## Troubleshooting

```bash
# Jalankan doctor
prox-menu  # → pilih 2

# Cek log
prox-menu  # → pilih 8

# Restart Nikki
prox-menu  # → pilih 5 → pilih 4

# Cek status
prox-menu  # → pilih 1
```
