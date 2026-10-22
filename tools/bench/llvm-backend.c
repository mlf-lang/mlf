/* One-process LLVM optimizer and object emitter. No source-language shortcuts:
 * the independent MLF checks run before this program receives LLVM IR.
 * Verification runs on both sides of the same generic lite pass pipeline.
 * Keep helpers out of line to bound code expansion; run CSE before combining.
 * O1 keeps optimized register allocation without instruction scheduling cost. */
#include <llvm-c/Analysis.h>
#include <llvm-c/Core.h>
#include <llvm-c/Error.h>
#include <llvm-c/IRReader.h>
#include <llvm-c/Target.h>
#include <llvm-c/Support.h>
#include <llvm-c/TargetMachine.h>
#include <llvm-c/Transforms/PassBuilder.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void fail(const char *stage, const char *message) {
    fprintf(stderr, "mlf-llvm: %s: %s\n", stage, message ? message : "failed");
    exit(1);
}

static void verify(LLVMModuleRef module, const char *stage) {
    char *error = NULL;
    if (LLVMVerifyModule(module, LLVMReturnStatusAction, &error))
        fail(stage, error);
    LLVMDisposeMessage(error);
}

static void attribute(LLVMContextRef context, LLVMValueRef function,
                      const char *key, const char *value) {
    LLVMAddAttributeAtIndex(function, LLVMAttributeFunctionIndex,
        LLVMCreateStringAttribute(context, key, (unsigned)strlen(key),
                                  value, (unsigned)strlen(value)));
}

int main(int argc, char **argv) {
    if (argc != 8 && argc != 9) {
        fprintf(stderr, "usage: mlf-llvm INPUT OUTPUT TRIPLE CPU TUNE FEATURES ABI [ARCHIVE_IR]\n");
        return 2;
    }
    const char *options_argv[] = {"mlf-llvm", "-global-isel=true", "-global-isel-abort=2", "-enable-misched=false"};
    LLVMParseCommandLineOptions(4, options_argv, "");
    if (LLVMInitializeNativeTarget() || LLVMInitializeNativeAsmPrinter())
        fail("initialize", "native target unavailable");
    LLVMContextRef context = LLVMContextCreate();
    LLVMMemoryBufferRef input = NULL;
    LLVMModuleRef module = NULL;
    char *error = NULL;
    if (argc == 9) {
        /* A fresh process can initialize while its producer checks source.
         * The FIFO carries only that build's complete LLVM text; retain an
         * identical regular file before parsing or optimization. */
        if (!freopen(argv[1], "rb", stdin)) fail("open stream", argv[1]);
        if (LLVMCreateMemoryBufferWithSTDIN(&input, &error)) fail("read stream", error);
        FILE *archive = fopen(argv[8], "wb");
        size_t size = LLVMGetBufferSize(input);
        if (!archive) fail("archive stream", argv[8]);
        if (fwrite(LLVMGetBufferStart(input), 1, size, archive) != size || fclose(archive))
            fail("archive stream", argv[8]);
    } else if (LLVMCreateMemoryBufferWithContentsOfFile(argv[1], &input, &error))
        fail("read", error);
    if (LLVMParseIRInContext(context, input, &module, &error))
        fail("parse", error);
    verify(module, "input verification");
    LLVMPassBuilderOptionsRef passes = LLVMCreatePassBuilderOptions();
    LLVMErrorRef pass_error = LLVMRunPasses(module,
        "globaldce,function(early-cse,instcombine,simplifycfg,tailcallelim),globaldce",
        NULL, passes);
    if (pass_error) fail("optimize", LLVMGetErrorMessage(pass_error));
    LLVMDisposePassBuilderOptions(passes);
    verify(module, "optimized verification");
    LLVMTargetRef target = NULL;
    if (LLVMGetTargetFromTriple(argv[3], &target, &error))
        fail("target", error);
    LLVMTargetMachineOptionsRef options = LLVMCreateTargetMachineOptions();
    LLVMTargetMachineOptionsSetCPU(options, argv[4]);
    LLVMTargetMachineOptionsSetFeatures(options, argv[6]);
    LLVMTargetMachineOptionsSetABI(options, argv[7]);
    LLVMTargetMachineOptionsSetCodeGenOptLevel(options, LLVMCodeGenLevelLess);
    LLVMTargetMachineOptionsSetRelocMode(options, LLVMRelocPIC);
    LLVMTargetMachineRef machine = LLVMCreateTargetMachineWithOptions(target, argv[3], options);
    LLVMDisposeTargetMachineOptions(options);
    if (!machine) fail("target", "cannot create target machine");
    LLVMSetTarget(module, argv[3]);
    LLVMTargetDataRef layout = LLVMCreateTargetDataLayout(machine);
    LLVMSetModuleDataLayout(module, layout);
    LLVMDisposeTargetData(layout);
    for (LLVMValueRef f = LLVMGetFirstFunction(module); f; f = LLVMGetNextFunction(f)) {
        attribute(context, f, "target-cpu", argv[4]);
        attribute(context, f, "tune-cpu", argv[5]);
        attribute(context, f, "target-features", argv[6]);
    }
    LLVMSetTargetMachineFastISel(machine, 0);
    LLVMSetTargetMachineGlobalISel(machine, 1);
    LLVMSetTargetMachineGlobalISelAbort(machine, LLVMGlobalISelAbortDisable);
    if (LLVMTargetMachineEmitToFile(machine, module, argv[2], LLVMObjectFile, &error)) {
        remove(argv[2]);
        fail("emit", error);
    }
    LLVMDisposeTargetMachine(machine);
    LLVMDisposeModule(module);
    LLVMContextDispose(context);
    return 0;
}
