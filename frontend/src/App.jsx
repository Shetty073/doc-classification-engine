import React, { useState, useEffect, useRef, useMemo } from 'react';
import {
  FileText,
  CheckCircle2,
  Clock,
  AlertCircle,
  XCircle,
  Search,
  Download,
  RefreshCw,
  Eye,
  Copy,
  Check,
  Upload,
  Layers,
  ShieldCheck,
  LogOut,
  ChevronRight,
  X,
  LayoutGrid,
  LayoutList,
  Filter,
  FileCheck,
  Building2,
  Server
} from 'lucide-react';

export default function App() {
  // Authentication State
  const [token, setToken] = useState(() => localStorage.getItem('doc_access_token') || '');
  const [user, setUser] = useState(() => localStorage.getItem('doc_username') || '');
  const [loginUsername, setLoginUsername] = useState('admin');
  const [loginPassword, setLoginPassword] = useState('admin_secure_pass123');
  const [authError, setAuthError] = useState('');
  const [authLoading, setAuthLoading] = useState(false);

  // Application Data State
  const [referenceId, setReferenceId] = useState('LOAN_APP_2026_MUM_001');
  const [inputReferenceId, setInputReferenceId] = useState('LOAN_APP_2026_MUM_001');
  const [statusSummary, setStatusSummary] = useState(null);
  const [completedDocs, setCompletedDocs] = useState([]);
  const [loadingDocs, setLoadingDocs] = useState(false);
  const [lastRefreshed, setLastRefreshed] = useState(new Date());

  // Upload & File Ingestion
  const [uploading, setUploading] = useState(false);
  const [uploadQueue, setUploadQueue] = useState([]);
  const [callbackUrl, setCallbackUrl] = useState('');
  const [showWebhookField, setShowWebhookField] = useState(false);
  const [dragActive, setDragActive] = useState(false);

  // Filters & Views
  const [searchTerm, setSearchTerm] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('ALL');
  const [statusFilter, setStatusFilter] = useState('ALL');
  const [viewMode, setViewMode] = useState('table'); // 'table' or 'grid'

  // Document Inspector Drawer
  const [inspectDoc, setInspectDoc] = useState(null);
  const [drawerTab, setDrawerTab] = useState('overview'); // 'overview', 'entities', 'quality', 'ocr'
  const [copiedKey, setCopiedKey] = useState('');

  // System Diagnostics
  const [systemHealth, setSystemHealth] = useState(null);

  const fileInputRef = useRef(null);

  // Check backend health
  useEffect(() => {
    const checkHealth = () => {
      fetch('/health')
        .then(res => res.json())
        .then(data => setSystemHealth(data))
        .catch(() => setSystemHealth({ status: 'offline' }));
    };
    checkHealth();
    const interval = setInterval(checkHealth, 30000);
    return () => clearInterval(interval);
  }, []);

  // Fetch documents for the active reference
  const fetchReferenceData = async (isBackground = false) => {
    if (!token || !referenceId) return;
    if (!isBackground) setLoadingDocs(true);

    try {
      const headers = { Authorization: `Bearer ${token}` };

      // 1. Overview status summary
      const statusRes = await fetch(`/documents/${referenceId}/status`, { headers });
      if (statusRes.ok) {
        const sData = await statusRes.json();
        setStatusSummary(sData);
      }

      // 2. Full documents listing
      const docsRes = await fetch(`/documents/${referenceId}`, { headers });
      if (docsRes.ok) {
        const cData = await docsRes.json();
        setCompletedDocs(cData);
      }
      setLastRefreshed(new Date());
    } catch (err) {
      console.error('Failed to fetch reference data:', err);
    } finally {
      if (!isBackground) setLoadingDocs(false);
    }
  };

  useEffect(() => {
    if (!token || !referenceId) return;
    fetchReferenceData();

    // Auto-polling for in-flight tasks
    const pollInterval = setInterval(() => {
      fetchReferenceData(true);
    }, 2500);

    return () => clearInterval(pollInterval);
  }, [token, referenceId]);

  // Auth Handler
  const handleLogin = async (e) => {
    if (e) e.preventDefault();
    setAuthLoading(true);
    setAuthError('');

    try {
      const formData = new URLSearchParams();
      formData.append('username', loginUsername);
      formData.append('password', loginPassword);

      const res = await fetch('/token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: formData,
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Authentication failed');
      }

      const data = await res.json();
      setToken(data.access_token);
      setUser(loginUsername);
      localStorage.setItem('doc_access_token', data.access_token);
      localStorage.setItem('doc_username', loginUsername);
    } catch (err) {
      setAuthError(err.message);
    } finally {
      setAuthLoading(false);
    }
  };

  const handleLogout = () => {
    setToken('');
    setUser('');
    localStorage.removeItem('doc_access_token');
    localStorage.removeItem('doc_username');
  };

  // Switch Reference
  const handleReferenceSubmit = (e) => {
    e.preventDefault();
    if (inputReferenceId.trim()) {
      setReferenceId(inputReferenceId.trim());
    }
  };

  // Upload Handlers
  const handleFiles = async (files) => {
    if (!files || files.length === 0) return;
    setUploading(true);

    const queueItems = Array.from(files).map(f => ({
      name: f.name,
      size: (f.size / 1024).toFixed(1) + ' KB',
      status: 'Uploading...'
    }));
    setUploadQueue(queueItems);

    try {
      const headers = { Authorization: `Bearer ${token}` };

      if (files.length === 1) {
        // Single file endpoint
        const formData = new FormData();
        formData.append('file', files[0]);
        formData.append('reference_id', referenceId);
        if (callbackUrl.trim()) formData.append('callback_url', callbackUrl.trim());

        const res = await fetch('/upload', {
          method: 'POST',
          headers,
          body: formData,
        });

        if (!res.ok) {
          const err = await res.json();
          throw new Error(err.detail || 'Upload failed');
        }
      } else {
        // Batch endpoint
        const formData = new FormData();
        Array.from(files).forEach(f => formData.append('files', f));
        formData.append('reference_id', referenceId);
        if (callbackUrl.trim()) formData.append('callback_url', callbackUrl.trim());

        const res = await fetch('/upload-batch', {
          method: 'POST',
          headers,
          body: formData,
        });

        if (!res.ok) {
          const err = await res.json();
          throw new Error(err.detail || 'Batch upload failed');
        }
      }

      // Refresh table immediately
      setTimeout(() => {
        fetchReferenceData();
        setUploadQueue([]);
      }, 1000);
    } catch (err) {
      alert(`Upload error: ${err.message}`);
    } finally {
      setUploading(false);
    }
  };

  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFiles(e.dataTransfer.files);
    }
  };

  const triggerDownload = (docId) => {
    const downloadUrl = `/documents/${docId}/download`;
    const link = document.createElement('a');
    link.href = downloadUrl;
    link.setAttribute('download', '');
    document.body.appendChild(link);
    link.click();
    link.remove();
  };

  const copyToClipboard = (text, key) => {
    navigator.clipboard.writeText(text);
    setCopiedKey(key);
    setTimeout(() => setCopiedKey(''), 2000);
  };

  // Filtered Documents
  const filteredDocs = useMemo(() => {
    return completedDocs.filter(doc => {
      const matchSearch =
        !searchTerm ||
        (doc.file_name && doc.file_name.toLowerCase().includes(searchTerm.toLowerCase())) ||
        (doc.file_path && doc.file_path.toLowerCase().includes(searchTerm.toLowerCase())) ||
        (doc.document_id && doc.document_id.toLowerCase().includes(searchTerm.toLowerCase())) ||
        (doc.category && doc.category.toLowerCase().includes(searchTerm.toLowerCase())) ||
        (doc.extracted_metadata && JSON.stringify(doc.extracted_metadata).toLowerCase().includes(searchTerm.toLowerCase()));

      const matchCategory =
        categoryFilter === 'ALL' ||
        doc.category === categoryFilter;

      const matchStatus =
        statusFilter === 'ALL' ||
        doc.status === statusFilter;

      return matchSearch && matchCategory && matchStatus;
    });
  }, [completedDocs, searchTerm, categoryFilter, statusFilter]);

  // Metrics Calculations
  const metrics = useMemo(() => {
    const total = completedDocs.length;
    const completed = completedDocs.filter(d => d.status === 'COMPLETED').length;
    const inProgress = completedDocs.filter(d => d.status === 'PENDING' || d.status === 'PROCESSING').length;
    const highConf = completedDocs.filter(d => (d.confidence_score || 0) >= 85).length;
    const autoRate = completed > 0 ? Math.round((highConf / completed) * 100) : 0;

    const scores = completedDocs.filter(d => d.quality_score != null).map(d => d.quality_score);
    const avgQuality = scores.length > 0 ? Math.round(scores.reduce((a, b) => a + b, 0) / scores.length) : 95;

    const issuesCount = completedDocs.reduce((acc, d) => {
      const issues = d.quality_issues || [];
      return acc + (issues.length > 0 ? 1 : 0);
    }, 0);

    return { total, completed, inProgress, autoRate, avgQuality, issuesCount };
  }, [completedDocs]);

  // Extract clean filename from doc or file_path
  const getCleanFilename = (item) => {
    if (!item) return 'document.pdf';
    if (typeof item === 'object') {
      if (item.file_name) return item.file_name;
      item = item.file_path || '';
    }
    const parts = String(item).replace(/\\/g, '/').split('/');
    const raw = parts[parts.length - 1];
    const clean = raw.replace(/^doc_[a-f0-9]{32}_/, '');
    return clean || raw || 'document.pdf';
  };

  // Available categories for filter dropdown
  const availableCategories = useMemo(() => {
    const set = new Set();
    completedDocs.forEach(d => {
      if (d.category) set.add(d.category);
    });
    return Array.from(set).sort();
  }, [completedDocs]);

  // If unauthenticated, show clean Enterprise Login
  if (!token) {
    return (
      <div className="login-container">
        <div className="login-card">
          <div className="login-header">
            <div className="login-logo">
              <Building2 size={24} />
            </div>
            <div>
              <h1 className="login-title">DocIntelligence Enterprise</h1>
              <p className="login-subtitle">RBI & Banking Document Classification Gateway</p>
            </div>
          </div>

          {authError && (
            <div style={{
              background: 'var(--danger-bg)',
              border: '1px solid var(--danger-border)',
              color: 'var(--danger-text)',
              padding: '0.65rem 0.85rem',
              borderRadius: 'var(--radius-sm)',
              fontSize: '0.8rem',
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem'
            }}>
              <AlertCircle size={16} />
              <span>{authError}</span>
            </div>
          )}

          <form onSubmit={handleLogin} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            <div className="form-group">
              <label className="form-label">Username</label>
              <input
                type="text"
                className="form-input"
                value={loginUsername}
                onChange={e => setLoginUsername(e.target.value)}
                placeholder="Enter authorized username"
                required
              />
            </div>

            <div className="form-group">
              <label className="form-label">Password</label>
              <input
                type="password"
                className="form-input"
                value={loginPassword}
                onChange={e => setLoginPassword(e.target.value)}
                placeholder="Enter password"
                required
              />
            </div>

            <button
              type="submit"
              className="btn btn-primary"
              disabled={authLoading}
              style={{ marginTop: '0.5rem', padding: '0.65rem' }}
            >
              {authLoading ? 'Verifying Credentials...' : 'Sign In to Banking Workspace'}
            </button>
          </form>

          <div className="login-compliance-badge">
            <ShieldCheck size={16} style={{ color: 'var(--success)' }} />
            <span>OAuth2 JWT Enclave • RBI KYC / PMLA Master Direction</span>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="app-container">
      {/* 1. Enterprise Top Navigation Bar */}
      <header className="enterprise-header">
        <div className="header-left">
          <div className="brand-badge">
            <div className="brand-icon-box">
              <Building2 size={18} />
            </div>
            <div className="brand-title-wrap">
              <span className="brand-name">DocClassify Gateway</span>
              <span className="brand-tag">Banking Intelligence • Enterprise v2.4</span>
            </div>
          </div>

          <div className="header-divider" />

          <div className="system-status-indicator">
            <span className={`status-dot ${systemHealth?.status === 'ok' ? '' : 'offline'}`} />
            <span>Service Node: {systemHealth?.status === 'ok' ? 'Online' : 'Degraded'}</span>
          </div>
        </div>

        <div className="header-right">
          <div className="tenant-pill">
            <Server size={13} />
            <span>REGION: AP-SOUTH-1</span>
          </div>

          <div className="user-profile-menu">
            <div className="user-avatar-pill">
              <div className="avatar-circle">
                {user.charAt(0).toUpperCase()}
              </div>
              <span>{user}</span>
            </div>

            <button
              onClick={handleLogout}
              className="btn-icon"
              title="Sign Out"
              aria-label="Sign Out"
            >
              <LogOut size={15} />
            </button>
          </div>
        </div>
      </header>

      {/* 2. Main Content Body */}
      <main className="main-wrapper">
        {/* KPI Summary Tiles */}
        <section className="metrics-row">
          <div className="metric-card">
            <div className="metric-label-row">
              <span>Total Documents</span>
              <Layers size={15} style={{ color: 'var(--primary)' }} />
            </div>
            <div className="metric-value-row">
              <span className="metric-value">{metrics.total}</span>
              <span className="metric-subtext">files in dossier</span>
            </div>
          </div>

          <div className="metric-card">
            <div className="metric-label-row">
              <span>In Processing</span>
              <Clock size={15} style={{ color: metrics.inProgress > 0 ? '#38bdf8' : 'var(--text-muted)' }} />
            </div>
            <div className="metric-value-row">
              <span className="metric-value" style={{ color: metrics.inProgress > 0 ? '#38bdf8' : 'inherit' }}>
                {metrics.inProgress}
              </span>
              <span className="metric-subtext">{metrics.inProgress > 0 ? 'analyzing pipeline' : 'all jobs finished'}</span>
            </div>
          </div>

          <div className="metric-card">
            <div className="metric-label-row">
              <span>Auto-Classification</span>
              <CheckCircle2 size={15} style={{ color: 'var(--success)' }} />
            </div>
            <div className="metric-value-row">
              <span className="metric-value">{metrics.autoRate}%</span>
              <span className="metric-subtext">{metrics.completed} classified</span>
            </div>
          </div>

          <div className="metric-card">
            <div className="metric-label-row">
              <span>Avg Quality Score</span>
              <FileCheck size={15} style={{ color: 'var(--info)' }} />
            </div>
            <div className="metric-value-row">
              <span className="metric-value">{metrics.avgQuality}</span>
              <span className="metric-subtext">/100 OCR clarity</span>
            </div>
          </div>
        </section>

        {/* Reference / Portfolio Workspace Switcher */}
        <section className="control-bar">
          <form onSubmit={handleReferenceSubmit} className="control-bar-left">
            <div className="ref-input-group">
              <span className="ref-label">PORTFOLIO REF:</span>
              <input
                type="text"
                className="ref-input"
                value={inputReferenceId}
                onChange={e => setInputReferenceId(e.target.value)}
                placeholder="e.g. LOAN_APP_2026_MUM_001"
              />
            </div>
            <button type="submit" className="btn btn-secondary">
              Load Dossier
            </button>
          </form>

          <div className="control-bar-right">
            <button
              onClick={() => fetchReferenceData()}
              className="btn btn-secondary"
              disabled={loadingDocs}
              title="Refresh Dossier Data"
            >
              <RefreshCw size={14} className={loadingDocs ? 'spin' : ''} />
              <span>{loadingDocs ? 'Refreshing...' : 'Refresh'}</span>
            </button>
          </div>
        </section>

        {/* Ingestion & Upload Section */}
        <section className="ingestion-panel">
          <div className="panel-header">
            <div>
              <h2 className="panel-title">
                <Upload size={16} />
                <span>Document Ingestion Gateway</span>
              </h2>
              <p className="panel-subtitle">Upload borrower verification documents, tax forms, or company registrations.</p>
            </div>
            <button
              type="button"
              className="btn btn-ghost"
              style={{ fontSize: '0.75rem' }}
              onClick={() => setShowWebhookField(!showWebhookField)}
            >
              {showWebhookField ? 'Hide Webhook Config' : 'Configure Webhook Callback'}
            </button>
          </div>

          {showWebhookField && (
            <div className="webhook-row">
              <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>Webhook URL:</span>
              <input
                type="url"
                className="webhook-input"
                placeholder="https://your-bank-core.internal/api/v1/callbacks/documents"
                value={callbackUrl}
                onChange={e => setCallbackUrl(e.target.value)}
              />
            </div>
          )}

          <div
            className={`dropzone ${dragActive ? 'active' : ''}`}
            onDragEnter={handleDrag}
            onDragLeave={handleDrag}
            onDragOver={handleDrag}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current && fileInputRef.current.click()}
          >
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept=".pdf,.png,.jpg,.jpeg,.tiff"
              style={{ display: 'none' }}
              onChange={e => {
                if (e.target.files && e.target.files.length > 0) {
                  handleFiles(e.target.files);
                }
                e.target.value = '';
              }}
            />
            <div>
              <p className="dropzone-text-primary">Click to select documents or drag & drop files here</p>
              <p className="dropzone-text-secondary">Direct support for PDF, PNG, JPG, and multi-page corporate filings</p>
            </div>
            <div className="dropzone-badges">
              <span className="drop-badge">PDF</span>
              <span className="drop-badge">PNG</span>
              <span className="drop-badge">JPG</span>
              <span className="drop-badge">MAX 50MB</span>
            </div>
          </div>

          {uploading && (
            <div className="upload-queue-card">
              <div className="upload-info">
                <RefreshCw size={16} className="spin" style={{ color: 'var(--primary)' }} />
                <span>Ingesting documents into classification pipeline...</span>
              </div>
              <span style={{ fontSize: '0.75rem', fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>
                {uploadQueue.length} files queued
              </span>
            </div>
          )}
        </section>

        {/* Document Explorer / Table View */}
        <section className="documents-section">
          {/* Table Toolbar */}
          <div className="table-toolbar">
            <div className="toolbar-filters">
              <div className="search-input-wrap">
                <Search size={14} style={{ color: 'var(--text-muted)' }} />
                <input
                  type="text"
                  className="search-input"
                  placeholder="Filter by name, ID, PAN, GSTIN..."
                  value={searchTerm}
                  onChange={e => setSearchTerm(e.target.value)}
                />
                {searchTerm && (
                  <button
                    onClick={() => setSearchTerm('')}
                    style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}
                  >
                    <X size={13} />
                  </button>
                )}
              </div>

              <select
                className="filter-select"
                value={categoryFilter}
                onChange={e => setCategoryFilter(e.target.value)}
              >
                <option value="ALL">All Categories</option>
                {availableCategories.map(cat => (
                  <option key={cat} value={cat}>{cat}</option>
                ))}
              </select>

              <select
                className="filter-select"
                value={statusFilter}
                onChange={e => setStatusFilter(e.target.value)}
              >
                <option value="ALL">All Statuses</option>
                <option value="COMPLETED">Completed</option>
                <option value="PROCESSING">Processing</option>
                <option value="FAILED">Failed</option>
              </select>
            </div>

            <div className="toolbar-actions">
              <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginRight: '0.5rem' }}>
                Showing {filteredDocs.length} of {completedDocs.length}
              </span>

              <div className="view-toggle-group">
                <button
                  className={`view-toggle-btn ${viewMode === 'table' ? 'active' : ''}`}
                  onClick={() => setViewMode('table')}
                  title="Table View"
                >
                  <LayoutList size={15} />
                </button>
                <button
                  className={`view-toggle-btn ${viewMode === 'grid' ? 'active' : ''}`}
                  onClick={() => setViewMode('grid')}
                  title="Grid View"
                >
                  <LayoutGrid size={15} />
                </button>
              </div>
            </div>
          </div>

          {/* Empty State */}
          {filteredDocs.length === 0 ? (
            <div className="empty-table-state">
              <div className="empty-icon-wrap">
                <FileText size={24} />
              </div>
              <h3 style={{ fontSize: '0.95rem', color: 'var(--text-primary)', fontWeight: 600 }}>No documents found</h3>
              <p style={{ fontSize: '0.8rem', maxWidth: '380px' }}>
                {completedDocs.length === 0
                  ? `No documents have been uploaded for reference '${referenceId}' yet. Use the upload zone above to ingest files.`
                  : 'No documents match your active search or category filters.'}
              </p>
            </div>
          ) : viewMode === 'table' ? (
            /* Standard Enterprise Table View */
            <div className="table-responsive">
              <table className="enterprise-table">
                <thead>
                  <tr>
                    <th>Document</th>
                    <th>Classification</th>
                    <th>Confidence</th>
                    <th>Quality</th>
                    <th>Extracted Entities</th>
                    <th>Ingested</th>
                    <th>Status</th>
                    <th style={{ textAlign: 'right' }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredDocs.map(doc => {
                    const filename = getCleanFilename(doc);
                    const isCompleted = doc.status === 'COMPLETED';
                    const isProcessing = doc.status === 'PROCESSING' || doc.status === 'PENDING';
                    const isFailed = doc.status === 'FAILED';
                    const score = doc.confidence_score || 0;

                    let confClass = 'low';
                    if (score >= 85) confClass = 'high';
                    else if (score >= 60) confClass = 'med';

                    const qScore = doc.quality_score ?? 95;
                    let qDotClass = 'pass';
                    if (qScore < 60) qDotClass = 'fail';
                    else if (qScore < 85) qDotClass = 'warning';

                    const entities = doc.extracted_metadata || {};
                    const entityKeys = Object.keys(entities).filter(k => entities[k] && typeof entities[k] === 'string');

                    return (
                      <tr
                        key={doc.document_id}
                        className="table-row"
                        onClick={() => {
                          setInspectDoc(doc);
                          setDrawerTab('overview');
                        }}
                      >
                        <td>
                          <div className="doc-cell">
                            <div className="doc-file-icon">
                              <FileText size={16} />
                            </div>
                            <div className="doc-info">
                              <span className="doc-name" title={filename}>{filename}</span>
                              <span className="doc-id-sub">{doc.document_id}</span>
                            </div>
                          </div>
                        </td>

                        <td>
                          {doc.category ? (
                            <div>
                              <span className={`category-pill ${doc.category === 'UNKNOWN' ? 'unknown' : ''}`}>
                                {doc.category}
                              </span>
                              {doc.guess && (
                                <div className="category-subtext">Guess: {doc.guess}</div>
                              )}
                            </div>
                          ) : isProcessing ? (
                            <span className="status-pill processing" style={{ fontSize: '0.72rem' }}>
                              <RefreshCw size={11} className="spin" style={{ marginRight: '4px' }} />
                              <span>Analyzing OCR...</span>
                            </span>
                          ) : isFailed ? (
                            <span className="status-pill failed" style={{ fontSize: '0.72rem' }}>
                              <span>Failed</span>
                            </span>
                          ) : (
                            <span style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>Queued...</span>
                          )}
                        </td>

                        <td>
                          {score > 0 ? (
                            <div className="confidence-cell">
                              <div className="confidence-header">
                                <span>{score}%</span>
                              </div>
                              <div className="progress-bar-bg">
                                <div
                                  className={`progress-bar-fill ${confClass}`}
                                  style={{ width: `${score}%` }}
                                />
                              </div>
                            </div>
                          ) : isProcessing ? (
                            <span style={{ color: '#60a5fa', fontSize: '0.72rem', fontStyle: 'italic' }}>Evaluating...</span>
                          ) : (
                            <span style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>—</span>
                          )}
                        </td>

                        <td>
                          {doc.quality_score != null ? (
                            <div className="quality-pill">
                              <span className={`quality-dot ${qDotClass}`} />
                              <span>{qScore}/100</span>
                            </div>
                          ) : isProcessing ? (
                            <span style={{ color: 'var(--text-muted)', fontSize: '0.72rem' }}>Scanning...</span>
                          ) : (
                            <span style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>—</span>
                          )}
                        </td>

                        <td>
                          <div className="entities-wrap">
                            {entityKeys.length > 0 ? (
                              entityKeys.slice(0, 2).map(k => (
                                <span key={k} className="entity-tag">
                                  <strong>{k.replace('_', ' ')}:</strong> {entities[k]}
                                </span>
                              ))
                            ) : isProcessing ? (
                              <span style={{ color: 'var(--text-muted)', fontSize: '0.72rem' }}>Extracting...</span>
                            ) : (
                              <span style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>—</span>
                            )}
                            {entityKeys.length > 2 && (
                              <span className="entity-tag">+{entityKeys.length - 2} more</span>
                            )}
                          </div>
                        </td>

                        <td style={{ color: 'var(--text-secondary)', fontSize: '0.75rem', whiteSpace: 'nowrap' }}>
                          {doc.created_at ? new Date(doc.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '—'}
                        </td>

                        <td>
                          <span className={`status-pill ${doc.status ? doc.status.toLowerCase() : 'pending'}`}>
                            {isProcessing && <RefreshCw size={10} className="spin" style={{ marginRight: '3px' }} />}
                            {doc.status}
                          </span>
                        </td>

                        <td>
                          <div
                            className="action-btn-group"
                            style={{ justifyContent: 'flex-end' }}
                            onClick={e => e.stopPropagation()}
                          >
                            <button
                              className="btn-icon"
                              onClick={() => triggerDownload(doc.document_id)}
                              title="Download File"
                            >
                              <Download size={14} />
                            </button>
                            <button
                              className="btn-icon"
                              onClick={() => {
                                setInspectDoc(doc);
                                setDrawerTab('overview');
                              }}
                              title="Inspect Details"
                            >
                              <ChevronRight size={14} />
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            /* Alternative Card Grid View */
            <div className="documents-grid">
              {filteredDocs.map(doc => {
                const filename = getCleanFilename(doc);
                const score = doc.confidence_score || 0;
                const entities = doc.extracted_metadata || {};
                const entityKeys = Object.keys(entities).filter(k => entities[k] && typeof entities[k] === 'string');

                return (
                  <div
                    key={doc.document_id}
                    className="doc-card"
                    onClick={() => {
                      setInspectDoc(doc);
                      setDrawerTab('overview');
                    }}
                  >
                    <div className="doc-card-header">
                      <div className="doc-cell" style={{ minWidth: 'auto' }}>
                        <div className="doc-file-icon">
                          <FileText size={16} />
                        </div>
                        <div className="doc-info">
                          <span className="doc-name">{filename}</span>
                          <span className="doc-id-sub">{doc.document_id}</span>
                        </div>
                      </div>
                      <span className={`status-pill ${doc.status ? doc.status.toLowerCase() : 'pending'}`}>
                        {doc.status}
                      </span>
                    </div>

                    <div>
                      {doc.category ? (
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                          <span className={`category-pill ${doc.category === 'UNKNOWN' ? 'unknown' : ''}`}>
                            {doc.category}
                          </span>
                          <span style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--text-secondary)' }}>
                            {score}% conf
                          </span>
                        </div>
                      ) : (
                        <span style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>Processing...</span>
                      )}
                    </div>

                    <div className="entities-wrap">
                      {entityKeys.map(k => (
                        <span key={k} className="entity-tag">
                          <strong>{k.replace('_', ' ')}:</strong> {entities[k]}
                        </span>
                      ))}
                    </div>

                    <div className="doc-card-footer">
                      <span>Quality: {doc.quality_score ?? 95}/100</span>
                      <div onClick={e => e.stopPropagation()}>
                        <button
                          className="btn btn-secondary"
                          style={{ padding: '0.25rem 0.5rem', fontSize: '0.72rem' }}
                          onClick={() => triggerDownload(doc.document_id)}
                        >
                          <Download size={12} />
                          <span>Download</span>
                        </button>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </section>
      </main>

      {/* 3. Slide-out Document Inspector Drawer */}
      {inspectDoc && (
        <div className="drawer-backdrop" onClick={() => setInspectDoc(null)}>
          <div className="drawer-panel" onClick={e => e.stopPropagation()}>
            {/* Drawer Header */}
            <div className="drawer-header">
              <div className="drawer-title-group">
                <h3 className="drawer-title">{getCleanFilename(inspectDoc)}</h3>
                <span className="drawer-subtitle">DOC_ID: {inspectDoc.document_id}</span>
              </div>
              <button
                className="btn-icon"
                onClick={() => setInspectDoc(null)}
                aria-label="Close Inspector"
              >
                <X size={16} />
              </button>
            </div>

            {/* Drawer Tabs */}
            <div className="drawer-tabs">
              <button
                className={`drawer-tab ${drawerTab === 'overview' ? 'active' : ''}`}
                onClick={() => setDrawerTab('overview')}
              >
                Classification
              </button>
              <button
                className={`drawer-tab ${drawerTab === 'entities' ? 'active' : ''}`}
                onClick={() => setDrawerTab('entities')}
              >
                Extracted Entities
              </button>
              <button
                className={`drawer-tab ${drawerTab === 'quality' ? 'active' : ''}`}
                onClick={() => setDrawerTab('quality')}
              >
                Quality Audit
              </button>
              <button
                className={`drawer-tab ${drawerTab === 'ocr' ? 'active' : ''}`}
                onClick={() => setDrawerTab('ocr')}
              >
                Raw OCR
              </button>
            </div>

            {/* Drawer Body */}
            <div className="drawer-body">
              {drawerTab === 'overview' && (
                <>
                  <div className="drawer-section">
                    <span className="drawer-section-title">Classification Summary</span>
                    <div className="details-grid">
                      <span className="details-key">Category:</span>
                      <span className="details-val" style={{ color: '#93c5fd', fontWeight: 600 }}>
                        {inspectDoc.category || 'PENDING'}
                      </span>

                      <span className="details-key">Confidence:</span>
                      <span className="details-val">
                        {inspectDoc.confidence_score ? `${inspectDoc.confidence_score}/100` : '—'}
                      </span>

                      {inspectDoc.guess && (
                        <>
                          <span className="details-key">Hypothesis / Guess:</span>
                          <span className="details-val" style={{ color: 'var(--warning-text)' }}>
                            {inspectDoc.guess}
                          </span>
                        </>
                      )}

                      <span className="details-key">Status:</span>
                      <span className="details-val">{inspectDoc.status}</span>

                      <span className="details-key">Reference Dossier:</span>
                      <span className="details-val">{inspectDoc.reference_id}</span>

                      <span className="details-key">Storage Path:</span>
                      <span className="details-val" style={{ fontSize: '0.7rem' }}>{inspectDoc.file_path}</span>
                    </div>
                  </div>

                  {inspectDoc.error_message && (
                    <div className="drawer-section">
                      <span className="drawer-section-title" style={{ color: 'var(--danger-text)' }}>Pipeline Error</span>
                      <div style={{
                        background: 'var(--danger-bg)',
                        border: '1px solid var(--danger-border)',
                        color: 'var(--danger-text)',
                        padding: '0.75rem',
                        borderRadius: 'var(--radius-sm)',
                        fontSize: '0.75rem',
                        fontFamily: 'var(--font-mono)'
                      }}>
                        {inspectDoc.error_message}
                      </div>
                    </div>
                  )}
                </>
              )}

              {drawerTab === 'entities' && (
                <div className="drawer-section">
                  <span className="drawer-section-title">Structured Extracted Fields</span>
                  {inspectDoc.extracted_metadata && Object.keys(inspectDoc.extracted_metadata).length > 0 ? (
                    <div className="details-grid">
                      {Object.entries(inspectDoc.extracted_metadata).map(([k, v]) => (
                        <React.Fragment key={k}>
                          <span className="details-key">{k.replace(/_/g, ' ').toUpperCase()}:</span>
                          <span className="details-val">
                            {typeof v === 'object' ? JSON.stringify(v) : String(v)}
                          </span>
                        </React.Fragment>
                      ))}
                    </div>
                  ) : (
                    <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                      No specific structured entities extracted for this category.
                    </p>
                  )}
                </div>
              )}

              {drawerTab === 'quality' && (
                <div className="drawer-section">
                  <span className="drawer-section-title">Document Image Quality Diagnostics</span>
                  <div className="details-grid">
                    <span className="details-key">Quality Score:</span>
                    <span className="details-val" style={{ fontWeight: 600, color: (inspectDoc.quality_score ?? 95) >= 80 ? 'var(--success-text)' : 'var(--warning-text)' }}>
                      {inspectDoc.quality_score ?? 95} / 100
                    </span>

                    <span className="details-key">Clarity Assessment:</span>
                    <span className="details-val">
                      {(inspectDoc.quality_score ?? 95) >= 85 ? 'Acceptable for Legal & Regulatory Submission' : 'Requires Manual Inspection'}
                    </span>
                  </div>

                  <span className="drawer-section-title" style={{ marginTop: '0.5rem' }}>Quality Flags Detected</span>
                  {inspectDoc.quality_issues && inspectDoc.quality_issues.length > 0 ? (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                      {inspectDoc.quality_issues.map((issue, idx) => (
                        <div
                          key={idx}
                          style={{
                            background: 'var(--warning-bg)',
                            border: '1px solid var(--warning-border)',
                            color: 'var(--warning-text)',
                            padding: '0.45rem 0.65rem',
                            borderRadius: 'var(--radius-xs)',
                            fontSize: '0.75rem',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '0.4rem'
                          }}
                        >
                          <AlertCircle size={14} />
                          <span>{issue}</span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div style={{
                      background: 'var(--success-bg)',
                      border: '1px solid var(--success-border)',
                      color: 'var(--success-text)',
                      padding: '0.55rem 0.75rem',
                      borderRadius: 'var(--radius-xs)',
                      fontSize: '0.75rem',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.5rem'
                    }}>
                      <CheckCircle2 size={14} />
                      <span>Zero quality defects detected. Resolution and contrast within optimal thresholds.</span>
                    </div>
                  )}
                </div>
              )}

              {drawerTab === 'ocr' && (
                <div className="drawer-section">
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <span className="drawer-section-title">OCR Text Stream</span>
                    <button
                      className="btn btn-secondary"
                      style={{ padding: '0.2rem 0.5rem', fontSize: '0.72rem' }}
                      onClick={() => copyToClipboard(inspectDoc.raw_text || '', 'ocr')}
                    >
                      {copiedKey === 'ocr' ? <Check size={12} /> : <Copy size={12} />}
                      <span>{copiedKey === 'ocr' ? 'Copied' : 'Copy Text'}</span>
                    </button>
                  </div>
                  <pre className="ocr-text-box">
                    {inspectDoc.raw_text || '[No OCR text available or processing in progress]'}
                  </pre>
                </div>
              )}
            </div>

            {/* Drawer Footer */}
            <div className="drawer-footer">
              <button
                className="btn btn-primary"
                onClick={() => triggerDownload(inspectDoc.document_id)}
              >
                <Download size={14} />
                <span>Download Original Document</span>
              </button>
              <button
                className="btn btn-secondary"
                onClick={() => setInspectDoc(null)}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
