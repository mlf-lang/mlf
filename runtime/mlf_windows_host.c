/* Native filesystem transport for the MLF package manager. Package policy,
 * dependency resolution and cache decisions remain in MLF. */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <winioctl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>

static wchar_t *absolute(const wchar_t *path) {
    DWORD n=GetFullPathNameW(path,0,NULL,NULL);
    wchar_t *full=n ? malloc(((size_t)n+1)*sizeof(wchar_t)) : NULL;
    if (!full || !GetFullPathNameW(path,n+1,full,NULL)) { free(full); return NULL; }
    for (wchar_t *c=full; *c; ++c) if (*c==L'/') *c=L'\\';
    return full;
}
static wchar_t *join(const wchar_t *a, const wchar_t *b) {
    size_t n=wcslen(a), m=wcslen(b);
    wchar_t *out=malloc((n+m+2)*sizeof(wchar_t));
    if (!out) return NULL;
    memcpy(out,a,n*sizeof(wchar_t)); out[n]=L'\\';
    memcpy(out+n+1,b,(m+1)*sizeof(wchar_t)); return out;
}
static int missing(DWORD error) { return error==ERROR_FILE_NOT_FOUND || error==ERROR_PATH_NOT_FOUND; }
static int mkdirs(const wchar_t *path) {
    DWORD attr=GetFileAttributesW(path);
    if (attr!=INVALID_FILE_ATTRIBUTES) return (attr & FILE_ATTRIBUTE_DIRECTORY)!=0;
    wchar_t *parent=_wcsdup(path);
    if (!parent) return 0;
    wchar_t *slash=wcsrchr(parent,L'\\');
    if (slash && slash>parent+2) { *slash=0; if (!mkdirs(parent)) { free(parent); return 0; } }
    free(parent);
    return CreateDirectoryW(path,NULL) || GetLastError()==ERROR_ALREADY_EXISTS;
}
static int remove_tree(const wchar_t *path) {
    DWORD attr=GetFileAttributesW(path);
    if (attr==INVALID_FILE_ATTRIBUTES) return missing(GetLastError());
    if (!(attr & FILE_ATTRIBUTE_DIRECTORY)) {
        if (attr & FILE_ATTRIBUTE_READONLY) SetFileAttributesW(path,attr & ~FILE_ATTRIBUTE_READONLY);
        return DeleteFileW(path)!=0;
    }
    /* Never traverse junctions or directory symlinks during recursive removal. */
    if (!(attr & FILE_ATTRIBUTE_REPARSE_POINT)) {
        wchar_t *pattern=join(path,L"*"); WIN32_FIND_DATAW entry;
        HANDLE search=pattern ? FindFirstFileW(pattern,&entry) : INVALID_HANDLE_VALUE;
        free(pattern);
        if (search==INVALID_HANDLE_VALUE && GetLastError()!=ERROR_FILE_NOT_FOUND) return 0;
        if (search!=INVALID_HANDLE_VALUE) {
            do {
                if (!wcscmp(entry.cFileName,L".") || !wcscmp(entry.cFileName,L"..")) continue;
                wchar_t *child=join(path,entry.cFileName);
                int ok=child && remove_tree(child); free(child);
                if (!ok) { FindClose(search); return 0; }
            } while (FindNextFileW(search,&entry));
            DWORD error=GetLastError(); FindClose(search);
            if (error!=ERROR_NO_MORE_FILES) return 0;
        }
    }
    return RemoveDirectoryW(path)!=0;
}
static int copy_tree(const wchar_t *from, const wchar_t *to) {
    DWORD attr=GetFileAttributesW(from);
    if (attr==INVALID_FILE_ATTRIBUTES) return 0;
    if (!(attr & FILE_ATTRIBUTE_DIRECTORY)) return CopyFileW(from,to,FALSE)!=0;
    if (attr & FILE_ATTRIBUTE_REPARSE_POINT) { SetLastError(ERROR_NOT_SUPPORTED); return 0; }
    if (!mkdirs(to)) return 0;
    wchar_t *pattern=join(from,L"*"); WIN32_FIND_DATAW entry;
    HANDLE search=pattern ? FindFirstFileW(pattern,&entry) : INVALID_HANDLE_VALUE; free(pattern);
    if (search==INVALID_HANDLE_VALUE) return GetLastError()==ERROR_FILE_NOT_FOUND;
    do {
        if (!wcscmp(entry.cFileName,L".") || !wcscmp(entry.cFileName,L"..")) continue;
        wchar_t *source=join(from,entry.cFileName), *destination=join(to,entry.cFileName);
        int ok=source && destination && copy_tree(source,destination);
        free(source); free(destination);
        if (!ok) { FindClose(search); return 0; }
    } while (FindNextFileW(search,&entry));
    DWORD error=GetLastError(); FindClose(search); return error==ERROR_NO_MORE_FILES;
}
static int safe_remove(const wchar_t *path) {
    wchar_t volume[32768];
    size_t n=wcslen(path);
    if (n<5 || !GetVolumePathNameW(path,volume,32768)) return 0;
    size_t root=wcslen(volume);
    while (n && path[n-1]==L'\\') --n;
    while (root && volume[root-1]==L'\\') --root;
    return n>root && !(n==root && !_wcsnicmp(path,volume,root));
}
static int junction(const wchar_t *source, const wchar_t *destination) {
    size_t n=wcslen(source), substitute=n+4;
    if (n>7000 || source[1]!=L':') { SetLastError(ERROR_NOT_SUPPORTED); return 0; }
    struct MountPoint {
        DWORD tag; WORD size, reserved;
        WORD substituteOffset, substituteLength, printOffset, printLength;
        wchar_t paths[1];
    };
    size_t total=16+(substitute+1+n+1)*sizeof(wchar_t);
    struct MountPoint *data=calloc(1,total);
    if (!data) return 0;
    data->tag=IO_REPARSE_TAG_MOUNT_POINT;
    data->size=(WORD)(total-8);
    data->substituteLength=(WORD)(substitute*sizeof(wchar_t));
    data->printOffset=(WORD)((substitute+1)*sizeof(wchar_t));
    data->printLength=(WORD)(n*sizeof(wchar_t));
    memcpy(data->paths,L"\\??\\",4*sizeof(wchar_t));
    memcpy(data->paths+4,source,(n+1)*sizeof(wchar_t));
    memcpy(data->paths+substitute+1,source,(n+1)*sizeof(wchar_t));
    if (!CreateDirectoryW(destination,NULL)) { free(data); return 0; }
    HANDLE dir=CreateFileW(destination,GENERIC_WRITE,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,NULL,OPEN_EXISTING,FILE_FLAG_OPEN_REPARSE_POINT|FILE_FLAG_BACKUP_SEMANTICS,NULL);
    DWORD written=0;
    int ok=dir!=INVALID_HANDLE_VALUE && DeviceIoControl(dir,FSCTL_SET_REPARSE_POINT,data,(DWORD)total,NULL,0,&written,NULL);
    DWORD error=GetLastError();
    if (dir!=INVALID_HANDLE_VALUE) CloseHandle(dir);
    if (!ok) RemoveDirectoryW(destination);
    free(data); SetLastError(error); return ok;
}
static int temporary_directory(const wchar_t *pattern) {
    wchar_t *path=absolute(pattern);
    if (!path) return 1;
    size_t n=wcslen(path);
    while (n && path[n-1]==L'X') --n;
    wchar_t *candidate=malloc((n+40)*sizeof(wchar_t));
    if (!candidate) { free(path); return 1; }
    LARGE_INTEGER clock; QueryPerformanceCounter(&clock);
    int ok=0;
    for (unsigned attempt=0;attempt<100;++attempt) {
        memcpy(candidate,path,n*sizeof(wchar_t));
        swprintf(candidate+n,40,L"%lx-%llx",(unsigned long)GetCurrentProcessId(),(unsigned long long)clock.QuadPart+attempt);
        if (CreateDirectoryW(candidate,NULL)) { ok=1; break; }
        if (GetLastError()!=ERROR_ALREADY_EXISTS) break;
    }
    if (ok) {
        int length=WideCharToMultiByte(CP_UTF8,0,candidate,-1,NULL,0,NULL,NULL);
        char *utf8=length ? malloc((size_t)length) : NULL;
        if (utf8 && WideCharToMultiByte(CP_UTF8,0,candidate,-1,utf8,length,NULL,NULL)) puts(utf8); else ok=0;
        free(utf8);
    }
    free(path); free(candidate); return ok ? 0 : 1;
}
int wmain(int argc, wchar_t **argv) {
    if (argc==4 && !wcscmp(argv[1],L"mktemp") && !wcscmp(argv[2],L"-d")) return temporary_directory(argv[3]);
    if (argc==3 && !wcscmp(argv[1],L"uname")) {
        if (!wcscmp(argv[2],L"-s")) { puts("Windows"); return 0; }
        if (!wcscmp(argv[2],L"-m")) { puts("x86_64"); return 0; }
        return 2;
    }
    if (argc<3) { fputs("usage: mlf-host mkdir|copy|move|remove|test|link PATH [PATH]\n",stderr); return 2; }
    const wchar_t *operation=argv[1]; int index=2;
    int recursive=0;
    while (index<argc && argv[index][0]==L'-') {
        if (!wcscmp(argv[index],L"-R")) recursive=1;
        ++index;
    }
    if (index>=argc) return 2;
    wchar_t *a=absolute(argv[index]), *b=index+1<argc ? absolute(argv[index+1]) : NULL;
    if (!a || (index+1<argc && !b)) { free(a); free(b); return 1; }
    int ok=0;
    if (!wcscmp(operation,L"mkdir") && index+1==argc) ok=mkdirs(a);
    else if (!wcscmp(operation,L"copy") && b && index+2==argc) ok=recursive ? copy_tree(a,b) : CopyFileW(a,b,FALSE)!=0;
    else if (!wcscmp(operation,L"move") && b && index+2==argc) ok=MoveFileExW(a,b,MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH)!=0;
    else if (!wcscmp(operation,L"remove") && index+1==argc) {
        if (!safe_remove(a)) { free(a); free(b); fputs("mlf-host: refusing unsafe removal path\n",stderr); return 2; }
        ok=remove_tree(a);
    } else if (!wcscmp(operation,L"test") && index+1==argc) {
        DWORD type; ok=GetBinaryTypeW(a,&type)!=0;
        free(a); free(b); return ok ? 0 : 1;
    } else if (!wcscmp(operation,L"link") && b && index+2==argc) {
        /* POSIX link targets are relative to the destination directory. */
        wchar_t *parent=_wcsdup(b), *slash=parent ? wcsrchr(parent,L'\\') : NULL;
        if (slash) *slash=0;
        int full=argv[index][0]==L'\\' || (wcslen(argv[index])>=2 && argv[index][1]==L':');
        wchar_t *relative=parent && !full ? join(parent,argv[index]) : NULL;
        wchar_t *source=full ? _wcsdup(a) : relative ? absolute(relative) : NULL;
        if (source) {
            DWORD attributes=GetFileAttributesW(source);
            if (attributes!=INVALID_FILE_ATTRIBUTES && (attributes & FILE_ATTRIBUTE_DIRECTORY)) ok=junction(source,b);
            else { DeleteFileW(b); ok=CreateHardLinkW(b,source,NULL) || CopyFileW(source,b,FALSE); }
        }
        free(parent); free(relative); free(source);
    } else { free(a); free(b); fputs("mlf-host: invalid operation or arguments\n",stderr); return 2; }
    DWORD error=ok ? ERROR_SUCCESS : GetLastError();
    free(a); free(b);
    if (!ok) fprintf(stderr,"mlf-host: operation failed (Win32 %lu)\n",(unsigned long)error);
    return ok ? 0 : 1;
}
