#!/usr/bin/env python3
"""Aggregate and report a complete same-run Silesia codec comparison."""
import argparse
import json
from pathlib import Path
import re
from statistics import median

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('name', nargs='?', default='codec-comparison')
    parser.add_argument('--host', default='CPU and OS not recorded', help='Locally verified CPU and OS description')
    args = parser.parse_args()
    raw = json.loads((ROOT / 'results' / (args.name + '.json')).read_text())
    compiler = raw['build'].get('compiler')
    if not isinstance(compiler, str) or not compiler.strip():
        raise ValueError('Missing captured compiler metadata')
    for variant in raw['build']['variants']:
        if variant['family'] != 'lz4' and (variant['variant'] != 'stock' or not variant.get('vanilla')):
            raise ValueError('Non-LZ4 comparison entries must be vanilla upstream')
    files = {f['name'] for f in raw['corpus']['files']}
    if raw['completedFiles'] != len(files):
        raise ValueError('Cannot publish an incomplete corpus run')
    groups = {}
    for row in raw['results']:
        key = (row['id'], row['level'], row['direction'])
        groups.setdefault(key, []).append(row)
    summary = []
    for (name, level, direction), rows in groups.items():
        if len(rows) != len(files) or {r['file'] for r in rows} != files:
            raise ValueError('Missing/duplicate files: ' + str((name, level, direction)))
        if any(len(r['samples']) != raw['sampleCount'] for r in rows):
            raise ValueError('Missing samples')
        total = sum(r['bytes'] for r in rows)
        compressed = sum(r['compressed'] for r in rows)
        ms = sum(median(s['ms'] / s['rounds'] for s in r['samples']) for r in rows)
        summary.append(dict(id=name, level=level, direction=direction, bytes=total,
            compressed=compressed, factor=total / compressed, MBps=total / ms / 1000))
    data = {(r['id'], r['level'], r['direction']): r for r in summary}

    def speed(name, level, direction):
        return data[name, level, direction]['MBps']

    table = '| Codec / level | Factor | Compression | Stock decode | Improved decode | Decode gain |\n'
    table += '|:--|--:|--:|--:|--:|--:|\n'
    for family, levels in [('lz4', ['default', 'hc9']), ('zstd', ['1', '3', '6']), ('zlib', ['1', '6'])]:
        stock = family + '-stock' if family == 'lz4' else family
        if not any(r['id'] == stock for r in summary):
            continue
        for level in levels:
            factor = data[stock, level, 'compress']['factor']
            comp = speed(stock, level, 'compress')
            before = speed(stock, level, 'decompress')
            if family != 'lz4':
                after_text, gain_text = '—', '—'
            else:
                after = speed(family + '-patched', level, 'decompress')
                after_text, gain_text = f'{after:,.0f} MB/s', f'{100 * (after / before - 1):.1f}%'
            label = {'lz4': 'LZ4', 'zstd': 'Zstd', 'zlib': 'zlib'}[family] + ' ' + level.replace('hc9', 'HC9')
            table += f'| {label} | {factor:.3f} | {comp:,.0f} MB/s | {before:,.0f} MB/s | {after_text} | {gain_text} |\n'
    detail = '| Build | Level | Factor | Compression | Decompression |\n|:--|:--|--:|--:|--:|\n'
    for descriptor in raw['build']['variants']:
        for level in descriptor['levels']:
            name, level_id = descriptor['id'], level['id']
            comp = data[name, level_id, 'compress']
            detail += (f"| {name} | {level_id} | {comp['factor']:.3f} | {comp['MBps']:,.0f} MB/s | "
                       f"{speed(name, level_id, 'decompress'):,.0f} MB/s |\n")
    report = '# Wasm32: LZ4 before/after compared with vanilla Zstd and zlib\n\n'
    browser = re.search(r'Chrome/([0-9.]+)', raw['userAgent'])
    browser_name = 'Chromium ' + browser.group(1) if browser else raw['userAgent']
    report += (args.host + ', ' + browser_name + ', `-O3`, '
        'scalar wasm32, one thread. All codecs were measured together using the same 12-file '
        'Silesia corpus (211,938,580 bytes). Values are decimal MB/s of uncompressed data.\n\n')
    report += f'Compiler: `{compiler}`.\n\n'
    report += table
    report += ('\nCompression in this table uses the stock build. Both compression and decompression '
        'run in Wasm. The changes target decompression; stock and improved builds produced '
        'identical compressed bytes at every tested LZ4 level. “Improved” means the selected local '
        'LZ4 wasm32 patches. Zstd and zlib are vanilla upstream releases; no local Zstd patches '
        'are built or measured by this harness.\n\n')
    report += ('LZ4 is the 1.10.0 development baseline pinned in `base.json`, before/after its fast-loop '
        'and 64-byte-copy changes. [Zstd 1.5.7](https://github.com/facebook/zstd/releases/tag/v1.5.7) '
        'comes directly from the official release archive, verified against its published SHA-256. '
        'zlib is upstream 1.3.1, pinned to Emscripten 4.0.6’s archive checksum and compiled '
        'directly with `-O3`. Exact revisions, source/module hashes, and commands are embedded in the raw result.\n\n')
    report += ('The Emscripten `memcpy` reference measured '
        f"{speed('lz4-patched', 'memcpy', 'copy'):,.0f} MB/s in this run.\n\n")
    report += '## Measurement method\n\n'
    report += ('Each file is one independent input: a raw LZ4 block, a Zstd frame, or a zlib stream. '
        'No dictionaries or cross-file history are used. Framing and zlib checksum work are included '
        'in the corresponding public APIs; these are complete codec operations, not identical wire formats.\n\n'
        'The timed APIs are `LZ4_compress_default`, `LZ4_compress_HC(...,9)`, `LZ4_decompress_safe`, '
        '`ZSTD_compress`, `ZSTD_decompress`, `compress2`, and `uncompress`. Zstd and zlib use their '
        'one-shot APIs, so context setup/allocation and checksums performed by those calls are timed. '
        'Likewise, any internal LZ4 allocation remains timed. Fetches, JavaScript input copies, '
        'harness allocations, hashes, and output verification are excluded. Buffers are reused.\n\n'
        'Every file/module/level is checked byte-for-byte before timing. Stock and patched compressed '
        f'streams must match. Each operation receives three warmup batches and {raw["sampleCount"]} measured batches '
        f'targeting {raw["targetMs"]:g} ms each; a single slow compression can exceed that duration. Repetitions run '
        'inside Wasm. Execution order rotates with a stride of seven and reverses every other sample. '
        'Corpus throughput is total bytes divided by the sum of per-file median time per repetition.\n\n'
        'LZ4 modules retain the preceding Silesia harness and 256 MiB fixed linear memory; the other '
        'modules use the same ABI and flags with 512 MiB to hold three compressed levels and encoder '
        'workspace. Both use a 1 MiB stack. Memory does not grow during timing. Zstd uses its upstream '
        'single-file library builder. No SIMD, memory64, or explicit LTO flags are enabled.\n\n'
        'These are warm-buffer measurements on one browser/CPU. They do not isolate native-versus-Wasm '
        'overhead or predict download/startup time. Small differences in compression rates between '
        'stock/patched builds below should not be interpreted as an encoder optimization. The original '
        'native README table remains unchanged.\n\n')
    report += '## Full before/after measurements\n\n' + detail
    report += ('\n[Raw timings](' + args.name + '.json) · [Aggregated values](' + args.name + '-summary.json)'
               ' · [Build commands and provenance](compare-build.json)\n\n')
    report += '## Reproduce\n\n'
    report += ('Requires Python 3.12+, Emscripten, this LZ4 checkout, and a browser. '
        'Use the compiler version recorded above to reproduce this run. '
        'From the LZ4 repository root:\n\n```sh\n'
        'python3 contrib/wasm32-performance/harness/compare_build.py --emcc /path/to/emcc\n'
        'python3 contrib/wasm32-performance/harness/serve.py\n```\n\n'
        'Open `http://127.0.0.1:8765/harness/compare.html` and wait for `DONE`. Keep other CPU-heavy '
        'work idle. The loopback server saves the raw JSON and per-file progress automatically.\n\n```sh\n'
        'python3 contrib/wasm32-performance/harness/compare_report.py --host "your CPU and OS"\n```\n\n'
        'The build fetches public Silesia data and the pinned vanilla Zstd/zlib source archives into ignored `local/`. '
        'Stock LZ4 comes from its pinned Git commit; patched LZ4 comes from the working tree. '
        'The separate experimental Zstd checkout is never read. An activated SDK can be used without '
        '`--emcc`; existing ignored local SDK configuration is also supported.\n')
    (ROOT / 'results' / (args.name + '-summary.json')).write_text(json.dumps(summary, indent=2) + '\n')
    (ROOT / 'results/CODEC-COMPARISON.md').write_text(report)
    print(table)
    print(detail)


if __name__ == '__main__':
    main()
