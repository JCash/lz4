#!/usr/bin/env python3
from pathlib import Path
import difflib,json,subprocess
ROOT=Path(__file__).resolve().parents[1]
REPO=ROOT.parents[1]
BASE=json.loads((ROOT/'base.json').read_text())['commit']
source=subprocess.check_output(['git','show',BASE+':lib/lz4.c'],cwd=REPO,text=True)
def patch(name,before,after):
 (ROOT/'patches'/name).write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='a/lib/lz4.c',tofile='b/lib/lz4.c')))
assert source.count('#  elif defined(__aarch64__)')==1
fast=source.replace('#  elif defined(__aarch64__)','#  elif defined(__aarch64__) || defined(__wasm32__)')
patch('0001-enable-fast-loop.patch',source,fast)
assert fast.count('#ifdef __aarch64__')==3
wide=fast.replace('#ifdef __aarch64__','#if defined(__aarch64__) || defined(__wasm32__)')
patch('0002-wide-copy-loop.patch',fast,wide)
needle='''    if (likely(s != 255)) return length;
    do {'''
replacement='''    if (likely(s != 255)) return length;
#if defined(__wasm32__)
    /* Wasm supports unaligned i64 loads even with 32-bit addresses.
     * Skip groups of extension bytes without weakening the input bound
     * or the 32-bit length overflow check. */
    while ((size_t)(ilimit - *ipPtr) >= 8) {
        U64 extension;
        LZ4_memcpy(&extension, *ipPtr, sizeof(extension));
        if (extension != (U64)-1) break;
        *ipPtr += 8;
        length += 8 * 255;
        if (unlikely(length > ((Rvl_t)(-1)/2))) return rvl_error;
    }
#endif
    do {'''
assert source.count(needle)==1
length=source.replace(needle,replacement)
patch('rejected/0003-wide-length-scan.patch',source,length)
print('Generated three independent/dependent candidate patches')
