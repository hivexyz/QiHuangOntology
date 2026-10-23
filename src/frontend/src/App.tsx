import { ChangeEvent, useEffect, useMemo, useRef, useState } from 'react';

type JsonValue = Record<string, unknown> | Array<unknown> | string | number | boolean | null;
type PageKey = 'dashboard' | 'login' | 'verify' | 'guideline' | 'api' | 'results';
type HttpMethod = 'GET' | 'POST';
type ServiceStatus = 'online' | 'attention' | 'offline';

type LoginResponse = {
  data?: {
    access_token?: string;
    user?: {
      email?: string;
      display_name?: string;
    };
  };
};

type ResultRecord = {
  id: number;
  title: string;
  createdAt: string;
  status: 'success' | 'error';
  payload: JsonValue;
};

type UserProfile = {
  email?: string;
  display_name?: string;
};

type ExplanationEvidence = {
  doc_id?: string;
  legacy_doc_id?: string;
  asset_type?: string;
  legacy_asset_type?: string;
  projection_asset_type?: string;
  projection_type?: string;
  text?: string;
  score?: number;
  metadata?: Record<string, unknown>;
};

type ResultEnvelope = {
  data?: {
    explanation?: string;
    explanation_evidence?: ExplanationEvidence[];
    explanation_meta?: Record<string, unknown>;
  };
};

type KnowledgeRelease = {
  release_code?: string;
  status?: string;
  published_at?: string | null;
  component_counts?: Record<string, number>;
  projection_count?: number;
};

type KnowledgeReleaseEnvelope = {
  data?: KnowledgeRelease[];
};

type GovernanceIssue = {
  issue_id?: string;
  severity?: string;
  status?: string;
  code?: string;
  title?: string;
  message?: string;
  object_type?: string;
  object_id?: string | null;
  action?: string | null;
  mention_id?: string | null;
  surface_text?: string | null;
  candidate_list?: Array<Record<string, unknown>>;
  resolved_concept_id?: string | null;
  canonical_name?: string | null;
  evidence_ids?: string[];
  evidence_sources?: Array<Record<string, unknown>>;
};

type ConceptProposal = {
  proposal_id?: string;
  decision_id?: string;
  mention_id?: string;
  surface_text?: string;
  concept_type?: string;
  standard_name?: string;
  definition?: string;
  evidence_ids?: string[];
  evidence_sources?: Array<Record<string, unknown>>;
  source_note?: string | null;
  status?: string;
  proposed_concept_id?: string | null;
  created_at?: string;
  reviewed_at?: string | null;
  reviewed_by?: string | null;
  review_reason?: string | null;
};

type OntologyConcept = {
  entity_id?: string;
  label?: string;
  standard_name?: string;
  aliases?: string[];
  kb_version?: string;
  attributes?: Record<string, unknown>;
};

type OntologyAssertion = {
  assertion_id?: string;
  subject_entity_id?: string;
  predicate_type?: string;
  object_entity_id?: string | null;
  object_value?: string | null;
  kb_version?: string;
  status?: string;
  evidence_ids?: string[];
  document_id?: string | null;
  review_status?: string | null;
  review_reason?: string | null;
  reviewed_by?: string | null;
  reviewed_at?: string | null;
};

type EvidenceSource = {
  evidence_id?: string;
  kb_version?: string;
  source_type?: string;
  source_uri?: string | null;
  source_title?: string | null;
  source_text?: string;
  document_id?: string | null;
};

type AssertionBundle = {
  assertion?: OntologyAssertion;
  condition?: { condition_set_id?: string; logic?: Record<string, unknown>; note?: string | null } | null;
  evidence_sources?: EvidenceSource[];
  change_records?: Array<Record<string, unknown>>;
};

type ConceptSearchResult = {
  concept?: OntologyConcept;
  matched_text?: string;
  match_type?: string;
  assertion_count?: number;
  evidence_count?: number;
};

type ConceptVerification = {
  concept?: OntologyConcept;
  release_code?: string | null;
  assertions?: AssertionBundle[];
  evidence_sources?: EvidenceSource[];
  change_records?: Array<Record<string, unknown>>;
  related_concepts?: OntologyConcept[];
};

type ReleaseDiff = {
  base_release_code?: string | null;
  target_release_code?: string;
  counts?: Record<string, Record<string, number>>;
  sections?: Record<string, { added?: Array<Record<string, unknown>>; removed?: Array<Record<string, unknown>>; common_count?: number }>;
};

type ObjectTimeline = {
  object_id?: string;
  object_type?: string | null;
  change_records?: Array<Record<string, unknown>>;
};

type ImportGovernance = {
  import_job?: {
    import_job_id?: string;
    kb_version_id?: string;
    status?: string;
    validation_report?: Record<string, unknown>;
    warning_count?: number;
    error_count?: number;
  };
  release_code?: string;
  summary?: {
    concepts?: number;
    assertions?: number;
    evidence?: number;
    mentions?: number;
    normalizations?: number;
    issue_count?: number;
    issue_counts_by_severity?: Record<string, number>;
    issue_counts_by_status?: Record<string, number>;
  };
  issues?: GovernanceIssue[];
  staged_assertions?: AssertionBundle[];
  concept_proposals?: ConceptProposal[];
};

const defaultApiBaseUrl = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api/v1';
const defaultGuideText = `附子（别名：黑附片）：功效：回阳救逆、温补。禁用于孕妇及代茶饮场景，不宜与海藻同服。
甘草：功效：补气。适用于食疗场景，但与海藻配伍禁忌。
黄芪：别名：北芪。功效：补气固表。适用于食疗和日常保健场景。`;
const storagePrefix = 'qihuang_shield_frontend';

function buildDefaultGuideVersion(date = new Date()): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  const hours = String(date.getHours()).padStart(2, '0');
  const minutes = String(date.getMinutes()).padStart(2, '0');
  const seconds = String(date.getSeconds()).padStart(2, '0');
  return `kb-guide-${year}${month}${day}-${hours}${minutes}${seconds}`;
}

const navigationItems: Array<{ key: PageKey; label: string; description: string }> = [
  { key: 'dashboard', label: '治理总览', description: '查看知识版本、待办事项与治理路径' },
  { key: 'login', label: '访问与权限', description: '登录、管理 Token、确认当前会话' },
  { key: 'verify', label: '知识查证', description: '检索概念、断言、条件与证据' },
  { key: 'guideline', label: '知识接入', description: '接入指南、生成本体候选并准备复核' },
  { key: 'api', label: '开发调试', description: '仅供接口联调与故障排查使用' },
  { key: 'results', label: '执行与证据', description: '查看抽取结果、依据与原始响应' },
];

const conceptTypeOptions = [
  'Concept',
  'Disease',
  'Symptom',
  'Pattern',
  'Pathogenesis',
  'TreatmentPrinciple',
  'TreatmentMethod',
  'Formula',
  'Herb',
  'Population',
  'Context',
  'Constitution',
  'Season',
  'Stage',
  'Dose',
  'Meridian',
  'ZangFu',
  'Acupoint',
];

const presetApiActions: Array<{
  label: string;
  description: string;
  path: string;
  method: HttpMethod;
  body?: Record<string, unknown>;
  requiresAuth?: boolean;
}> = [
  {
    label: '当前用户',
    description: '验证登录态与 Bearer Token 是否生效。',
    path: '/auth/me',
    method: 'GET',
    requiresAuth: true,
  },
  {
    label: '规则列表',
    description: '查看系统当前规则清单。',
    path: '/rules',
    method: 'GET',
    requiresAuth: true,
  },
  {
    label: '知识发布版本',
    description: '查看当前实例中的 draft 与 published 知识版本。',
    path: '/ontology-base/releases',
    method: 'GET',
    requiresAuth: true,
  },
];

function readStoredValue(key: string, fallback = ''): string {
  if (typeof window === 'undefined') {
    return fallback;
  }
  return window.localStorage.getItem(`${storagePrefix}:${key}`) || fallback;
}

function safeStringify(value: JsonValue): string {
  return typeof value === 'string' ? value : JSON.stringify(value, null, 2);
}

function parseResponseBody(rawText: string): JsonValue {
  try {
    return JSON.parse(rawText) as JsonValue;
  } catch {
    return rawText;
  }
}

function extractKnowledgeReleases(payload: JsonValue): KnowledgeRelease[] {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    return [];
  }
  const data = (payload as KnowledgeReleaseEnvelope).data;
  return Array.isArray(data) ? data : [];
}

function extractImportGovernance(payload: JsonValue): ImportGovernance | null {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    return null;
  }
  const data = (payload as { data?: ImportGovernance }).data;
  return data && typeof data === 'object' ? data : null;
}

function extractConceptSearchResults(payload: JsonValue): ConceptSearchResult[] {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    return [];
  }
  const data = (payload as { data?: ConceptSearchResult[] }).data;
  return Array.isArray(data) ? data : [];
}

function extractConceptVerification(payload: JsonValue): ConceptVerification | null {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    return null;
  }
  const data = (payload as { data?: ConceptVerification }).data;
  return data && typeof data === 'object' ? data : null;
}

function extractReleaseDiff(payload: JsonValue): ReleaseDiff | null {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    return null;
  }
  const data = (payload as { data?: ReleaseDiff }).data;
  return data && typeof data === 'object' ? data : null;
}

function extractObjectTimeline(payload: JsonValue): ObjectTimeline | null {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    return null;
  }
  const data = (payload as { data?: ObjectTimeline }).data;
  return data && typeof data === 'object' ? data : null;
}

async function requestJson(path: string, init?: RequestInit, token?: string): Promise<JsonValue> {
  const headers = new Headers(init?.headers || {});
  if (init?.body) {
    headers.set('Content-Type', 'application/json');
  }
  headers.set('X-Tenant-Code', 'tenant_demo');
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  const response = await fetch(`${defaultApiBaseUrl}${path}`, {
    ...init,
    headers,
  });

  const rawText = await response.text();
  const payload = rawText ? parseResponseBody(rawText) : null;
  if (!response.ok) {
    throw new Error(typeof payload === 'string' ? payload : JSON.stringify(payload, null, 2));
  }
  return payload;
}

function formatEvidenceLabel(item: ExplanationEvidence): string {
  const standardName = typeof item.metadata?.standard_name === 'string' ? item.metadata.standard_name : '';
  const assetType =
    item.projection_asset_type ||
    (typeof item.metadata?.projection_asset_type === 'string' ? item.metadata.projection_asset_type : '') ||
    item.asset_type ||
    (typeof item.metadata?.asset_type === 'string' ? item.metadata.asset_type : 'evidence');
  if (standardName) {
    return `${assetType} · ${standardName}`;
  }
  return assetType;
}

function extractExplanationBundle(payload: JsonValue): {
  explanation: string | null;
  evidence: ExplanationEvidence[];
  meta: Record<string, unknown> | null;
} {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    return { explanation: null, evidence: [], meta: null };
  }
  const envelope = payload as ResultEnvelope;
  const data = envelope.data;
  if (!data || typeof data !== 'object') {
    return { explanation: null, evidence: [], meta: null };
  }
  return {
    explanation: typeof data.explanation === 'string' ? data.explanation : null,
    evidence: Array.isArray(data.explanation_evidence) ? data.explanation_evidence : [],
    meta: data.explanation_meta && typeof data.explanation_meta === 'object' ? data.explanation_meta : null,
  };
}

function renderEvidenceDetail(item: ExplanationEvidence | null): JSX.Element | null {
  if (!item) {
    return null;
  }
  const metadataEntries = item.metadata ? Object.entries(item.metadata) : [];
  return (
    <section className="evidence-detail-card">
      <div className="evidence-panel-head">
        <h3>证据详情</h3>
        <span className="badge muted">
          {item.projection_asset_type || item.asset_type || 'evidence'}
        </span>
      </div>
      <div className="evidence-detail-grid">
        <div>
          <span>Doc ID</span>
          <code>{item.doc_id || 'unknown-doc'}</code>
        </div>
        {item.legacy_doc_id ? (
          <div>
            <span>Legacy Doc ID</span>
            <code>{item.legacy_doc_id}</code>
          </div>
        ) : null}
        <div>
          <span>Score</span>
          <strong>{typeof item.score === 'number' ? item.score.toFixed(4) : '-'}</strong>
        </div>
      </div>
      <div className="evidence-detail-body">
        <span>正文</span>
        <p>{item.text || '无正文内容'}</p>
      </div>
      {metadataEntries.length > 0 ? (
        <div className="metadata-table">
          <span>Metadata</span>
          <div className="metadata-list">
            {metadataEntries.map(([key, value]) => (
              <div key={key} className="metadata-row">
                <strong>{key}</strong>
                <span>{typeof value === 'string' ? value : JSON.stringify(value)}</span>
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </section>
  );
}

export default function App() {
  const [activePage, setActivePage] = useState<PageKey>('dashboard');
  const [email, setEmail] = useState(() => readStoredValue('email', 'admin@example.com'));
  const [password, setPassword] = useState('password123');
  const [token, setToken] = useState(() => readStoredValue('token'));
  const [userProfile, setUserProfile] = useState<UserProfile | null>(() => {
    const raw = readStoredValue('user_profile');
    if (!raw) {
      return null;
    }
    try {
      return JSON.parse(raw) as UserProfile;
    } catch {
      return null;
    }
  });
  const [guideTitle, setGuideTitle] = useState('中医指南示例');
  const [guideVersion, setGuideVersion] = useState(() => buildDefaultGuideVersion());
  const [guideText, setGuideText] = useState(defaultGuideText);
  const [guideFileName, setGuideFileName] = useState('');
  const [verifyQuery, setVerifyQuery] = useState('四君子汤');
  const [verifyConceptType, setVerifyConceptType] = useState('');
  const [verifyRelease, setVerifyRelease] = useState('');
  const [verifyResults, setVerifyResults] = useState<ConceptSearchResult[]>([]);
  const [selectedVerification, setSelectedVerification] = useState<ConceptVerification | null>(null);
  const [releaseDiff, setReleaseDiff] = useState<ReleaseDiff | null>(null);
  const [objectTimeline, setObjectTimeline] = useState<ObjectTimeline | null>(null);
  const [verifyLoading, setVerifyLoading] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('欢迎使用 QiHuang Shield 控制台。');
  const [resultRecords, setResultRecords] = useState<ResultRecord[]>([]);
  const [knowledgeReleases, setKnowledgeReleases] = useState<KnowledgeRelease[]>([]);
  const [importJobId, setImportJobId] = useState('');
  const [importGovernance, setImportGovernance] = useState<ImportGovernance | null>(null);
  const [governanceLoading, setGovernanceLoading] = useState(false);
  const [normalizationReviewIssue, setNormalizationReviewIssue] = useState<GovernanceIssue | null>(null);
  const [selectedNormalizationConcept, setSelectedNormalizationConcept] = useState('');
  const [normalizationReviewReason, setNormalizationReviewReason] = useState('');
  const [createNormalizationAlias, setCreateNormalizationAlias] = useState(true);
  const [normalizationReviewLoading, setNormalizationReviewLoading] = useState(false);
  const [conceptProposalIssue, setConceptProposalIssue] = useState<GovernanceIssue | null>(null);
  const [proposalConceptType, setProposalConceptType] = useState('Concept');
  const [proposalStandardName, setProposalStandardName] = useState('');
  const [proposalDefinition, setProposalDefinition] = useState('');
  const [proposalEvidenceIds, setProposalEvidenceIds] = useState<string[]>([]);
  const [proposalSourceNote, setProposalSourceNote] = useState('');
  const [conceptProposalLoading, setConceptProposalLoading] = useState(false);
  const [selectedConceptProposal, setSelectedConceptProposal] = useState<ConceptProposal | null>(null);
  const [proposalReviewReason, setProposalReviewReason] = useState('');
  const [proposalReviewLoading, setProposalReviewLoading] = useState(false);
  const [assertionReviewTarget, setAssertionReviewTarget] = useState<AssertionBundle | null>(null);
  const [assertionReviewReason, setAssertionReviewReason] = useState('');
  const [assertionReviewLoading, setAssertionReviewLoading] = useState(false);
  const [selectedResultId, setSelectedResultId] = useState<number | null>(null);
  const [customPath, setCustomPath] = useState('/auth/me');
  const [customMethod, setCustomMethod] = useState<HttpMethod>('GET');
  const [customBody, setCustomBody] = useState(`{
  \"content_id\": \"custom-demo-001\",
  \"content_text\": \"附子泡茶能治结节吗\",
  \"content_type\": \"note\",
  \"scenario\": \"tea_drink\",
  \"tenant_id\": \"tenant_demo\",
  \"policy_id\": \"pol_default_cn\"
}`);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [selectedEvidence, setSelectedEvidence] = useState<ExplanationEvidence | null>(null);

  const authenticated = useMemo(() => token.trim().length > 0, [token]);
  const latestResult = useMemo(
    () => resultRecords.find((item) => item.id === selectedResultId) || resultRecords[0] || null,
    [resultRecords, selectedResultId],
  );
  const latestExplanationBundle = useMemo(
    () => (latestResult ? extractExplanationBundle(latestResult.payload) : { explanation: null, evidence: [], meta: null }),
    [latestResult],
  );
  const latestPublishedRelease = useMemo(
    () => knowledgeReleases.find((release) => release.status === 'published') || null,
    [knowledgeReleases],
  );

  const successCount = resultRecords.filter((item) => item.status === 'success').length;
  const failedCount = resultRecords.filter((item) => item.status === 'error').length;
  const successRate = resultRecords.length > 0 ? Math.round((successCount / resultRecords.length) * 100) : 100;
  const serviceStatus: ServiceStatus = !authenticated
    ? 'attention'
    : failedCount > 0 && successCount === 0
      ? 'offline'
      : 'online';

  const dashboardStats = [
    { label: '服务状态', value: serviceStatus === 'online' ? '稳定运行' : serviceStatus === 'attention' ? '待确认' : '需要排查', hint: '基于当前登录状态与最近请求结果推断' },
    { label: 'API 地址', value: defaultApiBaseUrl, hint: '当前前端使用的后端 API Base URL' },
    { label: '成功率', value: `${successRate}%`, hint: '基于执行与证据中的最近请求记录' },
    { label: '最近记录', value: `${resultRecords.length}`, hint: '系统默认保留最近 20 条结果' },
  ];

  const operationMetrics = [
    { label: '已登录会话', value: authenticated ? '1' : '0', helper: authenticated ? '已写入本地 Token，可直接调用鉴权接口' : '尚未登录，部分功能将被限制' },
    { label: '成功请求', value: `${successCount}`, helper: '包括登录、导入、联调等成功返回' },
    { label: '失败请求', value: `${failedCount}`, helper: '建议在执行与证据中查看错误详情与响应体' },
    { label: '目标知识版本', value: guideVersion, helper: '下一次接入时将写入该目标版本号' },
  ];

  const governanceHighlights = [
    '版本明确：每次知识接入都绑定目标知识版本。',
    '证据可追溯：抽取结果保留解释与来源证据。',
    '变更可复核：先查看候选结果，再进入后续审核与发布流程。',
  ];

  const dossierSummaryItems = [
    { label: '概念', value: importGovernance?.summary?.concepts ?? 0 },
    { label: '断言', value: importGovernance?.summary?.assertions ?? 0 },
    { label: '证据', value: importGovernance?.summary?.evidence ?? 0 },
    { label: '提及', value: importGovernance?.summary?.mentions ?? 0 },
    { label: '归一化', value: importGovernance?.summary?.normalizations ?? 0 },
    { label: '问题', value: importGovernance?.summary?.issue_count ?? 0 },
  ];

  useEffect(() => {
    setSelectedEvidence(null);
  }, [latestResult]);

  useEffect(() => {
    if (typeof window === 'undefined') {
      return;
    }
    window.localStorage.setItem(`${storagePrefix}:email`, email);
  }, [email]);

  useEffect(() => {
    if (typeof window === 'undefined') {
      return;
    }
    if (token) {
      window.localStorage.setItem(`${storagePrefix}:token`, token);
    } else {
      window.localStorage.removeItem(`${storagePrefix}:token`);
    }
  }, [token]);

  useEffect(() => {
    if (typeof window === 'undefined') {
      return;
    }
    if (userProfile) {
      window.localStorage.setItem(`${storagePrefix}:user_profile`, JSON.stringify(userProfile));
    } else {
      window.localStorage.removeItem(`${storagePrefix}:user_profile`);
    }
  }, [userProfile]);

  useEffect(() => {
    if (!authenticated) {
      setKnowledgeReleases([]);
      return;
    }
    let cancelled = false;
    void requestJson('/ontology-base/releases', undefined, token)
      .then((payload) => {
        if (!cancelled) {
          setKnowledgeReleases(extractKnowledgeReleases(payload));
        }
      })
      .catch(() => {
        if (!cancelled) {
          setKnowledgeReleases([]);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [authenticated, token]);

  const pushResult = (title: string, status: 'success' | 'error', payload: JsonValue) => {
    const nextRecord: ResultRecord = {
      id: Date.now(),
      title,
      status,
      payload,
      createdAt: new Date().toLocaleString('zh-CN', { hour12: false }),
    };
    setResultRecords((current) => [nextRecord, ...current].slice(0, 20));
    setSelectedResultId(nextRecord.id);
  };

  const run = async (
    title: string,
    task: () => Promise<JsonValue>,
    options?: { successNotice?: string; redirectToResults?: boolean },
  ) => {
    setLoading(true);
    setError('');
    try {
      const data = await task();
      pushResult(title, 'success', data);
      setNotice(options?.successNotice || `${title} 已执行成功。`);
      if (options?.redirectToResults !== false) {
        setActivePage('results');
      }
      return data;
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setError(message);
      pushResult(title, 'error', { message, title });
      setNotice(`${title} 执行失败，请查看错误详情。`);
      if (options?.redirectToResults !== false) {
        setActivePage('results');
      }
      throw err;
    } finally {
      setLoading(false);
    }
  };

  const login = async () => {
    try {
      const payload = (await run(
        '用户登录',
        async () => {
          const response = (await requestJson('/auth/login', {
            method: 'POST',
            body: JSON.stringify({ email, password }),
          })) as LoginResponse;
          const nextToken = response.data?.access_token || '';
          const nextUser = response.data?.user || null;
          setToken(nextToken);
          setUserProfile(nextUser);
          return response as JsonValue;
        },
        { successNotice: '登录成功，已自动保存 Bearer Token。', redirectToResults: false },
      )) as LoginResponse;
      if (payload.data?.access_token) {
        setActivePage('dashboard');
      }
    } catch {
      // handled in run
    }
  };

  const logout = () => {
    setToken('');
    setUserProfile(null);
    setNotice('已退出登录并清空本地 Token。');
    setError('');
    setActivePage('login');
  };

  const saveManualToken = () => {
    setNotice('已保存当前手动输入的 Token。');
    setError('');
  };

  const loadImportGovernance = async (jobId: string, accessToken = token) => {
    if (!jobId || !accessToken) {
      return;
    }
    setGovernanceLoading(true);
    setError('');
    try {
      const payload = await requestJson(`/ontology/import-jobs/${jobId}/governance`, undefined, accessToken);
      setImportJobId(jobId);
      setImportGovernance(extractImportGovernance(payload));
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setError(`加载导入治理案卷失败：${message}`);
    } finally {
      setGovernanceLoading(false);
    }
  };

  const openNormalizationReview = (issue: GovernanceIssue) => {
    setNormalizationReviewIssue(issue);
    const firstCandidate = issue.candidate_list?.[0];
    setSelectedNormalizationConcept(
      issue.resolved_concept_id || (typeof firstCandidate?.concept_id === 'string' ? firstCandidate.concept_id : ''),
    );
    setNormalizationReviewReason('');
    setCreateNormalizationAlias(true);
  };

  const closeNormalizationReview = () => {
    if (normalizationReviewLoading) {
      return;
    }
    setNormalizationReviewIssue(null);
  };

  const submitNormalizationReview = async (status: 'resolved' | 'rejected') => {
    if (!normalizationReviewIssue?.object_id || !importJobId || !token) {
      return;
    }
    if (!normalizationReviewReason.trim()) {
      setError('请填写归一化处理理由。');
      return;
    }
    if (status === 'resolved' && !selectedNormalizationConcept) {
      setError('请选择一个候选概念后再确认归一。');
      return;
    }
    setNormalizationReviewLoading(true);
    setError('');
    try {
      const candidate = (normalizationReviewIssue.candidate_list || []).find(
        (item) => item.concept_id === selectedNormalizationConcept,
      );
      await requestJson(
        `/ontology/import-jobs/${importJobId}/normalizations/${normalizationReviewIssue.object_id}/review`,
        {
          method: 'POST',
          body: JSON.stringify({
            status,
            resolved_concept_id: status === 'resolved' ? selectedNormalizationConcept : undefined,
            canonical_name: status === 'resolved' && typeof candidate?.canonical_name === 'string' ? candidate.canonical_name : undefined,
            create_alias: status === 'resolved' ? createNormalizationAlias : false,
            reason: normalizationReviewReason.trim(),
            operator_id: userProfile?.email || 'frontend_curator',
          }),
        },
        token,
      );
      setNotice(status === 'resolved' ? '归一化决策已确认，治理案卷已刷新。' : '归一化决策已拒绝，治理案卷已刷新。');
      setNormalizationReviewIssue(null);
      await loadImportGovernance(importJobId, token);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setError(`归一化处理失败：${message}`);
    } finally {
      setNormalizationReviewLoading(false);
    }
  };

  const openConceptProposal = (issue: GovernanceIssue) => {
    setNormalizationReviewIssue(null);
    setConceptProposalIssue(issue);
    setProposalConceptType('Concept');
    setProposalStandardName(issue.surface_text || '');
    setProposalDefinition('');
    setProposalEvidenceIds(issue.evidence_ids || []);
    setProposalSourceNote(issue.message || '');
  };

  const closeConceptProposal = () => {
    if (conceptProposalLoading) {
      return;
    }
    setConceptProposalIssue(null);
  };

  const toggleProposalEvidence = (evidenceId: string) => {
    setProposalEvidenceIds((current) => (
      current.includes(evidenceId)
        ? current.filter((item) => item !== evidenceId)
        : [...current, evidenceId]
    ));
  };

  const submitConceptProposal = async () => {
    if (!conceptProposalIssue?.object_id || !importJobId || !token) {
      return;
    }
    if (!proposalStandardName.trim() || !proposalDefinition.trim()) {
      setError('请填写提案的标准名称和概念定义。');
      return;
    }
    if (proposalEvidenceIds.length === 0) {
      setError('概念提案至少需要关联一条来源证据。');
      return;
    }
    setConceptProposalLoading(true);
    setError('');
    try {
      await requestJson(
        `/ontology/import-jobs/${importJobId}/normalizations/${conceptProposalIssue.object_id}/concept-proposals`,
        {
          method: 'POST',
          body: JSON.stringify({
            concept_type: proposalConceptType,
            standard_name: proposalStandardName.trim(),
            definition: proposalDefinition.trim(),
            evidence_ids: proposalEvidenceIds,
            source_note: proposalSourceNote.trim() || undefined,
            operator_id: userProfile?.email || 'frontend_curator',
          }),
        },
        token,
      );
      setNotice('概念提案已提交，等待人工审核。');
      setConceptProposalIssue(null);
      await loadImportGovernance(importJobId, token);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setError(`概念提案提交失败：${message}`);
    } finally {
      setConceptProposalLoading(false);
    }
  };

  const openConceptProposalReview = (proposal: ConceptProposal) => {
    setSelectedConceptProposal(proposal);
    setProposalReviewReason('');
  };

  const closeConceptProposalReview = () => {
    if (!proposalReviewLoading) {
      setSelectedConceptProposal(null);
    }
  };

  const submitConceptProposalReview = async (status: 'approved' | 'rejected') => {
    if (!selectedConceptProposal?.proposal_id || !importJobId || !token) {
      return;
    }
    if (!proposalReviewReason.trim()) {
      setError('请填写概念提案的审核理由。');
      return;
    }
    setProposalReviewLoading(true);
    setError('');
    try {
      await requestJson(
        `/ontology/import-jobs/${importJobId}/concept-proposals/${selectedConceptProposal.proposal_id}/review`,
        {
          method: 'POST',
          body: JSON.stringify({
            status,
            reason: proposalReviewReason.trim(),
            operator_id: userProfile?.email || 'frontend_curator',
          }),
        },
        token,
      );
      setNotice(status === 'approved' ? '概念提案已通过，正式概念将在知识版本发布后生效。' : '概念提案已拒绝。');
      setSelectedConceptProposal(null);
      await loadImportGovernance(importJobId, token);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setError(`概念提案审核失败：${message}`);
    } finally {
      setProposalReviewLoading(false);
    }
  };

  const openAssertionReview = (bundle: AssertionBundle) => {
    setAssertionReviewTarget(bundle);
    setAssertionReviewReason('');
  };

  const closeAssertionReview = () => {
    if (!assertionReviewLoading) {
      setAssertionReviewTarget(null);
    }
  };

  const submitAssertionReview = async (status: 'accepted' | 'rejected') => {
    const assertionId = assertionReviewTarget?.assertion?.assertion_id;
    if (!assertionId || !importJobId || !token) {
      return;
    }
    if (!assertionReviewReason.trim()) {
      setError('请填写断言审核理由。');
      return;
    }
    setAssertionReviewLoading(true);
    setError('');
    try {
      await requestJson(
        `/ontology/import-jobs/${importJobId}/assertions/${assertionId}/review`,
        {
          method: 'POST',
          body: JSON.stringify({
            status,
            reason: assertionReviewReason.trim(),
            operator_id: userProfile?.email || 'frontend_curator',
          }),
        },
        token,
      );
      setNotice(status === 'accepted' ? '断言已标记为接受。' : '断言已拒绝，发布时会被排除。');
      setAssertionReviewTarget(null);
      await loadImportGovernance(importJobId, token);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setError(`断言审核失败：${message}`);
    } finally {
      setAssertionReviewLoading(false);
    }
  };

  const searchKnowledge = async () => {
    if (!verifyQuery.trim() || !token) {
      return;
    }
    setVerifyLoading(true);
    setError('');
    try {
      const params = new URLSearchParams({ query: verifyQuery.trim(), limit: '30' });
      if (verifyConceptType) {
        params.set('concept_type', verifyConceptType);
      }
      if (verifyRelease.trim()) {
        params.set('kb_version', verifyRelease.trim());
      }
      const payload = await requestJson(`/ontology-base/concept-search?${params.toString()}`, undefined, token);
      const items = extractConceptSearchResults(payload);
      setVerifyResults(items);
      setSelectedVerification(null);
      setNotice(`查证检索完成，找到 ${items.length} 个概念。`);
      if (items[0]?.concept?.entity_id) {
        await loadConceptVerification(items[0].concept.entity_id, items[0].concept.kb_version || verifyRelease.trim());
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setError(`知识查证失败：${message}`);
    } finally {
      setVerifyLoading(false);
    }
  };

  const loadConceptVerification = async (conceptId: string, releaseCode?: string | null) => {
    if (!conceptId || !token) {
      return;
    }
    setVerifyLoading(true);
    setError('');
    try {
      const params = new URLSearchParams();
      const release = (releaseCode || verifyRelease).trim();
      if (release) {
        params.set('kb_version', release);
      }
      const suffix = params.toString() ? `?${params.toString()}` : '';
      const payload = await requestJson(`/ontology-base/concepts/${conceptId}/verification${suffix}`, undefined, token);
      const verification = extractConceptVerification(payload);
      setSelectedVerification(verification);
      setObjectTimeline(null);
      if (verification?.concept?.entity_id) {
        await loadObjectTimeline(verification.concept.entity_id, 'concept');
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setError(`概念查证详情加载失败：${message}`);
    } finally {
      setVerifyLoading(false);
    }
  };

  const loadReleaseDiff = async (releaseCode?: string | null) => {
    const target = (releaseCode || selectedVerification?.release_code || selectedVerification?.concept?.kb_version || '').trim();
    if (!target || !token) {
      return;
    }
    setVerifyLoading(true);
    setError('');
    try {
      const payload = await requestJson(`/ontology-base/releases/${target}/diff`, undefined, token);
      setReleaseDiff(extractReleaseDiff(payload));
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setError(`版本差异加载失败：${message}`);
    } finally {
      setVerifyLoading(false);
    }
  };

  const loadObjectTimeline = async (objectId: string, objectType?: string) => {
    if (!objectId || !token) {
      return;
    }
    try {
      const params = new URLSearchParams();
      if (objectType) {
        params.set('object_type', objectType);
      }
      const suffix = params.toString() ? `?${params.toString()}` : '';
      const payload = await requestJson(`/ontology-base/objects/${objectId}/timeline${suffix}`, undefined, token);
      setObjectTimeline(extractObjectTimeline(payload));
    } catch {
      setObjectTimeline(null);
    }
  };

  const fileToBase64 = async (file: File): Promise<string> => {
    const buffer = await file.arrayBuffer();
    let binary = '';
    const bytes = new Uint8Array(buffer);
    const chunkSize = 0x8000;
    for (let index = 0; index < bytes.length; index += chunkSize) {
      const chunk = bytes.subarray(index, index + chunkSize);
      binary += String.fromCharCode(...chunk);
    }
    return btoa(binary);
  };

  const onGuideFileChange = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) {
      setGuideFileName('');
      return;
    }
    setGuideFileName(file.name);
    if (file.type.startsWith('text/') || /\.(txt|md|markdown|csv)$/i.test(file.name)) {
      const text = await file.text();
      setGuideText(text);
      setNotice(`已读取文本文件：${file.name}`);
      return;
    }
    setGuideText('');
    setNotice(`已选择二进制文件：${file.name}，提交时会自动转 base64 上传。`);
  };

  const importGuideline = async () => {
    const file = fileInputRef.current?.files?.[0];
    try {
      const response = await run(
      '中医指南上传与抽取',
      async () => {
        const body: Record<string, unknown> = {
          source_uri: guideFileName || 'frontend-guideline-demo',
          source_type: file ? 'guideline_file' : 'guideline_text',
          target_version_code: guideVersion,
          guide_title: guideTitle,
          guide_text: guideText,
        };
        if (file) {
          body.guide_file_name = file.name;
          body.guide_file_base64 = await fileToBase64(file);
        }
        return requestJson(
          '/ontology/guideline-imports',
          {
            method: 'POST',
            body: JSON.stringify(body),
          },
          token,
        );
      },
        { successNotice: '知识候选已生成，请检查导入治理案卷。', redirectToResults: false },
      );
      const responseData = typeof response === 'object' && response !== null ? (response as Record<string, unknown>).data : null;
      const importJob = responseData && typeof responseData === 'object' ? (responseData as Record<string, unknown>).import_job : null;
      const nextJobId = importJob && typeof importJob === 'object' ? String((importJob as Record<string, unknown>).import_job_id || '') : '';
      if (nextJobId) {
        await loadImportGovernance(nextJobId, token);
        setActivePage('guideline');
      }
    } catch {
      // handled in run
    }
  };

  const runPresetAction = async (label: string, path: string, method: HttpMethod, body?: Record<string, unknown>) => {
    await run(label, () =>
      requestJson(
        path,
        {
          method,
          body: body ? JSON.stringify(body) : undefined,
        },
        token,
      ),
    );
  };

  const fetchCurrentUser = async () => {
    try {
      const payload = await run('获取当前用户', () => requestJson('/auth/me', undefined, token), {
        successNotice: '当前登录用户信息获取成功。',
        redirectToResults: false,
      });
      const data = typeof payload === 'object' && payload !== null ? (payload as Record<string, unknown>).data : null;
      if (data && typeof data === 'object') {
        setUserProfile(data as UserProfile);
      }
    } catch {
      // handled in run
    }
  };

  const sendCustomRequest = async () => {
    await run('自定义接口请求', async () => {
      const normalizedPath = customPath.startsWith('/') ? customPath : `/${customPath}`;
      let body: string | undefined;
      if (customMethod === 'POST') {
        const trimmed = customBody.trim();
        body = trimmed ? JSON.stringify(JSON.parse(trimmed)) : undefined;
      }
      return requestJson(
        normalizedPath,
        {
          method: customMethod,
          body,
        },
        token,
      );
    });
  };

  const renderDashboardPage = () => (
    <div className="page-section stack-xl">
      <section className="hero-card hero-card-premium">
        <div className="hero-main">
          <div className="eyebrow-row">
            <span className="badge brand">Ontology Governance</span>
            <span className={`status-dot ${serviceStatus}`}>{serviceStatus === 'online' ? '服务稳定' : serviceStatus === 'attention' ? '待完成登录' : '需要排查'}</span>
          </div>
          <h1>让中医知识可审查、可追溯、可发布</h1>
          <p className="hero-text">
            从指南接入、候选抽取到证据复核，集中管理中医概念、关系、断言与知识版本。
          </p>
          <div className="hero-actions">
            <button onClick={() => setActivePage('guideline')}>接入知识</button>
            <button className="secondary" onClick={() => setActivePage('api')}>
              开发调试
            </button>
            <button className="ghost" onClick={() => setActivePage('results')}>
              查看证据与结果
            </button>
          </div>
        </div>

        <div className="hero-side">
          <div className="hero-side-card emphasis">
            <span>当前会话</span>
            <strong>{authenticated ? userProfile?.display_name || '已登录用户' : '未登录'}</strong>
            <small>{authenticated ? userProfile?.email || email : '请先完成鉴权再操作受保护接口'}</small>
          </div>
          <div className="hero-side-card">
            <span>服务连接</span>
            <code>{defaultApiBaseUrl}</code>
          </div>
          <div className="hero-side-card compact-metrics">
            <div>
              <span>成功</span>
              <strong>{successCount}</strong>
            </div>
            <div>
              <span>失败</span>
              <strong>{failedCount}</strong>
            </div>
          </div>
        </div>
      </section>

      <section className="governance-strip" aria-label="当前治理工作区状态">
        <div>
          <span>当前工作版本</span>
          <strong>{latestPublishedRelease?.release_code || guideVersion}</strong>
          <small>{latestPublishedRelease ? '当前已发布知识版本' : '下一次知识接入的目标版本'}</small>
        </div>
        <div>
          <span>最近变更</span>
          <strong>{latestResult ? latestResult.title : '暂无记录'}</strong>
          <small>{latestResult ? latestResult.createdAt : '等待第一次接入或服务调用'}</small>
        </div>
        <div>
          <span>证据状态</span>
          <strong>{latestExplanationBundle.evidence.length > 0 ? '已关联' : '待复核'}</strong>
          <small>{latestExplanationBundle.evidence.length > 0 ? '最近结果包含来源证据' : '导入后请检查证据与依据'}</small>
        </div>
      </section>

      <section className="stats-grid enhanced">
        {dashboardStats.map((item) => (
          <article key={item.label} className="stat-card premium">
            <span className="stat-label">{item.label}</span>
            <strong className="stat-value">{item.value}</strong>
            <p className="stat-hint">{item.hint}</p>
          </article>
        ))}
      </section>

      <section className="ops-grid">
        <article className="panel feature-panel">
          <div className="panel-header">
            <div>
              <h2>治理工作区</h2>
              <p>围绕知识接入、证据复核和版本管理组织主要入口。</p>
            </div>
          </div>
          <div className="shortcut-grid premium-shortcuts">
            <button className="shortcut-card premium" onClick={() => setActivePage('login')}>
              <strong>访问与权限</strong>
              <span>账号登录、Token 管理、当前用户校验</span>
            </button>
            <button className="shortcut-card premium" onClick={() => setActivePage('guideline')}>
              <strong>知识接入</strong>
              <span>上传指南文本或文件，生成本体候选</span>
            </button>
            <button className="shortcut-card premium" onClick={() => setActivePage('verify')}>
              <strong>知识查证</strong>
              <span>检索概念、断言、条件与证据</span>
            </button>
            <button className="shortcut-card premium" onClick={() => setActivePage('api')}>
              <strong>开发调试</strong>
              <span>验证知识服务接口与运行时状态</span>
            </button>
            <button className="shortcut-card premium" onClick={() => setActivePage('results')}>
              <strong>执行与证据</strong>
              <span>查看抽取结果、依据、引用和错误</span>
            </button>
          </div>
        </article>

        <article className="panel feature-panel">
          <div className="panel-header">
            <div>
              <h2>系统运行</h2>
              <p>把服务和最近执行状态集中展示，帮助定位接入问题。</p>
            </div>
          </div>
          <div className="metric-list">
            {operationMetrics.map((item) => (
              <div key={item.label} className="metric-row">
                <div>
                  <strong>{item.label}</strong>
                  <span>{item.helper}</span>
                </div>
                <em>{item.value}</em>
              </div>
            ))}
          </div>
        </article>
      </section>

      <section className="three-column-grid">
        <article className="panel">
          <div className="panel-header">
            <div>
              <h2>治理路径</h2>
              <p>当前前端先承载接入与证据查看，发布治理能力持续补齐。</p>
            </div>
          </div>
          <ol className="journey-list">
            <li>先在“访问与权限”页面完成登录或粘贴 Token。</li>
            <li>再在“知识接入”页面准备指南标题、目标版本和文件。</li>
            <li>最后在“执行与证据”确认候选结果、证据和异常信息。</li>
          </ol>
        </article>

        <article className="panel">
          <div className="panel-header">
            <div>
              <h2>治理原则</h2>
              <p>平台先管理可信知识，下游应用再消费已发布版本。</p>
            </div>
          </div>
          <ul className="tips-list compact">
            {governanceHighlights.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </article>

        <article className="panel cta-panel">
          <div className="panel-header">
            <div>
              <h2>当前任务</h2>
              <p>从一次知识接入开始，形成可检查的候选结果。</p>
            </div>
          </div>
          <div className="button-row vertical">
            <button onClick={() => void fetchCurrentUser()} disabled={loading || !authenticated}>
              获取当前用户
            </button>
              <button className="secondary" onClick={() => setActivePage('guideline')}>
                发起知识接入
            </button>
            <button className="ghost" onClick={() => setActivePage('api')}>
                前往开发调试
            </button>
          </div>
        </article>
      </section>
    </div>
  );

  const renderLoginPage = () => (
    <div className="page-section two-column">
      <section className="panel">
        <div className="panel-header">
          <div>
            <h2>身份认证</h2>
            <p>支持通过账号密码登录，也支持手动维护 Bearer Token。</p>
          </div>
          <span className={`badge ${authenticated ? 'success' : 'warning'}`}>{authenticated ? '会话有效' : '未认证'}</span>
        </div>
        <label>
          邮箱
          <input value={email} onChange={(event) => setEmail(event.target.value)} placeholder="请输入邮箱" />
        </label>
        <label>
          密码
          <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="请输入密码" />
        </label>
        <div className="button-row">
          <button onClick={() => void login()} disabled={loading}>
            {loading ? '处理中...' : '登录'}
          </button>
          <button className="secondary" onClick={() => void fetchCurrentUser()} disabled={loading || !authenticated}>
            刷新当前用户
          </button>
          <button className="danger" onClick={logout} disabled={!authenticated}>
            退出登录
          </button>
        </div>
      </section>

      <section className="panel">
        <div className="panel-header">
          <div>
            <h2>会话信息</h2>
            <p>登录成功后会将 Token 与用户信息保存在本地浏览器。</p>
          </div>
        </div>
        <div className="info-list info-list-single-mobile">
          <div>
            <span>显示名称</span>
            <strong>{userProfile?.display_name || '-'}</strong>
          </div>
          <div>
            <span>用户邮箱</span>
            <strong>{userProfile?.email || email || '-'}</strong>
          </div>
        </div>
        <label>
          Bearer Token
          <textarea rows={8} value={token} onChange={(event) => setToken(event.target.value)} placeholder="登录后会自动填充，也可手动粘贴。" />
        </label>
        <div className="button-row">
          <button className="secondary" onClick={saveManualToken} disabled={!token.trim()}>
            保存 Token
          </button>
          <button className="ghost" onClick={() => setActivePage('api')}>
            去接口联调
          </button>
        </div>
      </section>
    </div>
  );

  const renderVerificationPage = () => {
    const verification = selectedVerification;
    const concept = verification?.concept;
    return (
      <div className="page-section verification-layout">
        <section className="panel verification-search-panel">
          <div className="panel-header">
            <div>
              <h2>知识查证</h2>
              <p>按概念、版本和类型检索已发布知识，查看断言、条件与证据。</p>
            </div>
            <span className={`badge ${authenticated ? 'success' : 'warning'}`}>{authenticated ? '可查询' : '请先登录'}</span>
          </div>

          <div className="verify-form">
            <label>
              查询词
              <input value={verifyQuery} onChange={(event) => setVerifyQuery(event.target.value)} placeholder="例如：四君子汤、人参、脾气虚证" />
            </label>
            <label>
              概念类型
              <select value={verifyConceptType} onChange={(event) => setVerifyConceptType(event.target.value)}>
                <option value="">全部类型</option>
                {conceptTypeOptions.map((type) => <option key={type} value={type}>{type}</option>)}
              </select>
            </label>
            <label>
              知识版本
              <input value={verifyRelease} onChange={(event) => setVerifyRelease(event.target.value)} placeholder="留空则跨版本检索" />
            </label>
            <div className="button-row verify-actions">
              <button onClick={() => void searchKnowledge()} disabled={verifyLoading || !authenticated || !verifyQuery.trim()}>
                {verifyLoading ? '查询中...' : '查询知识'}
              </button>
              <button className="ghost" onClick={() => setVerifyRelease(latestPublishedRelease?.release_code || '')} disabled={!latestPublishedRelease}>
                使用最新发布版
              </button>
            </div>
          </div>

          <div className="verify-result-list">
            {verifyResults.length === 0 ? (
              <div className="empty-state">输入概念名或别名后开始查证。</div>
            ) : (
              verifyResults.map((item) => {
                const itemConcept = item.concept || {};
                const active = concept?.entity_id === itemConcept.entity_id;
                return (
                  <button
                    key={itemConcept.entity_id || item.matched_text}
                    className={`verify-result-item ${active ? 'active' : ''}`}
                    onClick={() => itemConcept.entity_id ? void loadConceptVerification(itemConcept.entity_id, itemConcept.kb_version || verifyRelease) : undefined}
                  >
                    <div>
                      <strong>{itemConcept.standard_name || '未命名概念'}</strong>
                      <span>{itemConcept.label || 'Concept'} · {itemConcept.kb_version || '-'}</span>
                    </div>
                    <small>{item.match_type || 'match'}: {item.matched_text || '-'}</small>
                    <em>{item.assertion_count || 0} 断言 / {item.evidence_count || 0} 证据</em>
                  </button>
                );
              })
            )}
          </div>
        </section>

        <section className="panel verification-detail-panel">
          {!verification ? (
            <div className="empty-state verify-empty-detail">选择一个概念后查看断言、条件、证据与版本信息。</div>
          ) : (
            <>
              <div className="verification-concept-head">
                <div>
                  <span className="section-kicker">{concept?.label || 'Concept'}</span>
                  <h2>{concept?.standard_name || '未命名概念'}</h2>
                  <p>{typeof concept?.attributes?.definition === 'string' ? concept.attributes.definition : '暂无定义'}</p>
                </div>
                <span className="badge success">{verification.release_code || concept?.kb_version || 'release'}</span>
              </div>

              {concept?.aliases && concept.aliases.length > 0 ? (
                <div className="alias-strip">
                  {concept.aliases.map((alias) => <span key={alias}>{alias}</span>)}
                </div>
              ) : null}

              <div className="verification-meta-grid">
                <article>
                  <div className="meta-card-head">
                    <strong>版本差异</strong>
                    <button className="ghost small" onClick={() => void loadReleaseDiff(verification.release_code || concept?.kb_version)} disabled={verifyLoading || !(verification.release_code || concept?.kb_version)}>
                      加载差异
                    </button>
                  </div>
                  {releaseDiff ? (
                    <div className="release-diff-summary">
                      <span>{releaseDiff.base_release_code || '无基线'} → {releaseDiff.target_release_code || '-'}</span>
                      {Object.entries(releaseDiff.counts || {}).map(([section, counts]) => (
                        <small key={section}>{section}: +{counts.added || 0} / -{counts.removed || 0} / ={counts.common || 0}</small>
                      ))}
                    </div>
                  ) : <small className="muted-line">加载后查看本版本相对上一发布版的变更。</small>}
                </article>
                <article>
                  <div className="meta-card-head">
                    <strong>变更时间线</strong>
                    <span className="badge muted">{objectTimeline?.change_records?.length || 0} 条</span>
                  </div>
                  {objectTimeline?.change_records && objectTimeline.change_records.length > 0 ? (
                    <div className="timeline-list">
                      {objectTimeline.change_records.slice(0, 4).map((record, index) => (
                        <small key={typeof record.change_id === 'string' ? record.change_id : index}>{String(record.change_type || 'change')} · {String(record.change_summary || '')}</small>
                      ))}
                    </div>
                  ) : <small className="muted-line">暂无聚合变更记录。</small>}
                </article>
              </div>

              <div className="verification-section">
                <div className="issue-queue-head">
                  <div>
                    <h3>断言</h3>
                    <p>每条断言都绑定条件、证据和所属版本。</p>
                  </div>
                  <span className="badge muted">{verification.assertions?.length || 0} 条</span>
                </div>
                <div className="verification-assertion-list">
                  {(verification.assertions || []).map((bundle) => {
                    const assertion = bundle.assertion || {};
                    const related = (verification.related_concepts || []).find((item) => item.entity_id === assertion.object_entity_id || item.entity_id === assertion.subject_entity_id);
                    return (
                      <article key={assertion.assertion_id} className="verification-assertion-card">
                        <div className="assertion-card-head">
                          <strong>{assertion.predicate_type || 'UNKNOWN_RELATION'}</strong>
                          <span className="badge muted">{assertion.status || 'draft'}</span>
                        </div>
                        <p>{related?.standard_name || assertion.object_value || assertion.object_entity_id || assertion.subject_entity_id}</p>
                        {bundle.condition ? (
                          <div className="condition-box">
                            <span>条件</span>
                            <code>{safeStringify(bundle.condition.logic || {})}</code>
                          </div>
                        ) : null}
                        {bundle.evidence_sources && bundle.evidence_sources.length > 0 ? (
                          <div className="verify-evidence-list">
                            {bundle.evidence_sources.map((evidence) => (
                              <blockquote key={evidence.evidence_id}>
                                <p>{evidence.source_text || '无证据正文'}</p>
                                <cite>{evidence.source_title || evidence.source_uri || evidence.evidence_id}</cite>
                              </blockquote>
                            ))}
                          </div>
                        ) : <small className="muted-line">暂无证据片段</small>}
                      </article>
                    );
                  })}
                </div>
              </div>

              {verification.related_concepts && verification.related_concepts.length > 0 ? (
                <div className="verification-section">
                  <h3>相关概念</h3>
                  <div className="related-concept-grid">
                    {verification.related_concepts.map((item) => (
                      <button key={item.entity_id} className="related-concept-chip" onClick={() => item.entity_id ? void loadConceptVerification(item.entity_id, item.kb_version) : undefined}>
                        <strong>{item.standard_name}</strong>
                        <span>{item.label}</span>
                      </button>
                    ))}
                  </div>
                </div>
              ) : null}
            </>
          )}
        </section>
      </div>
    );
  };

  const renderGuidelinePage = () => (
    <div className="page-section stack-lg">
      <section className="panel">
        <div className="panel-header">
          <div>
            <h2>知识接入与候选抽取</h2>
            <p>接入指南文本或文件，生成待复核的概念、关系、断言与证据候选。</p>
          </div>
          <span className={`badge ${authenticated ? 'success' : 'warning'}`}>{authenticated ? '允许提交' : '请先登录'}</span>
        </div>

        <div className="form-grid">
          <label>
            指南标题
            <input value={guideTitle} onChange={(event) => setGuideTitle(event.target.value)} placeholder="请输入指南标题" />
          </label>
          <label>
            目标知识版本
            <input
              value={guideVersion}
              onChange={(event) => setGuideVersion(event.target.value)}
              placeholder="例如：kb-guide-20260622-153045"
            />
          </label>
        </div>

        <label>
          指南文件
          <input ref={fileInputRef} type="file" accept=".txt,.md,.markdown,.csv,.docx,.pdf,application/pdf" onChange={(event) => void onGuideFileChange(event)} />
          {guideFileName ? <span className="field-help">已选择文件：{guideFileName}</span> : <span className="field-help">可选，不传文件时将直接使用下方正文。</span>}
        </label>

        <label>
          指南正文
          <textarea rows={14} value={guideText} onChange={(event) => setGuideText(event.target.value)} placeholder="粘贴中医医学指南正文，建议包含药材、功效、禁忌、适用场景等描述。" />
        </label>

        <div className="button-row">
          <button onClick={() => void importGuideline()} disabled={loading || !authenticated}>
            {loading ? '处理中...' : '生成本体候选'}
          </button>
          <button className="secondary" onClick={() => setGuideText(defaultGuideText)}>
            填充示例文本
          </button>
          <button className="ghost" onClick={() => setActivePage('results')}>
            查看抽取结果
          </button>
        </div>
      </section>

      <section className="governance-dossier panel">
        <div className="dossier-header">
          <div>
            <span className="section-kicker">导入案卷</span>
            <h2>导入治理案卷</h2>
            <p>这里汇总本次接入产生的候选资产与待处理问题。候选结果经过复核和校验后，才能进入发布。</p>
          </div>
          <div className="button-row">
            {importJobId ? (
              <button className="ghost" onClick={() => void loadImportGovernance(importJobId)} disabled={governanceLoading || !authenticated}>
                {governanceLoading ? '刷新中...' : '刷新案卷'}
              </button>
            ) : null}
            <span className={`badge ${importGovernance?.import_job?.status === 'published' ? 'success' : importGovernance ? 'warning' : 'muted'}`}>
              {importGovernance?.import_job?.status || '等待导入'}
            </span>
          </div>
        </div>

        {!importGovernance ? (
          <div className="empty-state dossier-empty">
            完成一次知识接入后，这里会显示版本摘要、抽取统计、归一化问题和校验告警。
          </div>
        ) : (
          <>
            <div className="dossier-summary-grid">
              <div className="dossier-summary-item dossier-release-item">
                <span>目标版本</span>
                <strong>{importGovernance.release_code || guideVersion}</strong>
              </div>
              {dossierSummaryItems.map((item) => (
                <div key={item.label} className="dossier-summary-item">
                  <span>{item.label}</span>
                  <strong>{item.value}</strong>
                </div>
              ))}
            </div>

            <div className="issue-queue-head">
              <div>
                <h3>待处理问题</h3>
                <p>按严重度展示会影响知识可信度或发布门禁的问题。</p>
              </div>
              <span className={`badge ${importGovernance.issues && importGovernance.issues.length > 0 ? 'warning' : 'success'}`}>
                {importGovernance.issues?.length || 0} 项
              </span>
            </div>

            {importGovernance.issues && importGovernance.issues.length > 0 ? (
              <div className="issue-list">
                {importGovernance.issues.map((issue, index) => {
                  const severity = issue.severity || 'warning';
                  return (
                    <article key={issue.issue_id || `${issue.code}-${index}`} className={`governance-issue ${severity}`}>
                      <div className="issue-severity">{severity === 'error' ? '阻断' : severity === 'warning' ? '待复核' : '提示'}</div>
                      <div className="issue-content">
                        <div className="issue-title-row">
                          <strong>{issue.title || issue.code || '治理问题'}</strong>
                          <span className="badge muted">{issue.status || 'open'}</span>
                        </div>
                        <p>{issue.message || '请打开问题详情确认处理方式。'}</p>
                        <small>
                          {issue.object_type || 'import_job'}{issue.object_id ? ` · ${issue.object_id}` : ''}
                          {issue.action ? ` · ${issue.action}` : ''}
                        </small>
                        {issue.action === 'resolve_normalization' ? (
                          <div className="issue-actions">
                            <button className="secondary small" onClick={() => openNormalizationReview(issue)} disabled={normalizationReviewLoading}>
                              处理归一化
                            </button>
                          </div>
                        ) : null}
                      </div>
                    </article>
                  );
                })}
              </div>
            ) : (
              <div className="empty-state dossier-empty">当前案卷没有待处理问题，可以继续进行证据复核。</div>
            )}

            {importGovernance.staged_assertions && importGovernance.staged_assertions.length > 0 ? (
              <section className="proposal-section assertion-review-section">
                <div className="issue-queue-head">
                  <div>
                    <h3>候选断言</h3>
                    <p>逐条确认语义是否成立；拒绝的断言发布时会被排除。</p>
                  </div>
                  <span className="badge muted">{importGovernance.staged_assertions.length} 条</span>
                </div>
                <div className="verification-assertion-list">
                  {importGovernance.staged_assertions.map((bundle, index) => {
                    const assertion = bundle.assertion || {};
                    const reviewStatus = assertion.review_status || 'pending';
                    return (
                      <article key={assertion.assertion_id || index} className={`verification-assertion-card assertion-review-card ${reviewStatus}`}>
                        <div className="assertion-card-head">
                          <strong>{assertion.predicate_type || 'UNKNOWN_RELATION'}</strong>
                          <span className={`badge ${reviewStatus === 'rejected' ? 'danger' : reviewStatus === 'accepted' ? 'success' : 'muted'}`}>{reviewStatus}</span>
                        </div>
                        <p>{assertion.object_value || assertion.object_entity_id || assertion.subject_entity_id || '-'}</p>
                        {assertion.review_reason ? <small className="muted-line">理由：{assertion.review_reason}</small> : null}
                        {bundle.evidence_sources && bundle.evidence_sources.length > 0 ? (
                          <div className="verify-evidence-list compact-evidence">
                            {bundle.evidence_sources.slice(0, 2).map((evidence) => (
                              <blockquote key={evidence.evidence_id}>
                                <p>{evidence.source_text || '无证据正文'}</p>
                                <cite>{evidence.source_title || evidence.evidence_id}</cite>
                              </blockquote>
                            ))}
                          </div>
                        ) : null}
                        <div className="issue-actions">
                          <button className="secondary small" onClick={() => openAssertionReview(bundle)} disabled={assertionReviewLoading}>
                            审核断言
                          </button>
                        </div>
                      </article>
                    );
                  })}
                </div>
              </section>
            ) : null}

            {importGovernance.concept_proposals && importGovernance.concept_proposals.length > 0 ? (
              <section className="proposal-section">
                <div className="issue-queue-head">
                  <div>
                    <h3>概念提案</h3>
                    <p>提案通过后才会在发布时生成正式 Concept。</p>
                  </div>
                  <span className="badge muted">{importGovernance.concept_proposals.length} 项</span>
                </div>
                <div className="proposal-list">
                  {importGovernance.concept_proposals.map((proposal, index) => (
                    <article key={proposal.proposal_id || `${proposal.standard_name}-${index}`} className="proposal-card">
                      <div className="proposal-card-head">
                        <div>
                          <strong>{proposal.standard_name || proposal.surface_text || '未命名概念'}</strong>
                          <small>{proposal.concept_type || 'Concept'} · {proposal.status || 'pending_review'}</small>
                        </div>
                        {proposal.status === 'pending_review' ? (
                          <button className="secondary small" onClick={() => openConceptProposalReview(proposal)} disabled={proposalReviewLoading}>
                            审核提案
                          </button>
                        ) : null}
                      </div>
                      <p>{proposal.definition || '暂无定义'}</p>
                      <small>原文：{proposal.surface_text || '-'} · 证据 {proposal.evidence_ids?.length || 0} 条</small>
                    </article>
                  ))}
                </div>
              </section>
            ) : null}
          </>
        )}
      </section>

      {normalizationReviewIssue ? (
        <div className="review-drawer-backdrop" role="presentation" onClick={closeNormalizationReview}>
          <section className="review-drawer" role="dialog" aria-modal="true" aria-labelledby="normalization-review-title" onClick={(event) => event.stopPropagation()}>
            <div className="review-drawer-header">
              <div>
                <span className="section-kicker">Normalization review</span>
                <h2 id="normalization-review-title">处理术语归一</h2>
                <p>确认原文提及是否对应已有标准概念。这个操作只修改当前导入任务的候选决策，不会直接发布整版知识。</p>
              </div>
              <button className="ghost small" onClick={closeNormalizationReview} disabled={normalizationReviewLoading}>
                关闭
              </button>
            </div>

            <div className="review-mention-card">
              <span>原文提及</span>
              <strong>{normalizationReviewIssue.surface_text || normalizationReviewIssue.message || '未命名提及'}</strong>
              <small>{normalizationReviewIssue.status === 'ambiguous' ? '系统找到多个可能概念，请人工选择。' : '系统暂未找到可直接确认的标准概念。'}</small>
            </div>

            {normalizationReviewIssue.candidate_list && normalizationReviewIssue.candidate_list.length > 0 ? (
              <div className="candidate-list">
                <div className="review-field-label">候选概念</div>
                {normalizationReviewIssue.candidate_list.map((candidate, index) => {
                  const conceptId = typeof candidate.concept_id === 'string' ? candidate.concept_id : '';
                  const canonicalName = typeof candidate.canonical_name === 'string' ? candidate.canonical_name : conceptId;
                  const conceptType = typeof candidate.concept_type === 'string' ? candidate.concept_type : 'Concept';
                  return (
                    <label key={`${conceptId}-${index}`} className={`candidate-option ${selectedNormalizationConcept === conceptId ? 'selected' : ''}`}>
                      <input
                        type="radio"
                        name="normalization-concept"
                        value={conceptId}
                        checked={selectedNormalizationConcept === conceptId}
                        onChange={() => setSelectedNormalizationConcept(conceptId)}
                      />
                      <span>
                        <strong>{canonicalName}</strong>
                        <small>{conceptType} · {conceptId}</small>
                      </span>
                    </label>
                  );
                })}
              </div>
            ) : (
              <div className="review-empty-note">
                <p>当前没有可选择的候选概念。可以拒绝归一，或提交一个带定义和证据的 Concept Proposal。</p>
                <button className="secondary small" onClick={() => openConceptProposal(normalizationReviewIssue)} disabled={normalizationReviewLoading}>
                  创建概念提案
                </button>
              </div>
            )}

            <label className="review-reason-field">
              处理理由
              <textarea rows={4} value={normalizationReviewReason} onChange={(event) => setNormalizationReviewReason(event.target.value)} placeholder="说明为什么选择这个概念，或为什么拒绝归一。" />
            </label>

            {normalizationReviewIssue.candidate_list && normalizationReviewIssue.candidate_list.length > 0 ? (
              <label className="alias-check">
                <input type="checkbox" checked={createNormalizationAlias} onChange={(event) => setCreateNormalizationAlias(event.target.checked)} />
                将原文提及保存为该概念的 draft alias
              </label>
            ) : null}

            <div className="review-drawer-actions">
              <button className="danger" onClick={() => void submitNormalizationReview('rejected')} disabled={normalizationReviewLoading}>
                {normalizationReviewLoading ? '处理中...' : '拒绝归一'}
              </button>
              <button onClick={() => void submitNormalizationReview('resolved')} disabled={normalizationReviewLoading || !selectedNormalizationConcept || !(normalizationReviewIssue.candidate_list && normalizationReviewIssue.candidate_list.length > 0)}>
                确认归一
              </button>
            </div>
          </section>
        </div>
      ) : null}

      {assertionReviewTarget ? (
        <div className="review-drawer-backdrop" role="presentation" onClick={closeAssertionReview}>
          <section className="review-drawer" role="dialog" aria-modal="true" aria-labelledby="assertion-review-title" onClick={(event) => event.stopPropagation()}>
            <div className="review-drawer-header">
              <div>
                <span className="section-kicker">Assertion review</span>
                <h2 id="assertion-review-title">审核候选断言</h2>
                <p>确认这条关系是否由证据支持。拒绝后，它会保留在案卷中，但不会进入发布结果。</p>
              </div>
              <button className="ghost small" onClick={closeAssertionReview} disabled={assertionReviewLoading}>关闭</button>
            </div>

            <div className="proposal-review-summary">
              <span>{assertionReviewTarget.assertion?.predicate_type || 'UNKNOWN_RELATION'}</span>
              <strong>{assertionReviewTarget.assertion?.object_value || assertionReviewTarget.assertion?.object_entity_id || '-'}</strong>
              <p>{assertionReviewTarget.assertion?.assertion_id}</p>
            </div>

            {assertionReviewTarget.condition ? (
              <div className="condition-box drawer-condition-box">
                <span>条件</span>
                <code>{safeStringify(assertionReviewTarget.condition.logic || {})}</code>
              </div>
            ) : null}

            <div className="proposal-evidence-list readonly">
              {(assertionReviewTarget.evidence_sources || []).map((evidence, index) => (
                <article key={evidence.evidence_id || index} className="proposal-evidence-option">
                  <span><strong>{evidence.source_text || '无证据正文'}</strong><small>{evidence.source_title || evidence.evidence_id || 'unknown-evidence'}</small></span>
                </article>
              ))}
            </div>

            <label className="review-reason-field">
              审核理由
              <textarea rows={4} value={assertionReviewReason} onChange={(event) => setAssertionReviewReason(event.target.value)} placeholder="说明接受或拒绝该断言的理由。" />
            </label>

            <div className="review-drawer-actions">
              <button className="danger" onClick={() => void submitAssertionReview('rejected')} disabled={assertionReviewLoading}>
                {assertionReviewLoading ? '处理中...' : '拒绝断言'}
              </button>
              <button onClick={() => void submitAssertionReview('accepted')} disabled={assertionReviewLoading}>
                接受断言
              </button>
            </div>
          </section>
        </div>
      ) : null}

      {conceptProposalIssue ? (
        <div className="review-drawer-backdrop" role="presentation" onClick={closeConceptProposal}>
          <section className="review-drawer proposal-drawer" role="dialog" aria-modal="true" aria-labelledby="concept-proposal-title" onClick={(event) => event.stopPropagation()}>
            <div className="review-drawer-header">
              <div>
                <span className="section-kicker">Concept proposal</span>
                <h2 id="concept-proposal-title">提交新概念提案</h2>
                <p>提案会留在当前导入任务中，经过类型、定义和证据审核后，才会生成正式 Concept。</p>
              </div>
              <button className="ghost small" onClick={closeConceptProposal} disabled={conceptProposalLoading}>关闭</button>
            </div>

            <div className="review-mention-card">
              <span>待治理原文</span>
              <strong>{conceptProposalIssue.surface_text || '未命名提及'}</strong>
              <small>{conceptProposalIssue.message || '该提及当前没有匹配到已有概念。'}</small>
            </div>

            <div className="form-grid proposal-form-grid">
              <label>
                概念类型
                <select value={proposalConceptType} onChange={(event) => setProposalConceptType(event.target.value)}>
                  {conceptTypeOptions.map((type) => <option key={type} value={type}>{type}</option>)}
                </select>
              </label>
              <label>
                标准名称
                <input value={proposalStandardName} onChange={(event) => setProposalStandardName(event.target.value)} placeholder="例如：月光虚证" />
              </label>
            </div>

            <label className="review-reason-field">
              概念定义
              <textarea rows={5} value={proposalDefinition} onChange={(event) => setProposalDefinition(event.target.value)} placeholder="用一句或几句话说明这个概念的边界和含义。" />
            </label>

            <div className="proposal-evidence-field">
              <div className="review-field-label">来源证据（至少选择一条）</div>
              {conceptProposalIssue.evidence_sources && conceptProposalIssue.evidence_sources.length > 0 ? (
                <div className="proposal-evidence-list">
                  {conceptProposalIssue.evidence_sources.map((evidence, index) => {
                    const evidenceId = typeof evidence.evidence_id === 'string' ? evidence.evidence_id : '';
                    const sourceText = typeof evidence.source_text === 'string' ? evidence.source_text : '无证据正文';
                    return (
                      <label key={evidenceId || index} className={`proposal-evidence-option ${proposalEvidenceIds.includes(evidenceId) ? 'selected' : ''}`}>
                        <input type="checkbox" checked={proposalEvidenceIds.includes(evidenceId)} onChange={() => toggleProposalEvidence(evidenceId)} />
                        <span><strong>{sourceText}</strong><small>{evidenceId} · {typeof evidence.source_title === 'string' ? evidence.source_title : '来源文档'}</small></span>
                      </label>
                    );
                  })}
                </div>
              ) : (
                <div className="review-empty-note">当前案卷没有可供选择的证据，不能提交新概念提案。</div>
              )}
            </div>

            <label className="review-reason-field">
              来源说明
              <textarea rows={3} value={proposalSourceNote} onChange={(event) => setProposalSourceNote(event.target.value)} placeholder="补充来源章节、适用范围或其他审阅备注。" />
            </label>

            <div className="review-drawer-actions">
              <button className="ghost" onClick={closeConceptProposal} disabled={conceptProposalLoading}>取消</button>
              <button onClick={() => void submitConceptProposal()} disabled={conceptProposalLoading || !proposalStandardName.trim() || !proposalDefinition.trim() || proposalEvidenceIds.length === 0}>
                {conceptProposalLoading ? '提交中...' : '提交概念提案'}
              </button>
            </div>
          </section>
        </div>
      ) : null}

      {selectedConceptProposal ? (
        <div className="review-drawer-backdrop" role="presentation" onClick={closeConceptProposalReview}>
          <section className="review-drawer proposal-drawer" role="dialog" aria-modal="true" aria-labelledby="concept-proposal-review-title" onClick={(event) => event.stopPropagation()}>
            <div className="review-drawer-header">
              <div>
                <span className="section-kicker">Concept proposal review</span>
                <h2 id="concept-proposal-review-title">审核概念提案</h2>
                <p>请确认概念边界和来源证据。通过后，正式概念只会在本次知识版本发布时进入主存储。</p>
              </div>
              <button className="ghost small" onClick={closeConceptProposalReview} disabled={proposalReviewLoading}>关闭</button>
            </div>

            <div className="proposal-review-summary">
              <span>{selectedConceptProposal.concept_type || 'Concept'}</span>
              <strong>{selectedConceptProposal.standard_name || selectedConceptProposal.surface_text || '未命名概念'}</strong>
              <p>{selectedConceptProposal.definition || '暂无定义'}</p>
            </div>

            <div className="proposal-evidence-list readonly">
              {(selectedConceptProposal.evidence_sources || []).map((evidence, index) => (
                <article key={typeof evidence.evidence_id === 'string' ? evidence.evidence_id : index} className="proposal-evidence-option">
                  <span><strong>{typeof evidence.source_text === 'string' ? evidence.source_text : '无证据正文'}</strong><small>{typeof evidence.evidence_id === 'string' ? evidence.evidence_id : 'unknown-evidence'}</small></span>
                </article>
              ))}
            </div>

            <label className="review-reason-field">
              审核理由
              <textarea rows={4} value={proposalReviewReason} onChange={(event) => setProposalReviewReason(event.target.value)} placeholder="说明通过或拒绝该概念提案的理由。" />
            </label>

            <div className="review-drawer-actions">
              <button className="danger" onClick={() => void submitConceptProposalReview('rejected')} disabled={proposalReviewLoading}>
                {proposalReviewLoading ? '处理中...' : '拒绝提案'}
              </button>
              <button onClick={() => void submitConceptProposalReview('approved')} disabled={proposalReviewLoading}>
                通过并生成 Concept
              </button>
            </div>
          </section>
        </div>
      ) : null}

      <section className="panel panel-split">
        <article className="subpanel">
          <h3>提交说明</h3>
          <ul className="tips-list compact">
            <li>若已配置大模型，系统会优先走 LLM 抽取，再回退规则抽取。</li>
            <li>支持上传 txt / md / csv / docx 文件。</li>
            <li>响应结果中可看到材料、关系数量、抽取引擎与回退信息。</li>
          </ul>
        </article>
        <article className="subpanel">
          <h3>导入前检查</h3>
          <ul className="tips-list compact">
            <li>确认知识版本号符合团队命名规范。</li>
            <li>二进制文件会在浏览器内转为 base64 后提交。</li>
            <li>导入结果只是候选知识，建议完成证据复核后再进入发布流程。</li>
          </ul>
        </article>
      </section>
    </div>
  );

  const renderApiPage = () => (
    <div className="page-section stack-lg">
      <section className="panel">
        <div className="panel-header">
          <div>
            <h2>预置联调场景</h2>
            <p>将高频 API 抽象为卡片，减少手动输入路径的成本。</p>
          </div>
        </div>
        <div className="api-action-grid">
          {presetApiActions.map((action) => (
            <article key={action.label} className="api-card premium">
              <div className="api-card-head">
                <strong>{action.label}</strong>
                <span className={`method-tag ${action.method === 'GET' ? 'get' : 'post'}`}>{action.method}</span>
              </div>
              <code>{action.path}</code>
              <p>{action.description}</p>
              <button className="secondary" onClick={() => void runPresetAction(action.label, action.path, action.method, action.body)} disabled={loading || (action.requiresAuth && !authenticated)}>
                发起请求
              </button>
            </article>
          ))}
        </div>
      </section>

      <section className="panel">
        <div className="panel-header">
          <div>
            <h2>自定义请求</h2>
            <p>适合逐个验证前端实际调用的 API，或快速补充临时调试路径。</p>
          </div>
        </div>
        <div className="form-grid api-form-grid">
          <label>
            请求方法
            <select value={customMethod} onChange={(event) => setCustomMethod(event.target.value as HttpMethod)}>
              <option value="GET">GET</option>
              <option value="POST">POST</option>
            </select>
          </label>
          <label>
            接口路径
            <input value={customPath} onChange={(event) => setCustomPath(event.target.value)} placeholder="例如 /auth/me" />
          </label>
        </div>
        <label>
          JSON Body
          <textarea rows={10} value={customBody} onChange={(event) => setCustomBody(event.target.value)} placeholder="POST 请求时填写 JSON 请求体" className="code-input" />
        </label>
        <div className="button-row">
          <button onClick={() => void sendCustomRequest()} disabled={loading}>
            发送请求
          </button>
          <button className="secondary" onClick={() => setActivePage('results')}>
            查看执行与证据
          </button>
        </div>
      </section>
    </div>
  );

  const renderResultsPage = () => (
    <div className="page-section results-layout">
      <section className="panel result-list-panel">
        <div className="panel-header">
          <div>
            <h2>执行记录</h2>
            <p>展示最近的接口响应、错误信息与导入结果。</p>
          </div>
          <button className="ghost" onClick={() => setResultRecords([])} disabled={resultRecords.length === 0}>
            清空记录
          </button>
        </div>
        <div className="result-list">
          {resultRecords.length === 0 ? (
            <div className="empty-state">暂无结果记录，先去登录或发起一次接口请求吧。</div>
          ) : (
            resultRecords.map((item) => (
              <button key={item.id} className={`result-item ${selectedResultId === item.id ? 'active' : ''}`} onClick={() => setSelectedResultId(item.id)}>
                <div className="result-item-head">
                  <strong>{item.title}</strong>
                  <span className={`badge ${item.status === 'success' ? 'success' : 'danger'}`}>{item.status === 'success' ? '成功' : '失败'}</span>
                </div>
                <span className="result-item-time">{item.createdAt}</span>
              </button>
            ))
          )}
        </div>
      </section>

      <section className="panel result-detail-panel">
        <div className="panel-header">
          <div>
            <h2>结果详情</h2>
            <p>{latestResult ? `${latestResult.title} · ${latestResult.createdAt}` : '请选择左侧一条结果查看详情'}</p>
          </div>
        </div>

        {latestExplanationBundle.explanation ? (
          <section className="evidence-panel">
            <div className="evidence-panel-head">
              <h3>Explanation</h3>
              <span className="badge success">RAG</span>
            </div>
            <p className="explanation-text">{latestExplanationBundle.explanation}</p>
            {latestExplanationBundle.meta ? (
              <div className="explanation-meta">
                <span>llm_used: {String(latestExplanationBundle.meta.llm_used ?? '-')}</span>
                <span>evidence_count: {String(latestExplanationBundle.meta.evidence_count ?? '-')}</span>
                <span>prompt_version: {String(latestExplanationBundle.meta.prompt_version ?? '-')}</span>
              </div>
            ) : null}
            {latestExplanationBundle.evidence.length > 0 ? (
              <div className="citation-list">
                {latestExplanationBundle.evidence.map((item, index) => (
                  <article key={`${item.doc_id || item.asset_type || 'evidence'}-${index}`} className="citation-card">
                    <div className="citation-card-head">
                      <strong>{formatEvidenceLabel(item)}</strong>
                      <span className="badge muted">#{index + 1}</span>
                    </div>
                    <code>{item.doc_id || 'unknown-doc'}</code>
                    <p>{item.text || '无证据正文'}</p>
                    <div className="citation-card-actions">
                      <small>score: {typeof item.score === 'number' ? item.score.toFixed(4) : '-'}</small>
                      <button className="ghost small" onClick={() => setSelectedEvidence(item)}>
                        查看详情
                      </button>
                    </div>
                  </article>
                ))}
              </div>
            ) : null}
            {renderEvidenceDetail(selectedEvidence)}
          </section>
        ) : null}

        <pre className="result-pre">{latestResult ? safeStringify(latestResult.payload) : '等待接口响应...'}</pre>
      </section>
    </div>
  );

  const renderActivePage = () => {
    switch (activePage) {
      case 'login':
        return renderLoginPage();
      case 'verify':
        return renderVerificationPage();
      case 'guideline':
        return renderGuidelinePage();
      case 'api':
        return renderApiPage();
      case 'results':
        return renderResultsPage();
      case 'dashboard':
      default:
        return renderDashboardPage();
    }
  };

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-block">
          <p className="brand-kicker">QiHuang Shield</p>
          <h1>本体治理平台</h1>
          <p>面向概念、关系、证据与版本发布的中医知识工作台。</p>
        </div>

        <div className="sidebar-section">
          <span className="sidebar-section-title">导航</span>
          <nav className="nav-menu">
            {navigationItems.map((item) => (
              <button key={item.key} className={`nav-item ${activePage === item.key ? 'active' : ''}`} onClick={() => setActivePage(item.key)}>
                <strong>{item.label}</strong>
                <span>{item.description}</span>
              </button>
            ))}
          </nav>
        </div>

        <div className="sidebar-footer">
          <div className="status-card highlight">
            <span>当前登录状态</span>
            <strong>{authenticated ? userProfile?.display_name || '已登录' : '未登录'}</strong>
            <small>{authenticated ? userProfile?.email || email : '请先前往访问与权限页面'}</small>
          </div>
          <div className="status-card compact">
            <span>API Base URL</span>
            <code>{defaultApiBaseUrl}</code>
          </div>
          <div className="status-card compact">
            <span>最近执行</span>
            <small>{resultRecords[0]?.title || '暂无记录'}</small>
          </div>
        </div>
      </aside>

      <main className="content-area">
        <header className="topbar premium-topbar">
          <div>
            <h2>{navigationItems.find((item) => item.key === activePage)?.label}</h2>
            <p>{notice}</p>
          </div>
          <div className="topbar-actions">
            {authenticated ? (
              <button className="secondary" onClick={() => void fetchCurrentUser()} disabled={loading}>
                刷新用户
              </button>
            ) : null}
            <button className="ghost" onClick={() => setActivePage('results')}>
              执行与证据
            </button>
          </div>
        </header>

        {error ? <section className="alert error">{error}</section> : null}
        {!error && notice ? <section className="alert info">{notice}</section> : null}

        {renderActivePage()}
      </main>
    </div>
  );
}
