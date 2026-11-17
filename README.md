# UNTESTED dependency-v12 preparation archive

This branch is an archive-only snapshot of work based on PR #51 commit `db7edc6900ee70aba6c65d5eb4db69029a0c7b82`. It is not a complete repository tree and must not be merged directly into main or the PR branch.

The four Python files preserve the prepared dependency-only ABI137-v12 test-reader maintenance. The original 0..131 reader pins and historical 131→133 adapter remain intact. The new layer is intended to accept only the five explicitly named Prelude exports through code 136, with two-way identity and duplicate-binding checks. Source inspection was completed, but these files have not been executed or qualified.

The separate extra-test text is a proposed additional synthetic closure/association test. It was not inserted into the test source, executed, or independently reviewed as final code. Synthetic tests are not native artifact admission or full compiler CI qualification.

Local execution became unavailable before validation. No test result is inferred from this archive. PR #51 and main are unchanged by this backup, and this tree contains no GitHub workflow files. Restore only the intended source files into a normal exact-head checkout, review the complete change, run the bounded tests, and then follow exact-head CI before publication to the PR.
