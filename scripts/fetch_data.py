#!/usr/bin/env python3
"""
Pulls the published-CSV export of the Google Sheet and converts it into
data.json for the dashboard. Locates blocks by label text (not fixed row
numbers) so it tolerates rows being added/removed above/below a block.

Requires env var SHEET_CSV_URL to be set (a "Publish to web -> CSV" link).
"""
import csv
import io
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone, timedelta

CSV_URL = os.environ.get("SHEET_CSV_URL", "").strip()
OUT_PATH = os.path.join(os.path.dirname(__file__), "..", "data.json")


def num(v):
    if v is None:
        return 0.0
    s = str(v).replace(",", "").strip()
    if s == "":
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def num_or_none(v):
    if v is None:
        return None
    s = str(v).replace(",", "").strip()
    if s == "":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def cell(row, idx):
    return row[idx] if idx < len(row) else ""


def find_row_idx(rows, predicate, start=0):
    for i in range(start, len(rows)):
        if predicate(rows[i]):
            return i
    return -1


def parse_sheet(rows):
    out = {
        "monthLocations": [],
        "monthTotal": {},
        "feed": [],
        "feedTotal": {},
        "b2b": {"qty": None, "avg": None},
        "rejection": {"qty": None, "avg": None},
        "totalSalesAllChannels": None,
        "sheetTitle": "SG MART Sales",
    }

    block2_title_idx = find_row_idx(
        rows, lambda r: "sg mart" in (cell(r, 0) or "").lower()
    )
    block1_header_idx = find_row_idx(
        rows, lambda r: (cell(r, 0) or "").strip().lower() == "location"
    )

    # ---- Block 1: monthly pivot ----
    if block1_header_idx != -1 and (
        block2_title_idx == -1 or block1_header_idx < block2_title_idx
    ):
        i = block1_header_idx + 1
        locs = []
        total_row = None
        steps = 0
        while i < len(rows) and steps < 300:
            r = rows[i]
            loc = (cell(r, 0) or "").strip()
            if loc == "":
                i += 1
                steps += 1
                continue
            if loc.lower() == "grand total":
                total_row = r
                i += 1
                break
            locs.append(
                {
                    "location": loc,
                    "hrsheet_qty": num(cell(r, 1)),
                    "hrsheet_price": num(cell(r, 2)),
                    "hrsheet_avg": num(cell(r, 3)),
                    "chsheet_qty": num(cell(r, 4)),
                    "chsheet_price": num(cell(r, 5)),
                    "chsheet_avg": num(cell(r, 6)),
                    "chcoil_qty": num(cell(r, 7)),
                    "chcoil_price": num(cell(r, 8)),
                    "hrcoil_qty": num(cell(r, 9)),
                    "hrcoil_price": num(cell(r, 10)),
                    "hrcoil_avg": num(cell(r, 11)),
                    "hrslits_qty": num(cell(r, 12)),
                    "hrslits_price": num(cell(r, 13)),
                    "hrslits_avg": num(cell(r, 14)),
                    "total_qty": num(cell(r, 15)),
                    "total_price": num(cell(r, 16)),
                    "total_avg": num(cell(r, 17)),
                }
            )
            i += 1
            steps += 1
        if locs:
            out["monthLocations"] = locs
        if total_row:
            out["monthTotal"] = {
                "hrsheet_qty": num(cell(total_row, 1)),
                "chsheet_qty": num(cell(total_row, 4)),
                "hrcoil_qty": num(cell(total_row, 9)),
                "total_qty": num(cell(total_row, 15)),
                "total_price": num(cell(total_row, 16)),
                "total_avg": num(cell(total_row, 17)),
            }

    # ---- Block 2: daily feed ----
    if block2_title_idx != -1:
        out["sheetTitle"] = (cell(rows[block2_title_idx], 0) or "").strip() or out["sheetTitle"]
        header_idx = block2_title_idx + 1
        i = header_idx + 1
        feed = []
        feed_total = None
        steps = 0
        while i < len(rows) and steps < 300:
            r = rows[i]
            loc = (cell(r, 0) or "").strip()
            if loc == "":
                i += 1
                steps += 1
                continue
            low = loc.lower()
            if low == "grand total":
                feed_total = r
                i += 1
                break
            if "b2b" in low or "rejection" in low:
                break
            feed.append(
                {
                    "location": loc,
                    "hrsheet": num(cell(r, 1)),
                    "hrsheet_avg": num(cell(r, 2)),
                    "chsheet": num(cell(r, 3)),
                    "chsheet_avg": num(cell(r, 4)),
                    "hrcoil": num(cell(r, 5)),
                    "hrcoil_avg": num(cell(r, 6)),
                    "total": num(cell(r, 7)),
                    "total_avg": num(cell(r, 8)),
                    "yesterday": num(cell(r, 9)),
                    "yesterday_avg": num(cell(r, 10)),
                    "stock": num(cell(r, 11)),
                    "transit": num(cell(r, 12)),
                }
            )
            i += 1
            steps += 1
        if feed:
            out["feed"] = feed
        if feed_total:
            out["feedTotal"] = {
                "hrsheet": num(cell(feed_total, 1)),
                "chsheet": num(cell(feed_total, 3)),
                "hrcoil": num(cell(feed_total, 5)),
                "total": num(cell(feed_total, 7)),
                "total_avg": num(cell(feed_total, 8)),
                "yesterday": num(cell(feed_total, 9)),
                "yesterday_avg": num(cell(feed_total, 10)),
                "stock": num(cell(feed_total, 11)),
                "transit": num(cell(feed_total, 12)),
            }

        for j in range(i, min(i + 40, len(rows))):
            label = (cell(rows[j], 0) or "").lower()
            if "b2b" in label:
                data_row = rows[j + 1] if j + 1 < len(rows) else []
                out["b2b"] = {
                    "qty": num_or_none(cell(data_row, 1)),
                    "avg": num_or_none(cell(data_row, 2)),
                }
            if "rejection" in label:
                data_row = rows[j + 1] if j + 1 < len(rows) else []
                out["rejection"] = {
                    "qty": num_or_none(cell(data_row, 1)),
                    "avg": num_or_none(cell(data_row, 2)),
                }
            for k, val in enumerate(rows[j]):
                if (val or "").strip().lower() == "total sales":
                    out["totalSalesAllChannels"] = num_or_none(cell(rows[j], k + 1))

    if not out["feed"] and not out["monthLocations"]:
        raise RuntimeError(
            'Could not find "Location" rows in this sheet — check the published '
            "tab matches the expected layout."
        )
    return out


def main():
    if not CSV_URL:
        print("ERROR: SHEET_CSV_URL is not set", file=sys.stderr)
        sys.exit(1)

    req = urllib.request.Request(CSV_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode("utf-8", errors="replace")

    rows = list(csv.reader(io.StringIO(raw)))
    parsed = parse_sheet(rows)

    ist = timezone(timedelta(hours=5, minutes=30))
    now_ist = datetime.now(ist)
    parsed["lastUpdated"] = now_ist.strftime("%d %b %Y, %I:%M %p IST")
    parsed["lastUpdatedIso"] = datetime.now(timezone.utc).isoformat()

    with open(OUT_PATH, "w") as f:
        json.dump(parsed, f, indent=2)

    print(f"Wrote {OUT_PATH} — {len(parsed['feed'])} feed rows, "
          f"{len(parsed['monthLocations'])} month rows.")


if __name__ == "__main__":
    main()
