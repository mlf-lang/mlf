/* Exercise the actual force helper emitted by each compiler, using values
 * constructed independently through the public runtime ABI. In particular,
 * forcing a constructor/closure must not demand its fields/environment. */
#include "mlf_runtime.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <gc/gc.h>

extern MlfValue *mlf_force_generated(MlfValue *);
static unsigned thunk_calls, application_calls;

static void check(int good, const char *message) {
    if (!good) { fprintf(stderr, "%s\n", message); exit(2); }
}

static MlfValue *poison(MlfEnv *env, MlfValue *argument) {
    (void)env; (void)argument;
    check(0, "force demanded a lazy field or capture");
    return NULL;
}

static MlfValue *saved(MlfEnv *env, MlfValue *argument) {
    (void)argument;
    ++thunk_calls;
    return mlf_env_get(env, 0);
}

static MlfValue *identity(MlfEnv *env, MlfValue *argument) {
    (void)env;
    ++application_calls;
    return argument;
}

static MlfValue *recursive(MlfEnv *env, MlfValue *argument) {
    (void)argument;
    return mlf_force_generated(mlf_env_get(env, 0));
}

static void success(void) {
    MlfValue *lazy = mlf_thunk(poison, NULL);
    MlfEnv *fields = mlf_env_new(3);
    for (unsigned i = 0; i < 3; ++i) mlf_env_set(fields, i, lazy);
    MlfValue *values[] = {
        mlf_integer("-17"), mlf_integer("4611686018427387904"),
        mlf_boolean(0), mlf_boolean(1), mlf_constructor(0, 0),
        mlf_double(1.25), mlf_string("ready", 5),
        mlf_closure(poison, fields), mlf_native_io(poison, fields),
        mlf_constructor1(1, lazy), mlf_constructor2(2, lazy, lazy),
        mlf_constructor_fields(3, fields), mlf_constructor(4, 3),
        mlf_primitive(8)
    };
    unsigned count = sizeof(values) / sizeof(values[0]);
    for (unsigned i = 0; i < count; ++i) {
        check(mlf_force_generated(values[i]) == values[i], "ready value changed");
        MlfValue *hole = mlf_hole();
        mlf_fill(hole, values[i]);
        check(mlf_force_generated(hole) == values[i], "completed indirection changed");
    }
    MlfEnv *env = mlf_env_new(1);
    mlf_env_set(env, 0, values[6]);
    MlfValue *thunk = mlf_thunk(saved, env);
    MlfValue *application = mlf_application(mlf_closure(identity, NULL), thunk);
    MlfValue *chain = application;
    for (unsigned i = 0; i < 20000; ++i) {
        MlfValue *hole = mlf_hole();
        mlf_fill(hole, chain);
        chain = hole;
    }
    GC_gcollect();
    check(mlf_force_generated(chain) == values[6], "long lazy spine changed");
    check(mlf_force_generated(thunk) == values[6], "memoized thunk changed");
    check(mlf_force_generated(application) == values[6], "memoized application changed");
    check(mlf_force_generated(chain) == values[6], "memoized spine changed");
    check(thunk_calls == 1 && application_calls == 1, "evaluation was not memoized");
    MlfValue *cycle = mlf_hole();
    MlfValue *constructor = mlf_constructor1(5, cycle);
    mlf_fill(cycle, constructor);
    check(mlf_force_generated(cycle) == constructor, "recursive data changed");
    check(mlf_force_generated(mlf_field(constructor, 0)) == constructor, "recursive field changed");
    printf("{\"ready_values\":%u,\"spine_length\":20000,\"thunk_calls\":%u,\"application_calls\":%u}\n",
           count, thunk_calls, application_calls);
}

int main(int argc, char **argv) {
    check(argc == 2, "force probe needs one mode");
    if (!strcmp(argv[1], "success")) { success(); return 0; }
    if (!strcmp(argv[1], "null")) (void)mlf_force_generated(NULL);
    else if (!strcmp(argv[1], "hole")) (void)mlf_force_generated(mlf_hole());
    else if (!strcmp(argv[1], "indirection-cycle")) {
        MlfValue *a = mlf_hole(), *b = mlf_hole();
        mlf_fill(a, b); mlf_fill(b, a);
        (void)mlf_force_generated(a);
    } else if (!strcmp(argv[1], "thunk-cycle")) {
        MlfEnv *env = mlf_env_new(1);
        MlfValue *thunk = mlf_thunk(recursive, env);
        mlf_env_set(env, 0, thunk);
        (void)mlf_force_generated(thunk);
    }
    check(0, "force probe did not reject invalid demand");
    return 2;
}
