"""
Rebuild app/matching/data/cities.tsv — the offline US + Canada city dataset
used for radius filtering, city autocomplete, and "Use my location".

Data source: GeoNames (https://www.geonames.org), licensed CC BY 4.0.
Download the country dumps first, then run this script:

    curl -O https://download.geonames.org/export/dump/US.zip && unzip US.zip
    curl -O https://download.geonames.org/export/dump/CA.zip && unzip CA.zip
    python scripts/build_cities.py US.txt CA.txt

Output columns (tab-separated): normalized_name, admin1 (state/province
abbr), country code, lat, lng, population. Name normalization here MUST stay
in sync with app/matching/geo.py::_normalize.
"""

import csv
import re
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "app" / "matching" / "data" / "cities.tsv"

# GeoNames stores Canadian admin1 as numeric codes; map to postal abbrs.
CA_ADMIN = {"01": "AB", "02": "BC", "03": "MB", "04": "NB", "05": "NL",
            "07": "NS", "08": "ON", "09": "PE", "10": "QC", "11": "SK",
            "12": "YT", "13": "NT", "14": "NU"}


def norm(name: str) -> str:
    n = name.lower().replace(".", "")
    n = re.sub(r"\s+", " ", n).strip()
    n = re.sub(r"^st ", "saint ", n)
    n = re.sub(r"^ft ", "fort ", n)
    n = re.sub(r"^mt ", "mount ", n)
    return n


def main(paths: list[str]) -> None:
    best: dict = {}  # (norm_name, admin1, country) -> (lat, lng, pop)
    for fn in paths:
        with open(fn, encoding="utf-8") as f:
            for line in f:
                p = line.split("\t")
                if len(p) < 15 or p[6] != "P":  # populated places only
                    continue
                try:
                    lat, lng, pop = float(p[4]), float(p[5]), int(p[14] or 0)
                except ValueError:
                    continue
                country = p[8]
                admin1 = CA_ADMIN.get(p[10], p[10]) if country == "CA" else p[10]
                key = (norm(p[2] or p[1]), admin1, country)
                if key not in best or pop > best[key][2]:
                    best[key] = (lat, lng, pop)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter="\t")
        for (nm, a1, cc), (lat, lng, pop) in best.items():
            if nm:
                w.writerow([nm, a1, cc, f"{lat:.4f}", f"{lng:.4f}", pop])
    print(f"wrote {len(best)} places to {OUT}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1:])
