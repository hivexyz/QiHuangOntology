# QiHuang Shield：从本体论/领域本体角度的项目审查

## 1. 审查目标

本文从“领域本体落地”的角度审查当前项目，而不是从传统 CRUD、接口联调或前后端功能完整性角度审查。

重点关注以下问题：

1. 项目当前是否已经形成了可复用的**统一语义层**；
2. 本体设计文档中的类、关系、约束、证据、版本机制，是否真正落到了实现里；
3. 当前实现是否足以支撑：
   - 指南导入
   - 图谱写入
   - 审核判定
   - explanation / citation
   - 向量检索与 RAG grounding
4. 如果还没有完全落地，差距主要在哪里，优先应补哪一层。

---

## 2. 总体结论

### 2.1 一句话判断

**当前项目已经具备“知识增强审核系统”的雏形，但严格从本体论角度看，它目前更像“规则引擎 + 轻量知识卡 + 图存储适配层 + 向量检索层”，还不能算一个成熟的本体驱动系统。**

### 2.2 当前阶段的准确定位

从工程形态上看，当前项目已经实现了以下闭环：

- 指南文本导入
- 规则/LLM 抽取
- 结构化实体与关系沉淀
- Neo4j 写入
- moderation 查询命中
- RAG explanation 与证据展示

但从“本体是否成为系统的核心约束层”来看，当前仍处在：

> **语义化数据建模阶段**，尚未进入真正的**本体约束驱动阶段**。

也就是说，项目已经有“本体设计意图”，但运行时主导系统行为的仍然是：

- knowledge card 结构
- rule engine 的布尔事实
- 若干硬编码关系类型
- 向量检索补充证据

而不是一个完整、稳定、可治理的 ontology layer。

---

## 3. 当前实现的优点

从本体工程落地角度，当前项目有几处做得是对的，而且非常关键。

### 3.1 已经有“统一语义层”的意识

`docs/QiHuang_Shield_Ontology_Design_v0.1.md` 已经明确提出了：

- 核心类
- 关系类型
- 术语归一
- 版本化
- 证据可追溯
- 图谱与向量层协同

这说明项目不是把 Neo4j 当成普通图数据库在用，而是已经在尝试建立**语义一致性约束**。这点非常重要。

### 3.2 实现上已经有可消费的最小语义单元

当前实现里的 `ontology_entities + knowledge_cards`，虽然还不是完整本体模型，但已经构成了可被多个模块复用的“最小语义载体”：

- 导入模块写入它
- moderation 模块读取它
- Neo4j 子图由它生成
- vector indexing 会序列化它

这说明项目已经形成了一个共享语义内核，而不是各模块各自维护一份知识结构。

### 3.3 关系类型已经开始与审核任务绑定

当前运行时真正起作用的关系包括：

- `HAS_EFFECT`
- `PROHIBITED_IN_CONTEXT`
- `ALLOWED_IN_CONTEXT`
- `NOT_FOR_POPULATION`
- `CONTRAINDICATED_WITH`

这几个关系并非随意建边，而是直接映射到审核风险判断，说明项目已经完成了“本体关系 -> 业务决策事实”的第一步。

### 3.4 有版本对象与导入作业对象

系统已有：

- `kb_version`
- `import_job`

这比“直接导入即生效”的一次性脚本系统要成熟很多。至少在模型层面，项目已经有知识版本治理的概念。

---

## 4. 从本体角度看，当前项目的核心问题

以下问题不是风格问题，而是会直接影响“本体是否真正成立”的结构性问题。

---

## 4.1 当前实现仍是“知识卡驱动”，不是“本体驱动”

### 现象

系统的核心运行对象实际上是 `KnowledgeCard`，不是本体中的“概念—关系—约束”。

当前 moderation 查询与 Neo4j 回退逻辑，主要消费的是：

- `knowledge_cards[entity_id].effects`
- `knowledge_cards[entity_id].not_for_populations`
- `knowledge_cards[entity_id].allowed_contexts`
- `knowledge_cards[entity_id].prohibited_contexts`
- `knowledge_cards[entity_id].contraindications`

也就是说，系统主要依赖“实体附带的一揽子属性包”，而不是独立的 ontology assertion。

### 本体上的问题

这会带来两个后果：

1. **关系不是一等公民**
   - 关系只存在于知识卡字段中；
   - 不方便表达关系级证据、关系级置信度、关系级版本。

2. **语义可扩展性受限**
   - 一旦新增关系类型，如 `SUPPORTED_BY`、`EXTRACTED_FROM`、`IS_A`、`NORMALIZED_TO`，当前 knowledge card 结构很快会膨胀；
   - 关系的 domain/range 约束无法独立维护。

### 判断

当前系统是“**以实体为中心的知识卡模型**”，不是“**以 assertion 为中心的本体模型**”。

---

## 4.2 文档中的核心本体类并未真正落地

### 设计文档中已有的类

文档提出了：

- `Concept`
- `Herb`
- `Formula`
- `Effect`
- `Indication`
- `Population`
- `Scenario`
- `UsageMethod`
- `Risk`
- `Contraindication`
- `EvidenceSource`
- `GuidelineDocument`
- `KnowledgeCard`
- `ClaimPattern`

### 实现中的实际落地情况

当前代码里真正稳定出现的类别主要是：

- `Material`
- `Effect`
- `Population`
- `Context`

OWL 导入时甚至默认把类统一映射为 `Material`。

### 本体上的问题

这意味着当前系统虽然写了“本体设计文档”，但实现尚未形成真正的**类型系统**：

- `Herb` 和 `Formula` 未分化；
- `Scenario` 与 `Context` 混用；
- `Indication`、`Risk`、`ClaimPattern` 在运行时不是一等实体；
- `EvidenceSource`、`GuidelineDocument` 未作为稳定节点参与图谱约束。

### 结果

最终系统更像是在做：

> “对部分审核相关字段做结构化抽取”

而不是：

> “围绕一个受约束的领域本体做知识建模和消费”。

---

## 4.3 术语归一层没有真正建立起来

### 设计意图

设计文档提出了一条比较正确的链路：

`文本 -> mention 抽取 -> mention 归一 -> canonical concept -> relation 入图`

### 当前实现

当前主链路大致是：

- 正则/LLM 直接产出材料名、功效、人群、场景
- 通过若干 alias/synonym 字典做有限清洗
- 直接写入 entity / knowledge card

系统里没有真正独立的：

- `Mention`
- `ConceptAlias`
- `NORMALIZED_TO`
- `ALIAS_OF`

### 本体上的问题

缺少独立归一层会导致：

1. **概念与提及混淆**
   - “孕妇”“妊娠期女性”“孕期女性”目前只是字符串同义映射，不是可追溯的归一结果。

2. **解释不可审计**
   - 系统难以回答“这条审核命中是因为用户文本中的哪个 mention 被归一到了哪个 canonical concept”。

3. **跨源导入容易碎片化**
   - 不同指南、不同 LLM 输出风格，容易形成多个近义但不完全一致的概念节点。

### 判断

当前有“归一化工具函数”，但还没有“归一化语义层”。

---

## 4.4 证据层不是一等模型，导致追溯链条不完整

### 文档目标

设计文档明确提出：

- `EvidenceSource`
- `SUPPORTED_BY`
- `EXTRACTED_FROM`
- `GuidelineDocument`

这套设计的本质，是要建立：

> 结论不是直接可信，而是“被某段证据支撑，并来自某个文档版本”。

### 当前实现

当前 evidence 的主要承载方式是：

- `knowledge_card["evidence"]` 中的文本列表
- vector chunk metadata
- explanation 返回中的 evidence pack

### 本体上的问题

这意味着证据仍然是“附属文本”，不是图谱中的一等对象，因而缺失：

- 证据唯一 ID
- 证据与导入文档的结构化绑定
- 关系级证据支撑
- chunk offset / source span 的统一表示
- 证据失效/替换后的可治理能力

### 后果

当前 explanation 可以“看起来有依据”，但还做不到严格意义上的：

> **ontology fact -> assertion -> evidence source -> source document version**

的完整可追溯链。

---

## 4.5 版本机制存在对象，但没有形成“已发布快照隔离”

这是当前项目最关键的本体治理问题之一。

### 当前实现现象

系统虽然有：

- `kb_version`
- `import_job`
- `publish_import_job`

但导入时会直接：

- `store.ontology_entities.update(...)`
- `store.knowledge_cards.update(...)`

也就是说，**草稿导入内容在发布前已经进入运行时主存**。

同时 moderation 查询没有按 `kb_version` 过滤，而是直接在当前 store / Neo4j snapshot 中查实体与关系。

### 本体上的问题

这会破坏 ontology governance 中最重要的原则之一：

> **草稿知识、候选知识、已发布知识必须隔离。**

当前模型下：

1. 未发布导入可能提前影响审核结果；
2. 多版本概念可能混在同一个查询空间里；
3. “当前审核是基于哪个本体快照”在语义上并不严格成立。

### 判断

现在的版本对象更像“管理台元数据”，还不是“运行时知识快照边界”。

---

## 4.6 关系约束未真正被建模为可校验机制

### 文档目标

设计文档已经提出 relation 的 domain/range 约束，例如：

- `HAS_EFFECT`: `Herb/Formula -> Effect`
- `CONTRAINDICATED_FOR`: `Herb/Formula -> Population`
- `DISALLOWED_IN`: `Herb/Formula -> Scenario`

### 当前实现

当前约束大多体现在：

- 导入代码的字段位置
- Neo4j 写边的几个固定分支
- moderation 查询时的字段假设

没有形成一个独立的、可配置的关系约束层。

### 本体上的问题

这会导致：

1. 错边进入系统时，难以统一拦截；
2. 新增关系时，必须同时修改导入、存储、查询、审核逻辑；
3. 关系语义无法被集中治理。

### 理想状态

至少应该有一层声明式关系模式，例如：

- relation code
- domain labels
- range labels
- cardinality hint
- evidence required
- moderation relevance

否则本体关系仍然停留在“几条硬编码枚举”的层面。

---

## 4.7 OWL 导入目前是“格式接入”，不是“本体语义接入”

### 当前实现的积极面

项目已经支持：

- RDF/XML
- Turtle
- JSON-LD
- Owlready2 / RDFlib 解析

这说明工程上已经在尝试接入正式本体文件，而不仅是文本抽取。

### 但当前的主要问题

1. **OWL class 默认映射为 `Material`**
   - 语义损失很大；
   - 不能保留类层级中的本体意图。

2. **`SUBCLASS_OF` 只做了统计，没有形成稳定关系消费链**
   - 文档中强调类层次；
   - 但运行时 moderation / query 逻辑基本不消费类继承关系。

3. **未知 object property 默认映射到 `HAS_EFFECT`**
   - 这会带来语义误判；
   - 一旦 OWL 中属性没有被显式映射，就可能被错误地理解为功效关系。

4. **OWL 的 richer semantics 基本未进入推理层**
   - restriction、等价类、属性特征都没有进入运行时语义系统。

### 判断

目前 OWL 能力更准确地说是：

> “支持把外部 OWL 文件解析并压扁为内部知识卡格式”

而不是：

> “支持把外部本体语义保持为系统内部可计算的 ontology layer”。

---

## 4.8 本体与审核事实之间存在“语义压缩”

### 当前 moderation 的事实层

moderation 最终消费的是一组布尔/枚举事实，例如：

- `has_prohibited_context`
- `has_population_risk`
- `has_effect_claim`
- `has_contraindication_pair`
- `has_long_term_usage`

### 这对工程是有效的

这种做法对于 MVP 非常实用，因为它让 rule engine 足够简单。

### 但本体上的代价

本体关系在进入审核引擎前被压缩成简单布尔事实，损失了很多语义信息：

- 哪条关系触发的；
- 关系来自哪个版本；
- 是否由别名归一得到；
- 是否存在冲突证据；
- 关系置信度是多少；
- 是否属于某个更高层概念路径推导。

### 结果

系统当前是：

> “本体辅助审核”

而不是：

> “本体驱动审核”。

---

## 4.9 场景/上下文的语义命名存在漂移

当前代码中，场景概念存在几种并行表达：

- `Scenario`（文档与业务层）
- `Context`（图谱/知识卡实现层）
- `tea_drink`（代码 canonical code）
- `茶饮` / `代茶饮`（显示或别名层）

这类问题看似不大，但对本体治理很关键，因为它暴露出：

1. display name 与 canonical code 没有严格分层；
2. 业务枚举与本体概念未完全对齐；
3. 同一语义在不同层被不同命名承载。

如果后续不治理，会导致：

- API、规则、图谱、前端解释用不同词；
- 版本迁移时难以保持语义一致。

---

## 5. 对当前项目的准确评价

如果必须给一个本体成熟度判断，我会这样评价：

### 5.1 当前不是“假的本体”

项目并不是简单地把几张表改名成 ontology 就结束了。它已经具备：

- 领域对象抽取
- 关系化表示
- 图数据库承载
- 向量层协同
- explanation 证据输出

这说明它确实在朝本体驱动系统演化。

### 5.2 但当前也还不是“完整本体系统”

距离成熟 ontology layer，至少还缺这四层：

1. **概念层**：统一类型系统与类层次；
2. **归一层**：mention / alias / canonical concept 分离；
3. **断言层**：关系成为一等对象，并带证据、版本、置信度；
4. **治理层**：发布快照隔离、约束校验、失效与回滚。

### 5.3 因此当前最准确的产品定义是

> **一个以知识卡为主语义载体、以图谱与向量为支撑、面向中医审核场景的知识增强 AI 系统。**

这个定义比“完整领域本体平台”更准确。

---

## 6. 建议的演进方向

下面给出我认为最值得做、且最符合当前代码基础的演进顺序。

---

## 6.1 P0：先把“已发布知识”和“草稿知识”隔离开

这是最优先的治理项。

### 建议

1. 导入结果先写入：
   - staging tables / staging graph / versioned snapshot
2. 只有 `publish` 后，才切换当前 active KB
3. moderation 查询必须显式绑定：
   - `active_kb_version`
   - 或 `requested_kb_version`

### 价值

- 让“版本”从管理字段变成运行时边界；
- 防止草稿知识污染审核结果；
- 为回滚、A/B、灰度发布提供基础。

---

## 6.2 P0：把证据建成一等对象

### 建议最小模型

- `GuidelineDocument`
- `EvidenceSource`
- `OntologyAssertion`

关系至少包括：

- `OntologyAssertion SUPPORTED_BY EvidenceSource`
- `EvidenceSource EXTRACTED_FROM GuidelineDocument`
- `OntologyAssertion ABOUT Concept`

### 价值

- explanation 才能做到真正可审计；
- citation 与源文本定位才能统一；
- 后续 RAG 与图谱可以围绕同一证据层协同。

---

## 6.3 P1：补齐“mention -> canonical concept”归一链

### 建议最小模型

- `Mention`
- `Concept`
- `ConceptAlias`

关系至少包括：

- `Mention NORMALIZED_TO Concept`
- `ConceptAlias ALIAS_OF Concept`

### 价值

- 解决多表达导致的概念碎片化；
- 让 explanation 可回答“为什么命中这个概念”；
- 使 LLM 抽取、规则抽取、向量召回可以汇聚到统一概念层。

---

## 6.4 P1：从 knowledge card 过渡到 assertion-centered 模型

### 当前问题

`KnowledgeCard` 适合展示，不适合承担全部本体职责。

### 建议

把 `KnowledgeCard` 定位为：

> 面向审核/展示的聚合视图

而不是底层事实真相。

底层建议拆成：

- `Concept`
- `OntologyAssertion`
- `EvidenceSource`
- `OntologyVersion`

然后由这些对象投影生成 knowledge card。

### 价值

- 展示层和知识层解耦；
- 可以自然支持关系级证据、冲突、置信度和多来源融合。

---

## 6.5 P1：把关系约束配置化

建议新增一套轻量 relation schema：

| 字段 | 说明 |
|---|---|
| `relation_code` | 关系编码 |
| `domain_labels` | 允许起点类型 |
| `range_labels` | 允许终点类型 |
| `symmetric` | 是否对称 |
| `evidence_required` | 是否要求证据 |
| `moderation_relevant` | 是否进入审核引擎 |

这样导入、校验、Neo4j 写入、查询层都能共享同一套关系约束。

---

## 6.6 P2：真正保留 OWL 语义，而不是只做压扁导入

### 建议

1. 保留：
   - class
   - object property
   - subclass hierarchy
2. 未识别 property 不要默认归到 `HAS_EFFECT`
3. OWL 导入要与内部 relation schema 对齐
4. 至少让 `IS_A / SUBCLASS_OF` 可被查询与解释层消费

### 价值

- 外部本体接入才不会语义失真；
- 才能逐步从“知识抽取系统”升级为“本体互操作系统”。

---

## 7. 推荐的目标架构

如果希望项目真正升级成“本体驱动审核系统”，我建议采用下面这套分层。

### 7.1 概念层 Concept Layer

承载稳定概念：

- Herb
- Formula
- Effect
- Population
- Scenario
- Risk
- ClaimPattern

### 7.2 归一层 Normalization Layer

承载：

- Mention
- Alias
- Canonical mapping
- normalization confidence

### 7.3 断言层 Assertion Layer

承载：

- subject concept
- predicate
- object concept / literal
- confidence
- status
- kb_version

### 7.4 证据层 Evidence Layer

承载：

- document
- chunk
- offset
- quoted text
- extraction source

### 7.5 投影视图层 Projection Layer

输出给业务消费：

- KnowledgeCard
- Moderation facts
- Explanation evidence pack
- Vector index document

这样一来：

- 本体层负责“真相”
- knowledge card 负责“展示”
- moderation facts 负责“规则消费”
- vector docs 负责“召回”

各层职责会清晰很多。

---

## 8. 结合当前代码的落地优先级建议

### 第一阶段：低成本高收益

1. published / draft 知识隔离
2. relation schema 配置化
3. evidence source 结构化
4. moderation 查询增加 `kb_version` 约束

### 第二阶段：真正补齐 ontology 核心能力

1. mention-normalization 层
2. assertion-centered 存储模型
3. `IS_A / SUBCLASS_OF` 可查询化
4. 关系级证据与置信度

### 第三阶段：高级本体能力

1. 轻量一致性校验
2. 冲突知识管理
3. 规则与本体路径联合解释
4. OWL 语义保持导入

---

## 9. 最终结论

从本体论/领域本体的角度看，当前项目的方向是正确的，但实现仍明显停留在“轻量语义建模 + 业务规则消费”阶段。

它的优势在于：

- 已经形成了可运行闭环；
- 已经有 ontology design 的清晰意识；
- 已经把图谱、向量、审核解释串起来了。

它当前最主要的不足在于：

- 概念层不够稳定；
- 关系层不是一等对象；
- 证据层没有结构化落地；
- 版本层没有形成发布隔离；
- 归一层缺位；
- OWL 接入仍是格式级，而非语义级。

因此，**当前项目适合被定义为“知识增强审核系统原型”，不宜高估为“完整本体驱动平台”**。

如果后续优先补齐：

1. 已发布快照隔离
2. 证据一等模型
3. mention-normalization 层
4. assertion-centered 存储

那么这个项目就会从“有本体设计文档的 AI 审核系统”，真正演进成“以本体为核心语义底座的审核系统”。
