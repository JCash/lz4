const pause = () => new Promise(resolve => setTimeout(resolve, 0));
const hash = async bytes => Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)),
    byte => byte.toString(16).padStart(2, '0')).join('');

function equal(actual, expected, label) {
    if (actual.length !== expected.length) throw Error(label + ': length');
    for (let i = 0; i < actual.length; ++i) {
        if (actual[i] !== expected[i]) throw Error(label + ': byte ' + i);
    }
}

export async function benchmark({sampleCount = 7, targetMs = 100}, read, log, checkpoint) {
    const corpus = JSON.parse(new TextDecoder().decode(await read('results/silesia-corpus.json')));
    const build = JSON.parse(new TextDecoder().decode(await read('results/compare-build.json')));
    const output = {sampleCount, targetMs, corpus, build, results: [], completedFiles: 0};
    const modules = [];
    for (const descriptor of build.variants) {
        if (descriptor.family !== 'lz4' && (descriptor.variant !== 'stock' || !descriptor.vanilla)) {
            throw Error('Comparison requires vanilla non-LZ4 libraries: ' + descriptor.id);
        }
        const binary = await read(descriptor.wasm);
        if (await hash(binary) !== descriptor.wasmSHA256) throw Error('Module hash: ' + descriptor.id);
        const {instance} = await WebAssembly.instantiate(binary, {
            wasi_snapshot_preview1: {proc_exit: n => { throw Error('Wasm exit ' + n); }},
        });
        instance.exports._initialize?.();
        modules.push({...descriptor, e: instance.exports});
    }
    for (const file of corpus.files) {
        log('Starting ' + file.name);
        const raw = await read('local/silesia/' + file.name);
        if (await hash(raw) !== file.sha256) throw Error('Input hash: ' + file.name);
        const jobs = [];
        const allocations = [];
        const streams = new Map();
        for (const module of modules) {
            const {id, family, variant, levels, e} = module;
            const capacity = e.bound(raw.length);
            const sizes = [raw.length, raw.length, capacity, ...levels.map(() => capacity)];
            const pointers = sizes.map(size => {
                const ptr = e.malloc(size);
                if (!ptr) throw Error('Allocation failed: ' + id);
                return ptr;
            });
            const [src, dst, scratch, ...compressedPtrs] = pointers;
            allocations.push({e, pointers});
            const bytes = (ptr, size) => new Uint8Array(e.memory.buffer, ptr, size);
            bytes(src, raw.length).set(raw);
            const add = (level, direction, operation, input, size, destination, limit, expected, compressed) => {
                const run = rounds => {
                    const start = performance.now();
                    const result = e.bench(operation, input, size, destination, limit, rounds);
                    const ms = performance.now() - start;
                    if (result !== expected) throw Error(`${id} ${level} ${direction}: ${result}`);
                    return ms;
                };
                jobs.push({id, family, variant, level, direction, bytes: raw.length, compressed,
                    run, rounds: 1, samples: []});
            };
            if (id === 'lz4-patched') {
                if (e.bench(0, src, raw.length, dst, raw.length, 1) !== raw.length) throw Error('memcpy');
                equal(bytes(dst, raw.length), raw, 'memcpy');
                add('memcpy', 'copy', 0, src, raw.length, dst, raw.length, raw.length, raw.length);
            }
            for (let index = 0; index < levels.length; ++index) {
                const {id: level, operation} = levels[index];
                const compressedPtr = compressedPtrs[index];
                const length = e.bench(operation, src, raw.length, compressedPtr, capacity, 1);
                if (length <= 0) throw Error('Compression failed: ' + id);
                const key = family + '/' + level;
                if (streams.has(key)) equal(bytes(compressedPtr, length), streams.get(key), key + ' stock/patched encoding');
                else streams.set(key, bytes(compressedPtr, length).slice());
                if (e.bench(3, compressedPtr, length, dst, raw.length, 1) !== raw.length) throw Error('Decode length: ' + id);
                equal(bytes(dst, raw.length), raw, id + ' ' + level + ' round trip');
                add(level, 'decompress', 3, compressedPtr, length, dst, raw.length, raw.length, length);
                add(level, 'compress', operation, src, raw.length, scratch, capacity, length, length);
            }
        }
        for (const job of jobs) {
            let perRoundMs = 0;
            for (let i = 0; i < 3; ++i) {
                const ms = job.run(job.rounds);
                perRoundMs = ms / job.rounds;
                job.rounds = Math.max(1, Math.ceil(25 / Math.max(0.01, perRoundMs)));
                await pause();
            }
            job.rounds = Math.max(1, Math.ceil(targetMs / Math.max(0.01, perRoundMs)));
        }
        for (let sample = 0; sample < sampleCount; ++sample) {
            // A coprime stride samples more positions with this larger set of operations.
            const start = (sample * 7) % jobs.length;
            let order = [...jobs.slice(start), ...jobs.slice(0, start)];
            if (sample % 2) order.reverse();
            for (const job of order) {
                const ms = job.run(job.rounds);
                job.samples.push({ms, rounds: job.rounds});
                await pause();
            }
        }
        for (const {run, ...job} of jobs) output.results.push({file: file.name, ...job});
        for (const {e, pointers} of allocations) for (const ptr of pointers) e.free(ptr);
        output.completedFiles++;
        await checkpoint(output);
        log('Verified and measured ' + file.name);
    }
    return output;
}
