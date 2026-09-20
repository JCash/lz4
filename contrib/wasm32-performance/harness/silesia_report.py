#!/usr/bin/env python3
"""Aggregate Silesia timings by bytes / total per-file median elapsed time."""
import argparse
import json
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('name', nargs='?', default='silesia-browser')
args = parser.parse_args()
data = json.loads((ROOT / 'results' / (args.name + '.json')).read_text())
groups = {}
for result in data['results']:
    key = (result['variant'], result['codec'], result['direction'])
    groups.setdefault(key, []).append(result)
summary = []
for (variant, codec, direction), rows in groups.items():
    assert len(rows) == len(data['corpus']['files'])
    total = sum(row['bytes'] for row in rows)
    compressed = sum(row['compressed'] for row in rows)
    ms = sum(median(sample['ms'] / sample['rounds'] for sample in row['samples']) for row in rows)
    summary.append(dict(variant=variant, codec=codec, direction=direction,
        bytes=total, compressed=compressed, factor=total / compressed, MBps=total / ms / 1000))
(ROOT / 'results' / (args.name + '-summary.json')).write_text(json.dumps(summary, indent=2) + '\n')
for row in summary:
    print(f"{row['variant']:7} {row['codec']:7} {row['direction']:10} factor {row['factor']:.3f} {row['MBps']:.1f} MB/s")
