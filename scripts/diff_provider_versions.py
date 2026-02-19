#!/usr/bin/env python3
import json
import sys
from datetime import datetime

def parse_date(api_version: str):
    # API versions are usually "YYYY-MM-DD" or "YYYY-MM-DD-preview"
    base = api_version.split("-preview")[0]
    return datetime.strptime(base, "%Y-%m-%d")

def to_map(doc: dict):
    # (dictionary) -> (dictionary) mapping resourceType -> set(apiVersions)
    mapping = {}  # (dictionary)
    for item in doc.get("resourceTypes", []):  # (list)
        rtype = item.get("resourceType")
        versions = set(item.get("apiVersions", []))  # (set)
        if rtype:
            mapping[rtype] = versions
    return mapping

def latest_version(versions_set):
    if not versions_set:
        return None

    def sort_key(v):
        try:
            return parse_date(v)
        except Exception:
            return datetime.min

    return sorted(list(versions_set), key=sort_key)[-1]

def main():
    # Usage: diff_provider_versions.py <public_norm_json> <gov_norm_json> <output_json>
    if len(sys.argv) != 4:
        print("Usage: diff_provider_versions.py <public_norm_json> <gov_norm_json> <output_json>")
        sys.exit(2)

    public_path = sys.argv[1]
    gov_path = sys.argv[2]
    output_path = sys.argv[3]

    with open(public_path, "r", encoding="utf-8") as f:
        pub = json.load(f)  # (dictionary)

    with open(gov_path, "r", encoding="utf-8") as f:
        gov = json.load(f)  # (dictionary)

    pub_map = to_map(pub)
    gov_map = to_map(gov)

    all_types = sorted(set(list(pub_map.keys()) + list(gov_map.keys())))

    results = {
        "namespace": pub.get("namespace") or gov.get("namespace"),
        "publicCloud": pub.get("cloud"),
        "govCloud": gov.get("cloud"),
        "generatedUtc": datetime.utcnow().isoformat() + "Z",
        "resourceTypeDiffs": []
    }  # (dictionary)

    for rtype in all_types:
        pub_versions = pub_map.get(rtype, set())
        gov_versions = gov_map.get(rtype, set())

        missing_in_gov = sorted(list(pub_versions - gov_versions))
        missing_in_public = sorted(list(gov_versions - pub_versions))

        latest_pub = latest_version(pub_versions)
        latest_gov = latest_version(gov_versions)

        lag_days = None
        if latest_pub and latest_gov:
            try:
                lag_days = (parse_date(latest_pub) - parse_date(latest_gov)).days
            except Exception:
                lag_days = None

        if missing_in_gov:
            status = "PublicAhead"
        elif missing_in_public:
            status = "GovAhead"
        else:
            status = "Aligned"

        results["resourceTypeDiffs"].append({
            "resourceType": rtype,
            "latestPublic": latest_pub,
            "latestGov": latest_gov,
            "lagDaysPublicAhead": lag_days,
            "missingInGov": missing_in_gov,
            "missingInPublic": missing_in_public,
            "status": status
        })  # (dictionary)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, sort_keys=True)

    print(f"Wrote parity diff to {output_path}")

if __name__ == "__main__":
    main()
