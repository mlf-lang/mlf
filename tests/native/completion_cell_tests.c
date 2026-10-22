/* Live native storage proof, intentionally independent of primitive numbers
 * for future Completion support. Uses the real MLF values, closures and GC. */
#include "../../runtime/mlf_completion.h"
#include <stdio.h>
#include <stdlib.h>

static unsigned assertions, callbacks, depth, max_depth, poison_calls;
static MlfCompletionScope *reentrant_scope;
static MlfCompletion *reentrant_cell;
static void require(int condition, const char *message) {
    ++assertions;
    if (!condition) { fprintf(stderr, "completion test: %s\n", message); exit(1); }
}
static void expect(MlfCompletionStatus actual, MlfCompletionStatus wanted,
                   const char *message) {
    if (actual != wanted) {
        fprintf(stderr, "completion test: %s (status %d, expected %d)\n",
                message, (int)actual, (int)wanted);
        exit(1);
    }
    ++assertions;
}
static MlfValue *number(const char *text) { return mlf_integer(text); }
static MlfValue *unit_action(void) { return mlf_prim1(0, mlf_constructor(0, 0)); }
static MlfEnv *capture(MlfValue *value) {
    MlfEnv *env = mlf_env_new(1); mlf_env_set(env, 0, value); return env;
}
static MlfValue *check_integer(MlfEnv *env, MlfValue *result) {
    ++depth; if (depth > max_depth) max_depth = depth;
    GC_gcollect();
    require(mlf_truth(mlf_eq_int(result, mlf_env_get(env, 0))), "integer result/capture survives GC");
    ++callbacks; --depth;
    return unit_action();
}
static MlfValue *check_string(MlfEnv *env, MlfValue *result) {
    ++depth; if (depth > max_depth) max_depth = depth;
    GC_gcollect();
    require(mlf_truth(mlf_prim2(12, result, mlf_env_get(env, 0))), "string result/capture survives GC");
    ++callbacks; --depth;
    return unit_action();
}
static MlfValue *ignore_value(MlfEnv *env, MlfValue *result) {
    (void)env; (void)result; ++callbacks; return unit_action();
}
static MlfValue *poison(MlfEnv *env, MlfValue *argument) {
    (void)env; (void)argument; ++poison_calls;
    fputs("completion test: forced lazy result\n", stderr); exit(1);
}
static MlfValue *resolve_from_callback(MlfEnv *env, MlfValue *result) {
    (void)env; (void)result;
    ++depth; if (depth > max_depth) max_depth = depth;
    unsigned before = callbacks;
    expect(mlf_completion_resolve(reentrant_scope, reentrant_cell, number("88")),
           MLF_COMPLETION_OK, "callback resolves another cell");
    require(callbacks == before, "resolution does not invoke nested callbacks");
    ++callbacks; --depth;
    return unit_action();
}
static MlfCompletion *new_cell(MlfCompletionScope *scope) {
    MlfCompletion *cell = NULL;
    expect(mlf_completion_new(scope, &cell), MLF_COMPLETION_OK, "allocate cell");
    require(cell != NULL && GC_base(cell) != NULL, "cell is traced allocation");
    return cell;
}
static MlfCompletionResume *subscribe(MlfCompletionScope *scope, MlfCompletion *cell,
                                      MlfValue *continuation) {
    MlfCompletionResume *resume = NULL;
    expect(mlf_completion_subscribe(scope, cell, continuation, &resume),
           MLF_COMPLETION_OK, "subscribe");
    require(resume != NULL && GC_base(resume) != NULL, "resumption is traced allocation");
    return resume;
}
static int drain_one(MlfCompletionScope *scope) {
    MlfCompletionResume *resume = NULL;
    MlfCompletionStatus status = mlf_completion_dequeue(scope, &resume);
    if (status == MLF_COMPLETION_EMPTY) return 0;
    expect(status, MLF_COMPLETION_OK, "dequeue");
    GC_gcollect();
    MlfValue *continuation = NULL, *result = NULL;
    expect(mlf_completion_take(scope, resume, &continuation, &result),
           MLF_COMPLETION_OK, "consume claimed callback once");
    require(resume->continuation == NULL && resume->result == NULL && resume->cell == NULL,
            "consumption drops owned payload roots");
    GC_gcollect();
    MlfValue *action = mlf_application(continuation, result);
    require(mlf_run(action, 1) == 0, "coordinator executes ordinary IO resumption");
    expect(mlf_completion_take(scope, resume, &continuation, &result),
           MLF_COMPLETION_CONSUMED, "resumption cannot run twice");
    return 1;
}
static void collect_pressure(void) {
    for (unsigned i = 0; i < 16; ++i) {
        void *allocation = GC_MALLOC(65536);
        require(allocation != NULL, "GC pressure allocation");
        GC_gcollect();
    }
}
static void populate_mixed(MlfCompletionScope *scope) {
    MlfCompletion *integers = new_cell(scope), *strings = new_cell(scope);
    MlfValue *large = number("1234567890123456789012345678901234567890");
    MlfValue *text = mlf_string("retained string", 15);
    subscribe(scope, integers, mlf_closure(check_integer, capture(large)));
    subscribe(scope, strings, mlf_closure(check_string, capture(text)));
    expect(mlf_completion_resolve(scope, integers, large), MLF_COMPLETION_OK, "resolve large integer");
    expect(mlf_completion_resolve(scope, strings, text), MLF_COMPLETION_OK, "resolve string");
    /* Only the scope and its traced graph need remain reachable after return. */
}
static void mixed_gc_and_lazy(void) {
    MlfCompletionScope *scope = mlf_completion_scope_new(3, 3);
    require(scope != NULL && GC_base(scope) != NULL, "scope is traced allocation");
    unsigned before = callbacks;
    populate_mixed(scope);
    require(callbacks == before, "register and resolve do not run user code");
    collect_pressure();
    require(drain_one(scope) && drain_one(scope) && !drain_one(scope), "two mixed callbacks drain");
    require(callbacks == before + 2, "mixed callbacks ran exactly once");
    MlfCompletion *lazy = new_cell(scope);
    subscribe(scope, lazy, mlf_closure(ignore_value, mlf_env_new(0)));
    expect(mlf_completion_resolve(scope, lazy, mlf_thunk(poison, mlf_env_new(0))),
           MLF_COMPLETION_OK, "resolve lazy poison");
    collect_pressure();
    require(drain_one(scope), "ignored lazy result callback runs");
    require(poison_calls == 0, "resolution, collection and dispatch preserve laziness");
    mlf_completion_scope_close(scope);
}
static void once_and_bounds(void) {
    MlfCompletionScope *scope = mlf_completion_scope_new(1, 2);
    MlfCompletion *cell = new_cell(scope), *overflow = NULL;
    MlfCompletionResume *extra = NULL;
    MlfValue *observed = NULL;
    expect(mlf_completion_new(scope, &overflow), MLF_COMPLETION_FULL, "retained cell bound");
    require(overflow == NULL, "failed allocation does not expose a cell");
    expect(mlf_completion_read(scope, cell, &observed), MLF_COMPLETION_EMPTY, "pending read");
    MlfValue *continuation = mlf_closure(check_integer, capture(number("42")));
    MlfCompletionResume *first = subscribe(scope, cell, continuation);
    MlfCompletionResume *second = subscribe(scope, cell, continuation);
    expect(mlf_completion_subscribe(scope, cell, continuation, &extra),
           MLF_COMPLETION_FULL, "pending callbacks reserve bounded capacity");
    expect(mlf_completion_resolve(scope, cell, number("42")), MLF_COMPLETION_OK,
           "resolve cannot fail when queue capacity reserved");
    expect(mlf_completion_resolve(scope, cell, mlf_thunk(poison, mlf_env_new(0))),
           MLF_COMPLETION_ALREADY_RESOLVED, "duplicate resolution preserves first result");
    expect(mlf_completion_read(scope, cell, &observed), MLF_COMPLETION_OK, "read resolved result");
    MlfValue *alias = observed;
    expect(mlf_completion_read(scope, cell, &observed), MLF_COMPLETION_OK, "repeat read");
    require(observed == alias, "repeated reads return same retained value");
    MlfCompletionResume *claimed = NULL;
    expect(mlf_completion_dequeue(scope, &claimed), MLF_COMPLETION_OK, "claim first registration");
    require(claimed == first, "registration order is FIFO");
    expect(mlf_completion_subscribe(scope, cell, continuation, &extra),
           MLF_COMPLETION_FULL, "claimed callback retains reservation");
    expect(mlf_completion_unsubscribe(scope, claimed), MLF_COMPLETION_OK, "cancel claimed callback");
    expect(mlf_completion_unsubscribe(scope, claimed), MLF_COMPLETION_CONSUMED, "cancel once");
    MlfCompletionResume *late = subscribe(scope, cell, continuation);
    expect(mlf_completion_dequeue(scope, &claimed), MLF_COMPLETION_OK, "claim earlier ready callback");
    require(claimed == second, "late registration follows earlier ready callback");
    expect(mlf_completion_unsubscribe(scope, claimed), MLF_COMPLETION_OK, "cancel ready callback");
    expect(mlf_completion_dequeue(scope, &claimed), MLF_COMPLETION_OK, "claim late callback");
    require(claimed == late, "late callback enqueued exactly once");
    expect(mlf_completion_unsubscribe(scope, claimed), MLF_COMPLETION_OK, "cancel late callback");
    require(scope->callbacks == 0 && scope->all_callbacks == NULL && scope->ready_head == NULL,
            "consumed registration list does not grow unbounded");
    mlf_completion_scope_close(scope);
}
static void owner_teardown(void) {
    MlfCompletionScope *owner = mlf_completion_scope_new(3, 5);
    MlfCompletionScope *other = mlf_completion_scope_new(1, 1);
    MlfCompletion *pending = new_cell(owner), *ready = new_cell(owner);
    MlfValue *continuation = mlf_closure(ignore_value, mlf_env_new(0));
    MlfCompletionResume *waiting = subscribe(owner, pending, continuation);
    MlfCompletionResume *claimed = subscribe(owner, ready, continuation);
    MlfCompletionResume *queued = subscribe(owner, ready, continuation), *out = NULL;
    MlfValue *value = NULL, *function = NULL;
    expect(mlf_completion_resolve(other, ready, number("1")), MLF_COMPLETION_WRONG_OWNER, "cross-owner resolve rejected");
    expect(mlf_completion_read(other, ready, &value), MLF_COMPLETION_WRONG_OWNER, "cross-owner read rejected");
    expect(mlf_completion_subscribe(other, ready, continuation, &out), MLF_COMPLETION_WRONG_OWNER, "cross-owner subscribe rejected");
    expect(mlf_completion_resolve(owner, ready, number("1")), MLF_COMPLETION_OK, "resolve before teardown");
    expect(mlf_completion_dequeue(owner, &out), MLF_COMPLETION_OK, "dequeue before teardown");
    require(out == claimed, "claimed registration is tracked through teardown");
    mlf_completion_scope_close(owner);
    mlf_completion_scope_close(owner);
    require(owner->cells == 0 && owner->callbacks == 0 && owner->all_cells == NULL &&
            owner->all_callbacks == NULL && owner->ready_head == NULL && owner->ready_tail == NULL,
            "close clears all scope-owned graph roots once");
    require(ready->result == NULL && pending->waiting_head == NULL &&
            waiting->continuation == NULL && claimed->continuation == NULL && queued->continuation == NULL,
            "close clears pending, queued and claimed roots");
    expect(mlf_completion_take(owner, claimed, &function, &value), MLF_COMPLETION_CLOSED,
           "claimed callback cannot fire after closure");
    expect(mlf_completion_read(owner, ready, &value), MLF_COMPLETION_CLOSED, "stale read rejected");
    expect(mlf_completion_resolve(owner, pending, number("2")), MLF_COMPLETION_CLOSED, "late resolve rejected");
    expect(mlf_completion_subscribe(owner, ready, continuation, &out), MLF_COMPLETION_CLOSED, "late subscribe rejected");
    expect(mlf_completion_dequeue(owner, &out), MLF_COMPLETION_CLOSED, "closed queue cannot drain");
    mlf_completion_scope_close(other);
}
static void non_reentrant_dispatch(void) {
    MlfCompletionScope *scope = mlf_completion_scope_new(2, 2);
    MlfCompletion *first = new_cell(scope), *second = new_cell(scope);
    reentrant_scope = scope; reentrant_cell = second;
    subscribe(scope, first, mlf_closure(resolve_from_callback, mlf_env_new(0)));
    subscribe(scope, second, mlf_closure(check_integer, capture(number("88"))));
    unsigned before = callbacks;
    expect(mlf_completion_resolve(scope, first, number("1")), MLF_COMPLETION_OK, "make first ready");
    require(callbacks == before, "resolution remains cold");
    require(drain_one(scope), "dispatch first callback");
    require(callbacks == before + 1, "second callback stays queued during first");
    require(drain_one(scope), "dispatch second callback");
    require(callbacks == before + 2 && max_depth == 1, "callback dispatch is non-reentrant");
    mlf_completion_scope_close(scope);
    reentrant_scope = NULL; reentrant_cell = NULL;
}
static void remove_pending_and_reuse(void) {
    MlfCompletionScope *scope = mlf_completion_scope_new(1, 3);
    MlfCompletion *cell = new_cell(scope);
    MlfValue *continuation = mlf_closure(ignore_value, mlf_env_new(0));
    MlfCompletionResume *a = subscribe(scope, cell, continuation);
    MlfCompletionResume *b = subscribe(scope, cell, continuation);
    MlfCompletionResume *c = subscribe(scope, cell, continuation);
    expect(mlf_completion_unsubscribe(scope, b), MLF_COMPLETION_OK, "remove middle pending waiter");
    expect(mlf_completion_unsubscribe(scope, a), MLF_COMPLETION_OK, "remove first pending waiter");
    expect(mlf_completion_unsubscribe(scope, c), MLF_COMPLETION_OK, "remove last pending waiter");
    require(cell->waiting_head == NULL && cell->waiting_tail == NULL, "waiter list fully cleared");
    expect(mlf_completion_resolve(scope, cell, number("9")), MLF_COMPLETION_OK, "resolve without waiters");
    for (unsigned i = 0; i < 128; ++i) {
        subscribe(scope, cell, continuation);
        require(drain_one(scope), "reuse bounded callback slot");
        require(scope->callbacks == 0 && scope->all_callbacks == NULL, "no historical callback retention");
    }
    mlf_completion_scope_close(scope);
}
int main(void) {
    mixed_gc_and_lazy();
    once_and_bounds();
    owner_teardown();
    non_reentrant_dispatch();
    remove_pending_and_reuse();
    printf("Native completion representation: %u checks, %u callbacks passed.\n", assertions, callbacks);
    return 0;
}
