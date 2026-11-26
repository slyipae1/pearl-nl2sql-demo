import logging
from pathlib import Path
from typing import Dict

import pandas as pd


ENCODING_TYPES = ["utf-8-sig", "utf-8", "cp1252", "latin1", "iso-8859-1", "utf-16", "utf-16le", "utf-16be"]


def resolve_database_root(db_source: str | Path) -> Path:
    path = Path(db_source)
    if path.is_file() or path.suffix.lower() in {".sqlite", ".db"}:
        return path.parent
    return path


def resolve_database_description_path(db_source: str | Path) -> Path:
    return resolve_database_root(db_source) / "database_description"


def _clean_description_text(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    if not isinstance(value, str) and text.lower() in {"nan", "na", "none", "<na>"}:
        return ""
    text = text.replace("\n", " ").replace("commonsense evidence:", "").strip()
    return " ".join(text.split())


def load_tables_description(
    db_source: str | Path,
    use_value_description: bool = False,
) -> Dict[str, Dict[str, Dict[str, str]]]:
    """
    Loads table descriptions from CSV files in the database directory.

    Args:
        db_directory_path (str): The path to the database directory.
        use_value_description (bool): Whether to include value descriptions.

    Returns:
        Dict[str, Dict[str, Dict[str, str]]]: A dictionary containing table descriptions.
    """
    description_path = resolve_database_description_path(db_source)

    if not description_path.exists():
        logging.warning(f"Description path does not exist: {description_path}")
        return {}

    table_description = {}
    for csv_file in description_path.glob("*.csv"):
        table_name = csv_file.stem.lower().strip()
        table_description[table_name] = {}
        could_read = False
        for encoding_type in ENCODING_TYPES:
            try:
                table_description_df = pd.read_csv(csv_file, index_col=False, encoding=encoding_type)
                for _, row in table_description_df.iterrows():
                    column_name = str(row.get("original_column_name", "")).strip()
                    if not column_name:
                        continue
                    expanded_column_name = _clean_description_text(row.get("column_name", ""))
                    column_description = _clean_description_text(row.get("column_description", ""))
                    data_format = _clean_description_text(row.get("data_format", ""))
                    value_description = ""
                    if use_value_description and pd.notna(row.get('value_description', '')):
                        value_description = _clean_description_text(row['value_description'])
                        if value_description.lower().startswith("not useful"):
                            value_description = value_description[10:].strip()
                    
                    table_description[table_name][column_name.lower()] = {
                        "original_column_name": column_name,
                        "column_name": expanded_column_name,
                        "column_description": column_description,
                        "data_format": data_format,
                        "value_description": value_description
                    }
                # logging.info(f"Loaded descriptions from {csv_file} with encoding {encoding_type}")
                could_read = True
                break
            except Exception:
                # print(f"Failed to read {csv_file} with encoding {encoding_type}, trying next encoding.")
                continue
    if not could_read:
        logging.warning(f"Could not read descriptions from {csv_file}")
    return table_description


def load_tables_concatenated_description(
    db_source: str | Path,
    use_value_description: bool = False,
) -> Dict[str, Dict[str, str]]:
    """
    Loads concatenated table descriptions from the database directory.

    Args:
        db_directory_path (str): The path to the database directory.
        use_value_description (bool): Whether to include value descriptions.

    Returns:
        Dict[str, Dict[str, str]]: A dictionary containing concatenated table descriptions.
    """
    tables_description = load_tables_description(db_source, use_value_description)
    concatenated_descriptions = {}
    
    for table_name, columns in tables_description.items():
        concatenated_descriptions[table_name] = {}
        
        for column_name, column_info in columns.items():
            concatenated_description = ", ".join(
                value for key, value in column_info.items() if key in ['column_name', 'column_description', 'value_description'] and value
            ).strip().replace("  ", " ")
            concatenated_descriptions[table_name][column_name] = concatenated_description.strip(", ")
    
    return concatenated_descriptions
