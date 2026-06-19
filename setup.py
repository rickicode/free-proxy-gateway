"""Setup for singbox-vpn CLI tool."""

from setuptools import setup, find_packages

setup(
    name="singbox-vpn",
    version="1.0.0",
    description="Auto WARP + Free Proxy + NAT manager for sing-box",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=[
        "pyyaml",
    ],
    entry_points={
        "console_scripts": [
            "singbox-vpn=singbox_vpn.cli:main",
        ],
    },
)
