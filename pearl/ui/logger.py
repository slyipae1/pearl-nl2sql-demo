"""Round-based conversation logger.

Appends one JSON line per completed round to a JSONL file.
Controlled by LOG_PATH env var. Noop when empty/not set.
"""

from __future__ import annotations

import json
import os
from utils.logging_config import get_logger

logger = get_logger(__name__)


def write_round_log(
    log_path: str,
    round_id: str,
    attended_nodes: list[str],
    nodes: list[dict],
) -> None:
    """Append one round as a JSON line to *log_path*.

    Creates the parent directory if it does not exist.
    Noop when *log_path* is empty.
    """
    if not log_path:
        return

    log_dir = os.path.dirname(log_path)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)

    entry = {
        "round_id": round_id,
        "attended_nodes": attended_nodes,
        "nodes": nodes,
    }

    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    logger.info("Wrote round log for round_id=%s to %s", round_id, log_path)
