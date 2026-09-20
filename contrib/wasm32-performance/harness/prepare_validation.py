#!/usr/bin/env python3
"""Create a deterministic LZ4 block corpus, including overlap and length limits."""
from pathlib import Path
import argparse,ctypes as C,hashlib,json,random,subprocess
ROOT=Path(__file__).resolve().parents[1];REPO=ROOT.parents[1]
p=argparse.ArgumentParser();p.add_argument('--raw-corpus',type=Path,required=True);a=p.parse_args()
libpath=ROOT/'local/build/native.dylib'
subprocess.run(['clang','-O2','-shared','-fPIC',str(REPO/'lib/lz4.c'),str(REPO/'lib/lz4hc.c'),'-o',str(libpath)],check=True)
z=C.CDLL(str(libpath))
for name,types in [('LZ4_compress_default',[C.c_void_p,C.c_void_p,C.c_int,C.c_int]),('LZ4_compress_HC',[C.c_void_p,C.c_void_p,C.c_int,C.c_int,C.c_int]),('LZ4_decompress_safe',[C.c_void_p,C.c_void_p,C.c_int,C.c_int])]:
 f=getattr(z,name);f.argtypes=types;f.restype=C.c_int
out=ROOT/'local/corpus/validation';out.mkdir(exist_ok=True)
manifest=[]
def save(raw,compressed,label):
 i=len(manifest);base=f'{i:05}'
 (out/(base+'.raw')).write_bytes(raw);(out/(base+'.lz4')).write_bytes(compressed)
 dst=C.create_string_buffer(max(1,len(raw)))
 n=z.LZ4_decompress_safe(compressed,dst,len(compressed),len(raw))
 assert n==len(raw) and dst.raw[:n]==raw,label
 manifest.append(dict(id=base,label=label,size=len(raw),compressed=len(compressed),sha256=hashlib.sha256(raw).hexdigest()))
# Generated Zstd outputs are plain bytes here; only LZ4 compression is used.
for group in ['standard','small']:
 for rawfile in sorted((a.raw_corpus/group).glob('*')):
  if rawfile.suffix=='.zst':continue
  raw=rawfile.read_bytes();dst=C.create_string_buffer(len(raw)+len(raw)//255+32)
  for level in ['fast','hc9']:
   n=z.LZ4_compress_default(raw,dst,len(raw),len(dst)) if level=='fast' else z.LZ4_compress_HC(raw,dst,len(raw),len(dst),9)
   assert n>0
   save(raw,dst.raw[:n],f'{group}-{rawfile.name}-{level}')
def ext(n):
 return bytes([255])*(n//255)+bytes([n%255])
def literal(raw):
 return bytes([min(len(raw),15)<<4])+(ext(len(raw)-15) if len(raw)>=15 else b'')+raw
rng=random.Random(1749)
# Boundaries around token nibbles, length-extension chunks, and copy sizes.
lengths=sorted(set(range(33))|{63,64,65,127,128,129,254,255,256,269,270,271,524,525,526,2054,2055,2056,2309,2310,2311,65534,65535,65536})
for n in lengths:
 raw=rng.randbytes(n);save(raw,literal(raw),f'literal-length-{n}')
matchlengths=[4,7,8,15,16,17,18,19,20,31,32,33,63,64,65,255,273,274,275,2058,2059,2060,2313,2314,2315,65536]
for offset in list(range(1,33))+[63,64,65,127,128,255,256,4096,65534,65535]:
 prefix=rng.randbytes(offset)
 for match in matchlengths:
  tail=rng.randbytes(max(5,12-match))
  raw=prefix+(prefix*((match+offset-1)//offset))[:match]+tail
  block=bytes([(min(offset,15)<<4)|min(match-4,15)])+(ext(offset-15) if offset>=15 else b'')+prefix+offset.to_bytes(2,'little')+(ext(match-19) if match>=19 else b'')+literal(tail)
  save(raw,block,f'offset-{offset}-match-{match}')
(ROOT/'local/corpus/validation-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
(ROOT/'results/validation-corpus.json').write_text(json.dumps({'blocks':len(manifest),'origin':'2000 deterministic plain outputs, each LZ4 fast and HC9 compressed, plus hand-encoded length/offset boundaries','nativeReference':'current checkout LZ4_decompress_safe','seed':1749,'manifest':manifest},indent=2)+'\n')
print('Generated and native-verified',len(manifest),'LZ4 blocks',flush=True)
