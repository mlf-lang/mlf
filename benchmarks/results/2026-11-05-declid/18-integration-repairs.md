# 18：集成验收修复记录

本记录覆盖以 `796aaf8b089d532c01779e46a57773123c4d0214` 为源码起点的 46 个文件、36 项集成修复。固定对照为 `726cd256aa90d3e8cf596842fbb29515c1bc5249`。逐项机器记录、源码 SHA、基线复现范围与完整证据 SHA 见 [修复 ledger](18-integration-repairs.json)。

本清单聚焦 unit、packages 和 backend。Port 的 25 个原夹具另经正常 crate 编译、LLVM 链接及原生执行预检，保留各自的独立 golden 与预算；正式全源码准备路径仍由最终根包 port 门槛验证。Parity 用独立 sidecar 记录 179 项源码 API 迁移，原始归档不变，并保留旧行认证、未知字段及篡改负控；实际 7,086 行导出预检与最终根包 parity 运行分别记账。

后续 CI 来源检查另有四项配套修复。Core 组成检查从原始冻结源码重建精确的前端入口改动，保留 746 个动作；完整 Linux release 检查链通过。Patricia 维护工具按已认证的完整来源清单识别 owner，覆盖位于 `tests` 的注册模块；原 75 项测试和历史 oracle 不变，77 项控制及正常 raw O2 的相关完整控制链通过。Figure12 保留旧语义 allowlist，以有限转写恢复并认证旧源码；独立 Direct visitor 同时拒绝 resolved ID 输入。真实 Direct 与原生路径的 79 个 coverage ID 一致，包含原 43 个标签（41 次执行和 2 个共享别名）、36 项辅助检查及另列的 4 正/7 负阶段控制。最后，`tests/mlf-package.json` 的 `references` 目标补入新增 import 所需的 `Tests.CoreHelpers`；其余目标与预算不变，所有目标的闭包、offline lock 和 locked plan 均通过。这些维护预检仍不替代最终源码上的完整验收。

这些结果来自保持输入不变的分次预检。真实测试动作、正常 raw crate 编译、公开编译器控制与独立数值 oracle 分别留有回执；它们合起来说明已定位问题的修复效果，不能记成一次最终全量通过。最后一次正常安装、锁与来源审计、性能配对、完整 unit 及原生八组门禁仍须在冻结后的同一源码上执行。

## 必需的生产修改

`libraries/mlf-frontend/Bootstrap/Layout.hs` 修复显式分号后的退缩进处理。旧谓词把分号后的整个换行处理跳过，导致嵌套 `do` 块留在错误作用域；分号是否重复与 dedent 是否执行是两个条件。修复保留 offside 的分号去重，仅让换行继续执行 dedent。原 17 组布局对照及 4 组分号控制通过。

`libraries/mlf-developer-tools/Package/Benchmark.hs` 的 Machin π 参考结果使用显式 `Integer` 运算。现有 `Int` 是有符号 64 位，原参考计算的幂会回绕，无法作为 30/50 位 π 的独立答案。补丁保留算法、位数与实际 benchmark 的 bounded 运算，只把参考计算换到 `intToInteger`、`mulInteger`、`quotInteger` 等明确原语。原生实现有独立的 `BIG_INTEGER`/GMP 路径；源码链审计与私有 GHC Harness 55 项通过，最终原生 Harness 的原断言仍是必须执行的门槛。

其余记录涉及测试 fixture、独立 oracle、测试 driver、元数据或真实 example 的现有源码 API 适配。生产 solver、`T.alphaEq`、全局 SourceEquality 及后端优化实现保持原契约。

## Oracle 与覆盖边界

- 布局比较只规范化物理文件/坐标，保留调用点标签、包/模块、wrapper、签名与所有权。Figure12 的源码 oracle 对 resolved ID 节点显式拒绝，保留原 43/36 断言及逐构造器控制。
- Int64 输入、IEEE-754 舍入、负零位表示和构造器 ABI 各有独立数学、C 或固定 ABI 控制。不得通过越域 literal 的回绕制造“通过”。树分配的错误 tag、boxed 正控及原布尔/损坏负控保留。
- 二进制对象通过真实 reader 读取；旧文本 codec 仅对显式 legacy 投影做 roundtrip。missing/stale/corrupt/forgery 的拒绝路径和原字节恢复均保留。
- GraphSolver 第 7 项的旧失败在 726/796 完全一致：嵌套 scheme 中的 `[] a85956` 与 `[] a84626` 都引用原 owner `32292` 量化的变量。新 oracle 先从每个原始节点建立一个全局双向结构/owner 对应，再检查全部自由变量覆盖及词法 alpha 等价。它拒绝跨 scheme 的 split/merge/swap、skolem 身份变化和变量捕获；仅允许独立证明为 closed、全 rigid 且处于变量 owner 闭包之外的 ground 结构改变分配/共享布局。
- 新 alias-path 守卫是测试 comparator 的终止/输入域要求。原辅助控制错误地假设生产 validator 会拒绝孤立 alias 环，失败已保留；这不构成生产 validator 回归结论。
- Backend 库存来自实际枚举的 541 个唯一动作和 50 个非空 family。严格 593 rows 由原动作的执行次数独立推导；PRSmoke 仍选择 12 个唯一原动作。元数据同步没有降低 guard，最终完整运行必须验证该总数。

## 已完成预检的范围

GraphSolver 8 个原动作分别通过：17,177 次完整 inference 图比较、2,701 次 witness 图比较、49,548 个原 Gen scheme 比较。第 7 项修复后的真实 eMLF 动作包含全部新正负控及原 9 个 fixture；其余 7 项源码逐字未改并沿用此前实际完成的运行。GraphUnification 3 项与 EmbeddingPruning 3 项通过，原 CoreSolver 的 19 模块正常 raw consumer 编译通过。

其他已有回执包括 Harness 55、Typeclasses 78、语言各 family、CoreModules 的 Modules 83/Separate 86/State 70/HM 6,703/annotations 126/16 examples，以及相关 crate、package 和 backend 原动作的分组重跑。Package 79 个 coverage ID 是两次明确区分的运行之并集。部分私有 GHC 桥为固定 guest `Int` literal 赋予等价 host 数值默认类型；这些桥只存在于诊断转换产物，没有进入 repo 源码。完整基线/修复范围与局限逐项记在 ledger 中。

## 逐项记录

表中源路径相对仓库根目录。最后一列给出代表性回执的 basename 与 SHA256 前缀；完整 SHA、同项其他回执和确定性归档 key 在 ledger 中。归档 key 为后续独立 evidence branch 的拟定路径，当前文档不宣称证据已发布。复现依照 `CONTRIBUTING.md` 与迁移计划的正常入口，并绑定最终 source/install/runner 回执；本机临时绝对路径不是可复现依据。

| 项 | 修复与保留边界 | 源文件 | 代表回执 / SHA256 前缀 |
|---|---|---|---|
| 01 | 显式隐藏 Prelude 的 Eq/fail，保留测试 Eq 及 (==)。 | `tests/Tests/Basic.emlf`<br>`tests/Tests/Helpers.emlf` | `receipt.json` · `99060292810db121` |
| 02 | 为仅用于 length 的错误标签表写明 String 元素类型。 | `tests/Tests/NativeABI.emlf` | `minimal-controls.json` · `3c9a4290fafe6c4f` |
| 03 | 把身份集合 fixture 转到 IntSet API，保留元素及 max+1。 | `tests/Tests/CrateQueries.emlf`<br>`tests/Tests/Separate.emlf` | `results.json` · `07f174dd3dbbbe1e` |
| 04 | 用 Rank.indexMap 显式包装受测树；独立 Map 期望值不变。 | `tests/Tests/ComponentProjection.emlf`<br>`tests/Tests/ProjectionRanks.emlf` | `final-receipt.json` · `d30eb085d918b7e6` |
| 05 | Figure12 源码 oracle 显式处理新构造器；拒绝把 resolved ID 节点当源码名字。 | `tests/Tests/Figure12.emlf` | `validation.json` · `20b23c549f0fd469` |
| 06 | 先完成正常前端阶段，再向 solver 提供约束；独立参考求解不变。 | `tests/Tests/CoreHelpers.emlf`<br>`tests/Tests/CoreSolver.emlf`<br>`tests/Tests/GraphUnification.emlf`<br>`tests/Tests/GraphSolver.emlf`<br>`tests/Tests/EmbeddingPruning.emlf` | `results.json` · `e03c6a0870d62c65` |
| 07 | 显式分号后仍执行 dedent，修复真实 Layout 控制流。 | `libraries/mlf-frontend/Bootstrap/Layout.hs` | `receipt.json` · `70577f21f3ff782f` |
| 08 | 布局比较仅忽略物理文件和坐标；保留调用点标签、owner、wrapper 和类型签名。 | `tests/Tests/Helpers.emlf`<br>`tests/Tests/Readability.emlf`<br>`tests/Tests/Guards.emlf`<br>`tests/Tests/SurfaceSyntax.emlf`<br>`tests/Tests/Datatypes.emlf`<br>`tests/Tests/Modules.emlf` | `receipt.json` · `fc209383ff43f0b8` |
| 09 | 为 command 字符串模式 fixture 声明 String -> Int。 | `tests/Tests/Readability.emlf` | `runtime-results.json` · `c285009bcd136871` |
| 10 | 把旧 let rec / IO Unit fixture 更新到现有 let / IO () 契约。 | `tests/Tests/Readability.emlf`<br>`tests/Tests/Guards.emlf` | `runtime-results.json` · `38988bfa46cc1a8e` |
| 11 | 保留 primitive constructor 负例，并分别断言 standalone 重命名与三条拒绝边界。 | `tests/Tests/Datatypes.emlf` | `receipt.json` · `ede40f960a8fddfd` |
| 12 | 更新 intrinsic unit fixture；保留显式名义 Unit 负控。 | `tests/Tests/Datatypes.emlf`<br>`tests/Tests/CrateCodegen.emlf` | `runtime-ghc-fixed-v3-result.json` · `ef0d53eca6cfecb8` |
| 13 | 先读真实二进制对象，再显式投影 legacy codec；保留当前损坏对象拒绝。 | `tests/Tests/CrateCodegen.emlf` | `runtime-baseline-after-result.json` · `fd1aaa720288d731` |
| 14 | 校验 NoPrelude、Primitive 注入与真实 Entity/Global/符号/调用点所有权。 | `tests/Tests/Modules.emlf`<br>`tests/Tests/Helpers.emlf` | `receipt.json` · `385787aad3f1ff90` |
| 15 | 三条实际 backend 消费的 state worker 改用 ST s ()，保留 LLVM 断言。 | `tests/Tests/StateCases.emlf` | `results.json` · `cae7698463004262` |
| 16 | 修复真实 multiparameter example 的表达式 :: 注解。 | `examples/multiparameter.emlf` | `runtime-result.json` · `626a1988d55cf511` |
| 17 | 修复真实 snake example 的两处 IO () 签名，保留自定义 List。 | `examples/snake.emlf` | `diagnostic-receipt-v2.json` · `73ae28ac769b59ed` |
| 18 | Machin π 参考 oracle 使用显式任意精度 Integer 原语。 | `libraries/mlf-developer-tools/Package/Benchmark.hs` | `shared-check.json` · `4281d19fe328db00` |
| 19 | C runtime fixture 使用有效 Int64 输入并验证 boxed 正控；保留布尔和负控。 | `tests/native/runtime_values.c` | `results.json` · `9aa79b5833e68c64` |
| 20 | 树分配审计使用明确 ABI 的 Tree.Node tag 69+1，并保留 wrong-tag 负控。 | `tests/native/benchmark_allocations.c` | `summary.json` · `326cabe8bb3983f4` |
| 21 | 仅移动 Prelude fixture 四个右括号，恢复原 32 个表达式的 append 结构。 | `tests/Tests/PreludeTests.emlf` | `receipt.json` · `6084522f1b03e1d7` |
| 22 | 给 NumericArrays 的 ops 与 prefix 明确字符串类型。 | `tests/Tests/NumericArrays.emlf` | `receipt.json` · `aa9ab55a41391315` |
| 23 | 给 BootstrapPrimitives 的 decodeDouble 输入及 contents 明确字符串类型。 | `tests/Tests/BootstrapPrimitives.emlf` | `receipt.json` · `33dd620226f848ea` |
| 24 | 严格同步 541 fixtures、50 families、593 预期 rows 与 PRSmoke 原 12 个选择。 | `tests/Tests/BackendSuite.emlf`<br>`tests/test-catalog.json`<br>`tests/Tests/CompilerTests.hs`<br>`tests/Tests/PRSmoke.emlf`<br>`tests/README.md` | `receipt-v1.json` · `36bb44e5cebcc51a` |
| 25 | 为被 generic shadow 丢弃的 quiet literal 注明 String；空输出 oracle 不变。 | `tests/Tests/IOTests.emlf` | `receipt.json` · `9585312d861988b0` |
| 26 | SeparateBackends 使用二进制读写快照；保留 missing/stale/corrupt/restore 断言。 | `tests/Tests/SeparateBackends.emlf` | `receipt.json` · `2450ffc3ba08689f` |
| 27 | Backend fixtures 改用 intrinsic ()；两个真实 driver 入口改用 []/(:)。 | `tests/Tests/ModuleBackends.emlf`<br>`tests/Tests/NumericArrays.emlf`<br>`tests/Tests/BackendCases.emlf`<br>`tests/Tests/ByteArrays.emlf`<br>`tests/Tests/BootstrapPrimitives.emlf`<br>`tests/Tests/DNA.emlf`<br>`tests/Tests/PRSmoke.emlf`<br>`bootstrap/RuntimeDriver.emlf`<br>`bootstrap/LLVMDriver.emlf` | `independent-static-review.json` · `a2dea3157c420726` |
| 28 | 区分 recursive do-let 的内外绑定名；保留 ordered-scope 的原输出。 | `tests/Tests/BackendCases.emlf` | `receipt.json` · `0d1d63df6d4c04fb` |
| 29 | 给 Cell/saved 绑定具体类型，使共享值脱离字典抽象；全部结构断言保留。 | `tests/Tests/ConstructorProjection.emlf` | `receipt.json` · `e26928bed374f814` |
| 30 | raw Codegen fixture 构造完整 69 项 builtin 前缀并验证固定 ABI 槽。 | `tests/Tests/EnvironmentAccess.emlf` | `receipt.json` · `a9a478dbaa3efbd8` |
| 31 | PackageReleases 以原始字节保存、恢复二进制对象；所有 forgery 断言保留。 | `tests/Tests/PackageReleases.emlf` | `receipt.json` · `3c1d4a2d72e1303b` |
| 32 | Bytes fixture 使用有效 Int64 边界及独立 IEEE-754 舍入 oracle。 | `tests/Tests/ByteArrays.emlf` | `receipt.json` · `2cca59eb528dd02a` |
| 33 | Module CLI 表达式改用 ::，保留完整复合 action 与最后三条拒绝路径。 | `tests/Tests/ModuleBackends.emlf` | `receipt.json` · `cb9aec8e6150ff66` |
| 34 | 负零 doubleToBits 的 Int64 oracle 改为 -9223372036854775808，仅增一个负号。 | `tests/Tests/BootstrapPrimitives.emlf` | `receipt.json` · `7e3eed60dd5f87ec` |
| 35 | primitive-callback 的数值条件用 eqInt，保留全局零 generic-call 强断言。 | `tests/Tests/HigherOrderSpecialization.emlf` | `receipt.json` · `6af23ab23fc76d1f` |
| 36 | 从原始节点建立全局受约束图对应，恢复 scheme 的真实 ambient 身份上下文。 | `tests/Tests/GraphSolver.emlf` | `receipt.json` · `981a2fad5362cee8` |
