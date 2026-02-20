#!/usr/bin/env python3
"""
report_parity_md.py

Generates:
  1) Human-readable Markdown report (tabular-first, like the Azure audit-scope page style)
  2) Optional CSV export for easy filtering

Input (parity JSON) is expected to look like:
  {
    "namespace": "Microsoft.Compute",
    "clouds": {"public": "...", "gov": "..."},          # (dictionary) optional
    "generatedAtUtc": "2026-02-20T13:07:12Z",           # optional
    "resourceTypes": [                                  # (list)
      {
        "name": "virtualMachines",
        "latestPublic": "2024-07-01",
        "latestGov": "2024-03-01",
        "missingInGov": ["2024-07-01", "2024-05-01"],   # (list)
        "missingInPublic": [],                          # (list)
        "lagDaysPublicAhead": 122,
        "status": "PublicAhead"
      }
    ]
  }

This script is defensive: it tolerates minor schema differences.
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        if v is None:
            return default
        return int(v)
    except Exception:
        return default


def _safe_str(v: Any, default: str = "") -> str:
    if v is None:
        return default
    s = str(v).strip()
    return s if s else default


def _safe_list(v: Any) -> List[Any]:
    if isinstance(v, list):
        return v
    if v is None:
        return []
    # If some earlier code outputs a comma-separated string, normalize it.
    if isinstance(v, str) and "," in v:
        return [x.strip() for x in v.split(",") if x.strip()]
    return []


def _truncate_list_display(items: List[str], max_items: int = 8) -> Tuple[str, int]:
    """
    Returns (display_string, remaining_count)
    """
    if not items:
        return "—", 0
    if len(items) <= max_items:
        return ", ".join(items), 0
    shown = items[:max_items]
    remaining = len(items) - max_items
    return ", ".join(shown) + f" (+{remaining} more)", remaining


def _load_json(path: Path) -> Dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Parity JSON root must be a JSON object (dictionary).")
    return data


def _infer_namespace(doc: Dict[str, Any], fallback: str = "") -> str:
    for k in ["namespace", "providerNamespace", "resourceProvider", "provider"]:
        if k in doc and doc[k]:
            return _safe_str(doc[k])
    return fallback


def _get_resource_items(doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    # Try common keys
    for k in ["resourceTypes", "resources", "types", "items"]:
        if k in doc and isinstance(doc[k], list):
            items = [x for x in doc[k] if isinstance(x, dict)]
            if items:
                return items
            return []
    # Some schemas might nest: {"data": {"resourceTypes": [...]}}
    data = doc.get("data")
    if isinstance(data, dict):
        for k in ["resourceTypes", "resources", "types", "items"]:
            if k in data and isinstance(data[k], list):
                items = [x for x in data[k] if isinstance(x, dict)]
                if items:
                    return items
                return []
    return []


def _extract_row(item: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalizes a resourceType parity record to a stable row (dictionary).

    Expected fields (with fallbacks):
      name/resourceType/type -> resourceType
      status -> status
      lagDaysPublicAhead / lagDays -> lagDaysPublicAhead
      latestPublic, latestGov
      missingInGov, missingInPublic (lists)
    """
    resource_type = (
        _safe_str(item.get("name"))
        or _safe_str(item.get("resourceType"))
        or _safe_str(item.get("type"))
        or _safe_str(item.get("resource_type"))
    )

    latest_public = _safe_str(item.get("latestPublic") or item.get("publicLatest") or item.get("latest_public"))
    latest_gov = _safe_str(item.get("latestGov") or item.get("govLatest") or item.get("latest_gov"))

    missing_in_gov = _safe_list(item.get("missingInGov") or item.get("missing_in_gov"))
    missing_in_public = _safe_list(item.get("missingInPublic") or item.get("missing_in_public"))

    status = _safe_str(item.get("status")).strip() or _safe_str(item.get("parityStatus")).strip()
    lag = item.get("lagDaysPublicAhead")
    if lag is None:
        lag = item.get("lagDays")
    lag_days = _safe_int(lag, 0)

    # Some schemas might express "GovAhead" with a separate lag metric; keep table simple:
    # - If GovAhead, we still show lagDaysPublicAhead as 0 (unless already computed).
    if status.lower() == "govahead" and lag_days > 0:
        # This would be inconsistent naming; leave as-is, but you may want separate "lagDaysGovAhead" later.
        pass

    return {
        "resourceType": resource_type,
        "status": status or "Unknown",
        "lagDaysPublicAhead": lag_days,
        "latestPublic": latest_public or "—",
        "latestGov": latest_gov or "—",
        "missingInGov": [str(x) for x in missing_in_gov],
        "missingInPublic": [str(x) for x in missing_in_public],
    }


def _status_sort_key(status: str) -> int:
    # Ordering for readability in some views (not used in default lag sort)
    s = status.lower()
    if s == "publicahead":
        return 0
    if s == "aligned":
        return 1
    if s == "govahead":
        return 2
    return 3


def _render_markdown_report(
    namespace: str,
    generated_at_utc: str,
    rows: List[Dict[str, Any]],
    top_n: int = 15,
    missing_list_limit: int = 8,
) -> str:
    total = len(rows)

    aligned = sum(1 for r in rows if str(r["status"]).lower() == "aligned")
    public_ahead = sum(1 for r in rows if str(r["status"]).lower() == "publicahead")
    gov_ahead = sum(1 for r in rows if str(r["status"]).lower() == "govahead")
    unknown = total - aligned - public_ahead - gov_ahead

    max_lag = max([r["lagDaysPublicAhead"] for r in rows], default=0)

    # Sort by lag desc, then status, then resourceType asc
    sorted_by_lag = sorted(
        rows,
        key=lambda r: (-_safe_int(r["lagDaysPublicAhead"], 0), _status_sort_key(str(r["status"])), str(r["resourceType"]).lower()),
    )

    # Build main table
    # Columns mimic audit-scope scan-ability: stable set, easy to compare quickly.
    lines: List[str] = []
    lines.append(f"# Azure ARM API Parity Report — {namespace}")
    lines.append("")
    lines.append(f"- Generated (UTC): `{generated_at_utc}`")
    lines.append(f"- Resource types analyzed: **{total}**")
    lines.append(f"- Status counts: **Aligned {aligned}**, **PublicAhead {public_ahead}**, **GovAhead {gov_ahead}**, **Unknown {unknown}**")
    lines.append(f"- Max lag (Public ahead): **{max_lag} days**")
    lines.append("")
    lines.append("## Parity Table")
    lines.append("")
    lines.append("| Resource Type | Status | Lag (days) | Latest Public | Latest Gov | Missing in Gov (#) | Missing in Public (#) |")
    lines.append("|---|---:|---:|---|---|---:|---:|")

    for r in sorted_by_lag:
        rt = str(r["resourceType"]) or "—"
        status = str(r["status"]) or "Unknown"
        lag = _safe_int(r["lagDaysPublicAhead"], 0)
        lp = str(r["latestPublic"]) or "—"
        lg = str(r["latestGov"]) or "—"
        mig = len(_safe_list(r.get("missingInGov")))
        mip = len(_safe_list(r.get("missingInPublic")))
        lines.append(f"| `{rt}` | {status} | {lag} | `{lp}` | `{lg}` | {mig} | {mip} |")

    lines.append("")
    lines.append(f"## Top {min(top_n, total)} Lagging Resource Types (Public ahead)")
    lines.append("")
    lines.append("| Rank | Resource Type | Lag (days) | Latest Public | Latest Gov | Missing in Gov (#) |")
    lines.append("|---:|---|---:|---|---|---:|")

    lagging = [r for r in sorted_by_lag if _safe_int(r["lagDaysPublicAhead"], 0) > 0]
    for i, r in enumerate(lagging[:top_n], start=1):
        lines.append(
            f"| {i} | `{r['resourceType']}` | {_safe_int(r['lagDaysPublicAhead'], 0)} | `{r['latestPublic']}` | `{r['latestGov']}` | {len(_safe_list(r.get('missingInGov')))} |"
        )

    # Optional drilldown: Missing versions table (capped)
    lines.append("")
    lines.append("## Missing API Versions (Drill-down)")
    lines.append("")
    lines.append("> Lists are truncated for readability. Use the parity JSON artifact for full details.")
    lines.append("")
    lines.append("| Resource Type | Missing in Gov (versions) | Missing in Public (versions) |")
    lines.append("|---|---|---|")

    # Sort drilldown by missing counts desc, then name
    by_missing = sorted(
        rows,
        key=lambda r: (-(len(r["missingInGov"]) + len(r["missingInPublic"])), str(r["resourceType"]).lower()),
    )
    for r in by_missing:
        mig_list = [str(x) for x in _safe_list(r.get("missingInGov"))]
        mip_list = [str(x) for x in _safe_list(r.get("missingInPublic"))]

        mig_disp, _ = _truncate_list_display(mig_list, max_items=missing_list_limit)
        mip_disp, _ = _truncate_list_display(mip_list, max_items=missing_list_limit)

        # Only show rows where something is missing
        if mig_list or mip_list:
            lines.append(f"| `{r['resourceType']}` | {mig_disp} | {mip_disp} |")

    lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append("- This report reflects **ARM management-plane api-version metadata** from provider discovery, not guaranteed feature availability.")
    lines.append("- For authoritative drill-down, rely on the generated parity JSON artifact.")
    lines.append("")

    return "\n".join(lines)


def _write_csv(path: Path, namespace: str, generated_at_utc: str, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "generatedAtUtc",
                "namespace",
                "resourceType",
                "status",
                "lagDaysPublicAhead",
                "latestPublic",
                "latestGov",
                "missingInGovCount",
                "missingInPublicCount",
            ]
        )
        for r in rows:
            w.writerow(
                [
                    generated_at_utc,
                    namespace,
                    r.get("resourceType", ""),
                    r.get("status", ""),
                    _safe_int(r.get("lagDaysPublicAhead"), 0),
                    r.get("latestPublic", ""),
                    r.get("latestGov", ""),
                    len(_safe_list(r.get("missingInGov"))),
                    len(_safe_list(r.get("missingInPublic"))),
                ]
            )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--parity-json", required=True, help="Path to output/<provider>.parity.json")
    ap.add_argument("--out-md", required=True, help="Path to output/<provider>.parity.md")
    ap.add_argument("--out-csv", default="", help="Optional: Path to output/<provider>.parity.csv")
    ap.add_argument("--top-n", type=int, default=15, help="Top N lagging rows to include")
    ap.add_argument("--missing-list-limit", type=int, default=8, help="Max missing api-versions to show per cell")
    args = ap.parse_args()

    parity_path = Path(args.parity_json)
    out_md = Path(args.out_md)
    out_csv = Path(args.out_csv) if args.out_csv else None

    doc = _load_json(parity_path)

    namespace = _infer_namespace(doc, fallback=parity_path.stem.replace(".parity", ""))
    generated_at_utc = _safe_str(doc.get("generatedAtUtc") or doc.get("generatedAt") or doc.get("computedAtUtc") or _now_utc_iso())

    items = _get_resource_items(doc)
    rows = [_extract_row(it) for it in items]

    # Filter out empty resourceType rows if any
    rows = [r for r in rows if str(r.get("resourceType", "")).strip()]

    md = _render_markdown_report(
        namespace=namespace,
        generated_at_utc=generated_at_utc,
        rows=rows,
        top_n=args.top_n,
        missing_list_limit=args.missing_list_limit,
    )

    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(md, encoding="utf-8")

    if out_csv is not None:
        _write_csv(out_csv, namespace, generated_at_utc, rows)

    print(f"Wrote Markdown: {out_md}")
    if out_csv is not None:
        print(f"Wrote CSV: {out_csv}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())