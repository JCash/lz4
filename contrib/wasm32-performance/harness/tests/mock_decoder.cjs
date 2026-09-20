/* Controlled decoder faults for testing the validator's process exit status. */
WebAssembly.instantiate = async function(binary) {
    const fault = binary[0];
    const memory = {buffer: new ArrayBuffer(8 * 1024 * 1024)};
    let next = 1024;
    return {instance: {exports: {
        memory,
        setup() {},
        malloc(size) {
            const ptr = next;
            next += size + 16;
            return ptr;
        },
        free() {},
        decode(src, size, dst, capacity) {
            const bytes = new Uint8Array(memory.buffer);
            if (size === 2 && bytes[src] === 0x10 && capacity >= 1) {
                const literal = bytes[src + 1];
                // Keep the original valid fixture correct; corrupt mutated literals only.
                bytes[dst] = fault === 2 && literal !== 0x5a ? literal ^ 1 : literal;
                return 1;
            }
            if (fault === 1) return 0;  // Accept malformed input instead of rejecting it.
            if (fault === 3) return -2; // Reject it at a different reported error offset.
            return -1;
        },
    }}};
};
