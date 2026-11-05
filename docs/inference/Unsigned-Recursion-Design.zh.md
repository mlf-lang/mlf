# MLF 类型推断能力与无签名递归设计报告

基准：PR #22，提交 c0c5dddd11ed5775e2a3d5564cfeeef8383610a5。研究日期：2026 年 10 月 24 日。

本报告回答两个问题：这个编译器应该自动推断到什么程度，以及如何在保留现有 MLF 和 xMLF 架构的前提下补上普通递归推断。建议默认推断普通 let、函数应用和普通递归；需要跨类型递归调用时，用显式多态接口提供所需信息。这样，标注集中在声明多态能力或消除歧义的位置。

结论：可以在 #22 上实施。完整路径包括递归声明表示、类约束处理、约束调度、泛化和目标证据生成。本报告完成理论研究与静态审计，作为后续实现及测试的依据。

## 一 结论的证据等级

本文严格区分四类陈述。

- 文献结论：原论文明确给出的规则、定理或算法，标注来源及章节。
- 代码事实：直接读取上述固定提交得到的现状，使用相对文件名及行号定位。
- 拟议设计：为该仓库提出的扩展规则、调度和证据构造，列明相应前提和验证方式。
- 待证明或待验证：需要推导、测试或独立检查支持的性质。样例测试负责验证具体行为，完整性和主类型性质另列证明义务。

## 二 推断能力应该如何理解

先约定四个术语。泛化是把独立于外部环境的未知类型变成量词；实例化是在一次使用中为这些量词选择类型；SCC 是依赖图中相互可达的一组定义；证据是目标语言中可检查的类型转换步骤。下文的关键流程是：先在 SCC 内共享并求解类型，再泛化导出，最后给每次使用生成证据。

### 1 普通推断与多态值

文献结论：图形 MLF 使用柔性有界量化保留可推迟的实例化选择；例如 choose id 可以保留一个统一描述，而不必提前选定 identity 是单态还是多态。无标注的核心语言保持 ML 的可类型性；“有主类型”和“存在终止的推断算法”则是不同命题。[R2，§§2、5]

对本项目的能力目标如下。

| 情形 | 默认行为 | 标注边界 |
| --- | --- | --- |
| 普通 lambda、应用和非递归 let | 自动推断；let 完成后按环境泛化 | 不因代码较长或定义位于模块顶层而强制签名 |
| 普通自递归、互递归 | 组内共享未知类型，组完成后泛化 | 同一递归假设不允许在组内任意换实例 |
| 高阶但并不多态使用的参数 | 自动推断 | “函数作为参数”本身不需要签名 |
| 被多态使用的 lambda 参数 | 使用局部标注声明需要的多态接口 | 例如同一个参数分别用于 Int 和 Bool |
| 带签名的多态递归 | 根据已声明的接口检查定义，各调用可合法实例化 | 签名必须足够表达递归所需的多态性 |
| 无签名的任意多态递归 | 不作为默认推断目标 | 提示具体冲突及需要标注的递归接口 |
| 类约束、名义数据、kind、模块 | 保留现有功能；分别列出额外义务 | 不从核心 MLF 定理直接推导整个项目完备 |

这里的“必要标注”指清晰、可解释的语言边界。实现应指出哪一个多态接口需要用户提供；全程序最少标注数的搜索另属优化问题。阶段性实现限制也应单独说明。

### 2 主类型如何保留实例化选择

以纯核心表达式为例，设 id 的类型为 ∀a. a → a，choose 的类型为 ∀b. b → b → b。MLF 可用 ∀(a ≥ ∀b. b → b). a → a 表达 choose id 的结果；两个 a 必须选择同一个实例。若提前把它压成一个普通 HM scheme，可能丢掉一等多态的合法使用。[R2，§2.1]

本次设计因此复用图形 MLF 的类型身份、柔性边、刚性边和作用域规则。“组内单态”准确地指每个未签名递归名字共享一个推断假设；该假设内部仍可保留已有的多态类型信息。

### 3 无标注时与 ML 等价的准确范围

文献结论：R2 的 Theorem 2 针对论文所生成的无标注核心约束；其证明依赖不引入新的刚性边，并与 ML 约束比较。应用这个结论时，要固定论文的语法和环境。带标注的 eMLF 可表达更多程序；iMLF 的可表达性与 eMLF 的可推断片段分别讨论。[R2，§5.1；R4，引言]

项目层面的适用边界：

- 必须先固定语法、原语和环境。环境中已给出的高阶多态接口本身就携带类型信息。
- 本次 ordinary recursion 是额外扩展，需说明它怎样归约为共享假设和合法的非循环实例化约束。
- 类约束另行验证实例解析、歧义、上下文传播和字典证据。
- 名义递归数据沿用声明好的构造子规则；a = List a 这样的无限类型方程继续由 occurs-check 拒绝。
- 一般递归允许发散。这里的类型检查保证类型规则成立，程序终止性另行分析。

## 三 文献给出的递归边界

文献结论：Recasting MLF §3.4 的 Rec⋆ 在检查函数体时给 f 一个共享类型 τ，结束后才在 continuation 中提供泛化结果。这里的共享“类型”可以包含 System F 多态性；其共享身份在递归体内保持一致。§4.2 说明多态使用递归参数需要显式类型信息；不受限的多态递归推断不可判定。[R1，§3.4 Rec⋆、§4.2 Recursion]

文献结论：R2 §5 处理实例化依赖无环的约束，先统一，再按依赖顺序传播实例化边并统一新增约束。因此，本次扩展需要保持该算法要求的实例化依赖边界。[R2，§5，Definitions 11–12、Theorem 1]

文献结论：Mycroft 将递归假设从普通类型放宽到 scheme，给出更强的递归规则；其 §6 明确是可能不终止的半算法。该节的 Note 2 讨论给定签名后检查固定点。本项目据此选择可判定的普通递归推断，并用签名检查处理多态递归。[R3，§§5–6]

拟议规则先用 HM 风格记号说明，再由第五、六节落实为 MLF 图和证据操作：

    Γ, f1 : α1, …, fn : αn ⊢ e1 : τ1, …, en : τn
    同时解 αi = τi 以及所有相关约束，得到 S
    σi = Gen(SΓ, Sαi)
    在 continuation 中使用 f1 : σ1, …, fn : σn

关键是顺序：“共享假设 → 解整组 → 相对解后的环境泛化 → 组外实例化”。签名存在时，直接用其作为接口，并验证 RHS 满足该接口。

因此，“所有递归定义都必须写签名”比普通递归规则要求的范围更大；另一方面，“所有多态递归都能完整自动推断”又超出了可判定边界。下面先检查 #22 已经实现了流程中的哪些部分，再确定要补齐的环节。

## 四 PR 22 已经有什么与缺什么

以下事实来自固定提交的代码审计。当前已具备共享类型绑定、图形约束和独立目标检查，本次主要工作是把它们接成完整的 unsigned 递归路径。

1. 前端已有真实依赖 SCC 分组。无自环单个声明走普通 SLet；循环组才走 SLetRec。Surface.hs:76–120。
2. 循环组在前端被要求每个成员都有闭合签名，当前 unsigned 支持的入口需要从这里补齐。Surface.hs:62–71。显式 let rec 和 do-local let rec 也使用该入口。
3. AST 中 SLetRec、SDoLetRec、CRec 的签名字段是必需项，无法表达“这里需要推断”。Types.hs:153、169、300。
4. 类转换同样假设每个递归成员都有签名，并据此抽取 predicates、调用 signedIn。Classes.hs:1101–1148。仅放宽 Surface 会在后续阶段再次失败。
5. 基础绑定已区分 Mono 和 Poly。变量的 Mono 分支与共享节点建立 equality，Poly 分支产生 scheme 实例化边。Constraint.hs:272–285。
6. 当前 CRec 为所有名字建立 Poly 签名绑定，再检查每个 RHS。Constraint.hs:315–344、549–563。
7. solvePrepared 先统一所有等式，再按生成顺序处理实例边，最后 normalize。unsigned SCC 完成和导出阶段需在这里接入。Constraint.hs:903–911。
8. 泛化通过图 binder 和 flexible flag 表达，schemeTypeIn 据此读出量词。可泛化集合的确定与后续 normalize 各有职责。Elaborate.hs:103–135。
9. 已有 typed XLetRec。目标 checker 在整个递归组环境下检查每个 RHS，并校验声明类型及名字作用域。Elaborate.hs:517–531；X/Check.hs:195–213。
10. 每次编译会独立检查目标项，再比较推断类型和目标类型的 alpha-equivalence，并检查 erasure 一致。CompilerCore.hs:49–77。这些门禁必须保留。

完整路径分别位于 libraries/mlf-frontend/Bootstrap、libraries/mlf-foundation/Bootstrap、libraries/mlf-inference/Bootstrap 和 libraries/mlf-xmlf/Bootstrap。附录提供固定提交链接。

## 五 拟议推断算法

根据上一节的缺口，扩展首先需要表达 unsigned 声明，然后确定整组约束何时完成、哪些类型可以导出。这一节给出具体调度和泛化设计；第六节接着说明如何把结果变成可检查的目标项。

### 1 分开运行时递归组和推断依赖

运行时需要打结的 SCC 与推断时必须同时求解的 SCC 不一定相同。保留原始值依赖图和 runtime SCC，另建推断调度。

- U 是未签名成员，S 是有闭合签名的成员。
- 先验证 S 的签名是否闭合、kind 正确，建立固定签名接口 Σ。此时尚未证明 RHS 实现了签名。
- 在 U 内按依赖建立子图。对 S 的引用通过固定接口 Σ。
- 按依赖顺序求解 U 的 SCC。完成后，在最终环境中逐一检查 S 的 RHS。
- 所有签名检查通过后，原始组才成为可接受的编译结果。

下面的混合签名程序说明为什么需要这一区分：

    f : forall a. a -> a
    f x = if true then x else g x
    g y = f y

预期 f 与 g 都可以有 ∀a. a → a。若检查 f 时先引入局部 skolem k，并把尚未完成的 g 的共享未知类型直接统一成 k → k，随后可能误报 skolem 逃逸。签名接口调度先从 f 的接口推断 g，再检查 f；但输出仍保留 f/g 的运行时递归组。unsigned g 在自己的未签名子 SCC 内继续遵守共享假设规则。

### 2 每个未签名递归名字只有一个共享类型根

对 unsigned 子 SCC C：

1. 保存外部环境 Γext，并为 C 建立专属推断区域。
2. 为每个 fi 分配唯一未知类型根 αi；全部加入当前组环境。
3. 对 ei 生成 MLF 约束。fi 的每个组内递归出现都引用同一 αi，不复制 scheme，不生成从“正在推断的 fi scheme”回到自身的实例化环。
4. RHS 可以包含普通 let、已完成定义、已签名接口的合法多态实例化；这些与 fi 的递归共享规则并不冲突。
5. RHS 的最终选定类型必须等于 αi。若子表达式先获得可泛化 scheme，必须通过现有 MLF 实例关系将其约束到 αi，G-node 则保留其 scheme 层角色。

### 3 解完之后才能导出

“解完”至少包括：组内等式已统一；函数应用、注解和非递归实例化依赖已满足；occurs-check、构造子、kind 和刚性冲突已处理；每条待导出路径的约束都有完成状态。

实现可以采用分阶段生成与求解，或显式 dependency-ordered worklist。实现方式以保持上述不变量为准。当前 writer 顺序对新增组边界的适用性，需要专门论证和回归测试。

导出依据解后的 Γext 和图 binder 归属。节点创建时间仅是记录信息，泛化资格由最终作用域决定。在 HM 子集，条件可写作：

    Gen(SΓext, Sτ) = forall (ftv(Sτ) \ ftv(SΓext)). Sτ

在图形 MLF 中，必须保留该条件对应的绑定树、柔性下界和依赖闭包。自由依赖可能通过另一成员、一个类型 bound、外层字典或已共享的未知节点间接出现。因此需要沿结构、bound 和 binder 检查完整依赖，同时按方向保留合法的外部引用：新的 flexible b 的 bound 可以合法提及外部 a；只要 a 留在外层且 prefix 良构，b 仍可能泛化。外部共享身份留在外层，作用域合法的新量词可在内层泛化。

“完成后固定 scheme”仅固定可泛化内部结构。scheme 中仍然引用的外部未知量继续与外部环境共享，之后必须接受外部约束的合法传播。

后续推断需要可供求解器使用的真实图形 scheme。候选做法是在组解完成后为每个成员物化 ExportScheme：创建独立的 export G-node，复制该成员可泛化内部结构和相关 bound，按新 owner 重建内部 binder，保留所有外部 frontier 节点的原身份，并记录原节点到副本的 provenance。不同导出成员之间的泛化变量从此可独立实例化，但每个导出内部原有的共享不可丢失；未泛化的外部节点仍跨成员共享。随后普通 G.expand/instantiateClosed 只从这个已完成的 scheme 出发，continuation 的生成或求解必须等到它可用。

上述“物化”需要新增不变量检查。必须核对复制域、binder 闭包、刚性边、kind、环境 frontier、实例 witness 和缓存的 scope index。组内原约束继续指向原 sharedRoot；导出副本的泛化内部与它分离，从而保留组外多态性。签名 RHS 后续使用已导出的 unsigned 接口，保持 scheme 内部固定。

### 4 外部变量如何保持共享

    \z ->
      let rec f n = if n == 0 then z else f (n - 1)
      in let i : Int = f 0 in (f 1 : Bool)

预期拒绝，因为两次使用要求同一 z 同时具有 Int 和 Bool。正确的作用域是在外层量化 z 的类型 a，局部 f 保持 Int → a。

还需测试间接依赖：f 返回 g 的结果，g 返回外部 z。只扫描 f 与 z 的直接引用关系，会漏掉这条路径。

### 5 有签名成员如何检查

已声明的 forall 按普遍性要求检查。例如 f : ∀a. a → a 要求每种 a 都成立，始终返回 Int 的实现应被拒绝。检查应保留现有 rigid/skolem 机制和无逃逸条件；递归调用则可按签名生成不同的合法实例。

本次保留现有签名语言边界，包括 existential/open recursive annotation 的检查。AST 用独立的“未签名推断模式”表示 unsigned，明确区别于 forall a. a 或 bottom 的显式签名。

### 6 类约束也必须穿过这条路径

普通 let 已有的 qualified inference 应尽量在 ordinary recursion 中保持一致。例如下列示意定义，应以 ∀a. Inspect a ⇒ a → Bool 作为目标能力：

    f x = if true then inspect x else f x

递归组内需要共享尚待解决的 predicates，组完成后统一做上下文传播、可泛化约束抽取和字典参数化。后续签名检查仅使用已证明的 givens，并继续处理 unsigned 伙伴尚待解决的 predicates。错误签名、缺失具体实例和真正歧义仍应拒绝。

完整规则与 Classes 的现有行为对齐。若第一批覆盖无类约束核心，交付时明确这一阶段范围，并继续把 qualified ordinary recursion 作为完整能力目标。

第一阶段的精确建议范围：支持所有 predicates 都能在已有规则下消解的 unsigned SCC，以及原有已签名 qualified recursion。这包括调用具体 class 实例的普通递归。需要从 unsigned 循环推断新字典接口时，给出明确的阶段性限制，并归入第二阶段工作。

第二阶段需要专门的 deferred dictionary interface。谓词槽的身份由类标识、解后的类型参数身份、所需 kind 和相关作用域共同确定。先收集每个 RHS 的直接 wanted 和合法非递归实例化产生的 wanted，再沿 unsigned 共享调用边传播这些有限约束身份，直到接口集合稳定；通过已有 givens/实例规则消解后，对仍需泛化的槽引入字典参数。必须证明传播的约束宇宙有限，并验证局部 givens 不被错误外泄，再采用该固定点算法。把原始 occurrence 列表沿环拼接会重复增长；把相同类名合并会丢失 Inspect Int 与 Inspect Bool 的区别。这部分需要在当前 SLet 处理之上新增递归接口设计。

## 六 xMLF 证据是实现的一部分

推断结束后，编译器已经知道每个定义的导出类型和每个使用点的类型。下一步要把两者的对应关系写进目标项，让独立检查器可以逐步核验。递归组内的共享假设，也在这里变成显式实例化证据。

文献结论：xMLF 将类型抽象和实例化显式化，实例化项是可局部检查的类型关系证据；图到 xMLF 的翻译需要在已解约束上构造这些证据，并保留擦除。相关约束解完后，再按规定的绑定次序和前提完成规范化与 rigidification。[R4，§§1.2、3.2–3.5]

对本项目，假设未签名递归 f 在推断体内共享 a → a，完成后导出 ∀a. a → a。目标表示的意图是：

    let rec f : forall a. a -> a =
      Λa. \x : a -> if true then x else f[a] x
    in ...

其中 f[a] 只是普通 forall 情形的简写，真实 MLF bound 需要对应的显式 computation。因此，forall binder 在递归体中的使用需要相应实例证据。

拟议证据义务：

1. 每个导出 scheme 的量词都有正确 kind、bound、依赖次序和 scope。
2. 每个 RHS 有从推断结果到其声明 binder 类型的合法证据及必要 type abstractions。
3. 每个 unsigned 组内引用有从最终导出 scheme 回到该处共享类型的证据。构造证据时使用已保存的类型身份对应关系，不根据字符串或量词顺序猜测。
4. 每个组外引用正常独立实例化。组内使用共享类型，组外使用泛化接口。
5. 多成员共享变量、每个成员不同的量词集合，以及 RHS 内部但未出现在返回类型的变量都必须有合法作用域。
6. 保留每份 RHS 的唯一性、真实递归 knot 和原 source erasure，仅增加必要的类型层证据。

当前 FVariable name Nothing 会直接输出 XVarTerm name。新增 unsigned 递归因此需要区别于普通 lambda Mono 引用的证据记录，或另一种经证明保持作用域和擦除的结构。应优先让目标语法和 checker 保持现有规则，不放松 checker 来接纳不完整的 elaboration。

### 多成员共享量词的具体候选表示

以下构造给出具体表示、操作顺序和检查点。为避免共享节点被错误移动到多个成员的 gen 下，保留一个真正拥有组内类型变量的 group scope；目标导出使用独立视图。

    RecGroupPlan
      groupScope                 合法图作用域，支配该组共享类型根
      outerEnvironment           外部环境及其类型依赖
      members                    名字、签名模式、sharedRoot、typedRhs、RHS 约束
      recursiveUses              被引用成员、occurrenceRoot、所在 RHS 和作用域

    SolvedGroupClosure
      telescope A                有依赖顺序的组级可泛化量词及 bound
      solvedMemberTypes          在共同 A 和外部环境下读出的 τi
      exports                    每个成员的 Ai、Σi 和原图身份映射

    ExportView i
      Ai                         A 中由 τi 及量词 bound 需要的依赖闭包
      Σi                         forall Ai. τi
      originMap                  原图代表节点到本次 fresh 类型变量的映射
      projection Pi              forall A. τi 到 Σi 的类型层证据

groupScope 需要满足现有 Graph 的结构可达性、binder 支配关系和 kind 不变量。region 构造 API 需要明确支持多成员根，并保持每个共享节点的唯一 binder owner。该构造的图合法性是实现前置验证项。

代码事实进一步限定了这里的实现：Graph.normalizeSparse:2293–2334 根据一个 GGen root 的结构可达性把根或不可达节点标为 rigid；同功能还有 dense 路径。因此，若直接用 f 的根代表整组，g 独有的变量可能被错误 rigidify。实现必须先让每个 export view 成为合法单根 scheme，并对剩余组内证据提供完整的多根作用域处理，或明确扩展 normalization 的区域规则且同时覆盖 dense/sparse。两条路线都以保留原有解决方案为验收标准，这部分需要新增实现。

共同 telescope A 只收集最终属于该组泛化边界的 flexible 节点，并按 bound 依赖拓扑排序。归外部环境拥有或共享的节点不进入 A；新量词的 bound 若合法提及外部变量，则保留该外部引用，不因此自动排除新量词。内层已经绑定的量词继续留在其原类型内。Ai 在 A 中取依赖闭包，因此不会保留一个依赖已删除组量词的 bound；外部依赖则仍由 Γext 提供。

候选 elaboration 算法：

1. 对每个 RHS i，创建整个 A 的 fresh 副本 Aᶦ，并建立按原图身份映射的局部类型环境。只复制目标绑定名，不复制尚未求解的图或重新做独立推断。
2. 在完整 Aᶦ 下 elaboration RHS，得到体类型 τiᶦ。这样即使某个组变量没有出现在 τi 中，RHS 内对伙伴的调用仍有合法的局部对应类型。
3. 引用 unsigned 伙伴 fj 时，从其 Σj 依次消去 Aj 的量词，将每个量词实例化到 Aᶦ 中的对应变量。对有界量词使用本地 bound 假设构造实例证据；局部上下文必须证明 bound ≤ 对应变量。
4. 为 RHS 加上 ΛAᶦ，得到 forall A. τi。再从左到右构造 Pi：保留的量词使用 under 递归进入，删除的量词使用 quantifier elimination，再 composition。消去以该量词的 bound 作 capture-avoiding substitution，更新后续仍待消去的 bound。因为 Ai 是依赖闭包，最终不会改变保留量词的 bound 或 τi，结果为精简的 Σi。当前 XOuter、XElim、XThen 已提供这种目标操作。
5. XLetRec 的 binder 直接声明 Σi，RHS 为 Pi 处理后的项。所有新增操作都只在类型层，擦除仍然是原来的一份 RHS，不增加值级别 alias 或复制递归 knot。

完整 A 如何帮助 RHS 内部使用：假设组解中 τf = a → b → b，τg = a → Bool，g 的 RHS 仍调用 f。在 g 内构造 f 的递归实例可能需要 b，即使 g 的导出类型不包含 b。完整 A 提供内部作用域，Pi 则使这部分量词不污染 g 的导出接口。

现有 Elaborate.edgeComputationIn 和相关 proof helper 可检查具体 source-to-target 对应。新增的 GroupClosure 逻辑负责决定 A、Ai、作用域归属及 projection；每步都生成交给冻结 checker 检查的实际证据。若 telescope 构造失败，修正对应的泛化或区域规则，并保持 scope 检查开启。

## 七 工作示例与验收矩阵

以下代码为语义示意，省略基础数据声明；预期类型按规则独立给定。落实为测试时需使用仓库实际语法，并明确标记运行结果。

| 编号 | 程序或场景 | 预期 | 核心检查 |
| --- | --- | --- | --- |
| A1 | let id = \x -> x in let n = id 1 in id true | 接受，Bool | 非递归 let 多态不退化 |
| A2 | \f -> let n = f 1 in f true | 拒绝 | 未标注参数不可被独立实例化 |
| A3 | 上例将 f 标为 ∀a. a → a | 接受，结果为 Bool | 局部高阶多态注解及实例证据 |
| R1 | 无签名 fact | 接受，Int → Int | 组内共享根和递归引用 |
| R2 | 无签名 even 与 odd | 接受，均为 Int → Bool | 相互递归及顺序无关 |
| R3 | f x = if true then x else f x；组外 f 1 与 f true | 接受，f 为 ∀a. a → a | 组内共享，组外分别实例化 |
| R4 | f x = if true then x else g x；g y = f y | 接受，两者为 ∀a. a → a | 共享变量、成员量化与交叉证据 |
| R5 | f x = if true then 0 else f (Cons x Nil) | 无签名拒绝 | a = List a；不可猜多态递归 |
| R6 | R5 的 f 有 ∀a. a → Int 签名 | 接受 | 递归使用在 a 与 List a 间变实例 |
| R7 | 同一 unsigned 递归 f 在组内同时要求 Int → Int 和 Bool → Bool | 拒绝 | 不偷偷 freshen 递归类型 |
| R8 | 第五节的捕获 z 反例及经 g 间接捕获版本 | 拒绝 | 外部依赖不可泛化 |
| R8b | 捕获 z 的 f n y 返回 z；组外先 f 0 true 再 f 0 1 | 接受 | z 的类型共享，但独立的 y 类型仍可泛化 |
| R9 | 第五节的 signed f 与 unsigned g 混合例 | 接受 | 签名接口切开推断循环；无 skolem 泄漏 |
| R10 | f : ∀a. a → a；f x = 1 | 拒绝 | 签名的普遍性检查 |
| R11 | ordinary recursion 调用 Inspect 方法 | 保持已有 qualified 能力或明确阶段限制 | predicates、givens、字典证据 |
| R12 | local、do-local、顶层、跨模块同 crate 的同构例子 | 行为一致 | AST、改名、依赖和缓存编码 |
| T1 | 删除 R3 目标项所需的递归 type application | 目标检查拒绝 | 证明检查器能发现缺失证据 |
| T2 | 改坏一个 XLetRec binder 类型、bound 或名字作用域 | 目标检查拒绝 | 不接受伪造声明或逃逸变量 |

还有四类必要回归：不同成员具有不同函数类型；显式 forall 重排和未使用 forall；递归名义数据与纯 alias 循环；外部 a 保持共享而 fresh flexible b 的合法 bound 提及 a 的图级正例。最后一项检查带合法外部参数的新 bound 仍保留应有的泛化能力。对可能不终止的例子只检查类型，不要求求值结束。仅在已有惰性值递归语义支持的范围内覆盖非函数 RHS，不将其扩展成任意递归类型推断。

每个正例至少经过：预设类型断言、生产目标 checker、冻结的 IndependentCheck/IndependentType、目标序列化后 parse/check、source/target erasure 比较。选取有限且会终止的例子用现有解释器核对结果。另做声明重排、无关声明插入、变量重命名的变形测试，检查结果是否只差 alpha-renaming。

## 八 实施顺序与停止条件

建议按下面顺序实施，不用第一阶段的成功掩盖后续义务。

1. 表示层：递归签名变为显式可选；更新所有解析、遍历、改名、反序列化及缓存 identity 路径，区分 None 与显式签名。
2. 核心推断：实现 unsigned 单成员和互递归子 SCC 的共享假设、求解边界及环境安全泛化。保留已签名路径。
3. 目标证据：实现导出 scheme、组内引用的实例证据及 RHS type abstractions，保持 target checker 不变。
4. 混合签名：用独立于 runtime SCC 的推断调度消除不必要限制；验证局部 skolem 和外部依赖。
5. 类和模块：完整接通 qualified inference、字典证据、跨模块组及缓存格式。若需变更缓存语义，应按项目现有版本规则处理。
6. 测试与诊断：将过去“所有递归都要签名”的拒绝用例有记录地迁移为接受例；保留真正的多态递归和错误签名负例。错误信息区分普通统一失败、需要多态递归接口、歧义和实现边界。

最低安全门槛是新代码产出的每个目标项仍通过所有现有验证门禁。完整交付还需要上述承诺的覆盖范围全部明确：哪些已实现，哪些明确未实现，哪些验证通过，哪些未运行。完成标准覆盖从源语法、推断到目标验证的全路径。

## 九 证明缺口与当前验证状态

待证明或待验证：

- unsigned SCC 的图构造是否恰好实现共享假设规则，并保留 MLF 而非仅 HM 的解决方案。
- 新调度产生的 scheme-instantiation 依赖是否保持可解算法要求的无环关系；runtime 递归环本身不构成反证。
- binder 提升、依赖闭包和组后泛化是否既不多泛化，也不无故丢失可泛化变量。
- signed-interface 调度在当前注解语言和类转换下的健全性、作用域和失败传播。
- 多成员导出 scheme 到组内共享类型的证据是否总能在合法作用域内构造。
- 类实例解析与已有数据、kind、模块扩展下的主类型及终止性，不由核心论文自动覆盖。

本报告提供实现规则、不变量和可反驳的例子。完整形式化健全性、完备性和主类型证明属于后续理论工作。独立目标检查负责验证生成项，源推断完整性和运行时性质分别验证。

截至报告完成：固定基准已审计，独立新分支已准备；编译器与测试保持原样，动态验收待执行。当前环境需要可用且获准使用的 ghc、cabal 或 emlf 工具链。接下来先交付报告，再依据这份设计实施并记录本次实际验证结果。

## 参考资料

[R1] Didier Le Botlan 与 Didier Rémy，Recasting MLF，INRIA RR 6228。重点为 §3.4 的 Rec⋆ 与 §4.2 的 Recursion。研究报告与出版版本的页码可能不同，因此使用章节和规则名定位。
https://gallium.inria.fr/~remy/mlf/recasting-mlf-RR.pdf

[R2] Didier Rémy 与 Boris Yakobowski，From ML to MLF Graphic Type Constraints with Efficient Type Inference，ICFP 2008。重点为 §1.2 泛化、§2 类型、§5 无环约束与 Theorems 1–2、§6 注解。本报告同时核对作者勘误版；作者注明修正了 Definitions 9、11 与 Figure 17，实施应以勘误版为准。
https://www.yakobowski.org/publis/2008/mlf-type-inference-icfp08-corrected.pdf
作者勘误说明：https://www.yakobowski.org/icfp08.html
所指定版本：https://gallium.inria.fr/~remy/mlf/Remy-Yakobowski@icfp08:mlf-type-inference.pdf

[R3] Alan Mycroft，Polymorphic Type Schemes and Recursive Definitions，1984。重点为 §§5–6，特别是 §6 的半算法说明和 Note 2。
https://www.cl.cam.ac.uk/~am21/papers/icop84.pdf

[R4] Didier Rémy 与 Boris Yakobowski，A Church Style Intermediate Language for MLF，2009 年 7 月作者稿。重点为 §1.2 的实例证据和 §§3.2–3.5 的 elaboration；此稿 §3.5 的 Theorem 6 是对应翻译结果。此处使用已核对的作者稿，不混用不同版本的定理编号。
https://www.yakobowski.org/publis/2009/xmlf.pdf

## 附录 固定提交代码定位

以下所有链接固定于同一个提交，不随分支后续变化。

- Surface 分组及签名门槛：https://github.com/mlf-lang/mlf/blob/c0c5dddd11ed5775e2a3d5564cfeeef8383610a5/libraries/mlf-frontend/Bootstrap/Surface.hs#L62-L120
- AST 表示：https://github.com/mlf-lang/mlf/blob/c0c5dddd11ed5775e2a3d5564cfeeef8383610a5/libraries/mlf-foundation/Bootstrap/Types.hs#L153
- 类递归转换：https://github.com/mlf-lang/mlf/blob/c0c5dddd11ed5775e2a3d5564cfeeef8383610a5/libraries/mlf-inference/Bootstrap/Classes.hs#L1101-L1148
- Mono、Poly 与递归约束：https://github.com/mlf-lang/mlf/blob/c0c5dddd11ed5775e2a3d5564cfeeef8383610a5/libraries/mlf-inference/Bootstrap/Constraint.hs#L272-L344
- 当前约束求解顺序：https://github.com/mlf-lang/mlf/blob/c0c5dddd11ed5775e2a3d5564cfeeef8383610a5/libraries/mlf-inference/Bootstrap/Constraint.hs#L903-L911
- 量词读出：https://github.com/mlf-lang/mlf/blob/c0c5dddd11ed5775e2a3d5564cfeeef8383610a5/libraries/mlf-inference/Bootstrap/Elaborate.hs#L108-L134
- 变量证据与目标递归：https://github.com/mlf-lang/mlf/blob/c0c5dddd11ed5775e2a3d5564cfeeef8383610a5/libraries/mlf-inference/Bootstrap/Elaborate.hs#L449-L531
- 目标检查：https://github.com/mlf-lang/mlf/blob/c0c5dddd11ed5775e2a3d5564cfeeef8383610a5/libraries/mlf-xmlf/Bootstrap/X/Check.hs#L195-L213
- 编译验证门禁：https://github.com/mlf-lang/mlf/blob/c0c5dddd11ed5775e2a3d5564cfeeef8383610a5/libraries/mlf-inference/Bootstrap/CompilerCore.hs#L49-L77
- 冻结测试 checker：https://github.com/mlf-lang/mlf/blob/c0c5dddd11ed5775e2a3d5564cfeeef8383610a5/tests/Tests/IndependentCheck.hs#L196-L212
