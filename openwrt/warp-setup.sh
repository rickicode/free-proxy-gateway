#!/bin/sh
# Generate 3 WARP accounts on-device via wgcf
# Keys are stored locally only — never committed to repo
# Usage: ash /etc/nikki/warp-setup.sh
set -e

WGCF="/usr/local/bin/wgcf"
WARP_FILE="/etc/nikki/profiles/warp.yml"
CRED_FILE="/etc/nikki/warp-creds.json"
COUNT=3

echo "=== WARP Account Generator ==="
echo ""

# Check wgcf
if ! command -v wgcf >/dev/null 2>&1; then
  echo "[0/4] Installing wgcf..."
  arch=$(uname -m)
  case "$arch" in
    x86_64|amd64) a="amd64" ;;
    aarch64|arm64) a="arm64" ;;
    armv7l|armhf) a="armv7" ;;
    *) a="amd64" ;;
  esac
  wget -qO "$WGCF" "https://github.com/ViRb3/wgcf/releases/latest/download/wgcf_${a}"
  chmod +x "$WGCF"
  echo "  OK: wgcf ($a)"
fi

echo "[1/4] Checking wireguard-tools..."
if ! command -v wg >/dev/null 2>&1; then
  apk add wireguard-tools 2>/dev/null || apt-get install -y -qq wireguard-tools 2>/dev/null || true
fi

echo "[2/4] Registering $COUNT WARP accounts..."
mkdir -p "$(dirname "$CRED_FILE")"

registered=0
for i in $(seq 1 $COUNT); do
  label="WARP$i"
  work=$(mktemp -d /tmp/warp-XXXXX)

  cd "$work"
  if ! wgcf generate 2>/dev/null; then
    echo "  ✗ $label: generate failed"
    rm -rf "$work"
    continue
  fi

  if ! wgcf register --accept-tos 2>/dev/null; then
    echo "  ✗ $label: register failed (rate limited?)"
    rm -rf "$work"
    sleep 3
    continue
  fi

  wgcf generate 2>/dev/null

  privkey=$(grep "PrivateKey" "$work/wgcf-profile.conf" 2>/dev/null | cut -d= -f2 | tr -d ' ')
  addr=$(grep "Address" "$work/wgcf-profile.conf" 2>/dev/null | cut -d= -f2 | tr -d ' ')
  addr_v4=$(echo "$addr" | cut -d, -f1)
  addr_v6=$(echo "$addr" | cut -d, -f2)

  rm -rf "$work"

  if [ -z "$privkey" ] || [ -z "$addr_v4" ]; then
    echo "  ✗ $label: parse failed"
    continue
  fi

  echo "  ✓ $label: $addr_v4"

  python3 -c "
import json, os, time
creds = {}
if os.path.exists('$CRED_FILE'):
    creds = json.load(open('$CRED_FILE'))
creds['$label'] = {
    'private_key': '$privkey',
    'address_v4': '$addr_v4',
    'address_v6': '$addr_v6',
    'refreshed_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
}
json.dump(creds, open('$CRED_FILE', 'w'), indent=2)
"

  registered=$((registered + 1))
  sleep 2
done

if [ "$registered" -eq 0 ]; then
  echo "  ✗ Gagal register semua akun. Coba lagi nanti."
  exit 1
fi

echo ""
echo "[3/4] Generating $WARP_FILE..."

python3 - "$CRED_FILE" "$WARP_FILE" "$COUNT" << 'PYEOF'
import json, sys

creds_file, output_file, count = sys.argv[1], sys.argv[2], int(sys.argv[3])
creds = json.load(open(creds_file))

lines = [
    "# Auto-generated WARP proxies (per-device)",
    "# Keys are local only — never committed to repo",
    "",
    "proxies:",
]

for i in range(1, count + 1):
    label = f"WARP{i}"
    d = creds.get(label, {})
    if not d.get("private_key"):
        continue
    lines.extend([
        f"  - name: {label}",
        f"    type: wireguard",
        f"    server: engage.cloudflareclient.com",
        f"    port: 2408",
        f"    private-key: {d['private_key']}",
        f"    public-key: bmXOC+F1FxEMF9dyiK2H5/1SUtzH0JuVo51h2wPfgyo=",
        f"    ip: {d.get('address_v4', '172.16.0.2')}",
    ])
    if d.get("address_v6"):
        lines.append(f'    ipv6: "{d["address_v6"]}"')
    lines.extend([
        f"    allowed-ips:",
        f"      - 0.0.0.0/0",
        f"    udp: true",
        f"    mtu: 1280",
        "",
    ])

warp_names = [f"WARP{i}" for i in range(1, count + 1) if creds.get(f"WARP{i}", {}).get("private_key")]
if not warp_names:
    print("No valid WARP credentials")
    sys.exit(1)

lines.extend([
    "proxy-groups:",
    "  - name: WARP-LB",
    "    type: load-balance",
    "    proxies:",
])
for name in warp_names:
    lines.append(f"      - {name}")
lines.extend([
    "    url: http://www.gstatic.com/generate_204",
    "    interval: 300",
    "",
    "  - name: PROXY-WARP",
    "    type: select",
    "    proxies:",
    "      - WARP-LB",
])
for name in warp_names:
    lines.append(f"      - {name}")
lines.append("      - DIRECT")
lines.append("")

with open(output_file, "w") as f:
    f.write("\n".join(lines))
print(f"Written {output_file} ({len(lines)} lines)")
PYEOF

echo ""
echo "[4/4] Verifikasi..."
if [ -f "$WARP_FILE" ]; then
  count=$(grep -c "private-key:" "$WARP_FILE" 2>/dev/null || echo 0)
  echo "  ✓ $WARP_FILE ($count WARP accounts)"
else
  echo "  ✗ $WARP_FILE tidak ditemukan"
  exit 1
fi

echo ""
echo "=== Selesai ==="
echo "Cred: $CRED_FILE"
echo "Profile: $WARP_FILE"
echo "Refresh: ash /etc/nikki/warp-setup.sh"
