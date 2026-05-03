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

SAMPLE_CSV = """location_id,location_name,country,state,city,latitude,longitude,timezone,enabled,나비볼밸브,솔밸브 오링,워터펌프 누수점검,Chiller F/W Version,HVAC F/W Version
FL001,BLACKWATER RIVER,US,FL,Milton,30.64915185,-86.94593818,America/Chicago,Y,60/66,N/A,10/66,3.0.0.0,3.0.0.1
FL002,CANOE,US,FL,Holt,30.68096031,-86.79231311,America/Chicago,Y,20/183,183/183,183/183,3.0.0.2,3.0.0.6
FL003,SAMPLE DISABLED,US,TX,Dallas,32.7767,-96.7970,America/Chicago,N,5/10,NA,,Pending,Completed
"""


# -----------------------------------------------------------------------------
# CSV / data processing
# -----------------------------------------------------------------------------
def get_required_columns() -> list[str]:
    return REQUIRED_COLUMNS.copy()


def create_sample_csv() -> bytes:
    return SAMPLE_CSV.encode("utf-8-sig")


@st.cache_data(show_spinner=False)
def _load_csv_bytes(file_bytes: bytes, source_name: str) -> pd.DataFrame:
    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "utf-8", "cp949"):
        try:
            return pd.read_csv(io.BytesIO(file_bytes), encoding=encoding, dtype=str, keep_default_na=False)
        except UnicodeDecodeError as exc:
            last_error = exc
        except Exception as exc:
            raise ValueError(f"CSV parsing failed for {source_name}: {exc}") from exc
    raise ValueError(f"CSV encoding failed for {source_name}. Tried utf-8-sig, utf-8, cp949. Last error: {last_error}")


def get_default_site_status_csv() -> bytes:
    """Return the bundled default CSV bytes.

    Streamlit's file_uploader cannot be pre-populated with a local file, so the
    app treats site_status.csv as the default data source until a user uploads
    another CSV. If the packaged file is missing, the embedded sample is used as
    a safe fallback.
    """
    default_path = Path(__file__).with_name(DEFAULT_SITE_STATUS_FILENAME)
    if default_path.exists():
        return default_path.read_bytes()
    return create_sample_csv()


def load_csv(uploaded_file: Any | None) -> pd.DataFrame:
    if uploaded_file is None:
        return _load_csv_bytes(get_default_site_status_csv(), DEFAULT_SITE_STATUS_FILENAME)
    file_bytes = uploaded_file.getvalue()
    return _load_csv_bytes(file_bytes, uploaded_file.name)


def get_task_columns(df: pd.DataFrame) -> list[str]:
    """Return user-defined work item columns only.

    Every column after `enabled` is treated as a work item except internal
    columns created by this app. Internal columns always start with `_`.
    """
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
        task_columns.append(col_name)
    return task_columns


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


def validate_dataframe(df: pd.DataFrame) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    issues: list[dict[str, Any]] = []
    working = df.copy()

    for col in get_required_columns():
        if col not in working.columns:
            _add_issue(issues, None, "", col, "", f"Required column '{col}' is missing.", "ERROR")
            working[col] = ""

    task_columns = get_task_columns(working)
    if not task_columns:
        _add_issue(issues, None, "", "task_columns", "", "No task columns found after 'enabled'.", "ERROR")

    # Required field checks
    for idx, row in working.iterrows():
        location_id = row.get("location_id", "")
        if str(location_id).strip() == "":
            _add_issue(issues, int(idx), location_id, "location_id", location_id, "location_id is missing.", "ERROR")

    # Duplicate location_id
    if "location_id" in working.columns:
        duplicated = working[working["location_id"].astype(str).str.strip().duplicated(keep=False)]
        for idx, row in duplicated.iterrows():
            if str(row.get("location_id", "")).strip():
                _add_issue(
                    issues,
                    int(idx),
                    row.get("location_id", ""),
                    "location_id",
                    row.get("location_id", ""),
                    "Duplicate location_id. location_id must be unique.",
                    "WARNING",
                )

    # Enabled normalization
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

    # Coordinates
    working["_latitude_num"] = pd.to_numeric(working["latitude"], errors="coerce")
    working["_longitude_num"] = pd.to_numeric(working["longitude"], errors="coerce")
    for idx, row in working.iterrows():
        if pd.isna(row.get("_latitude_num")):
            _add_issue(
                issues,
                int(idx),
                row.get("location_id", ""),
                "latitude",
                row.get("latitude", ""),
                "Latitude is missing or not numeric. Site cannot be displayed on the map.",
                "ERROR",
            )
        if pd.isna(row.get("_longitude_num")):
            _add_issue(
                issues,
                int(idx),
                row.get("location_id", ""),
                "longitude",
                row.get("longitude", ""),
                "Longitude is missing or not numeric. Site cannot be displayed on the map.",
                "ERROR",
            )

    # Timezone validation
    for idx, row in working.iterrows():
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

    # Task parsing quality issues
    for idx, row in working.iterrows():
        for task in task_columns:
            parsed = parse_status_value(row.get(task, ""))
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
                    "Task value is missing.",
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
            "issue": None, #"Dash placeholder value.",
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

    # Values containing an underscore are operational string/status values.
    # Treat them as string_status even if they also contain symbols that could
    # otherwise look like malformed progress data.
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

    # Values containing slash are likely intended as progress and should be treated as invalid.
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


def parse_all_task_statuses(row: pd.Series, task_columns: list[str]) -> dict[str, dict[str, Any]]:
    return {task: parse_status_value(row.get(task, "")) for task in task_columns}


def build_string_status_color_map(df: pd.DataFrame, task_columns: list[str]) -> dict[str, str]:
    values: set[str] = set()
    for task in task_columns:
        if task not in df.columns:
            continue
        for value in df[task].dropna().astype(str):
            parsed = parse_status_value(value)
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
    """Return a compact human-readable site name for KPI lists."""
    name = str(row.get("location_name", "")).strip()
    if name:
        return name
    location_id = str(row.get("location_id", "")).strip()
    return location_id or "Unnamed site"


def calculate_kpis(
    df: pd.DataFrame,
    filtered_df: pd.DataFrame,
    selected_task_columns: list[str],
    validation_issues: list[dict[str, Any]],
) -> dict[str, Any]:
    """Calculate KPI cards for the current filtered dashboard view.

    Display rules in this UI version:
    - Total Sites means currently displayed / filtered sites.
    - Raw total, enabled total, and data-quality issue count are intentionally
      excluded from the KPI board.
    - Critical status is shown to operators as Urgent Sites.
    """
    displayed_sites = len(filtered_df)
    complete_sites = 0
    incomplete_sites = 0
    urgent_site_names: list[str] = []
    warning_site_names: list[str] = []

    for _, row in filtered_df.iterrows():
        summary = calculate_site_summary_for_selected_tasks(row, selected_task_columns)
        parsed = summary["parsed"]
        progress_items = [p for p in parsed.values() if p["type"] == "progress"]
        has_dash_placeholder = any(str(row.get(task, "")).strip() in DASH_PLACEHOLDERS for task in selected_task_columns)
        has_invalid_progress = any(p["type"] == "invalid_progress" for p in parsed.values())
        has_numeric_below_100 = any((p["percent"] or 0) < 100 for p in progress_items)
        has_all_numeric_100 = bool(progress_items) and all((p["percent"] or 0) >= 100 for p in progress_items)

        if has_all_numeric_100 and not has_dash_placeholder and not has_invalid_progress:
            complete_sites += 1
        if has_numeric_below_100 or has_dash_placeholder or has_invalid_progress:
            incomplete_sites += 1

        status_level = summary["status_level"]
        if status_level == "Critical":
            urgent_site_names.append(_get_site_display_name(row))
        elif status_level == "Warning":
            warning_site_names.append(_get_site_display_name(row))

    return {
        "Total Sites": {"count": displayed_sites},
        "Complete Sites": {"count": complete_sites},
        "Incomplete Sites": {"count": incomplete_sites},
        "Urgent Sites": {"count": len(urgent_site_names), "sites": urgent_site_names},
        "Warning Sites": {"count": len(warning_site_names), "sites": warning_site_names},
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

    # Disabled sites are always excluded in this UI version. The former sidebar
    # option was removed to keep the operator view simpler.
    filtered = filtered[filtered["_enabled_bool"] == True]  # noqa: E712
    filtered = filtered[filtered["_can_display"] == True]  # noqa: E712

    for field in ("country", "state", "city"):
        selected = filters.get(field, [])
        if selected:
            filtered = filtered[filtered[field].astype(str).isin(selected)]

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
        filtered = filtered[filtered["_has_data_issue"] == True]  # noqa: E712

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
        parsed = parse_status_value(row.get(task, ""))
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
    # Tooltip must stay compact: show only the site name on hover.
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
        parsed = parse_status_value(row.get(task, ""))
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
            parsed = parse_status_value(row.get(task, ""))
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
    """Return a single clickable DivIcon containing the status dot and label.

    This makes MarkerCluster hide the site label while clustered and show it
    automatically when the marker is unclustered at higher zoom.
    """
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

    # Fit the initial viewport to all currently displayed enabled sites.
    # With the default filter state this means all valid enabled locations in
    # the active CSV. The dynamic st_folium key below forces this viewport to be
    # recalculated when a different CSV is uploaded.
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
        .kpi-card {
            background: #ffffff;
            border: 1px solid #9ca3af;
            border-radius: 0.85rem;
            padding: 0.9rem 1rem;
            margin-bottom: 0.75rem;
            box-shadow: 0 1px 5px rgba(0,0,0,0.12);
            min-height: 6.2rem;
            display: flex;
            flex-direction: column;
            gap: 0.55rem;
        }
        .kpi-card-sites {
            height: 9.4rem;
            min-height: 9.4rem;
            max-height: 9.4rem;
        }
        .kpi-card-main {
            display: flex;
            align-items: baseline;
            justify-content: space-between;
            gap: 0.8rem;
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
            flex-wrap: wrap;
            align-items: center;
            gap: 0.35rem;
            max-height: 4.6rem;
            overflow-y: auto;
            padding-top: 0.1rem;
        }
        .kpi-site-pill {
            display: inline-block;
            max-width: 12rem;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            background: #f3f4f6;
            border: 1px solid #d1d5db;
            border-radius: 999px;
            color: #111827;
            font-size: 0.78rem;
            font-weight: 700;
            padding: 0.16rem 0.5rem;
            line-height: 1.25;
        }
        .kpi-site-pill-more {
            background: #e5e7eb;
        }
        .kpi-empty-sites {
            color: #6b7280;
            font-size: 0.82rem;
            font-weight: 700;
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


def render_sidebar_upload_bottom(source_name: str) -> Any | None:
    st.sidebar.divider()
    st.sidebar.subheader("CSV")
    uploaded_file = st.sidebar.file_uploader("Upload site status CSV", type=["csv"], key="uploaded_site_status_csv")
    st.sidebar.download_button(
        "Download sample CSV template",
        data=create_sample_csv(),
        file_name="sample_site_status.csv",
        mime="text/csv",
        use_container_width=True,
    )
    st.sidebar.caption(f"Current file: {source_name}")
    return uploaded_file


def render_sidebar_filters(df: pd.DataFrame, task_columns: list[str]) -> dict[str, Any]:
    st.sidebar.header("Filters")
    if st.sidebar.button("Reset filters", use_container_width=True):
        keys_to_clear = [
            "filter_country",
            "filter_state",
            "filter_city",
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
        "search": search,
        "status_levels": status_levels,
        "data_issue_only": data_issue_only,
    }

def _kpi_card_html(title: str, count: Any, site_names: list[str] | None = None) -> str:
    safe_title = html.escape(str(title))
    safe_count = html.escape(str(count))
    site_list_html = ""
    if site_names is not None:
        visible_names = [str(name) for name in site_names[:10]]
        overflow = max(len(site_names) - len(visible_names), 0)
        if visible_names:
            pills = "".join(
                f"<span class='kpi-site-pill'>{html.escape(name)}</span>" for name in visible_names
            )
            if overflow:
                pills += f"<span class='kpi-site-pill kpi-site-pill-more'>+{overflow} more</span>"
            site_list_html = f"<div class='kpi-site-list'>{pills}</div>"
        else:
            site_list_html = "<div class='kpi-site-list kpi-empty-sites'>No sites</div>"
    card_class = "kpi-card kpi-card-sites" if site_names is not None else "kpi-card"
    return f"""
    <div class='{card_class}'>
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


def _kpi_sites(kpis: dict[str, Any], label: str) -> list[str]:
    value = kpis.get(label, {})
    if isinstance(value, dict):
        return list(value.get("sites", []))
    return []


def render_kpi_cards(kpis: dict[str, Any]) -> None:
    row1 = st.columns(3)
    row1_items = ["Total Sites", "Complete Sites", "Incomplete Sites"]
    for col, label in zip(row1, row1_items):
        col.markdown(_kpi_card_html(label, _kpi_count(kpis, label)), unsafe_allow_html=True)

    row2 = st.columns(2)
    for col, label in zip(row2, ["Urgent Sites", "Warning Sites"]):
        col.markdown(
            _kpi_card_html(label, _kpi_count(kpis, label), _kpi_sites(kpis, label)),
            unsafe_allow_html=True,
        )


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
        _render_task_detail_row(task, parse_status_value(site.get(task, "")))

    # with st.expander("All work items"):
    #     for task in task_columns:
    #         if task not in selected_task_columns:
    #             _render_task_detail_row(task, parse_status_value(site.get(task, "")))
    #
    # with st.expander("Future task_details.csv extension placeholder"):
    #     st.caption(
    #         "Planned fields: owner, status, detail, issue, action_plan, due_date, updated_at, updated_by, overdue, stale update."
    #     )


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
        table[f"{task}__display"] = table[task].apply(lambda value: parse_status_value(value)["display_text"])
        if len(selected_task_columns) == 1:
            table[f"{task}__percent"] = table[task].apply(lambda value: parse_status_value(value)["percent"])

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
    try:
        raw_df = load_csv(uploaded_file)
    except Exception as exc:
        st.error(str(exc))
        st.stop()

    source_name = uploaded_file.name if uploaded_file is not None else DEFAULT_SITE_STATUS_FILENAME
    validated_df, validation_issues = validate_dataframe(raw_df)
    task_columns = get_task_columns(validated_df)

    if not task_columns:
        st.error("No task columns found after the enabled column. Add at least one work item column.")
        render_sidebar_upload_bottom(source_name)
        issue_df = render_data_quality_report(validation_issues)
        render_download_buttons(pd.DataFrame(), issue_df)
        st.stop()

    selected_task_columns = render_task_selector(task_columns)
    filters = render_sidebar_filters(validated_df, task_columns)
    render_sidebar_upload_bottom(source_name)

    options = {
        "show_site_labels": True,
        "show_all_tasks_in_popup": True,
        "use_marker_cluster": True,
    }

    filtered_df = apply_filters(validated_df, filters, selected_task_columns)
    kpis = calculate_kpis(validated_df, filtered_df, selected_task_columns, validation_issues)

    header_cols = st.columns([2, 1, 1])
    header_cols[0].markdown(f"Prepared by: Byeonghun Kim")
    header_cols[1].markdown(f"**Uploaded file:** `{html.escape(source_name)}`")
    # header_cols[2].markdown(f"**Last updated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    header_cols[2].markdown(f"**Total sites:** {len(filtered_df)}")
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
