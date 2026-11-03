/* Stage04 readback harness template. SOURCE ONLY until separately reviewed.
 * No runtime header, target-language body, callback, model, or source compiler.
 * Fixed placeholder markers are replaced by the independently authored host driver.
 */
#include "ir8_packet_generated.h"
#include <inttypes.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static Ir8PacketWorkspace workspace;
static const Ir8PacketExpectedBindings trusted_bindings = @STAGE04_BINDINGS@;
static unsigned int harness_failures;

static void die(const char *message) {
    (void)fprintf(stderr, "stage04 harness: %s\n", message);
    exit(70);
}
/* Check in the size_t domain before either directory or row multiplication. */
static size_t checked_product(size_t count, size_t element_bytes,
                              const char *message) {
    if(element_bytes!=0 && count>SIZE_MAX/element_bytes) die(message);
    return count*element_bytes;
}
static void copy_at(void *to, const unsigned char *root, size_t length,
                    size_t offset, size_t bytes) {
    if (offset > length || bytes > length - offset) die("readback extent");
    (void)memcpy(to, root + offset, bytes);
}
static void store_at(unsigned char *root, size_t length, size_t offset,
                     const void *from, size_t bytes) {
    if (offset > length || bytes > length - offset) die("mutation extent");
    (void)memcpy(root + offset, from, bytes);
}
static void u32(uint32_t value) { (void)printf("%" PRIu32, value); }
static void span(Ir8PacketSpan value) {
    (void)printf("{\"object\":%" PRIu32 ",\"count\":%" PRIu32 "}",value.object,value.count);
}
static void bytes(const unsigned char *value, size_t count) {
    size_t i; (void)putchar('[');
    for (i=0;i<count;i++) { if(i) (void)putchar(',');u32(value[i]); }
    (void)putchar(']');
}
static void report_json(const Ir8PacketReport *r) {
    @STAGE04_REPORT_PRINTER@
}
static Ir8PacketObjectDirectoryEntry object_at(const unsigned char *root,
                                               size_t length, uint32_t object) {
    Ir8PacketProgramHeader h; Ir8PacketObjectDirectoryEntry e; size_t off;
    copy_at(&h,root,length,0,sizeof h);
    if(object>=h.directory_count) die("object id");
    off=checked_product((size_t)object,sizeof e,"directory arithmetic");
    if(off>SIZE_MAX-(size_t)h.directory_offset) die("directory arithmetic");
    copy_at(&e,root,length,(size_t)h.directory_offset+off,sizeof e);return e;
}
static size_t row_offset(const unsigned char *root,size_t length,uint32_t object,uint32_t row) {
    Ir8PacketObjectDirectoryEntry e=object_at(root,length,object);
    size_t off;
    if(row>=e.count || e.offset==UINT32_MAX) die("row id");
    off=checked_product((size_t)row,(size_t)e.element_bytes,"row arithmetic");
    if(off>SIZE_MAX-e.offset) die("row arithmetic");return e.offset+off;
}
static void row_json(uint32_t element,const unsigned char *root,size_t length,size_t offset) {
    switch(element) {
    @STAGE04_ROW_PRINTERS@
    default:die("unknown readback element");
    }
}
static void abi_json(void) {
    @STAGE04_ABI_PRINTER@
}
static void census_json(void) {
    @STAGE04_CENSUS_PRINTER@
}
static void directory_json(const unsigned char *root,size_t length) {
    Ir8PacketProgramHeader h;uint32_t i;
    copy_at(&h,root,length,0,sizeof h);(void)putchar('[');
    for(i=0;i<h.directory_count;i++) {
        if(i)(void)putchar(',');
        row_json(40,root,length,(size_t)h.directory_offset+(size_t)i*sizeof(Ir8PacketObjectDirectoryEntry));
    }
    (void)putchar(']');
}
static void objects_json(const unsigned char *root,size_t length) {
    Ir8PacketProgramHeader h;uint32_t i,j;
    copy_at(&h,root,length,0,sizeof h);(void)putchar('[');
    for(i=0;i<h.directory_count;i++) {
        Ir8PacketObjectDirectoryEntry e=object_at(root,length,i);
        if(i)(void)putchar(',');(void)printf("{\"object\":%" PRIu32 ",\"rows\":[",i);
        for(j=0;j<e.count;j++) {
            if(j)(void)putchar(',');row_json(e.element_type,root,length,row_offset(root,length,i,j));
        }
        (void)printf("]}");
    }
    (void)putchar(']');
}
static void semantic_json(const unsigned char *root,size_t length,const Ir8PacketReport *r) {
    (void)printf("{\"format\":\"ir8-stage04-native-readback/1\",\"status\":%" PRIu32 ",\"report\":",r->status);report_json(r);
    (void)printf(",\"root_bytes\":%zu,\"root_alignment\":%zu,\"abi\":",sizeof(struct Ir8Packet_generated_v1),_Alignof(struct Ir8Packet_generated_v1));abi_json();
    (void)printf(",\"census\":");census_json();(void)printf(",\"directory\":");directory_json(root,length);
    (void)printf(",\"objects\":");objects_json(root,length);(void)putchar('}');
}
static void mutation_result(const char *name,unsigned char *copy,size_t length,int dump) {
    Ir8PacketReport report;Ir8PacketStatus status;
    unsigned char *before=(unsigned char *)malloc(length);
    if(before==NULL)die("mutation snapshot allocation");
    (void)memcpy(before,copy,length);
    status=ir8_packet_validate(copy,length,&trusted_bindings,&workspace,&report);
    (void)printf(",{\"name\":\"%s\",\"status\":%" PRIu32 ",\"report\":",name,status);report_json(&report);
    if(dump && status==0) { (void)printf(",\"readback\":");semantic_json(copy,length,&report); }
    (void)putchar('}');
    if(memcmp(before,copy,length)!=0)harness_failures++;
    free(before);
}
int main(void) {
    const unsigned char *root=(const unsigned char *)ir8_packet_generated_data();
    size_t length=ir8_packet_generated_size();
    Ir8PacketReport report,repeated;Ir8PacketStatus status;unsigned char *allocation,*copy;
    if(length!=sizeof(struct Ir8Packet_generated_v1) || length>UINT32_C(4194304))die("getter extent");
    /* Actual untouched generated root is always validated FIRST. */
    status=ir8_packet_validate(root,length,&trusted_bindings,&workspace,&report);
    if(status!=0) { (void)printf("{\"format\":\"ir8-stage04-native-failure/1\",\"report\":");report_json(&report);(void)puts("}");return 1; }
    allocation=(unsigned char *)malloc(length+1);
    if(allocation==NULL)die("bounded copy allocation");copy=allocation+1;
    (void)memcpy(copy,root,length);
    (void)printf("{\"baseline\":");semantic_json(root,length,&report);
    (void)printf(",\"controls\":[");
    status=ir8_packet_validate(root,length,&trusted_bindings,&workspace,&repeated);
    if(status!=0 || @STAGE04_REPORT_COMPARE@)harness_failures++;
    (void)printf("{\"name\":\"repeat-original\",\"status\":%" PRIu32 ",\"report\":",status);report_json(&repeated);(void)putchar('}');
    /* Byte-aligned readable private copy, immutable during validation. */
    mutation_result("byte-aligned-copy",copy,length,0);
    if(memcmp(copy,root,length)!=0)harness_failures++;
    @STAGE04_MUTATIONS@
    (void)printf("],\"support\":{\"workspace_bytes\":%zu,\"report_bytes\":%zu,\"copy_allocation_bytes\":%zu,\"mutation_snapshot_bytes\":%zu,\"expected_bindings_bytes\":%zu},\"harness_failures\":%u}\n",sizeof workspace,sizeof report,length+1,length,sizeof trusted_bindings,harness_failures);
    free(allocation);
    return harness_failures ? 1 : 0;
}
