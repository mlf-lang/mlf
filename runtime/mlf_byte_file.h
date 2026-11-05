/* Shared raw-byte transport, no language values or UTF-8 content conversion.
 * Included after each host's UTF-8 filename fopen adapter. Caller owns output.
 * Empty diagnostic is success. Failures discard partial reads. */
#ifndef MLF_BYTE_FILE_H
#define MLF_BYTE_FILE_H
static const char *mlf_byte_file_read(const char *path, size_t path_length,
                                    int64_t limit, unsigned char **output, size_t *length) {
    *output = NULL; *length = 0;
    if (memchr(path, 0, path_length)) return "file path contains NUL";
    if (limit < 0 || (uint64_t)limit > INT64_MAX / 8 || (uint64_t)limit > SIZE_MAX)
        return "invalid byte file limit";
    FILE *file = fopen(path, "rb");
    if (!file) return "IO error: byte file read failed";
    size_t cap = (uint64_t)limit < 4096 ? (size_t)limit : 4096, used = 0;
    unsigned char *buffer = malloc(cap ? cap : 1);
    const char *error = "";
    if (!buffer) { fclose(file); return "out of memory"; }
    for (;;) {
        if (used == cap) {
            int next = fgetc(file);
            if (next == EOF) { if (ferror(file)) error = "IO error: byte file read failed"; break; }
            if (used == (size_t)limit) { error = "byte file exceeds limit"; break; }
            size_t remaining = (size_t)limit - cap;
            size_t growth = cap ? cap : 1;
            if (growth > remaining) growth = remaining;
            unsigned char *larger = realloc(buffer, cap + growth);
            if (!larger) { error = "out of memory"; break; }
            buffer = larger; cap += growth; buffer[used++] = (unsigned char)next;
        }
        size_t n = fread(buffer + used, 1, cap - used, file);
        used += n;
        if (ferror(file)) { error = "IO error: byte file read failed"; break; }
        if (feof(file)) break;
    }
    if (fclose(file) && !*error) error = "IO error: byte file read failed";
    if (*error) { free(buffer); return error; }
    *output = buffer; *length = used; return "";
}
static const char *mlf_byte_file_write(const char *path, size_t path_length,
                                     const unsigned char *bytes, size_t length) {
    if (memchr(path, 0, path_length)) return "file path contains NUL";
    FILE *file = fopen(path, "wb");
    if (!file) return "IO error: byte file write failed";
    int failed = fwrite(bytes, 1, length, file) != length;
    if (fclose(file)) failed = 1;
    return failed ? "IO error: byte file write failed" : "";
}
#endif
