import { useState, useEffect, useCallback } from "react";
import {
  LineChart, Line, BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer
} from "recharts";
import {
  Shield, AlertTriangle, CheckCircle, XCircle, Activity,
  Search, Filter, Download, RefreshCw, LogOut, User,
  TrendingUp, DollarSign, Eye, ChevronDown, ChevronUp,
  Bell, Settings, Database, Cpu, FileText, Lock
} from "lucide-react";

// ─── API Client ───────────────────────────────────────────────
const API_BASE = "http://localhost:8000";

async function apiFetch(path, options = {}, token = null) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
  return res.json();
}

// ─── Risk badge ───────────────────────────────────────────────
const RiskBadge = ({ level }) => {
  const styles = {
    CRITICAL: "bg-red-100 text-red-800 border border-red-300",
    HIGH:     "bg-orange-100 text-orange-800 border border-orange-300",
    MEDIUM:   "bg-yellow-100 text-yellow-800 border border-yellow-300",
    LOW:      "bg-green-100 text-green-800 border border-green-300",
  };
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-bold uppercase ${styles[level] || styles.LOW}`}>
      {level}
    </span>
  );
};

const StatusBadge = ({ status }) => {
  const styles = {
    OPEN:             "bg-blue-100 text-blue-800",
    UNDER_REVIEW:     "bg-purple-100 text-purple-800",
    CONFIRMED_FRAUD:  "bg-red-100 text-red-800",
    FALSE_POSITIVE:   "bg-green-100 text-green-800",
    ESCALATED:        "bg-orange-100 text-orange-800",
  };
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-semibold ${styles[status] || "bg-gray-100 text-gray-800"}`}>
      {status?.replace("_", " ")}
    </span>
  );
};

// ─── Stat Card ────────────────────────────────────────────────
const StatCard = ({ label, value, sub, icon: Icon, color = "blue", trend }) => {
  const colors = {
    blue:   "bg-blue-50 text-blue-600",
    red:    "bg-red-50 text-red-600",
    green:  "bg-green-50 text-green-600",
    yellow: "bg-yellow-50 text-yellow-600",
    purple: "bg-purple-50 text-purple-600",
  };
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm text-gray-500 font-medium">{label}</p>
          <p className="text-2xl font-bold text-gray-900 mt-1">{value}</p>
          {sub && <p className="text-xs text-gray-400 mt-0.5">{sub}</p>}
          {trend !== undefined && (
            <p className={`text-xs mt-1 font-medium ${trend >= 0 ? "text-red-500" : "text-green-500"}`}>
              {trend >= 0 ? "▲" : "▼"} {Math.abs(trend)}% vs yesterday
            </p>
          )}
        </div>
        <div className={`p-2.5 rounded-lg ${colors[color]}`}>
          <Icon size={20} />
        </div>
      </div>
    </div>
  );
};

// ─── Login Screen ─────────────────────────────────────────────
function LoginScreen({ onLogin }) {
  const [username, setUsername] = useState("analyst1");
  const [password, setPassword] = useState("Analyst@2024!");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleLogin = async () => {
    setLoading(true); setError("");
    try {
      const data = await apiFetch("/auth/login", {
        method: "POST",
        body: JSON.stringify({ username, password }),
      });
      onLogin(data.access_token, data.user);
    } catch (e) {
      setError("Invalid credentials. Try analyst1 / Analyst@2024! or admin / Admin@GPS2024!");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-blue-950 to-slate-900 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-2xl p-8 w-full max-w-md">
        <div className="flex items-center gap-3 mb-8">
          <div className="p-3 bg-blue-600 rounded-xl">
            <Shield size={28} className="text-white" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-gray-900">Fraud Detection System</h1>
            <p className="text-sm text-gray-500">Zambia Mobile Money — CBU CS301 Group 20</p>
          </div>
        </div>

        {error && (
          <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">{error}</div>
        )}

        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Username</label>
            <input
              className="w-full border border-gray-300 rounded-lg px-3 py-2.5 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
              value={username} onChange={e => setUsername(e.target.value)}
              placeholder="analyst1 or admin"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Password</label>
            <input type="password"
              className="w-full border border-gray-300 rounded-lg px-3 py-2.5 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
              value={password} onChange={e => setPassword(e.target.value)}
              onKeyDown={e => e.key === "Enter" && handleLogin()}
              placeholder="Password"
            />
          </div>
          <button
            onClick={handleLogin} disabled={loading}
            className="w-full bg-blue-600 hover:bg-blue-700 text-white font-semibold py-2.5 rounded-lg transition disabled:opacity-60"
          >
            {loading ? "Signing in..." : "Sign In"}
          </button>
        </div>

        <div className="mt-6 p-3 bg-gray-50 rounded-lg text-xs text-gray-500">
          <p className="font-semibold mb-1">Demo Credentials:</p>
          <p>Analyst: <code>analyst1</code> / <code>Analyst@2024!</code></p>
          <p>Admin: <code>admin</code> / <code>Admin@GPS2024!</code></p>
        </div>
      </div>
    </div>
  );
}

// ─── Alert Detail Modal ───────────────────────────────────────
function AlertModal({ alert, token, onClose, onRefresh }) {
  const [overrideDecision, setOverrideDecision] = useState(null);
  const [fraudType, setFraudType] = useState("");
  const [note, setNote] = useState("");
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState("");

  const handleOverride = async () => {
    if (overrideDecision === null) return;
    setLoading(true);
    try {
      await apiFetch(`/alerts/${alert.alert_id}/override`, {
        method: "POST",
        body: JSON.stringify({ is_fraud: overrideDecision, fraud_type: fraudType || null, note }),
      }, token);
      setMsg(overrideDecision ? "✓ Confirmed as fraud and logged in audit trail." : "✓ Cleared as false positive.");
      setTimeout(() => { onRefresh(); onClose(); }, 1500);
    } catch (e) {
      setMsg("Error: " + e.message);
    } finally {
      setLoading(false);
    }
  };

  const rs = alert.risk;
  const txn = alert.transaction;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto"
           onClick={e => e.stopPropagation()}>
        <div className="p-6 border-b border-gray-100 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <AlertTriangle className="text-orange-500" size={22} />
            <h2 className="font-bold text-gray-900">Fraud Alert Review</h2>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">✕</button>
        </div>

        <div className="p-6 space-y-5">
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div className="bg-gray-50 rounded-lg p-3">
              <p className="text-gray-500 text-xs mb-1">Alert ID</p>
              <p className="font-mono text-xs font-semibold">{alert.alert_id?.slice(0, 16)}...</p>
            </div>
            <div className="bg-gray-50 rounded-lg p-3">
              <p className="text-gray-500 text-xs mb-1">Status</p>
              <StatusBadge status={alert.status} />
            </div>
            {txn && <>
              <div className="bg-gray-50 rounded-lg p-3">
                <p className="text-gray-500 text-xs mb-1">Amount</p>
                <p className="font-bold text-gray-900">ZMW {txn.amount?.toLocaleString()}</p>
              </div>
              <div className="bg-gray-50 rounded-lg p-3">
                <p className="text-gray-500 text-xs mb-1">Channel / Type</p>
                <p className="font-semibold">{txn.channel} · {txn.transaction_type}</p>
              </div>
              <div className="bg-gray-50 rounded-lg p-3 col-span-2">
                <p className="text-gray-500 text-xs mb-1">Transaction ID</p>
                <p className="font-mono text-xs">{txn.transaction_id}</p>
              </div>
            </>}
          </div>

          {rs && (
            <div className="border border-gray-200 rounded-xl p-4">
              <div className="flex items-center justify-between mb-3">
                <p className="font-semibold text-gray-800 text-sm">Risk Assessment</p>
                <RiskBadge level={rs.risk_level} />
              </div>
              <div className="flex items-center gap-4 mb-3">
                <div>
                  <p className="text-3xl font-black text-gray-900">{rs.risk_score}<span className="text-lg text-gray-400">/100</span></p>
                  <p className="text-xs text-gray-500">Risk Score</p>
                </div>
                <div>
                  <p className="text-3xl font-black text-gray-900">{(rs.fraud_probability * 100).toFixed(1)}%</p>
                  <p className="text-xs text-gray-500">Fraud Probability</p>
                </div>
                <div>
                  <p className={`text-lg font-bold ${rs.automated_action === "BLOCK" ? "text-red-600" : rs.automated_action === "REVIEW" ? "text-yellow-600" : "text-green-600"}`}>
                    {rs.automated_action}
                  </p>
                  <p className="text-xs text-gray-500">ML Recommendation</p>
                </div>
              </div>

              {rs.reason_codes?.length > 0 && (
                <div>
                  <p className="text-xs font-semibold text-gray-600 mb-2">Risk Indicators:</p>
                  <div className="flex flex-wrap gap-1.5">
                    {rs.reason_codes.map(code => (
                      <span key={code} className="bg-red-50 text-red-700 border border-red-200 text-xs px-2 py-0.5 rounded-full">
                        {code.replace(/_/g, " ")}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Override controls */}
          {alert.status === "OPEN" || alert.status === "UNDER_REVIEW" ? (
            <div className="border-2 border-blue-100 rounded-xl p-4 bg-blue-50">
              <p className="font-semibold text-gray-800 mb-3 text-sm">Analyst Decision</p>

              <div className="flex gap-3 mb-3">
                <button
                  onClick={() => setOverrideDecision(true)}
                  className={`flex-1 py-2 rounded-lg text-sm font-semibold border-2 transition ${
                    overrideDecision === true
                      ? "border-red-500 bg-red-500 text-white"
                      : "border-red-200 text-red-600 bg-white hover:bg-red-50"
                  }`}
                >
                  ✗ Confirm Fraud
                </button>
                <button
                  onClick={() => setOverrideDecision(false)}
                  className={`flex-1 py-2 rounded-lg text-sm font-semibold border-2 transition ${
                    overrideDecision === false
                      ? "border-green-500 bg-green-500 text-white"
                      : "border-green-200 text-green-600 bg-white hover:bg-green-50"
                  }`}
                >
                  ✓ Clear as Legitimate
                </button>
              </div>

              {overrideDecision === true && (
                <select
                  value={fraudType} onChange={e => setFraudType(e.target.value)}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm mb-2"
                >
                  <option value="">Select fraud type...</option>
                  <option value="SIM_SWAP">SIM Swap</option>
                  <option value="SMISHING">Smishing</option>
                  <option value="AGENT_FRAUD">Agent Fraud</option>
                  <option value="SOCIAL_ENGINEERING">Social Engineering</option>
                  <option value="ACCOUNT_TAKEOVER">Account Takeover</option>
                  <option value="UNKNOWN">Unknown</option>
                </select>
              )}

              <textarea
                value={note} onChange={e => setNote(e.target.value)}
                placeholder="Add analyst notes (optional)..."
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm resize-none"
                rows={2}
              />

              {msg && <p className="text-sm font-medium mt-2 text-blue-700">{msg}</p>}

              <button
                onClick={handleOverride}
                disabled={overrideDecision === null || loading}
                className="w-full mt-3 bg-blue-600 hover:bg-blue-700 text-white font-semibold py-2.5 rounded-lg transition disabled:opacity-50 text-sm"
              >
                {loading ? "Saving..." : "Submit Decision — Logged to Audit Trail"}
              </button>
            </div>
          ) : (
            <div className="bg-gray-50 rounded-xl p-4 text-sm text-gray-600">
              This alert has been resolved. Status: <StatusBadge status={alert.status} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── Alerts Tab ───────────────────────────────────────────────
function AlertsTab({ token }) {
  const [alerts, setAlerts] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState("");
  const [selectedAlert, setSelectedAlert] = useState(null);
  const [loading, setLoading] = useState(false);

  const loadAlerts = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ page, per_page: 15 });
      if (statusFilter) params.set("status", statusFilter);
      const data = await apiFetch(`/alerts?${params}`, {}, token);
      setAlerts(data.items || []);
      setTotal(data.total || 0);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, [token, page, statusFilter]);

  useEffect(() => { loadAlerts(); }, [loadAlerts]);

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-bold text-gray-900">Fraud Alerts ({total})</h2>
        <div className="flex gap-2">
          <select
            value={statusFilter} onChange={e => { setStatusFilter(e.target.value); setPage(1); }}
            className="border border-gray-300 rounded-lg px-3 py-2 text-sm"
          >
            <option value="">All Statuses</option>
            <option value="OPEN">Open</option>
            <option value="UNDER_REVIEW">Under Review</option>
            <option value="CONFIRMED_FRAUD">Confirmed Fraud</option>
            <option value="FALSE_POSITIVE">False Positive</option>
          </select>
          <button onClick={loadAlerts} className="p-2 border border-gray-300 rounded-lg hover:bg-gray-50">
            <RefreshCw size={16} />
          </button>
        </div>
      </div>

      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden shadow-sm">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b border-gray-200">
            <tr>
              {["Alert ID", "Status", "Amount (ZMW)", "Risk", "Type", "Time", "Action"].map(h => (
                <th key={h} className="px-4 py-3 text-left text-xs font-semibold text-gray-600 uppercase tracking-wide">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {loading ? (
              <tr><td colSpan={7} className="px-4 py-8 text-center text-gray-400">Loading...</td></tr>
            ) : alerts.length === 0 ? (
              <tr><td colSpan={7} className="px-4 py-8 text-center text-gray-400">No alerts found</td></tr>
            ) : alerts.map(alert => (
              <tr key={alert.alert_id} className="hover:bg-gray-50 cursor-pointer"
                  onClick={() => setSelectedAlert(alert)}>
                <td className="px-4 py-3 font-mono text-xs text-gray-600">{alert.alert_id?.slice(0, 8)}...</td>
                <td className="px-4 py-3"><StatusBadge status={alert.status} /></td>
                <td className="px-4 py-3 font-semibold">
                  {alert.transaction?.amount ? `ZMW ${alert.transaction.amount.toLocaleString()}` : "—"}
                </td>
                <td className="px-4 py-3">
                  {alert.risk ? <RiskBadge level={alert.risk.risk_level} /> : "—"}
                </td>
                <td className="px-4 py-3 text-gray-600">{alert.transaction?.transaction_type || "—"}</td>
                <td className="px-4 py-3 text-gray-500 text-xs">
                  {alert.created_at ? new Date(alert.created_at).toLocaleString() : "—"}
                </td>
                <td className="px-4 py-3">
                  <button className="text-blue-600 hover:text-blue-800 font-medium text-xs">Review →</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      <div className="flex items-center justify-between mt-3 text-sm text-gray-600">
        <span>Showing {((page-1)*15)+1}–{Math.min(page*15, total)} of {total}</span>
        <div className="flex gap-2">
          <button onClick={() => setPage(p => Math.max(1, p-1))} disabled={page === 1}
            className="px-3 py-1 border border-gray-300 rounded disabled:opacity-50 hover:bg-gray-50">← Prev</button>
          <button onClick={() => setPage(p => p+1)} disabled={page * 15 >= total}
            className="px-3 py-1 border border-gray-300 rounded disabled:opacity-50 hover:bg-gray-50">Next →</button>
        </div>
      </div>

      {selectedAlert && (
        <AlertModal alert={selectedAlert} token={token} onClose={() => setSelectedAlert(null)} onRefresh={loadAlerts} />
      )}
    </div>
  );
}

// ─── Dashboard Tab ────────────────────────────────────────────
function DashboardTab({ token }) {
  const [stats, setStats] = useState(null);
  const [trends, setTrends] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      try {
        const [s, t] = await Promise.all([
          apiFetch("/dashboard/stats", {}, token),
          apiFetch("/dashboard/risk-trends?days=14", {}, token),
        ]);
        setStats(s);
        setTrends(t);
      } catch (e) { console.error(e); }
      finally { setLoading(false); }
    };
    load();
  }, [token]);

  if (loading) return <div className="text-center py-12 text-gray-400">Loading dashboard...</div>;
  if (!stats) return <div className="text-center py-12 text-red-400">Failed to load — is the API server running?</div>;

  const donut = [
    { name: "Confirmed Fraud", value: stats.confirmed_fraud, color: "#ef4444" },
    { name: "False Positive", value: stats.false_positives, color: "#22c55e" },
    { name: "Open", value: stats.open_alerts, color: "#3b82f6" },
  ];

  return (
    <div className="space-y-6">
      {/* Stat cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Total Transactions" value={stats.total_transactions?.toLocaleString()} icon={Activity} color="blue" />
        <StatCard label="Open Alerts" value={stats.open_alerts} sub="Awaiting review" icon={Bell} color="red" />
        <StatCard label="Confirmed Fraud" value={stats.confirmed_fraud} sub="This period" icon={AlertTriangle} color="yellow" />
        <StatCard label="Fraud Amount (ZMW)" value={`K${(stats.fraud_amount_zmw/1000).toFixed(1)}K`} icon={DollarSign} color="purple" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <StatCard label="Detection Precision" value={`${(stats.precision * 100).toFixed(1)}%`} sub="Confirmed / (Confirmed + FP)" icon={TrendingUp} color="green" />
        <StatCard label="High Risk Transactions" value={stats.high_risk_transactions?.toLocaleString()} icon={Shield} color="red" />
        <StatCard label="Alerts Today" value={stats.alerts_today} icon={Activity} color="blue" />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
          <h3 className="font-semibold text-gray-800 mb-4">Alert Trend — Last 14 Days</h3>
          {trends.length > 0 ? (
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={trends}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip />
                <Legend />
                <Line type="monotone" dataKey="total" stroke="#3b82f6" strokeWidth={2} name="Total Alerts" dot={false} />
                <Line type="monotone" dataKey="confirmed" stroke="#ef4444" strokeWidth={2} name="Confirmed Fraud" dot={false} />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-56 flex items-center justify-center text-gray-400 text-sm">
              No trend data yet — score some transactions to populate
            </div>
          )}
        </div>

        <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
          <h3 className="font-semibold text-gray-800 mb-4">Alert Outcomes</h3>
          {donut.some(d => d.value > 0) ? (
            <ResponsiveContainer width="100%" height={180}>
              <PieChart>
                <Pie data={donut} cx="50%" cy="50%" innerRadius={50} outerRadius={80}
                     dataKey="value" label={({ name, value }) => `${value}`}>
                  {donut.map((entry, i) => <Cell key={i} fill={entry.color} />)}
                </Pie>
                <Tooltip />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-44 flex items-center justify-center text-gray-400 text-sm text-center">
              No alert data yet
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── Score Transaction Tab ────────────────────────────────────
function ScoreTab({ token }) {
  const [form, setForm] = useState({
    sender_msisdn: "+260961234567",
    receiver_msisdn: "+260977654321",
    amount: "5000",
    transaction_type: "P2P",
    operator: "MTN",
    channel: "USSD",
    province: "Lusaka",
    sms_text: "",
  });
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleScore = async () => {
    setLoading(true); setError(""); setResult(null);
    try {
      const payload = {
        ...form,
        amount: parseFloat(form.amount),
        transaction_id: crypto.randomUUID(),
      };
      const data = await apiFetch("/score", { method: "POST", body: JSON.stringify(payload) }, token);
      setResult(data);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const setFraudScenario = () => {
    setForm(f => ({
      ...f,
      amount: "45000",
      sms_text: "MTN: Your account will be suspended. Verify now: mtn-zm.net/verify",
    }));
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm">
        <div className="flex items-center justify-between mb-5">
          <h2 className="font-bold text-gray-900">Score Transaction</h2>
          <button onClick={setFraudScenario} className="text-xs text-red-600 hover:text-red-800 font-medium border border-red-200 px-2 py-1 rounded">
            🔴 Load Fraud Scenario
          </button>
        </div>

        <div className="grid grid-cols-2 gap-3">
          {[
            ["sender_msisdn", "Sender MSISDN", "text"],
            ["receiver_msisdn", "Receiver MSISDN", "text"],
            ["amount", "Amount (ZMW)", "number"],
          ].map(([key, label, type]) => (
            <div key={key} className="col-span-2">
              <label className="block text-xs font-medium text-gray-600 mb-1">{label}</label>
              <input type={type} value={form[key]} onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
            </div>
          ))}

          {[
            ["transaction_type", "Type", ["P2P", "P2B", "CASHOUT", "CASHIN", "BILLPAY", "INTL_TRANSFER"]],
            ["operator", "Operator", ["MTN", "AIRTEL", "ZAMTEL"]],
            ["channel", "Channel", ["USSD", "APP", "AGENT", "API"]],
            ["province", "Province", ["Lusaka", "Copperbelt", "Southern", "Eastern", "Northern", "Western"]],
          ].map(([key, label, options]) => (
            <div key={key}>
              <label className="block text-xs font-medium text-gray-600 mb-1">{label}</label>
              <select value={form[key]} onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500">
                {options.map(o => <option key={o}>{o}</option>)}
              </select>
            </div>
          ))}

          <div className="col-span-2">
            <label className="block text-xs font-medium text-gray-600 mb-1">SMS Text (optional — smishing detection)</label>
            <textarea value={form.sms_text} onChange={e => setForm(f => ({ ...f, sms_text: e.target.value }))}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-blue-500"
              rows={2} placeholder="Paste suspicious SMS for NLP analysis..." />
          </div>
        </div>

        {error && <div className="mt-3 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-xs">{error}</div>}

        <button onClick={handleScore} disabled={loading}
          className="w-full mt-4 bg-blue-600 hover:bg-blue-700 text-white font-semibold py-2.5 rounded-lg transition disabled:opacity-60">
          {loading ? "Scoring..." : "Score Transaction →"}
        </button>
      </div>

      {/* Result panel */}
      <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm">
        <h2 className="font-bold text-gray-900 mb-5">Scoring Result</h2>
        {!result ? (
          <div className="h-64 flex items-center justify-center text-gray-400 text-sm text-center">
            Submit a transaction to see the risk assessment
          </div>
        ) : (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-5xl font-black text-gray-900">
                  {result.risk_score}<span className="text-2xl text-gray-400">/100</span>
                </p>
                <p className="text-sm text-gray-500 mt-1">Composite Risk Score</p>
              </div>
              <div className="text-right">
                <RiskBadge level={result.risk_level} />
                <p className={`text-xl font-bold mt-2 ${result.automated_action === "BLOCK" ? "text-red-600" : result.automated_action === "REVIEW" ? "text-yellow-600" : "text-green-600"}`}>
                  {result.automated_action}
                </p>
                <p className="text-xs text-gray-500">ML Recommendation</p>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="bg-gray-50 rounded-lg p-3">
                <p className="text-xs text-gray-500">Fraud Probability</p>
                <p className="font-bold text-gray-900">{(result.fraud_probability * 100).toFixed(1)}%</p>
              </div>
              <div className="bg-gray-50 rounded-lg p-3">
                <p className="text-xs text-gray-500">Model Used</p>
                <p className="font-bold text-gray-900 text-xs">{result.model_used?.replace("_", " ")}</p>
              </div>
              <div className="bg-gray-50 rounded-lg p-3">
                <p className="text-xs text-gray-500">Processing Time</p>
                <p className="font-bold text-gray-900">{result.processing_time_ms}ms</p>
              </div>
              {result.alert_id && (
                <div className="bg-red-50 rounded-lg p-3">
                  <p className="text-xs text-red-500">Alert Generated</p>
                  <p className="font-bold text-red-700 text-xs">{result.alert_id?.slice(0, 12)}...</p>
                </div>
              )}
            </div>

            {result.reason_codes?.length > 0 && (
              <div>
                <p className="text-xs font-semibold text-gray-600 mb-2">Risk Indicators Triggered:</p>
                <div className="space-y-1.5">
                  {result.reason_messages?.map((msg, i) => (
                    <div key={i} className="flex items-start gap-2 text-xs">
                      <span className="text-red-500 mt-0.5">⚑</span>
                      <span className="text-gray-700">{msg}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {result.sub_scores && (
              <div>
                <p className="text-xs font-semibold text-gray-600 mb-2">Score Breakdown:</p>
                <div className="space-y-1">
                  {Object.entries(result.sub_scores).filter(([, v]) => v > 0).map(([k, v]) => (
                    <div key={k} className="flex items-center justify-between text-xs">
                      <span className="text-gray-600">{k.replace(/_/g, " ")}</span>
                      <span className="font-bold text-orange-600">+{v}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Models Tab ───────────────────────────────────────────────
function ModelsTab({ token, userRole }) {
  const [models, setModels] = useState([]);
  const [retraining, setRetraining] = useState(false);
  const [retrainResult, setRetrainResult] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiFetch("/models", {}, token).then(setModels).catch(console.error).finally(() => setLoading(false));
  }, [token]);

  const triggerRetrain = async () => {
    if (!confirm("Start model retraining? This may take a few minutes.")) return;
    setRetraining(true);
    try {
      const result = await apiFetch("/models/retrain", { method: "POST" }, token);
      setRetrainResult(result);
      const updated = await apiFetch("/models", {}, token);
      setModels(updated);
    } catch (e) {
      setRetrainResult({ error: e.message });
    } finally {
      setRetraining(false);
    }
  };

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-bold text-gray-900">ML Model Registry</h2>
        {userRole === "SYSTEM_ADMIN" && (
          <button onClick={triggerRetrain} disabled={retraining}
            className="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white font-semibold px-4 py-2 rounded-lg text-sm transition disabled:opacity-60">
            <Cpu size={16} />
            {retraining ? "Retraining..." : "Trigger Retraining"}
          </button>
        )}
      </div>

      {retrainResult && (
        <div className={`p-4 rounded-xl border ${retrainResult.error ? "border-red-200 bg-red-50" : "border-green-200 bg-green-50"}`}>
          {retrainResult.error ? (
            <p className="text-red-700 text-sm">Error: {retrainResult.error}</p>
          ) : (
            <div className="text-sm">
              <p className="font-semibold text-green-800 mb-1">✓ Retraining complete — v{retrainResult.version}</p>
              <p className="text-green-700">{retrainResult.training_samples?.toLocaleString()} samples, {retrainResult.fraud_samples} fraud cases</p>
            </div>
          )}
        </div>
      )}

      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden shadow-sm">
        {loading ? (
          <div className="p-8 text-center text-gray-400">Loading models...</div>
        ) : models.length === 0 ? (
          <div className="p-8 text-center">
            <Cpu className="mx-auto text-gray-300 mb-3" size={32} />
            <p className="text-gray-500 text-sm">No trained models yet.</p>
            {userRole === "SYSTEM_ADMIN" && (
              <button onClick={triggerRetrain} className="mt-3 text-blue-600 hover:text-blue-800 text-sm font-medium">
                Click "Trigger Retraining" to train models →
              </button>
            )}
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                {["Model", "Version", "Status", "Precision", "Recall", "F1", "AUC-ROC", "MCC", "Trained"].map(h => (
                  <th key={h} className="px-4 py-3 text-left text-xs font-semibold text-gray-600 uppercase">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {models.map(m => (
                <tr key={m.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-semibold text-gray-900">{m.model_name}</td>
                  <td className="px-4 py-3 font-mono text-xs text-gray-600">{m.version}</td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-0.5 rounded text-xs font-semibold ${m.is_active ? "bg-green-100 text-green-800" : "bg-gray-100 text-gray-600"}`}>
                      {m.is_active ? "Active" : "Retired"}
                    </span>
                  </td>
                  {["precision", "recall", "f1_score", "auc_roc", "mcc"].map(k => (
                    <td key={k} className="px-4 py-3 text-gray-700">
                      {m.metrics[k] != null ? (
                        <span className={m.metrics[k] >= 0.85 ? "text-green-700 font-semibold" : m.metrics[k] >= 0.7 ? "text-yellow-700" : "text-red-600"}>
                          {(m.metrics[k] * 100).toFixed(1)}%
                        </span>
                      ) : "—"}
                    </td>
                  ))}
                  <td className="px-4 py-3 text-xs text-gray-500">{new Date(m.trained_at).toLocaleDateString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 text-sm text-blue-800">
        <p className="font-semibold mb-1">Monthly Retraining Pipeline</p>
        <p>The system automatically retrains all models on the 1st of each month at 02:00 using analyst-confirmed fraud labels since the last run. Targets: Precision ≥ 85%, Recall ≥ 80%, AUC-ROC ≥ 0.90.</p>
      </div>
    </div>
  );
}

// ─── Compliance Tab ───────────────────────────────────────────
function ComplianceTab({ token }) {
  const today = new Date();
  const firstOfMonth = new Date(today.getFullYear(), today.getMonth(), 1);
  const [start, setStart] = useState(firstOfMonth.toISOString().slice(0, 10));
  const [end, setEnd] = useState(today.toISOString().slice(0, 10));
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);

  const generateReport = async () => {
    setLoading(true);
    try {
      const data = await apiFetch("/compliance/report", {
        method: "POST",
        body: JSON.stringify({ period_start: start + "T00:00:00", period_end: end + "T23:59:59" }),
      }, token);
      setReport(data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const downloadAuditLog = async () => {
    const url = `${API_BASE}/compliance/audit-log?start=${start}T00:00:00&end=${end}T23:59:59`;
    const res = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
    const blob = await res.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `audit_log_${start}_${end}.csv`;
    a.click();
  };

  return (
    <div className="space-y-5">
      <h2 className="text-lg font-bold text-gray-900">BoZ Compliance Reporting</h2>

      <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm">
        <div className="grid grid-cols-3 gap-4 mb-5">
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Period Start</label>
            <input type="date" value={start} onChange={e => setStart(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Period End</label>
            <input type="date" value={end} onChange={e => setEnd(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
          </div>
        </div>

        <div className="flex gap-3">
          <button onClick={generateReport} disabled={loading}
            className="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white font-semibold px-4 py-2.5 rounded-lg text-sm transition disabled:opacity-60">
            <FileText size={16} />
            {loading ? "Generating..." : "Generate BoZ Report"}
          </button>
          <button onClick={downloadAuditLog}
            className="flex items-center gap-2 border border-gray-300 hover:bg-gray-50 text-gray-700 font-semibold px-4 py-2.5 rounded-lg text-sm transition">
            <Download size={16} />
            Export Audit Log CSV
          </button>
        </div>
      </div>

      {report && (
        <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm">
          <div className="flex items-center gap-2 mb-4">
            <CheckCircle className="text-green-500" size={20} />
            <h3 className="font-bold text-gray-900">Report Generated</h3>
            <span className="text-xs text-gray-500 ml-2">ID: {report.report_id?.slice(0, 12)}...</span>
          </div>
          <p className="text-sm text-gray-600 mb-4">Period: {report.period}</p>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {[
              ["Total Transactions", report.summary?.total_transactions?.toLocaleString()],
              ["Flagged Alerts", report.summary?.total_flagged],
              ["Confirmed Fraud", report.summary?.confirmed_fraud],
              ["Fraud Amount", `ZMW ${report.summary?.fraud_amount_zmw?.toLocaleString()}`],
            ].map(([label, value]) => (
              <div key={label} className="bg-gray-50 rounded-lg p-3">
                <p className="text-xs text-gray-500">{label}</p>
                <p className="font-bold text-gray-900 text-lg">{value}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 text-sm text-amber-800">
        <p className="font-semibold mb-1">Bank of Zambia Compliance Requirements</p>
        <ul className="space-y-0.5 text-xs">
          <li>• All fraud decisions are logged with analyst ID, timestamp, and reason (National Payment Systems Directives)</li>
          <li>• PII (MSISDNs, device IDs) hashed before storage — Zambia Data Protection Act No. 3 of 2021</li>
          <li>• System complies with ZICTA cybersecurity guidelines on incident reporting</li>
          <li>• Monthly compliance reports submitted to BoZ via this portal</li>
        </ul>
      </div>
    </div>
  );
}

// ─── Main App ─────────────────────────────────────────────────
export default function FraudDashboard() {
  const [token, setToken] = useState(null);
  const [user, setUser] = useState(null);
  const [activeTab, setActiveTab] = useState("dashboard");

  const handleLogin = (t, u) => { setToken(t); setUser(u); };
  const handleLogout = () => { setToken(null); setUser(null); };

  if (!token) return <LoginScreen onLogin={handleLogin} />;

  const tabs = [
    { id: "dashboard", label: "Dashboard", icon: Activity },
    { id: "alerts", label: "Alerts", icon: Bell },
    { id: "score", label: "Score Transaction", icon: Shield },
    { id: "models", label: "ML Models", icon: Cpu },
    { id: "compliance", label: "Compliance", icon: FileText },
  ];

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-slate-900 text-white px-6 py-3 flex items-center justify-between shadow-lg">
        <div className="flex items-center gap-3">
          <Shield className="text-blue-400" size={22} />
          <div>
            <h1 className="font-bold text-sm">Zambia Fraud Detection System</h1>
            <p className="text-xs text-slate-400">CBU CS301 · Group 20 · MTN · Airtel · Zamtel</p>
          </div>
        </div>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 text-sm">
            <div className="w-2 h-2 bg-green-400 rounded-full animate-pulse" />
            <span className="text-slate-300">Live</span>
          </div>
          <div className="flex items-center gap-2 text-sm text-slate-300">
            <User size={14} />
            <span>{user?.username}</span>
            <span className="bg-blue-600 text-xs px-1.5 py-0.5 rounded">{user?.role}</span>
          </div>
          <button onClick={handleLogout} className="flex items-center gap-1 text-slate-400 hover:text-white text-sm">
            <LogOut size={14} /> Sign out
          </button>
        </div>
      </div>

      {/* Nav */}
      <div className="bg-white border-b border-gray-200 px-6">
        <div className="flex gap-1">
          {tabs.map(tab => {
            const Icon = tab.icon;
            return (
              <button key={tab.id} onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-2 px-4 py-3.5 text-sm font-medium border-b-2 transition ${
                  activeTab === tab.id
                    ? "border-blue-600 text-blue-600"
                    : "border-transparent text-gray-500 hover:text-gray-800"
                }`}>
                <Icon size={15} />
                {tab.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Content */}
      <div className="p-6">
        {activeTab === "dashboard"   && <DashboardTab token={token} />}
        {activeTab === "alerts"      && <AlertsTab token={token} />}
        {activeTab === "score"       && <ScoreTab token={token} />}
        {activeTab === "models"      && <ModelsTab token={token} userRole={user?.role} />}
        {activeTab === "compliance"  && <ComplianceTab token={token} />}
      </div>
    </div>
  );
}
