# singbox-vpn Skill

Manage sing-box VPN gateway with auto WARP, free proxies, NAT, and DHCP.

## When to Load

- User asks about sing-box, VPN gateway, proxy management, NAT setup
- User wants to add/remove routing rules
- User wants to check status or diagnose issues
- User mentions "singbox-vpn", "proxy gateway", "WARP setup"

## Quick Reference

```bash
# Full setup on fresh OS
singbox-vpn install          # Install dependencies (sing-box, AdGuard, wg)
singbox-vpn setup            # Full setup (install + WARP + config + NAT)

# Management
singbox-vpn status           # Dashboard overview
singbox-vpn doctor           # Health check diagnostics

# WARP
singbox-vpn warp setup       # Register 2 WARP WireGuard endpoints
singbox-vpn warp status      # Check WARP status
singbox-vpn warp remove      # Remove WARP endpoints

# Proxy pool
singbox-vpn proxy fetch      # Fetch live proxies from GitHub
singbox-vpn proxy status     # Show proxy pool status

# NAT (per-interface)
singbox-vpn nat add eth2     # Add NAT for eth2 (routing + DHCP)
singbox-vpn nat add eth3     # Add NAT for eth3
singbox-vpn nat remove eth2  # Remove NAT for eth2
singbox-vpn nat list         # List configured interfaces
singbox-vpn nat status       # Show NAT status

# Route rules
singbox-vpn rule add --domain .netflix.com --outbound WARP
singbox-vpn rule add --keyword gambling --outbound BLOCK
singbox-vpn rule add --ip 10.0.0.0/8 --outbound DIRECT
singbox-vpn rule add --port 443 --network tcp --outbound WARP
singbox-vpn rule add --domain .openai.com --outbound OPENAI
singbox-vpn rule add --inbound mixed-1010 --outbound WARP
singbox-vpn rule remove 3    # Remove rule by index
singbox-vpn rule list        # List custom rules
singbox-vpn rule apply       # Re-deploy config with rules
```

## Architecture

```
Client (192.168.92.x)
    │
    ├─ DHCP → AdGuard Home (port 67)
    │         Gateway: 192.168.92.1
    │         DNS: 8.8.8.8 (hijacked by sing-box)
    │
    └─ Traffic → Policy Routing (pref 8999)
                    │
                    ├─ Private IPs → DIRECT
                    ├─ OpenAI/Anthropic → OPENAI outbound
                    ├─ Google/YouTube → GOOGLE outbound
                    └─ Everything else → GLOBAL (WARP default)
                            │
                            ├─ WARP1 (singtun0) ─┐
                            └─ WARP2 (singtun1) ─┘→ Cloudflare WARP
```

## Key Files

| File | Purpose |
|------|---------|
| `/etc/sing-box/config.json` | sing-box main config |
| `/etc/singbox-vpn/config.yaml` | singbox-vpn config |
| `/etc/singbox-vpn/rules.json` | Custom route rules |
| `/opt/AdGuardHome/AdGuardHome.yaml` | AdGuard Home config |
| `/usr/local/bin/fix-nat-<iface>.sh` | Persistent NAT script |
| `/opt/rules/ip-check.json` | IP check rule set source |
| `/opt/rules/compiled/ip-check.srs` | Compiled rule set |

## Outbound Types

| Tag | Description |
|-----|-------------|
| `DIRECT` | Direct connection (no proxy) |
| `WARP` | Cloudflare WARP (loadbalance of WARP1+WARP2) |
| `WARP1` / `WARP2` | Individual WARP endpoints |
| `BLOCK` | Block connection |
| `PROXY-FREE` | Free proxy pool (loadbalance) |
| `PROXY-ID`, `PROXY-SG`, etc. | Per-country proxy selectors |
| `OPENAI` | For OpenAI/Anthropic domains |
| `GOOGLE` | For Google/YouTube domains |
| `IPCHECK` | For IP check sites |

## NAT Approach

Uses **policy routing + MASQUERADE** (not TProxy):
- `ip rule add from <subnet> lookup 2022 pref 8999`
- `iptables -t nat -A POSTROUTING -s <subnet> -o singtun0 -j MASQUERADE`
- Handles all protocols: TCP, UDP, ICMP
- Survives reboot via systemd service

## Adding Rules (for AI)

When user says "add rule for X":

1. Parse the request to determine:
   - Match type: `--domain`, `--keyword`, `--ip`, `--port`, `--protocol`, `--network`, `--inbound`
   - Target outbound: `WARP`, `BLOCK`, `DIRECT`, `PROXY-XX`, etc.

2. Run: `singbox-vpn rule add --<match_type> <value> --outbound <target>`

3. Run: `singbox-vpn rule apply` to deploy

## Config Defaults

Config file: `/etc/singbox-vpn/config.yaml`

Key settings:
```yaml
warp:
  interfaces: [singtun0, singtun1]
proxy:
  github_raw: https://raw.githubusercontent.com/rickicode/free-proxy-gateway/main/output/live-proxies.json
  max_free: 40
  target_countries: [US, SG, ID, JP, KR, HK, DE, FR, GB, CA, AU, IN, NL, BR]
nat:
  interfaces: []           # Add via: singbox-vpn nat add <iface>
  dhcp_enabled: true
  dhcp_range_start: 100
  dhcp_range_end: 200
  dhcp_lease: 12h
singbox:
  mixed_port: 7890
  clash_api_port: 9090
  dns_server: 1.1.1.1
```

## Troubleshooting

```bash
singbox-vpn doctor          # Run all diagnostics
singbox-vpn status          # Check component status

# Common issues:
# - DHCP not working → Check AdGuard Home: systemctl status AdGuardHome
# - No internet → Check WARP: singbox-vpn warp status
# - Rules not applied → Run: singbox-vpn rule apply
# - After reboot timeout → Check: ip rule list | grep 192.168
```
