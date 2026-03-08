"""
Build world_cities_5k.jsonl and training_1k.jsonl from GeoNames data.

Usage:
    python -m geoguess.scripts.build_datasets

Downloads cities1000.txt from GeoNames (free, no account needed),
filters to population > 100k, samples 5000 globally balanced cities,
writes to geoguess_env/data/.
"""
from __future__ import annotations

import csv
import io
import json
import os
import random
import sys
import urllib.request
import zipfile
from collections import defaultdict
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)

GEONAMES_URL = "https://download.geonames.org/export/dump/cities1000.zip"

# GeoNames admin1 codes → biome heuristic (rough)
# country_code → default biome
COUNTRY_BIOME: dict[str, str] = {
    "AU": "subtropical", "ZA": "savanna", "KE": "savanna", "NG": "tropical",
    "BR": "tropical", "CO": "tropical", "ID": "tropical", "MY": "tropical",
    "TH": "tropical", "VN": "tropical", "PH": "tropical",
    "EG": "desert", "SA": "desert", "AE": "desert", "IR": "desert",
    "MX": "subtropical", "ES": "mediterranean", "PT": "mediterranean",
    "GR": "mediterranean", "IT": "mediterranean", "TR": "mediterranean",
    "CN": "temperate_deciduous", "JP": "temperate_deciduous",
    "KR": "temperate_deciduous", "US": "temperate_deciduous",
    "CA": "boreal", "RU": "boreal", "SE": "boreal", "NO": "boreal",
    "FI": "boreal", "DE": "temperate_deciduous", "FR": "temperate_deciduous",
    "GB": "temperate_deciduous", "PL": "temperate_deciduous",
    "IN": "subtropical", "PK": "subtropical", "BD": "tropical",
    "AR": "temperate_grassland", "UA": "temperate_grassland",
    "KZ": "temperate_grassland", "MN": "temperate_grassland",
}


def infer_biome(country_code: str, latitude: float) -> str:
    if country_code in COUNTRY_BIOME:
        return COUNTRY_BIOME[country_code]
    if abs(latitude) > 60:
        return "tundra"
    if abs(latitude) > 50:
        return "boreal"
    if abs(latitude) > 30:
        return "temperate_deciduous"
    if abs(latitude) > 15:
        return "subtropical"
    return "tropical"


def download_geonames() -> list[dict]:
    print(f"Downloading {GEONAMES_URL} ...")
    with urllib.request.urlopen(GEONAMES_URL, timeout=60) as resp:
        data = resp.read()
    zf = zipfile.ZipFile(io.BytesIO(data))
    txt = zf.read("cities1000.txt").decode("utf-8")

    # GeoNames columns: https://download.geonames.org/export/dump/readme.txt
    # 0:geonameid 1:name 2:asciiname 3:alternatenames 4:latitude 5:longitude
    # 6:feature class 7:feature code 8:country code 9:cc2 10:admin1 11:admin2
    # 12:admin3 13:admin4 14:population 15:elevation 16:dem 17:timezone 18:modification date

    cities = []
    for line in txt.splitlines():
        parts = line.split("\t")
        if len(parts) < 15:
            continue
        try:
            pop = int(parts[14])
        except ValueError:
            continue
        if pop < 100_000:
            continue
        try:
            lat = float(parts[4])
            lon = float(parts[5])
        except ValueError:
            continue
        cities.append({
            "geonameid": parts[0],
            "name": parts[2],  # ascii name
            "lat": lat,
            "lon": lon,
            "country_code": parts[8].upper(),
            "admin1": parts[10],
            "population": pop,
        })
    print(f"  Found {len(cities)} cities with population > 100k")
    return cities


def balance_sample(cities: list[dict], n: int, seed: int = 42) -> list[dict]:
    """Sample n cities balanced across continents/country groups."""
    # Rough continent grouping by country code prefix ranges
    def continent(cc: str) -> str:
        AF = {"DZ","AO","BJ","BW","BF","BI","CV","CM","CF","TD","KM","CG","CD","CI","DJ","EG","GQ","ER","SZ","ET","GA","GM","GH","GN","GW","KE","LS","LR","LY","MG","MW","ML","MR","MU","YT","MA","MZ","NA","NE","NG","RE","RW","SH","ST","SN","SC","SL","SO","ZA","SS","SD","TZ","TG","TN","UG","EH","ZM","ZW"}
        AS = {"AF","AM","AZ","BH","BD","BT","BN","KH","CN","CY","GE","IN","ID","IR","IQ","IL","JP","JO","KZ","KW","KG","LA","LB","MY","MV","MN","MM","NP","KP","OM","PK","PS","PH","QA","SA","SG","KR","LK","SY","TW","TJ","TH","TL","TM","AE","UZ","VN","YE"}
        EU = {"AL","AD","AT","BY","BE","BA","BG","HR","CY","CZ","DK","EE","FI","FR","DE","GR","HU","IS","IE","IT","XK","LV","LI","LT","LU","MK","MT","MD","MC","ME","NL","NO","PL","PT","RO","RU","SM","RS","SK","SI","ES","SE","CH","UA","GB","VA"}
        NA = {"AG","BS","BB","BZ","CA","CR","CU","DM","DO","SV","GD","GT","HT","HN","JM","MX","NI","PA","KN","LC","VC","TT","US"}
        SA = {"AR","BO","BR","CL","CO","EC","GY","PY","PE","SR","UY","VE"}
        OC = {"AU","FJ","KI","MH","FM","NR","NZ","PW","PG","WS","SB","TO","TV","VU"}
        for group, members in [("AF", AF), ("AS", AS), ("EU", EU), ("NA", NA), ("SA", SA), ("OC", OC)]:
            if cc in members:
                return group
        return "OTHER"

    by_continent: dict[str, list[dict]] = defaultdict(list)
    for c in cities:
        by_continent[continent(c["country_code"])].append(c)

    rng = random.Random(seed)
    chosen = []
    continents = list(by_continent.keys())
    per_continent = n // len(continents)
    for cont in continents:
        pool = by_continent[cont]
        rng.shuffle(pool)
        chosen.extend(pool[:per_continent])
    # fill remainder
    remainder = n - len(chosen)
    chosen_ids = {c["geonameid"] for c in chosen}
    all_rest = [c for c in cities if c["geonameid"] not in chosen_ids]
    rng.shuffle(all_rest)
    chosen.extend(all_rest[:remainder])
    rng.shuffle(chosen)
    return chosen[:n]


def write_jsonl(path: Path, records: list[dict]) -> None:
    with open(path, "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    print(f"  Written {len(records)} records -> {path}")


def main():
    cities = download_geonames()
    sampled = balance_sample(cities, 5000)

    world_cities = []
    for i, c in enumerate(sampled):
        loc = {
            "location_id": f"wc_{c['geonameid']}",
            "lat": c["lat"],
            "lon": c["lon"],
            "country_code": c["country_code"],
            "country_name": c["country_code"],   # full name lookup not needed for training
            "region": c["admin1"],
            "city": c["name"],
            "biome": infer_biome(c["country_code"], c["lat"]),
        }
        world_cities.append(loc)

    write_jsonl(DATA_DIR / "world_cities_5k.jsonl", world_cities)

    # training_1k: stratified 1000-subset, no overlap with a held-out eval split
    rng = random.Random(99)
    training = list(world_cities)
    rng.shuffle(training)
    write_jsonl(DATA_DIR / "training_1k.jsonl", training[:1000])

    print("Done. Datasets ready in", DATA_DIR)


if __name__ == "__main__":
    main()
