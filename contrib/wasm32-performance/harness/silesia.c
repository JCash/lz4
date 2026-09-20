#include <string.h>
#include "lz4.h"
#include "lz4hc.h"

/* Keep each memcpy call visible to the optimizer in the timed batch. */
__attribute__((noinline)) static int
copy_once(const char* src, char* dst, int size)
{
    memcpy(dst, src, (size_t)size);
    return size;
}

int bound(int size)
{
    return LZ4_compressBound(size);
}

/* Operations: memcpy, default compression, HC9 compression, safe decode. */
int bench(int operation, const char* src, int size, char* dst, int capacity, int rounds)
{
    int i;
    int result = -1;
    for (i = 0; i < rounds; ++i) {
        switch (operation) {
        case 0:
            result = copy_once(src, dst, size);
            break;
        case 1:
            result = LZ4_compress_default(src, dst, size, capacity);
            break;
        case 2:
            result = LZ4_compress_HC(src, dst, size, capacity, 9);
            break;
        case 3:
            result = LZ4_decompress_safe(src, dst, size, capacity);
            break;
        default:
            return -1;
        }
        if (result <= 0) return -1;
    }
    return result;
}
