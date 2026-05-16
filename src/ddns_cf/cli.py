from __future__ import annotations

import logging
from argparse import ArgumentParser
from pathlib import Path

from ddns_cf.config import ConfigError, load_config
from ddns_cf.service import DdnsService


def main() -> int:
    parser = ArgumentParser(description="Minimal Cloudflare DDNS service")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("/etc/ddns-cf/config.toml"),
        help="Path to TOML config file",
    )
    parser.add_argument("--once", action="store_true", help="Run one check then exit")
    parser.add_argument("--debug", action="store_true", help="Enable debug logs")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        config = load_config(args.config)
    except (OSError, ConfigError) as error:
        logging.getLogger(__name__).error("failed to load config: %s", error)
        return 2

    service = DdnsService(config)
    if args.once:
        results = service.run_once()
        return 1 if any(result.status == "failed" for result in results) else 0

    service.run_forever()
    return 0
