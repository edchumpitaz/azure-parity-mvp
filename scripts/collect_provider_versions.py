#!/usr/bin/env python3
import json
import sys
from datetime import datetime, timezone

def main():
    # Usage: collect_provider_versions.py <input_provider_json> <cloud_name> <output_json>
    if len(sys.argv) != 4:
        print("Usage: collect_provider_versions.py <input_provider_json> <cloud_name> <output_json>")
        sys.exit(2)

    input_path = sys.argv[1]
    cloud_name = sys.argv[2]
    output_path = sys.argv[3]

    with open(input_path, "r", encoding="utf-8") as f:
        provider_doc = json.load(f)  # (dictionary)

    namespace = provider_doc.get("namespace")
    resource_types = provider_doc.get("resourceTypes", [])  # (list)

    normalized = {
        "cloud": cloud_name,
        "namespace": namespace,
        "collectedUtc": datetime.now(timezone.utc).isoformat(),
        "resourceTypes": []
    }  # (dictionary)

    for rt in resource_types:
        rtype = rt.get("resourceType")
        api_versions = rt.get("apiVersions", [])  # (list)

        normalized["resourceTypes"].append({
            "resourceType": rtype,
            "apiVersions": api_versions
        })  # (dictionary)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(normalized, f, indent=2, sort_keys=True)

    print(f"Wrote normalized provider metadata to {output_path}")

if __name__ == "__main__":
    main()
