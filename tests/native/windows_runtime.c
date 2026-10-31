/* Native Windows regressions: integer widths, UTF-8 files, process argv,
 * redirects, deadlines, descendant cleanup, and OS-enforced file locking. */
#include "../../runtime/mlf_runtime.c"

static void require(int ok, const char *message) {
    if (!ok) { fprintf(stderr,"windows runtime: %s\n",message); exit(90); }
}
static MlfValue *text(const char *s) { return mlf_string(s,strlen(s)); }
static int eq(MlfValue *s, const char *expected) {
    return s->as.string.length==strlen(expected) && !memcmp(s->as.string.bytes,expected,strlen(expected));
}
#include "numeric_width_contract.h"
static MlfValue *packed(const char **fields) {
    char data[32768]; size_t n=0;
    for (;*fields;++fields) {
        size_t size=strlen(*fields)+1;
        require(n+size<=sizeof(data),"process test buffer");
        memcpy(data+n,*fields,size); n+=size;
    }
    return mlf_string(data,n);
}
static void host_command(const char *operation, const char *a, const char *b) {
    const char *helper=getenv("MLF_WINDOWS_HOST");
    require(helper && *helper,"native filesystem helper required");
    const char *fields[]={"10","","","",helper,operation,a,b,NULL};
    require(small_value(os_runProcess(text(""),packed(fields)))==0,operation);
}
static void long_paths(MlfValue *self) {
    char directory[1024]="windows-long-paths";
    for (int i=0;i<6;++i)
        strcat(directory,"/cache \xce\xbb-0123456789abcdef0123456789abcdef0123456789abcdef");
    require(strlen(directory)>300,"long path regression must exceed MAX_PATH");
    host_command("mkdir",directory,NULL);
    require(mlf_truth(os_directoryExists(text(directory))),"long directory exists");
    char file[1100], next[1100], copied[1100], output[1100], errors[1100], lockpath[1100], alias[1100];
    snprintf(file,sizeof(file),"%s/data \xce\xbb.mlfq",directory);
    snprintf(next,sizeof(next),"%s/./data \xce\xbb.mlfq.new",directory);
    snprintf(copied,sizeof(copied),"%s/copy.txt",directory);
    snprintf(output,sizeof(output),"%s/output.txt",directory);
    snprintf(errors,sizeof(errors),"%s/errors.txt",directory);
    snprintf(lockpath,sizeof(lockpath),"%s/query.lock",directory);
    snprintf(alias,sizeof(alias),"%s/alias",directory);
    write_file(text(next),text("abc"));
    write_file(text(file),text("old"));
    host_command("move",next,file);
    require(!mlf_truth(file_exists(text(next))) && mlf_truth(file_exists(text(file))),"long atomic rename");
    require(eq(read_file(text(file)),"abc"),"long UTF-8 file roundtrip");
    require(eq(os_fileDigest(text(file)),"ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"),"long file digest");
    host_command("copy",file,copied);
    require(eq(read_file(text(copied)),"abc"),"long file copy");
    MlfValue *items=os_listDirectory(text(directory));
    int found=0;
    for (size_t i=0;i<items->as.string.length;i+=strlen(items->as.string.bytes+i)+1)
        if (!strcmp(items->as.string.bytes+i,"data \xce\xbb.mlfq")) found=1;
    require(found,"long directory enumeration");
    MlfValue *canonical=canonical_path(text(file));
    require(strncmp(canonical->as.string.bytes,"//?/",4)!=0,"canonical path leaks extended namespace");
    require(eq(read_file(canonical),"abc"),"long canonical path roundtrip");
    /* A relative directory link must keep its target identity, and deleting
     * the link must never traverse the referenced directory. */
    host_command("link",".",alias);
    require(eq(canonical_path(text(alias)),canonical_path(text(directory))->as.string.bytes),"long junction identity");
    host_command("remove",alias,NULL);
    require(mlf_truth(file_exists(text(file))),"junction removal traversed target");
    host_command("link","data \xce\xbb.mlfq",alias);
    require(eq(canonical_path(text(alias)),canonical->as.string.bytes),"long file symlink identity");
    host_command("remove",alias,NULL);
    const char *fields[]={"10","",output,errors,self->as.string.bytes,"--echo","long path \xce\xbb",NULL};
    require(small_value(os_runProcess(text(""),packed(fields)))==0,"long process redirects");
    require(eq(read_file(text(output)),"long path \xce\xbb\n") && eq(read_file(text(errors)),"error\n"),"long redirect contents");
    MlfValue *lock=os_acquireFileLock(text(lockpath));
    os_releaseFileLock(lock);
    require(mlf_truth(file_exists(text(lockpath))),"long file lock");
    host_command("remove","windows-long-paths",NULL);
    require(!mlf_truth(os_directoryExists(text(directory))),"long recursive removal");
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
    check_numeric_widths();
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
    long_paths(self);
    puts("Windows runtime regressions passed"); return 0;
}
