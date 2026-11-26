from __future__ import annotations

import logging
import pickle
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from config import SETTINGS

logger = logging.getLogger(__name__)


@dataclass
class LoadedIndex:
    lsh: Any
    minhashes: dict[str, Any]
    index_dir: Path


class LSHIndexManager:
    def __init__(self) -> None:
        self._cache: dict[str, LoadedIndex] = {}

    def resolve_db_dir(self, db_name: str) -> Path:
        db_dir = SETTINGS.created_dbs_dir / db_name
        if not db_dir.exists():
            raise FileNotFoundError(f"Database directory not found: {db_dir}")
        return db_dir

    def resolve_index_dirs(self, db_name: str) -> tuple[Path, Path]:
        db_dir = self.resolve_db_dir(db_name)
        index_dir = db_dir / SETTINGS.detector_index_dir_name
        fallback_dir = db_dir / SETTINGS.detector_reference_index_dir_name
        return index_dir, fallback_dir

    def _index_file_triplet(self, db_name: str, base_dir: Path) -> tuple[Path, Path, Path]:
        return (
            base_dir / f"{db_name}_lsh.pkl",
            base_dir / f"{db_name}_minhashes.pkl",
            base_dir / f"{db_name}_unique_values.pkl",
        )

    def _exists_triplet(self, db_name: str, base_dir: Path) -> bool:
        lsh_file, minhash_file, _ = self._index_file_triplet(db_name, base_dir)
        return lsh_file.exists() and minhash_file.exists()

    def ensure_loaded(self, db_name: str) -> LoadedIndex:
        if db_name in self._cache:
            return self._cache[db_name]

        index_dir, fallback_dir = self.resolve_index_dirs(db_name)
        index_dir.mkdir(parents=True, exist_ok=True)

        # Read both: prefer index/, then fallback preprocessed/.
        if self._exists_triplet(db_name, index_dir):
            loaded = self._load_from_dir(db_name, index_dir)
            self._cache[db_name] = loaded
            return loaded

        if self._exists_triplet(db_name, fallback_dir):
            loaded = self._load_from_dir(db_name, fallback_dir)
            self._cache[db_name] = loaded
            return loaded

        # Nothing exists: write to index/ by default.
        self._build_index(db_name=db_name, target_dir=index_dir)
        loaded = self._load_from_dir(db_name, index_dir)
        self._cache[db_name] = loaded
        return loaded

    def _load_from_dir(self, db_name: str, base_dir: Path) -> LoadedIndex:
        lsh_file, minhash_file, _ = self._index_file_triplet(db_name, base_dir)
        with lsh_file.open("rb") as file:
            lsh = pickle.load(file)
        with minhash_file.open("rb") as file:
            minhashes = pickle.load(file)
        return LoadedIndex(lsh=lsh, minhashes=minhashes, index_dir=base_dir)

    @staticmethod
    def _normalize_text(value: Any) -> str:
        return " ".join(str(value or "").strip().split())

    @staticmethod
    def _create_minhash(text: str, signature_size: int, n_gram: int):
        from datasketch import MinHash

        text = text or ""
        grams = [text[i : i + n_gram] for i in range(max(len(text) - n_gram + 1, 1))] if text else []
        minhash = MinHash(num_perm=signature_size)
        if not grams:
            minhash.update(text.encode("utf-8"))
            return minhash
        for gram in grams:
            minhash.update(gram.encode("utf-8"))
        return minhash

    def _build_index(self, db_name: str, target_dir: Path) -> None:
        try:
            from datasketch import MinHashLSH
        except Exception as exc:
            raise RuntimeError(
                "datasketch is required for LSH index building. Install package `datasketch`."
            ) from exc

        db_path = self.resolve_db_dir(db_name) / f"{db_name}.sqlite"
        if not db_path.exists():
            raise FileNotFoundError(f"Database file not found: {db_path}")

        target_dir.mkdir(parents=True, exist_ok=True)

        signature_size = SETTINGS.detector_lsh_signature_size
        n_gram = SETTINGS.detector_lsh_ngram
        threshold = SETTINGS.detector_lsh_threshold

        lsh = MinHashLSH(threshold=threshold, num_perm=signature_size)
        minhashes: dict[str, Any] = {}
        unique_values: dict[str, dict[str, list[str]]] = {}

        conn = sqlite3.connect(str(db_path))
        try:
            table_rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()
            tables = [row[0] for row in table_rows if row and row[0] != "sqlite_sequence"]

            row_index = 0
            for table in tables:
                unique_values[table] = {}
                col_rows = conn.execute(f"PRAGMA table_info('{table}')").fetchall()
                for col in col_rows:
                    column = str(col[1])
                    col_type = str(col[2] or "").upper()
                    if col_type and not any(t in col_type for t in ["TEXT", "CHAR", "CLOB", "VARCHAR"]):
                        continue

                    # Insert column-name LSH entry.
                    col_key = f"col::{table}::{column}"
                    col_text = self._normalize_text(column)
                    if col_text:
                        col_hash = self._create_minhash(col_text.lower(), signature_size, n_gram)
                        lsh.insert(col_key, col_hash)
                        minhashes[col_key] = {
                            "kind": "column",
                            "table": table,
                            "column": column,
                            "value": column,
                            "minhash": col_hash,
                        }

                    # Build value entries.
                    query = f"SELECT DISTINCT `{column}` FROM `{table}` WHERE `{column}` IS NOT NULL LIMIT 4000"
                    rows = conn.execute(query).fetchall()
                    values: list[str] = []
                    for row in rows:
                        value = self._normalize_text(row[0])
                        if not value:
                            continue
                        if len(value) > 120:
                            continue
                        values.append(value)

                    if not values:
                        continue

                    unique_values[table][column] = values
                    for value in values:
                        value_key = f"val::{table}::{column}::{row_index}"
                        row_index += 1
                        val_hash = self._create_minhash(value.lower(), signature_size, n_gram)
                        lsh.insert(value_key, val_hash)
                        minhashes[value_key] = {
                            "kind": "value",
                            "table": table,
                            "column": column,
                            "value": value,
                            "minhash": val_hash,
                        }
        finally:
            conn.close()

        lsh_file, minhash_file, unique_values_file = self._index_file_triplet(db_name, target_dir)
        with lsh_file.open("wb") as file:
            pickle.dump(lsh, file)
        with minhash_file.open("wb") as file:
            pickle.dump(minhashes, file)
        with unique_values_file.open("wb") as file:
            pickle.dump(unique_values, file)

        logger.info("Built LSH index for %s at %s", db_name, target_dir)

    def query_keyword(self, db_name: str, keyword: str, top_n: int, kind: str = "value") -> list[dict[str, Any]]:
        keyword_text = self._normalize_text(keyword)
        if not keyword_text:
            return []

        loaded = self.ensure_loaded(db_name)
        signature_size = SETTINGS.detector_lsh_signature_size
        n_gram = SETTINGS.detector_lsh_ngram

        query_hash = self._create_minhash(keyword_text.lower(), signature_size, n_gram)
        try:
            candidate_keys = loaded.lsh.query(query_hash)
        except Exception:
            return []

        scored: list[tuple[float, dict[str, Any]]] = []
        for key in candidate_keys:
            payload = self._parse_payload(loaded.minhashes.get(key))
            if not payload:
                continue
            payload_kind = str(payload.get("kind") or "value")
            if kind and payload_kind != kind:
                continue

            payload_minhash = payload.get("minhash")
            if payload_minhash is None:
                continue
            score = float(query_hash.jaccard(payload_minhash))
            if score <= 0:
                continue
            scored.append((score, payload))

        scored.sort(key=lambda item: item[0], reverse=True)
        options: list[dict[str, Any]] = []
        for score, payload in scored[:top_n]:
            options.append(
                {
                    "table": str(payload.get("table") or ""),
                    "column": str(payload.get("column") or ""),
                    "value": str(payload.get("value") or ""),
                    "kind": str(payload.get("kind") or kind),
                    "score": round(score, 4),
                }
            )
        return options

    @staticmethod
    def _parse_payload(raw_payload: Any) -> dict[str, Any] | None:
        if raw_payload is None:
            return None

        if isinstance(raw_payload, dict):
            return raw_payload

        # Support legacy tuple payloads: (minhash, table, column, value)
        if isinstance(raw_payload, tuple) and len(raw_payload) >= 4:
            return {
                "minhash": raw_payload[0],
                "table": raw_payload[1],
                "column": raw_payload[2],
                "value": raw_payload[3],
                "kind": "value",
            }

        return None
