import { useMemo, useState } from 'react';

type JsonValue = Record<string, unknown> | Array<unknown> | string | number | boolean | null;

type LoginResponse = {
  data?: {
    access_token?: string;
    user?: {
      email?: string;
      display_name?: string;
    };
  };
};

const defaultApiBaseUrl = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api/v1';

async function requestJson(path: string, init?: RequestInit, token?: string): Promise<JsonValue> {
  const headers = new Headers(init?.headers || {});
  if (init?.body) {
    headers.set('Content-Type', 'application/json');
  }
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  const response = await fetch(`${defaultApiBaseUrl}${path}`, {
    ...init,
    headers,
  });

  const payload = (await response.json()) as JsonValue;
  if (!response.ok) {
    throw new Error(JSON.stringify(payload, null, 2));
  }
  return payload;
}

export default function App() {
  const [email, setEmail] = useState('admin@example.com');
  const [password, setPassword] = useState('password123');
  const [token, setToken] = useState('');
  const [result, setResult] = useState<JsonValue | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const authenticated = useMemo(() => token.trim().length > 0, [token]);

  const run = async (task: () => Promise<JsonValue>) => {
    setLoading(true);
    setError('');
    try {
      const data = await task();
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  const login = async () => {
    await run(async () => {
      const payload = (await requestJson('/auth/login', {
        method: 'POST',
        body: JSON.stringify({ email, password }),
      })) as LoginResponse;
      const nextToken = payload.data?.access_token || '';
      setToken(nextToken);
      return payload;
    });
  };

  return (
    <div className="page">
      <header className="hero">
        <div>
          <p className="eyebrow">QiHuang Shield</p>
          <h1>前后端分离项目骨架</h1>
          <p className="subtitle">
            该前端项目用于联调 FastAPI 审核服务，已预置登录、报表、规则、复核任务查询示例。
          </p>
        </div>
        <div className="endpoint-card">
          <span className="label">API Base URL</span>
          <code>{defaultApiBaseUrl}</code>
        </div>
      </header>

      <main className="layout">
        <section className="panel">
          <h2>登录</h2>
          <label>
            邮箱
            <input value={email} onChange={(event) => setEmail(event.target.value)} />
          </label>
          <label>
            密码
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </label>
          <button onClick={() => void login()} disabled={loading}>
            {loading ? '处理中...' : '调用 /auth/login'}
          </button>
          <label>
            Bearer Token
            <textarea
              rows={4}
              value={token}
              onChange={(event) => setToken(event.target.value)}
              placeholder="登录后自动填充，也可手动粘贴"
            />
          </label>
        </section>

        <section className="panel">
          <h2>联调快捷操作</h2>
          <div className="actions">
            <button disabled={loading} onClick={() => void run(() => requestJson('/auth/me', undefined, token))}>
              当前用户
            </button>
            <button
              disabled={loading}
              onClick={() => void run(() => requestJson('/review-tasks', undefined, token))}
            >
              复核任务列表
            </button>
            <button disabled={loading} onClick={() => void run(() => requestJson('/rules', undefined, token))}>
              规则列表
            </button>
            <button
              disabled={loading}
              onClick={() => void run(() => requestJson('/reports/overview', undefined, token))}
            >
              报表总览
            </button>
            <button
              disabled={loading}
              onClick={() =>
                void run(() =>
                  requestJson('/moderation/sync', {
                    method: 'POST',
                    body: JSON.stringify({
                      content_id: 'frontend-demo-001',
                      content_text: '附子泡茶能治结节吗',
                      content_type: 'note',
                      scenario: 'tea_drink',
                      tenant_id: 'tenant_demo',
                      policy_id: 'pol_default_cn',
                    }),
                  }),
                )
              }
            >
              同步审核 Demo
            </button>
          </div>
          {!authenticated && <p className="hint">除同步审核外，其余管理接口需要先登录获取 token。</p>}
        </section>
      </main>

      <section className="panel result-panel">
        <div className="result-header">
          <h2>结果面板</h2>
          {loading && <span className="status-pill">请求中</span>}
        </div>
        {error ? <pre className="error-box">{error}</pre> : null}
        <pre>{JSON.stringify(result, null, 2) || '等待调用接口...'}</pre>
      </section>
    </div>
  );
}
