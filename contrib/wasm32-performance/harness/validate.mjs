#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..'),corpus=path.join(root,'local/corpus');
const read=p=>fs.readFileSync(path.join(corpus,p));
const variants=process.argv.slice(2);if(!variants.length)variants.push('stock','fast32','fast64','length64','fast32-length64','fast64-length64');
const manifest=JSON.parse(read('manifest.json'));
const cases=manifest.map(f=>({id:'game-'+f.id,raw:`data/${f.id}.raw`,input:`data/${f.id}.lz4hc9`}));
for(const f of JSON.parse(read('validation-manifest.json')))cases.push({id:f.label,raw:`validation/${f.id}.raw`,input:`validation/${f.id}.lz4`});
const modules=[];
for(const variant of variants){
 if(variant.endsWith('-asan')){
  const {default:create}=await import(path.join(root,`local/build/${variant}.mjs`));const e=await create();e._setup();modules.push({variant,e,asan:true});
 }else{
  const {instance}=await WebAssembly.instantiate(fs.readFileSync(path.join(root,`local/build/${variant}.wasm`)),{env:{emscripten_notify_memory_growth:()=>{}},wasi_snapshot_preview1:{proc_exit:n=>{throw Error(`exit ${n}`);}}});
  const e=instance.exports;e._initialize?.();e.setup();modules.push({variant,e,asan:false});
 }
}
function decode(m,data,size){
 const malloc=m.asan?m.e._malloc:m.e.malloc,free=m.asan?m.e._free:m.e.free;
 const src=malloc(Math.max(1,data.length)),guard=malloc(Math.max(1,size)+(m.asan?0:128)),dst=guard+(m.asan?0:64);
 let heap=m.asan?m.e.HEAPU8:new Uint8Array(m.e.memory.buffer);heap.set(data,src);
 // Initialize equally: malformed zero-offset blocks can reference unwritten output.
 heap.fill(0x91,dst,dst+size);
 if(!m.asan){heap.fill(0xab,guard,dst);heap.fill(0xcd,dst+size,dst+size+64);}
 const n=(m.asan?m.e._decode:m.e.decode)(src,data.length,dst,size);
 heap=m.asan?m.e.HEAPU8:new Uint8Array(m.e.memory.buffer);
 if(!m.asan&&(!heap.subarray(guard,dst).every(x=>x===0xab)||!heap.subarray(dst+size,dst+size+64).every(x=>x===0xcd)))throw Error(`guard damaged: ${m.variant}`);
 if(n>size)throw Error('oversized output');
 const result={n:n<0?-1:n,errorOffset:n<0?n:null,data:n<0?null:Buffer.from(heap.subarray(dst,dst+n))};free(guard);free(src);return result;
}
for(const c of cases){
 const raw=read(c.raw),data=read(c.input);
 for(const m of modules){const r=decode(m,data,raw.length);if(r.n!==raw.length||!r.data.equals(raw))throw Error(`valid mismatch ${c.id} ${m.variant}`);}
}
console.log('Valid blocks passed:',cases.length);
let seed=1753;const random=()=>{seed^=seed<<13;seed^=seed>>>17;seed^=seed<<5;return seed>>>0;};
const differences=[];let errorOffsetDifferences=0;
for(let i=0;i<12000;i++){
 const c=cases[random()%cases.length];let data=Buffer.from(read(c.input)),size=fs.statSync(path.join(corpus,c.raw)).size;
 if(i%3===0)data=data.subarray(0,random()%data.length);
 else if(i%3===1)data[random()%data.length]^=1<<(random()%8);
 else size=random()%Math.max(1,size);
 const got=modules.map(m=>decode(m,data,size)),a=got[0];
 for(let j=1;j<modules.length;j++){
  const b=got[j];
  if(a.n!==b.n||(a.n>=0&&!a.data.equals(b.data)))differences.push({test:i,id:c.id,variant:modules[j].variant,capacity:size,baseline:a.n,patched:b.n});
  else if(a.n<0&&a.errorOffset!==b.errorOffset)errorOffsetDifferences++;
 }
}
const result={validBlocks:cases.length,malformedOrShortOutputCases:12000,variants,exactAllocations:true,outputGuards:'passed on non-sanitized variants',differences,errorOffsetDifferences};
const name=variants.some(v=>v.endsWith('-asan'))?'validation-sanitized':'validation';
fs.writeFileSync(path.join(root,`results/${name}.json`),JSON.stringify(result,null,2));
console.log(JSON.stringify({...result,differences:Object.fromEntries(variants.slice(1).map(v=>[v,differences.filter(x=>x.variant===v).length]))},null,2));
if(differences.length || errorOffsetDifferences){
 console.error(`Validation failed: ${differences.length} decode mismatches and ${errorOffsetDifferences} error-offset mismatches. See results/${name}.json.`);
 process.exitCode=1;
}
