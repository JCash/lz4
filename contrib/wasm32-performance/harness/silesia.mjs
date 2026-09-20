const pause = () => new Promise(resolve => setTimeout(resolve, 0));

function equal(actual, expected, label) {
    if (actual.length !== expected.length) throw Error(label + ': length');
    for (let i = 0; i < actual.length; ++i) {
        if (actual[i] !== expected[i]) throw Error(label + ': byte ' + i);
    }
}

export async function benchmark({sampleCount = 7, targetMs = 100}, read, log) {
    const corpus = JSON.parse(new TextDecoder().decode(await read('results/silesia-corpus.json')));
    const build = JSON.parse(new TextDecoder().decode(await read('results/silesia-build.json')));
    const output = {sampleCount, targetMs, corpus, build, results: []};
    const modules = [];
    for (const variant of ['stock', 'patched']) {
        const {instance} = await WebAssembly.instantiate(await read(`local/build/silesia-${variant}.wasm`), {
            wasi_snapshot_preview1: {proc_exit: n => { throw Error('Wasm exit ' + n); }},
        });
        instance.exports._initialize?.();
        modules.push({variant, e: instance.exports});
    }
    for (const file of corpus.files) {
        log('Starting ' + file.name);
        const raw = await read('local/silesia/' + file.name);
        const sha256 = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', raw)),
            byte => byte.toString(16).padStart(2, '0')).join('');
        if (sha256 !== file.sha256) throw Error('Input hash: ' + file.name);
        const jobs = [];
        const allocations = [];
        const streams = new Map();
        for (const {variant, e} of modules) {
            const capacity = e.bound(raw.length);
            const sizes = [raw.length, raw.length, capacity, capacity, capacity];
            const pointers = sizes.map(size => {
                const ptr = e.malloc(size);
                if (!ptr) throw Error('Allocation failed');
                return ptr;
            });
            const [src, dst, scratch, fast, hc] = pointers;
            allocations.push({e, pointers});
            const bytes = (ptr, size) => new Uint8Array(e.memory.buffer, ptr, size);
            bytes(src, raw.length).set(raw);
            if (e.bench(0, src, raw.length, dst, raw.length, 1) !== raw.length) throw Error('memcpy');
            equal(bytes(dst, raw.length), raw, variant + ' memcpy');
            const add = (codec, direction, operation, input, size, destination, limit, expected) => {
                const run = rounds => {
                    const start = performance.now();
                    const result = e.bench(operation, input, size, destination, limit, rounds);
                    const ms = performance.now() - start;
                    if (result !== expected) throw Error(`${variant} ${codec} ${direction}: ${result}`);
                    return ms;
                };
                jobs.push({variant, codec, direction, bytes: raw.length, compressed: expected,
                    run, rounds: 1, samples: []});
            };
            if (variant === 'patched') add('memcpy', 'copy', 0, src, raw.length, dst, raw.length, raw.length);
            for (const [codec, operation, compressedPtr] of [['default', 1, fast], ['hc9', 2, hc]]) {
                const length = e.bench(operation, src, raw.length, compressedPtr, capacity, 1);
                if (length <= 0) throw Error('Compression failed');
                if (streams.has(codec)) equal(bytes(compressedPtr, length), streams.get(codec), codec + ' stock/patched encoding');
                else streams.set(codec, bytes(compressedPtr, length).slice());
                if (e.bench(3, compressedPtr, length, dst, raw.length, 1) !== raw.length) throw Error('Decode length');
                equal(bytes(dst, raw.length), raw, variant + ' ' + codec + ' round trip');
                add(codec, 'decompress', 3, compressedPtr, length, dst, raw.length, raw.length);
                jobs.at(-1).compressed = length;
                if (variant === 'patched') add(codec, 'compress', operation, src, raw.length, scratch, capacity, length);
            }
        }
        for (const job of jobs) {
            let perRoundMs = 0;
            for (let i = 0; i < 3; ++i) {
                const ms = job.run(job.rounds);
                perRoundMs = ms / job.rounds;
                job.rounds = Math.max(1, Math.ceil(job.rounds * 25 / Math.max(0.01, ms)));
                await pause();
            }
            job.rounds = Math.max(1, Math.ceil(targetMs / Math.max(0.01, perRoundMs)));
        }
        // Rotate and reverse order so neither decoder always follows a cold cache.
        for (let sample = 0; sample < sampleCount; ++sample) {
            let order = [...jobs.slice(sample % jobs.length), ...jobs.slice(0, sample % jobs.length)];
            if (sample % 2) order.reverse();
            for (const job of order) {
                const ms = job.run(job.rounds);
                job.samples.push({ms, rounds: job.rounds});
                await pause();
            }
        }
        for (const {run, ...job} of jobs) output.results.push({file: file.name, ...job});
        for (const {e, pointers} of allocations) for (const ptr of pointers) e.free(ptr);
        log('Verified and measured ' + file.name);
    }
    return output;
}
