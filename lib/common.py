#!/usr/bin/env python3
"""
Shared constants and functions for free-proxy-gateway.

This module contains common code used by:
- freeproxy.py (scanner)
- scripts/merge_scan_results.py (merge script)
- gateway/proxy-collector.py (gateway collector)
"""

DEFAULT_GROUPS = ("PROXY-FREE", "PROXY-ID", "PROXY-SG", "PROXY-US")


def build_groups(records, target_countries):
    """Build proxy groups from records.
    
    Args:
        records: List of proxy records with 'tag' and 'country_code' fields
        target_countries: List of country codes to create groups for
        
    Returns:
        Dictionary mapping group names to lists of proxy tags
    """
    groups = {"PROXY-FREE": [record["tag"] for record in records]}
    for code in target_countries:
        groups[f"PROXY-{code}"] = [
            record["tag"] for record in records 
            if record["country_code"] == code
        ]
    return groups


def build_singbox_snapshot(records, groups):
    """Build sing-box configuration snapshot.
    
    Args:
        records: List of proxy records with 'outbound' field
        groups: Dictionary mapping group names to lists of proxy tags
        
    Returns:
        Complete sing-box configuration dictionary
    """
    outbounds = [
        {"type": "direct", "tag": "DIRECT"},
        {"type": "block", "tag": "BLOCK"},
    ]
    outbounds.extend(record["outbound"] for record in records)
    
    for group_name in DEFAULT_GROUPS:
        tags = groups.get(group_name, [])
        if not tags:
            continue
        outbounds.append(
            {
                "type": "loadbalance",
                "tag": group_name,
                "outbounds": tags,
                "url": "http://cp.cloudflare.com/generate_204",
                "interval": "5m",
                "strategy": "sticky-sessions",
                "ttl": "2m",
            }
        )
    
    selectable = ["DIRECT"] + [
        group for group in DEFAULT_GROUPS if groups.get(group)
    ]
    outbounds.append(
        {
            "type": "selector",
            "tag": "GLOBAL",
            "outbounds": selectable,
            "default": "DIRECT",
        }
    )
    
    return {
        "experimental": {
            "clash_api": {
                "external_controller": "127.0.0.1:9090",
                "secret": "",
            }
        },
        "inbounds": [
            {
                "type": "mixed",
                "tag": "mixed-in",
                "listen": "127.0.0.1",
                "listen_port": 7890,
            }
        ],
        "outbounds": outbounds,
        "route": {"auto_detect_interface": True, "final": "GLOBAL"},
    }
