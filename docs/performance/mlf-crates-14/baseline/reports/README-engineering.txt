mlf-crates14 优化前工程摘要

普通 MLF median 163.896307032 s；GHC 9.14.1 plain -O2 median 9.047647972 s；ratio 18.114797；目标 <=27.142943916 s。
同一冻结14源，依赖复用，目标544 fresh / 0 reused。GHC native objects 与 MLF checked xMLF+query cache 的终点不对称。

首项候选：Bootstrap.Module partialSelectItem/selectType 的 parent filter before union。late CCS 四个不重叠上下文占38.4513% sampled CPU、44.0067% allocation。不是已验证收益；保留alias、排序、去重、错误、fixed point、惰性与所有checks。

禁止混淆：forced diagnostic 197.156816802 s 不等于 ordinary phase wall；late profile 349.293843396 s / 318156 ticks 不可按CPU占比乘普通wall；GC是overlay，不加到阶段之上。主GHC分母是plain -O2，不是repo extra flags的8.847117296 s。

详细可编辑报告：mlf-crates14-preoptimization-profile-zh.docx
同内容纯文本：mlf-crates14-preoptimization-profile-zh.txt
复算值与来源哈希：report-derived-facts.json
报告构建入口：build_report.py（只读原证据并写本目录，不运行编译）

优化前状态：无性能代码改动。本报告须先交付，再按相同普通计时与语义门槛验证最小候选。未执行完整74模块native bootstrap。
