
#include <stdlib.h>
#include <stdint.h>
#if CODEC == 1
#include "lz4.h"
#elif CODEC == 2
#include "zstd.h"
static ZSTD_DCtx* ctx;
#endif
void setup(void) {
#if CODEC == 2
    ctx = ZSTD_createDCtx();
#endif
}
int decode(const void* src, int size, void* dst, int capacity) {
#if CODEC == 1
    return LZ4_decompress_safe(src, dst, size, capacity);
#elif CODEC == 2
    size_t n = ZSTD_decompressDCtx(ctx, dst, capacity, src, size);
    return ZSTD_isError(n) ? -1 : (int)n;
#else
    return size;
#endif
}
#if BENCH
struct Item { const void* src; int size; void* dst; int capacity; };
int batch(struct Item* items, int count, int rounds) {
    unsigned sum = 0;
    for (int r = 0; r < rounds; ++r) {
        for (int i = 0; i < count; ++i) {
            struct Item* item = items + i;
            int n = decode(item->src, item->size, item->dst, item->capacity);
            if (n != item->capacity) return -1;
            sum += n;
        }
    }
    return (int)(sum & 0x7fffffff);
}
#endif
