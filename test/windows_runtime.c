/* Native Windows regressions: integer widths, UTF-8 files, process argv,
 * redirects, deadlines, descendant cleanup, and OS-enforced file locking. */
#include "../runtime/mlf_runtime.c"

static void require(int ok, const char *message) {
    if (!ok) { fprintf(stderr,"windows runtime: %s\n",message); exit(90); }
}
static MlfValue *text(const char *s) { return mlf_string(s,strlen(s)); }
static int eq(MlfValue *s, const char *expected) {
    return s->as.string.length==strlen(expected) && !memcmp(s->as.string.bytes,expected,strlen(expected));
}
static MlfValue *packed(const char **fields) {
    char data[32768]; size_t n=0;
    for (;*fields;++fields) {
        size_t size=strlen(*fields)+1;
        require(n+size<=sizeof(data),"process test buffer");
        memcpy(data+n,*fields,size); n+=size;
    }
    return mlf_string(data,n);
}
int main(int argc, char **argv) {
    mlf_set_args(argc,argv);
    if (argument_count && !strcmp(argument_values[0],"--echo")) {
        for (int i=1;i<argument_count;++i) { fwrite(argument_values[i],1,strlen(argument_values[i]),stdout); fputc('\n',stdout); }
        fputs("error\n",stderr); return 0;
    }
    if (argument_count && !strcmp(argument_values[0],"--sleep")) { Sleep(30000); return 0; }
    if (argument_count && !strcmp(argument_values[0],"--marker")) {
        Sleep(2000); write_file(text(argument_values[1]),text("survived")); return 0;
    }
    if (argument_count && !strcmp(argument_values[0],"--lock")) {
        MlfValue *lock=os_acquireFileLock(text(argument_values[1]));
        write_file(text(argument_values[2]),text("acquired")); os_releaseFileLock(lock); return 0;
    }
    if (argument_count && !strcmp(argument_values[0],"--tree")) {
        char *args[]={argv[0],"--marker",argument_values[1],NULL};
        wchar_t *line=mlf_windows_command(args);
        STARTUPINFOW startup={0}; startup.cb=sizeof(startup); PROCESS_INFORMATION child={0};
        require(CreateProcessW(NULL,line,NULL,NULL,FALSE,CREATE_NO_WINDOW,NULL,NULL,&startup,&child),"spawn descendant");
        free(line); CloseHandle(child.hThread); CloseHandle(child.hProcess); Sleep(30000); return 0;
    }
    require(eq(show_integer(mlf_add_int(mlf_integer("4294967296"),mlf_integer("4611686018427387903"))),"4611686022722355199"),"64-bit tagged/big addition");
    require(eq(show_integer(mlf_sub_int(mlf_integer("-4611686018427387904"),mlf_integer("4294967296"))),"-4611686022722355200"),"64-bit tagged/big subtraction");
    require(eq(show_integer(integer_extended(MUL_INT,mlf_integer("4294967296"),mlf_integer("4294967296"))),"18446744073709551616"),"64-bit multiplication");
    require(integer_compare(mlf_integer("4294967296"),mlf_integer("18446744073709551616"))<0,"wide comparison");
    require(bounded_integer(mlf_integer("18446744073709551615"),UINT64_MAX,"wide bound")==UINT64_MAX,"64-bit unsigned conversion");
    require(eq(show_integer(double_to_bits(mlf_double(-1.0))),"13830554455654793216"),"double bit conversion");
    const char *unicode="windows-runtime-\xce\xbb data.txt";
    write_file(text(unicode),text("abc"));
    require(eq(read_file(text(unicode)),"abc"),"UTF-8 file roundtrip");
    require(eq(os_fileDigest(text(unicode)),"ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"),"SHA-256");
    require(eq(os_getEnv(text("MLF_MISSING_WINDOWS_TEST")),""),"missing environment");
    os_setEnv(text("MLF_WINDOWS_TEST"),text("\xce\xbb"));
    require(eq(os_getEnv(text("MLF_WINDOWS_TEST")),"\xce\xbb"),"UTF-8 environment");
    os_unsetEnv(text("MLF_WINDOWS_TEST"));
    require(eq(os_getEnv(text("MLF_WINDOWS_TEST")),""),"unset environment");
    MlfValue *self=executable_path();
    const char *fields[]={"10","","windows-argv.out","windows-argv.err",self->as.string.bytes,"--echo","a b","a\"b","tail\\","","\xce\xbb",NULL};
    require(small_value(os_runProcess(text(""),packed(fields)))==0,"process success");
    require(eq(read_file(text("windows-argv.out")),"a b\na\"b\ntail\\\n\n\xce\xbb\n"),"argument quoting and UTF-8");
    require(eq(read_file(text("windows-argv.err")),"error\n"),"stderr redirect");
    fields[2]="windows-merged.out"; fields[3]=fields[2];
    require(small_value(os_runProcess(text(""),packed(fields)))==0,"merged redirects");
    MlfValue *merged=read_file(text(fields[2]));
    require(strstr(merged->as.string.bytes,"error\n")!=NULL && strstr(merged->as.string.bytes,"a b\n")!=NULL,"shared output descriptor");
    const char *missing[]={"5","","","","mlf-nonexistent-test-command-75c9",NULL};
    require(small_value(os_runProcess(text(""),packed(missing)))==127,"missing executable status");
    const char *sleeping[]={"1","","","",self->as.string.bytes,"--sleep",NULL};
    require(small_value(os_runProcess(text(""),packed(sleeping)))==124,"process timeout");
    const char *tree[]={"1","","","",self->as.string.bytes,"--tree","windows-descendant.txt",NULL};
    require(small_value(os_runProcess(text(""),packed(tree)))==124,"process tree timeout");
    Sleep(2300);
    require(!mlf_truth(file_exists(text("windows-descendant.txt"))),"timed-out descendant survived");
    MlfValue *lock=os_acquireFileLock(text("windows-test.lock"));
    char *lockargs[]={self->as.string.bytes,"--lock","windows-test.lock","windows-lock.out",NULL};
    wchar_t *line=mlf_windows_command(lockargs); STARTUPINFOW startup={0}; startup.cb=sizeof(startup); PROCESS_INFORMATION child={0};
    require(CreateProcessW(NULL,line,NULL,NULL,FALSE,CREATE_NO_WINDOW,NULL,NULL,&startup,&child),"spawn lock contender"); free(line);
    require(WaitForSingleObject(child.hProcess,300)==WAIT_TIMEOUT,"lock contender did not block");
    os_releaseFileLock(lock);
    require(WaitForSingleObject(child.hProcess,5000)==WAIT_OBJECT_0,"lock contender remained blocked");
    DWORD status; require(GetExitCodeProcess(child.hProcess,&status) && !status,"lock contender failed");
    CloseHandle(child.hThread); CloseHandle(child.hProcess);
    require(eq(read_file(text("windows-lock.out")),"acquired"),"file lock handoff");
    puts("Windows runtime regressions passed"); return 0;
}
