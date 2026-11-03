#ifndef RIR_ALLOCATION_OBSERVER_H
#define RIR_ALLOCATION_OBSERVER_H

/* Include real allocator declarations before the runtime-only lexical macros.
 * This observer's own translation unit must NOT use those macros. */
#include <stdlib.h>
#include "rir_runtime.h"

void *rir_observer_malloc(size_t size);
void *rir_observer_calloc(size_t count, size_t size);
void rir_observer_free(void *pointer);
/* Called once, after the wrapper returned and serialized its evaluation report.
 * Writes allocation-observer.json in the process's explicit build-directory cwd.
 * The report and all pointers it contains must remain externally valid. */
void rir_observer_report(const RtReport *report);

#endif
