from __future__ import annotations

# ============================================================================
# EXCEPTION TRACKING SETUP (to disable, comment out the entire section below)
# ============================================================================

# --- START: EXCEPTION TRACKING - GLOBAL HOOK ---
import sys
import logging
import traceback
import os
import threading

_PEARL_EXC_LOG = os.path.join(os.getenv("TMPDIR", "/tmp"), "pearl_exceptions.log")

# Configure root logger to also log to file for exception tracking
_exc_logger = logging.getLogger("pearl.exceptions")
_exc_handler = logging.FileHandler(_PEARL_EXC_LOG, mode="a", encoding="utf-8")
_exc_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
_exc_logger.addHandler(_exc_handler)
_exc_logger.setLevel(logging.DEBUG)

def _global_excepthook(exc_type, exc_value, exc_tb):
    """Log uncaught exceptions at the top level."""
    _exc_logger.error("UNCAUGHT EXCEPTION", exc_info=(exc_type, exc_value, exc_tb))
    # Also write raw traceback to log file for inspection
    with open(_PEARL_EXC_LOG, "a", encoding="utf-8") as f:
        f.write("\n" + "=" * 80 + "\n")
        f.write(f"Uncaught exception (time logged, see above)\n")
        traceback.print_exception(exc_type, exc_value, exc_tb, file=f)
        f.write("=" * 80 + "\n\n")

sys.excepthook = _global_excepthook
# --- END: EXCEPTION TRACKING - GLOBAL HOOK ---

# --- START: EXCEPTION TRACKING - THREAD HOOK ---
def _thread_excepthook(args):
    """Log uncaught exceptions in threads."""
    _exc_logger.error("UNCAUGHT THREAD EXCEPTION", exc_info=(args.exc_type, args.exc_value, args.exc_traceback))
    with open(_PEARL_EXC_LOG, "a", encoding="utf-8") as f:
        f.write("\n" + "=" * 80 + "\n")
        f.write("Uncaught thread exception\n")
        traceback.print_exception(args.exc_type, args.exc_value, args.exc_traceback, file=f)
        f.write("=" * 80 + "\n\n")

if hasattr(threading, "excepthook"):
    threading.excepthook = _thread_excepthook
# --- END: EXCEPTION TRACKING - THREAD HOOK ---

print(f"[PEARL DIAGNOSTIC]: Exception tracking enabled. Writing to {_PEARL_EXC_LOG}")

# ============================================================================
# END EXCEPTION TRACKING SETUP
# ============================================================================

from config import SETTINGS

# Initialize logging before importing other modules that may log on import
from utils.logging_config import setup_root_logger
setup_root_logger(log_level=SETTINGS.log_level, log_path=SETTINGS.log_path, debug_full_prompts=SETTINGS.debug_full_prompts)

from ui.app import build_demo


def main() -> None:
    demo = build_demo()
    demo.launch(server_name=SETTINGS.host, server_port=SETTINGS.port, share=True)


if __name__ == "__main__":
    main()
