# LZ4 wasm32 fast decode loops

Baseline: LZ4 `0774d05537f9762f838f7ab541b7765f1a729cb5` (1.10.0 development checkout). Defold’s vendored 1.9.4 decoder was built separately as a reference, using the same wrapper and toolchain.

## Result and implementation

The selected changes enable LZ4’s existing fast decode loop on wasm32 and reuse the existing ARM64 64-byte copy path. The implementation consists of four architecture-guard changes in lib/lz4.c; the underlying copy loops, input/output checks, format, and compressor are unchanged.

- `patches/0001-enable-fast-loop.patch` enables the existing portable fast loop by default on wasm32. The existing LZ4_FAST_DEC_LOOP build override remains supported. The same first-stage experiment can be selected without source changes using `-DLZ4_FAST_DEC_LOOP=1`.
- `patches/0002-wide-copy-loop.patch` makes the existing 64-byte copy helper and its guarded literal/match paths available on wasm32. Matches use this path only when offset is at least 64; close overlapping matches retain the existing handling.
- `patches/rejected/0003-wide-length-scan.patch` tried reading groups of eight 255-valued length-extension bytes. It did not improve this workload consistently and is not applied.

Unlike Zstd, LZ4 has no Huffman/FSE bit accumulator to widen. Its ordinary eight-byte copy already becomes i64 loads/stores in Wasm. The opportunity here is selecting existing loop implementations that were disabled by architecture detection. No SIMD or memory64 is required.

## Browser measurements

Apple M5 Max, Chromium 153, Emscripten 4.0.6, scalar wasm32, -O3. All variants decode the same 92 compiled SideScroller resources, previously compressed individually with LZ4 HC9. Seven textures contain 16,257,440 uncompressed bytes; the other 85 resources contain 467,103 bytes.

The screening run used nine samples per variant and group. The independent confirmation used seventeen, with warmup and rotating/reversing execution order. Each sample runs a Wasm batch for approximately 150 ms. Allocation, fetches, and copies into Wasm memory are excluded. All outputs are verified before timing. GB/s below is decimal uncompressed throughput; the table uses confirmation medians.

| Data | Defold 1.9.4 GB/s | Current stock GB/s | Fast 32-byte loop GB/s | Fast 64-byte loop GB/s | Selected gain over stock |
|---|---:|---:|---:|---:|---:|
| textures | 6.69 | 6.71 | 8.59 | 9.22 | 37.4% |
| structured | 11.37 | 11.37 | 12.79 | 12.70 | 11.7% |

This is a decoder throughput result on one browser/CPU and a texture-heavy fixture corpus, not end-to-end game startup timing. The default current decoder and Defold 1.9.4 were close in these runs. The selected patch targets this current LZ4 checkout; no Defold engine source or build flags have been changed.

### Screening all candidates

| Candidate | Textures: gain over stock | Other resources: gain over stock |
|---|---:|---:|
| defold194 | -0.4% | +0.0% |
| stock | +0.0% | +0.0% |
| fast32 | +27.5% | +12.5% |
| fast64 | +36.3% | +12.0% |
| length64 | -0.3% | +0.1% |
| fast32-length64 | +28.2% | +11.0% |
| fast64-length64 | +35.1% | +11.2% |

## Code size

The size builds omit benchmark loops and use otherwise identical settings. Values include the common allocation/export scaffold. Differences are standalone decoder deltas, not a measured linked Defold engine delta. Gzip uses level 9, Brotli level 11.

| Variant | Raw Wasm bytes | Gzip bytes | Brotli bytes |
|---|---:|---:|---:|
| defold194 | 7,983 | 3,626 | 3,010 |
| stock | 8,073 | 3,661 | 3,072 |
| fast32 | 9,088 | 4,089 | 3,450 |
| fast64 | 9,242 | 4,155 | 3,468 |

The selected decoder adds 1,169 raw bytes, 494 gzip bytes, and 396 Brotli bytes over current stock.

## Why these paths help this corpus

- textures: 88.7% of decoded bytes come from matches; 88.9% of match bytes use offsets of at least 64, which can use the wider path when output bounds permit.
- structured: 71.2% of decoded bytes come from matches; 88.0% of match bytes use offsets of at least 64, which can use the wider path when output bounds permit.

These are encoded-work counts, not phase timings or hardware-counter measurements. They explain why larger copies are a plausible benefit, while the repeated uninstrumented benchmarks establish the observed gain. Most individual matches remain short; both fast and safe loops retain dedicated short-match paths.

## Validation

- 5,241 valid raw blocks passed in every candidate: 92 game resources, 4,000 blocks made by LZ4 fast/HC9 compression of deterministic generated inputs, and 1,149 hand-encoded literal/length/offset boundary blocks.
- Hand-encoded cases cover small overlap offsets, offsets 63/64/65, offsets 65,534/65,535, copy-width boundaries, and long extension-byte runs. A native decoder independently verified every generated block.
- All candidates matched stock on 12,000 deterministic truncations, bit flips, and short-output cases. Successful output bytes, success/failure, and observed negative error offsets matched; all output guards stayed intact.
- The selected fast64 variant passed the same 5,241 valid and 12,000 malformed/short-output cases under WebAssembly AddressSanitizer and UndefinedBehaviorSanitizer, with exact-sized allocations and assertions enabled. No sanitizer reports occurred.
- The upstream fuzzer completed 1,000 randomized wasm32 cycles with seed 1753 and assertions enabled, covering compression, decompression, dictionary, streaming, and partial-decode paths. The harness selects its existing malloc/free fallback because Emscripten cannot honor its Unix low-address mmap request; this does not validate that low-address mmap scenario.
- Native make check, source consistency, and whitespace checks are recorded in validation-status.json.

These are bounded tests on one Wasm engine/host, not exhaustive fuzzing or proof of memory safety. Firefox, WebKit, x86-64 hosts, a final linked engine build, and representative production archives remain to be measured. LZ4’s own source cautions that fast-loop performance can vary by CPU.

## Reproduction

From the repository root:

```sh
python3 contrib/wasm32-performance/harness/make_patches.py
python3 contrib/wasm32-performance/harness/build.py
python3 contrib/wasm32-performance/harness/build.py stock fast32 fast64 defold194 --size
python3 contrib/wasm32-performance/harness/serve.py
```

Open `http://127.0.0.1:8765/harness/benchmark.html?name=confirmation&samples=17&variants=defold194,stock,fast32,fast64` in the browser. The server binds only to loopback and saves JSON under results. Avoid other CPU-heavy work during timings.

```sh
node contrib/wasm32-performance/harness/validate.mjs
python3 contrib/wasm32-performance/harness/validate_build.py fast64
node contrib/wasm32-performance/harness/validate.mjs stock fast64-asan
node contrib/wasm32-performance/local/build/fast64-fuzzer.cjs -s1753 -t1 -i1000
make -j4 check
git diff --check
```

The builder uses the Git revision pinned in base.json plus the selected patches, in ignored source copies. It does not reset or check out the working tree. local/config.json and local/emconfig.py select the installed SDK. local/ also contains the complete test corpus, cached compiler runtime, generated modules, and a copy of the Defold 1.9.4 sources used for comparison. Those generated/machine-specific inputs are ignored by Git; a fresh clone needs them supplied.

prepare_validation.py regenerates the supplemental corpus from the deterministic plain-output fixtures saved in the Zstd experiment. The corpus manifest and hashes are retained in results. The fuzzer portability adjustment is recorded in harness/fuzzer-wasm.patch, and is applied only to its generated test source.
