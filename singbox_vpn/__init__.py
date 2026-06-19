"""singbox-vpn: Auto WARP + Free Proxy + NAT manager for sing-box.

Replicates exact setup from gateway server:
- 2x WARP WireGuard endpoints inside sing-box
- Auto fetch live proxies from free-proxy-singbox repo
- TProxy NAT per-interface + dnsmasq DHCP
- Status dashboard + Doctor diagnostics
"""

__version__ = "1.0.0"
