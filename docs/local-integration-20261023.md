# 本地四 PR 整合记录（2026-10-23）

代码快照：**`8a3e69b165765931c3ff762379a78db9659b2cd8`**，tree `ba0ae958b466ca08ffee79a83dadbd8b7d2156fa`。此提交冻结后，测试接入规划及清单以单独文档提交追加；不会改写这份代码快照。

## 位置与授权边界

- Worktree：`/Volumes/HPNVME/Users/ares/Documents/Codex/2026-10-23/task-2/mlf-integrated`
- Branch：`integration/pr-9-11-12-16-20261023`
- 独立 Git 存储：`/Volumes/HPNVME/Users/ares/Documents/Codex/2026-10-23/task-2/mlf-integration.git`
- Remote：`https://github.com/mlf-lang/mlf`，与原仓库 `.git` 后缀 URL 为同一仓库。
- Base main：`77ac8a7bc551ac71747b38c79fc5812d385165e3`，已含 #18 报告初始化和 focused-Core 准备修复。
- 代码交接时 `git status --porcelain=v1` 为空。四个精确 head 均通过 `merge-base --is-ancestor <head> <code-commit>` 检查。
- 本任务未 push、未创建/合并/关闭 GitHub PR、未改 main、未触发远端 CI/发布、未安装工具或改权限/凭据/系统环境。后续发布由父任务另行安排。

原仓库 `/Volumes/HPNVME/Users/ares/src/mlf-pr8` 保持 `codex/faster-pr-smoke` / `c16d7100fb97013c01be439653154eba90ceaaec`，无未提交改动，原有一个未推送提交仍在。没有 checkout/reset/stash 原仓库。初始只读进程观察没有发现 MLF/编译测试任务，没有改动用户进程。

## 固定输入与依赖

| PR | 精确 head | 与当前 main 的真实 merge-base | 本地合并提交 |
| --- | --- | --- | --- |
| [#9 async](https://github.com/mlf-lang/mlf/pull/9) | `9d3d59cd51d3b204c49bcfa7acc8c51c94c1d853` | `77ac8a7bc551ac71747b38c79fc5812d385165e3` | `02bff16b6f36ce6ea903e72d341ab1ebd947eeee` |
| [#11 guards](https://github.com/mlf-lang/mlf/pull/11) | `f29ad8b770eae70b505c40d9ba0d91b123f3db51` | `3d33c040e3ea3ef46e6b9981ccb0cf0d3318639f` | `d5f2f1bd9254c8892ac27e67352decc144feefac` |
| [#12 tuple/list](https://github.com/mlf-lang/mlf/pull/12) | `af88e6f417780c9d5f39f53604eb99b409de81a6` | `0c3464c9880589adea5dfe0c1af8a16f836617b4` | `2e394ff375ec3ca86df58a1ad12f27d73122cd66` |
| [#16 CI policy](https://github.com/mlf-lang/mlf/pull/16) | `597b107858695a79b095fcca175ccb979b11a9f2` | `3d33c040e3ea3ef46e6b9981ccb0cf0d3318639f` | `8a3e69b165765931c3ff762379a78db9659b2cd8` |

GitHub 只读元数据显示四个 PR 都开放且为 draft，base 名均为 `main`。记录的 API base SHA 分别等于表中的 merge-base；整合以实际 refs 和提交包含关系为准，不依赖 PR 正文中陈旧的 head。#9 最新三次同步提交在原 async 范围内，没有发现明显范围变更。代码冻结后再次 `ls-remote` 核对，上述 main 与四个 heads 未改变。

四个 heads 均尚未被 main 包含，彼此没有 head 包含依赖；#9 已包含当前 main，因此先合 #9，再将 guards 和 tuple/list 的语法交叉整合，最后处理 CI policy 的叠加。全部使用 merge commits，保留原 PR 历史，没有 squash/rebase/cherry-pick 替换历史。

## 冲突处理

| 合并 | 冲突与处理 |
| --- | --- |
| #9 | 无冲突；完整保留 async、runner/supervisor 和六项 PR gate，以及其已有最新 main 祖先。 |
| #11 | `CHANGELOG.md` 合并两项新增说明；`tests/README.md` 保留 async 段并更新 guards 后的 583 backend rows；`mlf.lock` 按实际合并输入生成。`CompilerTests.emlf` 自动合并保留 `suite_builds` 空数组默认值、`prepared_suite_targets` 空对象默认值和 main 的 focused-Core 准备逻辑。 |
| #12 | `Parser.emlf` 的 `bindingHead` 同时使用 `annotationSymbol` 与 `pLook (= 或 |)`，由 `equation` 消费 `=`；保留 legacy annotation 的 `|`/`=` 边界。Layout 自动合并后逐段复核，guard-if IfMark 清理、tuple/list 的括号/逗号/续行处理均保留。Changelog 保留所有 feature；锁再次重建。 |
| #16 | `ci.yml` 保留 main/#18 的 suite-receipt artifact、#9 的 async jobs、六项 needs 和 `length == 6`。用 #16 reusable qualification 接替旧 main fresh-native/package/self-host jobs，其 CLI/cache、六组 campaigns、Windows、benchmark 和 release-only packaging 仍在；`docs/ci.md` 同时保留两边准确说明。额外修正 policy contract 的旧四项 needs，使其与实际六项一致，并将文档的旧 480 秒 smoke watchdog 同步为脚本实际的 900 秒。 |

没有使用整文件 ours/theirs。语法独立审查确认七个 guards/Core/backend 注册文件与 #11 一致，四个 tuple/list fixture/runner 文件和三个根 target objects 与 #12 一致，14 项静态保留比较通过；这些比较不等于组合编译器的语义执行验证。

## 锁文件的生成与边界

现成 SDK `mlfpkg` 在进入命令逻辑前即因缺少 `/opt/homebrew/opt/gmp/lib/libgmp.10.dylib` 退出 134，因此没有成功执行原生 `lock` 或 `--locked plan`，没有为此安装或编译工具。

替代流程严格复现 `libraries/mlf-package-core/Package/Manifest.emlf` 的 `visitWith/sourceFiles/snapshot` 与 `Package.Json.render`：按依赖名字排序 DFS 后序；从 manifest 推导完整 library/target main/private module 集合；对实际原始 bytes 求 SHA-256；对象 key 排序、数组保序、单换行。先在原 main 和四个 PR 上分别回放，五份锁均**逐字节相同**，然后才生成组合树锁，未随意选择冲突的一侧。

第二个独立实现从 manifest 重建而非遍历既有锁，复核 **11 个 manifest、37 条依赖边、80 个源文件** 的完整集合、哈希、顺序及序列化字节；冻结代码上再次通过。锁 SHA-256：`2b45bb8ce32058d971a93ae92526c42ab647b46500f6f8c73ec4b02d5e8ba9bd`。

这证明当前纯本地根包图的 snapshot 一致性，不冒充 MLF parser、target import semantic validation、原生 locked plan 或完整 native/test 输入认证。根锁本来不涵盖所有独立 test manifests、fixtures 与 C 文件；详见[锁审计](integration-evidence-20261023/lock-audit.md)和[完整审计 JSON](integration-evidence-20261023/independent-lock-audit.json)。

## 实际轻量检查

- 工作树、index 和相对 main 的 `git diff --check` 通过；未合并 index 项 0，169 个变更路径无冲突标记。
- 17 份 config/manifest/catalog/lock JSON 解析；9 个 workflow + 1 个 composite action YAML 解析。
- 18 个变更 shell 文件 `bash -n`、4 个变更 JS 文件 `node --check` 通过。
- `node tools/release/test-ci-policy.mjs`：纯 workflow 文件/策略表达式检查通过。
- `bash tools/release/test-pr-gate.sh`：33 个合成 aggregate 成功/失败/缺失/取消/跳过 controls 通过。两条命令共约 0.18 秒，未启动编译或 campaign。
- 四 PR exact-head 祖先检查、原仓库 HEAD/status 保持检查通过。
- 稀疏排除的 `tools/profile/results/` **2,588 个 tracked 路径及 Git object ID** 与 main 完全一致，没有删除提交。

完整明细见[轻量检查记录](integration-evidence-20261023/lightweight-checks.json)。YAML 能解析不等价 actionlint；本机没有 actionlint，未下载/安装。

## 未执行与剩余风险

未执行 compiler/package-manager build、完整 root tests、unit/packages/parity/backends/port/self-host 六组 campaigns、fresh bootstrap、自举 fixed point、guards+tuple/list focused 组合语义测试、async language/native/Windows suites、性能基准、SDK relocation、完整 `tools/release/check.sh` 或任何远端任务。原生 `--locked plan` 与 actionlint 仍未完成，原因见上。

当前代码是**合并完成且轻量检查通过**，不是完整资格认证通过。组合 Parser/Layout、平台原生监督器、锁的原生工具接受性和全 CI 图仍需后续执行窗口。各 PR 的旧 receipts 不作为本次组合树的 pass。

## 测试统一接入规划

详见[主计划](test-framework-integration-plan-20261023.md)、[完整机器清单](testing-migration-inventory-20261023.json)、[全仓资产表](testing-inventory-20261023.tsv)和[外部逐入口表](testing-external-entrypoints-20261023.tsv)。目标是所有测试由框架实际管理发现/选择/执行/判定/清理/报告，而不是永远保留粗粒度 wrapper。各 adapter 保留独立 oracle、负例阶段、native/平台语义、fresh self-host、SDK 与性能采样要求；真实发布副作用仍独立。

输入范围、machine handoff 和完整 merge-base 记录分别见 [code-handoff.json](integration-evidence-20261023/code-handoff.json) 与 [dependencies.json](integration-evidence-20261023/dependencies.json)。
