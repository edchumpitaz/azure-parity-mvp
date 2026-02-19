#!/usr/bin/env python3
import json
import sys
from datetime import datetime

def main():
    # Usage: report_parity_md.py <parity_json> <output_md>
    if len(sys.argv) != 3:
        print("Usage: report_parity_md.py <parity_json> <output_md>")
        sys.exit(2)

    parity_path = sys.argv[1]
    out_md = sys.argv[2]

    with open(parity_path, "r", encoding="utf-8") as f:
        doc = json.load(f)  # (dictionary)

    namespace = doc.get("namespace", "UnknownNamespace")
    public_cloud = doc.get("publicCloud", "AzurePublic")
    gov_cloud = doc.get("govCloud", "AzureGov")
    generated_utc = doc.get("generatedUtc", datetime.utcnow().isoformat() + "Z")

    diffs = doc.get("resourceTypeDiffs", [])  # (list)

    aligned = [d for d in diffs if d.get("status") == "Aligned"]
    public_ahead = [d for d in diffs if d.get("status") == "PublicAhead"]
    gov_ahead = [d for d in diffs if d.get("status") == "GovAhead"]

    def lag_key(d):
        v = d.get("lagDaysPublicAhead")
        return v if isinstance(v, int) else -10**9

    top_lag = sorted(public_ahead, key=lag_key, reverse=True)[:10]

    def missing_count(d, field):
        vals = d.get(field, [])  # (list)
        return len(vals) if isinstance(vals, list) else 0

    top_missing_in_gov = sorted(public_ahead, key=lambda d: missing_count(d, "missingInGov"), reverse=True)[:10]

    lines = []
    lines.append(f"# API Version Parity Report: {namespace}")
    lines.append("")
    lines.append(f"- **Public cloud:** {public_cloud}")
    lines.append(f"- **Gov cloud:** {gov_cloud}")
    lines.append(f"- **Generated:** {generated_utc}")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- **Aligned resource types:** {len(aligned)}")
    lines.append(f"- **Public ahead:** {len(public_ahead)}")
    lines.append(f"- **Gov ahead:** {len(gov_ahead)}")
    lines.append("")

    lines.append("## Top 10 Largest Public→Gov Lag (by days)")
    lines.append("")
    if not top_lag:
        lines.append("_No lag detected (or lagDays could not be computed)._")
    else:
        lines.append("| Resource Type | Latest Public | Latest Gov | Lag (days) | Missing in Gov (count) |")
        lines.append("|---|---|---|---:|---:|")
        for d in top_lag:
            lines.append(
                f"| `{d.get('resourceType')}` | `{d.get('latestPublic')}` | `{d.get('latestGov')}` | "
                f"{d.get('lagDaysPublicAhead') if d.get('lagDaysPublicAhead') is not None else ''} | "
                f"{missing_count(d, 'missingInGov')} |"
            )
    lines.append("")

    lines.append("## Top 10 Most Missing API Versions in Gov (by count)")
    lines.append("")
    if not top_missing_in_gov:
        lines.append("_No missing API versions detected._")
    else:
        lines.append("| Resource Type | Missing in Gov (count) | Example Missing Versions (up to 5) |")
        lines.append("|---|---:|---|")
        for d in top_missing_in_gov:
            missing = d.get("missingInGov", [])  # (list)
            examples = ", ".join([f"`{v}`" for v in missing[:5]])
            lines.append(f"| `{d.get('resourceType')}` | {len(missing)} | {examples} |")
    lines.append("")

    lines.append("## Notes")
    lines.append("")
    lines.append("- This report compares **ARM provider-supported `api-version` sets** per resource type.")
    lines.append("- API-version lag is a strong indicator of management-plane parity, but it does not always guarantee feature absence (some features are backported or exposed differently).")
    lines.append("")

    with open(out_md, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"Wrote markdown report to {out_md}")

if __name__ == "__main__":
    main()