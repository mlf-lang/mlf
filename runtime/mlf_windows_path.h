/* Win32 filesystem boundary: deep content-addressed caches must not depend on
 * the machine's LongPathsEnabled registry setting or an executable manifest.
 * Keep logical paths outside this boundary, especially relative link targets. */
#ifndef MLF_WINDOWS_PATH_H
#define MLF_WINDOWS_PATH_H
#include <stdlib.h>
#include <string.h>
#include <wchar.h>

static inline wchar_t *mlf_windows_path_copy(const wchar_t *path) {
    wchar_t *copy=_wcsdup(path);
    if (!copy) SetLastError(ERROR_NOT_ENOUGH_MEMORY);
    return copy;
}
static inline wchar_t *mlf_windows_path(const wchar_t *path) {
    /* Preserve empty paths and explicit device/extended namespaces. */
    if (!*path || !wcsncmp(path,L"\\\\?\\",4) || !wcsncmp(path,L"\\\\.\\",4))
        return mlf_windows_path_copy(path);
    DWORD size=GetFullPathNameW(path,0,NULL,NULL);
    if (!size) return NULL;
    wchar_t *full=malloc((size_t)size*sizeof(wchar_t));
    if (!full) { SetLastError(ERROR_NOT_ENOUGH_MEMORY); return NULL; }
    DWORD length=GetFullPathNameW(path,size,full,NULL);
    if (!length || length>=size) {
        DWORD error=length ? ERROR_INSUFFICIENT_BUFFER : GetLastError();
        free(full); SetLastError(error); return NULL;
    }
    /* Directory creation has a stricter MAX_PATH - 12 limit. Short paths keep
     * ordinary Win32 behavior, including reserved names such as NUL. */
    if (length<MAX_PATH-12) { free(full); return mlf_windows_path_copy(path); }
    for (wchar_t *c=full; *c; ++c) if (*c==L'/') *c=L'\\';
    int unc=full[0]==L'\\' && full[1]==L'\\';
    size_t prefix=unc ? 8 : 4, skip=unc ? 2 : 0;
    wchar_t *result=malloc((prefix+length-skip+1)*sizeof(wchar_t));
    if (!result) { free(full); SetLastError(ERROR_NOT_ENOUGH_MEMORY); return NULL; }
    memcpy(result,unc ? L"\\\\?\\UNC\\" : L"\\\\?\\",prefix*sizeof(wchar_t));
    memcpy(result+prefix,full+skip,(length-skip+1)*sizeof(wchar_t));
    free(full); return result;
}

/* Define adapters before the API aliases, so each calls the real Win32 API.
 * Preserve its last-error value across temporary path cleanup. */
static inline DWORD mlf_path_GetFileAttributesW(LPCWSTR path) {
    wchar_t *p=mlf_windows_path(path);
    DWORD result=p ? GetFileAttributesW(p) : INVALID_FILE_ATTRIBUTES, error=GetLastError();
    free(p); SetLastError(error); return result;
}
static inline BOOL mlf_path_SetFileAttributesW(LPCWSTR path, DWORD attributes) {
    wchar_t *p=mlf_windows_path(path);
    BOOL result=p && SetFileAttributesW(p,attributes); DWORD error=GetLastError();
    free(p); SetLastError(error); return result;
}
static inline BOOL mlf_path_CreateDirectoryW(LPCWSTR path, LPSECURITY_ATTRIBUTES security) {
    wchar_t *p=mlf_windows_path(path);
    BOOL result=p && CreateDirectoryW(p,security); DWORD error=GetLastError();
    free(p); SetLastError(error); return result;
}
static inline BOOL mlf_path_RemoveDirectoryW(LPCWSTR path) {
    wchar_t *p=mlf_windows_path(path);
    BOOL result=p && RemoveDirectoryW(p); DWORD error=GetLastError();
    free(p); SetLastError(error); return result;
}
static inline BOOL mlf_path_DeleteFileW(LPCWSTR path) {
    wchar_t *p=mlf_windows_path(path);
    BOOL result=p && DeleteFileW(p); DWORD error=GetLastError();
    free(p); SetLastError(error); return result;
}
static inline BOOL mlf_path_CopyFileW(LPCWSTR from, LPCWSTR to, BOOL exclusive) {
    wchar_t *a=mlf_windows_path(from), *b=a ? mlf_windows_path(to) : NULL;
    BOOL result=a && b && CopyFileW(a,b,exclusive); DWORD error=GetLastError();
    free(a); free(b); SetLastError(error); return result;
}
static inline BOOL mlf_path_MoveFileExW(LPCWSTR from, LPCWSTR to, DWORD flags) {
    wchar_t *a=mlf_windows_path(from), *b=a ? mlf_windows_path(to) : NULL;
    BOOL result=a && b && MoveFileExW(a,b,flags); DWORD error=GetLastError();
    free(a); free(b); SetLastError(error); return result;
}
static inline HANDLE mlf_path_FindFirstFileW(LPCWSTR path, LPWIN32_FIND_DATAW entry) {
    wchar_t *p=mlf_windows_path(path);
    HANDLE result=p ? FindFirstFileW(p,entry) : INVALID_HANDLE_VALUE; DWORD error=GetLastError();
    free(p); SetLastError(error); return result;
}
static inline HANDLE mlf_path_CreateFileW(LPCWSTR path, DWORD access, DWORD sharing,
        LPSECURITY_ATTRIBUTES security, DWORD creation, DWORD attributes, HANDLE template) {
    wchar_t *p=mlf_windows_path(path);
    HANDLE result=p ? CreateFileW(p,access,sharing,security,creation,attributes,template) : INVALID_HANDLE_VALUE;
    DWORD error=GetLastError(); free(p); SetLastError(error); return result;
}
static inline BOOL mlf_path_GetBinaryTypeW(LPCWSTR path, LPDWORD type) {
    wchar_t *p=mlf_windows_path(path);
    BOOL result=p && GetBinaryTypeW(p,type); DWORD error=GetLastError();
    free(p); SetLastError(error); return result;
}
static inline BOOL mlf_path_CreateSymbolicLinkW(LPCWSTR link, LPCWSTR target, DWORD flags) {
    wchar_t *a=mlf_windows_path(link), *b=a ? mlf_windows_path(target) : NULL;
    BOOL result=a && b && CreateSymbolicLinkW(a,b,flags); DWORD error=GetLastError();
    free(a); free(b); SetLastError(error); return result;
}
static inline BOOL mlf_path_GetVolumePathNameW(LPCWSTR path, LPWSTR volume, DWORD size) {
    wchar_t *p=mlf_windows_path(path);
    BOOL result=p && GetVolumePathNameW(p,volume,size); DWORD error=GetLastError();
    free(p); SetLastError(error); return result;
}
#define GetFileAttributesW mlf_path_GetFileAttributesW
#define SetFileAttributesW mlf_path_SetFileAttributesW
#define CreateDirectoryW mlf_path_CreateDirectoryW
#define RemoveDirectoryW mlf_path_RemoveDirectoryW
#define DeleteFileW mlf_path_DeleteFileW
#define CopyFileW mlf_path_CopyFileW
#define MoveFileExW mlf_path_MoveFileExW
#define FindFirstFileW mlf_path_FindFirstFileW
#define CreateFileW mlf_path_CreateFileW
#define GetBinaryTypeW mlf_path_GetBinaryTypeW
#define CreateSymbolicLinkW mlf_path_CreateSymbolicLinkW
#define GetVolumePathNameW mlf_path_GetVolumePathNameW
#endif
