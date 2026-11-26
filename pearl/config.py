from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def load_env_file(env_path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not env_path.exists():
        return values
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


@dataclass(frozen=True)
class Settings:
    model_name: str
    api_base: str
    api_key: str
    coder_model_name: str
    coder_api_base: str
    coder_api_key: str
    detector_lsh_top_n: int
    detector_lsh_signature_size: int
    detector_lsh_ngram: int
    detector_lsh_threshold: float
    detector_index_dir_name: str
    detector_reference_index_dir_name: str
    host: str
    port: int
    save_temp_exec: bool
    manager_summary_timeout_seconds: int
    log_path: str
    preference_base_scope: str
    workspace_dir: Path
    project_dir: Path
    created_dbs_dir: Path
    temp_exec_dir: Path
    log_level: str
    debug_full_prompts: bool
    cand_gen_type: str
    toolcall_model_name: str
    toolcall_api_base: str
    toolcall_api_key: str
    similarity_measure: str
    embed_model_name: str
    embed_base_url: str
    embed_api_key: str
    detector_chroma_dir_name: str


def create_settings() -> Settings:
    project_dir = Path(__file__).resolve().parent
    workspace_dir = project_dir.parent
    env_values = load_env_file(project_dir / ".env")

    model_name = os.environ.get("MODEL_NAME", env_values.get("MODEL_NAME", "Qwen3.5-27B"))
    api_base = os.environ.get("BASE_URL", env_values.get("BASE_URL", ""))
    api_key = os.environ.get("API_KEY", env_values.get("API_KEY", ""))

    coder_model_name = os.environ.get("CODER_MODEL_NAME", env_values.get("CODER_MODEL_NAME", model_name))
    coder_api_base = os.environ.get("CODER_BASE_URL", env_values.get("CODER_BASE_URL", api_base))
    coder_api_key = os.environ.get("CODER_API_KEY", env_values.get("CODER_API_KEY", api_key))
    detector_lsh_top_n = int(os.environ.get("DETECTOR_LSH_TOP_N", env_values.get("DETECTOR_LSH_TOP_N", "5")))
    detector_lsh_signature_size = int(
        os.environ.get("DETECTOR_LSH_SIGNATURE_SIZE", env_values.get("DETECTOR_LSH_SIGNATURE_SIZE", "100"))
    )
    detector_lsh_ngram = int(os.environ.get("DETECTOR_LSH_NGRAM", env_values.get("DETECTOR_LSH_NGRAM", "3")))
    detector_lsh_threshold = float(
        os.environ.get("DETECTOR_LSH_THRESHOLD", env_values.get("DETECTOR_LSH_THRESHOLD", "0.5"))
    )
    detector_index_dir_name = os.environ.get("DETECTOR_INDEX_DIR", env_values.get("DETECTOR_INDEX_DIR", "index"))
    detector_reference_index_dir_name = os.environ.get(
        "DETECTOR_REFERENCE_INDEX_DIR",
        env_values.get("DETECTOR_REFERENCE_INDEX_DIR", "preprocessed"),
    )
    toolcall_model_name = os.environ.get("TOOLCALL_MODEL_NAME", env_values.get("TOOLCALL_MODEL_NAME", model_name))
    toolcall_api_base = os.environ.get("TOOLCALL_BASE_URL", env_values.get("TOOLCALL_BASE_URL", api_base))
    toolcall_api_key = os.environ.get("TOOLCALL_API_KEY", env_values.get("TOOLCALL_API_KEY", api_key))

    host = os.environ.get("HOST", env_values.get("HOST", "0.0.0.0"))
    port = int(os.environ.get("PORT", env_values.get("PORT", "7863")))

    raw_save_temp_exec = os.environ.get("SAVE_TEMP_EXEC", env_values.get("SAVE_TEMP_EXEC", "false"))
    save_temp_exec = str(raw_save_temp_exec).strip().lower() in {"1", "true", "yes", "y", "on"}
    manager_summary_timeout_seconds = int(
        os.environ.get(
            "MANAGER_SUMMARY_TIMEOUT_SECONDS",
            env_values.get("MANAGER_SUMMARY_TIMEOUT_SECONDS", "600"),
        )
    )

    log_path = os.environ.get("LOG_PATH", env_values.get("LOG_PATH", ""))
    log_level = os.environ.get("LOG_LEVEL", env_values.get("LOG_LEVEL", "INFO"))
    raw_debug_full_prompts = os.environ.get(
        "DEBUG_FULL_PROMPTS", env_values.get("DEBUG_FULL_PROMPTS", "false")
    )
    debug_full_prompts = str(raw_debug_full_prompts).strip().lower() in {"1", "true", "yes", "y", "on"}

    cand_gen_type = os.environ.get("CAND_GEN_TYPE", env_values.get("CAND_GEN_TYPE", "default"))
    preference_base_scope = os.environ.get(
        "PREFERENCE_BASE_SCOPE",
        env_values.get("PREFERENCE_BASE_SCOPE", "within_DB"),
    )
    
    similarity_measure = os.environ.get("SIMILARITY_MEASURE", env_values.get("SIMILARITY_MEASURE", "Default"))
    embed_model_name = os.environ.get("EMBED_MODEL_NAME", env_values.get("EMBED_MODEL_NAME", "Qwen/Qwen3-Embedding-0.6B"))
    embed_base_url = os.environ.get("EMBED_BASE_URL", env_values.get("EMBED_BASE_URL", "https://api-inference.modelscope.cn/v1"))
    embed_api_key = os.environ.get("EMBED_API_KEY", env_values.get("EMBED_API_KEY", ""))
    detector_chroma_dir_name = os.environ.get("DETECTOR_CHROMA_DIR", env_values.get("DETECTOR_CHROMA_DIR", "chroma_index"))

    created_dbs_dir = os.environ.get("CREATED_DBS_DIR", workspace_dir / "data" / "created_dbs")
    temp_exec_dir = project_dir / "temp_exec"
    temp_exec_dir.mkdir(parents=True, exist_ok=True)

    return Settings(
        model_name=model_name,
        api_base=api_base,
        api_key=api_key,
        coder_model_name=coder_model_name,
        coder_api_base=coder_api_base,
        coder_api_key=coder_api_key,
        toolcall_model_name=toolcall_model_name,
        toolcall_api_base=toolcall_api_base,
        toolcall_api_key=toolcall_api_key,
        detector_lsh_top_n=detector_lsh_top_n,
        detector_lsh_signature_size=detector_lsh_signature_size,
        detector_lsh_ngram=detector_lsh_ngram,
        detector_lsh_threshold=detector_lsh_threshold,
        detector_index_dir_name=detector_index_dir_name,
        detector_reference_index_dir_name=detector_reference_index_dir_name,
        host=host,
        port=port,
        save_temp_exec=save_temp_exec,
        manager_summary_timeout_seconds=manager_summary_timeout_seconds,
        log_path=log_path,
        preference_base_scope=preference_base_scope,
        log_level=log_level,
        debug_full_prompts=debug_full_prompts,
        cand_gen_type=cand_gen_type,
        workspace_dir=workspace_dir,
        project_dir=project_dir,
        created_dbs_dir=created_dbs_dir,
        temp_exec_dir=temp_exec_dir,
        similarity_measure=similarity_measure,
        embed_model_name=embed_model_name,
        embed_base_url=embed_base_url,
        embed_api_key=embed_api_key,
        detector_chroma_dir_name=detector_chroma_dir_name,
    )


SETTINGS = create_settings()
