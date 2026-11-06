# DeclId 迁移验收

固定基线是 `726cd256`，#43 并行增加的收尾报告已在 `3d6c472b` 同步。编译器安装、crate 编译和原生执行分别记录宿主及可执行文件。固定基线的安装回执、Foundation 三态文件、独立解码行及自编译结果保存在 [baseline](baseline/README.md)。每个编号的提交正文记录本步验证，最终安装、配对样本和复验记录随 stacked PR 提交。

| 编号 | 集成提交 | 正常入口和验收 |
|---|---|---|
| 00 | `80106d8a` | 从空目录安装固定编译器。Foundation 每个状态解出 3,403 行、19,277 条有序读取和 504 个 finish 回执。固定编译器自编译检查了 1,715 组，在发布目标索引时达到既有展开预算。 |
| 01 | `4bce27c8` | 实际模块解析区分别名、重导出、局部遮蔽和相同显示名。独立 crate 为同一实体分配不同槽，错误数值槽被拒绝。 |
| 02 | `144860c3` | `SourceInference.indexedPlan` 保留自引用及源码次序。独立 SCC/reach 对照覆盖 1,032 组。 |
| 03 | `52b1be8b` | `Compiler.compileLinked` 在声明所属模块选择可见实例，覆盖不同模块、局部遮蔽和复制的 helper。 |
| 04 | `dd91f24d` | 解析后追加 selector、字典和外部支持项，检验方法重定向、活动本地项和相同打印名的导入。12 再覆盖了两个同名方法属于不同类的情况。 |
| 05 | `dbfbf848` | `inventoryProtection` 的反向传播与独立 named 固定点对照，覆盖环、菱形、128 项长链、导入标志改变及不受影响的声明。 |
| 06 | `72c7a18d` | `--compile-crate` 使用已检查槽读取类型、约束和保护位，拒绝未完成组。保护位编辑通过冷、热、ICH 和语义审计。 |
| 07a | `a8229781` | 区分同一成员组的 Prepared、Scope、Infer、Finish 查询，检查 SCC 拆分、合并和成员顺序。 |
| 07b | `20cbd2fa` | 区分同组不同 site 或目标的 Evidence，保留候选角色、顺序及重复读取。 |
| 08 | `9f1289b9` | 文件查询与独立 parsed 查询都覆盖同名实体、槽漂移、局部 alpha 改名和改绑。改绑只重推断对应组。 |
| 09 | `1bd4b62f` | 源码和原生 prepared wrapper 按消费方槽选参数。覆盖未用 let 的 RHS、隐式模式方法、证据候选、空签名、遮蔽和错序。 |
| 10 | `ab33c613` | raw/final 片段按顺序核对签名、槽、类型、owner 及版本。错序、缺失、多出、重复和伪造产物均进入负例。 |
| 11 | `877ee708` | 对象独立重建 tag 427，覆盖换 owner、读顺序改变、陈旧或缺失 payload、伪造 stage，以及 ICH/语义审计的恢复路径。 |
| 12 | `b8c99cba` | `compileLinked`、parsed/file 查询及 class-lowered 路径传递全局槽。覆盖 lexical given、同名局部和全局、多态导入、互递归源码次序、生成字典、15 模块 prepared-library 生成器及关闭编码池的混合组。读取隐式字典前缀时沿结果位置的 xMLF 上界查找；原接口中的 checked 类型保留。 |
| 13 | `2be4713b` | `graphInterface` 比对公开、私有、重导出、类方法、空入口和合成入口。四种生产方／消费方组合产生相同接口、对象和报告。 |
| 14 | `a05a051f` | 四 crate 菱形删除源码、缓存后仍可链接并运行得到 42。未被入口引用的片段不进入结果，重复生产方、缺失依赖和类型不符均被拒绝。便携发布包使用已校验的接口闭包读取对象。三层依赖发布并搬移后，删除所有生产者源码与缓存，原生消费者仍输出 42；暖安装保留既有文件和回执。 |
| 15 | `32966899` | 声明槽 7/12 对调后，两个 Clang 链接程序均输出 42。已安装的原生 wrapper 命中 ABI 槽 238，复用了原生对象和运行时。 |
| 16 | `7dad036a` | 五组正式入口诊断与固定版本逐字节比较，包括歧义候选、遮蔽、生成方法、原始拼写、文件及行列。 |
| 17 | `8ccfc455` | 独立 reader 从真实 v2 结果重编码出 v1 的完整字节。独立 17 开发构建通过七个库，源码组冷编译 1,748/0、暖复用 0/1,748；目标 CURRENT 解出 20,765 行、410,543 条有序读取。独立回执见 [17-query-generation.json](17-query-generation.json)。暖态记录只有在查询键、结果摘要、完整有序读取及其版本、payload 位置逐字段相同时才共享旧节点；待发布 payload 和损坏修复流程保留。打包重复引用保留原 last-wins 键和值，避免重复复制 Map 路径。[局部控制及 RSS 探索回执](17-rss-controls.json) 不替代最终正式安装和配对验收。 |
| 18 | 见子 PR 的验收 SHA | 独立安装、根包 locked build/test、跨版本执行及 Foundation 配对样本使用同一个候选提交，具体回执随 PR 记录。Release 校验同时核对现行源码和不可变的 #29 原始树。二进制原生夹具按现有库边界编译同一份 51 模块清单，独立读取公开对象及安装产物；C4 保留闭合字节对照，并检查完整 open 内容、按需链接与实际篡改拒绝。原生根测试发现 Test.Process 丢弃泛型错误字段时缺少具体字符串类型；仅在该调用处补 String ascription。[原两模块的 GHC/native 对照](18-test-tools-controls.json) 验证接口、对象和报告字节相同，编译器的资格规则不变。 |

[18 的集成修复记录](18-integration-repairs.md)列出根包预检发现的生产问题、过期夹具及独立 oracle 边界；分次预检与最终同一源码上的全量验收分别记录。

## 剩余名字查找

[逐行清单](lookup-audit.tsv)列出迁移涉及的 34 个生产与原生生成模块中所有匹配行和调用方。统计以 17 的代码为准，共 358 项，其中 `Map String` 有 244 项、`X.nameHint` 有 70 项、`symbolName` 有 38 项、`lookup eqString` 有 6 项。同一行的不同查找词分别记录。

- **解析和生成。** `lookupEntity` 把原始拼写解析为模块实体。`generatedTableFor` 把按所属类提供的方法字段对齐到 selector 槽。独立解析、生成表及源码中的 `Global` 共享本次声明表；导入接口和重导出按定义方稳定身份进入消费方表。
- **类和局部作用域。** 六处 `lookup eqString` 中，两处查已知类的字段或实例实现，四处在发布包中按稳定 crate 身份查接口与重定位路径。类谓词、类型变量、局部 given、模式及 kind 环境有自己的名字域。`Constraint.BindingEnv` 的词法表和全局槽表分开保存；全局读取和递归边都按声明槽选择。
- **查询和快照。** `DeclScope` 保存外部稳定键和 named adapter。`CheckedContracts` 只在整组成功后发布新槽。Prepared 引用短号在本组引用表中解释。生成索引的稳定键和位置属于该代；读取旧边时用该代的定义和摘要复原。
- **公开产物和链接。** `decodeTrustedIds`、`finalBindings` 对齐文件参数和本地槽。`graphInterface`、`finalParameterIds` 和证据请求核对已选槽的 xMLF 名字、类型和顺序。`openIndex` 将对象的稳定名字映射到链接会话，之后按 `producerOf` 选片段。LLVM 通过声明到 ABI 槽的反向表选导入，检查 wrapper 的 hint 和类型。
- **诊断和兼容入口。** `symbolDisplay` 保存定义的显示标签，`displayNames` 同时服务于仍接收名字的历史错误。原始 AST、公开的 named API、旧 UnitObject 及类型／类命名空间保留各自的显示或序列化职责。

## 复验

独立安装、四种生产方／消费方组合、query 恢复及三种 shared-frontend 模式的命令见[迁移计划](../../../docs/declid-migration-plan.md)。以下命令使用该计划定义的绝对路径和已配置的原生 runner。自编译工具从新目录开始，核对发布的 CURRENT、接口和对象，分别验证编译器的组级暖命中与包管理器的整库复用。

```sh
python3 -B tools/performance/declid-migration/check_self_build.py "$AFTER" "$OUT/self-build"
python3 -B tools/performance/declid-migration/check_portable_release.py --before-manager "$BEFORE/bin/mlfpkg" --after-prefix "$AFTER" --runtime "$PWD/runtime/mlf_runtime.c" --output "$OUT/portable-release"
python3 -B tools/performance/declid-migration/check_xmlf.py "$BEFORE/bin/emlf" "$AFTER/bin/emlf" "$OUT/xmlf"
python3 -B tools/performance/dense-decode/foundation.py "$BEFORE/bin/emlf" "$AFTER/bin/emlf" \
  "$OUT/fixture/libraries/mlf-foundation" "$OUT/foundation" --warm-rounds 12 --cold-rounds 3 --profile-rounds 3
python3 -B tools/performance/declid-migration/compare_foundation.py "$OUT/foundation"
python3 -B tools/performance/declid-migration/check_foundation_receipts.py "$BEFORE/bin/emlf" "$AFTER/bin/emlf" "$OUT/foundation"
```
