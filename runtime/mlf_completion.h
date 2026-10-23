#ifndef MLF_COMPLETION_H
#define MLF_COMPLETION_H

/* Private representation for the opaque typed completion primitives.
 * One coordinator thread owns every operation, including draining resumptions.
 * All objects containing MlfValue pointers use scanned BDWGC allocations.
 * Cells and claimed callbacks retain their owner; no reachable object is freed.
 * Bounds cover retained cells and outstanding callbacks, including callbacks
 * waiting on unresolved cells and callbacks claimed but not yet consumed.
 */
#include "mlf_runtime.h"
#include <gc/gc.h>
#include <stddef.h>
#include <string.h>

typedef struct MlfCompletionScope MlfCompletionScope;
typedef struct MlfCompletion MlfCompletion;
typedef struct MlfCompletionResume MlfCompletionResume;

typedef enum {
    MLF_COMPLETION_OK,
    MLF_COMPLETION_EMPTY,
    MLF_COMPLETION_ALREADY_RESOLVED,
    MLF_COMPLETION_CLOSED,
    MLF_COMPLETION_FULL,
    MLF_COMPLETION_WRONG_OWNER,
    MLF_COMPLETION_CONSUMED,
    MLF_COMPLETION_NO_MEMORY,
    MLF_COMPLETION_BUSY
} MlfCompletionStatus;

enum { MLF_CELL_PENDING, MLF_CELL_RESOLVED, MLF_CELL_CLOSED };
enum { MLF_RESUME_PENDING, MLF_RESUME_READY, MLF_RESUME_CLAIMED,
       MLF_RESUME_TIMER, MLF_RESUME_CONSUMED, MLF_RESUME_CANCELLED };

struct MlfCompletionScope {
    int closed, dispatching;
    size_t cell_limit, callback_limit, cells, callbacks;
    MlfCompletion *all_cells;
    MlfCompletionResume *all_callbacks, *ready_head, *ready_tail, *timer_head, *timer_tail;
};
struct MlfCompletion {
    MlfCompletionScope *owner;
    MlfCompletion *next;
    int state;
    MlfValue *result;
    MlfCompletionResume *waiting_head, *waiting_tail;
};
struct MlfCompletionResume {
    MlfCompletionScope *owner;
    MlfCompletion *cell;
    int state, is_action;
    uint64_t deadline_ms;
    MlfValue *continuation, *result;
    MlfCompletionResume *all_prev, *all_next;
    MlfCompletionResume *wait_prev, *wait_next;
};

static inline void *mlf_completion_allocate(size_t size) {
    void *result = GC_MALLOC(size);
    if (result) memset(result, 0, size);
    return result;
}
static inline MlfCompletionScope *mlf_completion_scope_new(size_t cells,
                                                          size_t callbacks) {
    GC_INIT();
    MlfCompletionScope *scope = mlf_completion_allocate(sizeof(*scope));
    if (scope) { scope->cell_limit = cells; scope->callback_limit = callbacks; }
    return scope;
}
static inline MlfCompletionStatus mlf_completion_owner(MlfCompletionScope *scope,
                                                       MlfCompletion *cell) {
    if (!scope || !cell || cell->owner != scope) return MLF_COMPLETION_WRONG_OWNER;
    if (scope->closed || cell->state == MLF_CELL_CLOSED) return MLF_COMPLETION_CLOSED;
    return MLF_COMPLETION_OK;
}
static inline MlfCompletionStatus mlf_completion_new(MlfCompletionScope *scope,
                                                     MlfCompletion **out) {
    *out = NULL;
    if (!scope || scope->closed) return MLF_COMPLETION_CLOSED;
    if (scope->cells >= scope->cell_limit) return MLF_COMPLETION_FULL;
    MlfCompletion *cell = mlf_completion_allocate(sizeof(*cell));
    if (!cell) return MLF_COMPLETION_NO_MEMORY;
    cell->owner = scope;
    cell->next = scope->all_cells;
    scope->all_cells = cell;
    ++scope->cells;
    *out = cell;
    return MLF_COMPLETION_OK;
}
static inline void mlf_completion_append_ready(MlfCompletionScope *scope,
                                               MlfCompletionResume *resume) {
    resume->state = MLF_RESUME_READY;
    resume->wait_prev = scope->ready_tail;
    resume->wait_next = NULL;
    if (scope->ready_tail) scope->ready_tail->wait_next = resume;
    else scope->ready_head = resume;
    scope->ready_tail = resume;
}
static inline MlfCompletionStatus mlf_completion_resolve(MlfCompletionScope *scope,
                                                         MlfCompletion *cell,
                                                         MlfValue *result) {
    MlfCompletionStatus checked = mlf_completion_owner(scope, cell);
    if (checked != MLF_COMPLETION_OK) return checked;
    if (cell->state == MLF_CELL_RESOLVED) return MLF_COMPLETION_ALREADY_RESOLVED;
    /* Commit before making any callback ready. Resolution allocates nothing
     * and cannot fail due to capacity: registration already reserved slots. */
    cell->result = result;
    cell->state = MLF_CELL_RESOLVED;
    MlfCompletionResume *resume = cell->waiting_head;
    cell->waiting_head = cell->waiting_tail = NULL;
    while (resume) {
        MlfCompletionResume *next = resume->wait_next;
        resume->result = result;
        mlf_completion_append_ready(scope, resume);
        resume = next;
    }
    return MLF_COMPLETION_OK;
}
static inline MlfCompletionStatus mlf_completion_read(MlfCompletionScope *scope,
                                                      MlfCompletion *cell,
                                                      MlfValue **out) {
    *out = NULL;
    MlfCompletionStatus checked = mlf_completion_owner(scope, cell);
    if (checked != MLF_COMPLETION_OK) return checked;
    if (cell->state != MLF_CELL_RESOLVED) return MLF_COMPLETION_EMPTY;
    *out = cell->result;
    return MLF_COMPLETION_OK;
}
static inline MlfCompletionStatus mlf_completion_subscribe(MlfCompletionScope *scope,
                                                           MlfCompletion *cell,
                                                           MlfValue *continuation,
                                                           MlfCompletionResume **out) {
    *out = NULL;
    MlfCompletionStatus checked = mlf_completion_owner(scope, cell);
    if (checked != MLF_COMPLETION_OK) return checked;
    if (scope->callbacks >= scope->callback_limit) return MLF_COMPLETION_FULL;
    MlfCompletionResume *resume = mlf_completion_allocate(sizeof(*resume));
    if (!resume) return MLF_COMPLETION_NO_MEMORY;
    resume->owner = scope;
    resume->cell = cell;
    resume->continuation = continuation;
    resume->all_next = scope->all_callbacks;
    if (scope->all_callbacks) scope->all_callbacks->all_prev = resume;
    scope->all_callbacks = resume;
    ++scope->callbacks;
    if (cell->state == MLF_CELL_RESOLVED) {
        resume->result = cell->result;
        mlf_completion_append_ready(scope, resume);
    } else {
        resume->wait_prev = cell->waiting_tail;
        if (cell->waiting_tail) cell->waiting_tail->wait_next = resume;
        else cell->waiting_head = resume;
        cell->waiting_tail = resume;
    }
    *out = resume;
    return MLF_COMPLETION_OK;
}
static inline MlfCompletionStatus mlf_completion_enqueue(MlfCompletionScope *scope,
                                                         MlfValue *action,
                                                         MlfCompletionResume **out) {
    *out = NULL;
    if (!scope || scope->closed) return MLF_COMPLETION_CLOSED;
    if (scope->callbacks >= scope->callback_limit) return MLF_COMPLETION_FULL;
    MlfCompletionResume *resume = mlf_completion_allocate(sizeof(*resume));
    if (!resume) return MLF_COMPLETION_NO_MEMORY;
    resume->owner = scope;
    resume->is_action = 1;
    resume->continuation = action;
    resume->all_next = scope->all_callbacks;
    if (scope->all_callbacks) scope->all_callbacks->all_prev = resume;
    scope->all_callbacks = resume;
    ++scope->callbacks;
    mlf_completion_append_ready(scope, resume);
    *out = resume;
    return MLF_COMPLETION_OK;
}
static inline void mlf_completion_unlink_wait(MlfCompletionScope *scope,
                                             MlfCompletionResume *resume) {
    MlfCompletionResume **head, **tail;
    if (resume->state == MLF_RESUME_PENDING) {
        head = &resume->cell->waiting_head; tail = &resume->cell->waiting_tail;
    } else if (resume->state == MLF_RESUME_TIMER) {
        head = &scope->timer_head; tail = &scope->timer_tail;
    } else {
        head = &scope->ready_head; tail = &scope->ready_tail;
    }
    if (resume->wait_prev) resume->wait_prev->wait_next = resume->wait_next;
    else *head = resume->wait_next;
    if (resume->wait_next) resume->wait_next->wait_prev = resume->wait_prev;
    else *tail = resume->wait_prev;
    resume->wait_prev = resume->wait_next = NULL;
}
/* Timer registrations reserve the same bounded callback capacity. The sorted
 * timer list is FIFO for equal deadlines; maturation never invokes user code. */
static inline MlfCompletionStatus mlf_completion_delay(MlfCompletionScope *scope,
                                                       uint64_t deadline_ms,
                                                       MlfValue *action,
                                                       MlfCompletionResume **out) {
    MlfCompletionStatus status = mlf_completion_enqueue(scope, action, out);
    if (status != MLF_COMPLETION_OK) return status;
    MlfCompletionResume *resume = *out;
    mlf_completion_unlink_wait(scope, resume);
    resume->state = MLF_RESUME_TIMER;
    resume->deadline_ms = deadline_ms;
    MlfCompletionResume *before = scope->timer_head;
    while (before && before->deadline_ms <= deadline_ms) before = before->wait_next;
    resume->wait_next = before;
    resume->wait_prev = before ? before->wait_prev : scope->timer_tail;
    if (resume->wait_prev) resume->wait_prev->wait_next = resume;
    else scope->timer_head = resume;
    if (before) before->wait_prev = resume;
    else scope->timer_tail = resume;
    return MLF_COMPLETION_OK;
}
static inline void mlf_completion_mature(MlfCompletionScope *scope, uint64_t now_ms) {
    if (!scope || scope->closed) return;
    while (scope->timer_head && scope->timer_head->deadline_ms <= now_ms) {
        MlfCompletionResume *resume = scope->timer_head;
        mlf_completion_unlink_wait(scope, resume);
        mlf_completion_append_ready(scope, resume);
    }
}
static inline void mlf_completion_retire(MlfCompletionScope *scope,
                                         MlfCompletionResume *resume,
                                         int state) {
    if (resume->all_prev) resume->all_prev->all_next = resume->all_next;
    else scope->all_callbacks = resume->all_next;
    if (resume->all_next) resume->all_next->all_prev = resume->all_prev;
    resume->all_prev = resume->all_next = NULL;
    resume->continuation = resume->result = NULL;
    resume->cell = NULL;
    resume->state = state;
    --scope->callbacks;
}
static inline MlfCompletionStatus mlf_completion_unsubscribe(MlfCompletionScope *scope,
                                                             MlfCompletionResume *resume) {
    if (!scope || !resume || resume->owner != scope) return MLF_COMPLETION_WRONG_OWNER;
    if (scope->closed) return MLF_COMPLETION_CLOSED;
    if (resume->state >= MLF_RESUME_CONSUMED) return MLF_COMPLETION_CONSUMED;
    if (resume->state != MLF_RESUME_CLAIMED) mlf_completion_unlink_wait(scope, resume);
    mlf_completion_retire(scope, resume, MLF_RESUME_CANCELLED);
    return MLF_COMPLETION_OK;
}
static inline MlfCompletionStatus mlf_completion_dequeue(MlfCompletionScope *scope,
                                                         MlfCompletionResume **out) {
    *out = NULL;
    if (!scope || scope->closed) return MLF_COMPLETION_CLOSED;
    MlfCompletionResume *resume = scope->ready_head;
    if (!resume) return MLF_COMPLETION_EMPTY;
    mlf_completion_unlink_wait(scope, resume);
    resume->state = MLF_RESUME_CLAIMED;
    *out = resume;
    return MLF_COMPLETION_OK;
}
static inline MlfCompletionStatus mlf_completion_take(MlfCompletionScope *scope,
                                                      MlfCompletionResume *resume,
                                                      MlfValue **continuation,
                                                      MlfValue **result) {
    *continuation = *result = NULL;
    if (!scope || !resume || resume->owner != scope) return MLF_COMPLETION_WRONG_OWNER;
    if (scope->closed) return MLF_COMPLETION_CLOSED;
    if (resume->state != MLF_RESUME_CLAIMED) return MLF_COMPLETION_CONSUMED;
    /* Caller must retain both outputs through creation of its ordinary MLF IO
     * resumption. No allocation/callback happens between copying and clearing. */
    *continuation = resume->continuation;
    *result = resume->result;
    mlf_completion_retire(scope, resume, MLF_RESUME_CONSUMED);
    return MLF_COMPLETION_OK;
}
static inline void mlf_completion_scope_close(MlfCompletionScope *scope) {
    if (!scope || scope->closed) return;
    scope->closed = 1;
    MlfCompletionResume *resume = scope->all_callbacks;
    while (resume) {
        MlfCompletionResume *next = resume->all_next;
        resume->state = MLF_RESUME_CANCELLED;
        resume->continuation = resume->result = NULL;
        resume->cell = NULL;
        resume->all_prev = resume->all_next = NULL;
        resume->wait_prev = resume->wait_next = NULL;
        resume = next;
    }
    MlfCompletion *cell = scope->all_cells;
    while (cell) {
        MlfCompletion *next = cell->next;
        cell->state = MLF_CELL_CLOSED;
        cell->result = NULL;
        cell->waiting_head = cell->waiting_tail = NULL;
        cell->next = NULL;
        cell = next;
    }
    scope->all_cells = NULL;
    scope->all_callbacks = scope->ready_head = scope->ready_tail = NULL;
    scope->timer_head = scope->timer_tail = NULL;
    scope->cells = scope->callbacks = 0;
}
#endif
