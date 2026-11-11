# Astra 协作冲刺：完整 compiler 编译接近 GHC

## 目标、责任和时间

本轮由 Astra 负责设计协作、认领分工、调整优先级、分配机器窗口、审查证据和决定候选去留。主会话负责向用户传达结果和需要用户决定的事项，不代替 Astra 做日常技术调度。

启动日期：2026-11-10。用户提出三天冲刺目标，但没有约定精确到分钟的截止时间。恢复后不得重新计算三天或宣称已连续运行了未实际运行的时间。事件时间和完成状态见 [机器可读检查点](astra-sprint-20261110.json)。

最终目标仍是约 1× GHC，不能改成 3×。本轮不保证三天达标。禁止恢复 native A/B 自举或 fixed-point 长 campaign；GHC-hosted MLF 产出一份 runnable compiler 的性能端点，与下一代自举固定点是不同任务。

## 冻结的测量边界

- 共同基线：`f9bdb40a659bfdff4cbb782d438afbb0417dd2e1`。
- 当前完整 `MLF.Entry.Emlf` 递归共享源码闭包：90 模块、5,233,364 字节；不能沿用历史硬编码 81 模块。
- 比较同一 frozen workload，fresh target 起点，到 runnable compiler（含链接）的终点。MLF 是 ordinary GHC-built compiler；GHC 直接编译相同90模块和原有 Main wrapper。
- MLF 当前 full-compiler 路径把闭包编译为一个 fresh crate，并非 mlfpkg 按 package 构建流水线。结果只能描述这条路径，不包装成所有构建方式的最优倍率。
- 固定 primitive/host adapters、builtin/runtime 等依赖可按清单复用；目标 query、推断结果和 target objects 不得复用。生成的 builtin 模块是目标源码的一部分，不能只在 MLF 侧跳过。
- 工具链：GHC 9.14.1、Debian Clang 19.1.7、GMP/BDWGC；ordinary O2、单 job；精确工具和输入身份由每次 receipt 认证。
- 保留既有 600秒完整端点、5GiB进程树RSS、6GiB每进程地址空间、5GiB磁盘和3GiB主机可用内存保护。触发保护时保存失败，不通过提高限制或删检查制造成功。
- 旧 11-02 的 7.157× 是旧快照、每端两次的描述性结果，不是当前基线。小程序、14模块screen、C benchmark 和 native-host/GHC-host 比率均不代替本目标。

## 协作结构与任务认领

借鉴 [多代理团队文章](https://claude.dev/blog/safely-scaling-multi-agent-teams-with-fable-5-2/) 的独立工作区、明确任务所有权、依赖拆分和可检查的交付物，不照搬1000人规模。本轮共享一台约9.7GiB内存的云机器，编码和只读审查可并行，重构建和计时串行。下方按时间保留的事件段是历史记录，不能把旧段的“在途/未运行/未发布”当成最新状态；恢复时以最后一节及配套JSON为准。

| ID | 责任方向 | 独占源码范围 | 交付物 | 前提 |
| --- | --- | --- | --- | --- |
| B0 | 基线与证据 | 测量harness，不改生产算法 | 当前MLF/GHC完整端点资格、精确artifact/receipt、普通基线cohort | 工具链与producer认证 |
| B1 | 制品和后端 | 当前只有 backend-stages 诊断工具 | 小crate预检、当前完整checked输入分段诊断、ordinary LLVM原始字节一致 | B0可用checked artifact、资源令牌 |
| F1/F2/F3 | 前端和Graph优化 | 生产Graph.hs；实验独立分支 | Type memo已停止；F2小候选正确性已通过；F3语义、代表码形、普通Graph样本及完整ordinary producer通过；真实11模块Q通过，C进行中 | R2语义审查、B0普通码形证据、资源令牌 |
| R1（停止） | legacy调用内复用实验 | Bootstrap.CrateQuery、Bootstrap.CrateSession | 仅保留可恢复实验；已确认不在当前端点调用链上，不再安排producer/计时 | 不作为当前优化候选 |
| R2 | 当前graph边界定位 | 私有诊断中的CrateSession、CrateGraph | 真实IO返回/每SCC进度事件，与F1共用一次有界诊断 | 与F1固定接口、资源令牌 |
| M0/M1 | 基线与证据 | 冻结测量配置 | 基线和每个已符合条件候选的fresh、配对、ordinary端点 | B0成功；相应候选完成控制 |
| I1 | Astra集成与复核 | 单一集成分支 | 逐项纳入可接受改动、组合正确性/性能复测、最终差距 | 各候选的独立证据 |

每个任务只有一个当前负责人。需要改别人所有的owner时先协调，不互相覆盖。新发现要附精确源身份、输入、机制、已完成/未完成检查。候选任务失败或被否决属于正常终态，不阻塞其他合格候选的测量。分支和准确提交以检查点JSON为准。

## 资源令牌与执行节奏

1. 重任务开始前由 Astra 确认唯一令牌持有者。不要仅凭本shell的ps判断全机空闲：不同执行环境的进程视图可能不同。
2. 所有新重任务使用同一个共享排他锁，并保留各harness原有锁。锁作用域必须覆盖整个构建/测量cohort；失败时先确认子进程已回收，再释放令牌。
3. B0已先后完成MLF-native失败资格与GHC-native成功资格。资格数据不并入正式样本；MLF资格开头可能与一次约3秒控制有重叠，保留说明。
4. 当前MLF资格已在600.099秒触发wall保护，无checked/LLVM产物；GHC资格outer为155.931809537秒。完整倍率仍不可用。B1小main资格与F1/R2单次120秒计数定位都已完成。后续markers和P1诊断均已完成；当前F3语义门及普通码形门状态见末节和JSON，R1停止排期。完整90模块目标不变，小输入不顶替目标。
5. 之后正式样本由B0方向统一排队。这个队列可按真实阻塞调整，不能让无输入任务占着机器。
6. 不允许长时间同时构建多个内存重候选。没有令牌时继续源码审查、控制设计、文档与轻量git保存。
7. 中断的cohort保持不完整，不能拼接重启前后样本充当原定完整对照。新的cohort必须新目录、新计划；不要覆盖旧receipt。

共享锁的具体机器路径在恢复后由 Astra 为所有任务统一设置，而不是复制上次机器的绝对路径。建议外层使用 `flock -n`，不支持时用等价的、经过检查的进程级排他锁。现有本地目录锁本身不证明跨worktree互斥。

## 当前候选的边界

### F1：已停止的kindOf memo候选；转向当前raw-infer定位

单次调用内缓存成功kind结果；原算法作为诊断参考。已有O0/O2有限环境、菱形和需求/首错控制，但没有当前真实热点或性能收益证据。原计划对完整输入记录 roots、recursive_visits、unique_variable_roots、max_visits_per_root、roots_with_repeats，再核对checked原始字节与group身份。当前B0在产出checked前超时，因此先设计可在运行中读到计数及真实IO边界的有界诊断；完整输出验证仍是后续必需项。计数不是CPU份额。2026-11-10的唯一120秒诊断已提供停止依据：最后119.098秒快照完成956个fresh SCC，kindOf根调用1,590,641次，递归变量访问620,367次与每根去重求和完全相等，重复根为0、最大15访问/根。末段SCC持续推进，未卡在单一SCC。该证据只覆盖插桩前缀，不是全程序断言或普通CPU占比；本轮已停止memo候选，不追加微基准，并将生产Type恢复基线，保留原补丁和失败证据。新的前端任务是和R2共同分析实际raw-infer/query成本。

### B1：checked到LLVM分段诊断

链接未经修改的认证ordinary O2 producer对象，只编译诊断入口/host运输代码。阶段为load/decode/link/checked traversal、constructor table、erase、owned optimizer、representation、codegen、write。边界采用OPAQUE并保留嵌套bottom控制。String visitor只强制表示和scalar length，不声称逐字节扫描底层Text或offset index。

必须先小crate跑通，再拿当前完整artifact，要求fresh ordinary emission与诊断LLVM原始字节一致、marker完整有序、输入/工具pins前后相同。强制遍历、保留中间值和改变求值顺序会扰动GC；分段值仅作定位，不能相加充当ordinary成本或直接宣称加速。Build.result、capture/demand扫描等只是静态假设，尚未采用。

### R1：已停止的legacy调用内datatype context编码/hash复用

2026-11-10路径核查确认：当前 --compile-crate 经 CrateSession.compileGraphSources/compileGraphLocked 调用 CrateGraph.compile/compileLoweredIn，不经过R1修改的legacy writeSourceRecord路径。R1不适用于当前90模块端点，不能宣称会提速；完整producer/性能排期已撤销。该方向转为R2，协助F1定位当前graph路径。下述仅记录隔离实验的机制和恢复状态。

只在一次compiler调用内保留一个最多1MiB的不可变编码；更大对象走原路径。每个group仍保留destination检查、read-byte-compare、repair和staging/publication检查，不缓存目标编译结果。

两owner overlay只是窄语义gate，不是完整producer。完整性能对照必须普通build.py构建独立候选、产生自己receipt，不能借用baseline身份。所有已知corruption/missing repair、publication错误和需求/首错行为继续受控。

## 首轮检查点（历史记录；最新状态见末节和JSON）

- B0 MLF：600.09899221秒wall保护退出（-9）；采样峰值1,745,485,824字节；无完成stage/checked/LLVM。父进程wait4的0.235秒CPU未包含被终止compiler子进程，不能冒充完整任务CPU。
- 失败目录存在query-graph-v2及generations/results/staging子目录，仅文件是lock；payload到最终publish才写，不能据此认定未开始推断。
- B0 GHC：完整90模块加Main fresh、链接和version/identity检查通过，outer155.931809537秒；这只是单次资格，不是正式配对cohort。
- B1：远端 OPAQUE 修订 daa88b69cce840843d9e1197f6b1993d6580af9c；小main完整runner现已通过：5个目标group全fresh，128,805字节LLVM与fresh ordinary逐字节相等，26 nested与2 total forcing控制及独立native输出通过。后续源码/证据保存版本见JSON。全量诊断仍等待完整checked输入。
- F1/R2：组合诊断采用只读快照线程，每2秒flush数值计数与真实IO边界；不遍历/强制编译器AST。F1负责Counters/Main/Type和唯一构建/运行，R2负责私有Session/Graph边界。一次120秒、仅定位，不声称完整语义等价。
- 任何running状态只表示记录当时状态，恢复时必须重新核验进程、锁及产物。

## 三天阶段与验收

- 第一天：获得当前可运行端点或明确失败证据，定位主要成本，筛掉没有实际覆盖的候选。资源准备耗时如实记录。
- 第二天：并行开展少量高价值机制实验，串行控制与ordinary对照，及时保存独立分支。单项收益不能相加；正点估计不是稳定或普遍提速的保证。
- 第三天：停止扩展范围，冻结集成版本，做完整端点普通复测与关键语义回归。交付真实时间、MLF/GHC比率、阶段/资源、失败项、未完成资格和下一瓶颈。

正式对照预先固定输入、输出边界、采样顺序、样本数与统计量，保留所有样本。不要反复补样直到变好。fresh、warm和incremental分开。ordinary未插桩数据用于性能结论；诊断及资格只说明各自范围。不得删除source/target checks、改oracle、放宽语义或把有限检查说成完整发布资格。

## 重启后的恢复步骤

1. 从远端本分支取回本文件与JSON，记录具体commit；读取每个候选远端分支的准确commit和README。不要依赖任何会话记忆或旧机器临时目录。
2. Astra先核对用户后续指令：目标、暂停的native A/B/fixed-point、当前授权和三天预算有没有变化。本文不是替代用户新指令的长期许可。
3. 清点机器CPU/RAM/磁盘、现存进程、工具链及资源守卫。旧检查点里的running一律转为“需核验”；不能假设进程仍活着，也不能直接重跑可能尚在执行的动作。
4. 在独立worktree检出冻结baseline和候选提交，核对clean状态与owner范围。按基线恢复文档重新准备官方工具链、认证producer与fixed dependencies。旧绝对路径及旧机器二进制不能充当新机可用证明。
5. 重新计算完整闭包，并核对冻结90模块/5,233,364字节的输入hash；若为新源版本，应建立新的明确cohort，不改写旧基线。
6. 验证保全artifact的原始字节、receipt和源码/工具身份。未上传的二进制、缓存和本地raw logs不是已持久化证据，丢失时重新构建/重测并注明，不能仅凭摘要继续性能结论。
7. 建立跨worktree共享锁，确认所有方向都遵守后，按JSON里依赖与下一动作恢复。先处理阻碍，不启动被暂停的固定点。
8. 每个重要检查点更新本分支JSON/文档并从GitHub读回核验。用户需要决策时明确行动、目标、风险和选项；一般调度由Astra直接完成。

## 保存和发布边界

本分支仅保存协作设计、可恢复任务状态及公开项目证据；不含凭据、会话token或个人路径。实验分支不等于已经通过验收，不自动合并main或触发发布。不能将远端计划保存成功说成候选已完成。精确保存版本由Git提交固定，检查点引用的分支应同时记录commit以防漂移。

## 已核验远端恢复入口

- 基线工具链、冻结90模块清单与失败/成功资格位于独立分支 codex/full-compiler-baseline-20261110，提交 305914c90e8fdff3a912faa6b93c08146273cf3e。请使用 [该提交的README](https://github.com/mlf-lang/mlf/blob/305914c90e8fdff3a912faa6b93c08146273cf3e/tools/performance/full-compiler/baseline-20261110/README.md)，当前计划分支不包含其新增文件。
- 前端原始实验checkpoint：perf/frontend-20261110，提交 64ee679848211034a3cb1e2c1b44f8f600861ab0；[恢复README](https://github.com/mlf-lang/mlf/blob/64ee679848211034a3cb1e2c1b44f8f600861ab0/tools/performance/type-kind-memo/README.md)。该版本保存原始完整计数方案和memo控制，当前调度已改为F1/R2单次120秒组合诊断；不能按旧README盲跑完整600秒。组合方案后续提交以JSON为准。
- R1隔离实验已备份到 perf/compiler-reuse-20261110，提交 d2ee44d84370d41cda90fb921e5af8c11dac677a；[恢复README](https://github.com/mlf-lang/mlf/blob/d2ee44d84370d41cda90fb921e5af8c11dac677a/tools/performance/source-context-write-reuse/README.md)。它仍因不覆盖当前调用链而停用，不恢复producer/性能排期，也没有完整认证通过声明。

## 联合诊断完成后的调度（2026-11-10 13:50 UTC）

F1/R2第二个输出目录中的唯一完整120秒诊断已结束；第一个目录只是harness路径冲突，未运行完整诊断，原失败保留。诊断harness完成、compiler未完成：按120.126秒wall上限退出，所有受管子进程已回收，两层锁已重新验证空闲。80个快照只用于定位，无checked参考/最终产物，不当成普通性能样本。已停止Type memo；R2核对实际query/raw-infer路径；B0核查是否可复用现有QueryGraph阶段统计；B1只读评估受支持的分crate构建策略能否保持同一90模块、所有target fresh和同一runnable终点。备选策略必须另立实验，不能改写原单crate600秒失败。

联合诊断源码和原始快照已保存到远端76d366c676ffe78976588b6b74a2858fd33557d6，完整tree为78a27fc00df9d2589d447223aae4f5e199c509fc，与本机27efb8ff0e817fffd16d87c6759dfcf3174492f2完全一致；已fetch、完整diff为空并回读README。该46文件检查点保留80快照、原失败01、生产Type恢复及停止memo说明。[恢复README](https://github.com/mlf-lang/mlf/blob/76d366c676ffe78976588b6b74a2858fd33557d6/tools/performance/type-kind-memo/README.md)。新的markers-only方案另行实现，不能把旧controls或已完成120秒结果当作新方案通过。

## 下一次低扰动定位的准入（2026-11-10 14:07 UTC）

Astra已批准F1统一实现一次markers-only诊断，R2复核已有成功/失败路径和安全身份来源。生产Type保持冻结基线原字节，移除每根/每次访问计数和诊断专用优化限制，使用ordinary完整flags；controls使用独立对象目录。baseline receipt未记录host.o/supervisor.o的内容hash，因此不能直接声称这两个对象已经认证。新harness按原receipt的完整C编译命令/固定源/flags在私有目录重建，逐字节核对原对象并记录新pins，再仅传入.o链接。现有MLF_QUERY_PROFILE保持关闭，避免重复计时；其六槽最终汇总把raw需求和raw编码合并，不能替代此次按组定位。

每组只严格复制已由原prepared payload编码消费的有界owner信息，不投影可能仍惰性的sourceNode，不让reporter持有AST或thunk。身份包含运行源码身份、started ordinal、数字owner IDs和截断名称预览；不把截断名称当完整稳定身份。每组开始清空current，成功finish后保留last_completed。总SCC数在自然遍历结束前保持unknown，不提前求length。

现有IO marker之间用单调时钟累计四个已闭合需求wall窗口：prepared-record、raw-await、raw-record和finish；另报当前未闭合窗口age，仅保留最慢五组的有界身份。这些窗口包含GC和惰性残留，不是独占CPU份额或普通速度。小controls先验证零状态、窗口闭合、身份清空、未闭合age和top-five有界性，再允许一次最多120秒定位；构建600秒与现有资源守卫不变。当前只批准准备和该次有界运行，没有新增已完成性能证据。

main已合并#50至fc300bc9fdc389b585cbef0630fc8915d53e89c5；变化限于工具/CI/契约/文档，没有修改冻结90模块、host或runtime源码。当前诊断仍严格使用f9bdb40，不把旧producer重标成新main；最终集成需新建并认证相应build-driver身份。

## 后端小输入恢复资料（2026-11-10 14:16 UTC）

B1已保存并取回验证到perf/llvm-builder-20261110@b0144b0d66dd0806d5a00ec4eb9b0b920de1db67，tree为49d13cd1daa6926b8876acf157eef28369b79e33。[提交入口](https://github.com/mlf-lang/mlf/commit/b0144b0d66dd0806d5a00ec4eb9b0b920de1db67)。此次只新增/更新Smoke源码、恢复脚本、README和公开摘要，不含原始receipts、LLVM实体、内部绝对路径或完整tool/object清单。摘要保留精确receipt SHA，但hash不能恢复内容；如果本机原始证据丢失，需要重新执行并建立新资格，不能宣称完整raw证据已持久化。

已只读确认官方GHC安装自带profiling依赖库，支持-prof/-fprof-late，无需另装。Astra已要求准备下一层成本中心诊断草稿，尚未授权其构建或运行；只有当前markers-only结果仍不足时才准入。现有ordinary -rtsopts=ignoreAll不能直接追加-p取得报告。任何profiling会改变ABI/分配/成本，不作普通样本；外guard先终止则可能没有报告，不能放宽保护等待。当前唯一重任务仍为F1的markers-only控制/构建/单120秒运行。

## 低扰动定位完成（2026-11-10 14:21 UTC）

markers-only唯一运行已在120.480秒guard上限退出，compiler未完成；79快照，最后119.372秒时已开始957组、完成956个fresh组，reused为0、总数仍未知。尾端持续推进，非一个SCC卡死。已闭合的诊断wall需求窗口为raw-demand 91.767875213秒（956组）、prepared-record 4.654154082秒（957组）、raw-record 5.167865594秒（956组）、finish 1.074966639秒（956组）。最慢完成SCC为ordinal834，46个成员，span5.973414824秒，其中raw窗口5.102921896秒；后四个span约3.251、2.015、1.961、1.463秒。成本分散在许多组，不能称为某个Solver热点、普通CPU百分比或生产提速。

C对象重建逐字节认证、helper控制、输入post-pins均通过；这是一次构建和一次完整有界尝试，没有失败重试。子进程已回收，内外锁验证空闲。新源码/证据的远端持久化尚待核验，当前数字是结果摘要；不能仅凭摘要声称raw receipts仍可取回。下一步优先审查完整原CLI的late cost-centre诊断草稿，而非继续增加粗标签。96字符stable-name预览可能只容纳公共前缀，不能假称能从它唯一还原源函数；数字owner IDs需要精确源版本下的实际映射。

## 新直接干预候选：同90模块的fresh分crate策略（2026-11-10 14:25 UTC）

Astra将下一优先级调整为B2：使用现有公开--compile-crate协议，按原包边界将冻结90模块分为9个library slice和6模块entry，全部从空target构建，最后仍使用普通whole-program checked→LLVM→Clang→runnable入口。9库模块数分别为14、4、11、6、11、2、13、21、2，连entry共90；模块源码、exports和生产manifest不改，固定复用仅限B0原已允许的builtin/runtime等依赖。当次先前slice产物属于目标工作，其生成成本全部计入同一个600秒总端点，不能变成每库各600秒。现成mlfpkg --target emlf会编98模块，不能拿它与GHC90作同工作量比较。

该候选目前只有源码层面的可行性，尚无完整可执行产物或速度结果。B1方向负责实现独立调度harness，F1独立复核模块并集/唯一归属/哈希/依赖拓扑、新artifact身份与预算；先做小型真实分crate语义控制，再另行准入一次完整资格。所有失败和策略差异明确保留，不能覆盖原单crate600秒失败或声称生产算法已经变快。

暂停边界继续保守：不运行可能属于native A/B、代际或固定点验证的整套check_native.py。仅做不构成自举代际A/B的独立小crate语义fixture和CLI资格，并记录实际命令，不把这些检查说成完整compiler语义验收。完整原CLI late-profiler草稿继续准备和审查，但尚未编译/运行。

markers-only的9文件新源码/结构化快照检查点尚未获准公开上传，已知create_tree未执行且已停止。当前远端76d366c仍是前一个含Type计数的诊断。新的markers摘要已在本计划保全，但raw及新runner恢复状态要以JSON中确切remote_commit为准，不能假称其已push。

## B2小控制通过、完整资格在途（2026-11-10 14:48 UTC）

B2执行代码在perf/fresh-split-20261110@135a31331713baad0ddc4c22a09fd0ea312dc258，源码tree和10文件已取回核验；小控制摘要另保存到9c0bea5847b995334e3bdd2b588509d45f0111e1，执行代码未变。[恢复入口](https://github.com/mlf-lang/mlf/blob/9c0bea5847b995334e3bdd2b588509d45f0111e1/tools/performance/fresh-split/README.md)。小控制唯一运行5.160891106秒，采样进程树峰值178,864,128字节，三个crate分别3/2/2组全部fresh。原生输出、私有导出拒绝、类型错误拒绝、缺直接依赖拒绝及同位置完好副本先等价再损坏的SHA拒绝全部通过。原始receipt未公开，摘要明确不能从hash恢复raw内容。

Astra已准入并启动一次完整90模块fresh split资格，仍一组600秒总保护；截至本节时间没有完整结果，不应当作性能成功。重启后先查实际进程和receipt，不自动重跑。下一步按真实阶段和失败/成功结果决定优化，不自动开启正式cohort或被暂停的代际验证。

测量细节已据B0源码更正：GHC的155.931809537秒Runner到Clang产物完成及worker退出，CLI检查另在外侧，不包含其中。B2记录原Runner起点到Clang完成的时间，另列CLI、两项独立语义检查及整个资格scope；Clang标记与旧worker退出存在小的运输边界差异，应保留原时间戳，在正式比较时统一边界，不从单次资格宣称精确配对提速。

## B2完整资格失败，转P1成本定位（2026-11-10 14:59 UTC）

B2在原600.039880246秒wall保护下结束，第7库mlf-crates未完成。此前6库、59模块、2807组全fresh并通过各自接口检查，但没有entry、whole-program LLVM、Clang、CLI或最终独立语义结果，因此没有runnable时间/倍率。6个已闭合compile合计346.093917351秒，6次show接口合计0.684103539秒；最后约252.8775535秒主要是仍在途的crates编译，不应将已闭合stage与总wall的差额误算成包装开销。采样峰值1,008,721,920字节。不重试、不延长，也不把该策略视为已解决速度目标。

原guard的瞬间终端记录保留未改。独立精确任务进程核验无残留，两锁空闲，117个固定输入pins和18个已完成artifact pins均未变。原始receipts/部分artifact是否持久化以对应分支明确说明为准。

P1私有工具v2.1已完成独立静态复审，Astra现在只准入一次构建：完整原CLI95个home模块使用-prof ABI，600秒总build保护；成功后另行准入60秒控制，真实90秒内部/120秒外层诊断仍需单独决定。不会因为静态review通过就声称profiling工具已经可运行。它不恢复native A/B、代际验证或固定点。

## P1实证与新优化分工（2026-11-10 15:35 UTC）

P1完整95-home-module构建通过（320.047秒，峰值2,115,162,112字节）；六项控制在13.585秒内全部通过，包括真实正常/超时报告、实际POSIX持锁和活跃子进程取消清理，以及拒绝普通124退出或硬杀无报告。随后唯一完整90模块目标的有界诊断成功落盘：internal-timeout 90.2385秒、exit124、fresh有效89,395 ticks，报告89.39秒、约91.303GB分配；外scope98.475秒，峰值1,784,209,408字节。compiler未完成，这不是ordinary样本。子进程/锁清理通过。

证据指向Constraint.solvePrepared继承34.34%采样时间、Graph.Solver.instantiateExpandedPrepared25.32%、unifyPreparedFallback16.24%、Graph.unify12.11%、denseValidation9.51%。这些继承行重叠，不能相加；GC自占20.37%、PROFILING自占6.77%，safe FFI/子进程覆盖也有限，不能将比例当成普通CPU份额或预言提速。

F2由前端方向独占Graph.hs，B1方向独立复核。当前窄补丁只消除densePlace中非零graft成功路径已经完整执行过的第二次parents遍历，保留首次验证、graft0、失败和需求次序；尚未执行控制或证明收益。freeze区间表仅为备选，不混入patch。densePlaces全局继承仅0.630%，重复部分更小，不为该小机制直接安排完整compiler构建；同时只读考察更大的denseValidation/denseKind成本。

R3由query方向独占Graph/Solver.hs，B0方向独立复核。bitmap-seen提案已停用：其直接lookup宽松上界仅0.649%总ticks，且还含其他lookup，额外bitmap插入可能抵消。未执行控制或计时，生产Solver已恢复f9，归档保存到db68c774ae1d5919c4c5e28e62f9d6aca28c0017。下一步只读研究instantiateExpandedPrepared/fallback中同一操作内可能重复的已完成工作，不删除验证、扩缓存生命周期或改public API。

P1安全恢复checkpoint位于[fa7df4c39897a7dad4d21a44087c5927a12dc8d4的README](https://github.com/mlf-lang/mlf/blob/fa7df4c39897a7dad4d21a44087c5927a12dc8d4/tools/performance/full-compiler/late-profile-20261110/README.md)，四份源码与实际测试owners逐字相同，fetch树一致。只有源码、SHA清单和脱敏摘要持久化；13MB raw profile、完整receipts和binary未公开保存。B2失败摘要另已保存并取回验证到e0fa831b3d4cbd395f4d381dbebcb216ebc58365，原失败结论不变。

## Graph候选与恢复状态更新（2026-11-10 16:13 UTC）

markers-only九文件检查点已依具体公开许可保存并完整取回核验：perf/frontend-20261110@33bed9fb4073877ac5589097abf34a3fbac0d1f9，tree3cbb6096a8b5269f74c85289ad6736647efd870b。[恢复README](https://github.com/mlf-lang/mlf/blob/33bed9fb4073877ac5589097abf34a3fbac0d1f9/tools/performance/graph-markers/README.md)。此前的发布阻塞已解除；源码及79个结构化快照持久化，原始command/guard receipts仍仅本机，不能由hash恢复。

F2仅省去非零graft成功路径的重复parents回放。第01次门因测试代码布局语法错误停止，第02次因二进制与日志目录同名停止，两次都没有执行语义controls，失败证据保留。最小修正经独立复核后，第03次单240秒scope在34.714秒退出0：O0/O2均通过12000个validation、5616个public unify、1433个实际成功rebind及16条graft-parent边、480个Int64布局、20个需求/错误和6个alias控制。pins、C重建字节一致与清理通过。没有跑bench或完整producer，没有速度结论。[F2恢复版本6c53a64a](https://github.com/mlf-lang/mlf/blob/6c53a64a28230d3afa5c10f378d683473b930d74/tools/performance/dense-place/README.md)已取回核验，保留为独立未合并小候选。

Solver较大路径审查没有发现可以安全省掉的大块重复prepare/projection。unify前后验证对应不同图，不能复用旧证书删验证。bitmap候选继续停用，不用微小覆盖消耗完整compiler预算。

新的直接证据来自认证ordinary O2对象：Graph.readDense入口仍分配56字节，writeDense入口64字节，readDense有66个实际直接跳转，同时部分caller已经展开。P1中readDense为72字节/SCC entry，说明profiling确实放大，但不能把所有包装都称为剖析假象。这只是静态代码形状，不是动态频次、可省总分配或速度证明。Host Base的pure/bind和Primitive别名已经内联，故不盲改Base、pseq或编译flags。

F3在独立精确f9分支perf/graph-read-fusion-20261110只把34个函数中的54个饱和readDense调用按原body原位展开为readSTArray array(identity-low)。Graph SHA为fdb9e899392ac0068f9f11432d512d1168934455a6da733a10e7cabb52d19df3。公开helper、部分应用、所有write和F2补丁均不改；共享语法不支持INLINE类pragma，因此不增加pragma或改变parser。54处变换可精确逆回f9，独立语义审查通过。

F3唯一O0/O2语义门已通过，总240秒保护下实际41.017秒，bench=0；除了原有固定控制，21个实际改变路径的读需求控制和120个已验证有效图normalize对照均通过。控制审查已纠正共享<=先需parent cell的实际顺序；120个normalize对照不声称覆盖全部normal分支。pins、C对象原命令重建字节一致、producer复认证及子进程/两锁清理均通过。没有运行codegen、bench或完整producer；源码和脱敏结果已独立保存并取回核验：[F3恢复版本7d03b4c6](https://github.com/mlf-lang/mlf/blob/7d03b4c6278317f743311392d5d4cc3606ab1bc0/tools/performance/graph-read-fusion/README.md)，tree69b5d18ee1611a8d67141df6dfc02015eb12afbe。8文件含patch、可逆54点清单、已测controls/runner和脱敏摘要，raw receipts仍仅本机。

后续普通码形门由B0独立准备、R2复核，最多180秒，必须同原模块名Bootstrap.Graph、同ordinary O2 flags和认证依赖，不能用改名语义oracle对象证明生产码形。公开readDense入口理应仍在，必须看真实caller的跳转与heap分配是否消失或仅迁移。语义门通过及锁清理后才另行准入；短ordinary计时、11模块诊断切片和完整producer均未在此授权。若后来构建完整候选，须正常GHC --make重编接口fingerprint影响的反向依赖，不能只换Graph.o混链旧Solver/Constraint冒充完整candidate。当前仍没有合格完整MLF端点或提速倍率；native代际A/B与固定点继续暂停。

## 普通码形通过，首次短样本仍未产生（2026-11-10 16:41 UTC）

F3原名Graph代码生成第01次捕获因GHC -c接口搜索布局失败，未编译出baseline或candidate对象；原失败保留。仅把已认证接口复制到各侧-hidir，经独立差异复审后第02次在24.718秒完成，两份receipt、输入/输出pins和清理均通过。重编baseline Graph.o及Graph.hi与原ordinary producer逐字节相同，建立了真正可比的第三锚。

独立Core/Cmm复核确认代表性denseChild1到denseContains成功三读路径的局部静态分配由352降至176字节，不是只删除符号或把闭包搬到caller；仅构造但不执行action则由96增至104字节。densePlace action入口168降至120字节，其他入口不一定减少。.text由346382增至354814字节，约增2.43%。readDense直接跳转66降至0只是辅证，不能代表54处等量收益或动态调用次数。writeDenseInt源码虽未改，直接跳转也从41降至11，不能把旧profile写侧覆盖再全部当作增量机会。

[码形恢复检查点d79f7492](https://github.com/mlf-lang/mlf/blob/d79f7492c3b051d4cc14c1e2ae594d86a31f852e/tools/performance/full-compiler/graph-read-codegen-20261110/README.md)已远端逐文件和本机fetch全树核验。Python为已测原字节；公开shell仅参数化机器锁路径，明确未执行，原shell身份保留。没有公开raw dumps、完整receipts或对象。

唯一F3-samples-01短普通Graph尝试在60.740秒wall保护下停止，首次binary尚未启动：warmups和samples均为空，无法给中位数或比率。只知道停在初始状态save与预检结束save之间，不能指认具体hash或函数；已排除源码中的重复同锁等待。全post-pins未达，仅六个关键小文件后验身份吻合，不能冒称完整认证。子进程清理和两锁释放通过。原执行脚本、计划和脱敏失败摘要已保存并取回核验到[221764d0的恢复README](https://github.com/mlf-lang/mlf/blob/221764d065a0ac0db9314073478fa4b14e00fcd7/tools/performance/graph-read-fusion/README.md)，raw receipts仍只在本机。

下一版目前仅获准实现和静态审查，没有第二轮执行许可：本次只运行既有O2 binary，不执行GHC或producer，因此区分历史构建来源与实际执行闭包。固定原语义/码形receipt身份，保留当前binary、源/fixture及测量harness前后pins，并验证实际ELF loader与解析运行库；不再声称本次重认证未使用的整套GHC安装、旧对象和raw dumps。旧gate没有记录完整LD环境且脚本拼接未知尾部，不能假称清理后仍为原环境。新环境应明确固定，先用同一个O2 binary重跑原七行语义controls作为独立runtime资格，成功后再同环境运行原32批、两warmup和ABBAABBA八样本，全部仍在一个60秒scope内。保留阶段状态、失败和所有样本；不pilot、缩N或补样追逐好结果。

截至本节，没有任何普通编译器提速被验证或合并，当前完整MLF/GHC倍率仍不可用。B0单crate和B2同源分crate600秒失败都保持不变，GHC155.931809537秒只是一次资格。语义通过、静态分配减少、内部诊断比例和失败的零样本尝试都不能代替速度结果。下一步先取得可信小样本，再决定是否值得普通完整candidate构建与同边界复测；目标仍约1×GHC，native代际A/B与fixed-point继续暂停。

## 首个普通局部结果与下一真实编译门（2026-11-10 16:53 UTC）

F3-samples-02在29.452074332秒内完整通过。明确的新runtime下原七行语义controls耗时0.339976448秒并通过，随后两次warmup及预先固定ABBAABBA八样本全部完成，25个输入pins、实际ELF运行库映射/字节、后验及进程/锁清理均通过。没有构建、RTS变化、删样、pilot、补样或调整32批输入。

八条wall依次为2.914547461、2.620056983、2.597147202、4.398374533、3.762157255、2.946048692、2.236740465、2.457958738秒。基线中位3.338352358秒，候选2.6086020925秒，candidate/base为0.781404，描述性耗时降低约21.9%；几何均值比0.784236，两块比值约0.728571和0.844155。每侧只有4条，波动明显，不能当稳定普遍收益承诺。该harness计时含启动、选集、ID改名、Graph操作和完整序列化，不是纯unify成本、完整编译器速度或MLF-native速度。弱字符和仅证明消费及弱一致，不能替代先前精确语义门。

[已测新runner和完整脱敏样本检查点9c9d2fe0](https://github.com/mlf-lang/mlf/blob/9c9d2fe08afcbca11774279d269286ed4deda118/tools/performance/graph-read-fusion/README.md)已取回完整tree和README核验；旧649脚本及零样本失败01保留，raw receipts和机器路径未公开。这是本轮第一份普通局部性能结果，尚没有可确认的完整compiler提速或新的MLF/GHC倍率。

Astra准入下一阶段的准备而非执行：F1用正常完整manifest的GHC --make -fforce-recomp构建独立ordinary候选producer，生成自己的receipt，不把Graph.o换入旧Solver/Constraint反向依赖冒充完整candidate；具体600秒构建窗口待实际命令/范围审查。B0准备原冻结f9的inference11模块source→checked切片，历史99.039秒/780fresh组仅作容量参考，不充新样本，也不将切片换成candidate修改后的目标源码。切片始终不是完整90模块或GHC对照。

格式源码核查后的初始正确性门为.mlfci、.mlfco和.queries三个公开产物原始字节一致，保留相同crate id、源和依赖路径/顺序，仅fresh cache/output目录变化。早期依据legacy Q.queryKey猜测queries必随compiler digest改变的推断已撤回：当前QueryGraph rawNode hash描述内容，compiler digest绑定cache generation；不能预先放宽public query比较。任何不一致先停解释，不事后忽略字段。native代际A/B和fixed-point仍暂停。


## 完整候选已资格，真实编译对照进行中（2026-11-10 17:41 UTC）

F3正常完整ordinary producer在317.4046秒内通过原600秒保护，137个shared模块和4个host模块正常强制重编，13个程序建立完整新receipt。不是将Graph.o换入旧反向依赖。原builder、checker和verifier均未修改，CLI版本/身份、42与Unicode正例及Int/String类型负例通过；202个pins、实际进程清理和两锁释放通过。

构建前的两个实质阻塞已通过受支持路径解决。首先，原builtin verifier会创建新session子进程，不能让只监原pgrp/session的runner冒充完整资源保护；本轮改用仓库已有、可按PPID及PID启动身份追踪跨session后代的resource_watchdog，限额不变。其次，Graph属于官方56源builtin-source身份闭包，Graph修改必须产生新identity。独立候选只替换canonical文件唯一RawPrelude身份字段，事前明确为未验证派生候选；随后原check-candidate及fresh-literal真的执行成功，2,220,407字节实际生成stdout逐字节等于候选canonical，逆替换identity后整文件精确恢复f9原字节。因此现在有真实生成核验证据，绝未用旧identity、跳过gate或把手改字段先称为生成成功。

[完整producer恢复检查点7f580a70](https://github.com/mlf-lang/mlf/blob/7f580a7087266f27d928196add2ea5e44fc79952/tools/performance/graph-read-fusion/producer-plan.md)已在perf/graph-read-producer-20261110保存。完整tree b890098711bf81d1106558a0ec484557b744b613及五文件，包括canonical源码，均已通过连接器逐字节回读。计时静默期间没有运行本机fetch；这是远端全内容核验，不冒称本机fetch完成。完整binary、原始receipts和运行依赖不在该公开检查点内，丢失后须重建重新资格。

真实inference11门固定原f9的11模块、515,309字节、原5个依赖及其顺序。候选程序改变不改变被编译的目标源码。Q01只在启动层失败：裸python3交给os.execv导致找不到程序，未进入controller或编译。原失败保留；仅将同一Python解析为绝对路径，经独立差异复审后以全新Q02运行。Q02在212.283秒内通过，A为107.053秒、B为101.709秒，均是资格时间，不充正式样本。每腿780 fresh、0 reused，.mlfci、.mlfco和.queries三产物原始字节逐一等于历史B2及彼此。show-crate、query锁、421个输入pins、8个输出pins、实际runtime后验和清理通过。

Astra已另行准入并实际启动唯一C01正式切片对照：固定ABBA四腿，600秒总保护、每compile最多180秒，无额外warmup。全部源、五依赖、producer、runtime、Q双receipt及controller/launcher身份固定。前三项raw oracle和780 fresh门每腿都必须通过，四腿和最后pins完成之前不形成结果。观察时已完成的前两腿96.666秒与151.642秒波动明显，不能据部分数据判断收益或原因；全部保留，不删样、不补样、不续接重启前后结果。C即使完成也只描述11模块source→checked切片，不是完整90模块source→runnable或MLF/GHC倍率。

更大热点的只读筛选继续进行，但不挤占计时窗口。重绑定末尾整map构造只占旧profile约0.321% ticks/0.520% allocation，直接复用还可能改变惰性需求和修复错误缓存计数的语义，未进入CPU队列。当前QueryGraph已有encoded bytes、raw hash和contract复用，剩余双编码覆盖很小；CRC饱和调用只保留静态线索，不启动完整producer。GHC nursery调查仅核实默认4MiB和现有ignoreAll契约；没有ordinary GC计数，也没有调参或提速结论，下一步如需要先独立取得普通统计。任何host RTS结果都不外推MLF-native。

当前没有已合并的本轮性能收益，也没有完整current MLF/GHC倍率。单crate与split的600秒失败保留；目标仍接近1×GHC，不保证三天达到。native代际A/B和fixed-point继续暂停。恢复时先核C01真实结束状态及锁/进程，不能因本节写“进行中”就再启动一份。


## 真实11模块ABBA完成：本轮不支持提速（2026-11-10 17:45 UTC）

C01在462.613秒内完整结束，按预先固定ABBA保留全部四条wall：A96.666402、B151.642281、B104.524868、A104.961783秒。candidate/base中位比1.270493、几何均值比1.249875，两侧各2次。该cohort不支持真实slice提速；不能删去较慢B、补样追求更好数字，或用Q的107.053/101.709秒替换正式样本。Graph小harness约21.9%耗时下降不代表这个真实编译负载。

四腿对应wait4 user为93.387880、153.728915、101.349673、101.551000秒，system为3.584719、4.775379、3.233474、3.548310秒。较慢B也有更高的已记录user CPU，不能只解释成空等。没有采集CPU频率、节流或宿主竞争证据，原因仍未知。各腿最大单进程RSS为380.09、361.90、361.63、380.18MB；外guard峰404.6MB，最低可用RAM9.194GB、磁盘48.334GB，未逼近资源限制，但这不能证明没有其他环境影响。

正确性和执行证据全部成立：每腿780 fresh/0 reused，三个公开产物逐字节等原B2并彼此一致，show-crate/query锁检查通过；423个输入pins、16个输出pins及实际runtime后验通过。22个命令无残留后代，末次RSS0，两锁独立重获。完整outer receipt SHA为2708239e20b1af91f428892e412259d589a01d1220a29c94db5010753d3c86b2，work SHA为ecfd8d9fec6d6096f55776dec188a6da81a81fb41f4b888e4fa73818b8f43218。原始数据尚仅本机，独立安全恢复检查点正在整理，不以这些hash声称可以恢复缺失文件。

Astra决定暂不把F3纳入性能集成；它仍是正确性/码形已验证、局部harness有收益，但真实编译收益未成立的候选。先持久化全部结果，再只读检查执行与GC证据。没有自动重复C、开启full90或native代际验证。下一份普通GC诊断如实施须独立审查/准入，保留原资源保护、全部语义oracle及ignoreAll契约；不能把带统计的诊断wall混入普通样本。


## 恢复证据闭合与下一诊断边界（2026-11-10 17:55 UTC）

inference11完整检查点八文件已保存到[daf2f978的恢复入口](https://github.com/mlf-lang/mlf/blob/daf2f9780ba2a38e772fb65a6eb345ff01a8ef15/tools/performance/full-compiler/inference11-read-fusion-20261110/README.md)，整tree98c0cec31914101c0bfc8b7280796470c94eec6b与本地一致，完整fetch和逐文件字节核验通过。共55,768字节，含controller、launcher、workload模板、测试源码hash、README及Q01失败/Q02通过/C01四样本摘要。原始日志、receipts、查询树和binary不在公开检查点中。公开launcher仅参数化机器锁路径，明确未执行；原已测源码hash保留，换机器仍需重建依赖和重新资格。

四腿已有记录未见可辨source、binary、参数或runtime漂移，compile stdout/stderr均为空。仍没有ordinary GC/分配记录，不能据P1 profiled GC比例给C01慢B作事后解释。补充算法只读筛选找到了generateProgram成功验证后prepare对同一Graph重验的真实边界，但第二次验证仅799 ticks、约0.894%旧profile采样时间；recursive export链另一处同图重验未在该前缀命中。高频prepared fallback仍是不同local/rebuilt图，不能复用证书删除验证。当前不为这些低覆盖边界排CPU候选。

下一R5仅处于薄工具实现和独立review阶段，没有执行许可或新速度结论。拟setup最多120秒，私有重编原emlf六行Main及按原命令重建C、核字节后，链接对应侧已有94个非Main ordinary模块闭包；不能拿原共用位置的BuiltinPrelude Main冒充emlf，也不能把未在原receipt列hash的C对象追认为历史已认证。诊断另行最多420秒，两侧各一次原11模块fresh编译，每腿最多180秒，三个raw oracle与780 fresh条件不变。

两侧只加编译内-s统计落点并保留ignoreAll，不调nursery、不加profiler或并行GC、不改Graph和原producer。每个新诊断binary只能为目标编译启动一次，启动前拒绝已有stats文件或符号链接；GHC会截断统计文件，不能先跑version或随后show-crate覆盖它。统计仅说明该次普通进程的managed-heap分配/GC，不等于所有C分配、Graph独占成本、C01异常原因或普通吞吐结果。两阶段须分别取得令牌，不能自动连跑。

## Astra恢复调度与新审计（2026-11-10 20:54 UTC）

本次从远端`22b50be7014ede07db9e41d44cacf286c5ef6206`第15版恢复，由Astra继续承担协作、机器窗口和候选决策。三天仍从11月10日开始，不重启预算。新恢复分支`perf/astra-recovery-audit-20261111`末尾日期只是标签；事件以实际UTC为准。原计划分支经远端核对未漂移，本次不覆盖它。

冻结源码已在独立clean worktree恢复到f9bdb40；重新计算90模块、5,233,364字节，每个路径、字节数、SHA256和模块顺序均等于B0的冻结清单。见[本次库存核验](../../tools/performance/full-compiler/recovery-audit-20261110/source-inventory.json)。旧普通producer、当前sprint原始receipts和运行依赖未恢复，不能仅凭旧摘要接续旧cohort。历史F3真实ABBA不支持提速的结论保持不变，候选仍排除出集成。

当前为云端Debian13.6 Linux，不切用户电脑。约9.73GiB总内存、9.0GiB可用、55GiB工作区空闲。GCC14.2.0、ld2.44和glibc2.41与原基线一致，GHC及Clang尚缺。官方固定GHC9.14.1和Clang19.1.7下载地址已实测200；Astra为官方校验和固定、仅工作区内安装分配一次600秒setup窗口，所有既有内存/磁盘保护不变。/tmp是小于5GiB的tmpfs，不能作为通过5GiB磁盘下限的工作盘。

跨worktree共享flock已测试持有时拒绝竞争、释放后能独立重获；本轮所有重任务统一使用。sandbox-local ps不是全机空闲证明，不能据此推断旧机器进程。安装与重建不是性能样本；安装结束必须核对receipt、工具版本和清理后，才能另行准入producer构建。

新的静态审计优先检查fresh推断中closed检查到open检查的边界、canonicalOpen表示规范化，以及已有的编码/hash复用，而非先假定witness或安全检查都是浪费。不删除语义验证或放松制品oracle。普通GC薄诊断改为先准备baseline-only新实验，避免为已不支持提速的F3再次重建第二套producer；它只是准备，执行需新的资格、依赖、raw oracle和独立准入。旧R5的A/B设想不自动恢复，旧C01/full90、native代际A/B和fixed-point均不重跑。

## 工具链恢复完成，普通基线producer另行准入（2026-11-10 20:59 UTC）

官方11份固定archive/package的SHA256均通过，GHC9.14.1、Clang19.1.7、BDWGC8.2.8和GMP6.3.0已在工作区恢复；GHC小程序及Clang+GC/GMP的编译、链接、运行控制通过。整个setup实际244.252秒，峰进程树RSS2.590GB，最低可用内存6.530GB、最低可用磁盘51.064GB，所有原有限额满足。guard完整成功、末次RSS0，Astra独立重读receipt并重获共享锁。见[工具链摘要](../../tools/performance/full-compiler/recovery-audit-20261110/toolchain-summary.json)。这不是MLF编译性能数据。

Astra已分配下一次独立600秒普通基线producer构建，只用原f9源码及原builder、全137 shared/4host/13程序，保留check-candidate和fresh literal真实生成验证。成功后另有最多120秒小资格，重新认证receipt、全部object_inputs及C对象并运行原CLI/语义控制。运行环境明确固定，不能继承未知LD环境尾部后声称与历史相同。目标依赖重建、薄统计Main、inference11新资格及单次统计诊断尚未执行，不自动串接。

[新鲜编译路径审计](../../tools/performance/full-compiler/recovery-audit-20261110/cost-audit/README.md)已核对16份生产源码，并区分历史证据。closed检查与open检查可能重复遍历主体，但后者还建立可链接声明所有权，不能全称冗余。旧15模块诊断曾记录176,557 elaboration edges而witness fallback为0，旧同图验证消除screen只有0.2478%且未满足预定门；这些是历史线索，不是当前90/11模块成本。初始import节点确有两次编码/hash，但每次publish重编码整个AST的猜测不成立。后续先量化成本覆盖再选择生产改动。

## 普通baseline producer恢复资格完成（2026-11-10 21:07 UTC）

原f9 ordinary O2完整producer已在279.144547秒内通过，137 shared、4 host及13程序全部建立新receipt。原check-candidate与fresh-literal两门均实际通过；未改canonical源码或跳过生成验证。峰进程树RSS1.022GB，原600秒与其他资源保护均满足。之后独立小资格3.639881秒通过原authenticator前后核验、284个object/interface全清单hash、两份C对象及原命令、CLI版本/身份、42和Unicode正例及Bool/Int类型负例。两阶段均末次RSS0、无观察到的残留后代、两锁重获，Astra独立核对原receipt和锁。

[本次producer摘要](../../tools/performance/full-compiler/recovery-audit-20261110/producer-summary.json)记录新源/工具/制品身份；这只是恢复与资格，不是新target性能样本。94个emlf非Main对象与interface已独立列出。全producer共用的Main.o最后被其他程序覆盖，薄统计链接必须重编原emlf五行Main，不能混用最后Main。两份C对象还需在薄setup按原命令重建并逐字节相等，才可链接诊断。

此刻重锁空闲，只有新依赖恢复与薄统计控制器在静态准备/复核。它们分别需独立准入；目标source-to-checked、普通GC统计、完整90模块倍率均未产生新结果。旧F3、C01、native代际A/B与fixed-point状态不变。

## 新依赖恢复在总保护下失败，明确缩小诊断负载（2026-11-10 21:24 UTC）

唯一新inference11前置恢复在固定300秒总预算终止，未提高上限或续接。builtin fixture、foundation、language-core和frontend分别通过1、475、74、763 fresh / 0 reused与完整公开interface/query-lock检查，compile wall依次0.351484、29.536471、64.695432、164.217328秒。xmlf只剩26.855秒预算，虽然出现两份部分制品，但没有.queries和完成校验，不能列为已通过。语言核心与前端的已记录user CPU也增多，不能仅归因于等待；原因尚未判定。

launcher在300秒触发停止，包含终止清理的总耗时300.441秒；外guard被正常TERM协调停止并记录失败。峰RSS361.5MB，资源上限未放宽。所有原始失败与部分输出保留，无观察到的owned残留，三层orchestration锁与五个query锁已独立重获。但最终producer再认证和runtime-after未执行，因此没有完整依赖handoff，更没有inference11薄setup、GC统计或新的提速结果。见[失败报告](../../tools/performance/full-compiler/recovery-audit-20261110/prerequisites-failure.md)。

Astra不重跑或续接该失败。下一步仅准备一个另立的foundation14诊断：原f9的14模块、173,594字节、475 fresh，重新建立builtin、新ordinary Q和one-use D；只复用成功的ordinary producer/工具链，不拿失败依赖前缀充完整资格。保留SETUP120、QD420/每目标180秒及全部语义、raw三制品、runtime和资源条件，仍需新代码的独立复核与分阶段准入。它只能说明较小负载的普通managed-heap工作，不能替代11模块、full90或GHC比较。未改任何生产源码、验证策略或暂停任务。

## 共享锁新epoch与foundation14预检失败（2026-11-10 21:40 UTC）

当前sandbox中旧/workspace/shared目录已消失，其父文件系统只读，不能声称旧锁连续有效。Astra在共享工作区新建单一flock；协调端和执行端核对同一device/inode，持有时竞争被拒，释放后两次重获。只有foundation新envelope的锁位置改变，经36项测试和独立复核，原失败依赖和inference11文件未动。后续重任务必须采用此新epoch，不能回退为各自私有锁。

唯一准入的foundation SETUP01在8.386秒安全停止，commands为空，任何compiler、loader、builtin或统计控制均未启动。原producer认证通过，但新的通用嵌套pin收集器拒绝官方GHC launcher的已记录symlink；这是新诊断控制器的兼容性缺陷，不是编译失败或性能样本。外guard exit1、无资源理由，无owned残留，两锁均重获，失败原样保留。见[预检失败证据](../../tools/performance/full-compiler/recovery-audit-20261110/foundation14-setup-failure.json)。

只准备另立cohort02的严格alias绑定修正：须匹配已固定工具链receipt中的resolved_path和目标SHA并核验前后链接，不放宽通用regular-file输入门。需新增retarget/broken/missing/unknown-alias负控、独立复核、重新分阶段准入。没有SETUP/QD自动重试，没有GC结果，也没有任何生产优化或完整倍率。

## foundation14实际GC诊断完成（2026-11-10 21:56 UTC）

独立复核的alias专用修正只认证工具链receipt已有的三条链接及全部中间target，保留通用regular-file检查；46项测试通过。新cohort02的SETUP在94.322秒内通过新builtin、C原命令重建逐字节相等、原emlf Main/94对象、真实RTS传输控制和runtime/pin前后门。随后另行准入的一次QD在98.849秒完成，Q32.938978秒、D34.016559秒只是资格耗时，不是性能AB。两腿均475 fresh/0 reused，全部14 owner/builtin检查通过，三种公开制品与完整有序query JSON全等。所有原保护、one-use claim、收尾认证和锁均通过；最终观察RSS0，无owned残留。

[完整结果](../../tools/performance/full-compiler/recovery-audit-20261110/foundation14-gc/REPORT.md)：173,594字节的14模块工作负载分配60,546,927,152 managed-heap字节，GC复制4,299,126,432字节，59次major采样的最高存活堆36,197,520字节；raw memory105MiB。GC CPU5.413秒/RTS total32.230秒≈16.8%，mutator26.817秒。这支持继续定位大量短命分配及重复遍历，但不能判定哪项语义功能不必要。即使其他工作不变而把本次GC完全消除，纯算术上限也只约1.20倍，不能据此宣称完整编译已接近GHC。

原RTS文本保留了两项报告问题：冻结decoder把MiB convenience unit误写MB，分析按raw MiB；原%GC行显示0.0而time/productivity不符，16.8%明确按GC/Total推导，未改raw统计行。统计不含C/BDWGC全部分配，residency不是峰RSS。原raw SHA及仅路径banner脱敏文本、完整source/receipt身份和已复核控制器均已归档。

Astra将下一优先级改为allocation来源归因的只读设计：比较可用prof工具链/manual cost centre与低扰动demand标记，明确惰性边界，区分solve/elaboration、closed/open ownership、canonical图物化、fingerprint/编码。尚未准入新构建或目标执行，不盲调nursery，不删除安全检查或witness。失败inference11前置、foundation01及历史F3负结果均保留。full90完成、相对GHC倍率、生产提速、native代际A/B及fixed-point仍未新增通过。

## 下一归因实验的静态设计完成（2026-11-10 22:08 UTC）

Astra选择稀疏manual SCC的host-only可逆源码镜像，而非增加无法拆分惰性纯工作的新IO时钟。官方GHC9.14.1已存在所需23个package unit的profiling依赖；全安装库存53个_p.a、2,212个.p_hi，这只是presence，不等于实际link通过。静态import闭包是95个非Main模块（emlf94再加BuiltinPrelude一项），加两个独立Main；明确不冒充原137/4/13完整producer。

[决策和门槛](../../tools/performance/full-compiler/recovery-audit-20261110/allocation-attribution-design/DECISION.md)保留原137 frozen source --check-shared、实际check-candidate与fresh-generator字节门、普通producer独立认证、fresh Q/P三raw制品及完整query资格，之后才能另行准入单次profile。不能加deepseq/seq或提前提取inventory来制造易读归因，也不能把重叠inherited成本相加或把prof份额乘到普通60.55GB上。结果只能叫profiled source-demand allocation，不是普通独占CPU或可删除功能成本。

设计及工具链/源码库存已保存；执行控制器尚未实现，独立implementation审查及BUILD/QUALIFY/CONTROLS/TARGET-QUALIFICATION/ATTRIBUTION全部未准入。机器重锁空闲；后续先实现及复核，不自动恢复旧profile runner的RTS解析或弱oracle。

## 11月11日恢复实际实施，未把静态方案冒充持续运行

远端仍为revision22，先前阶段结束后没有新的profile执行。09:25UTC重连时，当前cloud挂载中的旧源码、工具链、producer、receipts和锁目录全部缺失；不能推断确切中断机制或旧主机全部进程状态。本次从2aa3208恢复干净f9源码，建立并交叉核验新共享锁epoch，三天预算不重置。

新TOOLCHAIN_SETUP_2已实际通过：176.852536秒、11个官方archive SHA、固定版本和两种compile/link/run控制均通过；峰RSS2.564GB、最终RSS0、最低可用RAM6.760GB、磁盘51.041GB，锁重获，源码clean。保留原600秒/5GiB RSS/6GiB AS/5GiB磁盘floor/3GiB RAM floor；工具链原12GiB输出cap与目标诊断cap分开，不混用。见[本轮证据](../../tools/performance/full-compiler/continuation-20261111/README.md)。

Astra已开始编写可逆SCC镜像、JSON归因解析、Linux保护runner、runtime pins及分阶段controller，并在进行实际轻量负例测试；不是仅重读计划。新ordinary producer恢复controller也在准备。所有旧缺失二进制必须重新资格，尚未准入新producer/profile目标执行；不会重复失败full90/C01或启用暂停campaign。阶段完成后继续已授权下一步或报告具体阻塞，不能把保存计划当作有进程持续运行。
