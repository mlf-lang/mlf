/* Binary transport for the MLF test harness. Assertions and codecs live in MLF. */
#include <stdio.h>
#include <string.h>
static int nibble(int c) { return c>='0'&&c<='9'?c-'0':c>='a'&&c<='f'?c-'a'+10:-1; }
int main(int argc,char **argv) {
    if(argc!=3 && argc!=4) return 2;
    if(!strcmp(argv[1],"read") && argc==3) {
        FILE *f=fopen(argv[2],"rb"); if(!f) return 1;
        int c; while((c=fgetc(f))!=EOF) if(printf("%02x",c)<0) { fclose(f); return 1; }
        int error=ferror(f); if(fclose(f)) error=1;
        return error || fflush(stdout)?1:0;
    }
    if(!strcmp(argv[1],"write") && argc==4) {
        FILE *f=fopen(argv[2],"wb"); if(!f) return 1;
        FILE *input=fopen(argv[3],"rb"); if(!input) { fclose(f); return 1; }
        int c;
        while((c=fgetc(input))!=EOF) {
            int a=nibble(c),b=nibble(fgetc(input));
            if(a<0||b<0||fputc(a*16+b,f)==EOF) { fclose(f); return 2; }
        }
        int error=ferror(input); if(fclose(input)) error=1;
        if(fclose(f)) error=1;
        return error?1:0;
    }
    return 2;
}
