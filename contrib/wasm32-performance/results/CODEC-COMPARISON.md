# Wasm32: LZ4 before/after compared with vanilla Zstd and zlib

Apple M5 Max, macOS 27.0, Chromium 153.0.0.0, `-O3`, scalar wasm32, one thread. All codecs were measured together using the same 12-file Silesia corpus (211,938,580 bytes). Values are decimal MB/s of uncompressed data.

Compiler: `emcc (Emscripten gcc/clang-like replacement + linker emulating GNU ld) 4.0.6 (1ddaae4d2d6dfbb678ecc193bc988820d1fc4633)`.

| Codec / level | Factor | Compression | Stock decode | Improved decode | Decode gain |
|:--|--:|--:|--:|--:|--:|
| LZ4 default | 2.085 | 779 MB/s | 4,080 MB/s | 4,952 MB/s | 21.4% |
| LZ4 HC9 | 2.721 | 46 MB/s | 4,769 MB/s | 5,963 MB/s | 25.0% |
| Zstd 1 | 2.894 | 670 MB/s | 1,563 MB/s | — | — |
| Zstd 3 | 3.205 | 440 MB/s | 1,396 MB/s | — | — |
| Zstd 6 | 3.461 | 134 MB/s | 1,478 MB/s | — | — |
| zlib 1 | 2.744 | 165 MB/s | 469 MB/s | — | — |
| zlib 6 | 3.107 | 48 MB/s | 500 MB/s | — | — |

Compression in this table uses the stock build. Both compression and decompression run in Wasm. The changes target decompression; stock and improved builds produced identical compressed bytes at every tested LZ4 level. “Improved” means the selected local LZ4 wasm32 patches. Zstd and zlib are vanilla upstream releases; no local Zstd patches are built or measured by this harness.

LZ4 is the 1.10.0 development baseline pinned in `base.json`, before/after its fast-loop and 64-byte-copy changes. [Zstd 1.5.7](https://github.com/facebook/zstd/releases/tag/v1.5.7) comes directly from the official release archive, verified against its published SHA-256. zlib is upstream 1.3.1, pinned to Emscripten 4.0.6’s archive checksum and compiled directly with `-O3`. Exact revisions, source/module hashes, and commands are embedded in the raw result.

The Emscripten `memcpy` reference measured 71,533 MB/s in this run.

## Measurement method

Each file is one independent input: a raw LZ4 block, a Zstd frame, or a zlib stream. No dictionaries or cross-file history are used. Framing and zlib checksum work are included in the corresponding public APIs; these are complete codec operations, not identical wire formats.

The timed APIs are `LZ4_compress_default`, `LZ4_compress_HC(...,9)`, `LZ4_decompress_safe`, `ZSTD_compress`, `ZSTD_decompress`, `compress2`, and `uncompress`. Zstd and zlib use their one-shot APIs, so context setup/allocation and checksums performed by those calls are timed. Likewise, any internal LZ4 allocation remains timed. Fetches, JavaScript input copies, harness allocations, hashes, and output verification are excluded. Buffers are reused.

Every file/module/level is checked byte-for-byte before timing. Stock and patched compressed streams must match. Each operation receives three warmup batches and 7 measured batches targeting 100 ms each; a single slow compression can exceed that duration. Repetitions run inside Wasm. Execution order rotates with a stride of seven and reverses every other sample. Corpus throughput is total bytes divided by the sum of per-file median time per repetition.

LZ4 modules retain the preceding Silesia harness and 256 MiB fixed linear memory; the other modules use the same ABI and flags with 512 MiB to hold three compressed levels and encoder workspace. Both use a 1 MiB stack. Memory does not grow during timing. Zstd uses its upstream single-file library builder. No SIMD, memory64, or explicit LTO flags are enabled.

These are warm-buffer measurements on one browser/CPU. They do not isolate native-versus-Wasm overhead or predict download/startup time. Small differences in compression rates between stock/patched builds below should not be interpreted as an encoder optimization. The original native README table remains unchanged.

## Full before/after measurements

| Build | Level | Factor | Compression | Decompression |
|:--|:--|--:|--:|--:|
| lz4-stock | default | 2.085 | 779 MB/s | 4,080 MB/s |
| lz4-stock | hc9 | 2.721 | 46 MB/s | 4,769 MB/s |
| lz4-patched | default | 2.085 | 778 MB/s | 4,952 MB/s |
| lz4-patched | hc9 | 2.721 | 46 MB/s | 5,963 MB/s |
| zstd | 1 | 2.894 | 670 MB/s | 1,563 MB/s |
| zstd | 3 | 3.205 | 440 MB/s | 1,396 MB/s |
| zstd | 6 | 3.461 | 134 MB/s | 1,478 MB/s |
| zlib | 1 | 2.744 | 165 MB/s | 469 MB/s |
| zlib | 6 | 3.107 | 48 MB/s | 500 MB/s |

[Raw timings](codec-comparison.json) · [Aggregated values](codec-comparison-summary.json) · [Build commands and provenance](compare-build.json)

## Reproduce

Requires Python 3.12+, Emscripten, this LZ4 checkout, and a browser. Use the compiler version recorded above to reproduce this run. From the LZ4 repository root:

```sh
python3 contrib/wasm32-performance/harness/compare_build.py --emcc /path/to/emcc
python3 contrib/wasm32-performance/harness/serve.py
```

Open `http://127.0.0.1:8765/harness/compare.html` and wait for `DONE`. Keep other CPU-heavy work idle. The loopback server saves the raw JSON and per-file progress automatically.

```sh
python3 contrib/wasm32-performance/harness/compare_report.py --host "your CPU and OS"
```

The build fetches public Silesia data and the pinned vanilla Zstd/zlib source archives into ignored `local/`. Stock LZ4 comes from its pinned Git commit; patched LZ4 comes from the working tree. The separate experimental Zstd checkout is never read. An activated SDK can be used without `--emcc`; existing ignored local SDK configuration is also supported.
