import argparse
import os

import uvicorn

from patchrelay.config import ConfigError, load_settings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="patchrelay")
    subcommands = parser.add_subparsers(dest="command")

    serve = subcommands.add_parser("serve", help="Run the PatchRelay server.")
    serve.add_argument("--config", default="patchrelay.yaml")
    serve.add_argument("--host")
    serve.add_argument("--port", type=int)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "serve":
        try:
            settings = load_settings(args.config)
        except ConfigError as exc:
            parser.error(str(exc))
        host = args.host or settings.server.host
        port = args.port or settings.server.port
        os.environ["PATCHRELAY_CONFIG"] = args.config
        uvicorn.run("patchrelay.app:create_app", host=host, port=port, factory=True)
        return

    parser.print_help()
