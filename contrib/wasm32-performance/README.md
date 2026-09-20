# LZ4 wasm32 decompression performance

[Measurements, validation, and reproduction instructions](results/REPORT.md)

[LZ4 before/after compared with vanilla Zstd and zlib](results/CODEC-COMPARISON.md)

[Code review](REVIEW.md) · [Silesia wasm32 compression/decompression benchmark](SILESIA.md)

The selected changes are applied to `lib/lz4.c` and preserved as separate patches against the Git revision recorded in `base.json`:

1. `patches/0001-enable-fast-loop.patch`: enable the existing fast decode loop on wasm32.
2. `patches/0002-wide-copy-loop.patch`: allow the existing 64-byte copy path on wasm32, retaining its offset and buffer checks.

The eight-byte length-extension scan is retained under `patches/rejected/` and is not applied.

- `harness/`: pinned-revision variant builder, browser benchmark, corpus analysis/generation, validation and sanitizers.
- `results/`: raw timings, reports, compiler commands, validation outcomes, and logs.
- `local/`: ignored corpus, generated modules, source copies, compiler configuration/cache, and Defold 1.9.4 comparison sources.

This is an experimental default change for wasm32. It needs additional browser/CPU and final engine measurements before production integration. The compressed format and compression behavior are unchanged; Defold source has not been modified.

## Harness regression checks

Run `python3 contrib/wasm32-performance/harness/tests/test_harness.py -v` from the repository root. The tests need Python and Node, but no Wasm SDK or downloaded corpus. Controlled decoder faults verify that validation saves diagnostics and exits nonzero for status, output-byte, and error-offset mismatches. Report checks verify that captured compiler and timing metadata are used and that missing compiler metadata fails explicitly.
