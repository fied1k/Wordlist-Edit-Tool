#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>
#include <stdint.h>
#if defined(_WIN32)
#include <wchar.h>
#endif

#define FASTFILTER_VERSION "1.0.0"
#define BUF_SIZE (1024 * 1024 * 4) // 4 MB I/O streaming buffer

// 64-bit FNV-1a Hash (Case-insensitive)
static inline uint64_t hash_str_lower(const char *str, int len) {
    uint64_t hash = 14695981039346656037ULL;
    for (int i = 0; i < len; i++) {
        hash ^= (uint64_t)(unsigned char)tolower((unsigned char)str[i]);
        hash *= 1099511628211ULL;
    }
    return hash == 0 ? 1 : hash; // 0 is reserved for empty slot
}

// Dynamic Open-Addressing Hash Set for 64-bit hashes
typedef struct {
    uint64_t *table;
    size_t capacity;
    size_t count;
} HashSet;

static HashSet* hashset_create(size_t initial_cap) {
    HashSet *set = (HashSet*)malloc(sizeof(HashSet));
    if (!set) return NULL;
    set->capacity = initial_cap;
    set->count = 0;
    set->table = (uint64_t*)calloc(set->capacity, sizeof(uint64_t));
    if (!set->table) {
        free(set);
        return NULL;
    }
    return set;
}

static void hashset_free(HashSet *set) {
    if (set) {
        free(set->table);
        free(set);
    }
}

static void hashset_resize(HashSet *set) {
    size_t old_cap = set->capacity;
    uint64_t *old_table = set->table;

    set->capacity *= 2;
    set->table = (uint64_t*)calloc(set->capacity, sizeof(uint64_t));
    if (!set->table) {
        // Fallback: restore old table if out of memory
        set->capacity = old_cap;
        set->table = old_table;
        return;
    }
    set->count = 0;

    for (size_t i = 0; i < old_cap; i++) {
        if (old_table[i] != 0) {
            uint64_t h = old_table[i];
            size_t idx = h & (set->capacity - 1);
            while (set->table[idx] != 0) {
                idx = (idx + 1) & (set->capacity - 1);
            }
            set->table[idx] = h;
            set->count++;
        }
    }
    free(old_table);
}

static int hashset_contains_or_add(HashSet *set, uint64_t h) {
    if (!set) return 0;
    if (set->count * 2 >= set->capacity) {
        hashset_resize(set);
    }
    size_t idx = h & (set->capacity - 1);
    while (set->table[idx] != 0) {
        if (set->table[idx] == h) return 1; // already present
        idx = (idx + 1) & (set->capacity - 1);
    }
    set->table[idx] = h;
    set->count++;
    return 0; // newly added
}

// Token delimiter helper: words consist of alphanumeric characters, hyphens, apostrophes, and underscores
static inline int is_token_char(unsigned char c) {
    return isalnum(c) || c == '-' || c == '\'' || c == '_';
}

// Core processing loop
static long long process_file_internal(
    FILE *src,
    FILE *dst,
    int min_len,
    int max_len,
    int charset_mode, // 0 = all, 1 = letters only, 2 = alphanumeric only
    int output_mode,  // 0 = list, 1 = preserve lines
    int dedup
) {
    char *in_buf = (char*)malloc(BUF_SIZE);
    char *out_buf = (char*)malloc(BUF_SIZE);
    if (in_buf) setvbuf(src, in_buf, _IOFBF, BUF_SIZE);
    if (out_buf) setvbuf(dst, out_buf, _IOFBF, BUF_SIZE);

    HashSet *set = dedup ? hashset_create(1048576) : NULL; // 1M slots initial (~8MB RAM)
    long long total_kept = 0;

    char line[65536];
    char word[4096];

    while (fgets(line, sizeof(line), src)) {
        char *ptr = line;
        int first_in_line = 1;

        while (*ptr) {
            // Skip non-token delimiters (whitespace, punctuation, symbols)
            while (*ptr && !is_token_char((unsigned char)*ptr)) {
                ptr++;
            }
            if (!*ptr) break;

            // Extract token
            int w_len = 0;
            while (*ptr && is_token_char((unsigned char)*ptr) && w_len < (int)sizeof(word) - 1) {
                word[w_len++] = *ptr++;
            }
            word[w_len] = '\0';

            // Trim leading/trailing hyphens, quotes, underscores
            int start = 0;
            while (start < w_len && (word[start] == '\'' || word[start] == '-' || word[start] == '_')) {
                start++;
            }
            int end = w_len - 1;
            while (end >= start && (word[end] == '\'' || word[end] == '-' || word[end] == '_')) {
                end--;
            }

            int clean_len = (end >= start) ? (end - start + 1) : 0;
            if (clean_len < min_len || clean_len > max_len) {
                continue;
            }

            word[start + clean_len] = '\0';
            char *clean_word = word + start;

            // Validate character set rules on clean token
            if (charset_mode == 1) { // letters only
                int valid = 1;
                for (int i = 0; i < clean_len; i++) {
                    if (!isalpha((unsigned char)clean_word[i])) {
                        valid = 0;
                        break;
                    }
                }
                if (!valid) continue;
            } else if (charset_mode == 2) { // alphanumeric only
                int valid = 1;
                for (int i = 0; i < clean_len; i++) {
                    if (!isalnum((unsigned char)clean_word[i])) {
                        valid = 0;
                        break;
                    }
                }
                if (!valid) continue;
            }

            // Deduplication check
            if (dedup && set) {
                uint64_t h = hash_str_lower(clean_word, clean_len);
                if (hashset_contains_or_add(set, h)) {
                    continue;
                }
            }

            // Write output
            if (output_mode == 0) { // list mode (1 word per line)
                fputs(clean_word, dst);
                fputc('\n', dst);
            } else { // preserve lines mode
                if (!first_in_line) fputc(' ', dst);
                fputs(clean_word, dst);
                first_in_line = 0;
            }
            total_kept++;
        }

        if (output_mode == 1 && !first_in_line) {
            fputc('\n', dst);
        }
    }

    if (dst) fflush(dst);
    if (in_buf) free(in_buf);
    if (out_buf) free(out_buf);
    if (set) hashset_free(set);

    return total_kept;
}

// Exported function (ANSI/UTF-8 path)
#if defined(_WIN32)
__declspec(dllexport)
#endif
long long process_file_fast(
    const char *src_path,
    const char *dst_path,
    int min_len,
    int max_len,
    int charset_mode,
    int output_mode,
    int dedup
) {
    FILE *src = fopen(src_path, "rb");
    if (!src) return -1;

    FILE *dst = fopen(dst_path, "wb");
    if (!dst) {
        fclose(src);
        return -2;
    }

    long long result = process_file_internal(src, dst, min_len, max_len, charset_mode, output_mode, dedup);
    fclose(src);
    fclose(dst);
    return result;
}

// Exported wide-character function for Windows Unicode file paths
#if defined(_WIN32)
__declspec(dllexport)
long long process_file_fast_w(
    const wchar_t *src_path,
    const wchar_t *dst_path,
    int min_len,
    int max_len,
    int charset_mode,
    int output_mode,
    int dedup
) {
    FILE *src = _wfopen(src_path, L"rb");
    if (!src) return -1;

    FILE *dst = _wfopen(dst_path, L"wb");
    if (!dst) {
        fclose(src);
        return -2;
    }

    long long result = process_file_internal(src, dst, min_len, max_len, charset_mode, output_mode, dedup);
    fclose(src);
    fclose(dst);
    return result;
}
#endif

// Standalone CLI interface when compiled with -DBUILD_CLI
#ifdef BUILD_CLI
int main(int argc, char **argv) {
    if (argc >= 2 && (strcmp(argv[1], "-v") == 0 || strcmp(argv[1], "--version") == 0)) {
        printf("fastfilter v%s\n", FASTFILTER_VERSION);
        return 0;
    }

    if (argc < 3) {
        printf("WordLengthFilter CLI v%s (Fast Native Engine)\n", FASTFILTER_VERSION);
        printf("Usage: fastfilter.exe <source_file> <output_file> [min_len] [max_len] [charset_mode] [output_mode] [dedup]\n\n");
        printf("Arguments:\n");
        printf("  <source_file>   Path to source text / wordlist file\n");
        printf("  <output_file>   Path to destination output file\n");
        printf("  [min_len]       Minimum length (default: 3)\n");
        printf("  [max_len]       Maximum length (default: 12)\n");
        printf("  [charset_mode]  0 = all words, 1 = letters only, 2 = alphanumeric only (default: 0)\n");
        printf("  [output_mode]   0 = one word per line, 1 = preserve lines (default: 0)\n");
        printf("  [dedup]         0 = keep duplicates, 1 = unique words only (default: 0)\n");
        return 1;
    }

    const char *src = argv[1];
    const char *dst = argv[2];
    int min_len = argc > 3 ? atoi(argv[3]) : 3;
    int max_len = argc > 4 ? atoi(argv[4]) : 12;
    int charset_mode = argc > 5 ? atoi(argv[5]) : 0;
    int output_mode = argc > 6 ? atoi(argv[6]) : 0;
    int dedup = argc > 7 ? atoi(argv[7]) : 0;

    printf("[WordLengthFilter] Processing '%s' -> '%s'...\n", src, dst);
    printf("Settings: min=%d, max=%d, charset=%d, mode=%d, dedup=%d\n",
           min_len, max_len, charset_mode, output_mode, dedup);

    long long kept = process_file_fast(src, dst, min_len, max_len, charset_mode, output_mode, dedup);
    if (kept == -1) {
        fprintf(stderr, "[ERROR] Could not open source file: %s\n", src);
        return 2;
    } else if (kept == -2) {
        fprintf(stderr, "[ERROR] Could not create destination file: %s\n", dst);
        return 3;
    }

    printf("[SUCCESS] Completed! Retained %lld words.\n", kept);
    return 0;
}
#endif