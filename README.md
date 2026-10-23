# QiHuang Shield：中医本体治理与知识服务平台

QiHuang Shield 的主产品是一个面向中医知识的治理与服务平台。它把指南、文献和其他结构化来源中的知识，转化为可审查、可追溯、可版本化发布的本体资产，再通过知识服务接口供审核、问答、内容生成等下游应用消费。

内容审核不是本体平台本身，而是当前用于验证知识服务价值的一个下游应用方向。

```text
指南 / 文献 / OWL / 人工录入
              ↓
      知识接入与候选抽取
              ↓
术语归一 · 概念建模 · 断言治理 · 证据审阅
              ↓
       校验门禁与版本发布
              ↓
   概念查询 · 条件查询 · 证据检索 · RAG
              ↓
审核 · 问答 · 科普生成 · 其他业务应用
```

## 当前能力

### 本体治理

- 术语/提及、概念、断言、条件、证据、版本治理分层建模。
- 支持中医核心概念、关系 Schema、条件化断言和证据来源。
- 指南文本或文件导入，优先使用 OpenAI-compatible LLM 抽取，失败时回退到规则抽取。
- 导入结果先进入 draft/staged 状态，不应直接视为已发布本体真相。
- 支持 `resolved`、`unresolved`、`ambiguous`、`rejected` 等术语归一治理状态。
- 支持 staged validation、未知关系阻断、缺少证据阻断和 OWL 未解析映射告警。
- 支持发布前校验、知识版本查询、术语资源发布与回滚。

### 知识服务

- 概念、断言、条件集、证据和变更记录查询。
- 概念 bundle、断言 bundle 和条件化查询。
- PostgreSQL 承载治理与业务状态，Neo4j 承载图关系，Milvus 承载可选向量索引。
- 向量服务不可用时支持本地 memory store，运行状态会通过 health/config 接口暴露。
- 知识卡是面向应用的 projection，不能替代 Concept、Assertion、Condition 和 Evidence 真相层。

### 下游应用示范

内容审核可以通过知识服务获取概念、条件、断言和证据，再结合自己的规则与策略生成审核结果。下游应用应该记录所使用的知识版本、规则版本、策略版本和 evidence trace，不应直接修改本体资产。

## 目录结构

```text
.
├── docs/
│   ├── 中医本体基座总纲_v0.1.md
│   ├── 中医本体基座最小数据模型_DDL_v0.1.sql
│   ├── 证据与来源规范_v0.1.md
│   ├── 条件化断言表达规范_v0.1.md
│   └── improvement/
├── src/backend/
│   ├── pyproject.toml
│   ├── docker-compose.yml
│   ├── src/qihuang_shield/
│   │   ├── api/
│   │   ├── services/
│   │   ├── schemas.py
│   │   ├── store.py
│   │   └── db_store.py
│   └── tests/
└── src/frontend/
    ├── src/App.tsx
    ├── src/styles.css
    └── package.json
```

## 快速启动

### 后端

本地开发默认使用 memory store，不会自动注入 demo 数据。需要演示账号时显式设置 `QHS_ENABLE_DEMO_SEED=true`。

```bash
cd src/backend
cp .env.example .env
UV_CACHE_DIR=../../.uv-cache uv sync --extra dev
env PYTHONUNBUFFERED=1 .venv/bin/python -m uvicorn qihuang_shield.app:app --app-dir src --host 127.0.0.1 --port 8001
```

接口地址：

- 健康检查：`http://127.0.0.1:8001/healthz`
- API 前缀：`http://127.0.0.1:8001/api/v1`

### 前端

```bash
cd src/frontend
npm install
VITE_API_BASE_URL=http://127.0.0.1:8001/api/v1 npm run dev -- --host 127.0.0.1 --port 5173
```

前端当前是一个治理工作台原型，包含：

- 治理总览：当前工作版本、执行状态和治理路径。
- 访问与权限：登录和 Bearer Token 管理。
- 知识接入：上传指南并生成本体候选。
- 执行与证据：查看抽取结果、解释和来源证据。
- 开发调试：供接口联调和问题排查使用，不是平台的主要业务入口。

## API 分层

### 治理 API

治理 API 负责写入候选资产、人工复核、校验和发布：

- `POST /api/v1/ontology/guideline-imports`
- `GET /api/v1/ontology/import-jobs/{import_job_id}`
- `GET /api/v1/ontology/import-jobs/{import_job_id}/governance`
- `POST /api/v1/ontology/import-jobs/{import_job_id}/normalizations/{decision_id}/review`
- `POST /api/v1/ontology/import-jobs/{import_job_id}/normalizations/{decision_id}/concept-proposals`
- `GET /api/v1/ontology/import-jobs/{import_job_id}/concept-proposals`
- `POST /api/v1/ontology/import-jobs/{import_job_id}/concept-proposals/{proposal_id}/review`
- `POST /api/v1/ontology/import-jobs/{import_job_id}/publish`
- `GET /api/v1/ontology/normalizations`
- `POST /api/v1/ontology/normalizations/{decision_id}/review`
- `POST /api/v1/ontology/normalizations/batch-review`
- `POST /api/v1/ontology/concept-aliases/{alias_id}/review`
- `POST /api/v1/ontology/terminology/versions/publish`
- `GET /api/v1/ontology-base/validate`

### 知识服务 API

知识服务 API 面向只读消费方，返回概念、断言、条件、证据和版本信息：

- `GET /api/v1/ontology-base/concepts`
- `GET /api/v1/ontology-base/concepts/{concept_id}/bundle`
- `GET /api/v1/ontology-base/assertions`
- `GET /api/v1/ontology-base/assertions/{assertion_id}/bundle`
- `GET /api/v1/ontology-base/assertions/{assertion_id}/evidence`
- `GET /api/v1/ontology-base/assertions/{assertion_id}/condition`
- `GET /api/v1/ontology-base/releases`
- `GET /api/v1/ontology-base/releases/{release_id}`
- `POST /api/v1/vector-search/query`
- `POST /api/v1/vector-search/rag-query`

下游调用应显式指定或记录所使用的知识版本。向量索引和 projection 都是知识版本的派生资产，不是独立事实源。

导入任务中的 staged 归一化决策可以在发布前通过 import-job review 接口处理；处理结果仍停留在 staged snapshot，只有发布任务后才会写入主知识存储。

对于没有候选概念的 `unresolved` 提及，可以提交 Concept Proposal。提案必须绑定概念类型、标准名称、定义和来源证据；提案审核通过后，系统才会在 staged snapshot 中生成正式 Concept，并让对应 Mention 指向该 Concept。提案被拒绝时不会创建概念。

## 演示配置

需要演示账号时，在 `src/backend/.env` 中显式开启：

```env
QHS_ENABLE_DEMO_SEED=true
QHS_STORAGE_BACKEND=memory
```

演示账号：

- 管理员：`admin@example.com` / `password123`
- 审核员：`reviewer@example.com` / `password123`

生产或共享环境不要使用这些账号、默认数据库密码和开发密钥。

## 验证

```bash
cd src/backend
UV_CACHE_DIR=../../.uv-cache uv run pytest -q
UV_CACHE_DIR=../../.uv-cache uv run python scripts/evaluate_golden.py eval/golden_smoke.jsonl

cd ../frontend
npm run build
```

当前测试重点覆盖：

- 认证、权限和租户边界；
- 离线 golden set 抽取评测冒烟；
- 指南导入、LLM 回退和 staged/publish 隔离；
- 术语归一多状态治理；
- assertion、condition、evidence 和 projection 查询；
- OWL 未知映射与发布门禁；
- 向量索引和 RAG evidence pack。

## 平台边界

平台的真相层是：

```text
Mention / Term
      ↓
NormalizationDecision
      ↓
Concept
      ↓
Assertion + ConditionSet
      ↓
Evidence / Provenance
      ↓
Knowledge Release
```

以下对象属于派生层：

- `knowledge_card_projections`：面向应用的读模型；
- 向量索引：面向语义召回的索引；
- RAG explanation：面向用户的解释；
- 审核结果：下游应用的业务决策。

任何自动抽取结果都只能作为候选输入。任何下游应用都不应绕过发布版本直接把检索结果或审核结果写成本体事实。

## 相关文档

- [中医本体基座总纲](docs/中医本体基座总纲_v0.1.md)
- [中医本体基座最小数据模型](docs/中医本体基座最小数据模型草案_v0.1.md)
- [证据与来源规范](docs/证据与来源规范_v0.1.md)
- [条件化断言表达规范](docs/条件化断言表达规范_v0.1.md)
- [核心关系定义规范](docs/核心关系定义规范_v0.1.md)
- [版本治理规范](docs/版本治理规范_v0.1.md)
- [当前项目审查报告](docs/improvement/当前项目审查报告_2026-06-29.md)
- [本体基座改进实施审计](docs/improvement/中医本体基座改进实施审计_v0.1.md)
