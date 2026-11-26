from __future__ import annotations

import logging
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from config import SETTINGS

logger = logging.getLogger(__name__)


@dataclass
class LoadedIndex:
    collection: Any  # chromadb Collection
    index_dir: Path


class EmbedIndexManager:
    """Embeddings-based index manager using Chromadb for similarity search."""
    
    def __init__(self) -> None:
        self._cache: dict[str, LoadedIndex] = {}
        self._client = None
    
    def _get_client(self):
        """Lazy-load chromadb client."""
        if self._client is None:
            try:
                # Best-effort telemetry suppression. Some Chroma builds still emit
                # posthog telemetry logs unless these are set before import/client init.
                os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
                os.environ.setdefault("CHROMA_ANONYMIZED_TELEMETRY", "False")
                os.environ.setdefault("CHROMA_TELEMETRY", "False")

                import chromadb
                from chromadb.config import Settings as ChromaSettings

                try:
                    import posthog

                    if hasattr(posthog, "capture"):
                        def _noop_capture(*args: Any, **kwargs: Any) -> None:
                            return None

                        posthog.capture = _noop_capture  # type: ignore[assignment]
                except Exception:
                    pass

                # Keep the index local to the DB-specific directory and disable telemetry noise.
                index_root = SETTINGS.created_dbs_dir / SETTINGS.detector_index_dir_name / SETTINGS.detector_chroma_dir_name
                index_root.mkdir(parents=True, exist_ok=True)
                self._client = chromadb.PersistentClient(
                    path=str(index_root),
                    settings=ChromaSettings(anonymized_telemetry=False, allow_reset=True),
                )
            except Exception as exc:
                raise RuntimeError(
                    "chromadb is required for embedding-based indexing. Install with: pip install chromadb"
                ) from exc
        return self._client
    
    def resolve_db_dir(self, db_name: str) -> Path:
        db_dir = SETTINGS.created_dbs_dir / db_name
        if not db_dir.exists():
            raise FileNotFoundError(f"Database directory not found: {db_dir}")
        return db_dir
    
    def resolve_index_dirs(self, db_name: str) -> tuple[Path, Path]:
        db_dir = self.resolve_db_dir(db_name)
        index_dir = db_dir / SETTINGS.detector_index_dir_name / SETTINGS.detector_chroma_dir_name
        fallback_dir = db_dir / SETTINGS.detector_reference_index_dir_name / SETTINGS.detector_chroma_dir_name
        return index_dir, fallback_dir
    
    def _get_embedding_client(self):
        """Get OpenAI-compatible embedding client."""
        try:
            from openai import OpenAI
            return OpenAI(
                base_url=SETTINGS.embed_base_url,
                api_key=SETTINGS.embed_api_key,
            )
        except Exception as exc:
            raise RuntimeError(
                "OpenAI client is required for embeddings. Install with: pip install openai"
            ) from exc
    
    def _create_embedding(self, text: str) -> list[float]:
        """Create embedding for text using configured model."""
        text_normalized = " ".join(str(text or "").strip().split())
        if not text_normalized:
            # Return zero vector for empty text
            return [0.0] * 768  # Adjust dimension as needed
        
        try:
            client = self._get_embedding_client()
            response = client.embeddings.create(
                model=SETTINGS.embed_model_name,
                input=text_normalized,
                encoding_format="float"
            )
            if response.data:
                return list(response.data[0].embedding)
        except Exception as exc:
            logger.warning("Failed to create embedding for '%s': %s", text_normalized[:50], exc)
        
        # Fallback: return zero vector
        return [0.0] * 768
    
    def ensure_loaded(self, db_name: str) -> LoadedIndex:
        """Ensure chroma collection is loaded for db_name."""
        if db_name in self._cache:
            return self._cache[db_name]
        
        index_dir, fallback_dir = self.resolve_index_dirs(db_name)
        index_dir.mkdir(parents=True, exist_ok=True)
        
        # Try to load from existing collection
        client = self._get_client()
        try:
            collection = client.get_collection(name=db_name)
            self._cache[db_name] = LoadedIndex(collection=collection, index_dir=index_dir)
            logger.info("Loaded existing chromadb collection for %s", db_name)
            return self._cache[db_name]
        except Exception:
            # Collection doesn't exist, build new one
            logger.info("Building new chromadb collection for %s", db_name)
        
        self._build_index(db_name=db_name, target_dir=index_dir)
        loaded = LoadedIndex(collection=client.get_collection(name=db_name), index_dir=index_dir)
        self._cache[db_name] = loaded
        return loaded
    
    def _build_index(self, db_name: str, target_dir: Path) -> None:
        """Build chromadb collection from database."""
        db_path = self.resolve_db_dir(db_name) / f"{db_name}.sqlite"
        if not db_path.exists():
            raise FileNotFoundError(f"Database file not found: {db_path}")
        
        target_dir.mkdir(parents=True, exist_ok=True)
        
        client = self._get_client()
        collection = client.create_collection(name=db_name)
        
        documents: list[str] = []
        metadatas: list[dict[str, str]] = []
        embeddings: list[list[float]] = []
        ids: list[str] = []
        
        row_index = 0
        
        conn = sqlite3.connect(str(db_path))
        try:
            table_rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()
            tables = [row[0] for row in table_rows if row and row[0] != "sqlite_sequence"]
            
            for table in tables:
                col_rows = conn.execute(f"PRAGMA table_info('{table}')").fetchall()
                for col in col_rows:
                    column = str(col[1])
                    col_type = str(col[2] or "").upper()
                    
                    # Only index text columns
                    if col_type and not any(t in col_type for t in ["TEXT", "CHAR", "CLOB", "VARCHAR"]):
                        continue
                    
                    # Add column name as document
                    col_id = f"col::{table}::{column}::{row_index}"
                    row_index += 1
                    documents.append(column)
                    embeddings.append(self._create_embedding(column))
                    metadatas.append({
                        "kind": "column",
                        "table": table,
                        "column": column,
                        "value": column,
                    })
                    ids.append(col_id)
                    
                    # Add column values
                    query = f"SELECT DISTINCT `{column}` FROM `{table}` WHERE `{column}` IS NOT NULL LIMIT 4000"
                    try:
                        rows = conn.execute(query).fetchall()
                    except Exception as exc:
                        logger.warning("Failed to query %s.%s: %s", table, column, exc)
                        continue
                    
                    for row in rows:
                        value_text = str(row[0] or "").strip()
                        if not value_text or len(value_text) > 120:
                            continue
                        
                        val_id = f"val::{table}::{column}::{row_index}"
                        row_index += 1
                        documents.append(value_text)
                        embeddings.append(self._create_embedding(value_text))
                        metadatas.append({
                            "kind": "value",
                            "table": table,
                            "column": column,
                            "value": value_text,
                        })
                        ids.append(val_id)
        finally:
            conn.close()
        
        # Add all documents to collection in batches
        if documents:
            batch_size = 100
            for i in range(0, len(documents), batch_size):
                collection.add(
                    ids=ids[i:i+batch_size],
                    embeddings=embeddings[i:i+batch_size],
                    metadatas=metadatas[i:i+batch_size],
                    documents=documents[i:i+batch_size],
                )
        
        logger.info("Built chromadb collection for %s with %d entries at %s", db_name, len(documents), target_dir)
    
    def query_keyword(self, db_name: str, keyword: str, top_n: int, kind: str = "value") -> list[dict[str, Any]]:
        """Query for similar entries using embedding similarity."""
        keyword_text = " ".join(str(keyword or "").strip().split())
        if not keyword_text:
            return []
        
        loaded = self.ensure_loaded(db_name)
        collection = loaded.collection
        
        try:
            query_embedding = self._create_embedding(keyword_text)
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=top_n * 2,  # Get more to filter by kind
            )
        except Exception as exc:
            logger.warning("Failed to query chromadb for '%s': %s", keyword_text[:50], exc)
            return []
        
        if not results or not results.get("metadatas"):
            return []
        
        options: list[dict[str, Any]] = []
        seen: set[str] = set()
        
        for i, metadata in enumerate(results["metadatas"][0]):
            if not metadata:
                continue
            
            payload_kind = str(metadata.get("kind") or "value")
            if kind and payload_kind != kind:
                continue
            
            # Deduplicate
            key = f"{payload_kind}::{metadata.get('table')}::{metadata.get('column')}::{metadata.get('value')}"
            if key in seen:
                continue
            seen.add(key)
            
            # Get similarity score from distances if available
            score = 0.0
            if results.get("distances") and i < len(results["distances"][0]):
                # Chromadb returns distances; convert to similarity (1 - distance for cosine)
                score = max(0.0, 1.0 - results["distances"][0][i])
            
            options.append({
                "table": str(metadata.get("table") or ""),
                "column": str(metadata.get("column") or ""),
                "value": str(metadata.get("value") or ""),
                "kind": payload_kind,
                "score": round(score, 4),
            })
            
            if len(options) >= top_n:
                break
        
        return options
