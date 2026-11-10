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

借鉴 [多代理团队文章](https://claude.dev/blog/safely-scaling-multi-agent-teams-with-fable-5-2/) 的独立工作区、明确任务所有权、依赖拆分和可检查的交付物，不照搬1000人规模。本轮共享一台约9.7GiB内存的云机器，编码和只读审查可并行，重构建和计时串行。

| ID | 责任方向 | 独占源码范围 | 交付物 | 前提 |
| --- | --- | --- | --- | --- |
| B0 | 基线与证据 | 测量harness，不改生产算法 | 当前MLF/GHC完整端点资格、精确artifact/receipt、普通基线cohort | 工具链与producer认证 |
| B1 | 制品和后端 | 当前只有 backend-stages 诊断工具 | 小crate预检、当前完整checked输入分段诊断、ordinary LLVM原始字节一致 | B0可用checked artifact、资源令牌 |
| F1 | 前端与统一诊断harness | 当前只改私有诊断入口/计数器；生产Type恢复基线 | kindOf memo已停止；下一步用低扰动SCC身份和需求窗口定位 | R2边界审查、资源令牌 |
| R1（停止） | legacy调用内复用实验 | Bootstrap.CrateQuery、Bootstrap.CrateSession | 仅保留可恢复实验；已确认不在当前端点调用链上，不再安排producer/计时 | 不作为当前优化候选 |
| R2 | 当前graph边界定位 | 私有诊断中的CrateSession、CrateGraph | 真实IO返回/每SCC进度事件，与F1共用一次有界诊断 | 与F1固定接口、资源令牌 |
| M0/M1 | 基线与证据 | 冻结测量配置 | 基线和每个已符合条件候选的fresh、配对、ordinary端点 | B0成功；相应候选完成控制 |
| I1 | Astra集成与复核 | 单一集成分支 | 逐项纳入可接受改动、组合正确性/性能复测、最终差距 | 各候选的独立证据 |

每个任务只有一个当前负责人。需要改别人所有的owner时先协调，不互相覆盖。新发现要附精确源身份、输入、机制、已完成/未完成检查。候选任务失败或被否决属于正常终态，不阻塞其他合格候选的测量。分支和准确提交以检查点JSON为准。

## 资源令牌与执行节奏

1. 重任务开始前由 Astra 确认唯一令牌持有者。不要仅凭本shell的ps判断全机空闲：不同执行环境的进程视图可能不同。
2. 所有新重任务使用同一个共享排他锁，并保留各harness原有锁。锁作用域必须覆盖整个构建/测量cohort；失败时先确认子进程已回收，再释放令牌。
3. B0已先后完成MLF-native失败资格与GHC-native成功资格。资格数据不并入正式样本；MLF资格开头可能与一次约3秒控制有重叠，保留说明。
4. 当前MLF资格已在600.099秒触发wall保护，无checked/LLVM产物；GHC资格outer为155.931809537秒。完整倍率仍不可用。B1小main资格与F1/R2单次120秒计数定位都已完成。下一步F1/R2共同准备去除Type计数的低扰动SCC窗口诊断；R1停止排期。完整90模块目标不变，小输入不顶替目标。
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

## 当前可核验检查点（后续更新见JSON）

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

新的联合诊断源码和原始快照提交在本机为27efb8ff0e817fffd16d87c6759dfcf3174492f2，远端仍未确认保存。旧远端64ee679不包含这次完成结果或Type恢复。恢复时先核对JSON最新remote_commit和范围；若新内容仍未保全，应据说明重新准备诊断，不能声称原始日志还可取回。

## 下一次低扰动定位的准入（2026-11-10 14:07 UTC）

Astra已批准F1统一实现一次markers-only诊断，R2复核已有成功/失败路径和安全身份来源。生产Type保持冻结基线原字节，移除每根/每次访问计数和诊断专用优化限制，使用ordinary完整flags与认证C对象；controls使用独立对象目录。现有MLF_QUERY_PROFILE保持关闭，避免重复计时；其六槽最终汇总把raw需求和raw编码合并，不能替代此次按组定位。

每组只严格复制已由原prepared payload编码消费的有界owner信息，不投影可能仍惰性的sourceNode，不让reporter持有AST或thunk。身份包含运行源码身份、started ordinal、数字owner IDs和截断名称预览；不把截断名称当完整稳定身份。每组开始清空current，成功finish后保留last_completed。总SCC数在自然遍历结束前保持unknown，不提前求length。

现有IO marker之间用单调时钟累计四个已闭合需求wall窗口：prepared-record、raw-await、raw-record和finish；另报当前未闭合窗口age，仅保留最慢五组的有界身份。这些窗口包含GC和惰性残留，不是独占CPU份额或普通速度。小controls先验证零状态、窗口闭合、身份清空、未闭合age和top-five有界性，再允许一次最多120秒定位；构建600秒与现有资源守卫不变。当前只批准准备和该次有界运行，没有新增已完成性能证据。

main已合并#50至fc300bc9fdc389b585cbef0630fc8915d53e89c5；变化限于工具/CI/契约/文档，没有修改冻结90模块、host或runtime源码。当前诊断仍严格使用f9bdb40，不把旧producer重标成新main；最终集成需新建并认证相应build-driver身份。
