/* Test the actual helper's removal guards without performing any removal. */
#define wmain mlf_host_main
#include "../../runtime/mlf_windows_host.c"
#undef wmain
static void require(int ok, const char *message) {
    if (!ok) { fprintf(stderr,"windows paths: %s\n",message); exit(90); }
}
int wmain(void) {
    wchar_t current[32768], volume[32768], extended[32768];
    DWORD n=GetCurrentDirectoryW(32768,current);
    require(n && n<32768,"current directory");
    require(GetVolumePathNameW(current,volume,32768),"current volume");
    require(!safe_remove(volume),"volume root removal guard");
    require(volume[1]==L':',"test requires a drive-rooted runner workspace");
    swprintf(extended,32768,L"\\\\?\\%ls",volume);
    require(!safe_remove(extended),"extended volume root removal guard");
    require(!safe_remove(L"\\\\.\\C:\\"),"device namespace removal guard");
    wchar_t *empty=mlf_windows_path(L""), *device=mlf_windows_path(L"NUL");
    require(empty && !*empty && device && !wcscmp(device,L"NUL"),"short path semantics");
    free(empty); free(device);
    wchar_t path[1024]=L"\\\\server\\share";
    for (int i=0;i<6;++i) wcscat(path,L"\\0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef");
    wchar_t *unc=mlf_windows_path(path);
    require(unc && !wcsncmp(unc,L"\\\\?\\UNC\\server\\share\\",21),"extended UNC spelling");
    require(!wcscmp(unc+8,path+2),"UNC path contents");
    free(unc);
    wcscpy(path,L"./windows-paths");
    for (int i=0;i<6;++i) wcscat(path,L"/0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef");
    wcscat(path,L"/child/../file");
    wchar_t *relative=mlf_windows_path(path);
    require(relative && !wcsncmp(relative,L"\\\\?\\",4),"absolute extended relative path");
    require(!wcschr(relative,L'/') && !wcsstr(relative,L"\\..\\") && !wcsstr(relative,L"\\child\\"),"normalize before extending");
    free(relative);
    puts("Windows path guards passed"); return 0;
}
