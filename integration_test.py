"""Compatibility entrypoint for the explicit, budget-monitored live runner.

Run `python integration_test.py --help` for model and preflight arguments.
Import is side-effect free. Inference requires --live; --preflight-only is free.
"""

import asyncio

from e2e_live import main


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
