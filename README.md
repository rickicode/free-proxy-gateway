# free-proxy-gateway

Proxy scanner + gateway manager. Mengumpulkan proxy publik yang live dan menyediakan config siap pakai.

## Arsitektur

```
┌──────────────────────────────────────────────────────────┐
│  GitHub Actions (Ubuntu/Debian)                           │
│  ├── freeproxy.py — scan proxy tiap 12 jam               │
│  ├── output/live-proxies.mihomo.yml — proxy list         │
│  └── auto-commit ke repo                                 │
└──────────────────────────────────────────────────────────┘
          ↓ download
┌──────────────────────────────────────────────────────────┐
│  OpenWrt Router (Nikki + Mihomo)                          │
│  ├── base.yml — config (rules, groups, DNS)               │
│  ├── free-proxies.yml — proxy list (auto-update)          │
│  ├── warp.yml — WARP accounts (per-device)                │
│  └── prox-menu — interactive management                   │
└──────────────────────────────────────────────────────────┘
```

---

## OpenWrt (Router/Gateway)

### Install

```bash
ash <(curl -sL https://raw.githubusercontent.com/rickicode/free-proxy-gateway/refs/heads/main/openwrt/installer.sh)
```

Installer otomatis install: Nikki, wgcf, wireguard-tools, python3, config, WARP, cron, `prox-menu`.

**Force reinstall deps:**
```bash
ash <(curl -sL ...) --force
```

### Menu

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

### Proxy Endpoints

| Port | Group | Default |
|------|-------|---------|
| 1010 | PROXY-1010 | WAN2 |
| 1011 | PROXY-1011 | PROXY-FREE |
| 1012 | PROXY-1012 | PROXY-ASIA |
| 1013 | PROXY-1013 | WARP-LB |
| 7890 | mixed | GLOBAL |

Detail: [openwrt/README.md](openwrt/README.md)

---

## Ubuntu/Debian (Scanner/Server)

### Install

```bash
# Clone repo
git clone https://github.com/rickicode/free-proxy-gateway.git
cd free-proxy-gateway

# Install dependencies
pip install -r requirements.txt  # atau: python3 setup.py install

# Download sing-box binary
./get-singbox.sh
```

### Jalankan Scan

```bash
# Scan penuh
python3 freeproxy.py scan --tcp-workers 128 --live-workers 16 --output output/live-proxies.json

# Scan per-shard (untuk parallel)
python3 freeproxy.py scan --shard-index 0 --shard-count 4 --tcp-workers 128 --live-workers 16 --output output/shard-0.json

# Merge hasil shard
python3 scripts/merge_scan_results.py --input-dir merged-input --output output/live-proxies.json

# Convert ke mihomo format
python3 scripts/convert_to_mihomo.py output/live-proxies.json output/live-proxies.mihomo.yml
```

### Output Files

| File | Description |
|------|-------------|
| `output/live-proxies.json` | Raw scan results |
| `output/live-proxies.mihomo.yml` | Mihomo proxy-provider format |
| `output/live-proxies.singbox.json` | Sing-box config format |
| `output/latest-summary.json` | Scan summary |

### GitHub Actions

Workflow `.github/workflows/free-proxy-gateway.yml`:
- Trigger: schedule tiap 12 jam + manual
- 4 shard paralel → merge → commit
- Output auto-update ke repo

---

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

---

## File Structure

```
free-proxy-gateway/
├── freeproxy.py                — Proxy scanner
├── scripts/
│   ├── convert_to_mihomo.py    — Convert to mihomo format
│   ├── merge_scan_results.py   — Merge shard results
│   └── proxy-collector.py      — Proxy source collector
├── lib/
│   └── common.py               — Shared utilities
├── openwrt/
│   ├── installer.sh            — OpenWrt auto-installer
│   ├── prox-menu.sh            — Interactive menu command
│   ├── base.yml                — Mihomo mixin config
│   ├── warp-setup.sh           — WARP account generator
│   └── rules/                  — Rule provider files
├── output/                     — Scan results (auto-generated)
├── .github/workflows/          — CI/CD
├── get-singbox.sh              — Download sing-box binary
└── README.md                   — This file
```
