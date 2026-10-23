# QiHuang Shield 领域本体设计草案 v0.1

## 1. 文档目标

本文档用于为 QiHuang Shield 当前的“中医健康内容审核 + 知识图谱 + 向量检索 + RAG explanation”能力提供一套可落地的**轻量领域本体设计方案**。

目标不是一步到位建设完整语义网平台，而是先建立一个能够被以下模块共同消费的统一语义层：

- 指南导入与知识抽取
- Neo4j 图谱写入与查询
- Knowledge Card 结构化沉淀
- 审核规则命中与可解释输出
- Milvus 向量检索与 evidence grounding
- 后续术语治理、约束校验与轻量推理

本文档聚焦工程落地，强调：

1. 概念统一
2. 关系可计算
3. 证据可追溯
4. 审核可解释
5. 图谱与向量层可协同

---

## 2. 设计原则

### 2.1 轻量本体优先

当前阶段不强依赖 RDF / OWL / SHACL 等完整语义网栈，优先在现有 Python + PostgreSQL + Neo4j + Milvus 架构中落地以下能力：

- 核心类定义
- 关系类型定义
- 术语归一
- 类型约束
- 可解释关系路径
- 与 RAG 元数据对齐

### 2.2 业务任务驱动

本体不是独立展示层，而是直接服务以下任务：

- 内容审核判定
- explanation 生成
- citation / evidence source 展示
- 指南知识沉淀
- 语义检索后的结构化补全

### 2.3 结构化知识与语义检索并行

- **Neo4j / Ontology Layer**：负责标准概念、关系、层次、约束、路径解释
- **Milvus / Vector Layer**：负责语义召回、原文 evidence、问句与文本片段匹配

### 2.4 统一 ID 与版本化

所有核心概念、知识卡、证据源、导入版本均应使用稳定 ID，并支持版本管理，避免仅依赖中文名称造成图谱漂移。

---

## 3. 领域范围

本文档聚焦“中医健康内容审核”场景中的高频领域对象，首期不追求覆盖整个中医药知识体系，而是优先覆盖能够直接增强审核主链路的概念：

- 中药 / 方药
- 功效与宣称
- 禁忌人群
- 使用场景
- 使用方式
- 配伍禁忌
- 风险类型
- 证据来源
- 知识卡

---

## 4. 核心类表

以下为建议在 v0.1 中落地的核心类。建议每个类至少具备：

- `concept_id`：稳定标识
- `canonical_name`：标准名称
- `display_name_zh`：中文展示名
- `alias_list`：同义词 / 别名列表
- `definition`：概念定义
- `ontology_version`：本体版本
- `status`：active / deprecated / draft

### 4.1 核心类清单

| 类名 | 建议 ID 前缀 | 说明 | 示例 |
|---|---|---|---|
| `Concept` | `concept_` | 顶层抽象类，所有概念节点的公共父类 | 概念抽象层 |
| `Herb` | `herb_` | 中药实体 | 附子、甘草 |
| `Formula` | `formula_` | 方剂实体 | 四君子汤 |
| `Effect` | `effect_` | 功效或作用概念 | 回阳救逆、补气 |
| `Indication` | `indication_` | 适应证、适用目的 | 阳虚、脾虚 |
| `Population` | `population_` | 人群概念 | 孕妇、儿童 |
| `Scenario` | `scenario_` | 使用或消费场景 | 代茶饮、长期服用 |
| `UsageMethod` | `usage_` | 使用方式概念 | 泡茶、煎煮、外敷 |
| `Risk` | `risk_` | 审核风险概念 | 特殊人群风险、功效越界风险 |
| `Symptom` | `symptom_` | 症状概念 | 咳嗽、乏力 |
| `Disease` | `disease_` | 疾病概念 | 高血压 |
| `Ingredient` | `ingredient_` | 成分概念 | 生物碱等 |
| `Contraindication` | `contra_` | 禁忌事项概念 | 孕妇禁用、代茶饮禁用 |
| `EvidenceSource` | `evidence_` | 证据来源节点 | 指南段落、导入文本片段 |
| `GuidelineDocument` | `guide_` | 指南文档节点 | 某导入指南版本 |
| `KnowledgeCard` | `kc_` | 标准化知识卡 | 附子禁忌人群卡 |
| `ClaimPattern` | `claim_` | 宣称模式或风险说法模板 | 治结节、包治百病 |

### 4.2 推荐类层次

#### Population 层次

- `Population`
  - `SpecialPopulation`
    - `PregnantWomen`
    - `LactatingWomen`
    - `Children`
    - `Elderly`
    - `ChronicDiseasePatients`

#### Scenario 层次

- `Scenario`
  - `ConsumptionScenario`
    - `TeaDrinkScenario`
    - `LongTermUseScenario`
    - `MedicinalDietScenario`
    - `ClinicalPrescriptionScenario`

#### Risk 层次

- `Risk`
  - `PopulationRisk`
  - `ScenarioMisuseRisk`
  - `CompatibilityRisk`
  - `OverclaimRisk`
  - `EvidenceWeaknessRisk`

### 4.3 核心类最小属性建议

| 类别 | 必填属性 | 可选属性 |
|---|---|---|
| `Herb` / `Formula` | `concept_id`, `canonical_name`, `display_name_zh` | `pinyin`, `alias_list`, `source_standard` |
| `Population` / `Scenario` / `UsageMethod` | `concept_id`, `canonical_name`, `display_name_zh` | `alias_list`, `parent_concept_id` |
| `Effect` / `Indication` / `Risk` | `concept_id`, `canonical_name`, `display_name_zh` | `definition`, `severity_hint` |
| `KnowledgeCard` | `knowledge_card_id`, `subject_concept_id`, `predicate_type`, `object_concept_id` | `confidence_score`, `evidence_level` |
| `EvidenceSource` | `evidence_id`, `source_uri`, `source_text` | `chunk_id`, `import_job_id`, `offset_start`, `offset_end` |

---

## 5. 关系表

关系分为三类：

1. **概念层关系**：定义概念之间的稳定语义连接
2. **证据层关系**：连接知识结论与来源
3. **治理层关系**：连接版本、导入任务、知识卡

### 5.1 核心关系清单

| 关系名 | 起点类 | 终点类 | 说明 | 示例 |
|---|---|---|---|---|
| `IS_A` | `Concept` | `Concept` | 类层次或子类归属 | `PregnantWomen IS_A SpecialPopulation` |
| `HAS_EFFECT` | `Herb`/`Formula` | `Effect` | 功效关系 | `附子 HAS_EFFECT 回阳救逆` |
| `INDICATED_FOR` | `Herb`/`Formula` | `Indication`/`Symptom`/`Disease` | 适应证关系 | `某方剂 INDICATED_FOR 脾虚` |
| `CONTRAINDICATED_FOR` | `Herb`/`Formula` | `Population` | 禁忌人群 | `附子 CONTRAINDICATED_FOR 孕妇` |
| `DISALLOWED_IN` | `Herb`/`Formula` | `Scenario` | 禁用场景 | `附子 DISALLOWED_IN 代茶饮` |
| `APPLICABLE_IN` | `Herb`/`Formula` | `Scenario` | 适用场景 | `某药 APPLICABLE_IN 临床处方` |
| `USED_AS` | `Herb`/`Formula` | `UsageMethod` | 使用方式 | `某药 USED_AS 煎煮` |
| `INCOMPATIBLE_WITH` | `Herb`/`Formula` | `Herb`/`Formula` | 配伍禁忌 | `附子 INCOMPATIBLE_WITH 海藻` |
| `HAS_RISK` | `Herb`/`Formula`/`ClaimPattern` | `Risk` | 风险绑定 | `治结节宣称 HAS_RISK OverclaimRisk` |
| `TRIGGERS_RISK_FOR` | `Scenario`/`Population`/`ClaimPattern` | `Risk` | 触发风险模式 | `LongTermUseScenario TRIGGERS_RISK_FOR PopulationRisk` |
| `SUPPORTED_BY` | `KnowledgeCard` | `EvidenceSource` | 证据支撑 | `知识卡 SUPPORTED_BY 指南片段` |
| `EXTRACTED_FROM` | `KnowledgeCard`/`EvidenceSource` | `GuidelineDocument` | 来源文档 | `知识卡 EXTRACTED_FROM 某指南` |
| `ABOUT` | `KnowledgeCard`/`EvidenceSource` | `Concept` | 该知识或证据与哪个概念相关 | `片段 ABOUT 附子` |
| `NORMALIZED_TO` | `Mention` | `Concept` | 文本 mention 归一到标准概念 | `孕期女性 NORMALIZED_TO PregnantWomen` |
| `ALIAS_OF` | `ConceptAlias` | `Concept` | 同义词归属 | `妊娠期女性 ALIAS_OF PregnantWomen` |

### 5.2 关系约束建议

为避免图谱成为“任意连边数据库”，建议在导入与写图阶段进行类型校验。

| 关系 | Domain | Range | 校验规则 |
|---|---|---|---|
| `HAS_EFFECT` | `Herb`/`Formula` | `Effect` | 不允许指向 `Population` |
| `CONTRAINDICATED_FOR` | `Herb`/`Formula` | `Population` | 终点必须是标准人群概念 |
| `DISALLOWED_IN` | `Herb`/`Formula` | `Scenario` | 终点必须是场景概念 |
| `INCOMPATIBLE_WITH` | `Herb`/`Formula` | `Herb`/`Formula` | 双端需为药物相关概念 |
| `SUPPORTED_BY` | `KnowledgeCard` | `EvidenceSource` | 证据必须保留原文 |
| `EXTRACTED_FROM` | `KnowledgeCard`/`EvidenceSource` | `GuidelineDocument` | 必须能追溯到导入文档 |

### 5.3 审核最相关关系优先级

首期建议优先保障以下关系高质量落地，因为它们直接服务审核主链路：

1. `CONTRAINDICATED_FOR`
2. `DISALLOWED_IN`
3. `INCOMPATIBLE_WITH`
4. `HAS_EFFECT`
5. `SUPPORTED_BY`

---

## 6. 术语归一策略

术语归一是本体落地的关键。建议把现有“抽取后直接落图”升级为：

**文本 -> mention 抽取 -> mention 归一 -> canonical concept -> relation 入图**

### 6.1 归一目标

解决以下问题：

- 同一概念多种表达导致图谱碎片化
- 审核文本使用口语表达，无法直接命中标准术语
- explanation 中术语不统一、证据难以汇总
- 向量召回与图谱概念脱节

### 6.2 归一层级

#### Level 1：字符串标准化

对 mention 做基础规范化：

- 去空格、全半角统一
- 简繁转换（如有需要）
- 常见标点清洗
- 数字表达统一

#### Level 2：别名映射

通过别名词典把不同文本映射到同一 canonical concept。

示例：

| 原始 mention | 归一概念 ID | 标准名 |
|---|---|---|
| 孕妇 | `population_pregnant_women` | 孕妇 |
| 妊娠期女性 | `population_pregnant_women` | 孕妇 |
| 孕期女性 | `population_pregnant_women` | 孕妇 |
| 泡茶喝 | `scenario_tea_drink` | 代茶饮 |
| 当茶喝 | `scenario_tea_drink` | 代茶饮 |
| 长期喝 | `scenario_long_term_use` | 长期服用 |
| 久服 | `scenario_long_term_use` | 长期服用 |

#### Level 3：模式归一

对宣称模式和风险问法做模板化归一。

示例：

- “能治结节吗” -> `claim_treat_nodule`
- “包治” / “根治” -> `claim_absolute_cure`
- “长期喝行不行” -> `scenario_long_term_use`

#### Level 4：向量辅助候选归一

对于词典未覆盖的 mention，可通过 embedding 召回候选 concept，再由规则或 LLM 选择最优归一结果。

### 6.3 归一数据结构建议

建议新增以下数据实体：

#### ConceptAlias

| 字段 | 说明 |
|---|---|
| `alias_id` | 别名记录 ID |
| `alias_text` | 别名文本 |
| `concept_id` | 对应标准概念 |
| `alias_type` | synonym / colloquial / abbreviation / extracted |
| `confidence_score` | 置信度 |
| `status` | active / review_pending |

#### MentionNormalizationLog

| 字段 | 说明 |
|---|---|
| `mention_text` | 原始 mention |
| `normalized_concept_id` | 归一到的概念 |
| `normalization_method` | dictionary / rule / llm / vector-assisted |
| `confidence_score` | 置信度 |
| `source_request_id` | 来源请求 |

### 6.4 归一优先级策略

建议采用以下优先级：

1. 精确词典映射
2. 规则模板映射
3. 上下文约束映射
4. 向量候选召回
5. LLM 判定
6. 人工待审

### 6.5 审核中的归一示例

用户文本：

> 附子泡茶孕妇能长期喝吗？

归一结果：

- “附子” -> `herb_fuzi`
- “泡茶” -> `scenario_tea_drink`
- “孕妇” -> `population_pregnant_women`
- “长期喝” -> `scenario_long_term_use`

这样审核引擎就不再依赖原词面，而是消费标准概念和关系。

---

## 7. Neo4j 标签与边设计

### 7.1 设计目标

Neo4j 作为 ontology graph 的主要承载层，应支持：

- 核心概念存储
- 类层次表达
- 知识卡挂载
- 证据追踪
- explanation path 查询
- 基础图约束校验

### 7.2 建议标签（Labels）

| Label | 用途 |
|---|---|
| `Concept` | 所有标准概念的公共标签 |
| `Herb` | 中药概念 |
| `Formula` | 方剂概念 |
| `Effect` | 功效概念 |
| `Indication` | 适应证概念 |
| `Population` | 人群概念 |
| `Scenario` | 场景概念 |
| `UsageMethod` | 使用方式概念 |
| `Risk` | 风险概念 |
| `Symptom` | 症状概念 |
| `Disease` | 疾病概念 |
| `KnowledgeCard` | 知识卡节点 |
| `EvidenceSource` | 证据源节点 |
| `GuidelineDocument` | 指南文档节点 |
| `ConceptAlias` | 别名节点，可选 |
| `Mention` | 原始 mention 节点，可选，用于归一链路调试 |

### 7.3 建议节点属性

#### Concept 类节点通用属性

```text
concept_id
canonical_name
display_name_zh
alias_list
definition
ontology_version
status
created_at
updated_at
```

#### KnowledgeCard 节点属性

```text
knowledge_card_id
card_type
subject_concept_id
predicate_type
object_concept_id
normalized_summary
evidence_level
confidence_score
source_uri
import_job_id
ontology_version
created_at
updated_at
```

#### EvidenceSource 节点属性

```text
evidence_id
source_uri
source_text
source_type
chunk_id
offset_start
offset_end
import_job_id
version_code
created_at
```

#### GuidelineDocument 节点属性

```text
guide_id
guide_title
source_uri
source_type
version_code
import_job_id
tenant_id
created_at
```

### 7.4 建议边（Relations）

首期推荐落地以下边：

- `IS_A`
- `HAS_EFFECT`
- `INDICATED_FOR`
- `CONTRAINDICATED_FOR`
- `DISALLOWED_IN`
- `APPLICABLE_IN`
- `USED_AS`
- `INCOMPATIBLE_WITH`
- `HAS_RISK`
- `SUPPORTED_BY`
- `EXTRACTED_FROM`
- `ABOUT`
- `ALIAS_OF`
- `NORMALIZED_TO`

### 7.5 Neo4j 建模建议

#### 建议 1：概念节点统一拥有 `Concept` 标签

例如 `附子` 节点标签可为：

```text
:Concept:Herb
```

这样既能做统一查询，也能按类型过滤。

#### 建议 2：知识结论不只存边，也保留 KnowledgeCard 节点

不要只写：

```text
(附子)-[:CONTRAINDICATED_FOR]->(孕妇)
```

还应补充：

```text
(knowledge_card)-[:ABOUT]->(附子)
(knowledge_card)-[:SUPPORTED_BY]->(evidence_source)
(knowledge_card)-[:EXTRACTED_FROM]->(guideline_document)
```

这样可支持：

- citation UI
- evidence detail UI
- 不同版本知识共存
- explanation 中展示证据来源

#### 建议 3：区分“概念关系”和“证据实例”

- 图谱边表达**稳定关系**
- KnowledgeCard / EvidenceSource 表达**关系来源与证据实例**

### 7.6 典型图谱示例

```text
(附子:Concept:Herb {concept_id: "herb_fuzi"})
  -[:CONTRAINDICATED_FOR]->
(孕妇:Concept:Population {concept_id: "population_pregnant_women"})

(附子)
  -[:DISALLOWED_IN]->
(代茶饮:Concept:Scenario {concept_id: "scenario_tea_drink"})

(kc_001:KnowledgeCard {predicate_type: "CONTRAINDICATED_FOR"})
  -[:ABOUT]->(附子)
(kc_001)
  -[:SUPPORTED_BY]->(evi_001:EvidenceSource)
(kc_001)
  -[:EXTRACTED_FROM]->(guide_001:GuidelineDocument)
```

### 7.7 索引与约束建议

建议至少建立：

- `Concept.concept_id` 唯一索引
- `KnowledgeCard.knowledge_card_id` 唯一索引
- `EvidenceSource.evidence_id` 唯一索引
- `GuidelineDocument.guide_id` 唯一索引
- `ConceptAlias.alias_text` 普通索引

---

## 8. Knowledge Card 结构升级方案

当前项目中的 Knowledge Card 建议从“展示型摘要卡”升级为“本体绑定的知识单元”。

### 8.1 升级目标

Knowledge Card 应承担以下职责：

1. 承载标准化知识三元/四元结构
2. 保留原文证据与来源
3. 作为 Milvus 向量化文档的重要单元
4. 作为 explanation citation 的主要展示对象
5. 作为审核规则消费的中间知识对象

### 8.2 推荐数据结构

```json
{
  "knowledge_card_id": "kc_fuzi_contra_pregnant_001",
  "card_type": "relation_assertion",
  "subject_concept_id": "herb_fuzi",
  "subject_display_name": "附子",
  "predicate_type": "CONTRAINDICATED_FOR",
  "object_concept_id": "population_pregnant_women",
  "object_display_name": "孕妇",
  "normalized_summary": "附子禁用于孕妇。",
  "source_text": "附子：禁用于孕妇及代茶饮场景。",
  "evidence_ids": ["evidence_001"],
  "guide_id": "guide_mainline_001",
  "source_uri": "mainline-guide.md",
  "import_job_id": "import_job_001",
  "ontology_version": "v0.1",
  "knowledge_version": "kb-mainline-001",
  "confidence_score": 0.94,
  "evidence_level": "guide_explicit",
  "status": "active"
}
```

### 8.3 推荐卡片类型

| card_type | 说明 |
|---|---|
| `relation_assertion` | 明确关系卡，如禁忌、功效、适用场景 |
| `risk_assertion` | 风险断言卡 |
| `claim_pattern_card` | 宣称模式卡 |
| `evidence_summary_card` | 多证据归纳卡 |
| `conflict_review_card` | 冲突待审卡 |

### 8.4 知识卡生成规则

建议每条高价值关系至少生成一张 Knowledge Card：

- `HAS_EFFECT`
- `CONTRAINDICATED_FOR`
- `DISALLOWED_IN`
- `INCOMPATIBLE_WITH`
- `HAS_RISK`

### 8.5 知识卡与图谱的关系

每张卡至少要能映射到：

- `subject_concept_id`
- `predicate_type`
- `object_concept_id`
- `evidence_id`
- `guide_id`

这样它既能反映图谱中的结构化结论，也能在 explanation 中展示证据来源。

### 8.6 知识卡与向量层的关系

Knowledge Card 建议作为向量索引的第一类对象，而不仅仅索引原始 chunk。原因：

- 卡片更短、更标准化
- 术语已归一
- 更适合被问句召回
- 更适合作为 LLM explanation 的 grounding 证据

### 8.7 升级后的检索优先级建议

RAG 检索时建议优先召回：

1. Knowledge Card
2. Guideline Chunk
3. 规则说明卡
4. 历史审核案例卡（如后续引入）

---

## 9. 审核规则如何消费 Ontology

从 ontology 角度升级审核主链路的关键，不是“规则更复杂”，而是“规则显式依赖标准概念和关系路径”。

### 9.1 当前建议的审核链路

建议将审核流程拆成以下阶段：

1. **文本解析**：抽实体、场景、人群、宣称模式
2. **术语归一**：归一到 ontology concept
3. **图谱查询**：查询实体相关关系
4. **规则判断**：基于 concept + relation path 输出命中
5. **证据挂载**：绑定 Knowledge Card / EvidenceSource
6. **explanation 生成**：输出自然语言解释 + citation

### 9.2 推荐规则输入结构

建议审核规则不要直接消费原始文本，而是消费归一后的结构：

```json
{
  "content_id": "demo-001",
  "detected_concepts": [
    {"concept_id": "herb_fuzi", "type": "Herb", "mention": "附子"},
    {"concept_id": "population_pregnant_women", "type": "Population", "mention": "孕妇"},
    {"concept_id": "scenario_tea_drink", "type": "Scenario", "mention": "泡茶"},
    {"concept_id": "scenario_long_term_use", "type": "Scenario", "mention": "长期喝"}
  ],
  "claim_patterns": [
    {"concept_id": "claim_treat_nodule", "mention": "治结节"}
  ]
}
```

### 9.3 规则消费模式

#### 模式 A：关系命中型

示例：特殊人群风险

规则逻辑：

- 若文本中命中 `Herb`
- 且命中 `Population`
- 且图谱存在：
  - `Herb CONTRAINDICATED_FOR Population`
- 则命中 `PopulationRisk`

#### 模式 B：场景禁用型

示例：代茶饮风险

规则逻辑：

- 若文本中命中 `Herb`
- 且命中 `TeaDrinkScenario`
- 且图谱存在：
  - `Herb DISALLOWED_IN TeaDrinkScenario`
- 则命中 `ScenarioMisuseRisk`

#### 模式 C：配伍风险型

- 若文本中同时命中两个药物概念
- 且图谱存在：
  - `A INCOMPATIBLE_WITH B`
- 则命中 `CompatibilityRisk`

#### 模式 D：功效宣称越界型

- 若文本命中 `ClaimPattern`
- 且宣称模式绑定 `OverclaimRisk`
- 或问句中的 Disease / Symptom 超出实体已有 `INDICATED_FOR` 范围
- 则命中 `OverclaimRisk`

### 9.4 规则输出建议增加 relation path

规则命中结果建议新增：

```json
{
  "rule_id": "R004",
  "risk_type": "PopulationRisk",
  "hit_concepts": ["herb_fuzi", "population_pregnant_women"],
  "relation_paths": [
    "herb_fuzi -> CONTRAINDICATED_FOR -> population_pregnant_women"
  ],
  "knowledge_card_ids": ["kc_fuzi_contra_pregnant_001"],
  "evidence_ids": ["evidence_001"]
}
```

这样 explanation 与 citation 能直接挂到命中的语义路径上。

### 9.5 explanation 输出建议

建议 API 输出增加：

- `normalized_terms`
- `relation_paths`
- `knowledge_cards`
- `risk_concepts`

示例：

```json
{
  "explanation": "内容涉及附子用于孕妇长期茶饮场景，存在特殊人群使用风险与场景不当风险。",
  "normalized_terms": [
    {"mention": "孕妇", "concept_id": "population_pregnant_women"},
    {"mention": "泡茶", "concept_id": "scenario_tea_drink"}
  ],
  "relation_paths": [
    "herb_fuzi -> CONTRAINDICATED_FOR -> population_pregnant_women",
    "herb_fuzi -> DISALLOWED_IN -> scenario_tea_drink"
  ],
  "knowledge_card_ids": [
    "kc_fuzi_contra_pregnant_001",
    "kc_fuzi_disallowed_tea_001"
  ]
}
```

### 9.6 首期建议落地的 3 条 ontology-driven 规则

1. **特殊人群风险**：`CONTRAINDICATED_FOR`
2. **禁用场景风险**：`DISALLOWED_IN`
3. **配伍禁忌风险**：`INCOMPATIBLE_WITH`

因为这三类规则最容易形成高质量“概念 -> 路径 -> 证据 -> explanation”闭环。

---

## 10. 与 Milvus 的元数据对齐设计

Milvus 在本体化体系中不应被弱化，而应承担“语义召回 + 证据补全 + 概念 grounding 候选”的角色。

### 10.1 设计目标

让 Milvus 检索结果能直接回连到：

- ontology concept
- knowledge card
- guide document
- evidence source
- 审核 relation path

### 10.2 建议索引对象类型

建议至少索引两类对象：

#### 类型 A：Guideline Chunk

原始指南切片，保留更多上下文。

#### 类型 B：Knowledge Card

标准化知识对象，适合问句精确召回。

### 10.3 建议统一 metadata 字段

#### 通用 metadata

| 字段 | 说明 |
|---|---|
| `doc_id` | 向量文档 ID |
| `doc_type` | `guide_chunk` / `knowledge_card` |
| `tenant_id` | 租户 |
| `ontology_version` | 本体版本 |
| `knowledge_version` | 知识版本 |
| `import_job_id` | 导入任务 |
| `source_uri` | 来源 URI |
| `guide_id` | 文档 ID |

#### Knowledge Card metadata

| 字段 | 说明 |
|---|---|
| `knowledge_card_id` | 知识卡 ID |
| `subject_concept_id` | 主体概念 |
| `predicate_type` | 关系类型 |
| `object_concept_id` | 客体概念 |
| `risk_concept_ids` | 相关风险概念 |
| `evidence_ids` | 证据 ID 列表 |

#### Guide Chunk metadata

| 字段 | 说明 |
|---|---|
| `chunk_id` | chunk ID |
| `chunk_index` | chunk 顺序 |
| `about_concept_ids` | 相关概念列表 |
| `derived_knowledge_card_ids` | 从该 chunk 抽取出的知识卡 |
| `evidence_id` | 该 chunk 对应证据 ID |

### 10.4 推荐索引文本模板

#### Knowledge Card 向量文本模板

```text
[知识卡]
主体：附子
关系：禁忌人群
客体：孕妇
标准化摘要：附子禁用于孕妇。
证据：附子：禁用于孕妇及代茶饮场景。
```

#### Guide Chunk 向量文本模板

```text
[指南片段]
附子：功效：回阳救逆。禁用于孕妇及代茶饮场景，不宜与海藻同服。
```

### 10.5 查询时的协同策略

#### 审核 explanation 场景

1. 根据审核命中的概念与 relation path，优先过滤召回相关 Knowledge Card
2. 若需要补充上下文，再检索相关 Guide Chunk
3. 返回 evidence pack 时同时附上：
   - `knowledge_card_id`
   - `subject_concept_id`
   - `predicate_type`
   - `object_concept_id`
   - `evidence_id`

#### RAG 问答场景

1. 对用户 query 先做 mention 归一，得到 concept 候选
2. 用 query + concept filter 检索 Milvus
3. 检索到的 card/chunk 再回连 Neo4j，补全结构化关系
4. 由 LLM 生成 grounded answer

### 10.6 召回排序建议

建议综合以下因素排序：

- 向量相似度
- concept overlap 数量
- 是否为 Knowledge Card
- 是否具备高质量 `SUPPORTED_BY` 证据
- 是否来自当前激活知识版本

### 10.7 向量结果回图谱的关键路径

Milvus 返回对象后，应能通过 metadata 快速完成以下跳转：

- `knowledge_card_id` -> Neo4j `KnowledgeCard`
- `subject_concept_id` / `object_concept_id` -> Neo4j `Concept`
- `evidence_id` -> `EvidenceSource`
- `guide_id` -> `GuidelineDocument`

这一步是“语义召回”和“本体解释”衔接的关键。

---

## 11. 建议的数据流升级方案

建议将当前指南导入与审核链路升级为如下结构。

### 11.1 指南导入链路

```text
指南文本
-> chunk 切分
-> mention 抽取
-> 术语归一
-> relation 生成
-> ontology 校验
-> Neo4j 写入 Concept / Relation / KnowledgeCard / EvidenceSource
-> Knowledge Card + Chunk 生成 embedding
-> Milvus 建索引
```

### 11.2 审核链路

```text
用户内容
-> mention 抽取
-> concept 归一
-> ontology relation 查询
-> rule hit
-> Milvus 检索 evidence pack
-> explanation 生成
-> 输出 citation / relation path / evidence source
```

---

## 12. 首期落地优先级建议

建议按以下顺序推进，避免一次性改动过大。

### P0：本体骨架与 ID 体系

- 定义核心类与关系
- 引入 `concept_id`
- 确定 Neo4j labels / relations 规范

### P1：术语归一

- 引入 alias 表
- 建基础词典
- 审核文本进入 concept normalization 流程

### P2：Knowledge Card 升级

- 绑定 subject / predicate / object
- 补 evidence_id / guide_id / ontology_version
- 用作 Milvus 主索引对象

### P3：规则消费 ontology

- R004 改造成 `CONTRAINDICATED_FOR` 规则
- R002 改造成 `INCOMPATIBLE_WITH` 规则
- 茶饮/长期服用场景命中改造成 `DISALLOWED_IN` 规则

### P4：explanation 增强

- 增加 `normalized_terms`
- 增加 `relation_paths`
- citation 显示 Knowledge Card + EvidenceSource

### P5：质量治理

- 关系类型校验
- 冲突检测
- 未归一术语告警
- 版本切换与失效机制

---

## 13. 后续演进方向

当 v0.1 稳定后，可考虑继续演进：

1. 引入 `SHACL` 风格约束校验思想，在应用层先实现图谱一致性检查
2. 增加 `SKOS` 风格同义词 / 上下位词建模能力
3. 支持 RDF/OWL 导出，方便与外部语义系统互通
4. 对风险结论增加可计算推理链，如父类风险继承、场景映射推理
5. 建立“本体版本 + 知识版本 + 导入版本”三层治理机制

---

## 14. 总结

QiHuang Shield 当前最适合演进的方向，不是直接转向重型语义网平台，而是建设一个**轻量、可计算、可解释、可与现有图谱和向量检索协同的领域本体层**。

v0.1 的落地重点应当是：

- 用核心类和关系稳定领域语义边界
- 用术语归一减少图谱碎片化
- 用 Knowledge Card 承接结构化知识与 citation UI
- 用 ontology relation path 提升审核可解释性
- 用 Milvus metadata 与 ontology ID 对齐实现检索-图谱协同

若本草案落地完成，QiHuang Shield 将从“知识图谱增强审核系统”进一步演进为：

> **具备轻量领域本体层、可解释路径与语义治理能力的知识增强型 AI 审核原型。**
