#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>
#include <stdint.h>
#if defined(_WIN32)
#include <wchar.h>
#endif

#define FASTFILTER_VERSION "1.2.0"
#define BUF_SIZE (1024 * 1024 * 4) // 4 MB I/O streaming buffer

// 64-bit FNV-1a Hash (Case-insensitive for standard words)
static inline uint64_t hash_str_lower(const char *str, int len) {
    uint64_t hash = 14695981039346656037ULL;
    for (int i = 0; i < len; i++) {
        hash ^= (uint64_t)(unsigned char)tolower((unsigned char)str[i]);
        hash *= 1099511628211ULL;
    }
    return hash == 0 ? 1 : hash; // 0 is reserved for empty slot
}

// 64-bit FNV-1a Hash (Exact case-sensitive for WPA2 keys/passwords)
static inline uint64_t hash_str_exact(const char *str, int len) {
    uint64_t hash = 14695981039346656037ULL;
    for (int i = 0; i < len; i++) {
        hash ^= (uint64_t)(unsigned char)str[i];
        hash *= 1099511628211ULL;
    }
    return hash == 0 ? 1 : hash;
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

// Token delimiter helpers
static inline int is_token_char(unsigned char c) {
    return isalnum(c) || c == '-' || c == '\'' || c == '_';
}

static inline int is_whitespace(unsigned char c) {
    return c == ' ' || c == '\t' || c == '\r' || c == '\n';
}

// Helper to split a path into base and extension
static void get_base_and_ext_a(const char *path, char *base, size_t base_sz, char *ext, size_t ext_sz) {
    const char *last_sep = strrchr(path, '\\');
    const char *last_fwd = strrchr(path, '/');
    if (last_fwd && (!last_sep || last_fwd > last_sep)) {
        last_sep = last_fwd;
    }
    const char *fname = last_sep ? last_sep + 1 : path;
    const char *dot = strrchr(fname, '.');
    if (dot) {
        size_t base_len = dot - path;
        if (base_len >= base_sz) base_len = base_sz - 1;
        strncpy(base, path, base_len);
        base[base_len] = '\0';
        strncpy(ext, dot, ext_sz - 1);
        ext[ext_sz - 1] = '\0';
    } else {
        strncpy(base, path, base_sz - 1);
        base[base_sz - 1] = '\0';
        ext[0] = '\0';
    }
}

#if defined(_WIN32)
static void get_base_and_ext_w(const wchar_t *path, wchar_t *base, size_t base_sz, wchar_t *ext, size_t ext_sz) {
    const wchar_t *last_sep = wcsrchr(path, L'\\');
    const wchar_t *last_fwd = wcsrchr(path, L'/');
    if (last_fwd && (!last_sep || last_fwd > last_sep)) {
        last_sep = last_fwd;
    }
    const wchar_t *fname = last_sep ? last_sep + 1 : path;
    const wchar_t *dot = wcsrchr(fname, L'.');
    if (dot) {
        size_t base_len = dot - path;
        if (base_len >= base_sz) base_len = base_sz - 1;
        wcsncpy(base, path, base_len);
        base[base_len] = L'\0';
        wcsncpy(ext, dot, ext_sz - 1);
        ext[ext_sz - 1] = L'\0';
    } else {
        wcsncpy(base, path, base_sz - 1);
        base[base_sz - 1] = L'\0';
        ext[0] = L'\0';
    }
}
#endif

// Output Writer with on-the-fly chunk rollover support
typedef struct {
    int is_wide;
    char base_a[4096];
    char ext_a[256];
#if defined(_WIN32)
    wchar_t base_w[4096];
    wchar_t ext_w[256];
#endif
    int part_num;
    long long split_lines;
    long long split_bytes;
    long long current_part_lines;
    long long current_part_bytes;
    FILE *dst;
    char *out_buf;
} OutputWriter;

static int writer_open_next_part(OutputWriter *w) {
    if (w->dst) {
        fflush(w->dst);
        fclose(w->dst);
        w->dst = NULL;
    }
    w->part_num++;
    w->current_part_lines = 0;
    w->current_part_bytes = 0;

    int is_split = (w->split_lines > 0 || w->split_bytes > 0);

#if defined(_WIN32)
    if (w->is_wide) {
        wchar_t part_path_w[4096];
        if (is_split) {
            swprintf(part_path_w, sizeof(part_path_w)/sizeof(wchar_t), L"%ls_part%d%ls", w->base_w, w->part_num, w->ext_w);
        } else {
            swprintf(part_path_w, sizeof(part_path_w)/sizeof(wchar_t), L"%ls%ls", w->base_w, w->ext_w);
        }
        w->dst = _wfopen(part_path_w, L"wb");
    } else
#endif
    {
        char part_path_a[4096];
        if (is_split) {
            snprintf(part_path_a, sizeof(part_path_a), "%s_part%d%s", w->base_a, w->part_num, w->ext_a);
        } else {
            snprintf(part_path_a, sizeof(part_path_a), "%s%s", w->base_a, w->ext_a);
        }
        w->dst = fopen(part_path_a, "wb");
    }

    if (!w->dst) return -1;
    if (w->out_buf) {
        setvbuf(w->dst, w->out_buf, _IOFBF, BUF_SIZE);
    }
    return 0;
}

static inline void writer_check_rollover(OutputWriter *w) {
    if ((w->split_lines > 0 && w->current_part_lines >= w->split_lines) ||
        (w->split_bytes > 0 && w->current_part_bytes >= w->split_bytes)) {
        writer_open_next_part(w);
    }
}

// Core processing loop
static long long process_file_internal(
    FILE *src,
    OutputWriter *writer,
    int min_len,
    int max_len,
    int charset_mode, // 0 = all, 1 = letters only, 2 = alphanumeric only, 3 = ASCII printable (32-126)
    int output_mode,  // 0 = list, 1 = preserve lines
    int dedup
) {
    char *in_buf = (char*)malloc(BUF_SIZE);
    if (in_buf) setvbuf(src, in_buf, _IOFBF, BUF_SIZE);

    writer->out_buf = (char*)malloc(BUF_SIZE);
    if (writer_open_next_part(writer) != 0) {
        if (in_buf) free(in_buf);
        if (writer->out_buf) free(writer->out_buf);
        return -2;
    }

    HashSet *set = dedup ? hashset_create(1048576) : NULL; // 1M slots initial (~8MB RAM)
    long long total_kept = 0;

    char line[65536];
    char word[4096];

    while (fgets(line, sizeof(line), src)) {
        char *ptr = line;
        int first_in_line = 1;

        if (output_mode == 1) {
            writer_check_rollover(writer);
        }

        if (charset_mode == 3) {
            // Mode 3: ASCII Printable (32-126) for WPA2 Wi-Fi Passphrases
            // Words/keys are whitespace-separated tokens; symbols and punctuation are preserved.
            while (*ptr) {
                while (*ptr && is_whitespace((unsigned char)*ptr)) {
                    ptr++;
                }
                if (!*ptr) break;

                int w_len = 0;
                int is_ascii = 1;
                while (*ptr && !is_whitespace((unsigned char)*ptr) && w_len < (int)sizeof(word) - 1) {
                    unsigned char c = (unsigned char)*ptr++;
                    if (c < 32 || c > 126) {
                        is_ascii = 0;
                    }
                    word[w_len++] = c;
                }
                word[w_len] = '\0';

                if (!is_ascii) continue; // Must be strictly ASCII printable
                if (w_len < min_len || w_len > max_len) continue;

                // Deduplication (exact case-sensitive for WPA2 passphrases)
                if (dedup && set) {
                    uint64_t h = hash_str_exact(word, w_len);
                    if (hashset_contains_or_add(set, h)) {
                        continue;
                    }
                }

                if (output_mode == 0) {
                    writer_check_rollover(writer);
                    fputs(word, writer->dst);
                    fputc('\n', writer->dst);
                    writer->current_part_lines++;
                    writer->current_part_bytes += w_len + 1;
                } else {
                    if (!first_in_line) {
                        fputc(' ', writer->dst);
                        writer->current_part_bytes++;
                    }
                    fputs(word, writer->dst);
                    writer->current_part_bytes += w_len;
                    first_in_line = 0;
                }
                total_kept++;
            }
        } else {
            // Standard word modes: 0 = all, 1 = letters only, 2 = alphanumeric only
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
                    writer_check_rollover(writer);
                    fputs(clean_word, writer->dst);
                    fputc('\n', writer->dst);
                    writer->current_part_lines++;
                    writer->current_part_bytes += clean_len + 1;
                } else { // preserve lines mode
                    if (!first_in_line) {
                        fputc(' ', writer->dst);
                        writer->current_part_bytes++;
                    }
                    fputs(clean_word, writer->dst);
                    writer->current_part_bytes += clean_len;
                    first_in_line = 0;
                }
                total_kept++;
            }
        }

        if (output_mode == 1 && !first_in_line) {
            fputc('\n', writer->dst);
            writer->current_part_lines++;
            writer->current_part_bytes++;
        }
    }

    if (writer->dst) {
        fflush(writer->dst);
        fclose(writer->dst);
        writer->dst = NULL;
    }
    if (writer->out_buf) {
        free(writer->out_buf);
        writer->out_buf = NULL;
    }
    if (in_buf) free(in_buf);
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
    int dedup,
    long long split_lines,
    long long split_bytes
) {
    FILE *src = fopen(src_path, "rb");
    if (!src) return -1;

    OutputWriter writer;
    memset(&writer, 0, sizeof(writer));
    writer.is_wide = 0;
    get_base_and_ext_a(dst_path, writer.base_a, sizeof(writer.base_a), writer.ext_a, sizeof(writer.ext_a));
    writer.split_lines = split_lines;
    writer.split_bytes = split_bytes;

    long long result = process_file_internal(src, &writer, min_len, max_len, charset_mode, output_mode, dedup);
    fclose(src);
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
    int dedup,
    long long split_lines,
    long long split_bytes
) {
    FILE *src = _wfopen(src_path, L"rb");
    if (!src) return -1;

    OutputWriter writer;
    memset(&writer, 0, sizeof(writer));
    writer.is_wide = 1;
    get_base_and_ext_w(dst_path, writer.base_w, sizeof(writer.base_w)/sizeof(wchar_t), writer.ext_w, sizeof(writer.ext_w)/sizeof(wchar_t));
    writer.split_lines = split_lines;
    writer.split_bytes = split_bytes;

    long long result = process_file_internal(src, &writer, min_len, max_len, charset_mode, output_mode, dedup);
    fclose(src);
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
        printf("Usage: fastfilter.exe <source_file> <output_file> [min_len] [max_len] [charset_mode] [output_mode] [dedup] [split_lines] [split_bytes]\n\n");
        printf("Arguments:\n");
        printf("  <source_file>   Path to source text / wordlist file\n");
        printf("  <output_file>   Path to destination output file\n");
        printf("  [min_len]       Minimum length (default: 3)\n");
        printf("  [max_len]       Maximum length (default: 12)\n");
        printf("  [charset_mode]  0 = all words (default)\n");
        printf("                  1 = letters only\n");
        printf("                  2 = alphanumeric only\n");
        printf("                  3 = ASCII printable only (32-126, WPA2 standard)\n");
        printf("  [output_mode]   0 = one word per line (default), 1 = preserve lines\n");
        printf("  [dedup]         0 = keep duplicates (default), 1 = unique words only\n");
        printf("  [split_lines]   Max lines/words per file chunk (default: 0 = disabled)\n");
        printf("  [split_bytes]   Max bytes per file chunk (e.g. 1073741824 = 1GB, default: 0 = disabled)\n");
        return 1;
    }

    const char *src = argv[1];
    const char *dst = argv[2];
    int min_len = argc > 3 ? atoi(argv[3]) : 3;
    int max_len = argc > 4 ? atoi(argv[4]) : 12;
    int charset_mode = argc > 5 ? atoi(argv[5]) : 0;
    int output_mode = argc > 6 ? atoi(argv[6]) : 0;
    int dedup = argc > 7 ? atoi(argv[7]) : 0;
    long long split_lines = argc > 8 ? atoll(argv[8]) : 0;
    long long split_bytes = argc > 9 ? atoll(argv[9]) : 0;

    printf("[WordLengthFilter] Processing '%s' -> '%s'...\n", src, dst);
    printf("Settings: min=%d, max=%d, charset=%d, mode=%d, dedup=%d, split_lines=%lld, split_bytes=%lld\n",
           min_len, max_len, charset_mode, output_mode, dedup, split_lines, split_bytes);

    long long kept = process_file_fast(src, dst, min_len, max_len, charset_mode, output_mode, dedup, split_lines, split_bytes);
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