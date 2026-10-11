/**
 * Bulk Certificate Generator — File Manager & Dashboard Frontend Logic
 * Vanilla JavaScript implementation for high performance & zero dependencies
 */

const state = {
  certificates: [],
  total: 0,
  jobs: [],
  stats: null,
  viewMode: 'table', // 'table' | 'grid'
  statusFilter: '',
  selectedJobId: '',
  searchQuery: '',
  pollTimer: null,
  currentSignatureData: null,
  socket: null,
  reconnectAttempts: 0,
  selectedCertIds: new Set(),
};

// --- DOM References ---
const elements = {
  statTotalCerts: document.getElementById('statTotalCerts'),
  statTotalJobs: document.getElementById('statTotalJobs'),
  statSuccessRate: document.getElementById('statSuccessRate'),
  statStorageUsed: document.getElementById('statStorageUsed'),
  statStorageBucket: document.getElementById('statStorageBucket'),
  storageBackendText: document.getElementById('storageBackendText'),
  btnRustFSConsole: document.getElementById('btnRustFSConsole'),
  
  jobFilterSelect: document.getElementById('jobFilterSelect'),
  searchInput: document.getElementById('searchInput'),
  filesContainer: document.getElementById('filesContainer'),
  btnDownloadZip: document.getElementById('btnDownloadZip'),
  btnDeleteBatch: document.getElementById('btnDeleteBatch'),
  btnDeleteEmptyBatches: document.getElementById('btnDeleteEmptyBatches'),
  batchInfoBar: document.getElementById('batchInfoBar'),
  btnDownloadSelectedZip: document.getElementById('btnDownloadSelectedZip'),
  btnDownloadSelectedText: document.getElementById('btnDownloadSelectedText'),
  btnDeleteSelected: document.getElementById('btnDeleteSelected'),
  btnDeleteSelectedText: document.getElementById('btnDeleteSelectedText'),
  btnRefresh: document.getElementById('btnRefresh'),

  btnNewBatch: document.getElementById('btnNewBatch'),
  btnViewTable: document.getElementById('btnViewTable'),
  btnViewGrid: document.getElementById('btnViewGrid'),

  // Live Job Banner
  liveJobBanner: document.getElementById('liveJobBanner'),
  liveJobTitle: document.getElementById('liveJobTitle'),
  liveJobProgressText: document.getElementById('liveJobProgressText'),
  liveJobPercent: document.getElementById('liveJobPercent'),
  liveProgressBar: document.getElementById('liveProgressBar'),
  liveJobRecipient: document.getElementById('liveJobRecipient'),
  
  // Preview Modal
  previewModal: document.getElementById('previewModal'),
  previewIframe: document.getElementById('previewIframe'),
  previewTitle: document.getElementById('previewTitle'),
  btnPreviewDownload: document.getElementById('btnPreviewDownload'),
  btnClosePreview: document.getElementById('btnClosePreview'),
  
  // New Job Modal
  jobModal: document.getElementById('jobModal'),
  jobForm: document.getElementById('jobForm'),
  btnCloseJobModal: document.getElementById('btnCloseJobModal'),
  btnCancelJobModal: document.getElementById('btnCancelJobModal'),
  recipientsContainer: document.getElementById('recipientsContainer'),
  recipientCountBadge: document.getElementById('recipientCountBadge'),
  btnAddRecipient: document.getElementById('btnAddRecipient'),
  btnUploadRecipientsFile: document.getElementById('btnUploadRecipientsFile'),
  recipientFileInput: document.getElementById('recipientFileInput'),
  fileUploadStatus: document.getElementById('fileUploadStatus'),
  btnSubmitJob: document.getElementById('btnSubmitJob'),

  // Signature Upload
  btnUploadSignature: document.getElementById('btnUploadSignature'),
  btnClearSignature: document.getElementById('btnClearSignature'),
  signatureFileInput: document.getElementById('signatureFileInput'),
  signaturePreviewBox: document.getElementById('signaturePreviewBox'),
  signaturePreviewImg: document.getElementById('signaturePreviewImg'),

  // Template and Sample Loaders
  btnLoadSample1: document.getElementById('btnLoadSample1'),
  btnLoadSample2: document.getElementById('btnLoadSample2'),
  templateCardClassic: document.getElementById('templateCardClassic'),
  templateCardModern: document.getElementById('templateCardModern'),
  
  toastContainer: document.getElementById('toastContainer'),
};

// --- Toast Notifications ---
function showToast(message, type = 'info') {
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  const tag = type === 'success' ? '[OK]' : type === 'error' ? '[ERR]' : '[INFO]';
  toast.innerHTML = `
    <span style="font-weight:700; font-size:0.75rem">${tag}</span>
    <span>${message}</span>
  `;
  elements.toastContainer.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(10px)';
    setTimeout(() => toast.remove(), 250);
  }, 3500);
}

// --- Fetch Metrics & Stats ---
async function fetchStats() {
  try {
    const res = await fetch('/api/stats/');
    if (!res.ok) return;
    const data = await res.json();
    state.stats = data;
    
    elements.statTotalCerts.textContent = data.total_certificates.toLocaleString();
    elements.statTotalJobs.textContent = data.total_jobs.toLocaleString();
    
    const rate = data.total_certificates > 0 
      ? Math.round((data.successful_certificates / data.total_certificates) * 100) 
      : 100;
    elements.statSuccessRate.textContent = `${rate}%`;
    elements.statStorageUsed.textContent = data.total_storage_formatted;

    if (elements.storageBackendText) {
      const isRustFS = ['s3', 'rustfs', 'minio'].includes((data.storage_backend || '').toLowerCase());
      if (isRustFS) {
        elements.storageBackendText.textContent = `Storage: RustFS (S3)`;
        if (elements.btnRustFSConsole) elements.btnRustFSConsole.style.display = 'inline-flex';
        if (elements.statStorageBucket) elements.statStorageBucket.textContent = `Bucket: ${data.bucket_name || 'certificates'}`;
      } else {
        elements.storageBackendText.textContent = `Storage: Local Disk`;
        if (elements.btnRustFSConsole) elements.btnRustFSConsole.style.display = 'none';
        if (elements.statStorageBucket) elements.statStorageBucket.textContent = 'Local Volume';
      }
    }
  } catch (err) {
    console.error('Error fetching stats:', err);
  }
}

// --- Fetch Jobs List ---
async function fetchJobs() {
  try {
    const res = await fetch('/api/jobs/?limit=100');
    if (!res.ok) return;
    state.jobs = await res.json();
    
    // Populate job select
    const currentVal = elements.jobFilterSelect.value;
    elements.jobFilterSelect.innerHTML = '<option value="">All Jobs / Batches</option>';
    state.jobs.forEach(job => {
      const opt = document.createElement('option');
      opt.value = job.id;
      const isEmpty = (job.total_recipients === 0 || (!job.successful_count && job.status !== 'processing' && job.status !== 'pending'));
      opt.textContent = `${job.title} (${job.total_recipients} certs) - ${job.status}${isEmpty ? ' [Empty]' : ''}`;
      elements.jobFilterSelect.appendChild(opt);
    });
    elements.jobFilterSelect.value = currentVal;

    
    // Check if any job is still pending/processing
    const activeJob = state.jobs.find(j => j.status === 'pending' || j.status === 'processing');
    if (activeJob && elements.liveJobBanner) {
      elements.liveJobBanner.style.display = 'block';
      if (elements.liveJobTitle) elements.liveJobTitle.textContent = activeJob.title;
      const done = (activeJob.successful_count || 0) + (activeJob.failed_count || 0);
      const total = activeJob.total_recipients || 0;
      const pct = total > 0 ? Math.round((done / total) * 100) : 0;
      if (elements.liveJobProgressText) elements.liveJobProgressText.textContent = `${done} / ${total}`;
      if (elements.liveJobPercent) elements.liveJobPercent.textContent = `${pct}%`;
      if (elements.liveProgressBar) elements.liveProgressBar.style.width = `${pct}%`;
      if (elements.liveJobRecipient) {
        elements.liveJobRecipient.textContent = activeJob.status === 'processing' ? 'Processing in worker...' : 'Queued...';
      }
    }

    if (activeJob && !state.pollTimer) {
      state.pollTimer = setInterval(() => {
        fetchCertificates(false);
        fetchStats();
        fetchJobs();
      }, 2500);
    } else if (!activeJob && state.pollTimer) {
      clearInterval(state.pollTimer);
      state.pollTimer = null;
    }
  } catch (err) {
    console.error('Error fetching jobs:', err);
  }
}

// --- Fetch Certificate Files ---
async function fetchCertificates(showSpinner = true) {
  if (showSpinner) {
    elements.filesContainer.innerHTML = `
      <div class="empty-state">
        <div class="empty-state-icon">Loading</div>
        <p>Loading certificate files...</p>
      </div>
    `;
  }

  try {
    const params = new URLSearchParams();
    if (state.selectedJobId) params.append('job_id', state.selectedJobId);
    if (state.statusFilter) params.append('status_filter', state.statusFilter);
    if (state.searchQuery) params.append('search', state.searchQuery);
    params.append('limit', '100');

    const res = await fetch(`/api/certificates/?${params.toString()}`);
    if (!res.ok) throw new Error('Failed to load certificates');
    
    const data = await res.json();
    state.certificates = data.items;
    state.total = data.total;

    // Retain only selected IDs that still exist in current result
    const currentIds = new Set(data.items.map(c => c.id));
    state.selectedCertIds = new Set(Array.from(state.selectedCertIds).filter(id => currentIds.has(id)));

    // Update batch selection toolbar actions and info bar
    updateSelectedJobUI();


    renderCertificates();
  } catch (err) {
    elements.filesContainer.innerHTML = `
      <div class="empty-state">
        <div class="empty-state-icon">Error</div>
        <p>Error loading certificate files: ${err.message}</p>
      </div>
    `;
  }
}

// --- Render Table or Grid View ---
function renderCertificates() {
  if (state.certificates.length === 0) {
    elements.filesContainer.innerHTML = `
      <div class="empty-state">
        <div class="empty-state-icon">Empty</div>
        <h3>No Certificates Found</h3>
        <p>No certificate files matched the current filters or query.</p>
      </div>
    `;
    return;
  }

  if (state.viewMode === 'table') {
    renderTableView();
  } else {
    renderGridView();
  }
}

function updateSelectionUI() {
  const count = state.selectedCertIds.size;
  if (elements.btnDownloadSelectedZip) {
    if (count > 0) {
      elements.btnDownloadSelectedZip.style.display = 'inline-flex';
      if (elements.btnDownloadSelectedText) {
        elements.btnDownloadSelectedText.textContent = `Download Selected (${count}) ZIP`;
      }
    } else {
      elements.btnDownloadSelectedZip.style.display = 'none';
    }
  }

  if (elements.btnDeleteSelected) {
    if (count > 0) {
      elements.btnDeleteSelected.style.display = 'inline-flex';
      if (elements.btnDeleteSelectedText) {
        elements.btnDeleteSelectedText.textContent = `Delete Selected (${count})`;
      }
    } else {
      elements.btnDeleteSelected.style.display = 'none';
    }
  }

  const selectAll = document.getElementById('selectAllCheckbox');
  if (selectAll) {
    selectAll.checked = state.certificates.length > 0 && state.certificates.every(c => state.selectedCertIds.has(c.id));
  }
}

async function downloadSelectedZip() {
  const ids = Array.from(state.selectedCertIds);
  if (ids.length === 0) {
    showToast('Please select at least one ready certificate to download', 'info');
    return;
  }

  if (elements.btnDownloadSelectedZip) {
    elements.btnDownloadSelectedZip.disabled = true;
  }
  if (elements.btnDownloadSelectedText) {
    elements.btnDownloadSelectedText.textContent = 'Generating ZIP...';
  }

  try {
    const res = await fetch('/api/certificates/download-selected-zip/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ certificate_ids: ids }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Failed to generate ZIP archive');
    }

    const blob = await res.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `selected_certificates_${ids.length}.zip`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);
    showToast(`Downloaded ZIP with ${ids.length} certificates`, 'success');
  } catch (err) {
    showToast(`Download error: ${err.message}`, 'error');
  } finally {
    if (elements.btnDownloadSelectedZip) {
      elements.btnDownloadSelectedZip.disabled = false;
    }
    updateSelectionUI();
  }
}

async function deleteSelectedCertificates() {
  const ids = Array.from(state.selectedCertIds);
  if (ids.length === 0) {
    showToast('Please select at least one certificate to delete', 'info');
    return;
  }

  const confirmMsg = `Are you sure you want to permanently delete the ${ids.length} selected certificate(s)? All generated files will be removed.`;
  if (!window.confirm(confirmMsg)) {
    return;
  }

  if (elements.btnDeleteSelected) {
    elements.btnDeleteSelected.disabled = true;
  }
  if (elements.btnDeleteSelectedText) {
    elements.btnDeleteSelectedText.textContent = 'Deleting...';
  }

  try {
    const res = await fetch('/api/certificates/bulk-delete/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ certificate_ids: ids }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Bulk deletion failed');
    }

    const data = await res.json();
    showToast(data.message || `Successfully deleted ${data.deleted_count} certificate(s)`, 'success');
    state.selectedCertIds.clear();
    updateSelectionUI();
    await fetchCertificates();
    await fetchStats();
    await fetchJobs();
  } catch (err) {
    showToast(`Error deleting certificates: ${err.message}`, 'error');
  } finally {
    if (elements.btnDeleteSelected) {
      elements.btnDeleteSelected.disabled = false;
    }
    updateSelectionUI();
  }
}


function renderTableView() {
  const rows = state.certificates.map(cert => {
    const statusBadge = getStatusBadge(cert.status);
    const size = cert.file_size_formatted || (cert.status === 'success' ? 'Ready' : '—');
    const isS3 = ['s3', 'rustfs', 'minio'].includes((cert.storage_backend || '').toLowerCase());
    const date = cert.created_at ? new Date(cert.created_at).toLocaleDateString() : '—';
    const isChecked = state.selectedCertIds.has(cert.id);
    const isReady = cert.status === 'success';

    const isModern = (cert.template || '').toLowerCase() === 'modern';
    const templateBadge = `<span class="template-badge ${isModern ? 'template-badge-modern' : 'template-badge-classic'}">${isModern ? 'Modern' : 'Classic'}</span>`;

    return `
      <tr class="${isChecked ? 'row-selected' : ''}">
        <td style="text-align:center; width:44px;">
          <input type="checkbox" class="cert-checkbox cert-select-checkbox" data-id="${cert.id}" ${isChecked ? 'checked' : ''} aria-label="Select certificate for ${escapeAttr(cert.recipient_name)}">
        </td>
        <td>
          <div class="file-info">
            <div class="file-icon" style="${isS3 ? 'background:linear-gradient(135deg, #EA580C, #C2410C); color:#FFF;' : ''}">${isS3 ? 'S3' : 'PDF'}</div>
            <div>
              <div class="file-name">${escapeHtml(cert.recipient_name)}</div>
              <div class="file-sub">${escapeHtml(cert.recipient_email || 'No email')}</div>
            </div>
          </div>
        </td>
        <td>
          <div class="file-name" style="font-size:0.85rem">
            ${escapeHtml(cert.job_title)}
            ${templateBadge}
          </div>
          <div class="file-sub">${escapeHtml(cert.job_organization)}</div>
        </td>
        <td>${statusBadge}</td>
        <td style="font-family:'JetBrains Mono', monospace; font-size:0.8rem; color:var(--text-muted)">
          ${size} ${isS3 ? '<span style="color:#FB923C; font-size:0.7rem; font-weight:600;">[RustFS]</span>' : ''}
        </td>
        <td style="font-size:0.8rem; color:var(--text-muted)">${date}</td>
        <td>
          <div style="display:flex; gap:6px; justify-content:flex-end">
            ${isReady ? `
              <button class="btn btn-secondary btn-icon" title="Preview PDF" onclick="openPreview('${cert.id}', '${escapeAttr(cert.recipient_name)}')">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                  <circle cx="12" cy="12" r="3"/>
                </svg>
              </button>
              <a href="${cert.download_url}" class="btn btn-secondary btn-icon" title="Download PDF" download>
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                  <polyline points="7 10 12 15 17 10"/>
                  <line x1="12" y1="15" x2="12" y2="3"/>
                </svg>
              </a>
            ` : ''}
            <button class="btn btn-danger btn-icon" title="Delete Certificate" onclick="deleteCertificate('${cert.id}')">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="3 6 5 6 21 6"/>
                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
              </svg>
            </button>
          </div>
        </td>
      </tr>
    `;
  }).join('');

  elements.filesContainer.innerHTML = `
    <div class="table-responsive">
      <table class="files-table">
        <thead>
          <tr>
            <th style="width:44px; text-align:center;">
              <input type="checkbox" id="selectAllCheckbox" class="cert-checkbox" title="Select all ready certificates">
            </th>
            <th>Recipient</th>
            <th>Course / Event</th>
            <th>Status</th>
            <th>Size</th>
            <th>Created</th>
            <th style="text-align:right">Actions</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
  `;
  updateSelectionUI();
}

function renderGridView() {
  const cards = state.certificates.map(cert => {
    const statusBadge = getStatusBadge(cert.status);
    const size = cert.file_size_formatted || '—';
    const date = new Date(cert.created_at).toLocaleDateString();
    const isS3 = ['s3', 'rustfs', 'minio'].includes((cert.storage_backend || '').toLowerCase());
    const isChecked = state.selectedCertIds.has(cert.id);
    const isReady = cert.status === 'success';

    const isModern = (cert.template || '').toLowerCase() === 'modern';
    const templateBadge = `<span class="template-badge ${isModern ? 'template-badge-modern' : 'template-badge-classic'}">${isModern ? 'Modern' : 'Classic'}</span>`;

    return `
      <div class="cert-card ${isChecked ? 'card-selected' : ''}">
        <div class="cert-card-header">
          <div style="display:flex; align-items:center; gap:10px;">
            <input type="checkbox" class="cert-checkbox cert-select-checkbox" data-id="${cert.id}" ${isChecked ? 'checked' : ''} aria-label="Select certificate for ${escapeAttr(cert.recipient_name)}">
            <div class="file-icon" style="width:36px; height:36px; font-size:12px; ${isS3 ? 'background:linear-gradient(135deg, #EA580C, #C2410C); color:#FFF;' : ''}">${isS3 ? 'S3' : 'PDF'}</div>
          </div>
          ${statusBadge}
        </div>
        <div>
          <div class="cert-card-title">${escapeHtml(cert.recipient_name)}</div>
          <div class="cert-card-course" style="display:flex; align-items:center; gap:6px; flex-wrap:wrap;">
            <span>${escapeHtml(cert.job_title)}</span>
            ${templateBadge}
          </div>
        </div>
        <div class="cert-card-meta">
          <span>${size} ${isS3 ? '<b style="color:#FB923C;">RustFS</b>' : ''}</span>
          <span>${date}</span>
        </div>
        <div class="cert-card-actions">
          ${isReady ? `
            <button class="btn btn-secondary" style="flex:1; padding:8px" onclick="openPreview('${cert.id}', '${escapeAttr(cert.recipient_name)}')">
              Preview
            </button>
            <a href="${cert.download_url}" class="btn btn-primary" style="flex:1; padding:8px; text-align:center" download>
              Download
            </a>
          ` : ''}
          <button class="btn btn-danger btn-icon" title="Delete Certificate" onclick="deleteCertificate('${cert.id}')">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="3 6 5 6 21 6"/>
              <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
            </svg>
          </button>
        </div>
      </div>
    `;
  }).join('');

  elements.filesContainer.innerHTML = `<div class="grid-container">${cards}</div>`;
  updateSelectionUI();
}

function getStatusBadge(status) {
  switch (status) {
    case 'success':
      return `<span class="badge badge-success">Ready</span>`;
    case 'failed':
      return `<span class="badge badge-failed">Failed</span>`;
    case 'processing':
      return `<span class="badge badge-processing">Rendering</span>`;
    default:
      return `<span class="badge badge-pending">Queued</span>`;
  }
}

// --- Preview Modal ---
function openPreview(id, name) {
  elements.previewTitle.textContent = `Certificate Preview — ${name}`;
  elements.previewIframe.src = `/api/certificates/${id}/preview/`;
  elements.btnPreviewDownload.href = `/api/certificates/${id}/download/`;
  elements.previewModal.classList.add('active');
}

function closePreview() {
  elements.previewModal.classList.remove('active');
  elements.previewIframe.src = 'about:blank';
}

// --- Delete Certificate ---
async function deleteCertificate(id) {
  if (!confirm('Are you sure you want to delete this certificate and remove its file?')) {
    return;
  }

  try {
    const res = await fetch(`/api/certificates/${id}/`, { method: 'DELETE' });
    if (!res.ok) throw new Error('Deletion failed');
    showToast('Certificate deleted successfully', 'success');
    fetchCertificates(false);
    fetchStats();
    fetchJobs();
  } catch (err) {
    showToast(`Error: ${err.message}`, 'error');
  }
}

// --- Download Job ZIP ---
function downloadCurrentJobZip() {
  if (!state.selectedJobId) return;
  window.location.href = `/api/jobs/${state.selectedJobId}/download-zip/`;
}

// --- Batch Selection and Deletion ---
function updateSelectedJobUI() {
  const selectedJob = state.jobs.find(j => j.id === state.selectedJobId);
  if (state.selectedJobId && selectedJob) {
    if (elements.btnDownloadZip) elements.btnDownloadZip.style.display = 'inline-flex';
    if (elements.btnDeleteBatch) elements.btnDeleteBatch.style.display = 'inline-flex';
    if (elements.batchInfoBar) {
      elements.batchInfoBar.style.display = 'flex';
      const tplName = selectedJob.template === 'modern' ? 'Modern Slate & Sky' : 'Classic Gold Parchment';
      const tplBadge = selectedJob.template === 'modern' ? '<span class="template-badge modern">[Modern]</span>' : '<span class="template-badge classic">[Classic]</span>';
      elements.batchInfoBar.innerHTML = `
        <div>
          <div class="batch-info-title">${escapeHtml(selectedJob.title)}</div>
          <div class="batch-info-meta">
            <span>Org: <strong>${escapeHtml(selectedJob.organization)}</strong></span>
            <span>Date: <strong>${escapeHtml(selectedJob.date_of_issue)}</strong></span>
            <span>Template: ${tplBadge} <strong>${tplName}</strong></span>
            <span>Status: <span class="status-badge ${selectedJob.status}">[${selectedJob.status.toUpperCase()}]</span></span>
            <span>Total: <strong>${selectedJob.total_recipients}</strong></span>
            <span>Ready: <strong style="color:var(--emerald-success);">${selectedJob.successful_count || 0}</strong></span>
            <span>Failed: <strong style="color:var(--rose-danger);">${selectedJob.failed_count || 0}</strong></span>
          </div>
        </div>
        <div style="display:flex; gap:8px;">
          <button class="btn btn-secondary" id="btnBannerDownloadZip" style="font-size:0.75rem; padding:5px 12px;">Download Batch ZIP</button>
          <button class="btn btn-danger" id="btnBannerDeleteBatch" style="font-size:0.75rem; padding:5px 12px;">Delete Batch</button>
        </div>
      `;
      const btnBannerDownloadZip = document.getElementById('btnBannerDownloadZip');
      if (btnBannerDownloadZip) {
        btnBannerDownloadZip.addEventListener('click', downloadCurrentJobZip);
      }
      const btnBannerDeleteBatch = document.getElementById('btnBannerDeleteBatch');
      if (btnBannerDeleteBatch) {
        btnBannerDeleteBatch.addEventListener('click', deleteCurrentBatch);
      }
    }
  } else {
    if (elements.btnDownloadZip) elements.btnDownloadZip.style.display = 'none';
    if (elements.btnDeleteBatch) elements.btnDeleteBatch.style.display = 'none';
    if (elements.batchInfoBar) elements.batchInfoBar.style.display = 'none';
  }
}

async function deleteCurrentBatch() {
  if (!state.selectedJobId) {
    showToast('Please select a batch to delete from the dropdown filter first', 'info');
    return;
  }
  const currentJob = state.jobs.find(j => j.id === state.selectedJobId);
  const batchTitle = currentJob ? currentJob.title : state.selectedJobId;
  const certCount = currentJob ? currentJob.total_recipients : 0;
  const confirmMsg = `Are you sure you want to delete batch "${batchTitle}" (${certCount} certificates)? All generated PDF files will be permanently deleted.`;
  if (!window.confirm(confirmMsg)) {
    return;
  }

  try {
    const res = await fetch(`/api/jobs/${encodeURIComponent(state.selectedJobId)}/`, {
      method: 'DELETE',
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Failed to delete batch');
    }
    showToast(`Batch "${batchTitle}" deleted successfully`, 'success');
    state.selectedJobId = '';
    if (elements.jobFilterSelect) elements.jobFilterSelect.value = '';
    updateSelectedJobUI();
    await fetchJobs();
    await fetchStats();
    await fetchCertificates();
  } catch (err) {
    showToast(`Error deleting batch: ${err.message}`, 'error');
  }
}

async function deleteEmptyBatches() {
  if (!window.confirm('Are you sure you want to delete all empty batches (batches with 0 certificates)?')) {
    return;
  }

  try {
    const res = await fetch('/api/jobs/cleanup/empty/', {
      method: 'DELETE',
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Failed to delete empty batches');
    }
    const data = await res.json();
    if (data.deleted_count === 0) {
      showToast('No empty batches found to delete', 'info');
    } else {
      showToast(`Successfully deleted ${data.deleted_count} empty batch(es)`, 'success');
    }
    if (state.selectedJobId && data.deleted_job_ids && data.deleted_job_ids.includes(state.selectedJobId)) {
      state.selectedJobId = '';
      if (elements.jobFilterSelect) elements.jobFilterSelect.value = '';
      updateSelectedJobUI();
    }
    await fetchJobs();
    await fetchStats();
    await fetchCertificates();
  } catch (err) {
    showToast(`Error cleaning empty batches: ${err.message}`, 'error');
  }
}


function updateTemplateCardUI(val) {
  if (elements.templateCardClassic) {
    elements.templateCardClassic.classList.toggle('active', val === 'classic');
  }
  if (elements.templateCardModern) {
    elements.templateCardModern.classList.toggle('active', val === 'modern');
  }
}

async function loadSampleSignature(url) {
  try {
    const res = await fetch(url);
    if (!res.ok) return;
    const blob = await res.blob();
    const reader = new FileReader();
    reader.onload = (e) => {
      state.currentSignatureData = e.target.result;
      if (elements.signaturePreviewImg) elements.signaturePreviewImg.src = e.target.result;
      if (elements.signaturePreviewBox) elements.signaturePreviewBox.style.display = 'inline-flex';
      if (elements.btnClearSignature) elements.btnClearSignature.style.display = 'inline-flex';
    };
    reader.readAsDataURL(blob);
  } catch (err) {
    console.error('Failed to load sample signature:', err);
  }
}

function populateRecipientsFromList(recipients) {
  elements.recipientsContainer.innerHTML = '';
  recipients.forEach(r => addRecipientRow(r.name, r.email));
  if (elements.fileUploadStatus) {
    elements.fileUploadStatus.textContent = `Loaded ${recipients.length} recipients`;
    elements.fileUploadStatus.style.display = 'block';
    elements.fileUploadStatus.style.color = 'var(--emerald-success)';
  }
}

async function loadSampleData(sampleNum) {
  if (sampleNum === 1) {
    document.getElementById('jobTitle').value = 'Full Stack Cloud & DevOps Engineering Bootcamp';
    document.getElementById('jobOrg').value = 'Global Tech Academy';
    document.getElementById('jobDate').value = '2026-10-15';

    const classicRadio = document.querySelector('input[name="jobTemplate"][value="classic"]');
    if (classicRadio) classicRadio.checked = true;
    updateTemplateCardUI('classic');

    try {
      const csvRes = await fetch('/static/samples/sample_recipients_1.csv');
      if (csvRes.ok) {
        const csvText = await csvRes.text();
        const lines = csvText.split(/\r?\n/).filter(line => line.trim().length > 0);
        const sampleRecipients = [];
        for (let i = 1; i < lines.length; i++) {
          const parts = lines[i].split(',');
          if (parts.length > 0 && parts[0].trim()) {
            sampleRecipients.push({
              name: parts[0].trim(),
              email: parts.length > 1 ? parts[1].trim() : '',
            });
          }
        }
        if (sampleRecipients.length > 0) {
          populateRecipientsFromList(sampleRecipients);
        }
      }
    } catch (e) {
      console.warn('Could not fetch sample CSV, using default list', e);
    }

    await loadSampleSignature('/static/samples/sample_signature_1.png');
    showToast('Loaded Sample 1 (50 Recipients & Classic Gold Template)', 'info');
  } else if (sampleNum === 2) {
    document.getElementById('jobTitle').value = 'Advanced AI & Neural Systems Masterclass';
    document.getElementById('jobOrg').value = 'Quantum Intelligence Institute';
    document.getElementById('jobDate').value = '2026-10-20';

    const modernRadio = document.querySelector('input[name="jobTemplate"][value="modern"]');
    if (modernRadio) modernRadio.checked = true;
    updateTemplateCardUI('modern');

    const sample2 = [
      { name: 'Jonathan Hayes', email: 'jonathan.hayes@quantumlabs.ai' },
      { name: 'Dr. Beatrix Lestrange', email: 'beatrix.lestrange@research.org' },
      { name: 'Carlos Santana Rodriguez', email: 'carlos.rodriguez@deepmind.io' },
      { name: 'Aisha Patel', email: 'aisha.patel@machineintelligence.com' },
      { name: 'Chloe Dupont', email: 'chloe.dupont@sorbonne-data.fr' },
      { name: 'Kenji Takahashi', email: 'kenji.takahashi@tokyotech.ac.jp' },
      { name: 'Michael Chang', email: 'michael.chang@ai-foundry.com' },
      { name: 'Fatima Zahra', email: 'fatima.zahra@computational.org' },
    ];
    populateRecipientsFromList(sample2);
    await loadSampleSignature('/static/samples/sample_signature_2.png');
    showToast('Loaded Sample 2 (AI Masterclass & Modern Slate Template)', 'info');
  }
}

// --- New Batch Modal Logic ---
function openJobModal() {
  elements.jobModal.classList.add('active');
  // Set default issue date to today's YYYY-MM-DD
  const today = new Date().toISOString().split('T')[0];
  document.getElementById('jobDate').value = today;
  resetRecipients();
  const classicRadio = document.querySelector('input[name="jobTemplate"][value="classic"]');
  if (classicRadio) classicRadio.checked = true;
  updateTemplateCardUI('classic');
  setTimeout(() => {
    const titleInput = document.getElementById('jobTitle');
    if (titleInput) titleInput.focus();
  }, 60);
}

function closeJobModal() {
  elements.jobModal.classList.remove('active');
  if (elements.btnNewBatch) elements.btnNewBatch.focus();
}

function clearSignature() {
  state.currentSignatureData = null;
  if (elements.signatureFileInput) elements.signatureFileInput.value = '';
  if (elements.signaturePreviewBox) elements.signaturePreviewBox.style.display = 'none';
  if (elements.signaturePreviewImg) elements.signaturePreviewImg.src = '';
  if (elements.btnClearSignature) elements.btnClearSignature.style.display = 'none';
}

function handleSignatureFileSelect(file) {
  if (!file) return;
  if (!file.type.startsWith('image/')) {
    showToast('Signature must be a valid PNG or JPEG image', 'error');
    return;
  }
  const reader = new FileReader();
  reader.onload = (e) => {
    state.currentSignatureData = e.target.result;
    if (elements.signaturePreviewImg) elements.signaturePreviewImg.src = e.target.result;
    if (elements.signaturePreviewBox) elements.signaturePreviewBox.style.display = 'inline-flex';
    if (elements.btnClearSignature) elements.btnClearSignature.style.display = 'inline-flex';
  };
  reader.onerror = () => {
    showToast('Failed to read signature image', 'error');
  };
  reader.readAsDataURL(file);
}

function updateRecipientCountBadge() {
  if (!elements.recipientCountBadge) return;
  const count = elements.recipientsContainer.querySelectorAll('.recipient-entry').length;
  elements.recipientCountBadge.textContent = `${count} recipient${count === 1 ? '' : 's'}`;
}

function resetRecipients() {
  clearSignature();
  elements.recipientsContainer.innerHTML = '';
  addRecipientRow();
  if (elements.fileUploadStatus) {
    elements.fileUploadStatus.textContent = '';
    elements.fileUploadStatus.style.display = 'none';
  }
  if (elements.recipientFileInput) {
    elements.recipientFileInput.value = '';
  }
  updateRecipientCountBadge();
}

function addRecipientRow(name = '', email = '') {
  const row = document.createElement('div');
  row.className = 'recipient-entry';
  row.innerHTML = `
    <input type="text" class="form-input recipient-name" value="${escapeAttr(name)}" placeholder="Recipient Full Name" required>
    <input type="email" class="form-input recipient-email" value="${escapeAttr(email)}" placeholder="Email (optional)">
    <button type="button" class="btn btn-danger btn-icon btn-remove-recipient" title="Remove Recipient">&times;</button>
  `;
  const btnRemove = row.querySelector('.btn-remove-recipient');
  if (btnRemove) {
    btnRemove.addEventListener('click', () => {
      row.remove();
      updateRecipientCountBadge();
    });
  }
  elements.recipientsContainer.appendChild(row);
  updateRecipientCountBadge();
}


// --- Import Recipients from JSON, CSV, or Excel File ---
async function handleRecipientFileUpload(file) {
  if (!file) return;

  if (elements.fileUploadStatus) {
    elements.fileUploadStatus.style.display = 'block';
    elements.fileUploadStatus.style.color = 'var(--text-muted)';
    elements.fileUploadStatus.textContent = `Parsing ${file.name}...`;
  }

  const formData = new FormData();
  formData.append('file', file);

  try {
    const res = await fetch('/api/recipients/parse-file/', {
      method: 'POST',
      body: formData,
    });

    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      throw new Error(errData.detail || 'Failed to parse file');
    }

    const data = await res.json();
    if (!data.recipients || data.recipients.length === 0) {
      throw new Error('No valid recipients found in uploaded file');
    }

    // Populate recipients rows
    elements.recipientsContainer.innerHTML = '';
    data.recipients.forEach(rec => {
      addRecipientRow(rec.name, rec.email || '');
    });

    if (elements.fileUploadStatus) {
      elements.fileUploadStatus.style.color = 'var(--emerald-success)';
      elements.fileUploadStatus.textContent = `Imported ${data.total_count} recipient(s) from ${file.name}`;
    }
    showToast(`Loaded ${data.total_count} recipient(s) from ${file.name}`, 'success');
  } catch (err) {
    if (elements.fileUploadStatus) {
      elements.fileUploadStatus.style.color = 'var(--rose-danger)';
      elements.fileUploadStatus.textContent = `Upload error: ${err.message}`;
    }
    showToast(err.message, 'error');
  }
}

async function handleJobSubmit(e) {
  e.preventDefault();
  
  const title = document.getElementById('jobTitle').value.trim();
  const organization = document.getElementById('jobOrg').value.trim();
  const date_of_issue = document.getElementById('jobDate').value.trim();
  
  const nameInputs = document.querySelectorAll('.recipient-name');
  const emailInputs = document.querySelectorAll('.recipient-email');
  
  const recipients = [];
  for (let i = 0; i < nameInputs.length; i++) {
    const name = nameInputs[i].value.trim();
    const email = emailInputs[i].value.trim() || null;
    if (name) {
      recipients.push({ name, email });
    }
  }

  if (recipients.length === 0) {
    showToast('At least one recipient is required', 'error');
    return;
  }

  elements.btnSubmitJob.disabled = true;
  elements.btnSubmitJob.textContent = 'Queueing Batch...';

  try {
    const selectedTemplate = document.querySelector('input[name="jobTemplate"]:checked')?.value || 'classic';
    const payload = {
      title,
      organization,
      date_of_issue,
      recipients,
      template: selectedTemplate,
    };
    if (state.currentSignatureData) {
      payload.signature_data = state.currentSignatureData;
    }

    const res = await fetch('/api/jobs/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail ? (typeof err.detail === 'string' ? err.detail : JSON.stringify(err.detail)) : 'Submission failed');
    }

    const data = await res.json();
    showToast(`Job queued! ${recipients.length} certificates generating in background.`, 'success');
    closeJobModal();

    // Immediately show live batch generation widget
    if (elements.liveJobBanner) {
      elements.liveJobBanner.style.display = 'block';
      if (elements.liveJobTitle) elements.liveJobTitle.textContent = title || `Job ${data.job_id.slice(0, 8)}`;
      if (elements.liveJobProgressText) elements.liveJobProgressText.textContent = `0 / ${recipients.length}`;
      if (elements.liveJobPercent) elements.liveJobPercent.textContent = `0%`;
      if (elements.liveProgressBar) elements.liveProgressBar.style.width = `0%`;
      if (elements.liveJobRecipient) elements.liveJobRecipient.textContent = 'Queued in background worker...';
    }
    
    // Keep view on All Jobs / Batches so previously generated files remain visible
    state.selectedJobId = '';
    if (elements.jobFilterSelect) {
      elements.jobFilterSelect.value = '';
    }
    await fetchJobs();
    fetchCertificates();
    fetchStats();
  } catch (err) {
    showToast(`Error: ${err.message}`, 'error');
  } finally {
    elements.btnSubmitJob.disabled = false;
    elements.btnSubmitJob.textContent = 'Generate Certificates';
  }
}

// --- Live WebSockets Job Tracking ---
let liveRefreshTimer = null;
function debounceRefresh() {
  if (liveRefreshTimer) return;
  liveRefreshTimer = setTimeout(() => {
    liveRefreshTimer = null;
    fetchCertificates();
    fetchStats();
  }, 1000);
}

function handleLiveJobEvent(event) {
  if (!event) return;
  const evtType = event.event || event.type;
  if (!evtType) return;

  const job_id = event.job_id;
  const title = event.title;
  const total = event.total != null ? event.total : (event.total_recipients != null ? event.total_recipients : 0);
  const processed = event.processed != null ? event.processed : (event.current != null ? event.current : 0);
  const percent = event.percent != null ? event.percent : (event.percentage != null ? event.percentage : 0);
  const current_recipient = event.current_recipient || event.recipient_name || '';

  if (evtType === 'job_started' || evtType === 'job_progress') {
    if (elements.liveJobBanner) {
      elements.liveJobBanner.style.display = 'block';
      if (elements.liveJobTitle) elements.liveJobTitle.textContent = title || `Job ${job_id ? job_id.slice(0, 8) : ''}`;
      if (elements.liveJobProgressText) elements.liveJobProgressText.textContent = `${processed} / ${total}`;
      const pct = percent != null ? percent : (total > 0 ? Math.round((processed / total) * 100) : 0);
      if (elements.liveJobPercent) elements.liveJobPercent.textContent = `${pct}%`;
      if (elements.liveProgressBar) elements.liveProgressBar.style.width = `${pct}%`;
      if (elements.liveJobRecipient) elements.liveJobRecipient.textContent = current_recipient ? `Recipient: ${current_recipient}` : 'Generating certificates...';
    }

    if (!state.selectedJobId || state.selectedJobId === job_id) {
      debounceRefresh();
    }
  } else if (evtType === 'job_completed') {
    if (elements.liveJobBanner) {
      if (elements.liveJobPercent) elements.liveJobPercent.textContent = '100%';
      if (elements.liveProgressBar) elements.liveProgressBar.style.width = '100%';
      if (elements.liveJobRecipient) elements.liveJobRecipient.textContent = 'Batch Completed Successfully';
      setTimeout(() => {
        if (elements.liveJobBanner) elements.liveJobBanner.style.display = 'none';
      }, 4000);
    }
    showToast(`Batch completed: ${title || (job_id ? job_id.slice(0, 8) : '')} (${total || 0} certificates ready)`, 'success');
    fetchStats();
    fetchJobs();
    fetchCertificates();
  } else if (evtType === 'job_failed') {
    if (elements.liveJobBanner) {
      if (elements.liveJobRecipient) elements.liveJobRecipient.textContent = `Batch failed: ${event.error || 'Worker error'}`;
      setTimeout(() => {
        if (elements.liveJobBanner) elements.liveJobBanner.style.display = 'none';
      }, 5000);
    }
    showToast(`Batch failed: ${event.error || 'Worker error'}`, 'error');
    fetchStats();
    fetchJobs();
    fetchCertificates();
  }
}

function initWebSocket() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${window.location.host}/ws/jobs`;

  try {
    const ws = new WebSocket(wsUrl);
    state.socket = ws;

    ws.onopen = () => {
      state.reconnectAttempts = 0;
      console.log('[WS] Connected to live job stream');
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        handleLiveJobEvent(data);
      } catch (err) {
        console.error('[WS] Parse error:', err);
      }
    };

    ws.onclose = () => {
      const delay = Math.min(10000, 1000 * Math.pow(2, state.reconnectAttempts || 0));
      state.reconnectAttempts = (state.reconnectAttempts || 0) + 1;
      setTimeout(initWebSocket, delay);
    };

    ws.onerror = () => {
      ws.close();
    };
  } catch (err) {
    console.error('[WS] Connection error:', err);
  }
}

// --- Utility Helpers ---
function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function escapeAttr(str) {
  if (!str) return '';
  return String(str).replace(/'/g, "\\'").replace(/"/g, '&quot;');
}

// --- Event Listeners Setup ---
function setupEventListeners() {
  // Filter pills
  document.querySelectorAll('.filter-pill').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.filter-pill').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      state.statusFilter = btn.dataset.status;
      fetchCertificates();
    });
  });

  // View toggle
  elements.btnViewTable.addEventListener('click', () => {
    state.viewMode = 'table';
    elements.btnViewTable.classList.add('active');
    elements.btnViewGrid.classList.remove('active');
    renderCertificates();
  });

  elements.btnViewGrid.addEventListener('click', () => {
    state.viewMode = 'grid';
    elements.btnViewGrid.classList.add('active');
    elements.btnViewTable.classList.remove('active');
    renderCertificates();
  });

  // Job Filter
  elements.jobFilterSelect.addEventListener('change', (e) => {
    state.selectedJobId = e.target.value;
    updateSelectedJobUI();
    fetchCertificates();
  });

  // Search input debounce
  let searchDebounce;
  elements.searchInput.addEventListener('input', (e) => {
    clearTimeout(searchDebounce);
    searchDebounce = setTimeout(() => {
      state.searchQuery = e.target.value.trim();
      fetchCertificates();
    }, 250);
  });

  // Refresh
  elements.btnRefresh.addEventListener('click', () => {
    fetchStats();
    fetchJobs();
    fetchCertificates();
    showToast('Refreshed file manager', 'info');
  });

  // Buttons & Modals
  if (elements.btnDownloadZip) {
    elements.btnDownloadZip.addEventListener('click', downloadCurrentJobZip);
  }
  if (elements.btnDeleteBatch) {
    elements.btnDeleteBatch.addEventListener('click', deleteCurrentBatch);
  }
  if (elements.btnDeleteEmptyBatches) {
    elements.btnDeleteEmptyBatches.addEventListener('click', deleteEmptyBatches);
  }
  if (elements.btnDownloadSelectedZip) {
    elements.btnDownloadSelectedZip.addEventListener('click', downloadSelectedZip);
  }
  if (elements.btnDeleteSelected) {
    elements.btnDeleteSelected.addEventListener('click', deleteSelectedCertificates);
  }

  // Delegation for table/grid selection checkboxes
  elements.filesContainer.addEventListener('change', (e) => {
    if (e.target && e.target.id === 'selectAllCheckbox') {
      const checked = e.target.checked;
      if (checked) {
        state.certificates.forEach(c => state.selectedCertIds.add(c.id));
      } else {
        state.certificates.forEach(c => state.selectedCertIds.delete(c.id));
      }
      renderCertificates();
    } else if (e.target && e.target.classList.contains('cert-select-checkbox')) {
      const id = e.target.dataset.id;
      if (e.target.checked) {
        state.selectedCertIds.add(id);
      } else {
        state.selectedCertIds.delete(id);
      }
      const tr = e.target.closest('tr');
      if (tr) tr.classList.toggle('row-selected', e.target.checked);
      const card = e.target.closest('.cert-card');
      if (card) card.classList.toggle('card-selected', e.target.checked);
      updateSelectionUI();
    }
  });

  elements.btnNewBatch.addEventListener('click', openJobModal);
  elements.btnCloseJobModal.addEventListener('click', closeJobModal);
  elements.btnCancelJobModal.addEventListener('click', closeJobModal);
  elements.btnAddRecipient.addEventListener('click', () => addRecipientRow());
  if (elements.btnUploadRecipientsFile && elements.recipientFileInput) {
    elements.btnUploadRecipientsFile.addEventListener('click', () => {
      elements.recipientFileInput.click();
    });
    elements.recipientFileInput.addEventListener('change', (e) => {
      const file = e.target.files && e.target.files[0];
      if (file) handleRecipientFileUpload(file);
    });
  }

  // Signature Upload
  if (elements.btnUploadSignature && elements.signatureFileInput) {
    elements.btnUploadSignature.addEventListener('click', () => {
      elements.signatureFileInput.click();
    });
    elements.signatureFileInput.addEventListener('change', (e) => {
      const file = e.target.files && e.target.files[0];
      if (file) handleSignatureFileSelect(file);
    });
  }
  if (elements.btnClearSignature) {
    elements.btnClearSignature.addEventListener('click', () => {
      clearSignature();
    });
  }

  // Template Card Selection
  document.querySelectorAll('input[name="jobTemplate"]').forEach(radio => {
    radio.addEventListener('change', (e) => {
      updateTemplateCardUI(e.target.value);
    });
  });
  if (elements.templateCardClassic) {
    elements.templateCardClassic.addEventListener('click', () => {
      const r = elements.templateCardClassic.querySelector('input[type="radio"]');
      if (r) { r.checked = true; updateTemplateCardUI('classic'); }
    });
  }
  if (elements.templateCardModern) {
    elements.templateCardModern.addEventListener('click', () => {
      const r = elements.templateCardModern.querySelector('input[type="radio"]');
      if (r) { r.checked = true; updateTemplateCardUI('modern'); }
    });
  }

  // Quick Load Sample Buttons
  if (elements.btnLoadSample1) {
    elements.btnLoadSample1.addEventListener('click', () => loadSampleData(1));
  }
  if (elements.btnLoadSample2) {
    elements.btnLoadSample2.addEventListener('click', () => loadSampleData(2));
  }

  elements.jobForm.addEventListener('submit', handleJobSubmit);

  elements.btnClosePreview.addEventListener('click', closePreview);
  elements.previewModal.addEventListener('click', (e) => {
    if (e.target === elements.previewModal) closePreview();
  });
  elements.jobModal.addEventListener('click', (e) => {
    if (e.target === elements.jobModal) closeJobModal();
  });

  // Keyboard accessibility: Escape closes any active modal
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      if (elements.previewModal.classList.contains('active')) closePreview();
      if (elements.jobModal.classList.contains('active')) closeJobModal();
    }
  });
}

// --- Initialize App ---
document.addEventListener('DOMContentLoaded', () => {
  setupEventListeners();
  fetchStats();
  fetchJobs();
  fetchCertificates();
  initWebSocket();
});
