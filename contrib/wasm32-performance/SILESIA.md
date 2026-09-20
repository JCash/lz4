# Silesia wasm32 benchmark

This standalone report uses the same corpus as the native benchmark in the top-level README. Both compression and decompression execute in WebAssembly; no native compression timing is substituted.

For the same-run comparison against vanilla Zstd and zlib, see [the cross-codec benchmark](results/CODEC-COMPARISON.md).

## Results

| Compressor | Factor | Compression | Decompression |
|:--|--:|--:|--:|
| memcpy | 1.000 | 71,522 MB/s | 71,522 MB/s |
| **LZ4 default** | **2.085** | **790 MB/s** | **4,977 MB/s** |
| **LZ4 HC -9** | **2.721** | **47 MB/s** | **5,996 MB/s** |

| Data compressed with | Stock decode MB/s | Patched decode MB/s | Gain |
|:--|--:|--:|--:|
| LZ4 default | 4,109 | 4,977 | 21.1% |
| LZ4 HC -9 | 4,812 | 5,996 | 24.6% |

Tables use the independent confirmation run: [raw samples](results/silesia-confirmation.json), [aggregated values](results/silesia-confirmation-summary.json). The [initial run](results/silesia-browser.json) and its [summary](results/silesia-browser-summary.json) are retained separately. Both runs verified all round trips and identical stock/patched compressed bytes.

## Inputs and build

- All 12 files from the [Silesia corpus](https://sun.aei.polsl.pl/~sdeor/index.php?page=silesia), totaling 211,938,580 uncompressed bytes. Each file is one independent raw LZ4 block, without frame headers or a dictionary.
- `harness/silesia.py` downloads the author's `.bz2` files, checks their published raw sizes and MD5 hashes, and records SHA-256 hashes in `results/silesia-corpus.json`. Corpus bytes remain in ignored `local/silesia/`.
- Stock sources come from the commit in `base.json`. Patched sources come directly from the working tree, including `lib/lz4.c` and `lib/lz4hc.c`; this benchmark does not assume the patch files reflect the current source. Source hashes, module hashes, and compiler commands are recorded in `results/silesia-build.json` and embedded in each browser result.
- Emscripten 4.0.6, `-O3 -DNDEBUG -std=c90`, scalar wasm32, single thread. No SIMD, memory64, or explicit LTO. Each instance has 256 MiB of fixed linear memory and a 1 MiB stack.
- Measurement host: Apple M5 Max, macOS 27.0, Chromium 153 in the Codex in-app browser. Exact browser user agent and timestamp are in the result JSON. These measurements do not establish performance on other browsers or CPUs.

## Method

The harness calls `LZ4_compress_default`, `LZ4_compress_HC` at level 9, and `LZ4_decompress_safe`. The `memcpy` reference uses Emscripten's C `memcpy`; inspection of the generated Wasm confirms a `memory.copy` instruction remains inside the counted repetition loop. All timed repetitions run in a C loop inside Wasm.

For every file, both modules compress it with both encoders. The harness requires the stock and patched compressed bytes to be identical and verifies every decoded byte against the original. Input SHA-256 hashes and the memcpy result are also checked before timing. Compression speed is measured using the patched module; the patch changes only decoder selection.

Each operation receives three warmup batches, followed by seven measured batches targeting approximately 100 ms each (one compression of a large file can take longer). Operation order rotates and reverses between samples. The input and output buffers are reused. Fetching, input copying from JavaScript, hashing, verification, and harness allocations are outside the timer. Allocations performed internally by the compression API remain included.

For each file and operation, take the median milliseconds per repetition. Corpus speed is total uncompressed bytes divided by the sum of those per-file medians, in decimal MB/s. It is not the arithmetic mean of file speeds. Factor is total original bytes divided by total compressed bytes. These are warm-buffer codec measurements, not download or application startup times. The older native README table uses a different machine, compiler, library version, and harness, so the two tables cannot isolate Wasm overhead.

## Reproduce

Requires Python 3.12+, Emscripten (activate its SDK first), and a browser. From the repository root:

```sh
python3 contrib/wasm32-performance/harness/silesia.py --emcc /path/to/emcc
python3 contrib/wasm32-performance/harness/serve.py
```

Open `http://127.0.0.1:8765/harness/silesia.html` and wait for `DONE`. Keep other CPU-heavy work idle. The loopback server saves `results/silesia-browser.json` automatically. To preserve another run, open `http://127.0.0.1:8765/harness/silesia.html?name=silesia-confirmation` instead.

```sh
python3 contrib/wasm32-performance/harness/silesia_report.py
# For an optional second run:
python3 contrib/wasm32-performance/harness/silesia_report.py silesia-confirmation
```

The builder also accepts the existing experiment's ignored `local/config.json`, `local/emconfig.py`, and `local/em-cache` when present. A fresh checkout can use an activated SDK without those machine-specific files. It needs access to the base Git commit and the public corpus download site; the game-resource and Defold comparison fixtures are not required for Silesia.
