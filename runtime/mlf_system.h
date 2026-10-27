/* POSIX host IO. Package policy, manifests and build decisions live in MLF. */
#ifndef MLF_SYSTEM_H
#define MLF_SYSTEM_H
#ifdef _WIN32
#include "mlf_system_windows.h"
#else
#include <dirent.h>
#include <fcntl.h>
#include <signal.h>
#include <sys/wait.h>
#include <time.h>

static MlfValue *os_getEnv(MlfValue *name) {
    const char *key = file_path(name);
    if (!*key || strchr(key,'=')) fail("IO error: getEnv failed");
    const char *text = getenv(key);
    if (!text) text = "";
    if (!valid_utf8((const unsigned char *)text,strlen(text))) fail("IO error: invalid UTF-8 input");
    return mlf_string(text,strlen(text));
}
static MlfValue *os_setEnv(MlfValue *name, MlfValue *contents) {
    /* Sequence the language operands explicitly; C argument evaluation order
     * must not choose which panic or path-validation failure is observed. */
    const char *key = file_path(name);
    const char *text = file_path(contents);
    if (setenv(key,text,1)) fail("IO error: setEnv failed");
    return mlf_constructor(1,0);
}
static MlfValue *os_unsetEnv(MlfValue *name) {
    if (unsetenv(file_path(name))) fail("IO error: unsetEnv failed");
    return mlf_constructor(1,0);
}
static MlfValue *os_directoryExists(MlfValue *name) {
    struct stat st;
    return mlf_boolean(!stat(file_path(name),&st) && S_ISDIR(st.st_mode));
}
static MlfValue *os_listDirectory(MlfValue *name) {
    DIR *dir = opendir(file_path(name));
    if (!dir) fail("IO error: listDirectory failed");
    size_t size = 0, capacity = 256;
    char *text = allocate(capacity);
    struct dirent *entry;
    errno = 0;
    while ((entry = readdir(dir))) {
        if (!strcmp(entry->d_name,".") || !strcmp(entry->d_name,"..")) continue;
        size_t n = strlen(entry->d_name) + 1;
        if (n > SIZE_MAX-size) fail("directory too large");
        if (size+n > capacity) { capacity = (size+n)*2; text = realloc(text,capacity); if (!text) fail("out of memory"); }
        memcpy(text+size,entry->d_name,n); size += n;
        errno = 0;
    }
    int failed = errno;
    if (closedir(dir)) failed = 1;
    if (failed) { free(text); fail("IO error: listDirectory failed"); }
    if (!valid_utf8((unsigned char *)text,size)) { free(text); fail("IO error: invalid UTF-8 input"); }
    MlfValue *result = mlf_string(text,size); free(text); return result;
}
static MlfValue *os_acquireFileLock(MlfValue *name) {
    int fd = open(file_path(name),O_RDWR|O_CREAT|O_CLOEXEC,0600);
    struct flock lock = {0}; lock.l_type = F_WRLCK; lock.l_whence = SEEK_SET;
    if (fd < 0) fail("IO error: acquireFileLock failed");
    while (fcntl(fd,F_SETLKW,&lock) < 0) if (errno != EINTR) { close(fd); fail("IO error: acquireFileLock failed"); }
    return small(fd);
}
static MlfValue *os_releaseFileLock(MlfValue *handle) {
    int fd = (int)bounded_integer(handle,INT_MAX,"invalid file lock");
    if (close(fd)) fail("IO error: releaseFileLock failed");
    return mlf_constructor(1,0);
}

/* cwd, plus NUL-terminated fields: timeout seconds, stdin file, stdout file,
 * stderr file, executable, arguments. Empty redirections inherit streams;
 * equal nonempty stdout/stderr paths share one descriptor. No shell is used. */
static MlfValue *os_runProcess(MlfValue *directory, MlfValue *specification) {
    const char *cwd = file_path(directory);
    specification = expect(specification,STRING);
    size_t length = specification->as.string.length, count = 0;
    const char *text = specification->as.string.bytes;
    if (!length || text[length-1]) fail("IO error: invalid process specification");
    for (size_t i=0; i<length; ++i) if (!text[i]) ++count;
    if (count < 5) fail("IO error: invalid process specification");
    char **parts = allocate((count+1)*sizeof(char *));
    size_t j=0; parts[j++] = (char *)text;
    for (size_t i=0; i+1<length; ++i) if (!text[i]) parts[j++] = (char *)text+i+1;
    parts[count] = NULL;
    char *end; errno=0;
    long seconds = strtol(parts[0],&end,10);
    if (errno || *end || seconds <= 0 || seconds > 2147483647 || !*parts[4]) { free(parts); fail("IO error: invalid process specification"); }
    /* Build workers belong to a runner-owned lifetime. Descendants must stay
     * in that process group so the guardian can clean them after worker,
     * coordinator, or runner death. The exact group check rejects stale env. */
    const char *scope = getenv("MLF_BUILD_SCOPE");
    char *scope_end = NULL;
    long scope_id = scope && *scope ? strtol(scope,&scope_end,10) : 0;
    int supervised = scope_id > 0 && scope_end && !*scope_end && scope_id == (long)getpgrp();
    fflush(NULL);
    pid_t pid = fork();
    if (pid < 0) { free(parts); fail("IO error: runProcess failed"); }
    if (!pid) {
        /* Only the child establishes its group. Concurrent parent/child
         * setpgid calls can fail with EPERM on Darwin. Verify the required
         * postcondition if the group was already established by the host. */
        if (!supervised && setpgid(0,0) && getpgrp()!=getpid()) _exit(126);
        if (*cwd && chdir(cwd)) _exit(126);
        for (int i=0;i<3;++i) {
            if (i==2 && *parts[3] && !strcmp(parts[2],parts[3])) { if (dup2(1,2)<0) _exit(126); continue; }
            if (!*parts[i+1]) continue;
            int fd = open(parts[i+1],i ? O_WRONLY|O_CREAT|O_TRUNC : O_RDONLY,0666);
            if (fd<0 || dup2(fd,i)<0) _exit(126);
            if (fd!=i) close(fd);
        }
        execvp(parts[4],parts+4);
        _exit(errno==ENOENT ? 127 : 126);
    }
    free(parts);
    struct timespec start,now,pause = {0,10000000};
    if (clock_gettime(CLOCK_MONOTONIC,&start)) { kill(-pid,SIGKILL); kill(pid,SIGKILL); waitpid(pid,NULL,0); fail("IO error: runProcess failed"); }
    int status;
    for (;;) {
        pid_t done = waitpid(pid,&status,WNOHANG);
        if (done == pid) break;
        if (done<0 && errno!=EINTR) fail("IO error: runProcess failed");
        clock_gettime(CLOCK_MONOTONIC,&now);
        if (now.tv_sec-start.tv_sec >= seconds && (now.tv_sec-start.tv_sec>seconds || now.tv_nsec>=start.tv_nsec)) {
            /* A timed-out supervised subprocess invalidates the whole action.
             * Killing its enclosing scope also stops grandchildren. */
            kill(supervised ? -getpgrp() : -pid,SIGKILL); kill(pid,SIGKILL); while (waitpid(pid,&status,0)<0 && errno==EINTR) {}
            return small(124);
        }
        nanosleep(&pause,NULL);
    }
    return small(WIFEXITED(status) ? WEXITSTATUS(status) : 128+WTERMSIG(status));
}

#endif
/* SHA-256, streaming binary files; independent of text encoding and tools. */
static uint32_t os_rotr(uint32_t x, unsigned n) { return (x>>n)|(x<<(32-n)); }
static void os_sha_block(uint32_t h[8], const unsigned char block[64]) {
    static const uint32_t k[64] = {
      0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
      0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
      0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
      0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
      0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
      0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
      0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
      0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2};
    uint32_t w[64];
    for(int i=0;i<16;++i) w[i]=((uint32_t)block[4*i]<<24)|((uint32_t)block[4*i+1]<<16)|((uint32_t)block[4*i+2]<<8)|block[4*i+3];
    for(int i=16;i<64;++i) {uint32_t a=w[i-15],b=w[i-2]; w[i]=w[i-16]+(os_rotr(a,7)^os_rotr(a,18)^(a>>3))+w[i-7]+(os_rotr(b,17)^os_rotr(b,19)^(b>>10));}
    uint32_t a=h[0],b=h[1],c=h[2],d=h[3],e=h[4],f=h[5],g=h[6],v=h[7];
    for(int i=0;i<64;++i) {uint32_t t=v+(os_rotr(e,6)^os_rotr(e,11)^os_rotr(e,25))+((e&f)^(~e&g))+k[i]+w[i];uint32_t u=(os_rotr(a,2)^os_rotr(a,13)^os_rotr(a,22))+((a&b)^(a&c)^(b&c)); v=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u;}
    h[0]+=a;h[1]+=b;h[2]+=c;h[3]+=d;h[4]+=e;h[5]+=f;h[6]+=g;h[7]+=v;
}
static MlfValue *os_fileDigest(MlfValue *name) {
    FILE *file = fopen(file_path(name),"rb");
    if (!file) fail("IO error: fileDigest failed");
    uint32_t h[8]={0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19};
    unsigned char buffer[65536],tail[128]={0};
    size_t n,remaining=0; uint64_t total=0;
    while ((n=fread(buffer,1,sizeof(buffer),file))) {
        total += n;
        size_t pos=0;
        if (remaining) { size_t take=n < 64-remaining ? n : 64-remaining; memcpy(tail+remaining,buffer,take); remaining+=take;pos+=take;if(remaining==64){os_sha_block(h,tail);remaining=0;} }
        while (n-pos>=64) {os_sha_block(h,buffer+pos);pos+=64;}
        if(pos<n){remaining=n-pos;memcpy(tail,buffer+pos,remaining);}
    }
    int failed=ferror(file);if(fclose(file))failed=1;if(failed)fail("IO error: fileDigest failed");
    size_t size=remaining<56?64:128;memset(tail+remaining,0,size-remaining);tail[remaining]=128;
    uint64_t bits=total*8;for(int i=0;i<8;++i)tail[size-1-i]=(unsigned char)(bits>>(8*i));
    os_sha_block(h,tail);if(size==128)os_sha_block(h,tail+64);
    char hex[65];for(int i=0;i<8;++i)snprintf(hex+8*i,9,"%08" PRIx32,h[i]);
    return mlf_string(hex,64);
}
#endif
