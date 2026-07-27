from __future__ import annotations

import hashlib
import html
import io
import math
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import branca.colormap as cm
from branca.element import MacroElement, Template
import folium
import pandas as pd
import streamlit as st
from folium.plugins import Fullscreen, MarkerCluster
from streamlit_folium import st_folium





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

NA_VALUES = {"n/a", "na", "#n/a", "#na", "#n/a!", "not applicable", "not available", "null", "none", "해당없음"}
DASH_PLACEHOLDERS = {"-", "–", "—"}
VALID_TRUE = {"y", "yes", "true", "1"}
VALID_FALSE = {"n", "no", "false", "0"}
PROGRESS_RE = re.compile(r"^\s*([+-]?\d+(?:\.\d+)?)\s*/\s*([+-]?\d+(?:\.\d+)?)\s*$")
DEFAULT_SITE_STATUS_FILENAME = "site_status.csv"
SITE_METADATA_COLUMNS = {"version", "updated_date"}
UPDATED_DATE_COLUMN_NAME = "updated_date"
SITE_QTY_COLUMN_NAME = "QTY"
UPDATED_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
dashboard_ver = "v1.53"
DEFAULT_TASK_CONFIG_FILENAME = "task_config.csv"
TASK_CONFIG_COLUMNS = ["task_name", "visible", "category", "display_order", "description"]
DEFAULT_SITE_PEOPLE_FILENAME = "site_people.csv"
SITE_PEOPLE_COLUMNS = ["Name", "Team", "Location", "Contact Information", "Note"]

CCX_START_COLUMN_NAME = "CCx Start"
HCX_START_COLUMN_NAME = "HCx Start"
COD_COLUMN_NAME = "COD"
GANTT_TABLE_HIDE_BREAKPOINT_PX = 1100
GANTT_LOOKBACK_DAYS = 7
GANTT_LOOKAHEAD_MONTHS = 2
GANTT_PHASE_BAR_DAYS = 21
COMMISSIONING_BASE_UNITS = 90.0
CCX_BASE_DURATION_DAYS = 14
HCX_BASE_DURATION_DAYS = 10
COMMISSIONING_MIN_DURATION_DAYS = 7
SCHEDULE_ENTRY_SPLIT_RE = re.compile(r"[;|\n\r]+|,\s*(?=\d{4}-\d{1,2}-\d{1,2})")
SCHEDULE_DATE_TOKEN_RE = re.compile(r"(?P<date>\d{4}-\d{1,2}-\d{1,2})")
SCHEDULE_UNIT_TOKEN_RE = re.compile(r"\(\s*(?P<units>\d+(?:\.\d+)?)\s*(?:ea|units?|대|pcs?)?\s*\)", re.IGNORECASE)
GANTT_SHOW_ALL_END_PADDING_DAYS = 7
GANTT_COMPLETED_HIDE_AFTER_DAYS = 21
GANTT_CCX_COLOR = "#2563eb"
GANTT_HCX_COLOR = "#dc2626"
GANTT_TODAY_COLOR = "#f59e0b"
GANTT_COMMERCIAL_COLOR = "#facc15"
GANTT_COD_COLOR = "#b45309"
GANTT_COMMERCIAL_OPERATION_LABEL = "Commercial Operation"
SITE_OVERVIEW_ACTIVE_LABEL = "Active / Pre-COD"
GANTT_CCX_ACTIVE_KPI_COLOR = "#bae6fd"
GANTT_HCX_ACTIVE_KPI_COLOR = "#fbcfe8"
GANTT_MIN_CHART_WIDTH_PX = 0
GANTT_ROW_LABEL_WIDTH_PX = 190
GANTT_MOBILE_ROW_LABEL_WIDTH_PX = 165
GANTT_TABLE_HIDE_ASPECT_RATIO = "1/1"

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

PERSON_BADGE_PALETTE = [
    {"background": "#2563eb", "border": "#bfdbfe", "color": "#ffffff"},
    {"background": "#0f766e", "border": "#99f6e4", "color": "#ffffff"},
    {"background": "#7c3aed", "border": "#ddd6fe", "color": "#ffffff"},
    {"background": "#ca8a04", "border": "#fef08a", "color": "#111827"},
    {"background": "#166534", "border": "#bbf7d0", "color": "#ffffff"},
    {"background": "#0891b2", "border": "#a5f3fc", "color": "#ffffff"},
    {"background": "#a21caf", "border": "#f5d0fe", "color": "#ffffff"},
    {"background": "#4d7c0f", "border": "#d9f99d", "color": "#ffffff"},
    {"background": "#4338ca", "border": "#c7d2fe", "color": "#ffffff"},
    {"background": "#0e7490", "border": "#cffafe", "color": "#ffffff"},
    {"background": "#9333ea", "border": "#e9d5ff", "color": "#ffffff"},
    {"background": "#be185d", "border": "#fbcfe8", "color": "#ffffff"},
    {"background": "#334155", "border": "#cbd5e1", "color": "#ffffff"},
    {"background": "#047857", "border": "#a7f3d0", "color": "#ffffff"},
    {"background": "#1e40af", "border": "#bfdbfe", "color": "#ffffff"},
    {"background": "#6b21a8", "border": "#e9d5ff", "color": "#ffffff"},
    {"background": "#854d0e", "border": "#fde68a", "color": "#ffffff"},
    {"background": "#155e75", "border": "#bae6fd", "color": "#ffffff"},
]

SAMPLE_CSV = """location_id,location_name,country,state,city,latitude,longitude,timezone,enabled,Version,updated_date,QTY,CCx Start,HCx Start,COD,CCx Start 2,HCx Start 2,COD 2,F/W Update,Valve1,Valve2,Water Pump,Chiller#1 F/W Version,Chiller#2 F/W Version,HVAC F/W Version,Note
FL001,BLACKWATER RIVER,US,FL,Milton,30.6,-86.9,America/Chicago,Y,1.5,2026-05-30,135,2026-05-01,2026-05-15,2026-05-29,2026-07-06(45),2026-07-20(45),2026-07-27(45),3/3,60/66,N/A,10/66,3.0.0.0,3.0.0.0,3.0.0.1,QTY 135; base schedule shows 90 after subtracting additional 45
FL002,CANOE,US,FL,Holt,30.6,-86.7,America/Chicago,Y,1.5,2026-05-30,183,2026-05-08,2026-06-05,#N/A,,,,1/3,20/183,183/183,183/183,3.0.0.2,3.0.0.2,3.0.0.6,QTY-driven commissioning schedule
FL003,CARTWHEEL,US,FL,Jay,30.9,-87.1,America/Chicago,Y,1.0,2026-05-30,189,"Commercial Operation, 2026-08-03(6)",2026-08-17(6),2026-08-24(6),,,,3/3,66/66,183/183,N/A,3.0.0.2,3.0.0.2,3.0.0.6,Legacy commercial operation with additional commissioning
FL004,SAMPLE DISABLED,US,TX,Dallas,32.7,-96.7,America/Chicago,N,1.0,2026-05-30,90,,,,,,,0/3,5/10,NA,,Pending,Pending,Completed,Disabled sample
"""

SAMPLE_TASK_CONFIG_CSV = """task_name,visible,category,display_order,description
CCx Start,Y,Schedule,5,CCx start date list; default quantity comes from site QTY minus additional CCx quantities
HCx Start,Y,Schedule,6,HCx start date list; default quantity comes from site QTY minus additional HCx quantities
COD,Y,Schedule,7,Commercial operation date list; default quantity comes from site QTY minus additional COD quantities
F/W Update,Y,Active Work,8,Firmware update completion basis
Valve1,Y,Active Work,10,Currently managed work item
Valve2,Y,Active Work,20,Currently managed work item
Water Pump,Y,Active Work,30,Currently managed work item
Chiller#1 F/W Version,Y,Information,40,Firmware version information; completion follows F/W Update
Chiller#2 F/W Version,Y,Information,50,Firmware version information; completion follows F/W Update
HVAC F/W Version,Y,Information,60,Firmware version information; completion follows F/W Update
Note,Y,Information,999,Free text notes; excluded from KPI completion counts
"""

SAMPLE_SITE_PEOPLE_CSV = """Name,Team,Location,Contact Information,Note
John Smith,US Service,FL001;jay,john.smith@example.com,Primary engineer for multiple sites
Park Minsoo,KR Support,CANOE,park.minsoo@example.com,Business traveler
David Kim,US Service,CARTWHEEL|BLACKWATER RIVER,david.kim@example.com,Remote support contact for multiple sites
Inactive Person,US Service,-,inactive.person@example.com,Hidden because Location is dash
"""





def get_required_columns() -> list[str]:
    return REQUIRED_COLUMNS.copy()


def create_sample_csv() -> bytes:
    return SAMPLE_CSV.encode("utf-8-sig")


def create_sample_task_config_csv() -> bytes:
    return SAMPLE_TASK_CONFIG_CSV.encode("utf-8-sig")


def create_sample_site_people_csv() -> bytes:
    return SAMPLE_SITE_PEOPLE_CSV.encode("utf-8-sig")


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


def get_default_site_people_csv() -> bytes | None:
    default_path = Path(__file__).with_name(DEFAULT_SITE_PEOPLE_FILENAME)
    if default_path.exists():
        return default_path.read_bytes()
    return None


def load_site_people(uploaded_file: Any | None) -> pd.DataFrame:
    if uploaded_file is None:
        default_bytes = get_default_site_people_csv()
        if default_bytes is None:
            return pd.DataFrame(columns=SITE_PEOPLE_COLUMNS)
        return _load_csv_bytes(default_bytes, DEFAULT_SITE_PEOPLE_FILENAME)
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
        source_df = source_df[source_df["_enabled_bool"] == True]

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



def _validate_schedule_date_metadata(
    working: pd.DataFrame,
    enabled_working: pd.DataFrame,
    issues: list[dict[str, Any]],
) -> None:
    qty_col = _get_site_qty_column(working.columns)
    if qty_col is not None:
        for idx, row in enabled_working.iterrows():
            qty_text = str(row.get(qty_col, "")).strip()
            if qty_text and qty_text.lower() not in NA_VALUES and qty_text not in DASH_PLACEHOLDERS and _parse_equipment_units(qty_text) is None:
                _add_issue(
                    issues,
                    int(idx),
                    row.get("location_id", ""),
                    qty_col,
                    row.get(qty_col, ""),
                    f"{qty_col} must be a positive equipment count because it is used as the site-level commissioning quantity.",
                    "WARNING",
                )

    for idx, row in enabled_working.iterrows():
        for phase in ("CCx", "HCx"):
            for schedule_col in _get_schedule_start_columns(working.columns, phase):
                raw_value = row.get(schedule_col, "")
                text = str(raw_value).strip()
                if not text or text.lower() in NA_VALUES or text in DASH_PLACEHOLDERS:
                    continue
                if _is_commercial_operation_value(text):
                    continue
                entries = _split_schedule_entries(raw_value)
                if not entries:
                    continue
                for entry in entries:
                    if _entry_is_schedule_placeholder(entry):
                        continue
                    if _parse_schedule_entry_date(entry) is None:
                        _add_issue(
                            issues,
                            int(idx),
                            row.get("location_id", ""),
                            schedule_col,
                            raw_value,
                            f"{schedule_col} contains an invalid schedule date entry. Use YYYY-MM-DD, YYYY-MM-DD(units), or Commercial Operation plus additional date entries.",
                            "WARNING",
                        )
                        break
                unit_col = _get_schedule_unit_column_for_start(working.columns, phase, schedule_col)
                if unit_col is not None:
                    unit_text = str(row.get(unit_col, "")).strip()
                    if unit_text and unit_text.lower() not in NA_VALUES and unit_text not in DASH_PLACEHOLDERS and _parse_equipment_units(unit_text) is None:
                        _add_issue(
                            issues,
                            int(idx),
                            row.get("location_id", ""),
                            unit_col,
                            row.get(unit_col, ""),
                            f"{unit_col} must be a positive equipment count. Example: 90.",
                            "WARNING",
                        )

        for cod_col in _get_cod_columns(working.columns):
            raw_value = row.get(cod_col, "")
            text = str(raw_value).strip()
            if not text or text.lower() in NA_VALUES or text in DASH_PLACEHOLDERS:
                continue
            entries = _split_schedule_entries(raw_value)
            if not entries:
                continue
            for entry in entries:
                if _entry_is_schedule_placeholder(entry):
                    continue
                if _parse_schedule_entry_date(entry) is None:
                    _add_issue(
                        issues,
                        int(idx),
                        row.get("location_id", ""),
                        cod_col,
                        raw_value,
                        f"{cod_col} contains an invalid COD date entry. Use YYYY-MM-DD or YYYY-MM-DD(units).",
                        "WARNING",
                    )
                    break
            unit_col = _get_cod_unit_column_for_date(working.columns, cod_col)
            if unit_col is not None:
                unit_text = str(row.get(unit_col, "")).strip()
                if unit_text and unit_text.lower() not in NA_VALUES and unit_text not in DASH_PLACEHOLDERS and _parse_equipment_units(unit_text) is None:
                    _add_issue(
                        issues,
                        int(idx),
                        row.get("location_id", ""),
                        unit_col,
                        row.get(unit_col, ""),
                        f"{unit_col} must be a positive equipment count. Example: 90.",
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
        if is_site_qty_column(col_name):
            continue
        if is_schedule_unit_column(col_name) or is_cod_unit_column(col_name) or _is_additional_schedule_start_column(col_name) or _is_additional_cod_column(col_name):
            continue
        task_columns.append(col_name)
    return task_columns


def is_note_column(column_name: str) -> bool:
    return str(column_name).strip().lower() == "note"


def is_schedule_column(column_name: str) -> bool:
    normalized = str(column_name).strip().lower()
    if normalized in {CCX_START_COLUMN_NAME.lower(), HCX_START_COLUMN_NAME.lower(), COD_COLUMN_NAME.lower()}:
        return True
    return _is_cod_column_name(column_name) and _cod_column_sequence(column_name) == 1


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

    enabled_working = working[working["_enabled_bool"] == True].copy()

    _validate_updated_date_metadata(working, enabled_working, issues)
    _validate_schedule_date_metadata(working, enabled_working, issues)

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
    for idx, row in working[working["_enabled_bool"] == True].iterrows():
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

    for idx, row in working[working["_enabled_bool"] == True].iterrows():
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

    for idx, row in working[working["_enabled_bool"] == True].iterrows():
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
    if is_note_column(task_name) or is_schedule_column(task_name):
        raw_value = value
        if value is None or pd.isna(value):
            display_text = ""
        elif is_schedule_column(task_name):
            parsed_date = _parse_schedule_date(value) if "_parse_schedule_date" in globals() else None
            display_text = parsed_date.strftime("%Y-%m-%d") if parsed_date else str(value).strip()
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


def _sort_site_entries(site_entries: list[Any]) -> list[Any]:
    def entry_name(entry: Any) -> str:
        if isinstance(entry, dict):
            return str(entry.get("name", ""))
        return str(entry)

    return sorted(site_entries, key=lambda entry: (entry_name(entry).casefold(), entry_name(entry)))


def _sort_sites_by_version(version_map: dict[str, list[Any]]) -> dict[str, list[Any]]:
    sorted_map: dict[str, list[Any]] = {}
    for version in sorted(version_map.keys(), key=_version_sort_key):
        sorted_map[version] = _sort_site_entries(version_map[version])
    return sorted_map


def get_version_filter_options(df: pd.DataFrame) -> list[str]:
    version_col = _get_version_column_name(df.columns)
    if version_col is None:
        return []

    source_df = df.copy()
    if "_enabled_bool" in source_df.columns:
        source_df = source_df[source_df["_enabled_bool"] == True]
    if "_can_display" in source_df.columns:
        source_df = source_df[source_df["_can_display"] == True]

    versions = {
        str(value).strip() if str(value).strip() else "No Version"
        for value in source_df[version_col].dropna().tolist()
    }
    return sorted(versions, key=_version_sort_key)


def _version_numeric_tuple(version: str) -> tuple[int, ...] | None:
    text = str(version).strip()
    match = re.search(r"(?<!\d)(?:version\s*)?[vV]?\s*(\d+(?:\.\d+)*)(?!\d)", text, flags=re.IGNORECASE)
    if not match:
        return None
    parts: list[int] = []
    for part in match.group(1).split("."):
        try:
            parts.append(int(part))
        except Exception:
            return None
    while len(parts) > 1 and parts[-1] == 0:
        parts.pop()
    return tuple(parts)


def _normalize_version_target(value: Any) -> str:
    version_tuple = _version_numeric_tuple(str(value))
    if version_tuple is None:
        return str(value).strip().casefold()
    if len(version_tuple) == 1:
        return f"{version_tuple[0]}.0"
    return f"{version_tuple[0]}.{version_tuple[1]}"


def _version_matches_quick_target(version: str, target: str) -> bool:
    version_tuple = _version_numeric_tuple(version)
    target_tuple = _version_numeric_tuple(target)
    if version_tuple is None or target_tuple is None:
        return str(version).strip().casefold() == str(target).strip().casefold()
    normalized_version = _normalize_version_target(version)
    normalized_target = _normalize_version_target(target)
    return normalized_version == normalized_target


def _get_quick_version_targets(version_options: list[str]) -> list[str]:
    preferred = ["1.0", "1.5"]
    targets: list[str] = []
    discovered: set[str] = set()
    for target in preferred:
        if any(_version_matches_quick_target(option, target) for option in version_options):
            normalized = _normalize_version_target(target)
            if normalized not in discovered:
                discovered.add(normalized)
                targets.append(target)

    for option in version_options:
        normalized = _normalize_version_target(option)
        if not normalized or normalized.casefold() in {"no version", "none", "not set"}:
            continue
        if normalized not in discovered:
            discovered.add(normalized)
            targets.append(normalized)
    return targets

def _version_css_class(version: str) -> str:
    numeric = _version_numeric_tuple(version)
    if not numeric:
        return "version-other"
    if numeric[:2] == (1, 0):
        return "version-1-0"
    if numeric[:2] == (1, 5):
        return "version-1-5"
    return "version-other"


def _version_badge_palette(version: str) -> dict[str, str]:
    css_class = _version_css_class(version)
    if css_class == "version-1-0":
        return {
            "class": css_class,
            "background": "#0f766e",
            "border": "#2dd4bf",
            "color": "#ffffff",
            "shadow": "rgba(15,118,110,0.26)",
        }
    if css_class == "version-1-5":
        return {
            "class": css_class,
            "background": "#7c3aed",
            "border": "#c084fc",
            "color": "#ffffff",
            "shadow": "rgba(124,58,237,0.26)",
        }
    return {
        "class": css_class,
        "background": "#475569",
        "border": "#94a3b8",
        "color": "#ffffff",
        "shadow": "rgba(71,85,105,0.24)",
    }


def _version_badge_html(version: str) -> str:
    safe_version = html.escape(str(version))
    palette = _version_badge_palette(version)
    css_class = html.escape(palette["class"])
    style = (
        "display:inline-block;"
        "border-radius:999px;"
        "padding:1px 7px;"
        "font-size:10px;"
        "font-weight:900;"
        "line-height:1.25;"
        "white-space:nowrap;"
        "letter-spacing:0.01em;"
        f"background:{palette['background']} !important;"
        f"border:1px solid {palette['border']} !important;"
        f"color:{palette['color']} !important;"
        f"box-shadow:0 1px 3px {palette['shadow']};"
    )
    return (
        f"<span class='site-version-badge site-version-badge-{css_class}' "
        f"style='{style}' "
        f"title='Version {safe_version}'>Version {safe_version}</span>"
    )



def _canonical_name(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).strip().lower())


def _find_column_by_canonical_names(columns: Any, candidates: list[str]) -> str | None:
    wanted = {_canonical_name(candidate) for candidate in candidates}
    for col in columns:
        if _canonical_name(col) in wanted:
            return str(col)
    return None


def _is_fw_version_column(column_name: str) -> bool:
    normalized = _canonical_name(column_name)
    return normalized in {
        "chiller1fwversion",
        "chiller2fwversion",
        "chillerfwversion",
        "hvacfwversion",
    } or normalized.endswith("fwversion")


def _is_fw_update_column(column_name: str) -> bool:
    return _canonical_name(column_name) in {"fwupdate", "firmwareupdate", "fupdate"}


def _get_fw_update_column_name(columns: Any) -> str | None:
    return _find_column_by_canonical_names(columns, ["F/W Update", "FW Update", "Firmware Update", "F Update"])


def _get_schedule_phase_for_column(task_name: str) -> str | None:
    normalized = _canonical_name(task_name)
    if normalized == _canonical_name(CCX_START_COLUMN_NAME):
        return "CCx"
    if normalized == _canonical_name(HCX_START_COLUMN_NAME):
        return "HCx"
    if normalized == _canonical_name(COD_COLUMN_NAME):
        return "COD"
    return None


def _build_schedule_segments_for_row(row: pd.Series) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    for segment in _build_schedule_segments_from_events(_get_schedule_events_for_row(row)):
        start = segment["start"]
        end = segment["end"]
        if end > start:
            segments.append(segment)
    segments.extend(_get_cod_events_for_row(row))
    return segments


def _make_kpi_status(status_type: str, display_text: str, percent: float | None = None, issue: str | None = None) -> dict[str, Any]:
    return {
        "raw_value": display_text,
        "type": status_type,
        "completed": None,
        "total": None,
        "percent": percent,
        "display_text": display_text,
        "color": get_color_for_progress(percent) if percent is not None else "gray",
        "issue": issue,
    }


def _schedule_kpi_status_for_row(row: pd.Series, task_name: str, today: datetime | None = None) -> dict[str, Any]:
    phase = _get_schedule_phase_for_column(task_name)
    current_day = _today_start(today)
    if phase is None:
        return _make_kpi_status("not_applicable", "N/A")
    if phase in {"CCx", "HCx"}:
        phase_events = [event for event in _build_schedule_segments_for_row(row) if event.get("type") == phase]
        if _row_has_commercial_operation(row, current_day):
            return _make_kpi_status("progress", "Complete", 100.0)
        if not phase_events:
            if _phase_has_legacy_commercial_operation(row, phase):
                return _make_kpi_status("progress", GANTT_COMMERCIAL_OPERATION_LABEL, 100.0)
            return _make_kpi_status("not_applicable", "N/A")
        active_segments = [event for event in phase_events if event.get("start") <= current_day < event.get("end")]
        if active_segments:
            active = min(active_segments, key=lambda item: item["end"])
            return _make_kpi_status("progress", f"Incomplete · active until {active['end'].strftime('%Y-%m-%d')}", 0.0)
        future_segments = [event for event in phase_events if event.get("start") > current_day]
        if future_segments:
            next_segment = min(future_segments, key=lambda item: item["start"])
            return _make_kpi_status("progress", f"Incomplete · next {next_segment['start'].strftime('%Y-%m-%d')}", 0.0)
        latest_segment = max(phase_events, key=lambda item: item["end"])
        return _make_kpi_status("progress", f"Complete · latest ended {latest_segment['end'].strftime('%Y-%m-%d')}", 100.0)
    cod_cols = _get_cod_columns(row.index)
    raw_values = [str(row.get(col, "")).strip() for col in cod_cols]
    has_raw_cod = any(text and text.lower() not in NA_VALUES and text not in DASH_PLACEHOLDERS for text in raw_values)
    if not has_raw_cod:
        return _make_kpi_status("not_applicable", "N/A")
    cod_events = _get_cod_events_for_row(row)
    if not cod_events:
        return _make_kpi_status("invalid_progress", "Invalid COD date", None, "Invalid COD date.")
    upcoming = [event for event in cod_events if event["start"] > current_day]
    if upcoming:
        next_cod = min(upcoming, key=lambda item: item["start"])
        return _make_kpi_status("progress", f"Incomplete · next COD {next_cod['start'].strftime('%Y-%m-%d')}", 0.0)
    latest_cod = max(cod_events, key=lambda item: item["start"])
    return _make_kpi_status("progress", f"Complete · latest COD {latest_cod['start'].strftime('%Y-%m-%d')}", 100.0)


def _build_kpi_statuses_for_row(row: pd.Series, selected_task_columns: list[str]) -> dict[str, dict[str, Any]]:
    statuses: dict[str, dict[str, Any]] = {}
    fw_update_col = _get_fw_update_column_name(row.index)
    for task in selected_task_columns:
        if is_note_column(task) or is_site_metadata_column(task) or is_schedule_column(task):
            continue
        if _is_fw_version_column(task):
            if fw_update_col is not None:
                statuses[f"{task} → {fw_update_col}"] = parse_task_status_value(fw_update_col, row.get(fw_update_col, ""))
            continue
        if _is_fw_update_column(task):
            statuses[task] = parse_task_status_value(task, row.get(task, ""))
            continue
        statuses[task] = parse_task_status_value(task, row.get(task, ""))
    return statuses

def is_kpi_calculation_task(task_name: str) -> bool:
    return not is_note_column(task_name) and not is_site_metadata_column(task_name) and not is_schedule_column(task_name)


def _build_site_overview_groups(filtered_df: pd.DataFrame) -> dict[str, list[Any]]:
    groups: dict[str, list[Any]] = {
        GANTT_COMMERCIAL_OPERATION_LABEL: [],
        SITE_OVERVIEW_ACTIVE_LABEL: [],
    }
    today = _today_start()

    for _, row in filtered_df.iterrows():
        site_entry = {
            "name": _get_site_display_name(row),
            "schedule_phase": get_current_schedule_phase(row, today),
        }
        group_name = GANTT_COMMERCIAL_OPERATION_LABEL if _row_has_commercial_operation(row, today) else SITE_OVERVIEW_ACTIVE_LABEL
        groups.setdefault(group_name, []).append(site_entry)

    return {group_name: _sort_site_entries(site_entries) for group_name, site_entries in groups.items()}


def calculate_kpis(
    df: pd.DataFrame,
    filtered_df: pd.DataFrame,
    selected_task_columns: list[str],
    validation_issues: list[dict[str, Any]],
) -> dict[str, Any]:
    displayed_sites = len(filtered_df)
    site_overview_groups = _build_site_overview_groups(filtered_df)
    complete_sites_by_version: dict[str, list[Any]] = {}
    incomplete_sites_by_version: dict[str, list[Any]] = {}

    for _, row in filtered_df.iterrows():
        parsed = _build_kpi_statuses_for_row(row, selected_task_columns)
        site_name = _get_site_display_name(row)
        version = _get_site_version(row)
        site_entry = {"name": site_name, "schedule_phase": get_current_schedule_phase(row)}

        kpi_scope_parsed = {
            task: status
            for task, status in parsed.items()
            if status["type"] != "string_status"
        }

        if not kpi_scope_parsed:
            continue

        is_incomplete = False
        for status in kpi_scope_parsed.values():
            status_type = status.get("type")
            if status_type == "not_applicable":
                continue
            if status_type == "progress":
                if (status.get("percent") or 0) < 100:
                    is_incomplete = True
                    break
                continue
            if status_type in {"missing", "invalid_progress"}:
                is_incomplete = True
                break
            is_incomplete = True
            break

        if is_incomplete:
            incomplete_sites_by_version.setdefault(version, []).append(site_entry)
        else:
            complete_sites_by_version.setdefault(version, []).append(site_entry)

    complete_sites_by_version = _sort_sites_by_version(complete_sites_by_version)
    incomplete_sites_by_version = _sort_sites_by_version(incomplete_sites_by_version)
    complete_count = sum(len(site_names) for site_names in complete_sites_by_version.values())
    incomplete_count = sum(len(site_names) for site_names in incomplete_sites_by_version.values())

    return {
        "Site Overview": {
            "count": displayed_sites,
            "sites_by_group": site_overview_groups,
        },
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




def _get_people_column(people_df: pd.DataFrame, candidates: list[str]) -> str | None:
    return _find_column_by_canonical_names(people_df.columns, candidates)


def _is_people_location_hidden_value(value: Any) -> bool:
    if value is None or pd.isna(value):
        return True
    text = str(value).strip()
    if not text:
        return True
    if text in DASH_PLACEHOLDERS:
        return True
    lowered = text.lower()
    return lowered in NA_VALUES or lowered in VALID_FALSE


def _build_site_location_lookup(site_df: pd.DataFrame) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for _, row in site_df.iterrows():
        location_id = str(row.get("location_id", "")).strip()
        location_name = str(row.get("location_name", "")).strip()
        if location_id:
            lookup.setdefault(_canonical_name(location_id), location_id)
        if location_name:
            lookup.setdefault(_canonical_name(location_name), location_id)
    return lookup


def _empty_site_people_df() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "Name",
            "Team",
            "Location",
            "Contact Information",
            "Note",
            "_visible_bool",
            "_matched_location_id",
            "_matched_location_name",
            "_matched_bool",
            "_source_location",
            "_location_token",
            "_source_row_index",
            "_site_people_order",
            "_person_key",
            "_assignment_key",
        ]
    )


def _split_people_locations(value: Any) -> list[str]:
    text = "" if value is None or pd.isna(value) else str(value).strip()
    if not text:
        return []
    parts = [part.strip() for part in re.split(r"\s*(?:;|\||,|\n|\r)+\s*", text) if part.strip()]
    return parts or [text]


def _people_person_key(name: str, team: str, contact: str) -> str:
    contact_key = str(contact).strip().casefold()
    if contact_key:
        return f"contact:{contact_key}"
    return f"name:{_canonical_name(name)}|team:{_canonical_name(team)}"


def prepare_site_people(
    people_df: pd.DataFrame,
    site_df: pd.DataFrame,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    issues: list[dict[str, Any]] = []
    if people_df is None or people_df.empty:
        return _empty_site_people_df(), issues

    name_col = _get_people_column(people_df, ["Name", "Person Name", "person_name", "이름"])
    team_col = _get_people_column(people_df, ["Team", "팀"])
    location_col = _get_people_column(people_df, ["Location", "Locations", "Site", "Sites", "Site ID", "Site IDs", "Site Name", "Site Names", "location_id", "location_name", "위치", "사이트"])
    contact_col = _get_people_column(people_df, ["Contact Information", "Contact", "Email", "Mail", "Email Address", "메일", "연락처"])
    note_col = _get_people_column(people_df, ["Note", "Notes", "Memo", "메모"])

    required_map = {
        "Name": name_col,
        "Team": team_col,
        "Location": location_col,
        "Contact Information": contact_col,
        "Note": note_col,
    }
    for required_name, actual_col in required_map.items():
        if actual_col is None:
            _add_issue(issues, None, "", f"site_people.{required_name}", "", f"site_people.csv is missing column '{required_name}'.", "WARNING")

    site_lookup = _build_site_location_lookup(site_df)
    id_to_name = {str(row.get("location_id", "")).strip(): str(row.get("location_name", "")).strip() for _, row in site_df.iterrows()}
    rows: list[dict[str, Any]] = []
    email_re = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

    for idx, row in people_df.iterrows():
        name = str(row.get(name_col, "") if name_col is not None else "").strip()
        team = str(row.get(team_col, "") if team_col is not None else "").strip() or "No Team"
        source_location = str(row.get(location_col, "") if location_col is not None else "").strip()
        contact = str(row.get(contact_col, "") if contact_col is not None else "").strip()
        note = str(row.get(note_col, "") if note_col is not None else "").strip()
        location_tokens = _split_people_locations(source_location)
        person_key = _people_person_key(name, team, contact)
        visible_tokens = [token for token in location_tokens if not _is_people_location_hidden_value(token)]
        visible = bool(visible_tokens)

        if visible and not name:
            _add_issue(issues, int(idx), "", "site_people.Name", name, "Person row with assigned Location is missing Name.", "WARNING")
        if visible and contact and not email_re.match(contact):
            _add_issue(issues, int(idx), "", "site_people.Contact Information", contact, "Contact Information should be an email address.", "INFO")

        if not visible_tokens:
            rows.append(
                {
                    "Name": name,
                    "Team": team,
                    "Location": source_location,
                    "Contact Information": contact,
                    "Note": note,
                    "_visible_bool": False,
                    "_matched_location_id": "",
                    "_matched_location_name": "",
                    "_matched_bool": False,
                    "_source_location": source_location,
                    "_location_token": source_location,
                    "_source_row_index": int(idx),
                    "_site_people_order": int(idx),
                    "_person_key": person_key,
                    "_assignment_key": f"{person_key}|hidden:{_canonical_name(source_location)}",
                }
            )
            continue

        seen_location_ids_for_row: set[str] = set()
        for location_token in visible_tokens:
            matched_location_id = site_lookup.get(_canonical_name(location_token), "") if location_token else ""
            matched_location_name = id_to_name.get(matched_location_id, "") if matched_location_id else ""

            if location_token and not matched_location_id:
                _add_issue(issues, int(idx), "", "site_people.Location", location_token, "Location does not match any enabled site location_id or location_name.", "WARNING")

            if matched_location_id and matched_location_id in seen_location_ids_for_row:
                continue
            if matched_location_id:
                seen_location_ids_for_row.add(matched_location_id)

            rows.append(
                {
                    "Name": name,
                    "Team": team,
                    "Location": location_token,
                    "Contact Information": contact,
                    "Note": note,
                    "_visible_bool": bool(matched_location_id),
                    "_matched_location_id": matched_location_id,
                    "_matched_location_name": matched_location_name,
                    "_matched_bool": bool(matched_location_id),
                    "_source_location": source_location,
                    "_location_token": location_token,
                    "_source_row_index": int(idx),
                    "_site_people_order": int(idx),
                    "_person_key": person_key,
                    "_assignment_key": f"{person_key}|site:{matched_location_id}" if matched_location_id else f"{person_key}|unmatched:{_canonical_name(location_token)}",
                }
            )

    if not rows:
        return _empty_site_people_df(), issues
    return pd.DataFrame(rows), issues


def get_people_filter_options(site_people_df: pd.DataFrame) -> dict[str, list[str]]:
    if site_people_df.empty:
        return {"team": []}
    active = site_people_df[(site_people_df["_visible_bool"] == True) & (site_people_df["_matched_bool"] == True)].copy()
    if active.empty:
        return {"team": []}
    active = active.drop_duplicates(subset=["_person_key"])
    teams = sorted([x for x in active["Team"].dropna().astype(str).unique().tolist() if x.strip()], key=lambda x: str(x).casefold())
    return {"team": teams}


def filter_site_people(site_people_df: pd.DataFrame, filters: dict[str, Any]) -> pd.DataFrame:
    if site_people_df.empty:
        return site_people_df.copy()
    filtered = site_people_df.copy()
    if not filters.get("people_show_assigned", True):
        return filtered.iloc[0:0].copy()
    filtered = filtered[(filtered["_visible_bool"] == True) & (filtered["_matched_bool"] == True)].copy()
    selected_teams = list(filters.get("people_team", []) or [])
    if selected_teams:
        filtered = filtered[filtered["Team"].astype(str).isin(selected_teams)].copy()
    query = str(filters.get("people_search", "") or "").strip().lower()
    if query:
        haystack = (
            filtered["Name"].astype(str)
            + " "
            + filtered["Team"].astype(str)
            + " "
            + filtered["Contact Information"].astype(str)
            + " "
            + filtered["Location"].astype(str)
            + " "
            + filtered["_source_location"].astype(str)
            + " "
            + filtered["_matched_location_id"].astype(str)
            + " "
            + filtered["_matched_location_name"].astype(str)
        ).str.lower()
        filtered = filtered[haystack.str.contains(re.escape(query), na=False)].copy()
    return filtered


def build_people_by_location(site_people_df: pd.DataFrame) -> dict[str, list[dict[str, Any]]]:
    people_by_location: dict[str, list[dict[str, Any]]] = {}
    if site_people_df.empty:
        return people_by_location
    deduped = site_people_df.drop_duplicates(subset=["_matched_location_id", "_person_key"]).copy()
    for _, row in deduped.iterrows():
        location_id = str(row.get("_matched_location_id", "")).strip()
        if not location_id:
            continue
        entry = {
            "name": str(row.get("Name", "")).strip(),
            "team": str(row.get("Team", "")).strip(),
            "contact": str(row.get("Contact Information", "")).strip(),
            "note": str(row.get("Note", "")).strip(),
            "location": str(row.get("Location", "")).strip(),
            "source_location": str(row.get("_source_location", "")).strip(),
            "person_key": str(row.get("_person_key", "")).strip(),
            "source_row_index": int(row.get("_source_row_index", 0)) if str(row.get("_source_row_index", "")).strip() else 0,
            "site_people_order": int(row.get("_site_people_order", row.get("_source_row_index", 0))) if str(row.get("_site_people_order", row.get("_source_row_index", ""))).strip() else 0,
        }
        people_by_location.setdefault(location_id, []).append(entry)
    for location_id, entries in people_by_location.items():
        entries.sort(key=lambda item: (int(item.get("site_people_order", 0)), str(item.get("name", "")).casefold(), str(item.get("person_key", ""))))
    return people_by_location


def get_people_for_site(row: pd.Series, people_by_location: dict[str, list[dict[str, Any]]] | None) -> list[dict[str, Any]]:
    if not people_by_location:
        return []
    location_id = str(row.get("location_id", "")).strip()
    return list(people_by_location.get(location_id, []))


def calculate_people_kpis(filtered_df: pd.DataFrame, filtered_people_df: pd.DataFrame) -> dict[str, Any]:
    active_people = filtered_people_df.copy() if filtered_people_df is not None else pd.DataFrame()
    if active_people.empty or filtered_df.empty:
        return {
            "Team Overview": {"count": 0, "team_counts": {}},
            "On-Site Staff": {"count": 0, "site_people": []},
        }

    site_lookup: dict[str, dict[str, str]] = {}
    for _, site_row in filtered_df.iterrows():
        location_id = str(site_row.get("location_id", "")).strip()
        if not location_id:
            continue
        location_name = str(site_row.get("location_name", "")).strip()
        site_lookup[location_id] = {
            "location_id": location_id,
            "location_name": location_name if location_name else location_id,
        }

    filtered_site_ids = set(site_lookup.keys())
    active_people = active_people[active_people["_matched_location_id"].astype(str).isin(filtered_site_ids)].copy()
    if active_people.empty:
        return {
            "Team Overview": {"count": 0, "team_counts": {}},
            "On-Site Staff": {"count": 0, "site_people": []},
        }

    person_color_index_map = _build_person_color_index_map(active_people)
    unique_people = active_people.drop_duplicates(subset=["_person_key"]).copy()
    team_counts: dict[str, int] = {}
    if not unique_people.empty:
        team_order_rows = unique_people.copy()
        team_order_rows["_team_sort_order"] = pd.to_numeric(team_order_rows.get("_site_people_order", team_order_rows.get("_source_row_index", 0)), errors="coerce").fillna(0).astype(int)
        team_summary = (
            team_order_rows.groupby("Team", sort=False)
            .agg(_person_count=("_person_key", "nunique"), _first_order=("_team_sort_order", "min"))
            .reset_index()
            .sort_values(["_first_order", "Team"], key=lambda col: col.astype(str).str.casefold() if col.name == "Team" else col)
        )
        team_counts = {str(row["Team"]): int(row["_person_count"]) for _, row in team_summary.iterrows()}
    site_rows: list[dict[str, Any]] = []
    for location_id, group in active_people.groupby("_matched_location_id"):
        location_id_text = str(location_id).strip()
        group = group.drop_duplicates(subset=["_person_key"]).copy()
        people_entries: list[dict[str, str]] = []
        for _, person_row in group.iterrows():
            person_name = str(person_row.get("Name", "")).strip()
            if not person_name:
                continue
            people_entries.append(
                {
                    "name": person_name,
                    "person_key": str(person_row.get("_person_key", "")).strip() or person_name,
                    "color_index": person_color_index_map.get(str(person_row.get("_person_key", "")).strip(), 0),
                    "source_row_index": int(person_row.get("_source_row_index", 0)) if str(person_row.get("_source_row_index", "")).strip() else 0,
                    "site_people_order": int(person_row.get("_site_people_order", person_row.get("_source_row_index", 0))) if str(person_row.get("_site_people_order", person_row.get("_source_row_index", ""))).strip() else 0,
                }
            )
        people_entries.sort(key=lambda item: (int(item.get("site_people_order", 0)), str(item.get("name", "")).casefold(), str(item.get("person_key", ""))))
        site_info = site_lookup.get(location_id_text, {"location_id": location_id_text, "location_name": location_id_text})
        site_rows.append(
            {
                "location_id": location_id_text,
                "location_name": site_info.get("location_name", location_id_text),
                "count": len(people_entries),
                "names": [str(person.get("name", "")).strip() for person in people_entries if str(person.get("name", "")).strip()],
                "people": people_entries,
            }
        )
    site_rows.sort(key=lambda item: (str(item.get("location_name", "")).casefold(), str(item.get("location_id", ""))))
    return {
        "Team Overview": {"count": len(team_counts), "team_counts": team_counts},
        "On-Site Staff": {"count": len(unique_people), "site_people": site_rows},
    }


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

    filtered = filtered[filtered["_enabled_bool"] == True].copy()
    filtered = filtered[filtered["_can_display"] == True].copy()

    for field in ("country", "state", "city"):
        selected = filters.get(field, [])
        if selected:
            filtered = filtered[filtered[field].astype(str).isin(selected)].copy()

    selected_versions = list(filters.get("version", []) or [])
    quick_version_target = str(filters.get("version_quick_target", "") or "").strip()
    if quick_version_target:
        if filtered.empty:
            return filtered
        mask = filtered.apply(lambda row: _version_matches_quick_target(_get_site_version(row), quick_version_target), axis=1)
        filtered = filtered[mask.reindex(filtered.index, fill_value=False).astype(bool)].copy()
    elif selected_versions:
        selected_set = {str(version).strip() for version in selected_versions}
        if filtered.empty:
            return filtered
        filtered = filtered[filtered.apply(lambda row: _get_site_version(row) in selected_set, axis=1).reindex(filtered.index, fill_value=False).astype(bool)].copy()

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


def build_site_label_html(row: pd.Series, selected_task_columns: list[str], show_labels: bool = True, people_by_location: dict[str, list[dict[str, Any]]] | None = None) -> str:
    if not show_labels:
        return ""
    site_name = html.escape(str(row.get("location_name", "")))
    location_id = html.escape(str(row.get("location_id", "")))
    site_version = _get_site_version(row)
    people_for_site = get_people_for_site(row, people_by_location)
    people_count_html = ""
    if people_for_site:
        people_count_html = f"<div class='site-people-badge' style='margin:2px 0 3px 0; display:inline-block; background:#e0f2fe; border:1px solid #38bdf8; color:#0f172a; border-radius:999px; padding:1px 7px; font-size:10px; font-weight:900;'>👥 {len(people_for_site)}</div>"
    lines = [
        f"<div style='font-weight:800; margin-bottom:2px; color:#111827;'>{site_name}</div>",
        f"<div class='site-version-row' style='margin:2px 0 3px 0;'>{_version_badge_html(site_version)}</div>",
        people_count_html,
    ]
    if len(selected_task_columns) == 1:
        task = selected_task_columns[0]
        parsed = parse_task_status_value(task, row.get(task, ""))
        display_text = _format_schedule_task_display(row, task, row.get(task, "")) if is_schedule_column(task) else parsed["display_text"]
        safe_task = html.escape(task)
        safe_display = html.escape(display_text)
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
    people_by_location: dict[str, list[dict[str, Any]]] | None = None,
) -> str:
    selected = task_columns if selected_task_columns is None else selected_task_columns
    site_name = html.escape(str(row.get("location_name", "")))
    city_state = html.escape(f"{row.get('city', '')}, {row.get('state', '')}".strip(", "))
    site_qty = _get_row_total_equipment_qty(row)
    site_qty_text = _format_equipment_units(site_qty)
    site_qty_html = ""
    if site_qty_text:
        site_qty_html = (
            '<div style="display:inline-block; margin:2px 0 8px 0; padding:3px 8px; '
            'border-radius:999px; background:#eef2ff; border:1px solid #c7d2fe; '
            'color:#1e1b4b; font-size:12px; font-weight:800;">'
            f"Site QTY: {html.escape(site_qty_text)} units"
            "</div>"
        )

    rows = []
    for task in selected:
        parsed = parse_task_status_value(task, row.get(task, ""))
        display_text = _format_schedule_task_display(row, task, row.get(task, "")) if is_schedule_column(task) else parsed["display_text"]
        rows.append(
            "<tr>"
            f"<td style='padding:4px 7px; font-weight:600; border-bottom:1px solid #eef2f7;'>{html.escape(task)}</td>"
            f"<td style='padding:4px 7px; border-bottom:1px solid #eef2f7;'>{html.escape(display_text)}</td>"
            "</tr>"
        )

    if show_all_tasks:
        remaining = [task for task in task_columns if task not in selected]
        if remaining:
            rows.append("<tr><td colspan='2' style='padding:7px; color:#4b5563; border-top:1px solid #d1d5db; font-weight:700;'>Other tasks</td></tr>")
        for task in remaining:
            parsed = parse_task_status_value(task, row.get(task, ""))
            display_text = _format_schedule_task_display(row, task, row.get(task, "")) if is_schedule_column(task) else parsed["display_text"]
            rows.append(
                "<tr>"
                f"<td style='padding:4px 7px; border-bottom:1px solid #eef2f7;'>{html.escape(task)}</td>"
                f"<td style='padding:4px 7px; border-bottom:1px solid #eef2f7;'>{html.escape(display_text)}</td>"
                "</tr>"
            )

    if not rows:
        rows.append("<tr><td colspan='2' style='padding:7px; color:#6b7280;'>No work item selected.</td></tr>")

    people_for_site = get_people_for_site(row, people_by_location)
    people_html = ""
    if people_for_site:
        people_names = "".join(f"<li>{html.escape(person.get('name', ''))}</li>" for person in people_for_site if person.get('name'))
        people_html = f"<div style='margin-top:9px; padding-top:7px; border-top:1px solid #d1d5db;'><div style='font-weight:800; font-size:12px; color:#111827; margin-bottom:3px;'>Assigned Staff</div><ul style='margin:0; padding-left:17px; font-size:12px; color:#111827;'>{people_names}</ul></div>"

    return f"""
    <div style="font-family:Arial, sans-serif; width:320px; color:#111827;">
      <div style="font-size:15px; font-weight:800; margin-bottom:2px; color:#000000;">{site_name}</div>
      <div style="font-size:12px; color:#374151; margin-bottom:3px;">{city_state}</div>
      {site_qty_html}
      <table style="border-collapse:collapse; width:100%; font-size:12px; color:#111827;">
        <thead>
          <tr style="background:#f3f4f6;"><th align="left" style="padding:4px 7px;">Task</th><th align="left" style="padding:4px 7px;">Status</th></tr>
        </thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
      {people_html}
    </div>
    """





class SiteStatusLegend(MacroElement):

    _template = Template(
        """
        {% macro script(this, kwargs) %}
        var {{ this.get_name() }} = L.control({position: 'bottomleft'});
        var {{ this.get_name() }}_legendDiv = null;
        {{ this.get_name() }}.onAdd = function (map) {
            var div = L.DomUtil.create('div', 'site-status-map-legend leaflet-control');
            div.innerHTML = {{ this.legend_html|tojson }};
            L.DomEvent.disableClickPropagation(div);
            L.DomEvent.disableScrollPropagation(div);
            {{ this.get_name() }}_legendDiv = div;
            return div;
        };
        {{ this.get_name() }}.addTo({{ this._parent.get_name() }});
        var {{ this.get_name() }}_style = document.createElement('style');
        {{ this.get_name() }}_style.innerHTML = `
            .site-status-map-legend {
                opacity: 1;
                transition: opacity 160ms ease, filter 160ms ease;
                z-index: 650 !important;
            }
            .site-status-map-legend.site-status-map-legend-dim {
                opacity: 0.28;
                filter: saturate(0.8);
            }
            .site-status-map-legend.site-status-map-legend-dim:hover {
                opacity: 0.96;
                filter: none;
            }
            .leaflet-popup-pane {
                z-index: 700 !important;
            }
        `;
        document.head.appendChild({{ this.get_name() }}_style);
        {{ this._parent.get_name() }}.on('popupopen', function () {
            if ({{ this.get_name() }}_legendDiv) {
                {{ this.get_name() }}_legendDiv.classList.add('site-status-map-legend-dim');
            }
        });
        {{ this._parent.get_name() }}.on('popupclose', function () {
            if ({{ this.get_name() }}_legendDiv) {
                {{ this.get_name() }}_legendDiv.classList.remove('site-status-map-legend-dim');
            }
        });
        {% endmacro %}
        """
    )

    def __init__(self, legend_html: str) -> None:
        super().__init__()
        self._name = "SiteStatusLegend"
        self.legend_html = legend_html


def add_legend_to_map(map_obj: folium.Map) -> None:
    legend_html = """
    <div style="
        background: #ffffff;
        color: #111827;
        border: 1px solid #9ca3af;
        border-radius: 8px;
        padding: 12px 14px;
        font-size: 13px;
        line-height: 1.55;
        font-weight: 600;
        box-shadow: 0 2px 10px rgba(0,0,0,0.25);
        max-width: 245px;
        max-height: 42vh;
        overflow-y: auto;
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
    map_obj.add_child(SiteStatusLegend(legend_html))



def build_site_marker_icon_html(row: pd.Series, selected_task_columns: list[str], color: str, people_by_location: dict[str, list[dict[str, Any]]] | None = None) -> str:
    label_html = build_site_label_html(row, selected_task_columns, show_labels=True, people_by_location=people_by_location)
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
    people_by_location: dict[str, list[dict[str, Any]]] | None = None,
) -> folium.Map:
    if df.empty:
        return folium.Map(location=[39.5, -98.35], zoom_start=4, tiles="CartoDB positron")

    bounds_df = df[["_latitude_num", "_longitude_num"]].dropna()
    center_lat = float(bounds_df["_latitude_num"].mean())
    center_lon = float(bounds_df["_longitude_num"].mean())
    initial_zoom = 10 if len(bounds_df) == 1 else 6
    map_obj = folium.Map(location=[center_lat, center_lon], zoom_start=initial_zoom, tiles="CartoDB positron", control_scale=True)
    Fullscreen(
        position="topleft",
        title="Full screen",
        title_cancel="Exit full screen",
        force_separate_button=True,
    ).add_to(map_obj)

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
        popup_html = build_popup_html(row, task_columns, selected_task_columns, show_all_tasks=show_all_tasks, people_by_location=people_by_location)
        popup = folium.Popup(popup_html, max_width=380)

        icon_html = build_site_marker_icon_html(row, selected_task_columns, color, people_by_location=people_by_location)
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
    people_by_location: dict[str, list[dict[str, Any]]] | None = None,
) -> None:
    if df.empty:
        st.info("No sites to display.")
        return
    map_obj = create_folium_map(df, task_columns, selected_task_columns, filters, options, people_by_location=people_by_location)
    map_key_material = "|".join(
        f"{row.get('location_id', '')}:{row.get('_latitude_num', '')}:{row.get('_longitude_num', '')}"
        for _, row in df.iterrows()
    )
    map_key = "site_status_map_" + hashlib.sha1(map_key_material.encode("utf-8")).hexdigest()[:12]
    map_data = st_folium(map_obj, width=None, height=680, returned_objects=["last_object_clicked"], key=map_key)
    clicked_site_id = _find_nearest_site_by_click(df, map_data.get("last_object_clicked") if map_data else None)
    if clicked_site_id:
        st.session_state.selected_site_id = clicked_site_id







def _get_schedule_column_name(columns: Any, target_name: str) -> str | None:
    return _find_case_insensitive_column(columns, target_name)


def _schedule_column_canonical(value: Any) -> str:
    return _canonical_name(value)


def _schedule_phase_for_column_name(column_name: Any) -> str | None:
    canonical = _schedule_column_canonical(column_name)
    if re.fullmatch(r"ccxstart\d*", canonical):
        return "CCx"
    if re.fullmatch(r"hcxstart\d*", canonical):
        return "HCx"
    return None


def _schedule_column_sequence(column_name: Any) -> int:
    canonical = _schedule_column_canonical(column_name)
    match = re.search(r"(\d+)$", canonical)
    return int(match.group(1)) if match else 1


def _is_schedule_start_column(column_name: Any) -> bool:
    return _schedule_phase_for_column_name(column_name) in {"CCx", "HCx"}


def _is_additional_schedule_start_column(column_name: Any) -> bool:
    if not _is_schedule_start_column(column_name):
        return False
    return _schedule_column_sequence(column_name) > 1


def is_schedule_unit_column(column_name: Any) -> bool:
    canonical = _schedule_column_canonical(column_name)
    return bool(re.fullmatch(r"(ccx|hcx)(units?|unitcount|equipment|equipmentcount|qty|quantity|count)\d*", canonical))


def _schedule_unit_column_sequence(column_name: Any) -> int:
    canonical = _schedule_column_canonical(column_name)
    match = re.search(r"(\d+)$", canonical)
    return int(match.group(1)) if match else 1


def _get_schedule_start_columns(columns: Any, phase: str) -> list[str]:
    phase_text = str(phase).strip().casefold()
    matched: list[tuple[int, int, str]] = []
    for order, col in enumerate(list(columns)):
        if _schedule_phase_for_column_name(col) == ("CCx" if phase_text == "ccx" else "HCx"):
            matched.append((_schedule_column_sequence(col), order, str(col)))
    return [col for _, _, col in sorted(matched, key=lambda item: (item[0], item[1]))]


def _get_schedule_unit_column_for_start(columns: Any, phase: str, start_column: Any) -> str | None:
    phase_prefix = "ccx" if str(phase).strip().casefold() == "ccx" else "hcx"
    sequence = _schedule_column_sequence(start_column)
    candidates: list[tuple[int, str]] = []
    for col in list(columns):
        canonical = _schedule_column_canonical(col)
        if not canonical.startswith(phase_prefix):
            continue
        if not is_schedule_unit_column(col):
            continue
        if _schedule_unit_column_sequence(col) != sequence:
            continue
        preference = 0
        if "unit" in canonical:
            preference = -3
        elif "equipment" in canonical:
            preference = -2
        elif "qty" in canonical or "quantity" in canonical:
            preference = -1
        candidates.append((preference, str(col)))
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: (item[0], item[1].casefold()))[0][1]


def _is_cod_column_name(column_name: Any) -> bool:
    canonical = _schedule_column_canonical(column_name)
    return bool(re.fullmatch(r"(?:cod|coddate|commercialoperation|commercialoperationdate)\d*", canonical))


def _cod_column_sequence(column_name: Any) -> int:
    canonical = _schedule_column_canonical(column_name)
    match = re.search(r"(\d+)$", canonical)
    return int(match.group(1)) if match else 1


def _is_additional_cod_column(column_name: Any) -> bool:
    return _is_cod_column_name(column_name) and _cod_column_sequence(column_name) > 1


def is_cod_unit_column(column_name: Any) -> bool:
    canonical = _schedule_column_canonical(column_name)
    return bool(re.fullmatch(r"(?:cod|commercialoperation)(?:units?|unitcount|equipment|equipmentcount|qty|quantity|count)\d*", canonical))


def _cod_unit_column_sequence(column_name: Any) -> int:
    canonical = _schedule_column_canonical(column_name)
    match = re.search(r"(\d+)$", canonical)
    return int(match.group(1)) if match else 1


def _get_cod_columns(columns: Any) -> list[str]:
    matched: list[tuple[int, int, str]] = []
    for order, col in enumerate(list(columns)):
        if _is_cod_column_name(col):
            matched.append((_cod_column_sequence(col), order, str(col)))
    return [col for _, _, col in sorted(matched, key=lambda item: (item[0], item[1]))]


def _get_cod_unit_column_for_date(columns: Any, cod_column: Any) -> str | None:
    sequence = _cod_column_sequence(cod_column)
    candidates: list[tuple[int, str]] = []
    for col in list(columns):
        canonical = _schedule_column_canonical(col)
        if not is_cod_unit_column(col):
            continue
        if _cod_unit_column_sequence(col) != sequence:
            continue
        preference = 0
        if "unit" in canonical:
            preference = -3
        elif "equipment" in canonical:
            preference = -2
        elif "qty" in canonical or "quantity" in canonical:
            preference = -1
        candidates.append((preference, str(col)))
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: (item[0], item[1].casefold()))[0][1]


def is_site_qty_column(column_name: Any) -> bool:
    canonical = _schedule_column_canonical(column_name)
    if not canonical:
        return False
    if canonical.startswith(("ccx", "hcx", "cod", "commercialoperation")):
        return False
    return canonical in {
        "qty",
        "quantity",
        "siteqty",
        "sitequantity",
        "siteequipmentqty",
        "siteequipmentquantity",
        "equipmentqty",
        "equipmentquantity",
        "equipmentcount",
        "totalqty",
        "totalquantity",
        "totalcount",
        "unitqty",
        "units",
        "totalunits",
        "installedqty",
        "installedquantity",
    }


def _get_site_qty_column(columns: Any) -> str | None:
    preference_order = {
        "qty": 0,
        "quantity": 1,
        "siteqty": 2,
        "sitequantity": 3,
        "equipmentqty": 4,
        "equipmentquantity": 5,
        "totalqty": 6,
        "totalquantity": 7,
    }
    candidates: list[tuple[int, int, str]] = []
    for order, col in enumerate(list(columns)):
        if not is_site_qty_column(col):
            continue
        canonical = _schedule_column_canonical(col)
        candidates.append((preference_order.get(canonical, 50), order, str(col)))
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: (item[0], item[1]))[0][2]


def _get_row_total_equipment_qty(row: pd.Series) -> float | None:
    qty_col = _get_site_qty_column(row.index)
    if qty_col is None:
        return None
    return _parse_equipment_units(row.get(qty_col, ""))


def _is_additional_schedule_quantity_event(event: dict[str, Any]) -> bool:
    return int(event.get("sequence", 1) or 1) > 1 or int(event.get("entry_order", 0) or 0) > 0


def _assign_qty_based_default_units(events: list[dict[str, Any]], total_units: float | None) -> list[dict[str, Any]]:
    if total_units is None or total_units <= 0:
        return events

    explicit_additional_units = 0.0
    for event in events:
        if _is_additional_schedule_quantity_event(event) and event.get("units_explicit") and event.get("units") is not None:
            explicit_additional_units += float(event["units"])

    remaining_units = max(float(total_units) - explicit_additional_units, 0.0)
    base_candidates = [
        event
        for event in events
        if not event.get("units_explicit")
        and int(event.get("sequence", 1) or 1) == 1
        and int(event.get("entry_order", 0) or 0) == 0
    ]
    if base_candidates:
        # The first base schedule receives the QTY remainder. This preserves the old one-row schedule model
        # while allowing later added schedules such as 2026-08-03(6) to be deducted from the site QTY.
        base_candidates[0]["units"] = remaining_units
        base_candidates[0]["units_source"] = "qty_remaining"
        base_candidates[0]["units_explicit"] = False
    return events


def _parse_equipment_units(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    if not text or text.lower() in NA_VALUES or text in DASH_PLACEHOLDERS:
        return None
    match = re.search(r"\d+(?:\.\d+)?", text.replace(",", ""))
    if not match:
        return None
    try:
        units = float(match.group(0))
    except ValueError:
        return None
    return units if units > 0 else None


def _format_equipment_units(units: float | None) -> str:
    if units is None:
        return ""
    value = units
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.1f}".rstrip("0").rstrip(".")


def _calculate_commissioning_duration_days(phase: str, units: float | None) -> int:
    base_days = CCX_BASE_DURATION_DAYS if str(phase).strip().casefold() == "ccx" else HCX_BASE_DURATION_DAYS
    unit_value = COMMISSIONING_BASE_UNITS if units is None else max(float(units), 1.0)
    scaled_days = math.ceil(unit_value / COMMISSIONING_BASE_UNITS * base_days)
    return max(COMMISSIONING_MIN_DURATION_DAYS, int(scaled_days))


def _split_schedule_entries(value: Any) -> list[str]:
    if value is None or pd.isna(value):
        return []
    text = str(value).strip()
    if not text:
        return []
    entries = [entry.strip() for entry in SCHEDULE_ENTRY_SPLIT_RE.split(text) if entry.strip()]
    return entries if entries else [text]


def _parse_schedule_entry_date(entry: Any) -> datetime | None:
    if entry is None or pd.isna(entry):
        return None
    text = str(entry).strip()
    if not text or text.lower() in NA_VALUES or text in DASH_PLACEHOLDERS or _is_commercial_operation_value(text):
        return None
    match = SCHEDULE_DATE_TOKEN_RE.search(text)
    date_text = match.group("date") if match else text
    parsed = pd.to_datetime(date_text, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.to_pydatetime().replace(hour=0, minute=0, second=0, microsecond=0)


def _parse_inline_units(entry: Any) -> float | None:
    if entry is None or pd.isna(entry):
        return None
    text = str(entry).strip()
    match = SCHEDULE_UNIT_TOKEN_RE.search(text)
    if not match:
        return None
    try:
        units = float(match.group("units"))
    except ValueError:
        return None
    return units if units > 0 else None


def _parse_schedule_date(value: Any) -> datetime | None:
    entries = _split_schedule_entries(value)
    if len(entries) != 1:
        return None
    return _parse_schedule_entry_date(entries[0])


def _format_schedule_date(value: Any) -> str:
    if _is_commercial_operation_value(value):
        return GANTT_COMMERCIAL_OPERATION_LABEL
    parsed = _parse_schedule_date(value)
    return parsed.strftime("%Y-%m-%d") if parsed else "—"


def _is_commercial_operation_value(value: Any) -> bool:
    if value is None or pd.isna(value):
        return False
    return str(value).strip().casefold() == GANTT_COMMERCIAL_OPERATION_LABEL.casefold()


def _has_legacy_commercial_operation_entry(value: Any) -> bool:
    """Return True when one of the comma/semicolon-delimited schedule entries is Commercial Operation."""
    return any(_is_commercial_operation_value(entry) for entry in _split_schedule_entries(value))


def _phase_has_legacy_commercial_operation(row: pd.Series, phase: str) -> bool:
    return any(
        _has_legacy_commercial_operation_entry(row.get(col, ""))
        for col in _get_schedule_start_columns(row.index, phase)
    )


def _entry_is_schedule_placeholder(entry: Any) -> bool:
    if entry is None or pd.isna(entry):
        return True
    text = str(entry).strip()
    return (
        not text
        or text.lower() in NA_VALUES
        or text in DASH_PLACEHOLDERS
        or _is_commercial_operation_value(text)
    )


def _format_qty_display(units: float | None, compact: bool = False) -> str:
    units_text = _format_equipment_units(units)
    if not units_text:
        return ""
    return f"Q{units_text}" if compact else f"Qty {units_text}"


def _schedule_event_display(event: dict[str, Any]) -> str:
    start = event.get("start")
    if not isinstance(start, datetime):
        return "—"
    qty_text = _format_qty_display(event.get("units"))
    if not qty_text:
        return start.strftime("%Y-%m-%d")
    return f"{start.strftime('%Y-%m-%d')} · {qty_text}"


def _format_schedule_events_for_phase(row: pd.Series, phase: str) -> str:
    events = [event for event in _get_schedule_events_for_row(row) if event.get("type") == phase]
    display_items: list[str] = []
    if _phase_has_legacy_commercial_operation(row, phase):
        display_items.append(GANTT_COMMERCIAL_OPERATION_LABEL)
    if events:
        events.sort(key=lambda item: (item["start"], int(item.get("sequence", 1)), int(item.get("entry_order", 0)), str(item.get("source_col", ""))))
        display_items.extend(_schedule_event_display(event) for event in events)
    return ", ".join(display_items) if display_items else "—"


def _format_cod_events_for_row(row: pd.Series) -> str:
    events = _get_cod_events_for_row(row)
    if not events:
        return "—"
    events.sort(key=lambda item: (item["start"], int(item.get("sequence", 1)), int(item.get("entry_order", 0)), str(item.get("source_col", ""))))
    return ", ".join(_schedule_event_display(event) for event in events)


def _format_schedule_task_display(row: pd.Series, task_name: str, value: Any) -> str:
    phase = _schedule_phase_for_column_name(task_name)
    if phase in {"CCx", "HCx"}:
        if _schedule_column_sequence(task_name) == 1:
            return _format_schedule_events_for_phase(row, phase)
        events = [
            event
            for event in _get_schedule_events_for_row(row)
            if event.get("type") == phase and _canonical_name(event.get("source_col", "")) == _canonical_name(task_name)
        ]
        if events:
            events.sort(key=lambda item: (item["start"], int(item.get("entry_order", 0))))
            return ", ".join(_schedule_event_display(event) for event in events)
    if _is_cod_column_name(task_name):
        if _cod_column_sequence(task_name) == 1:
            return _format_cod_events_for_row(row)
        events = [
            event
            for event in _get_cod_events_for_row(row)
            if _canonical_name(event.get("source_col", "")) == _canonical_name(task_name)
        ]
        if events:
            events.sort(key=lambda item: (item["start"], int(item.get("entry_order", 0))))
            return ", ".join(_schedule_event_display(event) for event in events)
    parsed = _parse_schedule_date(value)
    qty_text = _format_qty_display(_parse_inline_units(value))
    if parsed and qty_text:
        return f"{parsed.strftime('%Y-%m-%d')} · {qty_text}"
    return parsed.strftime("%Y-%m-%d") if parsed else str(value).strip()


def _add_months(dt: datetime, months: int) -> datetime:
    month = dt.month - 1 + months
    year = dt.year + month // 12
    month = month % 12 + 1
    days_in_month = [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28, 31, 30, 31, 31, 30, 31, 30, 31, 30, 31]
    # Correct the fixed list length defensively.
    days_in_month = [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    day = min(dt.day, days_in_month[month - 1])
    return dt.replace(year=year, month=month, day=day)


def _date_pct(dt: datetime, window_start: datetime, window_end: datetime) -> float:
    total_seconds = max((window_end - window_start).total_seconds(), 1)
    return max(0.0, min(100.0, (dt - window_start).total_seconds() / total_seconds * 100.0))


def _get_schedule_events_for_row(row: pd.Series) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    total_units = _get_row_total_equipment_qty(row)

    for phase in ("CCx", "HCx"):
        phase_events: list[dict[str, Any]] = []
        for start_col in _get_schedule_start_columns(row.index, phase):
            raw_value = row.get(start_col, "")
            raw_text = str(raw_value).strip()
            if not raw_text or raw_text.lower() in NA_VALUES or raw_text in DASH_PLACEHOLDERS or _is_commercial_operation_value(raw_text):
                continue

            sequence = _schedule_column_sequence(start_col)
            unit_col = _get_schedule_unit_column_for_start(row.index, phase, start_col)
            column_units = _parse_equipment_units(row.get(unit_col, "")) if unit_col is not None else None

            for entry_order, entry in enumerate(_split_schedule_entries(raw_value)):
                start_date = _parse_schedule_entry_date(entry)
                if start_date is None:
                    continue

                inline_units = _parse_inline_units(entry)
                units = inline_units
                units_explicit = inline_units is not None

                # For the first/base CCx or HCx schedule, the site-level QTY is the source of truth.
                # Existing CCx Units / HCx Units columns are still supported when QTY is absent,
                # but they no longer force every site to display the default 90 units.
                if units is None:
                    if sequence == 1 and total_units is not None:
                        units = None  # Assigned after additional explicit quantities are deducted.
                        units_explicit = False
                    elif column_units is not None:
                        units = column_units
                        units_explicit = True

                phase_events.append(
                    {
                        "type": phase,
                        "start": start_date,
                        "color": GANTT_CCX_COLOR if phase == "CCx" else GANTT_HCX_COLOR,
                        "units": units,
                        "units_explicit": units_explicit,
                        "units_source": "inline" if inline_units is not None else ("column" if units_explicit else "qty_pending"),
                        "source_col": str(start_col),
                        "unit_col": str(unit_col) if unit_col is not None else "",
                        "sequence": sequence,
                        "entry_order": entry_order,
                    }
                )

        phase_events = _assign_qty_based_default_units(phase_events, total_units)
        for event in phase_events:
            event["duration_days"] = _calculate_commissioning_duration_days(phase, event.get("units"))
        events.extend(phase_events)

    events.sort(key=lambda item: (item["start"], 0 if item["type"] == "CCx" else 1, int(item.get("sequence", 1)), int(item.get("entry_order", 0))))
    return events

def _get_cod_column_name(columns: Any) -> str | None:
    cod_cols = _get_cod_columns(columns)
    return cod_cols[0] if cod_cols else None


def _get_cod_events_for_row(row: pd.Series) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    total_units = _get_row_total_equipment_qty(row)

    for cod_col in _get_cod_columns(row.index):
        raw_value = row.get(cod_col, "")
        raw_text = str(raw_value).strip()
        if not raw_text or raw_text.lower() in NA_VALUES or raw_text in DASH_PLACEHOLDERS:
            continue

        sequence = _cod_column_sequence(cod_col)
        unit_col = _get_cod_unit_column_for_date(row.index, cod_col)
        column_units = _parse_equipment_units(row.get(unit_col, "")) if unit_col is not None else None

        for entry_order, entry in enumerate(_split_schedule_entries(raw_value)):
            cod_date = _parse_schedule_entry_date(entry)
            if cod_date is None:
                continue

            inline_units = _parse_inline_units(entry)
            units = inline_units
            units_explicit = inline_units is not None

            if units is None:
                if sequence == 1 and total_units is not None:
                    units = None
                    units_explicit = False
                elif column_units is not None:
                    units = column_units
                    units_explicit = True

            events.append(
                {
                    "type": "COD",
                    "start": cod_date,
                    "end": cod_date,
                    "color": GANTT_COD_COLOR,
                    "units": units,
                    "units_explicit": units_explicit,
                    "units_source": "inline" if inline_units is not None else ("column" if units_explicit else "qty_pending"),
                    "source_col": str(cod_col),
                    "unit_col": str(unit_col) if unit_col is not None else "",
                    "sequence": sequence,
                    "entry_order": entry_order,
                    "marker": "cod",
                }
            )

    events = _assign_qty_based_default_units(events, total_units)
    events.sort(key=lambda item: (item["start"], int(item.get("sequence", 1)), int(item.get("entry_order", 0)), str(item.get("source_col", ""))))
    return events

def _get_cod_date_for_row(row: pd.Series) -> datetime | None:
    """Return the latest COD date. Commercial Operation starts only after the final COD schedule has passed."""
    cod_events = _get_cod_events_for_row(row)
    cod_dates = [event["start"] for event in cod_events if isinstance(event.get("start"), datetime)]
    if not cod_dates:
        return None
    return max(cod_dates)


def _row_has_legacy_commercial_operation(row: pd.Series) -> bool:
    return any(
        _has_legacy_commercial_operation_entry(row.get(col, ""))
        for col in _get_schedule_start_columns(row.index, "CCx") + _get_schedule_start_columns(row.index, "HCx")
    )


def _today_start(today: datetime | None = None) -> datetime:
    return (today or datetime.now()).replace(hour=0, minute=0, second=0, microsecond=0)


def _row_has_cod_commercial_operation(row: pd.Series, today: datetime | None = None) -> bool:
    latest_cod_date = _get_cod_date_for_row(row)
    if latest_cod_date is None:
        return False
    return latest_cod_date <= _today_start(today)


def _row_has_commercial_operation(row: pd.Series, today: datetime | None = None) -> bool:
    # When COD schedules exist, COD is the source of truth: Commercial Operation starts after the final COD date.
    if _get_cod_events_for_row(row):
        return _row_has_cod_commercial_operation(row, today)
    return _row_has_legacy_commercial_operation(row)


def _build_schedule_segments_from_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    for event in events:
        start = event["start"]
        duration_days = int(event.get("duration_days") or _calculate_commissioning_duration_days(event.get("type", "CCx"), event.get("units")))
        end = start + timedelta(days=duration_days)
        segments.append({**event, "start": start, "end": end, "color": event["color"]})
    return segments


def get_current_schedule_phase(row: pd.Series, today: datetime | None = None) -> str | None:
    current_day = _today_start(today)
    active_segments = []
    for segment in _build_schedule_segments_from_events(_get_schedule_events_for_row(row)):
        if segment["start"] <= current_day < segment["end"]:
            active_segments.append(segment)
    if active_segments:
        active_segments.sort(key=lambda item: (0 if item["type"] == "HCx" else 1, item["start"]))
        return str(active_segments[0]["type"])
    if _row_has_commercial_operation(row, current_day):
        return GANTT_COMMERCIAL_OPERATION_LABEL
    return None


def _default_gantt_window(today: datetime) -> tuple[datetime, datetime]:
    return today - timedelta(days=GANTT_LOOKBACK_DAYS), _add_months(today, GANTT_LOOKAHEAD_MONTHS)


def _all_schedule_window(df: pd.DataFrame, today: datetime) -> tuple[datetime, datetime]:
    all_dates: list[datetime] = []
    for _, row in df.iterrows():
        for segment in _build_schedule_segments_from_events(_get_schedule_events_for_row(row)):
            all_dates.append(segment["start"])
            all_dates.append(segment["end"])
        for cod_event in _get_cod_events_for_row(row):
            if cod_event.get("start") is not None:
                all_dates.append(cod_event["start"])
    if not all_dates:
        return _default_gantt_window(today)
    window_start = min(all_dates)
    window_end = max(all_dates) + timedelta(days=GANTT_SHOW_ALL_END_PADDING_DAYS)
    if window_end <= window_start:
        window_end = window_start + timedelta(days=GANTT_SHOW_ALL_END_PADDING_DAYS)
    return window_start, window_end


def _build_gantt_rows(
    df: pd.DataFrame,
    include_all_schedules: bool,
) -> tuple[list[dict[str, Any]], datetime, datetime, datetime, bool]:
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    cc_cols = _get_schedule_start_columns(df.columns, "CCx")
    hc_cols = _get_schedule_start_columns(df.columns, "HCx")
    cod_cols = _get_cod_columns(df.columns)
    if not cc_cols and not hc_cols and not cod_cols:
        window_start, window_end = _default_gantt_window(today)
        return [], window_start, window_end, today, False

    window_start, window_end = _all_schedule_window(df, today) if include_all_schedules else _default_gantt_window(today)

    rows: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        location_name = _get_site_display_name(row)
        location_id = str(row.get("location_id", "")).strip()
        cod_events = _get_cod_events_for_row(row)
        cod_dates = [event["start"] for event in cod_events if isinstance(event.get("start"), datetime)]
        latest_cod_date = max(cod_dates) if cod_dates else None
        raw_events = _get_schedule_events_for_row(row)
        is_legacy_commercial = _row_has_legacy_commercial_operation(row)
        is_cod_commercial = latest_cod_date is not None and latest_cod_date <= today
        # If COD exists, the latest COD date is the source of truth. Legacy Commercial Operation text is retained as display history only.
        is_commercial = is_cod_commercial if latest_cod_date is not None else is_legacy_commercial

        segments: list[dict[str, Any]] = []

        raw_segments = _build_schedule_segments_from_events(raw_events)
        for segment in raw_segments:
            start = segment["start"]
            end = segment["end"]

            if not include_all_schedules and start + timedelta(days=GANTT_COMPLETED_HIDE_AFTER_DAYS) < today:
                continue
            visible_start = max(start, window_start)
            visible_end = min(end, window_end)
            if visible_end <= window_start or visible_start >= window_end or visible_end <= visible_start:
                continue
            segments.append(
                {
                    "type": segment["type"],
                    "start": start,
                    "end": end,
                    "visible_start": visible_start,
                    "visible_end": visible_end,
                    "color": segment["color"],
                    "left": _date_pct(visible_start, window_start, window_end),
                    "width": max(0.5, _date_pct(visible_end, window_start, window_end) - _date_pct(visible_start, window_start, window_end)),
                    "row_top": "8px" if segment["type"] == "CCx" else "31px",
                    "units": segment.get("units"),
                    "duration_days": segment.get("duration_days"),
                }
            )

        for cod_event in cod_events:
            cod_date = cod_event["start"]
            if window_start <= cod_date <= window_end:
                segments.append(
                    {
                        "type": "COD",
                        "start": cod_date,
                        "end": cod_date,
                        "visible_start": cod_date,
                        "visible_end": cod_date,
                        "color": GANTT_COD_COLOR,
                        "left": _date_pct(cod_date, window_start, window_end),
                        "width": 0.0,
                        "row_top": "20px",
                        "marker": "cod",
                        "units": cod_event.get("units"),
                        "sequence": cod_event.get("sequence"),
                        "entry_order": cod_event.get("entry_order"),
                    }
                )

        commercial_start: datetime | None = None
        if latest_cod_date is not None:
            commercial_start = latest_cod_date
        elif is_legacy_commercial:
            commercial_start = window_start

        if include_all_schedules and commercial_start is not None and commercial_start < window_end:
            visible_start = max(commercial_start, window_start)
            visible_end = window_end
            if visible_end > visible_start:
                segments.append(
                    {
                        "type": GANTT_COMMERCIAL_OPERATION_LABEL,
                        "start": commercial_start,
                        "end": window_end,
                        "visible_start": visible_start,
                        "visible_end": visible_end,
                        "color": GANTT_COMMERCIAL_COLOR,
                        "left": _date_pct(visible_start, window_start, window_end),
                        "width": max(0.5, _date_pct(visible_end, window_start, window_end) - _date_pct(visible_start, window_start, window_end)),
                        "row_top": "19px",
                    }
                )

        if not segments:
            continue
        sort_candidates = [segment["start"] for segment in segments if segment.get("start") is not None]
        sort_date = min(sort_candidates) if sort_candidates else window_end + timedelta(days=1)

        rows.append(
            {
                "location_name": location_name,
                "location_id": location_id,
                "cc_display": _format_schedule_events_for_phase(row, "CCx"),
                "hc_display": _format_schedule_events_for_phase(row, "HCx"),
                "cod_display": _format_cod_events_for_row(row),
                "segments": segments,
                "sort_date": sort_date,
                "is_commercial_operation": is_commercial,
                "has_cod": bool(cod_events),
            }
        )

    rows.sort(
        key=lambda item: (
            1 if item.get("is_commercial_operation") else 0,
            item["sort_date"],
            str(item["location_name"]).casefold(),
            str(item["location_id"]),
        )
    )
    return rows, window_start, window_end, today, include_all_schedules

def _format_gantt_axis_date(dt: datetime) -> str:
    return f"{dt.month}/{dt.day}"


def _get_gantt_base_tick_step_days(total_days: int) -> int:
    if total_days <= 21:
        return 2
    if total_days <= 75:
        return 7
    if total_days <= 180:
        return 14
    return 30


def _build_gantt_axis_ticks_for_step(
    window_start: datetime,
    window_end: datetime,
    step_days: int,
    css_class: str,
) -> str:
    ticks: list[str] = []
    cursor = window_start
    step_days = max(int(step_days), 1)
    while cursor <= window_end:
        left = _date_pct(cursor, window_start, window_end)
        label = _format_gantt_axis_date(cursor)
        ticks.append(
            f"<div class='gantt-tick {css_class}' style='left:{left:.3f}%;'><span>{html.escape(label)}</span></div>"
        )
        cursor += timedelta(days=step_days)

    if not ticks or cursor - timedelta(days=step_days) < window_end:
        left = _date_pct(window_end, window_start, window_end)
        label = _format_gantt_axis_date(window_end)
        ticks.append(
            f"<div class='gantt-tick {css_class} gantt-tick-end' style='left:{left:.3f}%;'><span>{html.escape(label)}</span></div>"
        )
    return "".join(ticks)


def _build_gantt_axis_ticks(window_start: datetime, window_end: datetime) -> str:
    total_days = max((window_end - window_start).days, 1)
    base_step = _get_gantt_base_tick_step_days(total_days)

    medium_step = max(base_step * 2, base_step + 1)
    narrow_step = max(base_step * 3, medium_step + 1)

    return "".join(
        [
            _build_gantt_axis_ticks_for_step(window_start, window_end, base_step, "gantt-tick-wide"),
            _build_gantt_axis_ticks_for_step(window_start, window_end, medium_step, "gantt-tick-medium"),
            _build_gantt_axis_ticks_for_step(window_start, window_end, narrow_step, "gantt-tick-narrow"),
        ]
    )


def _build_gantt_html(rows: list[dict[str, Any]], window_start: datetime, window_end: datetime, today: datetime, include_all_schedules: bool) -> str:
    today_left = _date_pct(today, window_start, window_end)
    axis_ticks = _build_gantt_axis_ticks(window_start, window_end)
    row_html: list[str] = []
    table_rows: list[str] = []

    for item in rows:
        safe_location = html.escape(str(item["location_name"]))
        safe_location_id = html.escape(str(item.get("location_id", "")))
        row_class = "gantt-row gantt-commercial-row" if item.get("is_commercial_operation") else "gantt-row"
        table_row_class = "gantt-table-row gantt-commercial-table-row" if item.get("is_commercial_operation") else "gantt-table-row"
        bars = []
        for segment in item["segments"]:
            segment_type = str(segment["type"])
            if segment.get("marker") == "cod":
                cod_units = segment.get("units")
                qty_text = _format_qty_display(cod_units)
                tooltip_qty = f" · Qty: {_format_equipment_units(cod_units)} units" if cod_units is not None else ""
                tooltip = f"{item['location_name']} · COD · {segment['start'].strftime('%Y-%m-%d')}{tooltip_qty}"
                cod_label = f"COD · {qty_text}" if qty_text else "COD"
                bars.append(
                    "<div "
                    "class='gantt-cod-marker' "
                    f"title='{html.escape(tooltip)}' "
                    f"style='left:{segment['left']:.3f}%; top:{segment['row_top']};'>"
                    "<span class='gantt-cod-diamond'></span>"
                    f"<span class='gantt-cod-label'>{html.escape(cod_label)}</span>"
                    "</div>"
                )
                continue

            is_commercial_segment = segment_type == GANTT_COMMERCIAL_OPERATION_LABEL
            bar_class = "gantt-bar-commercial" if is_commercial_segment else f"gantt-bar-{segment_type.lower()}"
            if is_commercial_segment:
                tooltip = f"{item['location_name']} · {segment_type} · {segment['start'].strftime('%Y-%m-%d')} to {segment['end'].strftime('%Y-%m-%d')}"
                label = GANTT_COMMERCIAL_OPERATION_LABEL
            else:
                units_label = _format_equipment_units(segment.get("units"))
                qty_text = _format_qty_display(segment.get("units"))
                duration_label = int(segment.get("duration_days") or (segment["end"] - segment["start"]).days)
                units_part = f" · Qty: {units_label} units" if units_label else ""
                tooltip = f"{item['location_name']} · {segment_type} · {segment['start'].strftime('%Y-%m-%d')} to {segment['end'].strftime('%Y-%m-%d')}{units_part} · Duration: {duration_label} days"
                label = f"{segment_type} · {qty_text}" if qty_text else segment_type
            bars.append(
                "<div "
                f"class='gantt-bar {bar_class}' "
                f"title='{html.escape(tooltip)}' "
                f"style='left:{segment['left']:.3f}%; width:{segment['width']:.3f}%; top:{segment['row_top']}; background:{html.escape(segment['color'])};'>"
                f"<span>{html.escape(label)}</span>"
                "</div>"
            )
        row_html.append(
            f"<div class='{row_class}'>"
            f"<div class='gantt-location-label' title='{safe_location_id}'>{safe_location}</div>"
            "<div class='gantt-track'>"
            f"<div class='gantt-today-line' style='left:{today_left:.3f}%;'></div>"
            f"{''.join(bars)}"
            "</div>"
            "</div>"
        )
        cod_display = str(item.get('cod_display', '—') or '—')
        cod_cell_class = "gantt-table-cell gantt-table-cod-cell" if cod_display != "—" else "gantt-table-cell"
        table_rows.append(
            f"<div class='{table_row_class}'>"
            f"<div class='gantt-table-cell gantt-table-location'>{safe_location}</div>"
            f"<div class='gantt-table-cell'>{html.escape(str(item.get('cc_display', '—') or '—'))}</div>"
            f"<div class='gantt-table-cell'>{html.escape(str(item.get('hc_display', '—') or '—'))}</div>"
            f"<div class='{cod_cell_class}'>{html.escape(cod_display)}</div>"
            "</div>"
        )

    return f"""
    <div class='gantt-container'>
        <div class='gantt-legend-row'>
            <span class='gantt-window-label'>Window: {html.escape(window_start.strftime('%Y-%m-%d'))} to {html.escape(window_end.strftime('%Y-%m-%d'))}</span>
            <span class='gantt-legend-group' aria-label='CCx HCx COD Commercial Operation legend'>
                <span class='gantt-legend-item'><span class='gantt-legend-dot gantt-legend-ccx'></span>CCx</span>
                <span class='gantt-legend-item'><span class='gantt-legend-dot gantt-legend-hcx'></span>HCx</span>
                <span class='gantt-legend-item'><span class='gantt-legend-cod-diamond'></span>COD</span>
                <span class='gantt-legend-item'><span class='gantt-legend-dot gantt-legend-co'></span>Commercial Operation</span>
            </span>
        </div>
        <div class='gantt-layout'>
            <div class='gantt-chart-scroll' aria-label='Responsive CCx HCx and COD Gantt chart'>
                <div class='gantt-chart-panel'>
                    <div class='gantt-axis gantt-axis-top'>
                        <div class='gantt-axis-track'>{axis_ticks}<div class='gantt-today-axis' style='left:{today_left:.3f}%;'><span>Today</span></div></div>
                    </div>
                    <div class='gantt-rows'>
                        {''.join(row_html)}
                    </div>
                    <div class='gantt-axis gantt-axis-bottom' aria-label='Bottom Gantt date axis'>
                        <div class='gantt-axis-track'>{axis_ticks}<div class='gantt-today-axis' style='left:{today_left:.3f}%;'><span>Today</span></div></div>
                    </div>
                </div>
            </div>
            <div class='gantt-table-panel'>
                <div class='gantt-table'>
                    <div class='gantt-table-header'><div>Location</div><div>CCx Schedule</div><div>HCx Schedule</div><div>COD</div></div>
                    <div class='gantt-table-body'>{''.join(table_rows)}</div>
                </div>
            </div>
        </div>
    </div>
    """


def render_gantt_chart_section(df: pd.DataFrame) -> None:
    include_all = st.checkbox(
        "Show All CCx/HCx/COD Schedules",
        value=False,
        key="gantt_show_all_schedules",
    )
    rows, window_start, window_end, today, include_all_schedules = _build_gantt_rows(df, include_all_schedules=include_all)
    if not rows:
        cc_cols = _get_schedule_start_columns(df.columns, "CCx")
        hc_cols = _get_schedule_start_columns(df.columns, "HCx")
        cod_cols = _get_cod_columns(df.columns)
        if not cc_cols and not hc_cols and not cod_cols:
            st.info("No `CCx Start`, `HCx Start`, or `COD` columns were found in the active CSV.")
        else:
            st.info("No CCx/HCx/COD schedule rows fall within the current Gantt display window.")
        return
    render_safe_html(_build_gantt_html(rows, window_start, window_end, today, include_all_schedules))




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
        .kpi-card-row-secondary {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 1rem;
            align-items: stretch;
            margin-bottom: 0.75rem;
        }
        .kpi-card-span-2 {
            grid-column: span 2;
        }
        .people-kpi-lines {
            display: flex;
            flex-direction: column;
            gap: 0.32rem;
            color: #111827;
            font-size: 0.78rem;
            font-weight: 800;
            line-height: 1.28;
        }
        .people-kpi-line {
            background: #f8fafc;
            border: 1px solid #e2e8f0;
            border-radius: 0.48rem;
            padding: 0.32rem 0.44rem;
            word-break: break-word;
            display: flex;
            align-items: center;
            flex-wrap: wrap;
            gap: 0.24rem;
        }
        .people-kpi-site-name {
            color: #111827;
            font-weight: 950;
            margin-right: 0.05rem;
        }
        .people-kpi-count {
            background: #e2e8f0;
            border: 1px solid #cbd5e1;
            border-radius: 999px;
            color: #0f172a;
            font-size: 0.72rem;
            font-weight: 950;
            padding: 0.04rem 0.38rem;
            line-height: 1.15;
        }
        .people-kpi-badge-list {
            display: inline-flex;
            align-items: center;
            flex-wrap: wrap;
            gap: 0.22rem;
        }
        .people-kpi-paren {
            color: #475569;
            font-weight: 900;
        }
        .people-name-badge {
            text-transform: uppercase;
        }
        @media (max-width: 900px) {
            .kpi-card-row-secondary {
                grid-template-columns: 1fr;
            }
            .kpi-card-span-2 {
                grid-column: span 1;
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
        .kpi-site-pill-ccx-active {
            background: #bae6fd !important;
            border-color: #38bdf8 !important;
            color: #0f172a !important;
        }
        .kpi-site-pill-hcx-active {
            background: #fbcfe8 !important;
            border-color: #f472b6 !important;
            color: #0f172a !important;
        }
        .kpi-site-pill-commercial-operation {
            background: #fef08a !important;
            border-color: #facc15 !important;
            color: #111827 !important;
        }
        .kpi-site-pill-active-pre-cod {
            background: #f8fafc !important;
            border-color: #cbd5e1 !important;
            color: #111827 !important;
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
            background: #f8fafc;
            border: 1px solid #e2e8f0;
            border-radius: 0.55rem;
            padding: 0.34rem 0.48rem;
        }
        .kpi-version-group-version-1-0 .kpi-version-header {
            background: #ccfbf1;
            border-color: #2dd4bf;
        }
        .kpi-version-group-version-1-5 .kpi-version-header {
            background: #f3e8ff;
            border-color: #c084fc;
        }
        .kpi-version-group-version-other .kpi-version-header {
            background: #f8fafc;
            border-color: #cbd5e1;
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
        .site-version-row { margin: 2px 0 3px 0; }
        .site-version-badge {
            display: inline-block;
            border-radius: 999px;
            padding: 1px 7px;
            font-size: 10px;
            font-weight: 900;
            line-height: 1.25;
            border: 1px solid rgba(17,24,39,0.18);
            color: #ffffff;
            white-space: nowrap;
            box-shadow: 0 1px 3px rgba(15,23,42,0.22);
            letter-spacing: 0.01em;
        }
        .site-version-badge-version-1-0 {
            background: #0f766e;
            border-color: #2dd4bf;
            color: #ffffff;
        }
        .site-version-badge-version-1-5 {
            background: #7c3aed;
            border-color: #c084fc;
            color: #ffffff;
        }
        .site-version-badge-version-other {
            background: #475569;
            border-color: #94a3b8;
            color: #ffffff;
        }
        .kpi-version-header .site-version-badge {
            font-size: 0.74rem;
            padding: 0.18rem 0.55rem;
            line-height: 1.15;
        }
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
    st.markdown(
        f"""
        <style>
        div[data-testid="stExpander"] summary p,
        div[data-testid="stExpander"] summary span {{
            font-size: 1.35rem !important;
            font-weight: 800 !important;
            line-height: 1.35 !important;
        }}
        .gantt-container {{
            background: #ffffff;
            color: #111827;
            border: 1px solid #9ca3af;
            border-radius: 0.9rem;
            padding: 0.95rem;
            overflow: hidden;
            box-shadow: 0 1px 5px rgba(0,0,0,0.16);
        }}
        .gantt-container * {{
            box-sizing: border-box;
        }}
        .gantt-legend-row {{
            display: flex;
            align-items: center;
            flex-wrap: wrap;
            gap: 0.75rem;
            margin-bottom: 0.75rem;
            color: #111827;
            font-size: 0.88rem;
            font-weight: 800;
        }}
        .gantt-window-label {{
            margin-right: auto;
            color: #111827;
        }}
        .gantt-legend-group {{
            display: inline-flex;
            align-items: center;
            flex-wrap: nowrap;
            gap: 0.75rem;
            white-space: nowrap;
            flex: 0 0 auto;
        }}
        .gantt-legend-item {{ display: inline-flex; align-items: center; gap: 0.3rem; color:#111827; }}
        .gantt-legend-dot {{ width: 0.75rem; height: 0.75rem; border-radius: 999px; display: inline-block; border:1px solid rgba(17,24,39,0.25); }}
        .gantt-legend-ccx {{ background: {GANTT_CCX_COLOR}; }}
        .gantt-legend-hcx {{ background: {GANTT_HCX_COLOR}; }}
        .gantt-legend-co {{ background: {GANTT_COMMERCIAL_COLOR}; }}
        .gantt-legend-cod-diamond {{
            width: 0.72rem;
            height: 0.72rem;
            display: inline-block;
            background: {GANTT_COD_COLOR};
            border: 1px solid rgba(17,24,39,0.35);
            transform: rotate(45deg);
            margin-right: 0.1rem;
        }}
        .gantt-layout {{
            display: grid;
            grid-template-columns: minmax(0, 1fr) minmax(250px, 0.28fr);
            gap: 0.8rem;
            align-items: stretch;
        }}
        .gantt-chart-scroll {{
            overflow: hidden;
            border: 1px solid rgba(148,163,184,0.45);
            border-radius: 0.65rem;
            background: #ffffff;
            min-width: 0;
            height: 100%;
        }}
        .gantt-chart-panel {{
            width: 100%;
            min-width: 0;
            padding: 0.15rem 0.25rem 0.25rem 0.25rem;
        }}
        .gantt-axis {{
            display: grid;
            grid-template-columns: {GANTT_ROW_LABEL_WIDTH_PX}px minmax(0, 1fr);
            min-height: 42px;
        }}
        .gantt-axis-top {{
            margin-bottom: 0.15rem;
        }}
        .gantt-axis-bottom {{
            margin-top: 0.15rem;
        }}
        .gantt-axis::before {{
            content: 'Location';
            color: #111827;
            font-size: 0.78rem;
            font-weight: 900;
            align-self: end;
            padding: 0 0.5rem 0.35rem 0;
        }}
        .gantt-axis-bottom::before {{
            content: '';
        }}
        .gantt-axis-track {{
            position: relative;
            min-height: 42px;
            background: #ffffff;
            min-width: 0;
        }}
        .gantt-axis-top .gantt-axis-track {{
            border-bottom: 1px solid #94a3b8;
        }}
        .gantt-axis-bottom .gantt-axis-track {{
            border-top: 1px solid #94a3b8;
        }}
        .gantt-tick {{
            position: absolute;
            height: 0.55rem;
            border-left: 1px solid #cbd5e1;
            transform: translateX(-0.5px);
        }}
        .gantt-tick-medium,
        .gantt-tick-narrow {{
            display: none;
        }}
        .gantt-tick-end span {{
            transform: translateX(-100%);
        }}
        .gantt-axis-top .gantt-tick {{
            bottom: 0;
        }}
        .gantt-axis-bottom .gantt-tick {{
            top: 0;
        }}
        .gantt-tick span {{
            position: absolute;
            transform: translateX(-50%);
            color: #111827;
            background: rgba(255,255,255,0.92);
            border-radius: 0.2rem;
            padding: 0 0.12rem;
            font-size: 0.70rem;
            font-weight: 800;
            white-space: nowrap;
            min-width: max-content;
        }}
        .gantt-axis-top .gantt-tick span {{
            bottom: 0.72rem;
        }}
        .gantt-axis-bottom .gantt-tick span {{
            top: 0.72rem;
        }}
        .gantt-today-axis {{
            position: absolute;
            top: 0;
            bottom: 0;
            border-left: 3px solid {GANTT_TODAY_COLOR};
            z-index: 10;
            pointer-events: none;
        }}
        .gantt-today-axis span {{
            position: absolute;
            top: 0;
            transform: translateX(-50%);
            background: {GANTT_TODAY_COLOR};
            color: #111827;
            border-radius: 999px;
            padding: 0.08rem 0.45rem;
            font-size: 0.72rem;
            font-weight: 900;
            white-space: nowrap;
            min-width: max-content;
            box-shadow: 0 1px 3px rgba(0,0,0,0.25);
        }}
        .gantt-axis-bottom .gantt-today-axis span {{
            top: auto;
            bottom: 0;
        }}
        .gantt-row {{
            display: grid;
            grid-template-columns: {GANTT_ROW_LABEL_WIDTH_PX}px minmax(0, 1fr);
            min-height: 60px;
            height: 60px;
            border-bottom: 1px solid #e2e8f0;
            background: #ffffff;
        }}
        .gantt-row:nth-child(even) {{ background: #f8fafc; }}
        .gantt-commercial-row {{ background: #fffbeb !important; }}
        .gantt-location-label {{
            color: #111827;
            font-size: 0.78rem;
            font-weight: 900;
            line-height: 1.15;
            padding: 0.45rem 0.5rem 0.45rem 0.25rem;
            overflow-wrap: anywhere;
            word-break: normal;
            background: inherit;
            display: flex;
            align-items: center;
            justify-content: flex-start;
            text-align: left;
            min-width: 0;
        }}
        .gantt-track {{
            position: relative;
            min-height: 60px;
            background: linear-gradient(to right, #f8fafc, #ffffff);
            overflow: hidden;
            min-width: 0;
        }}
        .gantt-today-line {{
            position: absolute;
            top: 0;
            bottom: 0;
            border-left: 3px solid {GANTT_TODAY_COLOR};
            z-index: 4;
            pointer-events: none;
        }}
        .gantt-bar {{
            position: absolute;
            height: 20px;
            min-width: 11px;
            border-radius: 999px;
            box-shadow: 0 1px 4px rgba(0,0,0,0.28);
            color: #ffffff;
            font-size: 0.68rem;
            font-weight: 900;
            display: flex;
            align-items: center;
            justify-content: center;
            overflow: hidden;
            white-space: nowrap;
            border: 1px solid rgba(255,255,255,0.85);
            z-index: 3;
        }}
        .gantt-bar span {{
            min-width: max-content;
            padding: 0 0.22rem;
            text-shadow: 0 1px 2px rgba(0,0,0,0.45);
        }}
        .gantt-bar-commercial {{
            color:#111827 !important;
            border-color: rgba(17,24,39,0.25);
        }}
        .gantt-bar-commercial span {{
            color:#111827 !important;
            text-shadow: none;
        }}
        .gantt-cod-marker {{
            position: absolute;
            z-index: 8;
            transform: translateX(-50%);
            display: inline-flex;
            align-items: center;
            gap: 0.22rem;
            pointer-events: auto;
            white-space: nowrap;
        }}
        .gantt-cod-diamond {{
            width: 13px;
            height: 13px;
            display: inline-block;
            background: {GANTT_COD_COLOR};
            border: 2px solid #ffffff;
            transform: rotate(45deg);
            box-shadow: 0 1px 4px rgba(0,0,0,0.35);
            flex: 0 0 auto;
        }}
        .gantt-cod-label {{
            color: #111827;
            background: #fffbeb;
            border: 1px solid rgba(180,83,9,0.45);
            border-radius: 999px;
            padding: 0.04rem 0.32rem;
            font-size: 0.66rem;
            font-weight: 900;
            box-shadow: 0 1px 3px rgba(0,0,0,0.20);
        }}
        .gantt-table-cod-cell {{
            color: #7c2d12 !important;
            font-weight: 900 !important;
        }}
        .gantt-table-panel {{
            display: block;
            background:#ffffff;
            color:#111827;
            height: 100%;
            overflow: hidden;
            border: 1px solid rgba(148,163,184,0.45);
            border-radius: 0.65rem;
            min-width: 0;
        }}
        .gantt-table {{
            width: 100%;
            color: #111827;
            font-size: 0.78rem;
            background:#ffffff;
        }}
        .gantt-table-header {{
            display: grid;
            grid-template-columns: minmax(0, 1.25fr) minmax(0, 0.85fr) minmax(0, 0.85fr) minmax(0, 0.75fr);
            min-height: 42px;
            align-items: end;
            border-bottom: 1px solid #94a3b8;
            background:#f1f5f9;
            color:#111827;
            font-weight: 900;
        }}
        .gantt-table-header > div {{
            padding: 0 0.35rem 0.35rem 0.35rem;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}
        .gantt-table-body {{
            width: 100%;
        }}
        .gantt-table-row {{
            display: grid;
            grid-template-columns: minmax(0, 1.25fr) minmax(0, 0.85fr) minmax(0, 0.85fr) minmax(0, 0.75fr);
            min-height: 60px;
            height: 60px;
            border-bottom: 1px solid #e2e8f0;
            background:#ffffff;
            color:#111827;
            align-items: center;
        }}
        .gantt-table-row:nth-child(even) {{ background:#f8fafc; }}
        .gantt-table-cell {{
            padding: 0.35rem;
            color:#111827;
            overflow-wrap: anywhere;
            font-weight: 700;
            line-height: 1.2;
        }}
        .gantt-table-location {{ font-weight: 900; }}
        .gantt-commercial-table-row {{
            background:#fffbeb !important;
            color:#111827;
            font-weight:900;
        }}
        @media (max-width: {GANTT_TABLE_HIDE_BREAKPOINT_PX}px), (max-aspect-ratio: {GANTT_TABLE_HIDE_ASPECT_RATIO}) {{
            .gantt-layout {{ grid-template-columns: minmax(0, 1fr); }}
            .gantt-table-panel {{ display: none; }}
        }}
        @media (max-width: 980px) {{
            .gantt-tick-wide {{ display: none; }}
            .gantt-tick-medium {{ display: block; }}
            .gantt-tick-narrow {{ display: none; }}
        }}
        @media (max-width: 640px) {{
            .gantt-tick-wide,
            .gantt-tick-medium {{ display: none; }}
            .gantt-tick-narrow {{ display: block; }}
        }}
        @media (max-width: 720px) {{
            .gantt-legend-row {{ align-items: flex-start; }}
            .gantt-legend-group {{ width: 100%; justify-content: flex-start; overflow-x: auto; padding-bottom: 0.1rem; }}
            .gantt-axis, .gantt-row {{
                grid-template-columns: minmax({GANTT_MOBILE_ROW_LABEL_WIDTH_PX}px, 42%) minmax(0, 1fr);
            }}
            .gantt-location-label {{ font-size:0.74rem; }}
            .gantt-tick span {{ font-size: 0.66rem; padding: 0 0.10rem; }}
            .gantt-bar {{ font-size:0.66rem; min-width: 12px; }}
        }}
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


def get_uploaded_site_people_from_state() -> Any | None:
    return st.session_state.get("uploaded_site_people_csv")


def render_sidebar_upload_bottom(source_name: str, task_config_source_name: str, site_people_source_name: str) -> tuple[Any | None, Any | None, Any | None]:
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

    st.sidebar.divider()
    st.sidebar.subheader("Site People")
    uploaded_site_people = st.sidebar.file_uploader("Upload site_people CSV", type=["csv"], key="uploaded_site_people_csv")
    st.sidebar.download_button(
        "Download sample site_people CSV",
        data=create_sample_site_people_csv(),
        file_name="site_people.csv",
        mime="text/csv",
        use_container_width=True,
    )
    st.sidebar.caption(f"Current site people file: {site_people_source_name}")
    return uploaded_file, uploaded_task_config, uploaded_site_people


def render_task_config_summary(all_task_columns: list[str], visible_task_columns: list[str], task_config_meta: dict[str, Any]) -> None:
    hidden_tasks = list(task_config_meta.get("hidden_tasks", []))
    st.sidebar.caption(f"Visible tasks: {len(visible_task_columns)} / {len(all_task_columns)}")
    if hidden_tasks:
        preview = ", ".join(str(task) for task in hidden_tasks[:6])
        if len(hidden_tasks) > 6:
            preview += f", +{len(hidden_tasks) - 6} more"
        st.sidebar.caption(f"Hidden by task_config: {preview}")


def render_version_quick_filter(df: pd.DataFrame) -> None:
    version_options = get_version_filter_options(df)
    if not version_options:
        st.session_state["filter_version_quick_target"] = "All"
        return

    quick_targets = _get_quick_version_targets(version_options)
    if not quick_targets:
        st.session_state["filter_version_quick_target"] = "All"
        return

    options = ["All"] + quick_targets
    current = str(st.session_state.get("filter_version_quick_target", "All") or "All")
    if current not in options:
        current = "All"
        st.session_state["filter_version_quick_target"] = "All"

    st.sidebar.subheader("Version Quick Filter")
    cols = st.sidebar.columns(len(options))
    for col, option in zip(cols, options):
        is_active = option == current
        button_label = f"✓ {option}" if is_active else option
        button_type = "primary" if is_active else "secondary"
        if col.button(button_label, key=f"version_quick_button__{option}", use_container_width=True, type=button_type):
            st.session_state["filter_version_quick_target"] = option
            st.session_state["filter_version"] = []
            st.rerun()

    selected = str(st.session_state.get("filter_version_quick_target", "All") or "All")
    if selected != "All":
        matched_versions = [option for option in version_options if _version_matches_quick_target(option, selected)]
        selected_text = ", ".join(str(version) for version in matched_versions) if matched_versions else "No matching version"
        st.sidebar.caption(f"Current Version filter: {selected} → {selected_text}")
    else:
        manual_versions = st.session_state.get("filter_version", [])
        if manual_versions:
            selected_text = ", ".join(str(version) for version in manual_versions)
            st.sidebar.caption(f"Current Version filter: {selected_text}")
        else:
            st.sidebar.caption("Current Version filter: All")
    st.sidebar.divider()

def render_sidebar_filters(df: pd.DataFrame, task_columns: list[str], site_people_df: pd.DataFrame | None = None) -> dict[str, Any]:
    st.sidebar.header("Filters")
    if st.sidebar.button("Reset filters", use_container_width=True):
        keys_to_clear = [
            "filter_people_show_assigned",
            "filter_people_team",
            "filter_people_search",
            "filter_country",
            "filter_state",
            "filter_city",
            "filter_version",
            "filter_version_quick_target",
            "filter_search",
            "filter_status_levels",
            "filter_data_issue_only",
        ]
        for key in keys_to_clear:
            st.session_state.pop(key, None)
        st.rerun()

    people_options = get_people_filter_options(site_people_df if site_people_df is not None else pd.DataFrame())
    st.sidebar.markdown("**People Filter**")
    people_show_assigned = st.sidebar.checkbox("Show assigned staff", value=True, key="filter_people_show_assigned")
    people_team = st.sidebar.multiselect("People Team", people_options.get("team", []), key="filter_people_team")
    people_search = st.sidebar.text_input("People search", key="filter_people_search")
    st.sidebar.divider()

    def unique_options(column: str) -> list[str]:
        if column not in df.columns:
            return []
        return sorted([x for x in df[column].dropna().astype(str).unique().tolist() if x.strip()])

    country = st.sidebar.multiselect("Country", unique_options("country"), key="filter_country")
    state = st.sidebar.multiselect("State", unique_options("state"), key="filter_state")
    city = st.sidebar.multiselect("City", unique_options("city"), key="filter_city")
    version_options = get_version_filter_options(df)
    quick_selection = str(st.session_state.get("filter_version_quick_target", "All") or "All")
    quick_target = "" if quick_selection == "All" else quick_selection
    version = st.sidebar.multiselect("Version", version_options, key="filter_version") if version_options else []
    if quick_target:
        version = []
        st.sidebar.caption("Manual Version filter is ignored while Version Quick Filter is active.")
    search = st.sidebar.text_input("Search location_id / location_name / city", key="filter_search")

    status_levels = st.sidebar.multiselect(
        "Status level",
        ["Critical", "Warning", "Normal", "Complete", "Info", "Not Applicable"],
        key="filter_status_levels",
    )
    data_issue_only = st.sidebar.checkbox("Only sites with data issues", key="filter_data_issue_only")

    return {
        "people_show_assigned": people_show_assigned,
        "people_team": people_team,
        "people_search": people_search,
        "country": country,
        "state": state,
        "city": city,
        "version": version,
        "version_quick_target": quick_target,
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


def _kpi_group_css_class(group_name: str, group_label_prefix: str = "Version") -> str:
    if str(group_label_prefix).strip().casefold() != "version":
        return "kpi-version-group-other"
    return f"kpi-version-group-{_version_css_class(group_name)}"


def _kpi_site_pill_html(site_entry: Any) -> str:
    if isinstance(site_entry, dict):
        site_name = str(site_entry.get("name", ""))
        phase = str(site_entry.get("schedule_phase", "") or "")
    else:
        site_name = str(site_entry)
        phase = ""

    extra_class = ""
    title_suffix = ""
    if phase == "CCx":
        extra_class = " kpi-site-pill-ccx-active"
        title_suffix = " · Active CCx schedule"
    elif phase == "HCx":
        extra_class = " kpi-site-pill-hcx-active"
        title_suffix = " · Active HCx schedule"
    elif phase == GANTT_COMMERCIAL_OPERATION_LABEL:
        extra_class = " kpi-site-pill-commercial-operation"
        title_suffix = " · Commercial Operation"

    safe_site_name = html.escape(site_name)
    safe_title = html.escape(site_name + title_suffix)
    return f"<span class='kpi-site-pill{extra_class}' title='{safe_title}'>{safe_site_name}</span>"


def _kpi_card_html(
    title: str,
    count: Any,
    sites_by_version: dict[str, list[Any]] | None = None,
    group_label_prefix: str = "Version",
) -> str:
    safe_title = html.escape(str(title))
    safe_count = html.escape(str(count))
    safe_group_label_prefix = html.escape(str(group_label_prefix))
    site_list_html = ""

    if sites_by_version is not None:
        if sites_by_version:
            version_groups: list[str] = []
            for version, site_names in sites_by_version.items():
                safe_version = html.escape(str(version))
                safe_version_count = html.escape(str(len(site_names)))
                pills = "".join(_kpi_site_pill_html(site) for site in site_names)
                if str(group_label_prefix).strip().casefold() == "version":
                    group_label_html = _version_badge_html(str(version))
                else:
                    group_prefix_html = (
                        f"<span class='kpi-version-label-prefix'>{safe_group_label_prefix}</span>"
                        if safe_group_label_prefix
                        else ""
                    )
                    group_label_html = f"{group_prefix_html}<span>{safe_version}</span>"
                no_sites_html = "<span class='kpi-empty-sites'>No sites</span>" if not site_names else ""
                group_css_class = html.escape(_kpi_group_css_class(str(version), group_label_prefix))
                version_groups.append(
                    f"<div class='kpi-version-group {group_css_class}'>"
                    "<div class='kpi-version-header'>"
                    "<span class='kpi-version-label'>"
                    f"{group_label_html}"
                    "</span>"
                    f"<span class='kpi-version-count'>{safe_version_count} site(s)</span>"
                    "</div>"
                    f"<div class='kpi-version-sites'>{pills}{no_sites_html}</div>"
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


def _kpi_sites_by_version(kpis: dict[str, Any], label: str) -> dict[str, list[Any]]:
    value = kpis.get(label, {})
    if isinstance(value, dict):
        grouped = value.get("sites_by_version", {})
        if isinstance(grouped, dict):
            return {str(version): list(site_names) for version, site_names in grouped.items()}
    return {}


def _kpi_sites_by_group(kpis: dict[str, Any], label: str) -> dict[str, list[Any]]:
    value = kpis.get(label, {})
    if isinstance(value, dict):
        grouped = value.get("sites_by_group", {})
        if isinstance(grouped, dict):
            return {str(group_name): list(site_names) for group_name, site_names in grouped.items()}
    return {}




def _person_badge_palette(person_key: str, color_index: int | None = None) -> dict[str, str]:
    if color_index is not None:
        try:
            return PERSON_BADGE_PALETTE[int(color_index) % len(PERSON_BADGE_PALETTE)]
        except Exception:
            pass
    key = str(person_key or "").strip()
    digest = int(hashlib.sha256(key.encode("utf-8")).hexdigest(), 16) if key else 0
    return PERSON_BADGE_PALETTE[digest % len(PERSON_BADGE_PALETTE)]


def _build_person_color_index_map(active_people: pd.DataFrame) -> dict[str, int]:
    if active_people is None or active_people.empty or "_person_key" not in active_people.columns:
        return {}
    unique_rows = active_people.drop_duplicates(subset=["_person_key"]).copy()
    unique_rows["_sort_name"] = unique_rows["Name"].astype(str).str.casefold()
    unique_rows["_sort_team"] = unique_rows["Team"].astype(str).str.casefold()
    unique_rows = unique_rows.sort_values(["_sort_name", "_sort_team", "_person_key"])
    keys = [str(key).strip() for key in unique_rows["_person_key"].tolist() if str(key).strip()]
    return {key: index % len(PERSON_BADGE_PALETTE) for index, key in enumerate(keys)}


def _person_badge_html(name: str, person_key: str | None = None, color_index: int | None = None) -> str:
    display_name = str(name or "").strip().upper()
    if not display_name:
        return ""
    palette = _person_badge_palette(person_key or display_name, color_index)
    safe_name = html.escape(display_name)
    style = (
        "display:inline-flex;"
        "align-items:center;"
        "border-radius:999px;"
        "padding:0.12rem 0.48rem;"
        "font-size:0.70rem;"
        "font-weight:900;"
        "line-height:1.15;"
        "letter-spacing:0.025em;"
        "white-space:nowrap;"
        f"background:{palette['background']};"
        f"border:1px solid {palette['border']};"
        f"color:{palette['color']};"
        "box-shadow:0 1px 3px rgba(15,23,42,0.18);"
    )
    return f"<span class='people-name-badge' style='{style}' title='{safe_name}'>{safe_name}</span>"


def _people_kpi_card_html(title: str, count: Any, lines: list[str], span_two: bool = False, lines_are_html: bool = False) -> str:
    safe_title = html.escape(str(title))
    safe_count = html.escape(str(count))
    extra_class = " kpi-card-span-2" if span_two else ""
    if lines:
        if lines_are_html:
            line_html = "".join(f"<div class='people-kpi-line'>{line}</div>" for line in lines)
        else:
            line_html = "".join(f"<div class='people-kpi-line'>{html.escape(line)}</div>" for line in lines)
    else:
        line_html = "<div class='people-kpi-line'>No assigned staff</div>"
    return f"""
    <div class='kpi-card{extra_class}'>
        <div class='kpi-card-main'>
            <div class='kpi-card-title'>{safe_title}</div>
            <div class='kpi-card-value'>{safe_count}</div>
        </div>
        <div class='people-kpi-lines'>{line_html}</div>
    </div>
    """


def render_people_kpi_cards(people_kpis: dict[str, Any]) -> None:
    team_value = people_kpis.get("Team Overview", {})
    staff_value = people_kpis.get("On-Site Staff", {})
    team_counts = team_value.get("team_counts", {}) if isinstance(team_value, dict) else {}
    team_lines = [f"{team}: {count}" for team, count in team_counts.items()]
    site_rows = staff_value.get("site_people", []) if isinstance(staff_value, dict) else []
    staff_lines = []
    for item in site_rows:
        location_name = str(item.get("location_name", "") or item.get("location_id", ""))
        safe_location_name = html.escape(location_name)
        safe_count = html.escape(str(item.get("count", 0)))
        people_entries = item.get("people", [])
        if people_entries:
            people_badges = "".join(
                _person_badge_html(str(person.get("name", "")), str(person.get("person_key", "")), person.get("color_index"))
                for person in people_entries
            )
        else:
            people_badges = "".join(_person_badge_html(str(name), str(name)) for name in item.get("names", []))
        staff_lines.append(
            "<span class='people-kpi-site-name'>"
            f"{safe_location_name}:"
            "</span>"
            f"<span class='people-kpi-count'>{safe_count}</span>"
            "<span class='people-kpi-paren'>(</span>"
            f"<span class='people-kpi-badge-list'>{people_badges}</span>"
            "<span class='people-kpi-paren'>)</span>"
        )
    html_content = "".join(
        [
            _people_kpi_card_html("On-Site Team Overview", team_value.get("count", 0) if isinstance(team_value, dict) else 0, team_lines),
            _people_kpi_card_html("On-Site Staff", staff_value.get("count", 0) if isinstance(staff_value, dict) else 0, staff_lines, span_two=True, lines_are_html=True),
        ]
    )
    render_safe_html(f"<div class='kpi-card-row-secondary'>{html_content}</div>")


def render_kpi_cards(kpis: dict[str, Any]) -> None:
    cards_html = "".join(
        [
            _kpi_card_html(
                "Site Overview",
                _kpi_count(kpis, "Site Overview"),
                _kpi_sites_by_group(kpis, "Site Overview"),
                group_label_prefix="",
            ),
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


def render_selected_site_detail(selected_site: pd.Series | None, task_columns: list[str], selected_task_columns: list[str], people_by_location: dict[str, list[dict[str, Any]]] | None = None) -> None:
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

    people_for_site = get_people_for_site(site, people_by_location)
    st.markdown("#### Assigned Staff")
    if people_for_site:
        people_table = pd.DataFrame(
            [
                {
                    "Name": person.get("name", ""),
                    "Team": person.get("team", ""),
                    "Contact Information": person.get("contact", ""),
                    "Note": person.get("note", ""),
                }
                for person in people_for_site
            ]
        )
        st.dataframe(people_table, use_container_width=True, hide_index=True)
    else:
        st.info("No assigned staff for this site.")

    st.markdown("#### Selected Work Items")
    for task in selected_task_columns:
        parsed = parse_task_status_value(task, site.get(task, ""))
        if is_schedule_column(task):
            parsed = {**parsed, "display_text": _format_schedule_task_display(site, task, site.get(task, ""))}
        _render_task_detail_row(task, parsed)


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
        if is_schedule_column(task):
            table[f"{task}__display"] = table.apply(lambda row, task=task: _format_schedule_task_display(row, task, row.get(task, "")), axis=1)
        else:
            table[f"{task}__display"] = table[task].apply(lambda value, task=task: parse_task_status_value(task, value)["display_text"])
        if len(selected_task_columns) == 1:
            table[f"{task}__percent"] = table[task].apply(lambda value, task=task: parse_task_status_value(task, value)["percent"])

    version_col = _get_version_column_name(table.columns)
    base_cols = ["location_id", "location_name"]
    if version_col is not None:
        base_cols.append(version_col)
    base_cols.extend(["country", "state", "city", "enabled"])
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





def main() -> None:
    render_floating_task_selector_css()
    st.title("Site Work Status Map Dashboard")

    uploaded_file = get_uploaded_file_from_state()
    uploaded_task_config = get_uploaded_task_config_from_state()
    uploaded_site_people = get_uploaded_site_people_from_state()
    try:
        raw_df = load_csv(uploaded_file)
        task_config_df = load_task_config(uploaded_task_config)
        site_people_raw_df = load_site_people(uploaded_site_people)
    except Exception as exc:
        st.error(str(exc))
        st.stop()

    source_name = uploaded_file.name if uploaded_file is not None else DEFAULT_SITE_STATUS_FILENAME
    bundled_task_config_exists = get_default_task_config_csv() is not None
    bundled_site_people_exists = get_default_site_people_csv() is not None
    task_config_source_name = (
        uploaded_task_config.name
        if uploaded_task_config is not None
        else (DEFAULT_TASK_CONFIG_FILENAME if bundled_task_config_exists else "Not loaded")
    )
    site_people_source_name = (
        uploaded_site_people.name
        if uploaded_site_people is not None
        else (DEFAULT_SITE_PEOPLE_FILENAME if bundled_site_people_exists else "Not loaded")
    )

    all_task_columns = get_task_columns(raw_df)
    task_columns, task_config_issues, task_config_meta = apply_task_config_to_task_columns(all_task_columns, task_config_df)
    validated_df, validation_issues = validate_dataframe(
        raw_df,
        task_columns_to_validate=task_columns,
        require_task_columns=not bool(all_task_columns),
    )
    site_people_df, site_people_issues = prepare_site_people(site_people_raw_df, validated_df)
    validation_issues = validation_issues + task_config_issues + site_people_issues

    if not all_task_columns:
        st.error("No task columns found after the enabled column. Add at least one work item column.")
        render_sidebar_upload_bottom(source_name, task_config_source_name, site_people_source_name)
        issue_df = render_data_quality_report(validation_issues)
        render_download_buttons(pd.DataFrame(), issue_df)
        st.stop()

    if not task_columns:
        st.warning("All work items are hidden by task_config.csv. The dashboard will show site/map context only until at least one task is set visible=Y.")

    render_version_quick_filter(validated_df)
    selected_task_columns = render_task_selector(task_columns)
    render_task_config_summary(all_task_columns, task_columns, task_config_meta)
    filters = render_sidebar_filters(validated_df, task_columns, site_people_df)
    render_sidebar_upload_bottom(source_name, task_config_source_name, site_people_source_name)

    options = {
        "show_site_labels": True,
        "show_all_tasks_in_popup": True,
        "use_marker_cluster": True,
    }

    filtered_df = apply_filters(validated_df, filters, selected_task_columns)
    filtered_people_df = filter_site_people(site_people_df, filters)
    people_by_location = build_people_by_location(filtered_people_df)
    kpi_task_columns = selected_task_columns if selected_task_columns else task_columns
    kpis = calculate_kpis(validated_df, filtered_df, kpi_task_columns, validation_issues)
    people_kpis = calculate_people_kpis(filtered_df, filtered_people_df)

    updated_date_display = get_updated_date_display(validated_df)
    render_dashboard_meta_header(source_name, updated_date_display, len(filtered_df))
    render_kpi_cards(kpis)
    render_people_kpi_cards(people_kpis)

    st.divider()
    st.subheader("Map")
    render_map(filtered_df, task_columns, selected_task_columns, filters, options, people_by_location=people_by_location)

    selected_site = None
    selected_site_id = st.session_state.get("selected_site_id")
    if selected_site_id and not filtered_df.empty:
        matched = filtered_df[filtered_df["location_id"].astype(str) == str(selected_site_id)]
        if not matched.empty:
            selected_site = matched.iloc[0]

    with st.expander("CCx / HCx Schedule", expanded=True):
        render_gantt_chart_section(filtered_df)

    with st.expander("Selected Site Detail", expanded=True):
        render_selected_site_detail(selected_site, task_columns, selected_task_columns, people_by_location=people_by_location)

    with st.expander("Data Table", expanded=False):
        filtered_table = render_data_table(filtered_df, selected_task_columns)

    with st.expander("Data Quality Report", expanded=False):
        issue_df = render_data_quality_report(validation_issues)

    with st.expander("Export", expanded=False):
        render_download_buttons(filtered_table, issue_df)


if __name__ == "__main__":
    main()
