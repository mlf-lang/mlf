/* UTF-8 filesystem adapters for the native Win64 runtime. */
#ifndef MLF_WINDOWS_H
#define MLF_WINDOWS_H
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#define BOOLEAN MLF_WINDOWS_BOOLEAN
#define COMPARE_STRING MLF_WINDOWS_COMPARE_STRING
#include <windows.h>
#include <shellapi.h>
#undef BOOLEAN
#undef COMPARE_STRING
#include <io.h>
#include <fcntl.h>
#include <wchar.h>
#include "mlf_windows_path.h"

static wchar_t *mlf_wide(const char *text) {
    int n = MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,text,-1,NULL,0);
    if (!n) { errno = EINVAL; return NULL; }
    wchar_t *wide = malloc((size_t)n * sizeof(wchar_t));
    if (!wide) return NULL;
    if (!MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,text,-1,wide,n)) { free(wide); return NULL; }
    return wide;
}
static char *mlf_utf8(const wchar_t *wide) {
    int n = WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,wide,-1,NULL,0,NULL,NULL);
    if (!n) { errno = EINVAL; return NULL; }
    char *text = malloc((size_t)n);
    if (!text) return NULL;
    if (!WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,wide,-1,text,n,NULL,NULL)) { free(text); return NULL; }
    return text;
}
static FILE *mlf_windows_fopen(const char *path, const char *mode) {
    wchar_t *wide = mlf_wide(path), *p = wide ? mlf_windows_path(wide) : NULL, *m = mlf_wide(mode);
    FILE *result = p && m ? _wfopen(p,m) : NULL;
    free(wide); free(p); free(m); return result;
}
static char *mlf_windows_realpath(const char *path, char *unused) {
    (void)unused;
    wchar_t *p = mlf_wide(path);
    if (!p) return NULL;
    HANDLE file = CreateFileW(p,0,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,NULL,OPEN_EXISTING,FILE_FLAG_BACKUP_SEMANTICS,NULL);
    free(p);
    if (file == INVALID_HANDLE_VALUE) return NULL;
    DWORD n = GetFinalPathNameByHandleW(file,NULL,0,FILE_NAME_NORMALIZED|VOLUME_NAME_DOS);
    wchar_t *buffer = n ? malloc(((size_t)n+1)*sizeof(wchar_t)) : NULL;
    DWORD written = buffer ? GetFinalPathNameByHandleW(file,buffer,n+1,FILE_NAME_NORMALIZED|VOLUME_NAME_DOS) : 0;
    CloseHandle(file);
    if (!written || written > n) { free(buffer); return NULL; }
    char *result;
    if (!wcsncmp(buffer,L"\\\\?\\UNC\\",8)) {
        /* Keep UNC roots while dropping the extended-path prefix. */
        buffer[6] = L'\\'; result = mlf_utf8(buffer+6);
    } else result = mlf_utf8(!wcsncmp(buffer,L"\\\\?\\",4) ? buffer+4 : buffer);
    free(buffer);
    if (result) for (char *c=result; *c; ++c) if (*c=='\\') *c='/';
    return result;
}
static ssize_t mlf_windows_getline(char **line, size_t *capacity, FILE *stream) {
    size_t n = 0;
    int c;
    while ((c=fgetc(stream)) != EOF) {
        if (n+1 >= *capacity) {
            size_t next = *capacity ? *capacity*2 : 128;
            if (next <= n || next > (size_t)PTRDIFF_MAX) { errno=ENOMEM; return -1; }
            char *text = realloc(*line,next);
            if (!text) return -1;
            *line=text; *capacity=next;
        }
        (*line)[n++]=(char)c;
        if (c=='\n') break;
    }
    if (!n && c==EOF) return -1;
    (*line)[n]=0;
    return (ssize_t)n;
}
static DWORD mlf_windows_attributes(const char *path) {
    wchar_t *p=mlf_wide(path);
    DWORD result=p ? GetFileAttributesW(p) : INVALID_FILE_ATTRIBUTES;
    free(p); return result;
}
#define fopen mlf_windows_fopen
#define realpath mlf_windows_realpath
#define getline mlf_windows_getline
#endif
