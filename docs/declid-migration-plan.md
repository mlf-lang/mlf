# DeclId 迁移交接计划

| 项目 | 约定 |
|---|---|
| 集成分支 | `codex/issue-37-declid-migration` |
| 分支起点 | `726cd256aa90d3e8cf596842fbb29515c1bc5249`，创建时 [PR #43](https://github.com/mlf-lang/mlf/pull/43) 的远端头 |
| 合回目标 | `mlf-lang/mlf:codex/issue-37-indexvec`，即 #43 的 head。#43 自身继续沿用 #29 基线并以 `main` 为目标 |
| 当前进度 | 已建集成分支。本计划中的实施项、验证和回合并均待接手 |

目标是让同一个顶层值、方法或生成绑定从解析到查询一直使用同一个声明槽。在接口、缓存、独立链接会话和原生布局之间显式转换身份。基线已经实现 `Global (Index Declaration)`、按表达式建 SCC 和按 ID 捕获实例 helper，也已实现 `finish-receipt-1`。其中 tag 427 绑定组名、最终片段 SHA 和按名字排序的导出契约摘要，有序读取及其版本由代际索引绑定。以这个版本建立对照，历史诊断结果作为研究参考。[现有 ID 设计](indexvec.md) · [查询与收尾契约](crate-query-graph.md)

## 各 agent 共用的设计

- **一张声明表。** 本计划用 `DeclId` 表示现有的 `V.Index Dependency.Declaration`。由解析器给定义实体分配槽，别名和重导出沿用原定义，生成的 selector、superclass accessor、字典和合成入口在同一域追加。导入绑定进入本次编译时建立本地槽。每槽持有一份规范名字。保留按名字查找的入口给解析、读外部数据和显示层。相同打印名的非活动导入不得捕获活动本地声明。
- **两个作用域。** 编译内的 `contracts[d]` 和 `bindings[d]` 解释本次声明表。持久化的短编号只在它所属的快照或引用表内有意义。跨代、跨 crate 时，用带定义 crate、模块和角色的稳定身份重新对应。给源码加入一个无关声明，即使改变数字槽，也须能认出原绑定。局部 binder、xMLF 的 `XName`、类型声明、模块、证据位置、求解器节点和 ABI 导出槽保留各自的身份。
- **三个不同的问题。** `Binding(d)` 定位一个绑定，`InferScc(members)` 和 `FinishScc(members)` 定位一个有序成员组，`Evidence(members, site, goal)` 再定位一个证据请求。身份回答“读谁”，摘要回答“读的是哪个结果版本”。保留词法 SCC 输出次序、组内源码次序、候选角色、候选顺序、重复读取及读取顺序。
- **阶段接口。** 已解析源码、checked 前驱、类生成项和查询驱动传 typed ID。原始解析 AST、兼容的 named API、诊断和公开产物在各自边界投影。凡是 lowering 引入新的全局引用，都在生成处绑定 ID。局部遮蔽与局部 given dictionary 继续走词法环境。保持库依赖方向和 shared-haskell-v1 支持范围。
- **表的更新。** 只发布已检查完成的前驱。区分空槽、外部槽和本地定义。按需使用作用域内的 builder 和不可变快照，避免每完成一个 SCC 就复制整张 `IndexVec`。编译失败、取消或重试不得暴露半成品。

例如，声明槽 7 属于 `A.f`，源码中读它写作 `Global(7)`，读取它的契约写作 `Binding(7)`。若 7 和 12 互递归，收尾查询的逻辑键是 `FinishScc([7,12])`。当另一代把 `A.f` 排到槽 9，旧边仍须通过旧表找到同一稳定定义及当时的摘要。这三个例子应进入独立测试。

## 实施清单

编号也是分别提交和验收的顺序。表中的“牵头”是分配给其他 agents 的角色。优先使用列出的函数定位代码，行号会随合入移动。

| 编号 / 牵头 | 交付内容与主要入口 | 本步验收 |
|---|---|---|
| 00 集成与验证 | 从固定起点单独安装基线，保存二进制 SHA、安装回执、Foundation 三态产物、解码后的查询行和自编译结果。建立每个编号的提交、正常入口、测试和证据清单。 | 别的 agent 能从干净 worktree 复现。分别记录源码提交、编译器宿主和实际运行的程序。 |
| 01 身份与解析 | 在 `Bootstrap.Dependency`、`Module`、`Resolved`、`Surface` 明确声明表的分配、追加、导入映射及越界规则。保留现有全局引用、重载模式、合成入口和实例 helper 的 ID 路径。 | 别名、重导出、遮蔽、同打印名不同实体、生成项晚于源码入表、跨 crate 同实体不同槽均通过。修改一处 `Global` 同时改变依赖和名字投影。 |
| 02 分组 | `SourceInference.indexedPlan / eligibleSource / planSteps` 携带组成员 ID、源码顺序和源码自引用标记，替代单成员组按自由名字再查自己的做法。分别处理 source-only、生成项和 mixed fallback。 | 单成员非递归、自递归、互递归、字典递归与原顺序一致。lowering 改变依赖的用例按新依赖处理。 |
| 03 类型类 | 把 `Module.resolvedCrateValueScopes`、`Crate.prepareCrate` 和 `Classes.ClassInventory` 中以值名字为键的可见性迁成 `visibleInstances[d]`。 | 两个模块作用域不同、局部遮蔽、实例新增或重排，均给出原有选择和诊断。 |
| 04 生成声明 | 在类生成阶段建立 `selectorOf[methodId]`，为生成的顶层字典和 superclass accessor 分配声明槽。让 `Dependency.resolvedGroups` 及证据候选使用生成时已知的 ID。 | 源码节点的槽不移动。方法重定向、生成字典、导入方法与本地同名、局部 given 和候选顺序分别有覆盖。 |
| 05 保护传播 | `Classes.inventoryProtection` 按 ID 建反向边。以直接受保护的成员和导入的保护标志为种子，只传播到可能改变的使用方。包含方法目标和隐藏字典引用。 | 与 named 算法逐项比较最终标志，覆盖环、菱形、长链、导入标志变化和未受影响成员。 |
| 06 前驱与 Binding | `SourceInference.selectedContractBindings`、`PreparedGroup` 和 `CrateGraph.recordBindings / requireNodes` 全程传 `DeclId`。以槽读取类型、约束及保护位，区分 `Binding(d)`、`InputBinding(d)`。保留前驱缺失和读取未完成 SCC 的错误。 | 通过正式 `--compile-crate` 走新路。仅变更保护位或约束也会触发正确的失效。生成/导入支持项在查询前拥有槽。 |
| 07 组与证据查询 | 分两笔迁移。先把 `Prepared / ScopeInventory / Scope / InferScc / FinishScc` 改成查询种类加完整成员 ID 列表，再迁 `CrateGraph.resolveRequests` 的组、site、规范化 goal 及有序顶层候选。 | 同成员不同查询、同组不同 site 或 goal、组拆分/合并均可区分。保持原有 raw/finish/evidence 依赖方向。 |
| 08 Prepared 输入 | `CrateGraph.preparedValue` 和 `CrateQuery.canonicalMember` 对全局引用使用组内短编号。引用表按稳定定义身份规范化并参与指纹。覆盖原始和 lowered 两份成员、隐式引用与候选。 | 无关声明重排、别名及局部 alpha 改名保持应有的命中。改为另一同名定义、改变候选顺序或保护信息触发失效。 |
| 09 导入参数 | `ImportParameters.select`、`ImportedRoot`、`PreparedLibraries` 将外部签名一次映射到消费方表，按 ID 选 wrapper 所需的顶层参数。 | 包括 lowered `SWanted` 的候选以及未使用局部绑定的 RHS。零导入、签名不匹配、本地同名和参数顺序分别验证。 |
| 10 片段加载 | `OpenFragment.decodeTrusted / readPackage / finalBindings` 将文件中的稳定参数身份、预期 ID 和类型一次按序对齐，去掉每个参数从列表头查类型的路径。覆盖 raw 和最终对象。 | 拒绝缺失、多出、重复、错序、错 owner、类型或版本不符。保留 SHA、stage、参数库存及局部 `XName` 验证。 |
| 11 收尾归属 | `SourceInference.validatePreparedOpen / prepareOpenFinish`、`CrateGraph.recordFinish` 的顶层成员、使用前驱及契约增量按 ID 匹配。继续按当次 checked 结果构造 tag 427。 | 独立从输出对象重建 receipt。交换 owner、过期版本、重排读取、缺失或损坏 payload、用 finish 冒充 raw 均正确恢复或拒绝。保留 ICH 和语义审计的不同保证。 |
| 12 Core 与推断 | 让全局身份贯通 class lowering、Core 和 `Constraint.buildCore`，以 `globalEnv[d]` 查顶层绑定。保留局部 lambda、let、模式、类型变量和 solver 节点的现有域。 | 顶层/局部重名、嵌套遮蔽、导入多态函数、递归声明和生成字典的类型、xMLF 及错误与基线一致。 |
| 13 接口与入口 | `CrateSession.graphInterface`、`Crate.entryBindings`、`CrateArtifact.validateOwnExportNamed` 按 ID 汇集值/方法的归属、保护契约及合成入口，在写公开接口时查稳定名字。 | 导出、私有、重导出、同名不同 crate、无入口及合成入口行为一致。类型/类/构造器继续以自己的命名空间校验。 |
| 14 按需链接 | `CrateArtifact.selectOpenFragments / linkOpenFragment` 在本次链接中建 `producerOf[d]`，从所选入口走片段依赖。独立读对象时将每个生产方的稳定身份映射到链接会话，保留原有顺序及 `Open.fresh`。 | 多 crate 钻石、无关片段、重复提供方、缺失依赖、导出类型不匹配以及无源码重链接均有通过/拒绝对照。 |
| 15 原生导出 | `LLVM.Library.prepareLayout / exportEntries` 及预编译库适配处建立 `DeclId → ABI slot` 映射，分别验证导出 key、hint、类型与布局。 | 调整声明槽顺序，既有原生导出仍定位到正确符号。加载、链接并实际执行跨包程序。 |
| 16 诊断 | 对已经知道顶层实体的错误用声明表取显示名。保留引用点位置、歧义候选和解析前的原始拼写。检查 `Module.resolvedCrateDisplayNames / displayNames` 的调用方。 | 同名导入、相互遮蔽、类型错误、生成声明和源码位置的诊断与基线逐条比对。 |
| 17 查询索引落盘 | 在 `QueryGraph`、独立 reader、缓存检查和性能工具中一起实现下述代际格式。绑定边直接用快照中的声明编号，组与证据边使用步骤 07 的描述符，datatype 保持自己的域。 | 逐行还原相同稳定键、结果摘要、有序读取及位置。覆盖兼容读取、损坏、原子发布和完整 `mlf-crates` 自编译。 |
| 18 集成与回合并 | 完成下文测试、性能对照、剩余字符串查找审计和 stacked PR。 | 00–17 每项都有实际提交或已存在路径的验证证据，最后一批在最新 #43 基线上重跑。 |

## 第 17 步的格式契约

1. 先给 generation 定版本和新的缓存目录。声明表记录稳定定义身份，组表记录规范成员顺序，证据描述符保留 site 和 goal。规定 `Binding`、`Input/Binding`、组、证据和 datatype 的不同编码。只有目标确为绑定时，边才能单写一个声明编号。独立解析的两个 crate 可以把同一实体分到不同槽。
2. 写出前验证每条读边在**当前待发布表**中存在，并核对目标结果摘要与观察到的版本。验证成功后才可省略边上重复的摘要。从旧代读入时，在**那一代**取回目标的稳定身份和版本，再与当前代比较。组成员或候选顺序不得由当次分配的整数偶然决定。
3. 读入先检查版本、配置、SHA、数量/工作量/深度边界，再检查槽范围、重复键、悬空边和循环。保留已有原子发布、并发写者串行化、失败后 `CURRENT` 指向最后一次成功代的契约。保留 v1 fixture 和独立解码能力。遇到不兼容的编译器配置时从冷缓存启动，旧 reader 仍可打开原来的文件。
4. 用独立 Python reader 将新图还原为旧逻辑行，逐项比较。对单纯改变索引表示的样本，再重编码并核对旧图的完整字节。对于按设计换版的 Prepared 指纹，单列格式差异，并核对实际输入、失效集合、checked 结果及产物。tag 427 收尾内容寻址和公开的 crate ABI 继续按已有协议验证。

## 分工与验证

集成 agent 管 00、01、17、18 和共享接口。前端/类型类 agent 管 02–05 和 12，查询 agent 管 06–08 和 11，产物/后端 agent 管 09、10 和 13–16。每一编号独立提交，并在该提交记录正常入口、回归用例和结果。多人从集成分支已验收的提交各建 worktree，涉及同一文件的改动按编号串行合入。验证 agent 可先准备独立 fixture 和基线，等前一步接口合入后再接候选。集成人等所有对应任务和命令结束，再勾选该项。

实际入口包括普通源码/模块编译、`CrateSession.compileGraphLocked` 的 resolved 和 lowered 两条路径、独立 `CrateQuery.compileParsedSourceGroups`、预编译库的源码/原生 wrapper，以及无源码的 `CrateArtifact.linkOpenCrate`。每个入口用一次真实调用证明它走到了分配给该步的实现。对确实仍接收原始名字的调用方保留 named adapter。

Agent 从 `origin/codex/issue-37-declid-migration` 建自己的工作分支，并把子 PR 的 base 设为集成分支。源码集中在 [frontend](../libraries/mlf-frontend/Bootstrap)、[inference](../libraries/mlf-inference/Bootstrap)、[crates](../libraries/mlf-crates/Bootstrap)、[xMLF](../libraries/mlf-xmlf/Bootstrap/X) 和 [LLVM](../libraries/mlf-llvm/Bootstrap/LLVM)。给集成 agent 的交付单列出编号、提交 SHA、改动的调用方、精确测试命令、结果和待处理项。

```sh
# WORK_BRANCH 例如 codex/declid-01-identity，WORKTREE 取独立的新路径
git fetch origin
git worktree add --no-track -b "$WORK_BRANCH" "$WORKTREE" origin/codex/issue-37-declid-migration
```

执行命令时从仓库根目录出发。分别从固定起点和候选建立独立安装，`BEFORE`、`AFTER` 指向其绝对路径，`OUT` 是新的证据目录。新增 shared 模块时核对 `shared-sources.json`、`mlf-shared.cabal` 和所属包 manifest。修改 builtin 生成闭包后重新生成 literal 并校验来源，最后用包管理器刷新 `mlf.lock`。[构建约定](../CONTRIBUTING.md) · [安装流程](../tools/shared/prepared-build.md)

```sh
# 在两个 checkout 分别执行，各自使用新的 INSTALL 路径
python3 -B tools/shared/build.py --build-dir "$INSTALL"

# 在候选 checkout 执行
mkdir -p "$OUT"
"$AFTER/bin/mlfpkg" --offline --locked plan > "$OUT/locked-plan.json"
python3 -B tests/indexvec/run.py --compiler "$AFTER/bin/emlf" \
  --reference-manager "$BEFORE/bin/mlfpkg" --reference-compiler "$BEFORE/bin/emlf" \
  --output "$OUT/indexvec"
python3 -B tools/performance/crate-query-graph/verify.py "$AFTER/bin/emlf" "$OUT/query"
"$AFTER/bin/shared-frontend" --frontend
"$AFTER/bin/shared-frontend" --native-first
"$AFTER/bin/shared-frontend" --native-second
```

下面两项使用已配置的原生工具链、`MLF_BUILD_RUNNER` 和 GC 路径。Foundation 的输出和安装均在计时之前准备，原始样本随最终的子 PR 提交。

```sh
"$AFTER/bin/mlfpkg" --offline --manifest libraries/mlf-crates/mlf-package.json \
  --build-dir "$OUT/mlf-crates-build" --cache-dir "$OUT/mlf-crates-cache" \
  --compiler "$AFTER/bin/emlf" --runtime "$PWD/runtime/mlf_runtime.c" --jobs 1 --timeout 21600 build
mkdir -p "$OUT/fixture"
git archive c5928b5b libraries/mlf-foundation | tar -x -C "$OUT/fixture"
python3 -B tools/performance/dense-decode/foundation.py "$BEFORE/bin/emlf" "$AFTER/bin/emlf" \
  "$OUT/fixture/libraries/mlf-foundation" "$OUT/foundation" --warm-rounds 12 --cold-rounds 3 --profile-rounds 3
```

| 门槛 | 必须交付的证据 |
|---|---|
| 语义与兼容性 | 原有 SCC 顺序及独立 oracle、源码/已 lowering 入口、相同拼写不同实体、增删声明导致槽漂移、多成员 SCC 拆合和局部 alpha 改名。用两版编译器的所有生产方/消费方组合编译、链接、运行。比较公开接口、对象、xMLF、诊断和独立运行结果。 |
| 缓存与收尾 | 除正常冷、热、编辑外，运行 `-Zincremental-verify-ich`、语义审计、receipt 重建、错误 owner/slot/goal、陈旧/错序读取、损坏对象、并发写入和发布 failpoint。独立 reader 的 schema/逻辑期望须独立于候选实现。 |
| 自编译 | 用固定工具链和正式 `mlfpkg` 路径从空缓存构建 `libraries/mlf-crates/mlf-package.json`。确认接口、对象、报告、可解码且已发布的 `CURRENT` 均存在，再运行一次验证复用。随后执行根包 locked build/test，并记录实际 compiler host。沿用既有展开预算，取得 `mlf-crates` 的完整发布结果。 |
| 性能 | 用 `c5928b5b` 的相同 14 个 Foundation 模块、相同工具链和独立种子缓存，运行 [配对脚本](../tools/performance/dense-decode/foundation.py)，热缓存/Version 编辑各 12 对，冷缓存 3 对，分项计时另跑。核对预期推断/复用数 `504/0`、`0/504`、`1/503`，同时保存墙钟、CPU、RSS、缓存字节、物理节点/边、展开工作量和编译器 SHA。历史离线估算不作为新版本实测。 |
| 覆盖闭合 | 逐项复核 query 驱动、Core、片段加载、链接和 ABI 的正常入口。对目标路径剩余的 `symbolName`、`X.nameHint`、`Map String` 和 `lookup eqString` 分类标注其解析、ABI、快照、局部绑定或诊断职责。未完成项或可复现退化留在集成分支解决。 |

## 合回 #43

在集成 worktree 中同步最新远端 #43，保留上游并行提交，在整合后的 SHA 上跑最后一轮门槛。建一个 **base 为 `codex/issue-37-indexvec`、head 为 `codex/issue-37-declid-migration`** 的 stacked PR。PR 正文列出各步提交、独立 reader 对照、基准样本及自编译回执。合并这个子 PR 即完成“合回 #43”。

```sh
git fetch origin
git switch codex/issue-37-declid-migration
git merge origin/codex/issue-37-indexvec
# 通过上述门槛后，推送集成分支并创建子 PR
git push origin codex/issue-37-declid-migration
gh pr create --repo mlf-lang/mlf --base codex/issue-37-indexvec \
  --head codex/issue-37-declid-migration --title "Carry declaration IDs through compilation and query storage" \
  --body-file "$OUT/pr-body.md"
# STACK_PR 为刚创建的子 PR，REVIEWED_SHA 为已验收的 head
gh pr merge "$STACK_PR" --repo mlf-lang/mlf --merge --match-head-commit "$REVIEWED_SHA"
git fetch origin
git merge-base --is-ancestor "$REVIEWED_SHA" origin/codex/issue-37-indexvec
gh pr view 43 --repo mlf-lang/mlf --json state,baseRefName,headRefName,headRefOid
```
