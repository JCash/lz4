# Review of the wasm32 decoder changes

Reviewed on branch `wasm32-improvements` against the base in `base.json`.

No blocking correctness issue was found in the four architecture-guard changes in `lib/lz4.c`. The current source is byte-for-byte identical to the generated `fast64` source used for the recorded sanitizer, differential, and fuzzer checks. The selected patch files reproduce that source.

## Code review

- The default fast loop now includes `__wasm32__` inside the existing `#ifndef LZ4_FAST_DEC_LOOP`. An explicit build override still takes precedence. The fast loop already supports 32-bit x86; it does not require 64-bit pointers or a 64-bit `size_t`.
- The 64-byte helper and both call sites use the same architecture condition. Long literals enter the wider copy only after the existing integer-overflow checks and only when both input and output retain 64 bytes beyond the logical copy end.
- Matches enter the wider copy only when the offset is at least 64, so each individual 64-byte memcpy has non-overlapping source/destination ranges. The existing fast-loop output limit reserves the over-copy space. Offsets below 16 retain the existing overlap helper; offsets 16–63 retain the two 16-byte copies.
- External-dictionary handling occurs before the new match-copy branch. Small buffers, partial-decode limits, and block tails retain the existing safe paths. The earlier wasm32 upstream fuzzer exercises dictionary, streaming, and partial-decode paths as well as ordinary blocks.
- No encoder, public API, compressed format, or non-Wasm architecture condition is changed. No explicit Wasm SIMD instructions are introduced.

## Evidence

See `results/REPORT.md` and its linked/raw result files for the existing 5,241 valid-block checks, 12,000 malformed/short-output comparisons, Wasm ASan/UBSan run, 1,000 upstream Wasm fuzzer cycles, and native `make check`. The fuzzer uses the documented malloc fallback because the Unix low-address mmap setup is unsupported in Emscripten.

The additional Silesia benchmark builds the actual working source, checks both encoders against stock byte-for-byte, and verifies full decoded output for all 12 large files. See `SILESIA.md` for the measurement and aggregation method.

Additional review checks are recorded in `results/review-status.json`: compiling the current source with `LZ4_FAST_DEC_LOOP=0` produces a byte-identical Wasm module to the stock size build; native arm64 compilation produces a byte-identical object file to stock. Inspection of the Silesia module confirms the memcpy reference retains a copy inside its repetition loop.

Performance evidence is limited to Chromium on Apple M5 Max. Other browser engines/CPUs and a final linked Defold engine remain unmeasured. The standalone decoder adds 1,169 raw Wasm bytes (494 gzip / 396 Brotli); that is not a measured engine-size delta.
