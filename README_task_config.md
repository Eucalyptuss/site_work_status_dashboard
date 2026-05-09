# task_config.csv Usage

This dashboard keeps historical work columns in `site_status.csv`, while `task_config.csv` controls which work items are visible in the active dashboard.

## Recommended files

- `site_status.csv`: site-level status/history data
- `task_config.csv`: dashboard visibility and display-order control for work items

You can either upload `task_config.csv` from the sidebar or place a file named `task_config.csv` in the same folder as `app.py`.

## task_config.csv columns

```csv
task_name,visible,category,display_order,description
Vavle1,N,Completed Work,10,All enabled sites completed; keep as history only
Valve2,Y,Active Work,20,Current work item
Note,Y,Information,999,Free text notes
```

| Column | Required | Purpose |
|---|---:|---|
| `task_name` | Yes | Must match a work-item column name in `site_status.csv` |
| `visible` | Recommended | `Y` shows the task; `N` hides it from the dashboard |
| `category` | Optional | Operational grouping such as Active Work or Completed Work |
| `display_order` | Optional | Lower numbers appear first in the work-item selector |
| `description` | Optional | Reason or management note |

## Behavior

- Hidden tasks remain in `site_status.csv`; they are not deleted.
- Hidden tasks do not appear in the work-item selector.
- Hidden tasks are excluded from Map popup, Selected Site Detail, Data Table, KPI calculation, and Data Quality checks.
- If no `task_config.csv` is loaded, all detected work-item columns remain visible.
- Invalid `visible` values default to visible `Y` to avoid accidentally hiding active work.
