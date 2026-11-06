# 全部测试迁入自有框架：实施设计

> 状态：详尽实施设计，尚未实施迁移或执行完整验证。代码基线 `8a3e69b165765931c3ff762379a78db9659b2cd8`；main `77ac8a7bc551ac71747b38c79fc5812d385165e3`，整合 #9/#11/#12/#16。各 PR 的历史资格认证不能代替组合树认证。

## 1. 目标与完成定义

目标是让所有现存测试受自有框架统一定义、发现、选择、调度、执行、诊断和报告管理。仅为一个 shell 脚本包一层并给它记录一个 pass，不算完成：框架必须知道其应执行的稳定测试 ID、前置条件、参数/矩阵、预期判定、各观察值、失败与清理结果，能够验证原覆盖没有消失。原生 C、PowerShell、编译器进程、独立 oracle、基准引擎可保留为正式执行适配器；它们不再是绕过框架的测试入口。

快 PR、main qualification、release、performance 都是对同一注册表的选择与资源策略，不各自维护一份测试实现。发布的网络写操作不是测试；发布规则、身份认证、tag 约束、SDK 可迁移性和产物内容验证都必须接入。

本次只交付设计和静态清单，不改变完整 campaign 的覆盖，不重写所有测试，不运行完整测试、bootstrap、self-host 或基准。

相关交付：[本地整合与验证记录](local-integration-20261023.md)、[完整迁移清单 JSON](testing-migration-inventory-20261023.json)、[全仓资产清单 TSV](testing-inventory-20261023.tsv)、[外部入口逐项矩阵](testing-external-entrypoints-20261023.tsv)。

## 2. 现状与清单契约

当前存在三个不同层次：

1. `testing/Test/{Case,Assert,Runner}.emlf` 的 Case/Assertion/Runner，`testing/tools/Test/Process.emlf` 的进程协议；`Tests.IntSetUnions` 等真正使用这一层。
2. `tests/Tests/{Catalog,Selection,CompilerTests,Coverage}.emlf` 和 `tests/test-catalog.json` 已实现 family 选择、六组完整 campaign、独立证据和 Core 物理分区。Core 的传统 `(label, IO Unit)` action 仍会通过旧失败机制终止进程，不等于每项均为可恢复 Case。
3. native/runtime、async、source smoke、CI policy、Windows、SDK 和性能脚本还有独立入口。部分是 campaign 依赖，部分由 workflow 直接运行；JSON 报告存在不等于框架已拥有其执行语义。

附件必须提供完整 tracked 文件资产表和所有发现的入口矩阵，而不是代表性例子。每个入口有当前层、源码位置、调用方、目标类别/adapter、迁移阶段、预期 inventory 来源、状态与未知项。每个 fixture/reference/helper/archive 都有归属，不能把任意 `.c` 或 `.emlf` 文件自动算成一条测试，也不能把历史 report 自动算成当前 oracle。

静态清单的边界：动态生成的 parity/property 测例和脚本内部断言未必能仅从文件名恢复全部叶子 ID。必须显式记录其生成规则、既有 immutable inventory、导出工作和未决状态；不声称本次已经运行 discovery 得到完整动态叶子集。迁移完成前这些未决项必须归零。

### 冻结树的实际静态盘点

清单绑定代码 commit `8a3e69b165765931c3ff762379a78db9659b2cd8`，不是后续文档 commit。全仓 3,486 个 tracked 路径逐一对应 Git tree；active 源文件扫描遗漏 0。目录计数为 `tests/` 257、`testing/` 9、`bootstrap/tests/` 58、`test/` 1、`examples/` 25、`runtime/` 18、`benchmarks/` 142；另分类标出 2,620 个历史测量资产和 `tmp/a8-reference/` 104 个独立参考实现/复现资产，均保留来源和 Git blob，不当作可直接执行的用例。

| 基线层级 | 静态核实数量/归属 | 解释 |
| --- | --- | --- |
| 根入口 | 4 executables，8 tests：tuple-list、tuple-list-native + 六 campaigns | root target 不等于 Case API 接入 |
| Catalog | 170 families：Core 35、Harness 53、Backends 50、Port 25、其余 7 | 与 `Catalog` 和 JSON 中的既有选择模型对齐 |
| Reviewed assertion inventory | Core 739、Harness 67、Regex 56、Framework 4、Packages 79、Figure12 77 + 2 aliases | 这是原 inventory，不是本次执行统计；JSON 附件保留完整 suite/ID 内容 |
| 追踪矩阵 | 577 行，包括 48 manifest targets、170 families、90 条 tuple/list authored observations、10 workloads、9 profiler methods，以及源码/脚本/workflow 候选入口等 | facade/family/leaf 是多层关系，**不可相加为独立测试数** |
| 外部入口专表 | 202 路径全部映射；118 个物化文件字节与 commit blob 相同，84 个历史脚本保留归档 | 与总表共享阶段映射；历史脚本不是额外 required runs |
| 明确待审项 | 243 个静态入口角色候选、6 个副作用工具的 contract 归属、90 个 tuple/list 拟稳定 ID，共 339 行 | 已给目标 adapter/phase；P0/P3/P7 必须完成语义审核，不得宣称当前迁移已经完成 |

所有 pending 条目在 JSON 的 `unresolved_entries` 中逐行列出，不能通过忽略未知项让完工计数归零。静态候选包含生产 CLI、fixture helper 与历史工具；实际 target 角色要由调用关系和测试意图审核，不能只因文件有 `main` 就执行。`TestFrameworkMain` 的 probe 使用 Runner，但 framework self-check 的四个 coverage IDs 也含 CLI/catalog/validator controls；不将它们全部称为已逐 Case 化。现有业务 suite 中明确使用 Case/Runner 的是 `IntSetUnions`，其余分类以清单的 current_layer 和 provenance 为准。

## 3. 框架能力差距与具体改造

| 能力 | 复用现有机制 | 拟补能力与文件 | 验收要求 |
| --- | --- | --- | --- |
| 定义/注册/稳定 ID | Case metadata、Catalog、Selection | `testing/Test/Descriptor.emlf`、`Registry.emlf`；扩展 `tests/Tests/Catalog.emlf` 与 JSON catalog，单一权威注册数据 | 每个可执行入口和每个逻辑 case 有唯一稳定 ID；源码 hash 不充当稳定 ID；重复/未知 ID 拒绝 |
| 参数化/生成测试 | parity 生成器、Core/HM/annotation oracle、backend matrix | `Test.Parameter`、`Test.Generator`；记录 generator version、seed、输入 digest、shrink trace、replay token | 同输入产生相同期望 ID 集合；生成失败不是零行成功；最小反例可复现 |
| 类型化断言 | Assert 与现有 literal/AST/type/trace oracle | 扩展 `Assert` 的 Eq/AST/Diagnostic/Exit/Signal/Trace/FileDigest/Matrix 比较；`Test.Expectation` | 负例必须在指定阶段被指定原因拒绝；任意非零退出不能满足“预期失败” |
| fixture 生命周期 | package/temp workspaces、native runner 清理 | `Test.Fixture`：suite/case scope，acquire/use/release，依赖注入和保留失败证据策略 | setup/执行/teardown 分别报告；异常/超时/取消都 join 子进程；清理失败不可吞掉 |
| 依赖构建/准备 | Package.Build、shared-candidate format 2、四 Port prepare 路由 | `Test.Plan`、`Test.Artifact`；复用现有 DAG，将 build/prepare/execute/validate 分离 | cache hit/prepare 不计测试通过；精确输入签名匹配后才复用；focused 不产生 full 资格 |
| 隔离/超时/取消 | Test.Process、native build runner、process supervisor | `Test.Adapter`、`Test.Deadline`；统一外层 deadline、child ownership 与 signal/exit 数据 | 崩溃/挂死/协议错误/取消/残留子进程有独立 outcome；外层进程退出与事件协议交叉验证 |
| 平台与 skip | 现有 OS 分支与 Windows 脚本 | `Test.Capability` 与显式 Required/Optional policy | 缺工具/平台不支持为 unsupported/skip+理由；必选 qualification 中不能变 pass |
| 异步 | 新 Async.Process、Task/Fiber、scope/completion API | `Test.Async` adapter，单调 deadline、scope 关闭/取消及诊断收集 | 虚拟/可控时序优先；真实进程边界保留；定时器误差不能被错误当性能或普适安全证明 |
| 并行预算 | native DAG、现行 jobs=1、共享 invocation limits | `Test.Resources`：CPU/memory/process/FD/exclusive-host leases | 嵌套并发共享预算；不为提速擅自提升 jobs；资源等待与执行超时分开 |
| 日志与诊断 | JSONL、stdout/stderr 文件、payload digest | `Test.Diagnostics`：结构化 assertion diff、阶段、原始日志索引与限量显示 | 保留完整原始数据；截断仅影响 UI；每条失败能追到 source/tool/config 与重放命令 |
| 结果/覆盖/证据 | Test.Runner schema v1、Coverage v1、Package.Verification、专用 verifier | `Test.Outcome`、`Test.Evidence`、`Test.Report`；版本化 envelope，保留原 payload | expected/observed 精确集合相等；无 missing/duplicate/stale/unknown ID；complete/pass/full 分开 |
| 重复采样与性能 | Benchmark engine、七样本/all-ten、immutable baseline、wall/CPU/RSS | `Test.Benchmark` adapter：warmup、样本顺序、环境、baseline、预算/统计/阈值 | correctness 与性能分别判定；保留全部原始样本/失败；不以最佳样本或九项替代十项 |

这些模块是拟新增设计，不是本次已实现文件。通用 `testing/Test` 层不得导入 compiler 专属模块，避免依赖环；compiler/oracle/scenario 实现留在 `tests/Tests/Adapters/*` 或现有 suite 模块。

### 实现时必须一起修改的注册与包文件

- `testing/mlf-package.json`：注册新增通用 `Test.*` 模块，保持库不依赖 compiler；`testing/README.md` 说明协议和兼容承诺。
- `tests/mlf-package.json`：每个 adapter 的 private modules/direct dependencies 和对应 suite binary；根 `mlf-package.json` 保留八个现有测试目标并让兼容命令转发同一计划。
- `tests/Tests/{Catalog,Selection,CompilerTests,Coverage}.emlf`、`tests/test-catalog.json`：统一描述符/选择/派发/集合验证。`Catalog.validate` 当前固定 11 个 unit IDs、六 campaigns 和部分单-family约束，不能只向 JSON 填入 native/async/SDK/perf 名称。
- `tests/Tests/{TestCatalog,FamilySelectionChecks,CoverageChecks}.emlf`：增加 schema/selector/full-vs-partial/重复与未知 ID 的故障控制，现有 controls 全保留。
- `tests/Tests/CoreRunner.emlf`、四个 Core partition registration、`tests/Tests/{BackendSuite,PortSuite,Corpus,Packages,PackageResolver,PackageReleases}.emlf`：按阶段把 action/matrix/scenario 的叶子定义接到正式 adapters，oracle 算法不移进通用测试库。
- `tools/release/*`、`.github/workflows/*`、`.github/actions/posix-qualification/action.yml`：依外部逐入口表迁移 selector/assertion/lifecycle；最终只保留 framework dispatch、平台 provision/上传和显式发布 wrapper。`tools/bench/`、`tools/profile/` 保留必要测量引擎，由 framework 明确管理 recipes/样本/判定。
- 任何新增 manifest/source 都重新生成并验证对应 lock；报告 envelope 可采用新版本，但原 `Test.Runner`/Coverage v1 payload 保持可读，版本不匹配 fail closed，不静默丢字段。schema 升级需提供 v1→新描述符 adapter 与至少一个兼容周期，最终期限在实施时确定。

## 4. 定义与适配器 API

以下为接口契约草图，不声称可直接编译；实现时沿用 MLF 现有类型/模块风格。

```text
TestId       = stable namespace + semantic name
CaseSpec     = { id, revision, kind, parameters, tags/axes, requirements,
                 fixture, prerequisites, expectedInventory, expectation,
                 cost, resources, deadlines, adapter }
Plan         = { catalogDigest, selectors, resolvedIds, platform,
                 nodes, policy, inputIdentities, coverageIntent }
Adapter      = describe -> plan -> prepare -> execute -> collect -> validate -> cleanup
Outcome      = Pass | AssertionFailure | ExpectedRejection | Crash | Timeout
             | Cancelled | ProtocolError | InfrastructureError | Unsupported | Skipped
Observation  = { caseId, variantId, stepId, phase, actualValue,
                 exit/signal, elapsed, rawEvidenceRefs }
Receipt      = { schema, runId, attemptId, source/tool/config identities,
                 expectedIds, observedIds, observations, cleanup,
                 status, complete, coverageScope, qualificationEligible }
```

`ExpectedRejection` 是经类型化 expectation 验证的观察，最终 case 可 pass；它不是将失败统一改名。`Timeout`/`Cancelled` 不可泛化为 pass。专门验证 supervisor timeout 的 case 必须明确“被测子进程 timeout”为预期数据，外层 case 自己仍须正常结束并验证回收。

`describe` 与 `plan` 不执行编译、下载、安装、bootstrap 或任意 test hook。`prepare` 可产生/复用经过身份认证的 artifact，永远不能独立满足测试覆盖。`execute` 的每个 child 由框架拥有；`collect` 保存原数据，`validate` 使用独立 expectation/oracle，`cleanup` 完成后才能封存 receipt。未来执行权限单独受任务授权约束；manifest 不可偷偷触发发布。

ID 规则：稳定 semantic TestId 与 source digest 分离；参数实例 ID 使用固定参数键排序+显式 seed/input digest；backend/OS/GC/profile 是 variant，不与逻辑 case 混淆。每次 attempt 有新 execution ID。alias 必须显式给出原 ID、共享执行的条件和理由；只允许同一验证路径内的等价执行共享，不能合并独立 oracle。

## 5. 各类测试的目标执行模型

| 类别 | 框架 adapter 与迁移规则 | 必保留语义 |
| --- | --- | --- |
| 普通 Case / Core / Harness | 先注册逐 action ID；旧 fatal IO action 进程隔离，再逐 family 迁移到类型化 Assert；禁止一次失败吞掉其余预期 ID | Core 四物理分区保持 partial，只有逻辑 union 精确完整才为 full；现有 family ownership 不重复 |
| 属性、生成、差分、负例 | Generator/Property/Negative adapters；原 runner/生成器作为明确 provider；负例指定 source/type/target/emission/runtime 阶段 | 原 HM/annotation 独立参考算法、counterexample 和 corpus seed；不能用候选编译器输出生成候选的期望 |
| compiler / target oracle / parity | CompilerOracle adapter； source compile、independent target check、interpreter/native observation 分别记录 | 固定 corpus/标签/alias 规则、frozen target 与独立 reference；未知/重复/缺失行 fail closed |
| runtime / native / async | NativeProcess 与 AsyncScenario adapters；C/Win32 payload 仍原生，新增内部 assertion ID/事件协议；先解析现有结构结果再逐项仪表化 | ABI、lifecycle、owner death、long-path、completion opacity、cancellation/join、negative controls；跨 OS 的运行不能互相替代 |
| package / cache / distribution | PackageScenario adapter，scenario 内有状态机 steps 和独立 workspace；fixture 与 artifact receipts 绑定 | resolver/source/checked-release 全 inventory、首次/replay/rebuild 次序、真实 checked interface 与失效边界 |
| backends | Matrix adapter，case 与 interpreter/LLVM rows 分离；事件/错误/emission-rejection 属 typed observations | 所有 family、零 row family 边界、预期 LLVM emission rejection、GC/trace/输出三方一致性 |
| port | Port adapter，四准备 DAG routes 与执行/独立 references 分离 | 25 fixtures、references、生成 inference 输入一致性；prepare/cache hit 不能替代实际执行 |
| fresh self-host / bootstrap | FreshStage adapter，空 artifact store、显式候选/种子 provenance、构建/比较/复核步骤 | fresh next-stage、LLVM/native bytes fixed point、不能复用候选冒充重建；bootstrap 本身不是普通缓存 case |
| tuple/list 与 guards 组合 | guards 保持 core-language；tuple/list standalone/native 迁为正式 family+variant，旧 CLI 转发；新增组合语义 inventory 单独审核 | annotationSymbol、guard lookahead、两种 Layout、七个 delimiter 和两个 guard AST oracle；现有测试不互相“去重” |
| source/CLI smoke | SourceSmoke/InstalledCLI adapter，固定轻量 import closure与可见 CLI route | source-interpreted candidate smoke 与已构建 binary unit 是不同路径；保留输出/诊断/seed 身份 |
| SDK relocation / release rules | Relocation/PolicyContract adapters；沙箱/mock 发布接口；真实包路径切换与消费者验证 | immutable tags、source/tool/依赖闭包、checksums、安装后 public entry route；测试中绝不执行真实发布 |
| performance / profiling | Benchmark adapter 管理 correctness、独占资源、七样本、baseline、threshold；profilers 为 opt-in Diagnostic 类型 | all ten、默认输入、独立正确性、fresh objects、真实 wall/CPU/RSS、失败证据；历史 profiler report 为资产不是 pass |
| CI policy / shell / PowerShell contracts | Policy adapter + typed matrix；原脚本先由框架启动，随后脚本只能当 adapter driver 或兼容 launcher | aggregate 对 failed/cancelled/skipped/missing 的 fault controls；脚本自身语法通过不代表 contracts 执行通过 |

特别的禁止执行约束：`tests/fixtures/async-gate/counterexample/incorrect-quantifier.emlf` 只允许编译/类型检查/检查拒绝证据，禁止 interpreter 或 native 执行；discovery/adapter 必须显式表达这个限制。`async-gate/check.sh` 的 representation proof 与 `async-completion/check.sh` 的 live completion gate 是不同验证路径。

## 6. 发现、选择与单一权威清单

沿用 `tests/test-catalog.json` / `Tests.Catalog`，选定一个权威数据源后生成另一种表示；不得让 JSON、MLF 和 workflow 维护互不校验的独立列表。现有分类轴（group/family/level/input/oracle/purpose 等）保持兼容，新类型与 capability/cost/profile 分开建模。

统一 discovery 输出包含：logical case、variant、dependency/prepare node、fixture/reference owner、script driver、archive 的区别。只有 case/variant 会贡献相应 coverage；helper 文件和构建 node 不增测试数。注册表引用 manifest target 的身份，不复制一份 build target 定义。

所有 selectors 先生成 immutable Plan，展示 resolved ID 集合与 digest。未知 selector、重复 ID、必选零匹配、缺少 required capability 拒绝执行；有意选择零 row 的合法 contract 用显式预期表示，不混同 selector 错误。full campaign 不接受仅挑选局部 family 后“补标签”变 full。

未来入口形式建议为 `./mlfpkg run compiler-tests -- list|plan|run ...`（具体 CLI 语法实施时扩展已有命令，不在本次承诺已支持）。现有 `unit/packages/parity/backends/port/self-host`、family flag 与 root `mlfpkg test` 继续兼容并转发到相同 Plan；不能旧入口和新入口各执行一遍。

## 7. 调度、fixture、资源与失败模型

- DAG 节点具有 build/prepare/test/validate/cleanup 类型；artifact 输入含 source tree、module closure、manifest/lock、compiler/native tool、runtime、flags、environment allowlist 与 platform digest。
- 重用现有 native runner、Package.Build、shared-candidate authentication 和 Async 的 scope/process 限额。多层 scheduler 使用同一预算和 ownership，禁止嵌套各开 N 个进程造成 N² 并发。
- 普通 case 可并行；共享可变 cache、package scenario、fresh self-host 使用隔离目录/串行步骤；性能持有独占 host lease。现有 build jobs=1 保持到有实测依据；成本估计不能直接提升并发。
- fixture acquire/setup/execute/teardown 各有 phase 结果。取消先停止 admission，再取消并 join 当前 children，收集日志后 cleanup。外层超时要给 cleanup 有界 grace；真实 cleanup 失败独立保留，不能用原 assertion 覆盖。
- 不支持平台/依赖缺失与 assertion failure 区别显示，但 required profile 中都不能满足 gate；optional dev skip 需可审计理由。预期 negative、expected signal 必须绑定 phase、具体错误/状态和独立 verifier。

## 8. 统一结果与证据

继续保存 `Test.Runner` JSONL、`Tests.Coverage`、package/build receipts、Port/parity/backend/performance 专用 payload 和 verifier。新 envelope 对它们建立索引和约束，不靠读取一句“passed”重新构造证据。

最小字段：schema/version、run/attempt/parent IDs、catalog/plan digest、requested/resolved selectors、source commit+dirty tree digest、manifest+lock/native inputs、compiler/manager/tool/dependency identities、platform/capabilities、phase/command、actual outer exit/signal/deadline、expected/observed IDs、oracle metrics、raw artifacts 路径+hash、resource telemetry、cleanup status、complete/pass/scope/qualificationEligible。

`complete` 只表示本次选择契约已终结；`passed` 表示所有必选判定通过；`full` 表示 expected universe 精确完整。它们互不替代。丢失、重复、未知、out-of-order 非法事件、提前退出、stderr/exit 不符、坏 hash、复用陈旧证据或未完成 cleanup 均不能被聚合器静默忽略。

报告先显示失败/未执行与复现命令，再给 family/campaign/adapter/platform 层次。逻辑 case 数、参数 variants、subprocess 次数、assertions、oracle observations、样本数分别展示，不将一个多 backend case 的两次执行混成“一条测试”来掩盖覆盖变化。

## 9. CI 策略：共用实现，不混淆门槛

- **PR/merge queue**：保留当前 metadata、native/source smoke、Windows runtime、build-runner、async-runtime、async-language 六个 required prerequisites。async-language 已包含真实 bootstrap 与四个 async gates，不能将当前整体 gate 宣称为纯廉价检查。未来加速须另有等价覆盖证据。
- **Main qualification**：选同一注册表的完整六组 POSIX campaigns、Windows 所要求的 native qualification、直接 CLI/package-cache 及 all-ten benchmark；完整矩阵和所有子任务必须成功，skip/cancel/missing 失败。
- **Release/rehearsal**：选取完整 qualification + SDK packaging/relocation/policy validation；发布 wrapper 独立做显式授权和 immutable existing tag 校验。`build_packages=false` 的 main 不发布。
- **Performance**：同一 benchmark cases 的独占环境策略与阈值配置；correctness pass 不满足性能验收，历史 report 不满足当前字节资格。

共享 profile 声明应由一个经 schema 校验的数据源产生/验证工作流使用的 ID。CI `needs`、permissions、timeout、platform provisioning 是外部策略边界，框架提供 plan 与 verifier，workflow 不再复制测试逻辑。release reusable graph 必须显式声明是否消耗 async gates；不能声称依赖未实际连接的 sibling job。

当前组合后的明确覆盖缺口：tuple/list 的两个 root test targets 不属于六个 `compiler-tests` campaign 的自动 coverage union；不能仅因六组 receipts 完整就认定这两个目标执行过。release reusable qualification 也不自动继承 `CI` 的 sibling async-language job。P0/P6 必须把这些入口逐项纳入同一 profile 注册表并证明 job/receipt 依赖连通，不能靠命名“complete”覆盖缺口。

## 10. 分阶段落地与验收

| 阶段 | 具体改动/依赖 | 完成条件与回退 |
| --- | --- | --- |
| P0 冻结基线与追踪 | 合并代码确认后，导出完整入口/fixture/family/case inventories；补每个 script 内部 ID；记录 reference/archive 边界；建立迁移 JSON schema | 每项 old ID/入口/资产都有目标或审核过的非测试理由；unknown 为阻塞项；本次只生成静态初稿，不声称动态基线完成 |
| P1 框架契约 | 新 Descriptor/Registry/Outcome/Expectation/Evidence；兼容 schema v1；扩展 Case/Assert/Runner、catalog contracts；构造重复/坏事件/skip/timeout/取消 controls | 所有故障类型不能变 pass；旧协议 consumer 可读；无业务 suite 迁移前先证明契约 |
| P2 生命周期与执行 | 新 Adapter/Fixture/Plan/Resources/Capability/Diagnostics；接 native runner 和 Async；typed subprocess/native/scenario API；保留 serial defaults | setup/teardown/owner death/超时/取消/日志故障 controls；所有 children join；不降现有监督器保障 |
| P3 第一批完整迁移 | IntSetUnions/framework 已接入用作兼容锚；Core/Harness 按 family 逐项；tuple/list、guards 与组合 inventory；source/CLI smoke 与 policy contracts | 每个旧 action 有新稳定 ID/expectation；新旧 expected/observed 集合逐项一致；旧 CLI 只转发；每次仅一个实现执行 |
| P4 原生/异步/包 | native/runtime/Win32/async language+checked package；resolver/integration/release/cache scenarios；C 内部 assertion 协议 | 原 lifecycle、opacity、negative、long path controls 全映射；script 单一 umbrella pass 不足；平台能力缺失明确阻塞对应 gate |
| P5 完整 compiler campaigns | parity、backends、port、independent oracles、fresh self-host；复用现有 runner/prepare/fixed-point verifier | 精确 case/family/row/alias/reference union 不变，所有准备和执行阶段齐全；独立 reviewer 验证 evidence；后续单独授权全量资格测试 |
| P6 SDK/性能/CI 全收口 | SDK relocation/tag/publish mocks、Benchmark adapter、profile 数据与 workflow generated/validated selectors | 全十项七样本及阈值不弱化；主/发布/PR 不维护不同测试实现；真实发布动作仍外置；所需平台后续执行认证 |
| P7 退休旁路 | 删除旁路选择/判定逻辑，仅保留命名兼容 launcher→framework；原 native/reference 引擎归 framework driver 所有；文档迁移 | 静态 entrypoint audit 无未管理测试入口；旧命令行为兼容+去重控制；暂不删历史资产/独立 oracle。删除任何旧文件应在单独实现 PR 审核 |

可并行工作：P0 inventory 与 P1 协议设计；P3 各独立 family 迁移可并行，但共享 ID/schema/runner 由单一 owner 合并。P4/P5/P6 都依赖 P1/P2；不能为了赶 CI 改 workflow 先绕过未完成 evidence validator。

双轨期间的“比对”有两种：复用同次 raw observation 分别跑 legacy/new validator（廉价，先做）；确需验证执行等价时在隔离空间各跑一次并明确标注 validation campaign，正常 CI 不双跑。迁移 ledger 记录每个入口 active implementation=legacy|framework，唯一 dispatcher 防止双跑；切换失败只回退 dispatcher，不删除旧 evidence。

## 11. 可机器检查的完成标准

1. `old_entrypoints == mapped_old_entrypoints`；每个可执行旧入口恰有一个 active dispatcher/正式 adapter 或经审核的 non-test 分类；无空 target/owner/pending/unknown。
2. `old_fixture_ids == mapped_fixture_ids`，reference/oracle provenance 与内容 digest 保留；同名不同内容 fixture 不合并。`test/fixtures/figure12-a8.emlf` 与 `tests/fixtures/figure12-a8.emlf` 必须分别登记。
3. 对每个 suite/profile/platform，`expected_case_ids == observed_terminal_case_ids`；multiset 数量一致，无重复/丢失/新增未知；alias 经显式规则验证。family union、Core partitions、backend rows、Port fixtures、parity corpus 均独立校验。
4. Outcome truth-table 覆盖预期拒绝、错误 phase、timeout、cancel、signal、bad protocol、missing child、failed setup/cleanup、skip/unsupported、corrupt/stale evidence；required gate 只接受符合契约的通过。
5. 脚本/workflow 入口静态扫描与允许清单一致：测试命令经 framework plan/execute/verify；兼容 launcher 不另作 selector/assertion；真实 publish 命令仅在 release wrapper 的 allowlist，不能从 test adapter 调用。
6. source/tool/config/manifest/lock/runtime/dependency 改动均使不适用的 evidence/cache invalid；source dirty 状态明确，不可只记录 commit 而忽略修改文件。
7. legacy 与新 adapter 的固定输出/诊断/exit、leaf IDs、oracle metrics、raw evidence hashes 的差异有审核理由；不能靠修改 golden 使迁移通过。
8. 所有 required OS/arch/profile 的执行验收通过后才宣布“全部接入完成”；静态 mapping 完成只允许声明“规划/注册覆盖完整”。

## 12. 风险、未知项与决策

默认保留 MLF 框架为权威、现有原生 engines 为 adapter、所有历史覆盖、现有平台与阈值、serial build policy。无需因普通文件布局选择阻塞当前规划。

需要后续确认/测量的语义项：required 与 optional capability 的矩阵（尤其哪些 Windows compiler-language routes 是正式保证）、PR 延迟预算是否允许调整 async gate、性能 noise/统计策略是否保持现行规则、失败 artifacts 的保留配额、property fuzzing 的固定 CI seeds 与额外 soak 策略、public `Test` API 与报告版本的兼容期限。这些在未决定前按现有行为保守继承，不降低门槛。

主要风险：Case 改写改变求值/懒性或退出边界；同一 fixture 在不同 oracle 路径误删；matrix 行数被 umbrella receipt 隐藏；nested scheduler 超售资源；bootstrap 自举形成循环依赖；被测框架自身失败被误当 suite failure；benchmarks 被并发或不同依赖污染；Windows 能力未执行却被跨平台标记完成；旧脚本兼容层长期演变为第二实现。

缓解：先冻结 inventory/expectation，再分 family 切换；框架自身通过独立原生协议 controls 验证；per-path oracle provenance；full/partial 与 phase 的强类型限制；所有重验证单独取得执行窗口，保留失败证据。

## 13. 验证分层与成本

| 层 | 命令/方式 | 预计成本与当前状态 |
| --- | --- | --- |
| L0 静态 | `git diff --check`、冲突标记/未合并 index、manifest/lock 哈希与 graph、JSON/YAML 解析、`bash -n`、清单路径/唯一 ID 校验 | 秒到分钟；本次只执行此类，实际结果列入整合报告 |
| L1 框架契约 | 现成轻量 protocol/validator fault controls；已构建 runner 的 focused framework/selector controls | 通常秒到数分钟，但若须先构建 native runner 则另计；本次未运行 |
| L2 目标语义 | guards+tuple/list 组合、async 生命周期、selected native/package/Port family；必须使用组合树匹配 compiler | 构建可能数十分钟，执行由选中集合决定；后续授权后先列 exact plan 与估算 |
| L3 完整资格 | locked candidate build、完整 unit/packages/parity/backends/port/self-host；按已有六组 entrypoints | 数十分钟至小时，受机器/缓存影响；本次明确未运行，不以 PR 历史结果替代 |
| L4 平台/性能/发布验收 | 全平台 main graph、all-ten 七样本 benchmark、SDK relocation、fresh bootstrap/release rehearsal | 长时独占资源/多平台；本次不触发本地或远端任务；真实发布仍需单独明确授权 |

未来每次执行先保存 exact selection plan、source/tool/config identities、资源和超时预算，再执行并存 raw receipts。`tools/release/check.sh` 会运行多个回归，不能将其称为纯静态检查或在本次无条件运行。缺少 actionlint/其他工具时记录未执行，不安装工具来掩盖限制。
