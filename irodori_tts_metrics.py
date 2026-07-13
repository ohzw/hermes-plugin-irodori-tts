#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

DEFAULT_LOG = Path("~/.hermes/logs/tts-rewrite/timings.jsonl").expanduser()


def load_records(path: Path = DEFAULT_LOG, limit: int | None = None) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                rows.append(obj)
    if limit and limit > 0:
        rows = rows[-limit:]
    return rows


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    if len(values) == 1:
        return values[0]
    k = (len(values) - 1) * p
    lo = math.floor(k)
    hi = math.ceil(k)
    if lo == hi:
        return values[int(k)]
    return values[lo] * (hi - k) + values[hi] * (k - lo)


def stat(values: list[float]) -> dict[str, float]:
    values = [float(v) for v in values if v is not None]
    if not values:
        return {"avg": 0.0, "p50": 0.0, "p90": 0.0, "min": 0.0, "max": 0.0}
    return {
        "avg": statistics.fmean(values),
        "p50": percentile(values, 0.5),
        "p90": percentile(values, 0.9),
        "min": min(values),
        "max": max(values),
    }


def ms(record: dict[str, Any], key: str) -> float:
    timing = record.get("timing_ms") or {}
    if not isinstance(timing, dict):
        return 0.0
    return float(timing.get(key) or 0)


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    ok = [r for r in records if r.get("status") == "ok"]
    errors = [r for r in records if r.get("status") != "ok"]
    total_values = [ms(r, "total") for r in ok]
    rewrite_values = [ms(r, "rewrite") for r in ok]
    irodori_values = [ms(r, "irodori_request") for r in ok]
    server_values = [ms(r, "server_start_or_health") for r in ok]
    write_values = [ms(r, "write_output") for r in ok]
    other_values = [max(0.0, ms(r, "total") - ms(r, "rewrite") - ms(r, "irodori_request") - ms(r, "server_start_or_health") - ms(r, "write_output")) for r in ok]

    sums = {
        "rewrite": sum(rewrite_values),
        "irodori_request": sum(irodori_values),
        "server_start_or_health": sum(server_values),
        "write_output": sum(write_values),
        "other": sum(other_values),
    }
    denominator = sum(total_values) or 1.0
    ratios = {k: v / denominator for k, v in sums.items()}
    bottleneck = max(ratios, key=ratios.get) if ok else None

    by_model: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in ok:
        label = f"{r.get('rewrite_provider') or 'unknown'} / {r.get('rewrite_model') or 'unknown'}"
        by_model[label].append(r)

    model_summary = {}
    for label, rows in by_model.items():
        model_summary[label] = {
            "runs": len(rows),
            "rewrite_ms": stat([ms(r, "rewrite") for r in rows]),
            "total_ms": stat([ms(r, "total") for r in rows]),
        }

    return {
        "runs": len(records),
        "ok_runs": len(ok),
        "error_runs": len(errors),
        "latest_ts": records[-1].get("ts") if records else None,
        "total_ms": stat(total_values),
        "rewrite_ms": stat(rewrite_values),
        "irodori_request_ms": stat(irodori_values),
        "server_start_or_health_ms": stat(server_values),
        "write_output_ms": stat(write_values),
        "other_ms": stat(other_values),
        "bottleneck": bottleneck,
        "ratios": ratios,
        "by_model": model_summary,
    }


def seconds(ms_value: float) -> str:
    return f"{ms_value / 1000:.2f}s"


def print_summary(records: list[dict[str, Any]]) -> None:
    summary = summarize(records)
    print(f"Irodori TTS timings: last {summary['runs']} runs ({summary['ok_runs']} ok, {summary['error_runs']} errors)")
    if not records:
        print("No timing records yet.")
        return
    for label, key in [
        ("total", "total_ms"),
        ("rewrite", "rewrite_ms"),
        ("irodori", "irodori_request_ms"),
        ("server", "server_start_or_health_ms"),
        ("other", "other_ms"),
    ]:
        s = summary[key]
        print(f"{label:>8}: avg {seconds(s['avg']):>7}  p50 {seconds(s['p50']):>7}  p90 {seconds(s['p90']):>7}")
    print(f"bottleneck: {summary['bottleneck'] or 'n/a'}")
    if summary["by_model"]:
        print("\nBy rewrite model:")
        for label, item in sorted(summary["by_model"].items()):
            print(f"- {label}: runs={item['runs']} rewrite_avg={seconds(item['rewrite_ms']['avg'])} total_avg={seconds(item['total_ms']['avg'])}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize Irodori TTS timing logs")
    parser.add_argument("--log", default=str(DEFAULT_LOG), help="Path to timings.jsonl")
    parser.add_argument("--last", type=int, default=20, help="Number of recent records to summarize")
    parser.add_argument("--json", action="store_true", help="Print JSON summary")
    args = parser.parse_args()

    records = load_records(Path(args.log).expanduser(), limit=args.last)
    if args.json:
        print(json.dumps({"summary": summarize(records), "recent": records}, ensure_ascii=False, indent=2))
    else:
        print_summary(records)


if __name__ == "__main__":
    main()
