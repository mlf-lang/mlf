# Benchmark 性能优化交接：2026-10-27

本轮按用户要求收尾：完成已有候选的取舍和相关测试，推送到 PR #25，随后暂停。
**尚未完成全部性能目标；不要把这次推送解读为十项达标。**

## 工作区和目标

- 工作区：`/Users/ares/.codex/worktrees/ce41/mlf`。
- 本地工作分支：`codex/benchmark-performance-recovery`。
- 推送目标：[PR #25](https://github.com/mlf-lang/mlf/pull/25)，分支
  `codex/unsigned-recursion-pr22-20261024`。保留 PR 的 draft 和 base，不合并 PR。
- 起点：`2957dd08321c38dbf94a75cb275a5f48e897f58e`；此前检查点：`24a777e`。
- 原目标：十个原有 workload，各三次样本，完整编译时间 ≤3× C、运行时间 ≤2× C。
  workload、输入、C 实现、C flags、独立输出 oracle 和门槛均未放宽。

详细诊断见 [performance recovery](benchmark-performance-recovery-20261026.md)，
各 cohort 的摘要、范围与 receipt SHA 见
[closeout evidence](benchmark-performance-recovery-evidence-20261027.json)。
下文 `.mlf-build/` 路径相对上述工作区；原始日志和可执行文件保留在本机，未作为源码提交。
已有 receipt 不应覆盖，后续运行使用新的输出目录。

## 已确认的原因与生产改动

1. `83e5c31` 的 canonical standalone facade 会将完整 builtin Prelude 纳入每个
   root 的推断；投影、重新绑定和验证反复处理已有图，成为主要前端成本。
   生产入口现在对符合条件的 standalone root 复用经过独立检查的 builtin 数据；
   原始 source scope、完整 class/instance lowering、用户整体推断和最终 target
   检查仍保留，不符合条件时走普通路径。
2. 既有 Solver 优化保留原始一般算法 fallback，并经过完整图、links、nextId、
   finish 和 LLVM 比较。当前生产 Solver 是 `604662…d960e`；本轮额外的
   `ground-leaf-9` 仍是实验，不能混同为已合入优化。
3. Regex 已有 bounded ASCII DFA/skip/Span 加速，保留一般 Unicode/Thompson
   fallback。本轮接受的 weighted credit 计算同时计入反向比较和 shift lookup；
   Span suffix 增加 ASCII membership table，Unicode 仍用原 `contains`。
   最终生产 Regex SHA256：
   `016cda4d5a9cd2ed0161976ab4150d74c1b2843cb6a5a046aef72eccc1945b0d`。
4. 之前检查点还包括严格求值顺序修复、已知 WHNF 复用、ASCII string lookup、
   String-list primitive、line-buffer/GC 调整及可选 runtime/LLVM/link 并行流水线。
   primitive ABI 是 `mlf-primitive-108-v5`，builtin interface 是 v9；不能混用旧 v8
   产物。生产 concat 仍是 two-pass，streaming join 仍未采用。
5. 正式构建和 direct-test authentication 新增 builtin source identity 与 fresh
   ordinary generation 的逐字节验证。生成数据不能反过来进入 fresh producer closure。
6. imported-library adapter 已注册，生产 registry **仍为 `[]`**，保持普通 fallback。
   `Standalone.normalizeWithScope` 的签名已移至定义前，修复真实 shared parser
   拒绝 GHC 所接受的非相邻签名问题。

## 已完成的验证

| 范围 | 结果与证据 |
| --- | --- |
| 生产 builtin 路径 | `performance-recovery/production-controls-1/receipt.json`：fresh regeneration、33 semantic、36 native O0/O2、46 direct-import、39 context mutation、15 artifact checks；231 input pins 不变 |
| 正式 verifier/provenance | `performance-recovery/builtin-verifier-controls-2/receipt.json`：82 项执行通过，4 项既有 Linux `/proc` 控制在 macOS 跳过；根代理收尾再次运行同一 86 项 suite 通过 |
| 最终生产 Regex suffix | `regex-production-suffix-ghc-93/receipt.json`：70 literal、17 demand、12 scheduler、82,948 differential pairs；`regex-production-suffix-native-94/receipt.json`：56 native O0/O2。未使用 source override；测试仅额外暴露 private helpers |
| imported-library fixture | `prepared-library-fixture-results-3/receipt.json`：33 cases、366 commands、50 interpreter、100 native executions；所有声明的执行模式完成，inputs 不变 |
| fixture 独立重生成 | `prepared-library-fixture-3/regeneration/receipt.json`：新 producer/object/query cache，同一路径 profile 的 5 个输出逐字节一致 |
| benchmark 定义 | `python3 tools/bench/check-migration.py` 通过十项 inventory、pins、flags、fixtures、dependencies、entry paths；这是静态检查，不是性能通过 |
| 收尾语法与差异 | 新增/修改 Python 文件通过 syntax compile，`git diff --check` 通过；未执行的 controller/builder 扩展已归档撤回 |

Regex 的这些 native 程序由 pinned ready-let 诊断编译器产生；这不等于新建
stageA 编译器的完整资格认证。早期失败的 fixture/oracle 收据仍保留，没有改写为通过。

原生 stageA 与独立 postflight 已通过，路径
`performance-recovery/native-prepared-current/revisions/diagnostic-121c/`。
真实 offline lock/locked plan、121-module shared parser、native build、native builtin
fresh verification 均完成；binary 为该目录下 `build/bin/emlf`，SHA256
`8c093562c511143a16640f650812d217609c8d515472883b2b53d777a007be10`。
该 source snapshot 先于最后的 suffix76 库更新，不能标记成整个最终提交的 native
bootstrap 资格；完整 Core/Benchmark campaigns 没有运行。

## 最近的完整流水线结果

`performance-recovery/production-nine-gate-1/run.json` 完成并验证 inputs 未变。
这是 **9 项诊断**，未包含 Regex，也不是最终源码的十项资格测试。使用同一个
生产 GHC compiler 作 candidate/baseline、原 low-latency backend、fresh runtime
objects、streamed LLVM/link；因此只建立对 C 的比较，不建立 candidate/baseline 加速。

| Workload | 完整编译 / C | 运行 / C |
| --- | ---: | ---: |
| binary-trees | 3.3630 | 0.6971 |
| pidigits | 3.1853 | 1.6731 |
| n-body | 5.4297 | 1.2962 |
| fannkuch-redux | 3.2284 | 1.6621 |
| spectral-norm | 3.2557 | 0.9015 |
| fasta | 4.7242 | 1.1839 |
| mandelbrot | 3.4788 | 0.7530 |
| reverse-complement | 3.3124 | 2.5480 |
| k-nucleotide | 5.0847 | 1.6825 |

编译 **0/9**、运行 **8/9**。多数编译卡在 fresh runtime C 的约 0.45–0.47 s；
n-body/fasta/k-nucleotide 的前端另需约 0.702/0.599/0.754 s。
LLVM/link 的 wall interval 含等待，不能与前端/runtime interval 相加。
reverse-complement 的 C wall 为 0.355/0.468/0.909 s，MLF 为
0.384/1.192/1.216 s，输入/hash 相同且可执行文件相同；保留失败结果，原因尚待隔离，
不能凭波动把它算作通过。

隔离重复同一 C/MLF binary 和输入的五对样本得到 wall 0.176312/0.346320 s
（1.964× C），child CPU 0.139992/0.316112 s（2.258× C），输出 hash 全相同。
`performance-recovery/reverse-io-repeat-1/receipt.json` 不替换上述失败的完整流水线结果。

最后的 Regex 三样本对照中，credit54→suffix76：Clang O2 运行
1.514192→1.398310 s（改善 7.65%），生产 helper 2.014418→1.928656 s
（改善 4.26%）；C 为 0.563403 s。最终 suffix 仍分别是 2.482× / **3.423× C**。
LLVM→object 编译代价分别增加约 26 / 6 ms，不能混称为完整编译时间。
证据：`regex-force-screen-pairs-89/receipt.json`、`regex-force-screen-compile-90/receipt.json`。

单独的三次生产 CLI 前端比较已经完成：tree 7.36478→0.290610 s，
n-body 7.80210→0.725261 s，pidigits 7.19062→0.237781 s，LLVM 逐字节相同。
这些是 source→LLVM 数据，**不是完整编译时间**。

新建 native 与此前 GHC production CLI 的后续静默对照，30 次 LLVM 全部逐字节一致：

| Workload | GHC 前端，s | Native 前端，s |
| --- | ---: | ---: |
| binary-trees | 0.252897 | 0.455878 |
| n-body | 0.697612 | 0.925868 |
| pidigits | 0.220272 | 0.437908 |
| fasta | 0.583807 | 0.752508 |
| k-nucleotide | 0.699985 | 0.931667 |

Native 仍慢 1.29–1.99×，不能假设换 native host 就会解决前端门槛。两个 source
snapshot 还差 empty-library 接线和签名邻接修复，不能把差额纯归因于 host。
native build 本身用了 2044.774 s（并行正确性会话，不是公平性能比较）。静态观察：
current LLVM 63.4 MB，最大 entry 约 110,185 行/7.27 MB；原 LLVM 44.5 MB，
相应 entry 约 4,930 行/290 KB。约 0.17–0.23 s 的前端差额和大入口提示 literal
构造/启动值得 profile，但目前没有因果结论。可研究通用的闭合不可变 constructor
literal 静态初始化或有类型边界的构造拆分，必须保留 GC、共享、惰性和分配身份语义。
证据：`performance-recovery/native-frontend-closeout-1/receipt.json`。

## 下轮仍可继续的实验

- **Ground leaf graft**：`performance-recovery/ground-leaf-handoff.json`。
  212 controls 和五个实际 workload 上的新增采纳全部得到相同完整图、links、nextId、
  双 finish、LLVM。最后五项静默计时中 CPU 变化：n-body -3.94%、tree +0.36%、
  pidigits 约不变、fasta +2.64%、k-nucleotide +1.58%，无可信整体收益，因此未推广。
  如继续修改它，仍需当前 production identity 下的维护测试和大
  `Package.Benchmark` 回归。主要剩余形状是顶层 arr/app 匹配、内部 old bottom
  接收新结构；并非 frontier binder equality。幸存 fresh 节点可能真实需要 raise，
  不能简单替换 ID。
- **LLVM force 内联**：全量 AlwaysInliner 改善运行时间，但 LLVM-to-object
  编译由约 0.23 增至 0.55 s；仅保留 force/numeric alwaysinline、allocator 改
  inlinehint 后约 0.45 s。均未推广。更小的 direct-WHNF/one-hop-peek guards
  已通过 IR-only 24 benchmark +72 ABI 控制和独立 C oracle 16 控制，仍需选中
  策略的实际 source compiler build 和完整 demand tests，不能以 IR 实验冒充资格。
- **Completion TU**：`performance-recovery/completion-tu-controls-1/receipt.json`。
  17 个函数 body/representation 不变，original/embedded/split × O0/O2 的
  39 commands、12 native executions 通过；每种模式包含 1,330 completion 和
  20 Async checks。没有生产集成或编译收益结论。后续须使用 fresh O2 objects，
  更新真正流水线/runner 的 stage 和 artifact 记录，保留全部 runtime 支持。
- **库预编译的安装方式**：现有 fixture registry 的 absolute lexical profile
  不能直接作为可移植生产 literal 提交。下一步建议在 build/install 的 canonical
  source 准备阶段，用普通 parser/crate compiler 为明确的库根生成唯一 Data module，
  独立重生成后再普通构建；不修改 live checkout、不使用额外 `-i` shadow。
  不同安装路径重新准备。不要任意替换 target String 路径，也不要增添无信任锚的
  runtime raw-cache loader。详见
  [prepared-libraries README](../tools/experimental/prepared-libraries/README.md)。

## 恢复工作时

先核对 PR head、工作区和已有 receipt；不得把历史二进制重新标记为当前源码产物。
未执行的 `native_controller.py` 大 campaign 和 multi-target builder 扩展已保存到
`performance-recovery/closeout-controller-proposals-1/`，未公开提交；
`build_candidate.py` 已精确恢复 24a。该目录的 `source-transition.json` 记录精确
SHA 和归档，旧四份 seed/native/postflight/builtin receipts 与 binaries 原样保留。
历史 receipt 曾记录的非编译 live driver 路径现在已变化，不能声称这些原路径仍然
fresh，应核对保存的精确字节。缓存接续需要明确的 receipt/source inventory adoption
和真实 lock/plan/build，不能直接套用未执行 controller 的 refresh 状态。
完整 core 35 / benchmark 40 families 与完整 bootstrap 资格尚未执行。

正确性构建最多同时两项；性能测量独占，先确认所有其他 agent/编译进程停止。
优先围绕已测的 runtime C 编译下限、三个慢前端、Regex 的后端取舍继续，最后跑
完整十项三样本 gate。保持 source/ABI/provenance、target checks、错误顺序及原有
workload 定义，不通过修改门槛、删检查或缓存用户程序制造达标。
