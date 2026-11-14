# Main 固定48腿：真实结果与边界

两块及完整48腿已通过真实独立审核（combined `33829f5e71c9a1ed5cc530566450ef06d473dba8de4b5abbc6c554657983c408`）。12个cell保持原M,G,G,M顺序；每端每cell仅2次，所有同binary raw产物零例外匹配。没有重测、剔除或补样。

## Foundation14原始两观测

|指标|MLF frontend (M)|GHC typed-only (G)|两观测均值 M/G|
|---|---|---|---|
|Total CPU s|20.564 / 21.129|0.544 / 0.546|38.25×|
|MUT CPU s|16.833 / 17.366|0.244 / 0.241|70.51×|
|GC CPU s|3.729 / 3.762|0.297 / 0.300|12.55×|
|child guard elapsed s|20.807319 / 21.378982|0.683273 / 0.695035|30.61×|
|allocated bytes|60,608,900,384 / 60,608,900,384|511,558,192 / 511,553,264|118.48×|
|GC copied bytes|4,330,461,968 / 4,330,429,400|116,347,632 / 116,319,784|37.22×|
|max residency bytes|38,942,992 / 39,439,824|16,147,080 / 16,146,992|2.43×|

M的均值Total CPU 20.8465s中，MUT约82.0%，GC约18.0%。因此这次大差距不只是GC用时；但MUT包含整个非GC工作，不能据此定位特定算法、查询或序列化成本。Allocation大不等于全部CPU原因。

## 输入梯度（均值，全部原观测另存）

|family/endpoint|n16|n32|n64|n128|n256|n16→256 CPU倍数|allocation倍数|
|---|---|---|---|---|---|---|---|
|flat/M Total CPU s|0.279|0.339|0.461|0.850|1.4535|5.21×|6.10×|
|flat/G Total CPU s|0.136|0.1625|0.1255|0.176|0.197|1.45×|2.57×|
|chain/M Total CPU s|0.265|0.3105|0.3135|0.388|0.5445|2.05×|2.39×|
|chain/G Total CPU s|0.1205|0.1225|0.1425|0.138|0.1365|1.13×|1.19×|

每次n翻倍，flat/M Total CPU倍数为1.22、1.36、1.84、1.71；chain/M为1.17、1.01、1.24、1.40。flat/M最后两段GC均值约2.14×、2.17×，但Total CPU并未同步超过2×。这组范围未展示Total CPU超过输入翻倍的平均增长；不证明线性，也不排除被固定成本遮蔽的超线性。只有5个规模、每端2次，不能把增长迹象提升为渐近复杂度结论。基线M Total CPU为0.242/0.240s、G为0.141/0.085s，单列且未作数据驱动扣除。

## 必须保留的比较边界

- M产生checked/published frontend工件，G只接受类型并写typed interfaces。输入相同，工作端点不等价。上述比值是这些端点的观测差，不是整个MLF编译器相对GHC的等价速度或达标证明。
- RTS CPU已舍入；guard elapsed含监督/采样开销，不是精确target wall。短样例与2观测不足以支持稳定优势或显著性。
- fresh query/application cache不代表OS冷缓存，没有drop系统cache。
- maximum residency是major-GC抽样存活量，不是RSS；copied bytes是GC复制，不是图访问/复制/约束计数。此轮未测这些算法事件。
- n=0基线不除零；Foundation size=None没有单一生成规模单位，不纳入shape梯度。负数/bool/非整数规模也不归一化。舍入0的CPU比率返回null/不可分辨。
- stage146.87s、234.96s及累计1099.71s都是资源/认证/清理账，不在性能指标里。没有把qualification或completion时长当编译速度。

## 文件与可追溯性

`all48-observations.csv`保留48条原始观测和guard/RTS fullpin；`results.json`/`results.md`保留两观测、均值、每n/每source-byte归一化及全部相邻比值。`findings.json`对应上面事实。`verification.json`逐项与独立审核combined-samples对齐。

原冻结reducer v1完整读取时暴露Foundation size=None的纯汇总边界bug；它未改输入或运行目标。独立v2只收紧一处归一化谓词，v1和原预览保留。实际48腿只读归约已完成；没有重测。v1首次导入产生的两枚自有.pyc已精确记录并清除，所有原冻结成员hash不变。

生成器的通用`final_combined_review=pending`字段/标题保留原模板值，表示它不自行颁发审核门；本目录`report.json`单独绑定上述已经真实通过的最终combined审核，作为当前资格状态。不要用模板占位字段否认或替代独立审核。
