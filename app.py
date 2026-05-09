from __future__ import annotations

import hashlib
import html
import io
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import branca.colormap as cm
import folium
import pandas as pd
import streamlit as st
from folium.plugins import MarkerCluster
from streamlit_folium import st_folium


# -----------------------------------------------------------------------------
# Page configuration
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Site Work Status Map Dashboard",
    page_icon="🗺️",
    layout="wide",
    initial_sidebar_state="expanded",
)

REQUIRED_COLUMNS: list[str] = [
    "location_id",
    "location_name",
    "country",
    "state",
    "city",
    "latitude",
    "longitude",
    "timezone",
    "enabled",
]

NA_VALUES = {"n/a", "na", "not applicable", "해당없음"}
DASH_PLACEHOLDERS = {"-", "–", "—"}
VALID_TRUE = {"y", "yes", "true", "1"}
VALID_FALSE = {"n", "no", "false", "0"}
PROGRESS_RE = re.compile(r"^\s*([+-]?\d+(?:\.\d+)?)\s*/\s*([+-]?\d+(?:\.\d+)?)\s*$")
DEFAULT_SITE_STATUS_FILENAME = "site_status.csv"
SITE_METADATA_COLUMNS = {"version", "updated_date", "qty", "note"}
UPDATED_DATE_COLUMN_NAME = "updated_date"
UPDATED_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
dashboard_ver = "v1.10"
DEFAULT_TASK_CONFIG_FILENAME = "task_config.csv"
TASK_CONFIG_COLUMNS = ["task_name", "visible", "category", "display_order", "description"]

STATUS_COLORS = {
    "green": "#2e7d32",
    "blue": "#1976d2",
    "orange": "#ef6c00",
    "red": "#c62828",
    "gray": "#757575",
    "lightgray": "#bdbdbd",
    "darkgray": "#616161",
    "purple": "#6a1b9a",
    "warning": "#f9a825",
}

FOLIUM_ICON_COLOR = {
    "green": "green",
    "blue": "blue",
    "orange": "orange",
    "red": "red",
    "gray": "gray",
    "lightgray": "lightgray",
    "darkgray": "darkgray",
    "purple": "purple",
    "warning": "orange",
}

STRING_STATUS_PALETTE = [
    "#5e35b1",
    "#00897b",
    "#3949ab",
    "#7cb342",
    "#00acc1",
    "#8e24aa",
    "#43a047",
    "#546e7a",
    "#6d4c41",
    "#f4511e",
]

SAMPLE_CSV = """location_id,location_name,country,state,city,latitude,longitude,timezone,enabled,Valve1,Valve2,Water Pump,Chiller F/W Version,HVAC F/W Version
FL001,BLACKWATER RIVER,US,FL,Milton,30.6,-86.9,America/Chicago,Y,60/66,N/A,10/66,3.0.0.0,3.0.0.1
FL002,CANOE,US,FL,Holt,30.6,-86.7,America/Chicago,Y,20/183,183/183,183/183,3.0.0.2,3.0.0.6
FL003,SAMPLE DISABLED,US,TX,Dallas,32.7,-96.7,America/Chicago,N,5/10,NA,,Pending,Completed
"""

SAMPLE_TASK_CONFIG_CSV = """task_name,visible,category,display_order,description
Valve1,Y,Active Work,10,Currently managed work item
Valve2,Y,Active Work,20,Currently managed work item
Water Pump,Y,Active Work,30,Currently managed work item
Chiller F/W Version,Y,Information,40,Firmware version information
HVAC F/W Version,Y,Information,50,Firmware version information
Note,Y,Information,999,Free text notes; excluded from KPI completion counts
"""


# -----------------------------------------------------------------------------
# CSV / data processing
# -----------------------------------------------------------------------------
def get_required_columns() -> list[str]:
    return REQUIRED_COLUMNS.copy()


def create_sample_csv() -> bytes:
    return SAMPLE_CSV.encode("utf-8-sig")


def create_sample_task_config_csv() -> bytes:
    return SAMPLE_TASK_CONFIG_CSV.encode("utf-8-sig")


@st.cache_data(show_spinner=False)
def _load_csv_bytes(file_bytes: bytes, source_name: str) -> pd.DataFrame:
    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "utf-8", "cp949"):
        try:
            text = file_bytes.decode(encoding)
            first_line = text.splitlines()[0] if text.splitlines() else ""
            sep = "\t" if first_line.count("\t") > first_line.count(",") else ","
            return pd.read_csv(io.StringIO(text), sep=sep, dtype=str, keep_default_na=False)
        except UnicodeDecodeError as exc:
            last_error = exc
        except Exception as exc:
            raise ValueError(f"CSV parsing failed for {source_name}: {exc}") from exc
    raise ValueError(f"CSV encoding failed for {source_name}. Tried utf-8-sig, utf-8, cp949. Last error: {last_error}")


def get_default_site_status_csv() -> bytes:
    default_path = Path(__file__).with_name(DEFAULT_SITE_STATUS_FILENAME)
    if default_path.exists():
        return default_path.read_bytes()
    return create_sample_csv()


def load_csv(uploaded_file: Any | None) -> pd.DataFrame:
    if uploaded_file is None:
        return _load_csv_bytes(get_default_site_status_csv(), DEFAULT_SITE_STATUS_FILENAME)
    file_bytes = uploaded_file.getvalue()
    return _load_csv_bytes(file_bytes, uploaded_file.name)


def get_default_task_config_csv() -> bytes | None:
    default_path = Path(__file__).with_name(DEFAULT_TASK_CONFIG_FILENAME)
    if default_path.exists():
        return default_path.read_bytes()
    return None


def load_task_config(uploaded_file: Any | None) -> pd.DataFrame:
    if uploaded_file is None:
        default_bytes = get_default_task_config_csv()
        if default_bytes is None:
            return pd.DataFrame(columns=TASK_CONFIG_COLUMNS)
        return _load_csv_bytes(default_bytes, DEFAULT_TASK_CONFIG_FILENAME)
    return _load_csv_bytes(uploaded_file.getvalue(), uploaded_file.name)


def _find_case_insensitive_column(columns: Any, target_name: str) -> str | None:
    target = str(target_name).strip().lower()
    for col in columns:
        if str(col).strip().lower() == target:
            return str(col)
    return None


def is_site_metadata_column(column_name: str) -> bool:
    return str(column_name).strip().lower() in SITE_METADATA_COLUMNS


def _get_updated_date_column_name(columns: Any) -> str | None:
    return _find_case_insensitive_column(columns, UPDATED_DATE_COLUMN_NAME)


def get_updated_date_display(df: pd.DataFrame) -> str:
    updated_date_col = _get_updated_date_column_name(df.columns)
    if updated_date_col is None:
        return "Not set"

    source_df = df
    if "_enabled_bool" in source_df.columns:
        source_df = source_df[source_df["_enabled_bool"] == True]  # noqa: E712

    values = [
        str(value).strip()
        for value in source_df[updated_date_col].dropna().tolist()
        if str(value).strip()
    ]
    return values[0] if values else "Not set"


def _validate_updated_date_metadata(
    working: pd.DataFrame,
    enabled_working: pd.DataFrame,
    issues: list[dict[str, Any]],
) -> None:
    updated_date_col = _get_updated_date_column_name(working.columns)
    if updated_date_col is None:
        _add_issue(
            issues,
            None,
            "",
            UPDATED_DATE_COLUMN_NAME,
            "",
            "Optional metadata column 'updated_date' is missing. Add it to show Updated Date in the dashboard header.",
            "INFO",
        )
        return

    non_empty_values: list[str] = []
    for idx, row in enabled_working.iterrows():
        raw_value = row.get(updated_date_col, "")
        text = str(raw_value).strip()
        if not text:
            _add_issue(
                issues,
                int(idx),
                row.get("location_id", ""),
                updated_date_col,
                raw_value,
                "updated_date is missing for an enabled site. Use YYYY-MM-DD, e.g. 2026-05-09.",
                "WARNING",
            )
            continue
        non_empty_values.append(text)
        if not UPDATED_DATE_RE.match(text):
            _add_issue(
                issues,
                int(idx),
                row.get("location_id", ""),
                updated_date_col,
                raw_value,
                "updated_date should use YYYY-MM-DD format, e.g. 2026-05-09.",
                "WARNING",
            )
            continue
        try:
            datetime.strptime(text, "%Y-%m-%d")
        except ValueError:
            _add_issue(
                issues,
                int(idx),
                row.get("location_id", ""),
                updated_date_col,
                raw_value,
                "updated_date is not a valid calendar date.",
                "WARNING",
            )

    distinct_values = sorted(set(non_empty_values))
    if len(distinct_values) > 1:
        _add_issue(
            issues,
            None,
            "",
            updated_date_col,
            "; ".join(distinct_values),
            "Enabled rows contain multiple updated_date values. Use one dashboard-level data date unless row-level dates are intentional.",
            "WARNING",
        )


def _normalize_task_config_visible(value: Any) -> bool:
    if value is None or pd.isna(value):
        return True
    text = str(value).strip().lower()
    if text == "":
        return True
    if text in VALID_TRUE:
        return True
    if text in VALID_FALSE:
        return False
    return True


def _parse_task_display_order(value: Any, fallback_order: int) -> tuple[int, int]:
    if value is None or pd.isna(value) or str(value).strip() == "":
        return (1, fallback_order)
    try:
        return (0, int(float(str(value).strip())))
    except Exception:
        return (1, fallback_order)


def _get_task_config_column(task_config_df: pd.DataFrame, column_name: str) -> str | None:
    return _find_case_insensitive_column(task_config_df.columns, column_name)


def apply_task_config_to_task_columns(
    all_task_columns: list[str],
    task_config_df: pd.DataFrame,
) -> tuple[list[str], list[dict[str, Any]], dict[str, Any]]:

    issues: list[dict[str, Any]] = []
    meta: dict[str, Any] = {
        "config_loaded": not task_config_df.empty,
        "hidden_tasks": [],
        "unknown_config_tasks": [],
        "invalid_visible_rows": 0,
    }

    if task_config_df.empty:
        return all_task_columns.copy(), issues, meta

    task_name_col = _get_task_config_column(task_config_df, "task_name")
    if task_name_col is None:
        _add_issue(
            issues,
            None,
            "",
            "task_config.task_name",
            "",
            "task_config.csv is loaded but missing required column 'task_name'. All task columns will remain visible.",
            "WARNING",
        )
        return all_task_columns.copy(), issues, meta

    visible_col = _get_task_config_column(task_config_df, "visible")
    order_col = _get_task_config_column(task_config_df, "display_order")

    task_lookup = {str(task).strip().casefold(): task for task in all_task_columns}
    config_by_task_key: dict[str, dict[str, Any]] = {}
    duplicate_keys: set[str] = set()

    for idx, row in task_config_df.iterrows():
        raw_task_name = row.get(task_name_col, "")
        task_name = str(raw_task_name).strip()
        if not task_name:
            _add_issue(
                issues,
                int(idx),
                "",
                "task_config.task_name",
                raw_task_name,
                "task_config.csv contains a blank task_name row. The row is ignored.",
                "WARNING",
            )
            continue

        task_key = task_name.casefold()
        if task_key in config_by_task_key:
            duplicate_keys.add(task_key)

        raw_visible = row.get(visible_col, "Y") if visible_col is not None else "Y"
        visible_text = str(raw_visible).strip().lower()
        if visible_text and visible_text not in VALID_TRUE and visible_text not in VALID_FALSE:
            meta["invalid_visible_rows"] += 1
            _add_issue(
                issues,
                int(idx),
                "",
                "task_config.visible",
                raw_visible,
                "Invalid visible value in task_config.csv. Use Y/Yes/TRUE/1 or N/No/FALSE/0. This row defaults to visible=Y.",
                "WARNING",
            )

        config_by_task_key[task_key] = {
            "task_name": task_name,
            "visible": _normalize_task_config_visible(raw_visible),
            "display_order": row.get(order_col, "") if order_col is not None else "",
            "row_index": int(idx),
        }

    for task_key in sorted(duplicate_keys):
        _add_issue(
            issues,
            None,
            "",
            "task_config.task_name",
            config_by_task_key[task_key]["task_name"],
            "Duplicate task_name in task_config.csv. The last matching row is used.",
            "WARNING",
        )

    for task_key, config in config_by_task_key.items():
        if task_key not in task_lookup:
            meta["unknown_config_tasks"].append(config["task_name"])
            _add_issue(
                issues,
                config.get("row_index"),
                "",
                "task_config.task_name",
                config["task_name"],
                "task_config.csv references a task not found in site_status.csv. The row is ignored.",
                "INFO",
            )

    ordered_visible_tasks: list[tuple[tuple[int, int], int, str]] = []
    hidden_tasks: list[str] = []
    for fallback_order, task in enumerate(all_task_columns):
        task_key = str(task).strip().casefold()
        config = config_by_task_key.get(task_key)
        visible = True if config is None else bool(config["visible"])
        if not visible:
            hidden_tasks.append(task)
            continue
        display_order_value = config.get("display_order", "") if config is not None else ""
        order_key = _parse_task_display_order(display_order_value, fallback_order)
        ordered_visible_tasks.append((order_key, fallback_order, task))

    meta["hidden_tasks"] = hidden_tasks
    visible_tasks = [task for _, _, task in sorted(ordered_visible_tasks, key=lambda item: (item[0], item[1]))]
    return visible_tasks, issues, meta


def get_task_columns(df: pd.DataFrame) -> list[str]:
    if "enabled" not in df.columns:
        return []
    enabled_idx = list(df.columns).index("enabled")
    task_columns: list[str] = []
    for col in list(df.columns)[enabled_idx + 1 :]:
        col_name = str(col)
        if not col_name.strip():
            continue
        if col_name.startswith("_"):
            continue
        if is_site_metadata_column(col_name):
            continue
        task_columns.append(col_name)
    return task_columns


def is_note_column(column_name: str) -> bool:
    return str(column_name).strip().lower() == "note"


def normalize_enabled(value: Any) -> bool | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in VALID_TRUE:
        return True
    if text in VALID_FALSE:
        return False
    if text == "" or text == "nan":
        return None
    return None


def _add_issue(
    issues: list[dict[str, Any]],
    row_index: int | None,
    location_id: Any,
    column: str,
    raw_value: Any,
    issue: str,
    severity: str,
) -> None:
    issues.append(
        {
            "row_index": row_index,
            "location_id": "" if pd.isna(location_id) else str(location_id),
            "column": column,
            "raw_value": "" if pd.isna(raw_value) else str(raw_value),
            "issue": issue,
            "severity": severity,
        }
    )


def validate_dataframe(
    df: pd.DataFrame,
    task_columns_to_validate: list[str] | None = None,
    require_task_columns: bool = True,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    issues: list[dict[str, Any]] = []
    working = df.copy()

    for col in get_required_columns():
        if col not in working.columns:
            _add_issue(issues, None, "", col, "", f"Required column '{col}' is missing.", "ERROR")
            working[col] = ""

    task_columns = task_columns_to_validate if task_columns_to_validate is not None else get_task_columns(working)
    if require_task_columns and not task_columns:
        _add_issue(issues, None, "", "task_columns", "", "No task columns found after 'enabled'.", "ERROR")

    working["_enabled_bool"] = working["enabled"].apply(normalize_enabled)
    for idx, row in working.iterrows():
        if row.get("_enabled_bool") is None:
            _add_issue(
                issues,
                int(idx),
                row.get("location_id", ""),
                "enabled",
                row.get("enabled", ""),
                "Invalid enabled value. Use Y, Yes, TRUE, 1, N, No, FALSE, or 0.",
                "WARNING",
            )

    enabled_working = working[working["_enabled_bool"] == True].copy()  # noqa: E712

    _validate_updated_date_metadata(working, enabled_working, issues)

    for idx, row in enabled_working.iterrows():
        location_id = row.get("location_id", "")
        if str(location_id).strip() == "":
            _add_issue(issues, int(idx), location_id, "location_id", location_id, "location_id is missing.", "ERROR")

    if "location_id" in enabled_working.columns:
        enabled_location_ids = enabled_working["location_id"].astype(str).str.strip()
        duplicated = enabled_working[enabled_location_ids.duplicated(keep=False)]
        for idx, row in duplicated.iterrows():
            if str(row.get("location_id", "")).strip():
                _add_issue(
                    issues,
                    int(idx),
                    row.get("location_id", ""),
                    "location_id",
                    row.get("location_id", ""),
                    "Duplicate location_id among enabled sites. location_id must be unique for active dashboard rows.",
                    "WARNING",
                )

    working["_latitude_num"] = pd.to_numeric(working["latitude"], errors="coerce")
    working["_longitude_num"] = pd.to_numeric(working["longitude"], errors="coerce")
    for idx, row in working[working["_enabled_bool"] == True].iterrows():  # noqa: E712
        if pd.isna(row.get("_latitude_num")):
            _add_issue(
                issues,
                int(idx),
                row.get("location_id", ""),
                "latitude",
                row.get("latitude", ""),
                "Latitude is missing or not numeric. Enabled site cannot be displayed on the map.",
                "ERROR",
            )
        if pd.isna(row.get("_longitude_num")):
            _add_issue(
                issues,
                int(idx),
                row.get("location_id", ""),
                "longitude",
                row.get("longitude", ""),
                "Longitude is missing or not numeric. Enabled site cannot be displayed on the map.",
                "ERROR",
            )

    for idx, row in working[working["_enabled_bool"] == True].iterrows():  # noqa: E712
        tz = str(row.get("timezone", "")).strip()
        if tz:
            try:
                ZoneInfo(tz)
            except ZoneInfoNotFoundError:
                _add_issue(
                    issues,
                    int(idx),
                    row.get("location_id", ""),
                    "timezone",
                    row.get("timezone", ""),
                    "Invalid timezone. Local time will not be calculated.",
                    "WARNING",
                )
        else:
            _add_issue(
                issues,
                int(idx),
                row.get("location_id", ""),
                "timezone",
                row.get("timezone", ""),
                "Timezone is missing.",
                "INFO",
            )

    for idx, row in working[working["_enabled_bool"] == True].iterrows():  # noqa: E712
        for task in task_columns:
            parsed = parse_task_status_value(task, row.get(task, ""))
            if parsed["type"] == "invalid_progress":
                _add_issue(
                    issues,
                    int(idx),
                    row.get("location_id", ""),
                    task,
                    row.get(task, ""),
                    parsed["issue"] or "Invalid progress value.",
                    "ERROR",
                )
            elif parsed["type"] == "missing":
                _add_issue(
                    issues,
                    int(idx),
                    row.get("location_id", ""),
                    task,
                    row.get(task, ""),
                    "Task value is missing for an enabled site.",
                    "WARNING",
                )

    working["_can_display"] = working["_latitude_num"].notna() & working["_longitude_num"].notna()
    issue_df = pd.DataFrame(issues)
    if not issue_df.empty:
        counts = issue_df.groupby("location_id").size().to_dict()
    else:
        counts = {}
    working["_data_issue_count"] = working["location_id"].astype(str).map(counts).fillna(0).astype(int)
    working["_has_data_issue"] = working["_data_issue_count"] > 0
    return working, issues

def get_color_for_progress(percent: float | None) -> str:
    if percent is None or pd.isna(percent):
        return "darkgray"
    if percent >= 100:
        return "green"
    if percent >= 70:
        return "blue"
    if percent >= 30:
        return "orange"
    return "red"


def _format_number(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return f"{value:g}"


def parse_status_value(value: Any) -> dict[str, Any]:
    raw_value = value
    if value is None or pd.isna(value):
        return {
            "raw_value": raw_value,
            "type": "missing",
            "completed": None,
            "total": None,
            "percent": None,
            "display_text": "Missing",
            "color": "darkgray",
            "issue": "Missing value.",
        }

    text = str(value).strip()
    if text == "":
        return {
            "raw_value": raw_value,
            "type": "missing",
            "completed": None,
            "total": None,
            "percent": None,
            "display_text": "Missing",
            "color": "darkgray",
            "issue": "Missing value.",
        }

    if text in DASH_PLACEHOLDERS:
        return {
            "raw_value": raw_value,
            "type": "missing",
            "completed": None,
            "total": None,
            "percent": None,
            "display_text": "-",
            "color": "darkgray",
            "issue": None,
        }

    if text.lower() in NA_VALUES:
        return {
            "raw_value": raw_value,
            "type": "not_applicable",
            "completed": None,
            "total": None,
            "percent": None,
            "display_text": "N/A",
            "color": "gray",
            "issue": None,
        }

    if "_" in text:
        return {
            "raw_value": raw_value,
            "type": "string_status",
            "completed": None,
            "total": None,
            "percent": None,
            "display_text": text,
            "color": "gray",
            "issue": None,
        }

    match = PROGRESS_RE.match(text)
    if match:
        completed = float(match.group(1))
        total = float(match.group(2))
        if total <= 0:
            return {
                "raw_value": raw_value,
                "type": "invalid_progress",
                "completed": completed,
                "total": total,
                "percent": None,
                "display_text": "Invalid",
                "color": "purple",
                "issue": "Progress denominator must be greater than 0.",
            }
        if completed < 0:
            return {
                "raw_value": raw_value,
                "type": "invalid_progress",
                "completed": completed,
                "total": total,
                "percent": None,
                "display_text": "Invalid",
                "color": "purple",
                "issue": "Progress completed value cannot be negative.",
            }
        percent = completed / total * 100
        display_text = f"{_format_number(completed)}/{_format_number(total)} · {percent:.1f}%"
        return {
            "raw_value": raw_value,
            "type": "progress",
            "completed": completed,
            "total": total,
            "percent": percent,
            "display_text": display_text,
            "color": get_color_for_progress(percent),
            "issue": None,
        }

    if "/" in text:
        return {
            "raw_value": raw_value,
            "type": "invalid_progress",
            "completed": None,
            "total": None,
            "percent": None,
            "display_text": "Invalid",
            "color": "purple",
            "issue": "Progress value must use numeric completed/total format, e.g. 60/66.",
        }

    return {
        "raw_value": raw_value,
        "type": "string_status",
        "completed": None,
        "total": None,
        "percent": None,
        "display_text": text,
        "color": "gray",
        "issue": None,
    }


def parse_task_status_value(task_name: str, value: Any) -> dict[str, Any]:
    if is_note_column(task_name):
        raw_value = value
        if value is None or pd.isna(value):
            display_text = ""
        else:
            display_text = str(value).strip()
        return {
            "raw_value": raw_value,
            "type": "string_status",
            "completed": None,
            "total": None,
            "percent": None,
            "display_text": display_text,
            "color": "gray",
            "issue": None,
        }
    return parse_status_value(value)


def parse_all_task_statuses(row: pd.Series, task_columns: list[str]) -> dict[str, dict[str, Any]]:
    return {task: parse_task_status_value(task, row.get(task, "")) for task in task_columns}


def build_string_status_color_map(df: pd.DataFrame, task_columns: list[str]) -> dict[str, str]:
    values: set[str] = set()
    for task in task_columns:
        if task not in df.columns:
            continue
        for value in df[task].dropna().astype(str):
            parsed = parse_task_status_value(task, value)
            if parsed["type"] == "string_status":
                values.add(parsed["display_text"])
    color_map: dict[str, str] = {}
    for value in sorted(values):
        digest = int(hashlib.sha256(value.encode("utf-8")).hexdigest(), 16)
        color_map[value] = STRING_STATUS_PALETTE[digest % len(STRING_STATUS_PALETTE)]
    return color_map


def get_color_for_string_status(value: str, color_map: dict[str, str]) -> str:
    return color_map.get(str(value), STATUS_COLORS["gray"])


# -----------------------------------------------------------------------------
# Status calculations
# -----------------------------------------------------------------------------
def calculate_site_summary_for_selected_tasks(row: pd.Series, selected_task_columns: list[str]) -> dict[str, Any]:
    parsed_map = parse_all_task_statuses(row, selected_task_columns)
    progress_values = [p["percent"] for p in parsed_map.values() if p["type"] == "progress" and p["percent"] is not None]
    has_string = any(p["type"] == "string_status" for p in parsed_map.values())
    has_na = any(p["type"] == "not_applicable" for p in parsed_map.values())
    has_missing = any(p["type"] == "missing" for p in parsed_map.values())
    has_invalid = any(p["type"] == "invalid_progress" for p in parsed_map.values())

    min_percent = min(progress_values) if progress_values else None
    avg_percent = sum(progress_values) / len(progress_values) if progress_values else None

    if progress_values:
        if min_percent is not None and min_percent >= 100:
            status_level = "Complete"
            marker_color = "green"
        elif min_percent is not None and min_percent < 30:
            status_level = "Critical"
            marker_color = "red"
        elif min_percent is not None and min_percent < 70:
            status_level = "Warning"
            marker_color = "orange"
        else:
            status_level = "Normal"
            marker_color = "blue"
    elif has_invalid or has_missing:
        status_level = "Warning"
        marker_color = "purple" if has_invalid else "darkgray"
    elif has_string:
        status_level = "Info"
        marker_color = "gray"
    elif has_na:
        status_level = "Not Applicable"
        marker_color = "lightgray"
    else:
        status_level = "Info"
        marker_color = "gray"

    return {
        "parsed": parsed_map,
        "min_percent": min_percent,
        "avg_percent": avg_percent,
        "has_warning_indicator": has_missing or has_invalid,
        "has_missing": has_missing,
        "has_invalid": has_invalid,
        "has_string_status": has_string,
        "has_not_applicable": has_na,
        "marker_color": marker_color,
        "status_level": status_level,
    }


def get_marker_color_for_selected_tasks(row: pd.Series, selected_task_columns: list[str]) -> str:
    return calculate_site_summary_for_selected_tasks(row, selected_task_columns)["marker_color"]


def calculate_status_level(row: pd.Series, selected_task_columns: list[str]) -> str:
    return calculate_site_summary_for_selected_tasks(row, selected_task_columns)["status_level"]


def _get_site_display_name(row: pd.Series) -> str:
    name = str(row.get("location_name", "")).strip()
    if name:
        return name
    location_id = str(row.get("location_id", "")).strip()
    return location_id or "Unnamed site"


def _get_version_column_name(columns: Any) -> str | None:
    return _find_case_insensitive_column(columns, "version")


def _get_site_version(row: pd.Series) -> str:
    version_col = _get_version_column_name(row.index)
    if version_col is None:
        return "No Version"
    version = str(row.get(version_col, "")).strip()
    return version if version else "No Version"


def _version_sort_key(version: str) -> tuple[Any, ...]:
    text = str(version).strip()
    lowered = text.lower()
    match = re.match(r"^\s*[vV]?\s*(\d+(?:\.\d+)*)(.*)$", text)
    if match:
        number_part = tuple(int(part) for part in match.group(1).split("."))
        suffix = match.group(2).strip().lower()
        return (0, number_part, suffix)
    return (1, lowered)


def _sort_site_names(site_names: list[str]) -> list[str]:
    return sorted(site_names, key=lambda name: (str(name).casefold(), str(name)))


def _sort_sites_by_version(version_map: dict[str, list[str]]) -> dict[str, list[str]]:
    sorted_map: dict[str, list[str]] = {}
    for version in sorted(version_map.keys(), key=_version_sort_key):
        sorted_map[version] = _sort_site_names(version_map[version])
    return sorted_map


def get_version_filter_options(df: pd.DataFrame) -> list[str]:
    version_col = _get_version_column_name(df.columns)
    if version_col is None:
        return []

    source_df = df.copy()
    if "_enabled_bool" in source_df.columns:
        source_df = source_df[source_df["_enabled_bool"] == True]  # noqa: E712
    if "_can_display" in source_df.columns:
        source_df = source_df[source_df["_can_display"] == True]  # noqa: E712

    versions = {
        str(value).strip() if str(value).strip() else "No Version"
        for value in source_df[version_col].dropna().tolist()
    }
    return sorted(versions, key=_version_sort_key)


def is_kpi_calculation_task(task_name: str) -> bool:
    return not is_note_column(task_name) and not is_site_metadata_column(task_name)


def calculate_kpis(
    df: pd.DataFrame,
    filtered_df: pd.DataFrame,
    selected_task_columns: list[str],
    validation_issues: list[dict[str, Any]],
) -> dict[str, Any]:
    displayed_sites = len(filtered_df)
    complete_sites_by_version: dict[str, list[str]] = {}
    incomplete_sites_by_version: dict[str, list[str]] = {}

    kpi_task_columns = [task for task in selected_task_columns if is_kpi_calculation_task(task)]

    for _, row in filtered_df.iterrows():
        parsed = parse_all_task_statuses(row, kpi_task_columns)
        site_name = _get_site_display_name(row)
        version = _get_site_version(row)

        kpi_scope_parsed = {
            task: status
            for task, status in parsed.items()
            if status["type"] != "string_status"
        }

        all_kpi_scope_items_are_not_applicable = bool(kpi_scope_parsed) and all(
            status["type"] == "not_applicable" for status in kpi_scope_parsed.values()
        )
        if all_kpi_scope_items_are_not_applicable:
            complete_sites_by_version.setdefault(version, []).append(site_name)
            continue

        applicable_parsed = {
            task: status
            for task, status in kpi_scope_parsed.items()
            if status["type"] != "not_applicable"
        }

        progress_items = [p for p in applicable_parsed.values() if p["type"] == "progress"]
        applicable_tasks = list(applicable_parsed.keys())
        has_dash_placeholder = any(str(row.get(task, "")).strip() in DASH_PLACEHOLDERS for task in applicable_tasks)
        has_invalid_progress = any(p["type"] == "invalid_progress" for p in applicable_parsed.values())
        has_numeric_below_100 = any((p["percent"] or 0) < 100 for p in progress_items)
        has_all_numeric_100 = bool(progress_items) and all((p["percent"] or 0) >= 100 for p in progress_items)

        if has_all_numeric_100 and not has_dash_placeholder and not has_invalid_progress:
            complete_sites_by_version.setdefault(version, []).append(site_name)
        if has_numeric_below_100 or has_dash_placeholder or has_invalid_progress:
            incomplete_sites_by_version.setdefault(version, []).append(site_name)

    complete_sites_by_version = _sort_sites_by_version(complete_sites_by_version)
    incomplete_sites_by_version = _sort_sites_by_version(incomplete_sites_by_version)
    complete_count = sum(len(site_names) for site_names in complete_sites_by_version.values())
    incomplete_count = sum(len(site_names) for site_names in incomplete_sites_by_version.values())

    return {
        "Total Sites": {"count": displayed_sites},
        "Complete Sites": {
            "count": complete_count,
            "sites_by_version": complete_sites_by_version,
        },
        "Incomplete Sites": {
            "count": incomplete_count,
            "sites_by_version": incomplete_sites_by_version,
        },
    }


# -----------------------------------------------------------------------------
# Filtering
# -----------------------------------------------------------------------------
def filter_by_progress_threshold(df: pd.DataFrame, selected_task_columns: list[str], threshold: float | None) -> pd.DataFrame:
    if threshold is None:
        return df
    mask = []
    for _, row in df.iterrows():
        summary = calculate_site_summary_for_selected_tasks(row, selected_task_columns)
        min_percent = summary["min_percent"]
        mask.append(min_percent is not None and min_percent < threshold)
    return df[pd.Series(mask, index=df.index)]


def filter_by_status_level(df: pd.DataFrame, selected_task_columns: list[str], selected_levels: list[str]) -> pd.DataFrame:
    if not selected_levels:
        return df
    levels = df.apply(lambda row: calculate_status_level(row, selected_task_columns), axis=1)
    return df[levels.isin(selected_levels)]


def apply_filters(df: pd.DataFrame, filters: dict[str, Any], selected_task_columns: list[str]) -> pd.DataFrame:
    filtered = df.copy()

    filtered = filtered[filtered["_enabled_bool"] == True]
    filtered = filtered[filtered["_can_display"] == True]

    for field in ("country", "state", "city"):
        selected = filters.get(field, [])
        if selected:
            filtered = filtered[filtered[field].astype(str).isin(selected)]

    selected_versions = filters.get("version", [])
    if selected_versions:
        filtered = filtered[
            filtered.apply(lambda row: _get_site_version(row) in selected_versions, axis=1)
        ]

    query = str(filters.get("search", "")).strip().lower()
    if query:
        haystack = (
            filtered["location_id"].astype(str)
            + " "
            + filtered["location_name"].astype(str)
            + " "
            + filtered["city"].astype(str)
        ).str.lower()
        filtered = filtered[haystack.str.contains(re.escape(query), na=False)]

    if filters.get("data_issue_only", False):
        filtered = filtered[filtered["_has_data_issue"] == True]

    levels = filters.get("status_levels", [])
    if levels:
        filtered = filter_by_status_level(filtered, selected_task_columns, levels)

    return filtered


# -----------------------------------------------------------------------------
# HTML helpers
# -----------------------------------------------------------------------------
def _badge_html(text: str, color: str) -> str:
    safe_text = html.escape(str(text))
    color_value = STATUS_COLORS.get(color, color)
    return (
        f"<span style='display:inline-block; padding:2px 6px; border-radius:999px; "
        f"background:{html.escape(color_value)}; color:#fff; font-size:11px; line-height:1.3;'>{safe_text}</span>"
    )


def _status_badge_for_parsed(parsed: dict[str, Any], color_map: dict[str, str] | None = None) -> str:
    if parsed["type"] == "string_status" and color_map is not None:
        return _badge_html(parsed["display_text"], get_color_for_string_status(parsed["display_text"], color_map))
    return _badge_html(parsed["display_text"], parsed["color"])


def build_site_label_html(row: pd.Series, selected_task_columns: list[str], show_labels: bool = True) -> str:
    if not show_labels:
        return ""
    site_name = html.escape(str(row.get("location_name", "")))
    location_id = html.escape(str(row.get("location_id", "")))
    lines = [f"<div style='font-weight:800; margin-bottom:2px; color:#111827;'>{site_name}</div>"]
    if len(selected_task_columns) == 1:
        task = selected_task_columns[0]
        parsed = parse_task_status_value(task, row.get(task, ""))
        safe_task = html.escape(task)
        safe_display = html.escape(parsed["display_text"])
        badge_color = STATUS_COLORS.get(parsed["color"], STATUS_COLORS["gray"])
        lines.append(
            "<div style='margin-top:2px; color:#111827;'>"
            f"<span>{safe_task}: </span>"
            f"<span class='site-label-badge' style='background:{badge_color}; color:#ffffff !important; font-weight:800; text-shadow:0 1px 2px rgba(0,0,0,0.45);'>{safe_display}</span>"
            "</div>"
        )
    return f"""
    <div data-location-id="{location_id}" style="
        background:rgba(255,255,255,0.92);
        border:1px solid rgba(0,0,0,0.18);
        border-radius:8px;
        padding:5px 7px;
        box-shadow:0 1px 5px rgba(0,0,0,0.25);
        font-family:Arial, sans-serif;
        font-size:11px;
        color:#111;
        min-width:110px;
        max-width:240px;
        white-space:normal;
    ">
        {''.join(lines)}
    </div>
    """


def build_tooltip_text(row: pd.Series, selected_task_columns: list[str]) -> str:
    return str(row.get("location_name", ""))


def build_popup_html(
    row: pd.Series,
    task_columns: list[str],
    selected_task_columns: list[str] | None = None,
    show_all_tasks: bool = False,
) -> str:
    selected = task_columns if selected_task_columns is None else selected_task_columns
    site_name = html.escape(str(row.get("location_name", "")))
    city_state = html.escape(f"{row.get('city', '')}, {row.get('state', '')}".strip(", "))

    rows = []
    for task in selected:
        parsed = parse_task_status_value(task, row.get(task, ""))
        rows.append(
            "<tr>"
            f"<td style='padding:4px 7px; font-weight:600; border-bottom:1px solid #eef2f7;'>{html.escape(task)}</td>"
            f"<td style='padding:4px 7px; border-bottom:1px solid #eef2f7;'>{html.escape(parsed['display_text'])}</td>"
            "</tr>"
        )

    if show_all_tasks:
        remaining = [task for task in task_columns if task not in selected]
        if remaining:
            rows.append("<tr><td colspan='2' style='padding:7px; color:#4b5563; border-top:1px solid #d1d5db; font-weight:700;'>Other tasks</td></tr>")
        for task in remaining:
            parsed = parse_task_status_value(task, row.get(task, ""))
            rows.append(
                "<tr>"
                f"<td style='padding:4px 7px; border-bottom:1px solid #eef2f7;'>{html.escape(task)}</td>"
                f"<td style='padding:4px 7px; border-bottom:1px solid #eef2f7;'>{html.escape(parsed['display_text'])}</td>"
                "</tr>"
            )

    if not rows:
        rows.append("<tr><td colspan='2' style='padding:7px; color:#6b7280;'>No work item selected.</td></tr>")

    warning = ""
    summary = calculate_site_summary_for_selected_tasks(row, selected)
    if summary["has_warning_indicator"]:
        warning = "<div style='margin-top:7px; color:#92400e; font-size:12px; font-weight:700;'>⚠ Data issue exists for selected tasks.</div>"

    return f"""
    <div style="font-family:Arial, sans-serif; width:320px; color:#111827;">
      <div style="font-size:15px; font-weight:800; margin-bottom:2px; color:#000000;">{site_name}</div>
      <div style="font-size:12px; color:#374151; margin-bottom:7px;">{city_state}</div>
      <table style="border-collapse:collapse; width:100%; font-size:12px; color:#111827;">
        <thead>
          <tr style="background:#f3f4f6;"><th align="left" style="padding:4px 7px;">Task</th><th align="left" style="padding:4px 7px;">Status</th></tr>
        </thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
      {warning}
    </div>
    """


# -----------------------------------------------------------------------------
# Map rendering
# -----------------------------------------------------------------------------
def add_legend_to_map(map_obj: folium.Map) -> None:
    legend_html = """
    <div style="
        position: fixed;
        bottom: 30px;
        left: 30px;
        z-index: 9999;
        background: #ffffff;
        color: #111827;
        border: 1px solid #9ca3af;
        border-radius: 8px;
        padding: 12px 14px;
        font-size: 13px;
        line-height: 1.55;
        font-weight: 600;
        box-shadow: 0 2px 10px rgba(0,0,0,0.25);
    ">
      <div style="font-weight:800; font-size:14px; margin-bottom:7px; color:#000000;">Status Legend</div>
      <div><span style="background:#2e7d32;width:11px;height:11px;display:inline-block;border-radius:50%;margin-right:6px;"></span>Complete / 100%</div>
      <div><span style="background:#1976d2;width:11px;height:11px;display:inline-block;border-radius:50%;margin-right:6px;"></span>70–99.9%</div>
      <div><span style="background:#ef6c00;width:11px;height:11px;display:inline-block;border-radius:50%;margin-right:6px;"></span>30–69.9%</div>
      <div><span style="background:#c62828;width:11px;height:11px;display:inline-block;border-radius:50%;margin-right:6px;"></span>Below 30%</div>
      <div><span style="background:#757575;width:11px;height:11px;display:inline-block;border-radius:50%;margin-right:6px;"></span>String status / Info</div>
      <div><span style="background:#bdbdbd;width:11px;height:11px;display:inline-block;border-radius:50%;margin-right:6px;"></span>N/A</div>
      <div><span style="background:#6a1b9a;width:11px;height:11px;display:inline-block;border-radius:50%;margin-right:6px;"></span>Invalid / Data issue</div>
    </div>
    """
    map_obj.get_root().html.add_child(folium.Element(legend_html))



def build_site_marker_icon_html(row: pd.Series, selected_task_columns: list[str], color: str) -> str:
    label_html = build_site_label_html(row, selected_task_columns, show_labels=True)
    safe_color = html.escape(str(color))
    return f"""
    <div style="width:240px; text-align:center; pointer-events:auto;">
        <div style="width:16px; height:16px; margin:0 auto 4px auto; border-radius:50%; border:2px solid #111827; box-shadow:0 1px 5px rgba(0,0,0,0.35); background:{safe_color};"></div>
        <div style="display:flex; justify-content:center;">{label_html}</div>
    </div>
    """

def create_folium_map(
    df: pd.DataFrame,
    task_columns: list[str],
    selected_task_columns: list[str],
    filters: dict[str, Any],
    options: dict[str, Any],
) -> folium.Map:
    if df.empty:
        return folium.Map(location=[39.5, -98.35], zoom_start=4, tiles="CartoDB positron")

    bounds_df = df[["_latitude_num", "_longitude_num"]].dropna()
    center_lat = float(bounds_df["_latitude_num"].mean())
    center_lon = float(bounds_df["_longitude_num"].mean())
    initial_zoom = 10 if len(bounds_df) == 1 else 6
    map_obj = folium.Map(location=[center_lat, center_lon], zoom_start=initial_zoom, tiles="CartoDB positron", control_scale=True)

    if len(bounds_df) >= 2:
        map_obj.fit_bounds(
            bounds_df[["_latitude_num", "_longitude_num"]].values.tolist(),
            padding=(35, 35),
        )

    use_cluster = bool(options.get("use_marker_cluster", True))
    show_all_tasks = bool(options.get("show_all_tasks_in_popup", True))

    marker_parent: Any = MarkerCluster(name="Sites").add_to(map_obj) if use_cluster else map_obj

    for _, row in df.iterrows():
        lat = float(row["_latitude_num"])
        lon = float(row["_longitude_num"])
        color_key = get_marker_color_for_selected_tasks(row, selected_task_columns)
        color = STATUS_COLORS.get(color_key, STATUS_COLORS["gray"])
        tooltip = build_tooltip_text(row, selected_task_columns)
        popup_html = build_popup_html(row, task_columns, selected_task_columns, show_all_tasks=show_all_tasks)
        popup = folium.Popup(popup_html, max_width=380)

        icon_html = build_site_marker_icon_html(row, selected_task_columns, color)
        icon_height = 76 if len(selected_task_columns) == 1 else 56
        folium.Marker(
            location=[lat, lon],
            tooltip=tooltip,
            popup=popup,
            icon=folium.DivIcon(
                icon_size=(240, icon_height),
                icon_anchor=(120, 10),
                html=icon_html,
            ),
        ).add_to(marker_parent)

    add_legend_to_map(map_obj)
    return map_obj


def _find_nearest_site_by_click(df: pd.DataFrame, clicked: dict[str, Any] | None) -> str | None:
    if not clicked or df.empty:
        return None
    click_lat = clicked.get("lat")
    click_lng = clicked.get("lng")
    if click_lat is None or click_lng is None:
        return None
    distances = []
    for idx, row in df.iterrows():
        try:
            d = (float(row["_latitude_num"]) - float(click_lat)) ** 2 + (float(row["_longitude_num"]) - float(click_lng)) ** 2
            distances.append((d, idx))
        except Exception:
            continue
    if not distances:
        return None
    _, nearest_idx = min(distances, key=lambda item: item[0])
    return str(df.loc[nearest_idx, "location_id"])


def render_map(
    df: pd.DataFrame,
    task_columns: list[str],
    selected_task_columns: list[str],
    filters: dict[str, Any],
    options: dict[str, Any],
) -> None:
    if df.empty:
        st.info("No sites to display.")
        return
    map_obj = create_folium_map(df, task_columns, selected_task_columns, filters, options)
    map_key_material = "|".join(
        f"{row.get('location_id', '')}:{row.get('_latitude_num', '')}:{row.get('_longitude_num', '')}"
        for _, row in df.iterrows()
    )
    map_key = "site_status_map_" + hashlib.sha1(map_key_material.encode("utf-8")).hexdigest()[:12]
    map_data = st_folium(map_obj, width=None, height=680, returned_objects=["last_object_clicked"], key=map_key)
    clicked_site_id = _find_nearest_site_by_click(df, map_data.get("last_object_clicked") if map_data else None)
    if clicked_site_id:
        st.session_state.selected_site_id = clicked_site_id


# -----------------------------------------------------------------------------
# UI rendering
# -----------------------------------------------------------------------------
def render_floating_task_selector_css() -> None:
    st.markdown(
        """
        <style>
        .block-container { padding-top: 1.4rem; }
        div[data-testid="stMetric"] {
            background: #ffffff !important;
            border: 1px solid #9ca3af !important;
            padding: 0.9rem 1rem !important;
            border-radius: 0.75rem !important;
            box-shadow: 0 1px 5px rgba(0,0,0,0.12) !important;
        }
        div[data-testid="stMetric"] label,
        div[data-testid="stMetric"] label p,
        div[data-testid="stMetricLabel"],
        div[data-testid="stMetricLabel"] p {
            color: #111827 !important;
            opacity: 1 !important;
            font-weight: 700 !important;
        }
        div[data-testid="stMetricValue"],
        div[data-testid="stMetricValue"] div,
        div[data-testid="stMetricValue"] p {
            color: #000000 !important;
            opacity: 1 !important;
            font-size: 1.75rem !important;
            font-weight: 800 !important;
            line-height: 1.05 !important;
        }
        .kpi-card-row {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 1rem;
            align-items: stretch;
            margin-bottom: 0.75rem;
        }
        .kpi-card {
            background: #ffffff;
            border: 1px solid #9ca3af;
            border-radius: 0.85rem;
            padding: 0.9rem 1rem;
            box-shadow: 0 1px 5px rgba(0,0,0,0.12);
            min-height: 6.2rem;
            height: auto;
            display: flex;
            flex-direction: column;
            gap: 0.55rem;
            overflow: visible;
        }
        @media (max-width: 900px) {
            .kpi-card-row {
                grid-template-columns: 1fr;
            }
        }
        .kpi-card-main {
            display: flex;
            align-items: baseline;
            justify-content: space-between;
            gap: 0.8rem;
            flex: 0 0 auto;
        }
        .kpi-card-title {
            color: #111827;
            font-size: 0.92rem;
            font-weight: 800;
            line-height: 1.2;
        }
        .kpi-card-value {
            color: #000000;
            font-size: 2.5rem;
            font-weight: 900;
            line-height: 1.05;
            text-align: right;
            min-width: 2.5rem;
        }
        .kpi-site-list {
            display: flex;
            flex-direction: column;
            align-content: flex-start;
            align-items: stretch;
            gap: 0;
            overflow: visible;
            padding: 0.1rem 0 0 0;
            flex: 1 1 auto;
        }
        .kpi-site-pill {
            display: inline-block;
            max-width: 100%;
            white-space: normal;
            word-break: break-word;
            background: #f3f4f6;
            border: 1px solid #d1d5db;
            border-radius: 999px;
            color: #111827;
            font-size: 0.74rem;
            font-weight: 700;
            padding: 0.14rem 0.45rem;
            line-height: 1.22;
        }
        .kpi-empty-sites {
            color: #6b7280;
            font-size: 0.82rem;
            font-weight: 700;
        }
        .kpi-version-group {
            width: 100%;
            background: transparent;
            padding: 0.42rem 0 0.52rem 0;
        }
        .kpi-version-group + .kpi-version-group {
            border-top: 1px solid #cbd5e1;
            margin-top: 0.28rem;
            padding-top: 0.72rem;
        }
        .kpi-version-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 0.5rem;
            color: #111827;
            font-size: 0.80rem;
            font-weight: 900;
            margin-bottom: 0.36rem;
            line-height: 1.2;
        }
        .kpi-version-label {
            display: inline-flex;
            align-items: center;
            gap: 0.25rem;
            color: #111827;
            font-weight: 900;
        }
        .kpi-version-label-prefix {
            color: #4b5563;
            font-size: 0.72rem;
            font-weight: 800;
            text-transform: uppercase;
            letter-spacing: 0.03em;
        }
        .kpi-version-count {
            color: #4b5563;
            font-size: 0.72rem;
            font-weight: 800;
            white-space: nowrap;
        }
        .kpi-version-sites {
            display: flex;
            flex-wrap: wrap;
            align-items: flex-start;
            gap: 0.3rem;
        }
        .map-control-panel {
            background: rgba(255,255,255,0.96);
            border: 1px solid #e5e7eb;
            border-radius: 0.85rem;
            padding: 0.8rem 0.9rem;
            box-shadow: 0 2px 10px rgba(0,0,0,0.08);
            max-height: 680px;
            overflow-y: auto;
        }
        .site-marker-wrap {
            width: 240px;
            text-align: center;
            transform: translateX(0);
            pointer-events: auto;
        }
        .site-marker-dot {
            width: 16px;
            height: 16px;
            margin: 0 auto 4px auto;
            border-radius: 50%;
            border: 2px solid #111827;
            box-shadow: 0 1px 5px rgba(0,0,0,0.35);
        }
        .site-marker-label-wrap {
            display: flex;
            justify-content: center;
        }
        .site-label-name { font-weight: 800; margin-bottom: 2px; color: #111827; }
        .site-label-task { margin-top: 2px; color: #111827; }
        .site-label-badge { color: #fff; border-radius: 999px; padding: 1px 5px; font-size: 10px; }
        [data-testid="stSidebar"] div.stButton > button {
            min-height: 2.6rem !important;
            height: 2.6rem !important;
            padding: 0.25rem 0.35rem !important;
            font-size: 0.78rem !important;
            line-height: 1.05 !important;
            white-space: nowrap !important;
        }
        .detail-card {
            border: 1px solid #e5e7eb;
            border-radius: 0.75rem;
            padding: 0.85rem 1rem;
            background: #fff;
            margin-bottom: 0.5rem;
        }
        .dashboard-meta-row {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            align-items: stretch;
            gap: 0.75rem;
            margin: 0.35rem 0 0.95rem 0;
            width: 100%;
        }
        .dashboard-meta-item {
            min-height: 2.35rem;
            display: flex;
            align-items: center;
            color: var(--text-color, inherit);
            font-size: 0.94rem;
            font-weight: 700;
            line-height: 1.25;
            min-width: 0;
            white-space: normal;
            overflow: visible;
            text-overflow: clip;
            word-break: break-word;
        }
        .dashboard-meta-item span {
            color: inherit;
        }
        .dashboard-meta-left {
            justify-content: flex-start;
            text-align: left;
        }
        .dashboard-meta-center {
            justify-content: center;
            text-align: center;
        }
        .dashboard-meta-right {
            justify-content: flex-end;
            text-align: right;
        }
        .dashboard-meta-label {
            font-weight: 800;
            margin-right: 0.25rem;
            flex: 0 0 auto;
        }
        .dashboard-meta-code {
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
            color: inherit;
            background: rgba(128, 128, 128, 0.14);
            border: 1px solid rgba(128, 128, 128, 0.35);
            border-radius: 0.35rem;
            padding: 0.08rem 0.32rem;
            min-width: 0;
            max-width: 100%;
            overflow-wrap: anywhere;
            word-break: break-word;
            white-space: normal;
        }
        @media (max-width: 1050px) {
            .dashboard-meta-row {
                grid-template-columns: repeat(2, minmax(0, 1fr));
                gap: 0.45rem 0.75rem;
            }
            .dashboard-meta-item,
            .dashboard-meta-left,
            .dashboard-meta-center,
            .dashboard-meta-right {
                justify-content: flex-start;
                text-align: left;
            }
        }
        @media (max-width: 620px) {
            .dashboard-meta-row {
                grid-template-columns: 1fr;
                gap: 0.35rem;
            }
            .dashboard-meta-item {
                min-height: 2.0rem;
                align-items: flex-start;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _init_task_state(task_columns: list[str]) -> None:
    current_tasks = list(task_columns)
    if "task_columns_signature" not in st.session_state:
        st.session_state.task_columns_signature = ""
    signature = "|".join(current_tasks)
    if st.session_state.task_columns_signature != signature:
        st.session_state.task_columns_signature = signature
        st.session_state.selected_task_columns = current_tasks.copy()
        st.session_state.last_valid_selected_task_columns = current_tasks.copy()
        for task in current_tasks:
            st.session_state[f"task_checkbox__{task}"] = True
    if "selected_task_columns" not in st.session_state:
        st.session_state.selected_task_columns = current_tasks.copy()
    if "last_valid_selected_task_columns" not in st.session_state:
        st.session_state.last_valid_selected_task_columns = current_tasks.copy()
    if "selected_site_id" not in st.session_state:
        st.session_state.selected_site_id = None
    st.session_state["show_site_labels"] = True
    st.session_state["show_all_tasks_in_popup"] = True
    st.session_state["use_marker_cluster"] = True


def get_selected_task_columns(task_columns: list[str]) -> list[str]:
    selected = [
        task
        for task in task_columns
        if st.session_state.get(f"task_checkbox__{task}", task in st.session_state.selected_task_columns)
    ]
    if selected:
        st.session_state.last_valid_selected_task_columns = selected.copy()
    st.session_state.selected_task_columns = selected.copy()
    return selected


def render_task_selector(task_columns: list[str]) -> list[str]:
    _init_task_state(task_columns)
    st.sidebar.subheader("작업 항목 선택")

    c1, c2, c3 = st.sidebar.columns(3)
    with c1:
        if st.button("Select All", use_container_width=True):
            for task in task_columns:
                st.session_state[f"task_checkbox__{task}"] = True
    with c2:
        if st.button("Clear All", use_container_width=True):
            for task in task_columns:
                st.session_state[f"task_checkbox__{task}"] = False
    with c3:
        if st.button("Reset", use_container_width=True):
            for task in task_columns:
                st.session_state[f"task_checkbox__{task}"] = True

    if not task_columns:
        st.sidebar.info("No visible work items. Edit task_config.csv to set at least one task visible=Y.")
    else:
        with st.sidebar.container():
            for task in task_columns:
                st.checkbox(task, key=f"task_checkbox__{task}")

    selected = get_selected_task_columns(task_columns)
    st.sidebar.caption(f"Selected: {len(selected)} / {len(task_columns)}")
    st.sidebar.divider()
    return selected


def render_selected_task_summary(selected_task_columns: list[str], task_columns: list[str]) -> None:
    if len(selected_task_columns) == 0:
        st.info(
            f"Selected: 0 / {len(task_columns)} · No work item is selected. Markers use neutral info status; popups still show all tasks."
        )
    elif len(selected_task_columns) == 1:
        st.info(
            f"Selected: 1 / {len(task_columns)} · Map labels show site name plus `{selected_task_columns[0]}` status directly when clustering is off."
        )
    else:
        st.info(
            f"Selected: {len(selected_task_columns)} / {len(task_columns)} · Map labels show site names only when clustering is off. Popup/detail panel shows task details."
        )


def get_uploaded_file_from_state() -> Any | None:
    return st.session_state.get("uploaded_site_status_csv")


def get_uploaded_task_config_from_state() -> Any | None:
    return st.session_state.get("uploaded_task_config_csv")


def render_sidebar_upload_bottom(source_name: str, task_config_source_name: str) -> tuple[Any | None, Any | None]:
    st.sidebar.divider()
    st.sidebar.subheader("CSV")
    uploaded_file = st.sidebar.file_uploader("Upload site status CSV", type=["csv"], key="uploaded_site_status_csv")
    st.sidebar.download_button(
        "Download sample site status CSV",
        data=create_sample_csv(),
        file_name="sample_site_status.csv",
        mime="text/csv",
        use_container_width=True,
    )
    st.sidebar.caption(f"Current site status file: {source_name}")

    st.sidebar.divider()
    st.sidebar.subheader("Task Config")
    uploaded_task_config = st.sidebar.file_uploader("Upload task_config CSV", type=["csv"], key="uploaded_task_config_csv")
    st.sidebar.download_button(
        "Download sample task_config CSV",
        data=create_sample_task_config_csv(),
        file_name="task_config.csv",
        mime="text/csv",
        use_container_width=True,
    )
    st.sidebar.caption(f"Current task config file: {task_config_source_name}")
    return uploaded_file, uploaded_task_config


def render_task_config_summary(all_task_columns: list[str], visible_task_columns: list[str], task_config_meta: dict[str, Any]) -> None:
    hidden_tasks = list(task_config_meta.get("hidden_tasks", []))
    st.sidebar.caption(f"Visible tasks: {len(visible_task_columns)} / {len(all_task_columns)}")
    if hidden_tasks:
        preview = ", ".join(str(task) for task in hidden_tasks[:6])
        if len(hidden_tasks) > 6:
            preview += f", +{len(hidden_tasks) - 6} more"
        st.sidebar.caption(f"Hidden by task_config: {preview}")


def render_sidebar_filters(df: pd.DataFrame, task_columns: list[str]) -> dict[str, Any]:
    st.sidebar.header("Filters")
    if st.sidebar.button("Reset filters", use_container_width=True):
        keys_to_clear = [
            "filter_country",
            "filter_state",
            "filter_city",
            "filter_version",
            "filter_search",
            "filter_status_levels",
            "filter_data_issue_only",
        ]
        for key in keys_to_clear:
            st.session_state.pop(key, None)
        st.rerun()

    def unique_options(column: str) -> list[str]:
        if column not in df.columns:
            return []
        return sorted([x for x in df[column].dropna().astype(str).unique().tolist() if x.strip()])

    country = st.sidebar.multiselect("Country", unique_options("country"), key="filter_country")
    state = st.sidebar.multiselect("State", unique_options("state"), key="filter_state")
    city = st.sidebar.multiselect("City", unique_options("city"), key="filter_city")
    version_options = get_version_filter_options(df)
    version = st.sidebar.multiselect("Version", version_options, key="filter_version") if version_options else []
    search = st.sidebar.text_input("Search location_id / location_name / city", key="filter_search")

    status_levels = st.sidebar.multiselect(
        "Status level",
        ["Critical", "Warning", "Normal", "Complete", "Info", "Not Applicable"],
        key="filter_status_levels",
    )
    data_issue_only = st.sidebar.checkbox("Only sites with data issues", key="filter_data_issue_only")

    return {
        "country": country,
        "state": state,
        "city": city,
        "version": version,
        "search": search,
        "status_levels": status_levels,
        "data_issue_only": data_issue_only,
    }


def render_safe_html(html_content: str) -> None:
    if hasattr(st, "html"):
        st.html(html_content)
    else:
        st.markdown(html_content, unsafe_allow_html=True)


def render_dashboard_meta_header(source_name: str, updated_date: str, total_sites: int) -> None:
    """Render the dashboard meta header in four equal-width areas."""
    safe_source_name = html.escape(str(source_name))
    safe_updated_date = html.escape(str(updated_date))
    safe_total_sites = html.escape(str(total_sites))
    render_safe_html(
        f"""
        <div class='dashboard-meta-row'>
            <div class='dashboard-meta-item dashboard-meta-left'>
                <span class='dashboard-meta-label'>Developer:</span>
                <span>Byeonghun Kim, {dashboard_ver}</span>
            </div>
            <div class='dashboard-meta-item dashboard-meta-center'>
                <span class='dashboard-meta-label'>Uploaded file:</span>
                <span class='dashboard-meta-code'>{safe_source_name}</span>
            </div>
            <div class='dashboard-meta-item dashboard-meta-center'>
                <span class='dashboard-meta-label'>Updated Date:</span>
                <span class='dashboard-meta-code'>{safe_updated_date}</span>
            </div>
            <div class='dashboard-meta-item dashboard-meta-right'>
                <span class='dashboard-meta-label'>Total sites:</span>
                <span>{safe_total_sites}</span>
            </div>
        </div>
        """
    )


def _kpi_card_html(
    title: str,
    count: Any,
    sites_by_version: dict[str, list[str]] | None = None,
) -> str:
    safe_title = html.escape(str(title))
    safe_count = html.escape(str(count))
    site_list_html = ""

    if sites_by_version is not None:
        if sites_by_version:
            version_groups: list[str] = []
            for version, site_names in sites_by_version.items():
                safe_version = html.escape(str(version))
                safe_version_count = html.escape(str(len(site_names)))
                pills = "".join(
                    f"<span class='kpi-site-pill'>{html.escape(str(name))}</span>"
                    for name in site_names
                )
                version_groups.append(
                    "<div class='kpi-version-group'>"
                    "<div class='kpi-version-header'>"
                    "<span class='kpi-version-label'>"
                    "<span class='kpi-version-label-prefix'>Version</span>"
                    f"<span>{safe_version}</span>"
                    "</span>"
                    f"<span class='kpi-version-count'>{safe_version_count} site(s)</span>"
                    "</div>"
                    f"<div class='kpi-version-sites'>{pills}</div>"
                    "</div>"
                )
            site_list_html = f"<div class='kpi-site-list'>{''.join(version_groups)}</div>"
        else:
            site_list_html = "<div class='kpi-site-list kpi-empty-sites'>No sites</div>"

    return f"""
    <div class='kpi-card'>
        <div class='kpi-card-main'>
            <div class='kpi-card-title'>{safe_title}</div>
            <div class='kpi-card-value'>{safe_count}</div>
        </div>
        {site_list_html}
    </div>
    """


def _kpi_count(kpis: dict[str, Any], label: str) -> Any:
    value = kpis.get(label, {"count": 0})
    if isinstance(value, dict):
        return value.get("count", 0)
    return value


def _kpi_sites_by_version(kpis: dict[str, Any], label: str) -> dict[str, list[str]]:
    value = kpis.get(label, {})
    if isinstance(value, dict):
        grouped = value.get("sites_by_version", {})
        if isinstance(grouped, dict):
            return {str(version): list(site_names) for version, site_names in grouped.items()}
    return {}


def render_kpi_cards(kpis: dict[str, Any]) -> None:
    cards_html = "".join(
        [
            _kpi_card_html("Total Sites", _kpi_count(kpis, "Total Sites")),
            _kpi_card_html(
                "Complete Sites",
                _kpi_count(kpis, "Complete Sites"),
                _kpi_sites_by_version(kpis, "Complete Sites"),
            ),
            _kpi_card_html(
                "Incomplete Sites",
                _kpi_count(kpis, "Incomplete Sites"),
                _kpi_sites_by_version(kpis, "Incomplete Sites"),
            ),
        ]
    )
    render_safe_html(f"<div class='kpi-card-row'>{cards_html}</div>")


def _render_task_detail_row(task: str, parsed: dict[str, Any]) -> None:
    with st.container(border=True):
        cols = st.columns([2.3, 1.1, 1.1, 1.1, 2.2])
        cols[0].markdown(f"**{task}**")
        cols[1].write(str(parsed["raw_value"]))
        cols[2].write(parsed["type"])
        if parsed["percent"] is not None:
            cols[3].write(f"{parsed['percent']:.1f}%")
        else:
            cols[3].write("—")
        cols[4].write(parsed["display_text"])
        if parsed["type"] == "progress" and parsed["percent"] is not None:
            st.progress(min(max(float(parsed["percent"]) / 100, 0), 1), text=parsed["display_text"])
        elif parsed["issue"]:
            st.warning(parsed["issue"])


def render_selected_site_detail(selected_site: pd.Series | None, task_columns: list[str], selected_task_columns: list[str]) -> None:
    st.subheader("Selected Site Detail")
    if selected_site is None:
        st.info("Click a marker or site label on the map to view site details.")
        return

    site = selected_site
    title = f"{site.get('location_name', '')} ({site.get('location_id', '')})"
    st.markdown(f"### {html.escape(str(title))}")
    info_cols = st.columns(4)
    info_cols[0].metric("Country", site.get("country", ""))
    info_cols[1].metric("State", site.get("state", ""))
    info_cols[2].metric("City", site.get("city", ""))
    tz = str(site.get("timezone", "")).strip()
    local_time = "—"
    if tz:
        try:
            local_time = datetime.now(ZoneInfo(tz)).strftime("%m-%d %H:%M")
        except ZoneInfoNotFoundError:
            local_time = "Invalid timezone"
    info_cols[3].metric("Local Time", local_time)

    st.markdown("#### Selected Work Items")
    for task in selected_task_columns:
        _render_task_detail_row(task, parse_task_status_value(task, site.get(task, "")))


def _to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8-sig")


def render_data_table(filtered_df: pd.DataFrame, selected_task_columns: list[str]) -> pd.DataFrame:
    st.subheader("Data Table")
    table = filtered_df.copy()
    if table.empty:
        st.info("No rows match the current filters.")
        return table

    table["calculated_status_level"] = table.apply(lambda row: calculate_status_level(row, selected_task_columns), axis=1)
    table["min_selected_progress_percent"] = table.apply(
        lambda row: calculate_site_summary_for_selected_tasks(row, selected_task_columns)["min_percent"], axis=1
    )
    for task in selected_task_columns:
        table[f"{task}__display"] = table[task].apply(lambda value, task=task: parse_task_status_value(task, value)["display_text"])
        if len(selected_task_columns) == 1:
            table[f"{task}__percent"] = table[task].apply(lambda value, task=task: parse_task_status_value(task, value)["percent"])

    base_cols = ["location_id", "location_name", "country", "state", "city", "enabled"]
    selected_display_cols = []
    for task in selected_task_columns:
        selected_display_cols.append(task)
        selected_display_cols.append(f"{task}__display")
        if f"{task}__percent" in table.columns:
            selected_display_cols.append(f"{task}__percent")
    display_cols = [c for c in base_cols + selected_display_cols + ["calculated_status_level", "min_selected_progress_percent"] if c in table.columns]
    st.dataframe(table[display_cols], use_container_width=True, hide_index=True)

    return table[display_cols]


def render_data_quality_report(validation_issues: list[dict[str, Any]]) -> pd.DataFrame:
    st.subheader("Data Quality Report")
    issue_df = pd.DataFrame(validation_issues)
    if issue_df.empty:
        st.success("No data quality issues found.")
        return issue_df
    severity_order = {"ERROR": 0, "WARNING": 1, "INFO": 2}
    issue_df["_severity_order"] = issue_df["severity"].map(severity_order).fillna(9)
    issue_df = issue_df.sort_values(["_severity_order", "row_index", "column"]).drop(columns=["_severity_order"])
    st.dataframe(issue_df, use_container_width=True, hide_index=True)
    return issue_df


def render_download_buttons(filtered_table: pd.DataFrame, issue_df: pd.DataFrame) -> None:
    st.subheader("Export")
    col1, col2, col3 = st.columns(3)
    col1.download_button(
        "Download filtered site status CSV",
        data=_to_csv_bytes(filtered_table),
        file_name="filtered_site_status.csv",
        mime="text/csv",
        use_container_width=True,
        disabled=filtered_table.empty,
    )
    col2.download_button(
        "Download data quality issue CSV",
        data=_to_csv_bytes(issue_df),
        file_name="data_quality_issues.csv",
        mime="text/csv",
        use_container_width=True,
        disabled=issue_df.empty,
    )
    col3.download_button(
        "Download sample CSV template",
        data=create_sample_csv(),
        file_name="sample_site_status.csv",
        mime="text/csv",
        use_container_width=True,
    )


# -----------------------------------------------------------------------------
# Main app
# -----------------------------------------------------------------------------
def main() -> None:
    render_floating_task_selector_css()
    st.title("Site Work Status Map Dashboard")

    uploaded_file = get_uploaded_file_from_state()
    uploaded_task_config = get_uploaded_task_config_from_state()
    try:
        raw_df = load_csv(uploaded_file)
        task_config_df = load_task_config(uploaded_task_config)
    except Exception as exc:
        st.error(str(exc))
        st.stop()

    source_name = uploaded_file.name if uploaded_file is not None else DEFAULT_SITE_STATUS_FILENAME
    bundled_task_config_exists = get_default_task_config_csv() is not None
    task_config_source_name = (
        uploaded_task_config.name
        if uploaded_task_config is not None
        else (DEFAULT_TASK_CONFIG_FILENAME if bundled_task_config_exists else "Not loaded")
    )

    all_task_columns = get_task_columns(raw_df)
    task_columns, task_config_issues, task_config_meta = apply_task_config_to_task_columns(all_task_columns, task_config_df)
    validated_df, validation_issues = validate_dataframe(
        raw_df,
        task_columns_to_validate=task_columns,
        require_task_columns=not bool(all_task_columns),
    )
    validation_issues = validation_issues + task_config_issues

    if not all_task_columns:
        st.error("No task columns found after the enabled column. Add at least one work item column.")
        render_sidebar_upload_bottom(source_name, task_config_source_name)
        issue_df = render_data_quality_report(validation_issues)
        render_download_buttons(pd.DataFrame(), issue_df)
        st.stop()

    if not task_columns:
        st.warning("All work items are hidden by task_config.csv. The dashboard will show site/map context only until at least one task is set visible=Y.")

    selected_task_columns = render_task_selector(task_columns)
    render_task_config_summary(all_task_columns, task_columns, task_config_meta)
    filters = render_sidebar_filters(validated_df, task_columns)
    render_sidebar_upload_bottom(source_name, task_config_source_name)

    options = {
        "show_site_labels": True,
        "show_all_tasks_in_popup": True,
        "use_marker_cluster": True,
    }

    filtered_df = apply_filters(validated_df, filters, selected_task_columns)
    kpis = calculate_kpis(validated_df, filtered_df, selected_task_columns, validation_issues)

    updated_date_display = get_updated_date_display(validated_df)
    render_dashboard_meta_header(source_name, updated_date_display, len(filtered_df))
    render_kpi_cards(kpis)

    st.divider()
    st.subheader("Map")
    render_map(filtered_df, task_columns, selected_task_columns, filters, options)

    selected_site = None
    selected_site_id = st.session_state.get("selected_site_id")
    if selected_site_id and not filtered_df.empty:
        matched = filtered_df[filtered_df["location_id"].astype(str) == str(selected_site_id)]
        if not matched.empty:
            selected_site = matched.iloc[0]

    st.divider()
    render_selected_site_detail(selected_site, task_columns, selected_task_columns)

    st.divider()
    filtered_table = render_data_table(filtered_df, selected_task_columns)

    st.divider()
    issue_df = render_data_quality_report(validation_issues)
    render_download_buttons(filtered_table, issue_df)


if __name__ == "__main__":
    main()
