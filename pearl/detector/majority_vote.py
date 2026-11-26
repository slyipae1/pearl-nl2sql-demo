import logging
import concurrent.futures

import sqlite3
import random
import logging
from typing import Any, Union, List, Dict
import threading

from pathlib import Path
from typing import Any
from config import SETTINGS

def resolve_db_path(db_name: str) -> Path:
        db_path = SETTINGS.created_dbs_dir / db_name / f"{db_name}.sqlite"
        if not db_path.exists():
            raise FileNotFoundError(f"Database file not found: {db_path}")
        return db_path

def execute_sql(db_path: str, sql: str, fetch: Union[str, int] = "all", timeout: int = 120) -> Any:
    # normalized quoted identifiers quoting styles
    # sql = sql.replace('\"', '`').replace('"', '`') # normalize to double quotes for quoted identifiers
    class QueryThread(threading.Thread):
        def __init__(self):
            threading.Thread.__init__(self)
            self.result = None
            self.exception = None

        def run(self):
            try:
                with sqlite3.connect(db_path, timeout=120) as conn:
                    cursor = conn.cursor()
                    cursor.execute(sql)
                    if fetch == "all":
                        self.result = cursor.fetchall()
                    elif fetch == "one":
                        self.result = cursor.fetchone()
                    elif fetch == "random":
                        samples = cursor.fetchmany(10)
                        self.result = random.choice(samples) if samples else []
                    elif isinstance(fetch, int):
                        self.result = cursor.fetchmany(fetch)
                    else:
                        raise ValueError("Invalid fetch argument. Must be 'all', 'one', 'random', or an integer.")
            except Exception as e:
                self.exception = e
    query_thread = QueryThread()
    query_thread.start()
    query_thread.join(timeout)
    if query_thread.is_alive():
        raise TimeoutError(f"SQL query execution exceeded the timeout of {timeout} seconds.")
    if query_thread.exception:
        # print(f"ERROR: execute_sql() Error in execute_sql: {query_thread.exception}\nSQL: {sql}")
        raise query_thread.exception
    return query_thread.result


def perform_majority_vote(sql_candidates: List[str], db_name: str, execution_timeout: int = 30, 
                         max_workers: int = 4, max_rows: int = 10, max_tokens: int = 2000,
                         drop_failed: bool = True) -> List[Dict[str, Any]]:
    """
    Perform majority voting on a list of SQL candidates.
    
    Args:
        sql_candidates: List of SQL strings to vote on
        db_name: Database ID
        execution_timeout: Timeout for SQL execution
        max_workers: Maximum number of concurrent workers
        max_rows: Maximum rows for result summary
        max_tokens: Maximum tokens for result summary
        
    Returns:
        List of ranked voting results
    """
    if not sql_candidates:
        return []
    db_path = resolve_db_path(db_name)
    # Execute all candidates concurrently
    execution_results = _execute_sql_candidates(
        sql_candidates, str(db_path), 
        execution_timeout, max_workers, max_rows, max_tokens
    )
    
    # Calculate majority vote
    vote_results = _calculate_majority_vote(execution_results, drop_failed=drop_failed)
    # log summary
    try:
        logging.info("majority_vote: total_successful=%d total_failed=%d drop_failed=%s",
                     vote_results.get("total_successful", 0), vote_results.get("total_failed", 0), drop_failed)
    except Exception:
        pass
    # Convert to required format
    return _convert_to_ranked_format(vote_results, drop_failed=drop_failed)


def _execute_sql_candidates(sql_candidates: List[str], db_path: str,
                           execution_timeout: int, max_workers: int, 
                           max_rows: int, max_tokens: int) -> List[Dict[str, Any]]:
    """Execute SQL candidates concurrently."""
    execution_tasks = []
    
    for i, sql in enumerate(sql_candidates):
        executable_sql = sql
        execution_tasks.append({
            "option_index": i,
            "original_sql": sql,
            "executable_sql": executable_sql,
            "db_path": db_path,
            "max_rows": max_rows,
            "max_tokens": max_tokens
        })
    
    # Execute tasks concurrently
    execution_results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_task = {
            executor.submit(_execute_single_sql, task): task 
            for task in execution_tasks
        }
        
        for future in concurrent.futures.as_completed(future_to_task):
            task = future_to_task[future]
            try:
                result = future.result(timeout=execution_timeout)
                execution_results.append(result)
            except Exception as e:
                execution_results.append({
                    "option_index": task["option_index"],
                    "original_sql": task["original_sql"],
                    "executable_sql": task["executable_sql"],
                    "error": str(e),
                    "status": "error",
                    "result_summary": f"Execution failed: {str(e)}"
                })
    
    # Sort by option index to maintain order
    execution_results.sort(key=lambda x: x["option_index"])
    
    return execution_results


def _execute_single_sql(task: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a single SQL query."""
    try:
        result = execute_sql(
            task["db_path"], 
            task["executable_sql"], 
            timeout=60
        )
        
        # Extract column names if available
        column_names = None
        try:
            import sqlite3
            with sqlite3.connect(task["db_path"]) as conn:
                cursor = conn.cursor()
                cursor.execute(task["executable_sql"])
                column_names = [desc[0] for desc in cursor.description]
        except:
            pass
        
        return {
            "option_index": task["option_index"],
            "original_sql": task["original_sql"],
            "executable_sql": task["executable_sql"],
            "result": result,
            "column_names": column_names,
            "status": "success",
            "result_summary": _create_result_summary(result, column_names, task["max_rows"], task["max_tokens"])
        }
        
    except Exception as e:
        return {
            "option_index": task["option_index"],
            "original_sql": task["original_sql"],
            "executable_sql": task["executable_sql"],
            "error": str(e),
            "status": "error",
            "result_summary": f"Execution failed: {str(e)}"
        }


def _create_result_summary(result, column_names=None, max_rows: int = 10, max_tokens: int = 1000) -> str:
    """Create a summary or direct representation of execution result."""
    try:
        if isinstance(result, list):
            num_rows = len(result)
            
            # Convert to set to remove duplicates for size estimation
            if result and isinstance(result[0], (list, tuple)):
                unique_result = list(set(tuple(row) for row in result))
            else:
                unique_result = list(set(result))
            
            unique_rows = len(unique_result)
            
            # Estimate token length
            result_str = str(unique_result)
            estimated_tokens = len(result_str.split())
            
            # If small enough, return the actual unique result set
            if unique_rows <= max_rows and estimated_tokens <= max_tokens:
                return f"Result set: {unique_result}"
            
            # Otherwise, create summary
            if num_rows > 0 and isinstance(result[0], (list, tuple)):
                num_cols = len(result[0])
                col_summaries = []
                for col_idx in range(min(num_cols, 5)):
                    col_values = [row[col_idx] for row in result if len(row) > col_idx]
                    unique_count = len(set(col_values))
                    missing_count = sum(1 for v in col_values if v is None or v == '')
                    
                    if column_names and col_idx < len(column_names):
                        col_name = column_names[col_idx]
                    else:
                        col_name = f"col{col_idx+1}"
                    
                    col_summaries.append(f"{col_name}: {unique_count} unique, {missing_count} missing")
                
                summary = f"{num_rows} rows, {num_cols} cols, {', '.join(col_summaries)}"
                if unique_rows != num_rows:
                    summary += f" ({unique_rows} unique rows)"
                return summary
            else:
                summary = f"{num_rows} rows"
                if unique_rows != num_rows:
                    summary += f" ({unique_rows} unique)"
                return summary
        else:
            return str(result)
    except Exception as e:
        logging.warning(f"Error creating result summary: {e}")
        return "Unable to create summary"


def _results_are_equivalent(result1, result2) -> bool:
    """Check if two SQL execution results are equivalent using set comparison."""
    try:
        if result1 is None and result2 is None:
            return True
        if result1 is None or result2 is None:
            return False
        
        if isinstance(result1, list) and isinstance(result2, list):
            if result1 and isinstance(result1[0], (list, tuple)):
                set1 = set(tuple(row) for row in result1)
                set2 = set(tuple(row) for row in result2)
                return set1 == set2
            else:
                return set(result1) == set(result2)
        else:
            return result1 == result2
            
    except Exception as e:
        logging.warning(f"Error in result comparison: {e}")
        return str(result1) == str(result2)


def _calculate_majority_vote(execution_results: List[Dict], drop_failed: bool = True) -> Dict[str, Any]:
    """Calculate majority vote using direct set comparison for result equivalence."""
    # handle empty results -> marked as status as empty
    reformatted_result = []
    for r in execution_results:
        if r["status"] == "success" and (r["result"] is None or len(list(r["result"])) == 0):
            r["error"] = f"Empty result {r['result']}"
            r['status'] = "error"
        reformatted_result.append(r)
    successful_results = [r for r in reformatted_result if r["status"] == "success"]
    failed_results = [r for r in reformatted_result if not r["status"] == "success"]

    # Group results by equivalent execution results
    result_groups = []
    
    for result in successful_results:
        current_result = result["result"]
        
        # Find if this result matches any existing group
        matched_group = None
        for group in result_groups:
            existing_result = group["result"]
            
            try:
                if _results_are_equivalent(current_result, existing_result):
                    matched_group = group
                    break
            except Exception as e:
                logging.warning(f"Error comparing results: {e}")
                continue
        
        if matched_group is not None:
            matched_group["SQLs"].append(result)
            matched_group["votes"] += 1
        else:
            result_groups.append({
                "result": current_result,
                "SQLs": [result],
                "votes": 1
            })
    
    # Sort groups by vote count (descending)
    result_groups.sort(key=lambda x: x["votes"], reverse=True)
    
    # Assign ranks
    current_rank = 1
    prev_votes = None
    
    for group in result_groups:
        votes = group["votes"]
        
        if prev_votes is not None and votes < prev_votes:
            current_rank += 1
        
        group["rank"] = current_rank
        group["vote_category"] = "majority" if current_rank == 1 else "minority_success"
        group["vote_count"] = votes
        
        prev_votes = votes
    
    # Handle failed results
    failed_groups = []
    failed_rank = current_rank + 1 if result_groups else 1

    for result in failed_results:
        failed_groups.append({
            "result": None,
            "SQLs": [result],
            "votes": 0,
            "rank": failed_rank,
            "vote_category": "failed",
            "vote_count": 0
        })

    # If drop_failed is True, exclude failed groups from ranked options
    if drop_failed:
        ranked_options = result_groups
    else:
        ranked_options = result_groups + failed_groups

    all_failed = len(successful_results) == 0

    return {
        "all_failed": all_failed,
        "ranked_options": ranked_options,
        "total_successful": len(successful_results),
        "total_failed": len(failed_results)
    }


def _convert_to_ranked_format(vote_results: Dict[str, Any], drop_failed: bool = True) -> List[Dict[str, Any]]:
    """Convert vote results to the compact ranked cluster format.
    
    Each cluster contains:
    - rnk: rank
    - SQLs: list[str]
    - shared_results: raw execution payload used by the UI
    - shared_result_summary: prompt-safe cluster summary
    """
    ranked_options = vote_results.get("ranked_options", [])
    formatted_results = []

    def _build_shared_results_payload(sql_result: Dict[str, Any]) -> Dict[str, Any] | None:
        if not sql_result:
            return None
        if str(sql_result.get("status") or "").lower() != "success":
            return None
        return {
            "result": sql_result.get("result"),
            "column_names": sql_result.get("column_names"),
            "status": sql_result.get("status", "unknown"),
        }
    
    for group in ranked_options:
        sql_strings = [str(sql_result.get("original_sql") or "").strip() for sql_result in group.get("SQLs", []) if str(sql_result.get("original_sql") or "").strip()]
        if group["vote_category"] != "failed":
            first_sql = group["SQLs"][0] if group.get("SQLs") else {}
            shared_results = _build_shared_results_payload(first_sql)
            representative_summary = str(first_sql.get("result_summary") or "No summary available")
            
            formatted_results.append({
                "rnk": group["rank"],
                "SQLs": sql_strings,
                "shared_results": shared_results,
                "shared_result_summary": representative_summary,
            })
        else:
            # If drop_failed is True we skip appending failed clusters entirely
            if drop_failed:
                continue
            error_text = f"Execution failed: {group.get('SQLs', [{}])[0].get('error', 'Unknown error')}" if group.get("SQLs") else "Execution failed: Unknown error"
            formatted_results.append({
                "rnk": group["rank"],
                "SQLs": sql_strings,
                "shared_results": None,
                "shared_result_summary": error_text,
            })
    
    return formatted_results