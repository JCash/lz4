#!/usr/bin/env python3
"""Describe encoded work; these byte counts are not CPU time measurements."""
from pathlib import Path
from collections import Counter
import json
ROOT=Path(__file__).resolve().parents[1]
files=json.loads((ROOT/'local/corpus/manifest.json').read_text())
results={}
for group in ['textures','structured']:
 counts=Counter()
 for f in files:
  if f['group']!=group:continue
  data=(ROOT/'local/corpus/data'/f"{f['id']}.lz4hc9").read_bytes();pos=0;out=0
  def length(value):
   global pos
   if value==15:
    while True:
     b=data[pos];pos+=1;value+=b;counts['extensionBytes']+=1
     if b!=255:break
   return value
  while pos<len(data):
   token=data[pos];pos+=1;lit=length(token>>4);pos+=lit;out+=lit;counts['literalBytes']+=lit;counts['sequences']+=1
   if pos==len(data):break
   offset=int.from_bytes(data[pos:pos+2],'little');pos+=2;match=length(token&15)+4;out+=match;counts['matchBytes']+=match
   counts['offsetLess16Bytes' if offset<16 else 'offset16To63Bytes' if offset<64 else 'offsetAtLeast64Bytes']+=match
   counts['shortMatches' if match<=18 else 'longMatches']+=1
  assert out==f['size']
 results[group]=dict(counts)
(ROOT/'results/block-analysis.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps(results,indent=2))
