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
  btnRefresh: document.getElementById('btnRefresh'),
  btnNewBatch: document.getElementById('btnNewBatch'),
  btnViewTable: document.getElementById('btnViewTable'),
  btnViewGrid: document.getElementById('btnViewGrid'),
  
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
  btnAddRecipient: document.getElementById('btnAddRecipient'),
  btnSubmitJob: document.getElementById('btnSubmitJob'),
  
  toastContainer: document.getElementById('toastContainer'),
};

// --- Toast Notifications ---
function showToast(message, type = 'info') {
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.innerHTML = `
    <span>${type === 'success' ? '✓' : type === 'error' ? '✕' : 'ℹ'}</span>
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
      opt.textContent = `${job.title} (${job.total_recipients} certs) - ${job.status}`;
      elements.jobFilterSelect.appendChild(opt);
    });
    elements.jobFilterSelect.value = currentVal;
    
    // Check if any job is still pending/processing
    const hasActiveJobs = state.jobs.some(j => j.status === 'pending' || j.status === 'processing');
    if (hasActiveJobs && !state.pollTimer) {
      state.pollTimer = setInterval(() => {
        fetchCertificates(false);
        fetchStats();
        fetchJobs();
      }, 3000);
    } else if (!hasActiveJobs && state.pollTimer) {
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
        <div class="empty-state-icon">⌛</div>
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

    // Enable/disable ZIP button
    if (state.selectedJobId) {
      elements.btnDownloadZip.style.display = 'inline-flex';
    } else {
      elements.btnDownloadZip.style.display = 'none';
    }

    renderCertificates();
  } catch (err) {
    elements.filesContainer.innerHTML = `
      <div class="empty-state">
        <div class="empty-state-icon">⚠️</div>
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
        <div class="empty-state-icon">📄</div>
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

function renderTableView() {
  const rows = state.certificates.map(cert => {
    const statusBadge = getStatusBadge(cert.status);
    const size = cert.file_size_formatted || (cert.status === 'success' ? 'Ready' : '—');
    const isS3 = ['s3', 'rustfs', 'minio'].includes((cert.storage_backend || '').toLowerCase());

    return `
      <tr>
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
          <div class="file-name" style="font-size:0.85rem">${escapeHtml(cert.job_title)}</div>
          <div class="file-sub">${escapeHtml(cert.job_organization)}</div>
        </td>
        <td>${statusBadge}</td>
        <td style="font-family:'JetBrains Mono', monospace; font-size:0.8rem; color:var(--text-muted)">
          ${size} ${isS3 ? '<span style="color:#FB923C; font-size:0.7rem; font-weight:600;">[RustFS]</span>' : ''}
        </td>
        <td style="font-size:0.8rem; color:var(--text-muted)">${date}</td>
        <td>
          <div style="display:flex; gap:6px; justify-content:flex-end">
            ${cert.status === 'success' ? `
              <button class="btn btn-secondary btn-icon" title="Preview PDF" onclick="openPreview('${cert.id}', '${escapeAttr(cert.recipient_name)}')">
                👁️
              </button>
              <a href="${cert.presigned_url || cert.download_url}" class="btn btn-secondary btn-icon" title="Download PDF" download>
                ⬇️
              </a>
            ` : ''}
            <button class="btn btn-danger btn-icon" title="Delete Certificate" onclick="deleteCertificate('${cert.id}')">
              🗑️
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
}

function renderGridView() {
  const cards = state.certificates.map(cert => {
    const statusBadge = getStatusBadge(cert.status);
    const size = cert.file_size_formatted || '—';
    const date = new Date(cert.created_at).toLocaleDateString();
    const isS3 = ['s3', 'rustfs', 'minio'].includes((cert.storage_backend || '').toLowerCase());

    return `
      <div class="cert-card">
        <div class="cert-card-header">
          <div class="file-icon" style="width:42px; height:42px; font-size:14px; ${isS3 ? 'background:linear-gradient(135deg, #EA580C, #C2410C); color:#FFF;' : ''}">${isS3 ? 'S3' : 'PDF'}</div>
          ${statusBadge}
        </div>
        <div>
          <div class="cert-card-title">${escapeHtml(cert.recipient_name)}</div>
          <div class="cert-card-course">${escapeHtml(cert.job_title)}</div>
        </div>
        <div class="cert-card-meta">
          <span>${size} ${isS3 ? '<b style="color:#FB923C;">RustFS</b>' : ''}</span>
          <span>${date}</span>
        </div>
        <div class="cert-card-actions">
          ${cert.status === 'success' ? `
            <button class="btn btn-secondary" style="flex:1; padding:8px" onclick="openPreview('${cert.id}', '${escapeAttr(cert.recipient_name)}')">
              Preview
            </button>
            <a href="${cert.presigned_url || cert.download_url}" class="btn btn-primary" style="flex:1; padding:8px; text-align:center" download>
              Download
            </a>
          ` : ''}
          <button class="btn btn-danger btn-icon" onclick="deleteCertificate('${cert.id}')">
            🗑️
          </button>
        </div>
      </div>
    `;
  }).join('');

  elements.filesContainer.innerHTML = `<div class="grid-container">${cards}</div>`;
}

function getStatusBadge(status) {
  switch (status) {
    case 'success':
      return `<span class="badge badge-success">✓ Ready</span>`;
    case 'failed':
      return `<span class="badge badge-failed">✕ Failed</span>`;
    case 'processing':
      return `<span class="badge badge-processing">⚙ Rendering</span>`;
    default:
      return `<span class="badge badge-pending">⌛ Queued</span>`;
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

// --- New Batch Modal Logic ---
function openJobModal() {
  elements.jobModal.classList.add('active');
  // Set default issue date to today's YYYY-MM-DD
  const today = new Date().toISOString().split('T')[0];
  document.getElementById('jobDate').value = today;
  resetRecipients();
  setTimeout(() => {
    const titleInput = document.getElementById('jobTitle');
    if (titleInput) titleInput.focus();
  }, 60);
}

function closeJobModal() {
  elements.jobModal.classList.remove('active');
  if (elements.btnNewBatch) elements.btnNewBatch.focus();
}

function resetRecipients() {
  elements.recipientsContainer.innerHTML = `
    <div class="recipient-entry">
      <input type="text" class="form-input recipient-name" placeholder="Recipient Full Name" required>
      <input type="email" class="form-input recipient-email" placeholder="Email (optional)">
    </div>
  `;
}

function addRecipientRow() {
  const row = document.createElement('div');
  row.className = 'recipient-entry';
  row.innerHTML = `
    <input type="text" class="form-input recipient-name" placeholder="Recipient Full Name" required>
    <input type="email" class="form-input recipient-email" placeholder="Email (optional)">
    <button type="button" class="btn btn-danger btn-icon" onclick="this.parentElement.remove()">✕</button>
  `;
  elements.recipientsContainer.appendChild(row);
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
    const res = await fetch('/api/jobs/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title,
        organization,
        date_of_issue,
        recipients,
      }),
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail ? (typeof err.detail === 'string' ? err.detail : JSON.stringify(err.detail)) : 'Submission failed');
    }

    const data = await res.json();
    showToast(`Job queued! ${recipients.length} certificates generating in background.`, 'success');
    closeJobModal();
    
    // Select newly submitted job
    state.selectedJobId = data.job_id;
    await fetchJobs();
    elements.jobFilterSelect.value = data.job_id;
    fetchCertificates();
    fetchStats();
  } catch (err) {
    showToast(`Error: ${err.message}`, 'error');
  } finally {
    elements.btnSubmitJob.disabled = false;
    elements.btnSubmitJob.textContent = 'Generate Certificates';
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
  elements.btnDownloadZip.addEventListener('click', downloadCurrentJobZip);
  elements.btnNewBatch.addEventListener('click', openJobModal);
  elements.btnCloseJobModal.addEventListener('click', closeJobModal);
  elements.btnCancelJobModal.addEventListener('click', closeJobModal);
  elements.btnAddRecipient.addEventListener('click', addRecipientRow);
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
});
