# 给本地 agent 的测试任务：A1 私有索引实验

请在我的本地机器上独立复测这个**尚未接受的实验**，不要预设它会加速。
可以优先研究并实现原生 macOS 平台适配；不要因为现有 Linux 工具链
collector 不支持 Darwin 就直接放弃。不要操作远端分支、开/合并 PR 或部署。

## 精确版本与已知结论

- 仓库：`https://github.com/mlf-lang/mlf`
- 实验分支：`codex/a1-private-index-experiment-20261028`
- 比较基线 P3：`875e483de49655030c4ffba1995b60610a50273a`
- A1 被测源码/脚本提交：`5a89143ecbcaaef152a7e88331583660192e106d`
- 分支上其后的 prompt/说明提交只用于文档；测试时显式使用上面的 candidate SHA。
- A1 包含 A0 私有会话 paged64 反向索引 + A1 直接初始化，**不是**只改 admission
  的隔离测试。公开 Solver API 不变，保留所有 graph/type/term/evidence/erasure 检查。
- 原云端正式中位数：P3 89.958440899 s、A1 87.533935668 s、GHC 8.282240412 s；
  整体改善 2.695139%，A1/GHC 10.568872x，未过预声明 5% 接受线，远未达 <=3x。
  不要拿本机秒数与该云端秒数相除来声称加速。

先阅读仓库 CONTRIBUTING、tests/README，以及
`tools/performance/a1-private-index/README.md`、`CONTROL-SCOPE.md`、
`docs/performance/a1-private-index/README.md` 和 `portable-validation.json`。
现有 portable controls 已在云端实际通过；新鲜 clone 的整个 portable prepare/campaign
包装脚本只做了静态审查，并未在云端重新端到端运行。发现包装错误应保留失败日志并修复，
不要把未运行步骤说成已验证，也不要拿修复前后的性能腿混合统计。

## 取得真实文件，不假设任何云端目录存在

在你选定的本地工作目录创建新的 clone（不要覆盖已有工作）：

```sh
git clone --branch codex/a1-private-index-experiment-20261028 \
  https://github.com/mlf-lang/mlf.git mlf-a1-local-test
cd mlf-a1-local-test
git rev-parse 875e483de49655030c4ffba1995b60610a50273a^{commit}
git rev-parse 5a89143ecbcaaef152a7e88331583660192e106d^{commit}
```

如果已有 checkout，先检查未提交修改，用新的 worktree/clone；不要丢弃用户工作。
本分支携带完整 14 个目标源文件、54 个提供方源文件、GHC host closure、
独立控制源码及脚本，不需要下载云端二进制或恢复目标推断缓存。
完整历史 ZIP 在 Library 中只是证据备份，**不是运行前提**。

## 平台与工具链：先同机资格，再测量

1. 记录 macOS/Linux 版本、架构、CPU/核心/亲和性（如适用）、内存、磁盘、电源模式，
   实际 GHC/CC 路径、版本、二进制与动态依赖哈希，Python/Git 版本。
2. 使用普通 **GHC 9.14.1**、Python **3.11+**、一个固定 C toolchain；P3/A1/普通 GHC
   均在同一机器、同一工具链、同一运行环境。不要跨 VM/native、x86/ARM、Rosetta 混比。
   GHC producer 使用维护中的 O2、`-j1`、`-fpedantic-bottoms`、`-fno-state-hack`，
   保留接口/语法/穷尽检查与 `-rtsopts=ignoreAll`。固定 `GHC_ENVIRONMENT=-`、`GHCRTS=''`，
   不加 `+RTS -N`，不改 GC 参数、不启用 profiling；记录实际 locale。
3. **原生 macOS 优先探索**：现有 `tools/shared/build.py:toolchain_inputs` 的 Linux/ldd
   collector 以及 reproduction 的 `/proc`、`sched_getaffinity`、RLIMIT/RSS 处理需要真实
   平台适配。可另建可审查的 adapter/patch，使用真实可用的 macOS 工具链/依赖发现
   （例如经过解析/校验的 `otool`、SDK/系统库信息）、资源采样和路径规则。
   不要简单 monkeypatch 掉认证函数、伪造 Linux receipt、把缺失检查变成成功。
   对两种 producer 对称应用必要的平台层改动，保留原始 patch、逐文件原/新哈希、理由、
   独立控制及负向失败测试；明确它是**新的 macOS 资格**，不是已认证 Linux 结果。
   算法源码、冻结目标/provider 字节和语义检查不可借移植变动；若确需语义改动先报告。
   macOS `ru_maxrss` 常以 bytes 表示，Linux 以 KiB；核实实际 API，不能直接复制乘1024。
   AS 限制若与平台虚拟地址布局冲突，报告并提出等效受审查资源保护，不静默删除限制。
4. 如果原生适配暂时无法保持这些门禁，报告精确阻碍；可用已有 Linux VM/container
   作为后备，标记 guest 结果，不称为原生 Mac 性能。安装新工具/VM 若需要额外权限，
   按本地环境规则申请，不擅自更改系统安全设置。
5. 串行执行，没有其他编译/压测；进程树 RSS <=5GiB，AS <=6GiB/进程（平台适配如上），
   host available >=3GiB、磁盘剩余 >=4GiB、每重任务 <=6h。不要降低门禁来跑完。
   保留失败/中断记录，先查旧进程终态，不盲目重复。禁止启动已取消的 native74/bootstrap。

## Linux 已有入口（macOS adapter 应保留同一协议）

下面路径是**你实际选择的本地绝对路径**，不是已存在的示例目录。先填写变量：

```sh
BASE=875e483de49655030c4ffba1995b60610a50273a
CANDIDATE=5a89143ecbcaaef152a7e88331583660192e106d
GHC=/absolute/path/to/ghc-9.14.1
CC=/absolute/path/to/cc
WORK=/absolute/new/output/outside/the/checkout

python3 -B tools/performance/a1-private-index/reproduce.py \
  --source-checkout "$PWD" --base-ref "$BASE" --candidate-ref "$CANDIDATE" \
  --ghc "$GHC" --cc "$CC" --work-dir "$WORK" --prepare-only
```

准备成功会输出 `preparation.json` 的真实 SHA256。先审查全部门禁通过，再填写它：

```sh
PREPARATION_SHA256=the_actual_printed_sha256
python3 -B tools/performance/a1-private-index/reproduce.py \
  --work-dir "$WORK" --run-campaign \
  --preparation-receipt "$WORK/preparation.json" \
  --preparation-sha256 "$PREPARATION_SHA256"
```

每个 attempt 用新目录，不覆盖/修改旧失败收据。原生 macOS adapter 如需自己的入口，
给出同样可执行命令、patch 和输出格式，并审查其与上述协议的对应关系。

## 不可省略的输入、正确性与缓存门禁

- `fixtures/manifest.json` SHA256：
  `b23d7f0dc3482e86e58ba27f7484c48170732589662feca807db8ce2bc7106ba`。
  路径前缀为 `tools/performance/a1-private-index/`。
  内含各目标/provider/host 文件的真实逐文件 SHA256，不按当前包目录重新选目标。
- 原冻结 descriptor SHA256：
  `102d2f829a06caaad08e4123631f7fd4146ec3fd320c334571aa58378d40710c`。
  测的是同一个 **14-module mlf-crates**；当前 A1 producer 的 crates 包有15模块、shared
  有123模块，不能拿它们替代冻结目标。原始 frozen commit 是
  `aa11ffd318a2efa5be9805524710d0677eedb86f`，提供方包含已记录基线修复，manifest 才是字节依据。
- 一次本地新构建两个正式 producer。六提供方54模块仅构建一次，两个 MLF 实现复用
  **相同本地路径/相同字节**的依赖和 builtin。独立解码/读取并检查全部7个对象，坏对象
  必须被拒绝。独立6组/28 traces、22 admission、9 parsed-file 全输出字节对照、4 privacy
  negatives 必须通过，不能仅编译成功或 candidate 自己产生期望值。
- 每个 MLF 计时腿：目标 query 目录最初不存在，**544 fresh / 0 reused**，全部
  `cached:false`，544个有序 `{id,members}` 精确匹配固定 oracle。
  禁止推断缓存预热/目标结果缓存/跳 type/term/xMLF 检查，禁止以改计数器冒充新推断。
- 同一本机 P3 第1轮建立 `.mlfci`/`.mlfco` 原始字节参照；后续 P3/A1 必须完全相同。
  依赖路径嵌入产物，不能强求本机与云端产物哈希相同，**但本机比较不得归一化输出**。
  `query_key` 含实现身份，不把它误作跨实现字节 oracle，原始 report 必须保留。
- 普通 GHC 先构建精确70模块 no-link closure，每腿只复用非目标56模块/112个hi-o文件；
  目标14个始终重编。参数 plain `--make -no-link -j1 -O2`，不加仅 producer 使用的 flags。
  验证实际编译14模块、56依赖字节不变；不要把整套70模块重编与 MLF 比。

## 固定九腿次序与报告

正式只执行预声明的三轮九腿，不因为某腿慢而删样本/重跑挑结果：

1. **GHC → P3 → A1**
2. **A1 → GHC → P3**
3. **P3 → A1 → GHC**

这是 cold **target**，不是 OS cold；不刷 OS cache，也不声称刷过。主指标是 compiler
subprocess launch→exit wall，准备/拷贝/认证/事后检查在外。分开列出 user CPU、system CPU、
最大单子进程 RSS、采样进程组峰值 RSS（注明采样方法、单位与覆盖范围），不能互换或用CPU占比
推算阶段墙钟。记录监测本身开销的界限。GHC 输出普通O2对象，MLF输出checked xMLF+queryfiles，
这个终点不对称必须披露。

最终请给：环境与适配patch/资格结果；确切base/candidate+本地平台patch身份；每腿按执行顺序
wall/CPU/RSS；三个中位数、A1/P3 与 A1/GHC、三对比值；源/hash/544fresh0reuse/字节门禁结果；
所有失败/中断及排除理由（若有，不能用替换样本伪装原固定方案）；原始receipt/log位置。
明确区分“算法优化效果”“平台移植/包装修复”“未运行/未支持”，无论提升、无改善或变慢都如实报告。
不要据一个有利单对直接接受优化，也不要把此14模块切片当全部编译器/bootstrap性能。
