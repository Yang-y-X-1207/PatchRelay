import argparse

import uvicorn


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="patchrelay")
    subcommands = parser.add_subparsers(dest="command")

    serve = subcommands.add_parser("serve", help="Run the PatchRelay server.")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", default=8787, type=int)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "serve":
        uvicorn.run("patchrelay.app:app", host=args.host, port=args.port)
        return

    parser.print_help()
