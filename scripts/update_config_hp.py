import sys
import json
from collections import defaultdict


AMERICA_CC = ["US", "CA", "MX", "BR", "AR", "CL", "CO", "PE", "VE", "EC", "UY", "PY", "BO"]
ASIA_CC = ["SG", "ID", "JP", "KR", "HK", "TW", "MY", "TH", "VN", "IN", "CN",
           "KZ", "UZ", "AE", "SA", "QA", "KW", "BH", "OM", "IL", "JO",
           "PH", "KH", "LA", "MM", "BD", "LK", "NP", "MN"]
EUROPE_CC = ["DE", "NL", "FR", "GB", "PL", "IT", "LT", "SE", "LU", "LV", "FI",
             "NO", "RO", "AT", "CH", "BE", "EE", "ES", "IE", "RU", "AL", "BG",
             "CZ", "DK", "GR", "TR", "UA", "HU", "PT", "SK", "SI", "HR", "RS",
             "BA", "MD", "IS"]


def pick_region(proxies, allowed, total, per_cc, prefix):
    """Fair round-robin: bucket per country (live order preserved),
    tiap ronde ambil 1 dari tiap negara. max per_cc, total cap.
    Return (outbounds, cc_list) — cc_list untuk diagnostik."""
    allowed_set = set(allowed)
    buckets = defaultdict(list)
    for p in proxies:
        cc = p.get("country_code")
        if cc not in allowed_set:
            continue
        ob = p.get("outbound")
        if not ob or not isinstance(ob, dict):
            continue
        buckets[cc].append(p)
    out = []
    out_cc = []
    seen = set()
    taken = defaultdict(int)   # per-cc count
    cursor = defaultdict(int)  # posisi scan per bucket
    while len(out) < total:
        progress = False
        for cc in sorted(buckets.keys()):
            if len(out) >= total:
                break
            if taken[cc] >= per_cc:
                continue
            bucket = buckets[cc]
            # cari item berikutnya yg tag-nya belum dipakai
            while cursor[cc] < len(bucket):
                p = bucket[cursor[cc]]
                cursor[cc] += 1
                ob = p.get("outbound")
                base = (ob.get("tag") if isinstance(ob, dict) else None) or p.get("tag") or f"{cc}-{cursor[cc]}"
                tag = f"{prefix}-{base}"
                if tag in seen:
                    continue
                ob = dict(ob)
                ob["tag"] = tag
                # sing-box 1.12+: outbound wajib domain_resolver (userspace TUN tanpa /etc/resolv.conf)
                ob.setdefault("domain_resolver", "dns-direct")
                seen.add(tag)
                out.append(ob)
                out_cc.append(cc)
                taken[cc] += 1
                progress = True
                break  # 1 per negara per ronde
        if not progress:
            break
    return out, out_cc


def main():
    if len(sys.argv) < 3:
        sys.exit(1)

    cfg_path = sys.argv[1]
    proxies_path = sys.argv[2]

    try:
        with open(cfg_path, 'r') as f:
            cfg = json.load(f)

        with open(proxies_path, 'r') as f:
            prox_data = json.load(f)
    except Exception:
        sys.exit(1)

    proxies = prox_data.get("proxies", [])
    if not proxies:
        print("update_config_hp: live-proxies.json kosong (no proxies key)", file=sys.stderr)
        sys.exit(2)

    # FREE: global diverse 30 (max 2 per country)
    free_outbounds = []
    free_per_cc = {}
    for i, p in enumerate(proxies):
        if len(free_outbounds) >= 30:
            break
        ob = p.get("outbound")
        if not ob or not isinstance(ob, dict):
            continue
        cc = p.get("country_code") or "XX"
        if free_per_cc.get(cc, 0) >= 2:
            continue
        ob = dict(ob)
        tag = f"free-{cc}-{i}"
        if any(o.get("tag") == tag for o in free_outbounds):
            continue
        ob["tag"] = tag
        ob.setdefault("domain_resolver", "dns-direct")
        free_outbounds.append(ob)
        free_per_cc[cc] = free_per_cc.get(cc, 0) + 1

    # Region groups: 30 each. per-cc longgar (US dominan 2028/3601).
    america_outbounds, _ = pick_region(proxies, AMERICA_CC, 30, 15, "am")
    asia_outbounds, _ = pick_region(proxies, ASIA_CC, 30, 8, "asia")
    europe_outbounds, _ = pick_region(proxies, EUROPE_CC, 30, 8, "eu")

    if not free_outbounds:
        print("update_config_hp: tidak ada free_outbounds setelah filter (0/30)", file=sys.stderr)
        sys.exit(2)

    cfg.setdefault("outbounds", [])
    cfg["outbounds"].extend(free_outbounds)
    if america_outbounds:
        cfg["outbounds"].extend(america_outbounds)
    if asia_outbounds:
        cfg["outbounds"].extend(asia_outbounds)
    if europe_outbounds:
        cfg["outbounds"].extend(europe_outbounds)

    free_tags = [o["tag"] for o in free_outbounds]
    america_tags = [o["tag"] for o in america_outbounds]
    asia_tags = [o["tag"] for o in asia_outbounds]
    europe_tags = [o["tag"] for o in europe_outbounds]

    # sing-box pakai urltest untuk auto-select berdasarkan latency.
    cfg["outbounds"].append({
        "type": "urltest",
        "tag": "PROXY-FREE",
        "outbounds": free_tags,
        "url": "https://www.gstatic.com/generate_204",
        "interval": "10m",
        "tolerance": 50
    })

    if america_tags:
        cfg["outbounds"].append({
            "type": "urltest",
            "tag": "PROXY-AMERICA",
            "outbounds": america_tags,
            "url": "https://www.gstatic.com/generate_204",
            "interval": "10m",
            "tolerance": 50
        })
    else:
        cfg["outbounds"].append({
            "type": "selector",
            "tag": "PROXY-AMERICA",
            "outbounds": ["PROXY-FREE"]
        })

    if asia_tags:
        cfg["outbounds"].append({
            "type": "urltest",
            "tag": "PROXY-ASIA",
            "outbounds": asia_tags,
            "url": "https://www.gstatic.com/generate_204",
            "interval": "10m",
            "tolerance": 50
        })
    else:
        cfg["outbounds"].append({
            "type": "selector",
            "tag": "PROXY-ASIA",
            "outbounds": ["PROXY-FREE"]
        })

    if europe_tags:
        cfg["outbounds"].append({
            "type": "urltest",
            "tag": "PROXY-EUROPE",
            "outbounds": europe_tags,
            "url": "https://www.gstatic.com/generate_204",
            "interval": "10m",
            "tolerance": 50
        })
    else:
        cfg["outbounds"].append({
            "type": "selector",
            "tag": "PROXY-EUROPE",
            "outbounds": ["PROXY-FREE"]
        })

    # GLOBAL: selector gabungan semua region untuk tampilan Yacd
    all_group_tags = [t for t in ["PROXY-FREE", "PROXY-AMERICA", "PROXY-ASIA", "PROXY-EUROPE"] if any(o.get("tag") == t for o in cfg["outbounds"])]
    if all_group_tags and not any(o.get("tag") == "GLOBAL" for o in cfg["outbounds"]):
        cfg["outbounds"].append({
            "type": "selector",
            "tag": "GLOBAL",
            "outbounds": all_group_tags
        })

    with open(cfg_path, 'w') as f:
        json.dump(cfg, f, indent=2)


if __name__ == '__main__':
    main()
