#!/usr/bin/env python3
from pathlib import Path
import argparse,difflib,json,os,subprocess
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('variant');p.add_argument('--fuzzer-only',action='store_true');a=p.parse_args()
config=json.loads((ROOT/'local/config.json').read_text());env=dict(os.environ,EM_CONFIG=str(ROOT/'local/emconfig.py'),EM_CACHE=str(ROOT/'local/em-cache'))
build=ROOT/'local/build';src=build/(a.variant+'-source')
common=[config['emcc'],'-O1','-DLZ4_DEBUG=1','-sALLOW_MEMORY_GROWTH=1','-sMAXIMUM_MEMORY=4294967296','-sINITIAL_MEMORY=134217728','-sSTACK_SIZE=2097152']
if not a.fuzzer_only:
 cmd=common+['-fsanitize=address,undefined','-fno-sanitize-recover=all','-DCODEC=1','-I'+str(src/'lib'),str(ROOT/'harness/decoder.c'),str(src/'lib/lz4.c'),
  '--no-entry','-sMODULARIZE=1','-sEXPORT_ES6=1','-sENVIRONMENT=node','-sEXPORTED_FUNCTIONS='+json.dumps(['_setup','_decode','_malloc','_free']),'-o',str(build/(a.variant+'-asan.mjs'))]
 subprocess.run(cmd,env=env,check=True);(ROOT/'results/sanitizer-build.json').write_text(json.dumps(cmd,indent=2)+'\n')
# Emscripten cannot honor the Unix low-address mmap request. Select the
# fuzzer's existing malloc/free fallback without changing decoder tests.
fuzzer_original=(src/'tests/fuzzer.c').read_text()
fuzzer_port=fuzzer_original.replace('#ifdef __unix__   /* is expected to be triggered on linux+gcc */', '#if defined(__unix__) && !defined(__EMSCRIPTEN__)   /* native low-address mmap */')
assert fuzzer_port != fuzzer_original
fuzzer_source=build/'fuzzer-wasm.c';fuzzer_source.write_text(fuzzer_port)
(ROOT/'harness/fuzzer-wasm.patch').write_text(''.join(difflib.unified_diff(fuzzer_original.splitlines(True),fuzzer_port.splitlines(True),fromfile='a/tests/fuzzer.c',tofile='b/tests/fuzzer.c')))
cmd=common+['-O2','-I'+str(src/'lib'),'-I'+str(src/'programs'),'-I'+str(src/'tests'),
 *[str(src/f) for f in ['lib/lz4.c','lib/lz4hc.c','lib/xxhash.c']],
 str(fuzzer_source),'-sENVIRONMENT=node','-sEXIT_RUNTIME=1','-o',str(build/(a.variant+'-fuzzer.cjs'))]
subprocess.run(cmd,env=env,check=True);(ROOT/'results/fuzzer-build.json').write_text(json.dumps(cmd,indent=2)+'\n')
print('Built sanitizer decoder and upstream wasm32 fuzzer',flush=True)
