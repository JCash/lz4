#include <stddef.h>
#if CODEC == 2
#include "zstd.h"
#elif CODEC == 3
#include "zlib.h"
#endif

int bound(int size)
{
#if CODEC == 2
    return (int)ZSTD_compressBound((size_t)size);
#else
    return (int)compressBound((uLong)size);
#endif
}

/* The same batch ABI as silesia.c. Operation 3 always means decompression. */
int bench(int operation, const void* src, int size, void* dst, int capacity, int rounds)
{
    int i;
    int result = -1;
    for (i = 0; i < rounds; ++i) {
#if CODEC == 2
        size_t n;
        if (operation == 3) {
            n = ZSTD_decompress(dst, (size_t)capacity, src, (size_t)size);
        } else {
            int level = operation == 1 ? 1 : operation == 2 ? 3 : 6;
            n = ZSTD_compress(dst, (size_t)capacity, src, (size_t)size, level);
        }
        if (ZSTD_isError(n)) return -1;
        result = (int)n;
#else
        uLongf n = (uLongf)capacity;
        int error;
        if (operation == 3) {
            error = uncompress((Bytef*)dst, &n, (const Bytef*)src, (uLong)size);
        } else {
            int level = operation == 1 ? 1 : 6;
            error = compress2((Bytef*)dst, &n, (const Bytef*)src, (uLong)size, level);
        }
        if (error != Z_OK) return -1;
        result = (int)n;
#endif
        if (result <= 0) return -1;
    }
    return result;
}
