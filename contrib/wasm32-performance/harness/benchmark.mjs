export async function benchmark({variants, levels=['lz4hc9'], sampleCount=9, targetMs=150}, read, log=()=>{}) {
    const files=JSON.parse(new TextDecoder().decode(await read('local/corpus/manifest.json')));
    const output={variants,levels,sampleCount,targetMs,results:[]};
    for(const codec of levels){
        const modules=[];
        for(const variant of variants){
            const {instance}=await WebAssembly.instantiate(await read(`local/build/${variant}.wasm`),{env:{bench_now:()=>performance.now(),emscripten_notify_memory_growth:()=>{}},wasi_snapshot_preview1:{proc_exit:n=>{throw Error(`exit ${n}`);}}});
            const e=instance.exports;e._initialize?.();e.setup();
            const entries=[];
            for(const f of files){
                const data=await read(`local/corpus/data/${f.id}.${codec}`),raw=await read(`local/corpus/data/${f.id}.raw`);
                const src=e.malloc(data.length),dst=e.malloc(f.size);
                new Uint8Array(e.memory.buffer).set(data,src);
                if(e.decode(src,data.length,dst,f.size)!==f.size)throw Error(`decode length: ${variant} ${f.id}`);
                const result=new Uint8Array(e.memory.buffer,dst,f.size);
                for(let j=0;j<raw.length;j++)if(result[j]!==raw[j])throw Error(`decode bytes: ${variant} ${f.id}`);
                entries.push({...f,src,dst,compressed:data.length});
            }
            modules.push({variant,e,entries});
        }
        for(const group of ['textures','structured']){
            const runners=[];
            for(const {variant,e,entries} of modules){
                const selected=entries.filter(f=>f.group===group),total=selected.reduce((s,f)=>s+f.size,0);
                const ptr=e.malloc(selected.length*16),view=new DataView(e.memory.buffer);
                selected.forEach((f,i)=>[f.src,f.compressed,f.dst,f.size].forEach((n,j)=>view.setUint32(ptr+16*i+4*j,n,true)));
                const run=rounds=>{const t=performance.now();if(e.batch(ptr,selected.length,rounds)<0)throw Error('batch');return performance.now()-t;};
                let rounds=1;
                for(let i=0;i<5;i++){const ms=run(rounds);rounds=Math.max(1,Math.ceil(rounds*40/Math.max(.01,ms)));await new Promise(r=>setTimeout(r,0));}
                rounds=Math.max(1,Math.ceil(rounds*targetMs/40));
                runners.push({variant,e,total,run,rounds,samples:[]});
            }
            // Rotate order, reversing every other round to reduce position bias.
            for(let i=0;i<sampleCount;i++){
                let order=[...runners.slice(i%runners.length),...runners.slice(0,i%runners.length)];
                if(i%2)order.reverse();
                for(const r of order){
                    r.e.profile_reset?.();const ms=r.run(r.rounds);
                    r.samples.push({ms,rounds:r.rounds,MBps:r.total*r.rounds/ms/1000,phases:r.e.profile_time?[0,1,2].map(k=>r.e.profile_time(k)):null});
                    await new Promise(r=>setTimeout(r,0));
                }
            }
            for(const r of runners)output.results.push({codec,group,variant:r.variant,bytes:r.total,samples:r.samples});
            log(`Finished ${codec} ${group}`);
        }
    }
    return output;
}
