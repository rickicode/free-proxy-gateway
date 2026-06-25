# Cloudflare WARP WireGuard Setup

Setup Cloudflare WARP sebagai VPN backup di OpenWrt via Nikki/Mihomo.

## Step 1: Register WARP account

Dari Proxmox atau mesin Linux lain:

```bash
# Install wireguard-tools
apt-get install -y wireguard-tools

# Generate key pair
PRIVATE_KEY=$(wg genkey)
PUBLIC_KEY=$(echo $PRIVATE_KEY | wg pubkey)

# Register ke Cloudflare WARP
RESPONSE=$(curl -sL -X POST 'https://api.cloudflareclient.com/v0a2161/reg' \
  -H 'Content-Type: application/json' \
  -H 'User-Agent: okhttp/3.12.1' \
  -d "{
    \"key\": \"$PUBLIC_KEY\",
    \"install_id\": \"$(cat /proc/sys/kernel/random/uuid)\",
    \"fcm_token\": \"$(cat /proc/sys/kernel/random/uuid)\",
    \"tos\": \"$(date -u +%Y-%m-%dT%H:%M:%S.000Z)\",
    \"model\": \"Linux\",
    \"serial_number\": \"$(cat /proc/sys/kernel/random/uuid)\"
  }")

# Extract config
echo "PrivateKey: $PRIVATE_KEY"
echo "PublicKey: bmXOC+F1FxEMF9dyiK2H5/1SUtzH0JuVo51h2wPfgyo="
echo "IPv4: $(echo $RESPONSE | python3 -c 'import json,sys; print(json.load(sys.stdin)["config"]["interface"]["addresses"]["v4"])')"
echo "IPv6: $(echo $RESPONSE | python3 -c 'import json,sys; print(json.load(sys.stdin)["config"]["interface"]["addresses"]["v6"])')"
```

## Step 2: Tambah WARP ke Nikki mixin

Edit `/etc/nikki/mixin.yaml`:

```yaml
nikki-proxies:
  - name: WARP-1
    type: wireguard
    server: engage.cloudflareclient.com
    port: 2408
    private-key: <PRIVATE_KEY_DARI_STEP_1>
    public-key: bmXOC+F1FxEMF9dyiK2H5/1SUtzH0JuVo51h2wPfgyo=
    ip: 172.16.0.2
    ipv6: "<IPv6_DARI_STEP_1>"
    allowed-ips:
      - 0.0.0.0/0
    udp: true
    mtu: 1280

nikki-proxy-groups:
  - name: PROXY-WARP
    type: select
    proxies:
      - WARP-1
      - DIRECT

  - name: WARP-LB
    type: load-balance
    proxies:
      - WARP-1
    url: http://www.gstatic.com/generate_204
    interval: 300
```

## Step 3: Tambah WARP ke GLOBAL

Di Nikki dashboard (http://IP:9090/ui):
1. Buka **proxy-groups**
2. Edit **GLOBAL**
3. Tambah `PROXY-WARP` ke list

## Step 4: Restart Nikki

```bash
/etc/init.d/nikki restart
```

## Step 5: Test

```bash
# Switch GLOBAL ke PROXY-WARP
curl -s -H "Authorization: Bearer <secret>" \
  -X PUT http://127.0.0.1:9090/proxies/GLOBAL \
  -d '{"name":"PROXY-WARP"}'

# Test IP
curl -s --proxy http://127.0.0.1:7890 https://ifconfig.me

# Harusnya IP Cloudflare, bukan ISP
```

## Multiple WARP Accounts (Load Balance)

Bikin 3 akun WARP berbeda, tambah ke mixin:

```yaml
nikki-proxies:
  - name: WARP-1
    type: wireguard
    private-key: <KEY_1>
    ...

  - name: WARP-2
    type: wireguard
    private-key: <KEY_2>
    ...

  - name: WARP-3
    type: wireguard
    private-key: <KEY_3>
    ...

nikki-proxy-groups:
  - name: PROXY-WARP
    type: select
    proxies:
      - WARP-LB
      - WARP-1
      - WARP-2
      - WARP-3
      - DIRECT

  - name: WARP-LB
    type: load-balance
    proxies:
      - WARP-1
      - WARP-2
      - WARP-3
    url: http://www.gstatic.com/generate_204
    interval: 300
```

## Tailscale Integration (opsional)

```bash
# Install tailscale
apk add tailscale

# Login
tailscale up --advertise-routes=192.168.x.0/24 --accept-routes --accept-dns=false --ssh

# Firewall zone
uci add firewall zone
uci set firewall.@zone[-1].name=tailscale
uci set firewall.@zone[-1].network=tailscale
uci set firewall.@zone[-1].input=ACCEPT
uci set firewall.@zone[-1].output=ACCEPT
uci set firewall.@zone[-1].forward=ACCEPT
uci commit firewall

# Enable auto-start
/etc/init.d/tailscale enable
```

## Troubleshooting

### WARP gak konek
```bash
# Cek WireGuard handshake
wg show

# Cek route
ip route | grep warp

# Test langsung
curl -s --interface warp https://ifconfig.me
```

### WARP lambat
Ganti endpoint:
```
engage.cloudflareclient.com:2408
162.159.192.1:2408
162.159.193.1:2408
```
