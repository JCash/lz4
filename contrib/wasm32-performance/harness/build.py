#!/usr/bin/env python3
from pathlib import Path
import argparse,gzip,hashlib,io,json,os,shutil,subprocess,tarfile
ROOT=Path(__file__).resolve().parents[1];REPO=ROOT.parents[1]
BASE=json.loads((ROOT/'base.json').read_text())['commit']
PATCHES={'stock':[],'fast32':['0001-enable-fast-loop.patch'],'fast64':['0001-enable-fast-loop.patch','0002-wide-copy-loop.patch'],
 'length64':['rejected/0003-wide-length-scan.patch'],'fast32-length64':['0001-enable-fast-loop.patch','rejected/0003-wide-length-scan.patch'],
 'fast64-length64':['0001-enable-fast-loop.patch','0002-wide-copy-loop.patch','rejected/0003-wide-length-scan.patch'],'defold194':[]}
p=argparse.ArgumentParser();p.add_argument('variants',nargs='*',choices=list(PATCHES));p.add_argument('--size',action='store_true');a=p.parse_args()
config=json.loads((ROOT/'local/config.json').read_text());env=dict(os.environ,EM_CONFIG=str(ROOT/'local/emconfig.py'),EM_CACHE=str(ROOT/'local/em-cache'))
build=ROOT/'local/build';build.mkdir(parents=True,exist_ok=True)
log=ROOT/'results'/('build-size.json' if a.size else 'build.json');commands=json.loads(log.read_text()) if log.exists() else {}
for variant in a.variants or list(PATCHES):
 src=build/(variant+'-source');stamp=BASE+''.join(hashlib.sha256((ROOT/'patches'/name).read_bytes()).hexdigest() for name in PATCHES[variant])
 if variant=='defold194':stamp+=hashlib.sha256((ROOT/'local/defold194/lz4.c').read_bytes()).hexdigest()
 if src.exists() and (not (src/'.stamp').exists() or (src/'.stamp').read_text()!=stamp):shutil.rmtree(src)
 if not src.exists():
  src.mkdir()
  if variant=='defold194':shutil.copytree(ROOT/'local/defold194',src/'lib')
  else:
   archive=subprocess.check_output(['git','archive',BASE,'lib','tests','programs'],cwd=REPO)
   with tarfile.open(fileobj=io.BytesIO(archive)) as tar:tar.extractall(src,filter='data')
   for name in PATCHES[variant]:subprocess.run(['git','apply',str(ROOT/'patches'/name)],cwd=src,check=True)
  (src/'.stamp').write_text(stamp)
 exports=['_setup','_decode','_malloc','_free']+([] if a.size else ['_batch'])
 out=build/(variant+('-size' if a.size else '')+'.wasm')
 cmd=[config['emcc'],'-O3','-DNDEBUG','-DCODEC=1','-DBENCH='+str(int(not a.size)),str(ROOT/'harness/decoder.c'),'-I'+str(src/'lib'),str(src/'lib/lz4.c'),
      '--no-entry','-sSTANDALONE_WASM=1','-sFILESYSTEM=0','-sALLOW_MEMORY_GROWTH=1','-sINITIAL_MEMORY=67108864','-sSTACK_SIZE=1048576',
      '-sEXPORTED_FUNCTIONS='+json.dumps(exports),'-o',str(out)]
 subprocess.run(cmd,env=env,check=True);commands[variant]=cmd;print('Built',out.name,flush=True)
 if a.size:
  b=out.read_bytes();row=dict(variant=variant,raw=len(b),gzip=len(gzip.compress(b,compresslevel=9,mtime=0)),brotli=len(subprocess.check_output(['brotli','-q','11','-c',str(out)])))
  (ROOT/'results'/f'{variant}-size.json').write_text(json.dumps(row,indent=2)+'\n')
log.write_text(json.dumps(commands,indent=2)+'\n')
