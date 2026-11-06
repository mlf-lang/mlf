/* Native Win32 implementation of the host IO protocol. No shell or MSYS DLL. */
#ifndef MLF_SYSTEM_WINDOWS_H
#define MLF_SYSTEM_WINDOWS_H
static MlfValue *os_getEnv(MlfValue *name) {
    const char *key=file_path(name);
    if (!*key || strchr(key,'=')) fail("IO error: getEnv failed");
    wchar_t *wide=mlf_wide(key);
    if (!wide) fail("IO error: getEnv failed");
    SetLastError(ERROR_SUCCESS);
    DWORD n=GetEnvironmentVariableW(wide,NULL,0);
    if (!n) { DWORD error=GetLastError(); free(wide); if (error && error!=ERROR_ENVVAR_NOT_FOUND) fail("IO error: getEnv failed"); return mlf_string("",0); }
    wchar_t *buffer=allocate((size_t)n*sizeof(wchar_t));
    DWORD written=GetEnvironmentVariableW(wide,buffer,n);
    free(wide);
    if (written>=n) { free(buffer); fail("IO error: getEnv failed"); }
    char *text=mlf_utf8(buffer); free(buffer);
    if (!text) fail("IO error: invalid UTF-8 input");
    MlfValue *result=mlf_string(text,strlen(text)); free(text); return result;
}
static MlfValue *os_setEnv(MlfValue *name, MlfValue *contents) {
    const char *key=file_path(name);
    if (!*key || strchr(key,'=')) fail("IO error: setEnv failed");
    wchar_t *wide=mlf_wide(key), *value=mlf_wide(file_path(contents));
    int failed=!wide || !value || _wputenv_s(wide,value);
    /* The CRT treats an empty value as deletion. Win32 preserves emptiness. */
    if (!failed && !*value) failed=!SetEnvironmentVariableW(wide,L"");
    free(wide); free(value);
    if (failed) fail("IO error: setEnv failed");
    return mlf_constructor(1,0);
}
static MlfValue *os_unsetEnv(MlfValue *name) {
    const char *key=file_path(name);
    if (!*key || strchr(key,'=')) fail("IO error: unsetEnv failed");
    wchar_t *wide=mlf_wide(key);
    int failed=!wide || _wputenv_s(wide,L"");
    free(wide);
    if (failed) fail("IO error: unsetEnv failed");
    return mlf_constructor(1,0);
}
static MlfValue *os_directoryExists(MlfValue *name) {
    DWORD attributes=mlf_windows_attributes(file_path(name));
    return mlf_boolean(attributes!=INVALID_FILE_ATTRIBUTES && (attributes & FILE_ATTRIBUTE_DIRECTORY));
}
static MLF_NOINLINE MlfValue *os_listDirectory(MlfValue *name) {
    const char *path=file_path(name);
    DWORD attributes=mlf_windows_attributes(path);
    if (attributes==INVALID_FILE_ATTRIBUTES || !(attributes & FILE_ATTRIBUTE_DIRECTORY)) fail("IO error: listDirectory failed");
    size_t length=strlen(path);
    char *pattern=allocate(length+3); memcpy(pattern,path,length); memcpy(pattern+length,"/*",3);
    wchar_t *wide=mlf_wide(pattern); free(pattern);
    WIN32_FIND_DATAW entry;
    HANDLE search=wide ? FindFirstFileW(wide,&entry) : INVALID_HANDLE_VALUE;
    free(wide);
    if (search==INVALID_HANDLE_VALUE) {
        if (GetLastError()==ERROR_FILE_NOT_FOUND) return mlf_string("",0);
        fail("IO error: listDirectory failed");
    }
    size_t size=0, capacity=256;
    char *text=allocate(capacity);
    do {
        if (!wcscmp(entry.cFileName,L".") || !wcscmp(entry.cFileName,L"..")) continue;
        char *item=mlf_utf8(entry.cFileName);
        if (!item) { FindClose(search); free(text); fail("IO error: invalid UTF-8 input"); }
        size_t n=strlen(item)+1;
        if (n>SIZE_MAX-size || size+n>SIZE_MAX/2) fail("directory too large");
        if (size+n>capacity) { capacity=(size+n)*2; char *next=realloc(text,capacity); if (!next) fail("out of memory"); text=next; }
        memcpy(text+size,item,n); size+=n; free(item);
    } while (FindNextFileW(search,&entry));
    DWORD error=GetLastError(); FindClose(search);
    if (error!=ERROR_NO_MORE_FILES) { free(text); fail("IO error: listDirectory failed"); }
    MlfValue *result=mlf_string(text,size); free(text); return result;
}
static MlfValue *os_acquireFileLock(MlfValue *name) {
    wchar_t *wide=mlf_wide(file_path(name));
    HANDLE file=wide ? CreateFileW(wide,GENERIC_READ|GENERIC_WRITE,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,NULL,OPEN_ALWAYS,FILE_ATTRIBUTE_NORMAL,NULL) : INVALID_HANDLE_VALUE;
    free(wide);
    if (file==INVALID_HANDLE_VALUE) fail("IO error: acquireFileLock failed");
    OVERLAPPED overlapped={0};
    if (!LockFileEx(file,LOCKFILE_EXCLUSIVE_LOCK,0,MAXDWORD,MAXDWORD,&overlapped)) { CloseHandle(file); fail("IO error: acquireFileLock failed"); }
    return small((intptr_t)file);
}
static MlfValue *os_releaseFileLock(MlfValue *handle) {
    HANDLE file=(HANDLE)(uintptr_t)bounded_integer(handle,INTPTR_MAX,"invalid file lock");
    if (!CloseHandle(file)) fail("IO error: releaseFileLock failed");
    return mlf_constructor(1,0);
}
/* Always quote each argument, using the Microsoft CRT backslash/quote rules. */
static wchar_t *mlf_windows_command(char **arguments) {
    size_t capacity=1;
    for (char **arg=arguments; *arg; ++arg) {
        size_t n=strlen(*arg);
        if (n>(SIZE_MAX-capacity-3)/2) return NULL;
        capacity+=2*n+3;
    }
    wchar_t *line=allocate(capacity*sizeof(wchar_t)), *out=line;
    for (char **arg=arguments; *arg; ++arg) {
        wchar_t *wide=mlf_wide(*arg);
        if (!wide) { free(line); return NULL; }
        if (arg!=arguments) *out++=L' ';
        *out++=L'"';
        const wchar_t *p=wide;
        while (*p) {
            size_t slashes=0;
            while (*p==L'\\') { ++slashes; ++p; }
            size_t emit=(*p==L'"' || !*p) ? 2*slashes : slashes;
            while (emit--) *out++=L'\\';
            if (*p==L'"') *out++=L'\\';
            if (*p) *out++=*p++;
        }
        *out++=L'"'; free(wide);
    }
    *out=0; return line;
}
static HANDLE mlf_windows_redirect(const char *path, int stream) {
    if (!*path) {
        HANDLE result=NULL;
        HANDLE original=GetStdHandle(stream==0 ? STD_INPUT_HANDLE : stream==1 ? STD_OUTPUT_HANDLE : STD_ERROR_HANDLE);
        if (!DuplicateHandle(GetCurrentProcess(),original,GetCurrentProcess(),&result,0,TRUE,DUPLICATE_SAME_ACCESS)) return INVALID_HANDLE_VALUE;
        return result;
    }
    wchar_t *wide=mlf_wide(path);
    SECURITY_ATTRIBUTES security={sizeof(security),NULL,TRUE};
    HANDLE result=wide ? CreateFileW(wide,stream ? GENERIC_WRITE : GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,&security,stream ? CREATE_ALWAYS : OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,NULL) : INVALID_HANDLE_VALUE;
    free(wide); return result;
}
static MLF_NOINLINE MlfValue *os_runProcess(MlfValue *directory, MlfValue *specification) {
    const char *cwd=file_path(directory);
    specification=expect(specification,STRING);
    size_t length=specification->as.string.length, count=0;
    const char *text=specification->as.string.bytes;
    if (!length || text[length-1]) fail("IO error: invalid process specification");
    for (size_t i=0; i<length; ++i) if (!text[i]) ++count;
    if (count<5) fail("IO error: invalid process specification");
    char **parts=allocate((count+1)*sizeof(char *)); size_t j=0; parts[j++]=(char *)text;
    for (size_t i=0; i+1<length; ++i) if (!text[i]) parts[j++]=(char *)text+i+1;
    parts[count]=NULL;
    char *end; errno=0; long seconds=strtol(parts[0],&end,10);
    if (errno || *end || seconds<=0 || !*parts[4]) { free(parts); fail("IO error: invalid process specification"); }
    wchar_t *line=mlf_windows_command(parts+4), *working=*cwd ? mlf_wide(cwd) : NULL;
    HANDLE streams[3]={INVALID_HANDLE_VALUE,INVALID_HANDLE_VALUE,INVALID_HANDLE_VALUE};
    HANDLE job=NULL; PROCESS_INFORMATION process={0}; DWORD code=126;
    if (!line || (*cwd && !working)) goto cleanup;
    for (int i=0;i<3;++i) {
        if (i==2 && *parts[3] && !strcmp(parts[2],parts[3])) streams[2]=streams[1];
        else streams[i]=mlf_windows_redirect(parts[i+1],i);
        if (streams[i]==INVALID_HANDLE_VALUE) goto cleanup;
    }
    job=CreateJobObjectW(NULL,NULL);
    JOBOBJECT_EXTENDED_LIMIT_INFORMATION limits={0};
    limits.BasicLimitInformation.LimitFlags=JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
    if (!job || !SetInformationJobObject(job,JobObjectExtendedLimitInformation,&limits,sizeof(limits))) goto cleanup;
    STARTUPINFOW startup={0}; startup.cb=sizeof(startup); startup.dwFlags=STARTF_USESTDHANDLES;
    startup.hStdInput=streams[0]; startup.hStdOutput=streams[1]; startup.hStdError=streams[2];
    fflush(NULL);
    if (!CreateProcessW(NULL,line,NULL,NULL,TRUE,CREATE_SUSPENDED|CREATE_NO_WINDOW,NULL,working,&startup,&process)) {
        DWORD error=GetLastError(); code=(error==ERROR_FILE_NOT_FOUND || error==ERROR_PATH_NOT_FOUND) ? 127 : 126; goto cleanup;
    }
    if (!AssignProcessToJobObject(job,process.hProcess) || ResumeThread(process.hThread)==(DWORD)-1) {
        TerminateProcess(process.hProcess,126); WaitForSingleObject(process.hProcess,INFINITE); goto cleanup;
    }
    ULONGLONG start=GetTickCount64(), budget=(ULONGLONG)seconds*1000;
    for (;;) {
        DWORD waited=WaitForSingleObject(process.hProcess,10);
        if (waited==WAIT_OBJECT_0) { if (!GetExitCodeProcess(process.hProcess,&code)) code=126; break; }
        if (waited==WAIT_FAILED) { TerminateJobObject(job,126); WaitForSingleObject(process.hProcess,INFINITE); code=126; break; }
        if (GetTickCount64()-start>=budget) { TerminateJobObject(job,124); WaitForSingleObject(process.hProcess,INFINITE); code=124; break; }
    }
cleanup:
    if (process.hThread) CloseHandle(process.hThread);
    if (process.hProcess) CloseHandle(process.hProcess);
    if (job) CloseHandle(job);
    for (int i=0;i<3;++i) if (streams[i]!=INVALID_HANDLE_VALUE && (i!=2 || streams[2]!=streams[1])) CloseHandle(streams[i]);
    free(line); free(working); free(parts); return small(code);
}
#endif
