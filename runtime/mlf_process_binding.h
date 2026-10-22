/* Private primitive-82 transport. Requests and replies are NUL-separated UTF-8
 * fields, never shell commands or pointers. Replies contain bounded metadata;
 * process stdout/stderr go directly to files/inherited streams, not memory. */
#ifndef MLF_PROCESS_BINDING_H
#define MLF_PROCESS_BINDING_H
#define MLF_PS_REQUEST_LIMIT (1024u * 1024u)
#define MLF_PS_FIELD_LIMIT 4096u

typedef struct { char bytes[512]; size_t length; } MlfProcessReply;
/* Per-interpreter-entry checkpoints preserve outer native/interpreted scopes.
 * Only integer metadata is retained here; there are no MLF callbacks/values. */
typedef struct MlfProcessScopeRecord {
    mlf_process_scope scope;
    uint64_t serial;
    struct MlfProcessScopeRecord *next;
} MlfProcessScopeRecord;
static MlfProcessScopeRecord *mlf_ps_records;
static uint64_t mlf_ps_serial;
static void mlf_process_binding_clear(void) {
    while (mlf_ps_records) {
        MlfProcessScopeRecord *record=mlf_ps_records;
        mlf_ps_records=record->next; free(record);
    }
}
static void mlf_ps_forget_scope(mlf_process_scope scope) {
    MlfProcessScopeRecord **at=&mlf_ps_records;
    while (*at) {
        if ((*at)->scope==scope) { MlfProcessScopeRecord *record=*at; *at=record->next; free(record); return; }
        at=&(*at)->next;
    }
}
static void mlf_ps_reply_field(MlfProcessReply *reply, const char *field) {
    size_t n = strlen(field) + 1;
    if (n > sizeof(reply->bytes) - reply->length) fail("process supervisor reply overflow");
    memcpy(reply->bytes + reply->length, field, n); reply->length += n;
}
static void mlf_ps_reply_int(MlfProcessReply *reply, int64_t value) {
    char number[32]; snprintf(number, sizeof(number), "%" PRId64, value);
    mlf_ps_reply_field(reply, number);
}
static void mlf_ps_reply_uint(MlfProcessReply *reply, uint64_t value) {
    char number[32]; snprintf(number, sizeof(number), "%" PRIu64, value);
    mlf_ps_reply_field(reply, number);
}
static int mlf_ps_parse_uint(const char *text, uint64_t maximum, uint64_t *value) {
    if (!*text) return 0;
    uint64_t n = 0;
    for (const unsigned char *p = (const unsigned char *)text; *p; ++p) {
        if (*p < '0' || *p > '9') return 0;
        uint64_t digit = (uint64_t)(*p - '0');
        if (n > maximum / 10 || (n == maximum / 10 && digit > maximum % 10)) return 0;
        n = n * 10 + (*p - '0');
    }
    *value = n; return 1;
}
static int mlf_ps_parse_wait(const char *text, double *seconds) {
    uint64_t n;
    if (!strcmp(text,"-1")) { *seconds = -1; return 1; }
    if (!mlf_ps_parse_uint(text,UINT32_MAX,&n)) return 0;
    *seconds = (double)n / 1000.; return 1;
}
static int mlf_ps_parse_handle(char **fields, mlf_process_handle *handle) {
    uint64_t slot;
    return mlf_ps_parse_uint(fields[0],UINT64_MAX,&handle->scope) &&
        mlf_ps_parse_uint(fields[1],UINT64_MAX,&handle->generation) &&
        mlf_ps_parse_uint(fields[2],UINT32_MAX,&slot) && (handle->slot=(uint32_t)slot,1);
}
static void mlf_ps_reply_handle(MlfProcessReply *r, mlf_process_handle h) {
    mlf_ps_reply_uint(r,h.scope); mlf_ps_reply_uint(r,h.generation); mlf_ps_reply_uint(r,h.slot);
}
static void mlf_ps_reply_outcome(MlfProcessReply *r, const mlf_process_outcome *o) {
    mlf_ps_reply_int(r,o->kind); mlf_ps_reply_int(r,o->exit_code);
    mlf_ps_reply_int(r,o->launch_error); mlf_ps_reply_int(r,o->cleanup_error);
    mlf_ps_reply_int(r,o->cancel_reason);
}
static MlfValue *mlf_process_request(MlfValue *request) {
    MlfValue *text = expect(request,STRING);
    MlfProcessReply reply = {{0},0};
    mlf_process_status status = MLF_PROCESS_INVALID_ARGUMENT;
    char **fields = NULL, *copy = NULL;
    size_t count = 0, n = text->as.string.length;
    if (!n || n > MLF_PS_REQUEST_LIMIT || text->as.string.bytes[n-1]) goto finished;
    copy = allocate(n);
    memcpy(copy,text->as.string.bytes,n);
    fields = allocate((MLF_PS_FIELD_LIMIT + 1) * sizeof(*fields));
    for (size_t at=0; at<n;) {
        if (count == MLF_PS_FIELD_LIMIT) goto finished;
        fields[count++] = copy+at; at += strlen(copy+at)+1;
    }
    if (count < 2 || strcmp(fields[0],"MLF-PROCESS-1")) {
        status=MLF_PROCESS_UNSUPPORTED; goto finished;
    }
    const char *op = fields[1];
    if (!strcmp(op,"version") && count==2) {
        status=MLF_PROCESS_OK; mlf_ps_reply_int(&reply,status); mlf_ps_reply_int(&reply,1);
    } else if (!strcmp(op,"checkpoint") && count==2) {
        status=MLF_PROCESS_OK; mlf_ps_reply_int(&reply,status); mlf_ps_reply_uint(&reply,mlf_ps_serial);
    } else if (!strcmp(op,"finish") && count==4) {
        uint64_t checkpoint,mode;
        if (!mlf_ps_parse_uint(fields[2],mlf_ps_serial,&checkpoint) ||
            !mlf_ps_parse_uint(fields[3],1,&mode)) goto finished;
        status=MLF_PROCESS_OK;
        while (mlf_ps_records && mlf_ps_records->serial>checkpoint) {
            mlf_process_scope scope=mlf_ps_records->scope;
            mlf_process_status closed=mlf_process_scope_close(scope,(mlf_process_close_mode)mode);
            mlf_ps_forget_scope(scope);
            if (closed) status=closed;
        }
    } else if (!strcmp(op,"shutdown") && count==2) {
        mlf_process_shutdown(); mlf_process_binding_clear(); status=MLF_PROCESS_OK;
    } else if (!strcmp(op,"create") && count==5) {
        uint64_t jobs,pending,retained; mlf_process_scope scope;
        if (!mlf_ps_parse_uint(fields[2],UINT32_MAX,&jobs) ||
            !mlf_ps_parse_uint(fields[3],UINT32_MAX,&pending) ||
            !mlf_ps_parse_uint(fields[4],UINT32_MAX,&retained)) goto finished;
        mlf_process_options options={(uint32_t)jobs,(uint32_t)pending,(uint32_t)retained};
        if (mlf_ps_serial==UINT64_MAX) goto finished;
        status=mlf_process_scope_create(&options,&scope);
        if (!status) {
            MlfProcessScopeRecord *record=allocate(sizeof(*record));
            record->scope=scope; record->serial=++mlf_ps_serial;
            record->next=mlf_ps_records; mlf_ps_records=record;
            mlf_ps_reply_int(&reply,status); mlf_ps_reply_uint(&reply,scope);
        }
    } else {
        uint64_t scope;
        if (count<3 || !mlf_ps_parse_uint(fields[2],UINT64_MAX,&scope)) goto finished;
        if (!strcmp(op,"close") && count==4) {
            uint64_t mode;
            if (!mlf_ps_parse_uint(fields[3],1,&mode)) goto finished;
            status=mlf_process_scope_close(scope,(mlf_process_close_mode)mode);
            if (status==MLF_PROCESS_OK || status==MLF_PROCESS_SYSTEM_ERROR) mlf_ps_forget_scope(scope);
        } else if (!strcmp(op,"cancelScope") && count==4) {
            uint64_t reason;
            if (!mlf_ps_parse_uint(fields[3],INT_MAX,&reason)) goto finished;
            status=mlf_process_cancel_scope(scope,(int)reason);
        } else if ((!strcmp(op,"poll") && count==3) || (!strcmp(op,"wait") && count==4)) {
            double wait=0; mlf_process_event event;
            if (count==4 && !mlf_ps_parse_wait(fields[3],&wait)) goto finished;
            status=mlf_process_wait_next(scope,wait,&event);
            if (!status) { mlf_ps_reply_int(&reply,status); mlf_ps_reply_handle(&reply,event.handle); mlf_ps_reply_outcome(&reply,&event.outcome); }
        } else if ((!strcmp(op,"await") || !strcmp(op,"cancel")) && count==7) {
            mlf_process_handle handle;
            if (!mlf_ps_parse_handle(fields+3,&handle)) goto finished;
            if (!strcmp(op,"await")) {
                double wait; mlf_process_outcome outcome;
                if (!mlf_ps_parse_wait(fields[6],&wait)) goto finished;
                status=mlf_process_await(scope,handle,wait,&outcome);
                if (!status) { mlf_ps_reply_int(&reply,status); mlf_ps_reply_outcome(&reply,&outcome); }
            } else {
                uint64_t reason;
                if (!mlf_ps_parse_uint(fields[6],INT_MAX,&reason)) goto finished;
                status=mlf_process_cancel(scope,handle,(int)reason);
            }
        } else if (!strcmp(op,"submit") && count>=14) {
            uint64_t environment,running,total,argc,envc;
            if (!mlf_ps_parse_uint(fields[8],1,&environment) ||
                !mlf_ps_parse_uint(fields[9],UINT32_MAX,&running) ||
                !mlf_ps_parse_uint(fields[10],UINT32_MAX,&total) ||
                !mlf_ps_parse_uint(fields[11],MLF_PS_FIELD_LIMIT,&argc) || !argc ||
                12+argc>=count || !mlf_ps_parse_uint(fields[12+argc],MLF_PS_FIELD_LIMIT,&envc) ||
                13+argc+envc!=count || (!environment && envc)) goto finished;
            char **argv=allocate((argc+1)*sizeof(*argv)), **env=allocate((envc+1)*sizeof(*env));
            for (size_t i=0;i<argc;++i) argv[i]=fields[12+i];
            for (size_t i=0;i<envc;++i) env[i]=fields[13+argc+i];
            mlf_process_spec spec={fields[3],(const char *const *)argv,fields[4],fields[5],fields[6],fields[7],
                (mlf_process_environment)environment,environment ? (const char *const *)env : NULL,(double)running/1000.,(double)total/1000.};
            mlf_process_handle handle;
            status=mlf_process_submit(scope,&spec,&handle);
            free(argv); free(env);
            if (!status) { mlf_ps_reply_int(&reply,status); mlf_ps_reply_handle(&reply,handle); }
        }
    }
finished:
    if (!reply.length) { mlf_ps_reply_int(&reply,status); if (status) mlf_ps_reply_field(&reply,mlf_process_status_string(status)); }
    free(fields); free(copy);
    return mlf_string(reply.bytes,reply.length);
}
#endif
