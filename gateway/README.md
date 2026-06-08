# Gateway VPS — sing-box Internet Gateway

> **Host:** `192.168.90.78` (root)  
> **Peran:** Internet gateway untuk LAN `192.168.92.0/24`  
> **Arsitektur:** VPS → sing-box (TProxy) → outbound (WARP / proxy publik)

---

## Arsitektur

```
LAN (192.168.92.0/24)
  │
  ├── ens19 (192.168.92.1)
  │     └── TProxy :7893 (tcp + udp)
  │           └── sing-box routing
  │                 ├── DIRECT  → eth0 (ISP langsung)
  │                 ├── WARP    → WireGuard (Cloudflare)
  │                 │              ├── WARP1 (singtun0)
  │                 │              └── WARP2 (singtun1)
  │                 └── PROXY-FREE  → proxy publik dari GitHub scan
  │                                    ├── free-US-1, free-SG-1, ...
  │                                    ├── PROXY-US (urltest)
  │                                    ├── PROXY-SG (urltest)
  │                                    └── PROXY-ID (urltest)
  │
  └── Mixed proxy :7890 (HTTP/SOCKS5 untuk admin)
```

## Alur Data Proxy

```
┌──────────────────────────────────────────────────────────────────┐
│ GitHub Actions (tiap 12 jam)                                     │
│                                                                  │
│  freeproxy.py scan                                               │
│    → fetch 7 sumber publik (trojan/vless/vmess/ss)              │
│    → parse → dedupe → shard → TCP test → live test → GeoIP      │
│    → output: output/live-proxies.json (~400-700 proxy live)      │
│                                                                  │
│  Raw URL: github.com/rickicode/free-proxy-singbox/...            │
└────────────────────────────────┬─────────────────────────────────┘
                                 │ pull tiap 5 jam
                                 ▼
┌──────────────────────────────────────────────────────────────────┐
│ VPS Gateway — proxy-collector.py (cron 0 */5 * * *)             │
│                                                                  │
│  1. Fetch live-proxies.json dari GitHub raw                      │
│  2. Clash API → keep existing free-* proxy dgn delay <500ms      │
│  3. Ambil fresh proxy dari GitHub (sudah live-tested, skip test) │
│  4. Tag: free-US-1, free-SG-2, free-NL-3, ...                   │
│  5. Build PROXY-FREE + per-country urltest groups                │
│  6. Update selector → restart sing-box                           │
└──────────────────────────────────────────────────────────────────┘
```

## Struktur Folder

```
/opt/
├── gw.py                    ← Main CLI (install, status, rule, mode)
├── proxy-collector.py       ← Pull proxy dari GitHub → update config
├── proxy-rules.json         ← Managed rules (dari gw rule add)
├── STATE.md                 ← State dokumentasi
├── rules/
│   ├── ip-check.json        ← Source rule ip-check
│   └── compiled/
│       └── ip-check.srs     ← Compiled binary rule
└── warp2/
    └── wgcf-account.toml    ← WARP2 credential (jika ada)
```

## CLI: `gw.py`

| Perintah | Fungsi |
|----------|--------|
| `gw` | Menu interaktif |
| `gw status` | Status sing-box + external IP + NAT |
| `gw start\|stop\|restart` | Service control |
| `gw enable\|disable` | Enable/disable on boot |
| `gw logs` | journalctl follow live |
| `gw rule list\|add <host> <ob>\|remove <host>` | Atur routing manual |
| `gw mode <DIRECT\|WARP\|WARP1\|WARP2>` | Ganti default GLOBAL |
| `gw update-proxies` | Jalankan proxy-collector manual |
| `gw compile` | Recompile local rule sets |
| `gw install` | Instal ulang dari nol (⚠️ reset) |

## Outbounds & Groups

| Outbound | Type | Sumber |
|----------|------|--------|
| `DIRECT` | direct | Koneksi ISP langsung |
| `BLOCK` | block | Drop traffic |
| `WARP1` | direct (bind: singtun0) | Cloudflare WARP akun 1 |
| `WARP2` | direct (bind: singtun1) | Cloudflare WARP akun 2 |
| `WARP` | urltest | Auto-pilih WARP1/WARP2 tercepat |
| `free-{CC}-{N}` | trojan/vless/vmess/ss | Dari GitHub scan |
| `PROXY-FREE` | urltest | Semua free-* proxy |
| `PROXY-{CC}` | urltest | Per-country (US, SG, ID, JP, KR...) |

## Selectors (pilih manual via YACD)

| Selector | Default | Pilihan |
|----------|---------|---------|
| `GLOBAL` | DIRECT | DIRECT, WARP, WARP1, WARP2, PROXY-*, PROXY-FREE |
| `GOOGLE` | DIRECT | WARP, WARP1, WARP2, DIRECT, PROXY-* |
| `OPENAI` | WARP | WARP, WARP1, WARP2, DIRECT, PROXY-* |
| `IPCHECK` | WARP | WARP, WARP1, WARP2, DIRECT, PROXY-* |

## Route Rules (urutan)

```
1. sniff → detect protocol
2. dns → hijack-dns (redirect ke sing-box DNS)
3. ip_is_private → DIRECT
4. managed rules → outbound sesuai (dari gw rule add)
5. openai + anthropic → OPENAI selector
6. google + play + youtube → GOOGLE selector
7. speedtest + ip-check → IPCHECK selector
8. final → GLOBAL selector
```

## WARP Credentials

| Akun | Private Key | Interface |
|------|-------------|-----------|
| WARP1 | `qEqVXpiY9Te8mbmw02wVl7wa/gg0qqc2UoUbjuKC6VE=` | singtun0 |
| WARP2 | `+KauKf1ZD8XsgClXa1e4I0+136kupoPKc/2+jZUZQmg=` | singtun1 |

Public key (sama): `bmXOC+F1FxEMF9dyiK2H5/1SUtzH0JuVo51h2wPfgyo=`

## Rule Sets

| Tag | Sumber | Isi |
|-----|--------|-----|
| `community-speedtest` | MetaCubeX remote | speedtest.net, ookla |
| `community-openai` | MetaCubeX remote | openai.com, chatgpt.com |
| `community-anthropic` | MetaCubeX remote | claude.ai, anthropic.com |
| `community-google` | MetaCubeX remote | google.com |
| `community-google-play` | MetaCubeX remote | play.google.com |
| `community-youtube` | MetaCubeX remote | youtube.com |
| `local-ip-check` | Local compiled `rules/compiled/ip-check.srs` | ifconfig.co, ipinfo.io, dll |

## Cron

```
0 */5 * * *  /usr/bin/python3 /opt/proxy-collector.py
             >> /var/log/proxy-collector.log 2>&1
```

## YACD UI

```
http://192.168.90.78:9090/ui/
```

## Repo counterpart

Semua file di folder ini adalah **shadow copy** dari file yang aktif di VPS `192.168.90.78`.

| File Repo | File VPS |
|-----------|----------|
| `gateway/gw.py` | `/opt/gw.py` — main CLI |
| `gateway/proxy-collector.py` | `/opt/proxy-collector.py` — pull proxy dari GitHub |
| `gateway/config.json` | `/etc/sing-box/config.json` (base template) |
| `gateway/sing-box.service` | `/etc/systemd/system/sing-box.service` |
| `gateway/tproxy-setup.sh` | `/usr/local/bin/tproxy-setup` — TProxy iptables |
| `gateway/99-gateway.conf` | `/etc/sysctl.d/99-gateway.conf` — IP forwarding |
| `gateway/proxy-rules.json` | `/opt/proxy-rules.json` — managed rules storage |
| `gateway/STATE.md` | `/opt/STATE.md` |
| `gateway/rules/ip-check.json` | `/opt/rules/ip-check.json` |
| `gateway/rules/compiled/ip-check.srs` | `/opt/rules/compiled/ip-check.srs` (binary) |

## Setup LAN Client

```
IP      : 192.168.92.x/24
Gateway : 192.168.92.1
DNS     : 1.1.1.1
```

## Catatan Penting

- `gw install` akan **reset semua** — dynamic outbounds (PROXY-*) ikut hilang. Hanya jalankan untuk server fresh.
- `gw rule add/remove` **aman** — tidak reset dynamic outbounds.
- Proxy dari GitHub sudah **TCP + live + GeoIP** terverifikasi. `proxy-collector.py` hanya keep-alive via clash API.
- Kalau butuh proxy segar, jalanin `gw update-proxies` atau tunggu cron 5 jam.
