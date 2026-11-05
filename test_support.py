"""Hermetic test imports: never inherit operator credentials/configuration."""

import os


def isolate_environment():
    for name in list(os.environ):
        if name.startswith("OPENROUTER_") or name == "WEBUI_SECRET_KEY":
            os.environ.pop(name)
