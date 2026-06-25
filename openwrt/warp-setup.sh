#!/bin/sh
# Generate 3 WARP accounts on-device via wgcf
# Keys stored locally only — never committed to repo
# Output: /etc/nikki/profiles/warp.yml (proxies only, proxy-provider format)
set -e

WGCF="/usr/local/bin/wgcf"
WARP_FILE="/etc/nikki/profiles/warp.yml"
CRED_FILE="/etc/nikki/warp-creds.json"
COUNT=3
PUBLIC_KEY="bmXOC+F1FxEMF9dyiK2H5/1SUtzH0JuVo51h2wPfgyo="
ENDPOINT="engage.cloudflareclient.com"

echo "=== WARP Account Generator ==="

# Install wgcf if missing
if ! command -v wgcf >/dev/null 2>&1; then
  echo "[0] Installing wgcf..."
  arch=$(uname -m)
  case "$arch" in x86_64|amd64) a="amd64";; aarch64|arm64) a="arm64";; *) a="amd64";; esac
  wget -qO "$WGCF" "https://github.com/ViRb3/wgcf/releases/latest/download/wgcf_${a}"
  chmod +x "$WGCF"
fi

# Register accounts
mkdir -p "$(dirname "$CRED_FILE")"
registered=0

for i in $(seq 1 $COUNT); do
  label="WARP$i"
  echo -n "  $label: "
  work=$(mktemp -d)
  cd "$work"

  if ! wgcf register --accept-tos 2>/dev/null; then
    echo "rate limited"
    rm -rf "$work"; sleep 3; continue
  fi
  if ! wgcf generate 2>/dev/null; then
    echo "generate failed"
    rm -rf "$work"; continue
  fi

  privkey=$(grep "PrivateKey" "$work/wgcf-profile.conf" 2>/dev/null | cut -d= -f2 | tr -d ' ')
  addr=$(grep "Address" "$work/wgcf-profile.conf" 2>/dev/null | cut -d= -f2 | tr -d ' ')
  addr_v4=$(echo "$addr" | cut -d, -f1)
  addr_v6=$(echo "$addr" | cut -d, -f2)
  rm -rf "$work"

  [ -z "$privkey" ] || [ -z "$addr_v4" ] && echo "parse failed" && continue
  echo "$addr_v4"

  python3 -c "
import json, os, time
creds = json.load(open('$CRED_FILE')) if os.path.exists('$CRED_FILE') else {}
creds['$label'] = {'private_key':'$privkey','address_v4':'$addr_v4','address_v6':'$addr_v6','refreshed_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}
json.dump(creds, open('$CRED_FILE','w'), indent=2)
"
  registered=$((registered + 1))
  sleep 2
done

[ "$registered" -eq 0 ] && echo "Gagal semua. Coba lagi nanti." && exit 1

# Generate proxy-provider YAML (proxies only)
echo ""
python3 - "$CRED_FILE" "$WARP_FILE" "$COUNT" "$PUBLIC_KEY" "$ENDPOINT" << 'PYEOF'
import json, sys
creds_file, out_file, count, pubkey, endpoint = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4], sys.argv[5]
creds = json.load(open(creds_file))
lines = ["# WARP proxies (per-device, auto-generated)", "# Keys local only — never committed to repo", "", "proxies:"]
for i in range(1, count + 1):
    d = creds.get(f"WARP{i}", {})
    if not d.get("private_key"): continue
    lines.extend([
        f'  - name: WARP-{i}',
        f'    type: wireguard',
        f'    server: {endpoint}',
        f'    port: 2408',
        f'    private-key: {d["private_key"]}',
        f'    public-key: {pubkey}',
        f'    ip: {d.get("address_v4", "172.16.0.2")}',
    ])
    if d.get("address_v6"):
        lines.append(f'    ipv6: "{d["address_v6"]}"')
    lines.extend([f'    allowed-ips:', f'      - 0.0.0.0/0', f'    udp: true', f'    mtu: 1280', ''])
with open(out_file, 'w') as f: f.write('\n'.join(lines))
print(f"Written {out_file} ({len(lines)} lines)")
PYEOF

echo ""
echo "Done. WARP credentials: $CRED_FILE"
echo "Profile: $WARP_FILE"
