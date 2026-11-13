# r15 ordinary paired VALIDATE → BENCH

这是已落盘供独立审阅的 runner，不是已通过的运行结果。本交付未启动 compiler、
controller、guard、fixture 或 benchmark；只做 Python AST 静态检查。
`complete=true` 的有效运行结果必须是对应 work 下的 `stages/PHASE/final.json`，
不能只看 worker receipt。

代码固定在 N/validation；输出根必须由 admission.work 显式指定为
`N/validation-runNN`（例如 run01）。每次失败保留旧 work、claim、输出和清理证据；
需要重试时建立新 run02，不删除/复用旧 claim，不重跑两个已认证 ordinary producer。
任何 fixture 修正都需新 SHA、独立 review、新 admission；不能改动一个已准入运行的代码或输入。

## 固定边界

- A：R/source，f9bdb40a659bfdff4cbb782d438afbb0417dd2e1；
  B：N/source，8433ca438213516118ce9079adf9db0cb91188bc。
- 这是普通 GHC producer 的 paired benchmark，**不是 native-generation A/B 或固定点**。
- VALIDATE、BENCH 分别 600 秒，分别 SHA-bound approved admission 和 one-use claim。
- 原 I/guard.py 文件哈希固定，outer guard 使用 N/coordination/lock-epoch.json，
  共享 R/heavy flock 和 candidate reproduction flock；worker 调用原 verify_worker_scope。
- 原 guard LIMITS 保留：6 GiB address-space、5 GiB tree RSS、5 GiB free disk、
  3 GiB host available、4 GiB output。工作命令均 run_child；
  编译/链接和每次样本最多 180 秒，并裁切到 outer 剩余预算。
  fixture 执行最多 90 秒，CLI/show 最多 30 秒。原认证器的只读 git 查询位于 outer 期限内。
- 无自动下一阶段、无自动重试、无覆盖旧运行、无放宽清理或隔离门。

## 源码/producer 真实性

每侧独立加载未改的原 oracles，仅把该实例 BASE 绑定对应 reviewed commit。
原 authenticate、137 modules / 13 executables / 284 objects/interfaces、
原 packages/optimization/demand flags、bootstrap-only 验证不绕过。

同时核对两侧自己的 handoff、BUILD/CONTROLS controller、outer final cleanup、
watchdog、原 producer receipt、五条真实 CLI stdout/stderr、94 非 Main 闭包、
C 源码/对象/原命令和原 Emlf Main。启动和结束重验 producer/source/package/executable
哈希；样本命令之外核验二进制和参考数据。两侧 toolchain、已安装 dependencies 与
package database 哈希必须一致。

## VALIDATE

两侧分别构建独立 Main：
1. EncodeInputReuse.hs：pure 18 个完整 case-id + summary；publication 四个完整
   case-id + summary，使用全新不存在的绝对根。
2. QueryIndex.hs：仅 pure 与 publication，精确匹配仓库既有的四行/一行输出。
3. ArtifactBinary.hs：仅 root-bounds，精确 `PASS root-bounds\n`。
4. 只在 B 构建 EncodeFirstFailure.hs，运行两个小型控制：
   首次编码 Left 不求 poisoned children/key/session，以及成功的完整 session/payload bytes。
   精确匹配两条 PASS 和 `SUMMARY\t2\t2`。
5. 两侧从各自原 Emlf Main 单独编译新的 Main.o/Main.hi，再链接 ordinary 测量二进制；
   对这些新二进制重跑 version、identity、42、Unicode、type-rejection 五项真实 CLI 控制。

所有 fixture/原 Main 均使用 one-shot `-c`，独立 `-o` 和显式 `-ohi`。
接口搜索只走本侧已认证 objects，hidir 指本侧 producer objects，odir 指新目录。
绝不使用 producer 最后留下的 Main.o/Main.hi，绝不混合 A/B 对象。

EncodeInputReuse 唯一额外 package 是已由原 installed_dependencies pin 的 filepath。
其他原 package/optimization/demand flags 不变。维护 fixture 不添加 filepath。
ArtifactBinary 在本侧认证的94闭包基础上仅追加 Package.Distribution 和
Package.Release 的 .o，连同其 .hi 校验；fixture链接范围96模块。
其他 fixture/ordinary Emlf 使用94闭包，均附原 host.o/supervisor.o。
不编译新项目模块，不运行 ArtifactBinary constructors 或 native 全套。

EncodeInputReuse 初始批准 SHA：
`a379a3b2313c0c52affcfed0bd6144f0962f4201b5e89b6d7f0caa2e43db3e95`。
EncodeFirstFailure 初始 SHA：
`50e50cec9ac764dd12d9b4990c4dda7bf559e5c2c6f3ba6a95e52a19cbaec604`。
实际准入的 fixture inventory 必须与独立 review 中的完整 SHA map 相同；
这允许经审查修正 fixture 后新建 run，而不更改冻结 compiler source。

这些控制不证明 OOM、异步取消或假设的第二次 IO 失败等价，也不冒称完整
Haskell/native 回归已通过。本 runner 没有加入额外 Python 维护套件。

## ordinary RTS 与 BENCH

ordinary 二进制不加 -prof、SCC probe 或 profiling flags。
链接使用 `-rtsopts=ignoreAll` 与 compiled-in
`-with-rtsopts=-s<work>/active/A.stats`（B同理）。
GHCRTS 必须为空；每次此类二进制运行的 stats 必须初始不存在，
由原子 guard 归档到本条命令目录。所有CLI也归档/解析统计，但不进入性能样本。

BENCH 先验证本 work 的 VALIDATE worker、outer final cleanup 和 final.json，
再复验所有验证阶段 immutable outputs。使用已认证 r14 fixed builtin W 的两个
artifact；用原 O.foundation 检查 R/source 的固定14模块/173594 bytes。
工作负载标签是 compiler-shapes/foundation14，实际 crate identity 沿原 O.IDENTITY：
`fresh-split/compiler90/mlf-foundation`，spec字段配置与r14 ordinary-Q一致，
仅每个样本的 queries/output prefix 使用全新目录。

固定 ABBA×3，无隐式热身，A/B各6次。每个样本均：
- 新空 queries、新 prefix，无跨样本 cache 复用；
- 原 guard 保存 stdout/stderr/command/实际输出/cleanup；
- 475 fresh、0 reuse、完整 ordered queries；
- 所有14 owner及固定 builtin依赖；
- .mlfci/.mlfco/.queries 三份 raw bytes 与 r14 ordinary-Q 完全相等；
- 原 POSIX query-lock 重新获取检查；
- 保存 guard wall、原 parser 解析的 ordinary RTS allocated bytes。

失败即停止。只有12个样本完成、全部终检和 outer cleanup 成功后，launcher 才在
final.json 中写 median、6组相邻配对（AB/BA方向归一）的比值和变化量。
guard wall 与 RTS整进程分配分domain报告，不等同于 profiling exclusive attribution，
不推断统计显著性、native性能或所有工作负载的通用加速。

## 审阅与启动接口

所有命令都使用 `/usr/bin/python3 -B N/validation/controller.py`。

1. `inventory`：仅输出待review的 code_pins/fixture_pins，complete=false。
   审阅后由协调者写独立 JSON，至少包含：
   `{"complete":true,"code_pins":{...},"fixture_pins":{...}}`。
   不把 inventory 自身视为完成审查。
2. `draft VALIDATE --work N/validation-run01 --review REVIEW.json --output ADMISSION.json`
   创建新的 work 目录和**approved=false**草案，不执行工作。
3. 协调者核对完整草案，依据现有用户授权设 approved=true，计算最终文件 SHA-256；
   然后 `run VALIDATE --admission ADMISSION.json --sha256 SHA`。
4. 确认 VALIDATE 的 final.json 和外层 cleanup/leaseclear 后，
   `draft BENCH --work N/validation-run01 --review REVIEW.json --output BENCH.json`。
   单独审阅批准并重新计算该阶段 SHA，再 `run BENCH ...`。
5. `_worker` 仅供原 guard 直接子进程调用；直接运行将被身份/租约门拒绝。

admission 捕获 work、环境（只将原TMPDIR改为work/tmp）、Python、epoch/locks、
两个 handoff、完整 code/fixture/reference SHA map、两个固定commit、ABBA序列，
以及 BENCH 所需的 VALIDATE三份精确prior pin。运行中不得修改这些文件。
结果不会自动发布，也不会推送代码。
