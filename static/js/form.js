/**
 * form.js — Hall Ticket Generator
 * IBM Carbon Design System UI layer
 *
 * Responsibilities
 * ────────────────
 * 1. Dynamic subject rows  (add / remove / renumber, max 7)
 * 2. Photo drag-and-drop + preview
 * 3. Client-side validation — Carbon cds-form-item--error pattern
 * 4. Build FormData (JSON string "data" + binary "photo")
 * 5. POST /generate → stream PDF back → browser download
 * 6. Carbon progress modal with timed step labels
 * 7. Auto-mirror cert name from student name
 *
 * All DOM queries are cached. Subject operations are O(N), N ≤ 7.
 */

'use strict';

/* ═══════════════════════════════════════════════════════════
   DOM CACHE
═══════════════════════════════════════════════════════════ */
const form          = document.getElementById('hall-ticket-form');
const subjectsList  = document.getElementById('subjects-list');
const addSubjectBtn = document.getElementById('add-subject-btn');
const subjectError  = document.getElementById('subject-error');
const subjectsStatus = document.getElementById('subjects-status');
const branchInput = document.getElementById('branch');
const yearInput = document.getElementById('year');
const semesterInput = document.getElementById('semester');
const regulationInput = document.getElementById('regulation');

const photoInput      = document.getElementById('photo');
const dropZone        = document.getElementById('drop-zone');
const dropPlaceholder = document.getElementById('drop-placeholder');
const photoPreview    = document.getElementById('photo-preview');
const photoNameBox    = document.getElementById('photo-name');
const photoNameText   = document.getElementById('photo-name-text');
const photoError      = document.getElementById('photo-error');

const submitBtn     = document.getElementById('submit-btn');
const submitIcon    = document.getElementById('submit-icon');
const submitSpinner = document.getElementById('submit-spinner');
const submitLabel   = document.getElementById('submit-label');

const notifyError   = document.getElementById('notify-error');
const notifyErrorTitle = document.getElementById('notify-error-title');
const notifyErrorBody  = document.getElementById('notify-error-body');
const notifySuccess    = document.getElementById('notify-success');
const notifySuccessBody = document.getElementById('notify-success-body');

const overlay       = document.getElementById('progress-overlay');
const progressBar   = document.getElementById('progress-bar');
const progressTrack = document.getElementById('progress-track');
const progressLabel = document.getElementById('progress-label');
const progressSub   = document.getElementById('progress-sub');

const MAX_SUBJECTS = 7;
let photoPreviewUrl = null;
let subjectCatalogPromise;
let subjectLoadVersion = 0;


/* ═══════════════════════════════════════════════════════════
   HELPERS — CARBON ERROR STATE
   Uses .cds-form-item--error on the wrapper to show the
   .cds-error-text sibling (CSS display:block on that class).
═══════════════════════════════════════════════════════════ */

function setFieldError(formItemId, hasError) {
  const item = document.getElementById(formItemId);
  if (!item) return;
  if (hasError) {
    item.classList.add('cds-form-item--error');
  } else {
    item.classList.remove('cds-form-item--error');
  }
}

function clearAllErrors() {
  document.querySelectorAll('.cds-form-item--error').forEach(el =>
    el.classList.remove('cds-form-item--error')
  );
  subjectError.style.display = 'none';
  photoError.style.display   = 'none';
}


/* ═══════════════════════════════════════════════════════════
   SECTION 1 — SUBJECT ROWS
═══════════════════════════════════════════════════════════ */

function subjectCount() {
  return subjectsList.querySelectorAll('.subject-row').length;
}

/** Re-number rows and update ARIA labels (O(N), N ≤ 7). */
function renumberSubjects() {
  subjectsList.querySelectorAll('.subject-row').forEach((row, i) => {
    const n   = i + 1;
    row.dataset.index = n;
    row.querySelector('.subject-row__num').textContent = n;
    const inp = row.querySelector('.subject-name');
    inp.placeholder       = `Subject ${n} name`;
    inp.setAttribute('aria-label', `Subject ${n} name`);
    const removeBtn = row.querySelector('.subject-row__remove');
    if (removeBtn) {
      removeBtn.title                     = `Remove subject ${n}`;
      removeBtn.setAttribute('aria-label', `Remove subject ${n}`);
    }
  });
}

function updateRemoveButtons() {
  const rows = subjectsList.querySelectorAll('.subject-row');
  rows.forEach(row => {
    const btn = row.querySelector('.subject-row__remove');
    if (!btn) return;
    if (rows.length > 1) btn.classList.remove('hidden');
    else                  btn.classList.add('hidden');
  });
}

function toggleAddButton() {
  const atMax = subjectCount() >= MAX_SUBJECTS;
  addSubjectBtn.disabled = atMax;
}

function attachRemoveHandler(row) {
  row.querySelector('.subject-row__remove')?.addEventListener('click', () => {
    row.remove();
    renumberSubjects();
    updateRemoveButtons();
    toggleAddButton();
  });
}

function addSubjectRow(subjectName = '', focus = true) {
  if (subjectCount() >= MAX_SUBJECTS) return;

  const idx = subjectCount() + 1;
  const row = document.createElement('div');
  row.className    = 'subject-row';
  row.dataset.index = idx;
  row.setAttribute('role', 'listitem');

  row.innerHTML = `
    <span class="subject-row__num" aria-hidden="true">${idx}</span>
    <input type="text"
           class="cds-input subject-name"
           placeholder="Subject ${idx} name"
           aria-label="Subject ${idx} name"
           maxlength="120" />
    <button type="button"
            class="subject-row__remove"
            title="Remove subject ${idx}"
            aria-label="Remove subject ${idx}">
      <svg viewBox="0 0 32 32" fill="currentColor" aria-hidden="true">
        <path d="M24 9.4L22.6 8 16 14.6 9.4 8 8 9.4 14.6 16 8 22.6 9.4 24 16 17.4 22.6 24 24 22.6 17.4 16 24 9.4z"/>
      </svg>
    </button>
  `;

  attachRemoveHandler(row);
  subjectsList.appendChild(row);
  row.querySelector('.subject-name').value = subjectName;
  updateRemoveButtons();
  toggleAddButton();
  if (focus) row.querySelector('.subject-name').focus();
}

function setSubjectRows(names) {
  subjectsList.replaceChildren();
  const subjectNames = names.slice(0, MAX_SUBJECTS);
  if (subjectNames.length === 0) subjectNames.push('');
  subjectNames.forEach(name => addSubjectRow(name, false));
}

async function loadSubjectCatalog() {
  subjectCatalogPromise ??= fetch('/static/data/subjects.json').then(response => {
    if (!response.ok) throw new Error('Subject catalogue could not be loaded.');
    return response.json();
  });
  return subjectCatalogPromise;
}

async function loadRegulationsForSelection() {
  const loadVersion = ++subjectLoadVersion;
  const branch = branchInput.value;
  const year = yearInput.value;
  const semester = semesterInput.value;
  regulationInput.disabled = true;
  setSubjectRows([]);

  if (!branch || !year || !semester) {
    regulationInput.replaceChildren(new Option('Select branch, year, and semester first', ''));
    subjectsStatus.textContent = 'Select a branch, year, and semester to load saved subjects.';
    return;
  }

  regulationInput.replaceChildren(new Option('Loading regulations…', ''));
  subjectsStatus.textContent = 'Loading regulations…';
  try {
    const catalog = await loadSubjectCatalog();
    if (loadVersion !== subjectLoadVersion) return;

    const matchingCurricula = catalog.curricula.filter(item =>
      item.branch === branch && item.year === year && item.semester === semester
    );
    const regulations = [...new Set(matchingCurricula
      .map(item => item.regulation)
      .filter(value => typeof value === 'string' && value.trim()))];

    regulationInput.replaceChildren(new Option('Select a regulation', ''));
    regulations.forEach(value => regulationInput.add(new Option(value, value)));
    regulationInput.add(new Option('Not listed (manual entry)', 'manual'));
    regulationInput.disabled = false;

    if (regulations.length === 1) {
      regulationInput.value = regulations[0];
      await loadSubjectsForSelection();
    } else if (regulations.length > 1) {
      subjectsStatus.textContent = 'Select a regulation to load its saved subjects.';
    } else {
      regulationInput.value = 'manual';
      setSubjectRows([]);
      subjectsStatus.textContent = 'No saved regulations for this combination. Add subjects manually.';
    }
  } catch (error) {
    if (loadVersion !== subjectLoadVersion) return;
    subjectCatalogPromise = null;
    regulationInput.replaceChildren(new Option('Not listed (manual entry)', 'manual'));
    regulationInput.disabled = false;
    regulationInput.value = 'manual';
    setSubjectRows([]);
    subjectsStatus.textContent = 'Could not load saved subjects. Add subjects manually.';
    console.error('[HallTicket] Subject catalogue error:', error);
  }
}

async function loadSubjectsForSelection() {
  const loadVersion = ++subjectLoadVersion;
  const { value: branch } = branchInput;
  const { value: year } = yearInput;
  const { value: semester } = semesterInput;
  const { value: regulation } = regulationInput;

  if (!branch || !year || !semester || !regulation) return;
  if (regulation === 'manual') {
    setSubjectRows([]);
    subjectsStatus.textContent = 'Manual entry selected. Add or edit subjects below.';
    return;
  }

  subjectsStatus.textContent = 'Loading subjects…';
  try {
    const catalog = await loadSubjectCatalog();
    if (loadVersion !== subjectLoadVersion) return;
    const entries = catalog.curricula.filter(item =>
      item.branch === branch && item.year === year && item.semester === semester &&
      item.regulation === regulation
    );
    const names = [...new Set(entries.flatMap(entry =>
      Array.isArray(entry.subjects)
        ? entry.subjects.filter(name => typeof name === 'string' && name.trim())
        : []
    ))];
    setSubjectRows(names.slice(0, MAX_SUBJECTS));
    subjectsStatus.textContent = names.length > MAX_SUBJECTS
      ? `Loaded ${MAX_SUBJECTS} of ${names.length} subjects. The ticket supports up to ${MAX_SUBJECTS}.`
      : names.length
        ? `Loaded ${names.length} suggested subjects. You can edit or remove them.`
      : 'No saved subjects for this combination. Add subjects manually.';
  } catch (error) {
    if (loadVersion !== subjectLoadVersion) return;
    subjectCatalogPromise = null;
    setSubjectRows([]);
    subjectsStatus.textContent = 'Could not load saved subjects. Add subjects manually.';
    console.error('[HallTicket] Subject catalogue error:', error);
  }
}

// Wire first row's remove button
attachRemoveHandler(subjectsList.querySelector('.subject-row'));
addSubjectBtn.addEventListener('click', addSubjectRow);
[branchInput, yearInput, semesterInput].forEach(select =>
  select.addEventListener('change', loadRegulationsForSelection)
);
regulationInput.addEventListener('change', loadSubjectsForSelection);


/* ═══════════════════════════════════════════════════════════
   SECTION 2 — PHOTO UPLOAD & PREVIEW
═══════════════════════════════════════════════════════════ */

function showPhotoPreview(file) {
  if (!file || !file.type.startsWith('image/')) return;

  if (photoPreviewUrl) URL.revokeObjectURL(photoPreviewUrl);
  photoPreviewUrl = URL.createObjectURL(file);
  photoPreview.src       = photoPreviewUrl;
  photoPreview.style.display = 'block';
  dropPlaceholder.style.display = 'none';
  dropZone.classList.add('cds-file-drop--preview');

  photoNameText.textContent = `${file.name}  (${(file.size / 1024).toFixed(0)} KB)`;
  photoNameBox.style.display = 'flex';
  photoError.style.display   = 'none';
}

window.addEventListener('pagehide', () => {
  if (photoPreviewUrl) URL.revokeObjectURL(photoPreviewUrl);
});

photoInput.addEventListener('change', () => {
  if (photoInput.files[0]) showPhotoPreview(photoInput.files[0]);
});

// Drag-and-drop
dropZone.addEventListener('dragover', e => {
  e.preventDefault();
  dropZone.classList.add('drag-over');
});
['dragleave', 'dragend'].forEach(evt =>
  dropZone.addEventListener(evt, () => dropZone.classList.remove('drag-over'))
);
dropZone.addEventListener('drop', e => {
  e.preventDefault();
  dropZone.classList.remove('drag-over');
  const file = e.dataTransfer?.files[0];
  if (file) {
    const dt = new DataTransfer();
    dt.items.add(file);
    photoInput.files = dt.files;
    showPhotoPreview(file);
  }
});


/* ═══════════════════════════════════════════════════════════
   SECTION 3 — VALIDATION
   Carbon pattern: add .cds-form-item--error to the wrapper.
   CSS shows the .cds-error-text child automatically.
═══════════════════════════════════════════════════════════ */

/** Map: formItemId → { inputId, errorId, errorMsg, validate? } */
const FIELDS = [
  { wrap: 'fi-student-name',  input: 'student_name', msg: 'Full name is required.' },
  { wrap: 'fi-father-name',   input: 'father_name',  msg: "Father's name is required." },
  {
    wrap: 'fi-hall-ticket', input: 'hall_ticket',
    msg: 'Enter a valid 1–10 alphanumeric hall ticket number.',
    validate: v => /^[A-Za-z0-9]{1,10}$/.test(v),
  },
  { wrap: 'fi-student-type',  input: 'student_type', msg: 'Please select an exam type.' },
  { wrap: 'fi-branch',        input: 'branch',       msg: 'Please select a branch.' },
  { wrap: 'fi-year',          input: 'year',         msg: 'Please select a year.' },
  { wrap: 'fi-semester',      input: 'semester',     msg: 'Please select a semester.' },
  { wrap: 'fi-regulation',   input: 'regulation',   msg: 'Please select a regulation.' },
  { wrap: 'fi-month-year',    input: 'month_year',   msg: 'Examination month and year is required.' },
  { wrap: 'fi-cert-name',     input: 'cert_name',    msg: 'Certificate name is required.' },
  { wrap: 'fi-cert-date',     input: 'cert_date',    msg: 'Academic year is required.' },
];

function validateForm() {
  clearAllErrors();
  const errors = [];

  for (const f of FIELDS) {
    const el  = document.getElementById(f.input);
    const val = el?.value.trim() ?? '';

    const empty   = val === '';
    const invalid = f.validate ? !f.validate(val) : false;

    if (empty || invalid) {
      setFieldError(f.wrap, true);
      errors.push(f.msg);
    }
  }

  // Subjects
  const filledSubjects = [...subjectsList.querySelectorAll('.subject-name')]
    .filter(s => s.value.trim());
  if (filledSubjects.length === 0) {
    subjectError.style.display = 'block';
    errors.push('At least one subject name is required.');
  }

  // Photo
  if (!photoInput.files[0]) {
    photoError.style.display = 'block';
    errors.push('A student photograph is required.');
  }

  return { valid: errors.length === 0, errors };
}


/* ═══════════════════════════════════════════════════════════
   SECTION 4 — CARBON NOTIFICATIONS
═══════════════════════════════════════════════════════════ */

function showNotification(type, message, title = null) {
  // Hide both first
  notifyError.classList.remove('is-visible');
  notifySuccess.classList.remove('is-visible');

  if (type === 'error') {
    notifyErrorTitle.textContent = title || 'Validation error';
    notifyErrorBody.innerHTML    = message;
    notifyError.classList.add('is-visible');
    notifyError.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  } else {
    notifySuccessBody.innerHTML = message;
    notifySuccess.classList.add('is-visible');
    notifySuccess.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }
}

function clearNotifications() {
  notifyError.classList.remove('is-visible');
  notifySuccess.classList.remove('is-visible');
}


/* ═══════════════════════════════════════════════════════════
   SECTION 5 — PROGRESS MODAL
═══════════════════════════════════════════════════════════ */

const STEPS = [
  { pct: 10, label: 'Uploading data…',              sub: 'Sending your information to the server.' },
  { pct: 30, label: 'Removing background…',          sub: 'AI model is isolating the subject from the photo.' },
  { pct: 60, label: 'Still removing background…',    sub: 'The first run may take longer while the model initializes.' },
  { pct: 82, label: 'Generating PDF…',               sub: 'Filling template.pdf with your details.' },
  { pct: 95, label: 'Finalising document…',          sub: 'Almost there!' },
];

let stepTimers = [];

function showOverlay() {
  overlay.classList.add('is-visible');
  overlay.style.display = 'flex';
  progressBar.style.width = '0%';
  progressTrack?.setAttribute('aria-valuenow', '0');
  progressLabel.textContent = 'Starting…';
  progressSub.textContent   = 'Preparing your request…';

  const delays = [600, 3500, 13000, 23000, 32000];
  STEPS.forEach((step, i) => {
    const t = setTimeout(() => {
      progressBar.style.width = step.pct + '%';
      progressTrack?.setAttribute('aria-valuenow', String(step.pct));
      progressLabel.textContent = step.label;
      progressSub.textContent   = step.sub;
    }, delays[i]);
    stepTimers.push(t);
  });
}

function hideOverlay(success = true) {
  stepTimers.forEach(clearTimeout);
  stepTimers = [];

  if (success) {
    progressBar.style.width = '100%';
    progressTrack?.setAttribute('aria-valuenow', '100');
    progressLabel.textContent = 'Done! Downloading your PDF…';
    progressSub.textContent   = '';
  }

  setTimeout(() => {
    overlay.style.display = 'none';
    overlay.classList.remove('is-visible');
  }, success ? 1400 : 0);
}


/* ═══════════════════════════════════════════════════════════
   SECTION 6 — PAYLOAD BUILDER
═══════════════════════════════════════════════════════════ */

function buildPayload() {
  const subjects = [...subjectsList.querySelectorAll('.subject-name')]
    .map((el, i) => ({ number: i + 1, name: el.value.trim() }))
    .filter(s => s.name);

  return {
    student: {
      name:        document.getElementById('student_name').value.trim(),
      father_name: document.getElementById('father_name').value.trim(),
      hall_ticket: document.getElementById('hall_ticket').value.trim().toUpperCase(),
      type:        document.getElementById('student_type').value,
    },
    academic: {
      branch:   document.getElementById('branch').value,
      year:     document.getElementById('year').value,
      semester: document.getElementById('semester').value,
    },
    examination: {
      month_year: document.getElementById('month_year').value.trim(),
    },
    subjects,
    certificate: {
      name: document.getElementById('cert_name').value.trim(),
      date: document.getElementById('cert_date').value.trim(),
    },
  };
}


/* ═══════════════════════════════════════════════════════════
   SECTION 7 — SUBMIT HANDLER
═══════════════════════════════════════════════════════════ */

function setLoading(loading) {
  submitBtn.disabled             = loading;
  submitIcon.style.display       = loading ? 'none'  : 'block';
  submitSpinner.style.display    = loading ? 'block' : 'none';
  submitLabel.textContent        = loading ? 'Generating…' : 'Generate hall ticket';
  submitBtn.setAttribute('aria-busy', String(loading));
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a   = document.createElement('a');
  a.href     = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

form.addEventListener('submit', async e => {
  e.preventDefault();
  clearNotifications();

  const { valid, errors } = validateForm();
  if (!valid) {
    showNotification('error', errors[0]);
    // Scroll to first errored field
    const firstErr = document.querySelector('.cds-form-item--error .cds-input, .cds-form-item--error .cds-select');
    firstErr?.focus();
    return;
  }

  const payload  = buildPayload();
  const formData = new FormData();
  formData.append('data',  JSON.stringify(payload));
  formData.append('photo', photoInput.files[0]);

  setLoading(true);
  showOverlay();

  try {
    const response = await fetch('/generate', {
      method: 'POST',
      body:   formData,
      // Browser sets Content-Type with correct boundary automatically
    });

    if (!response.ok) {
      let detail = `Server error (${response.status})`;
      try {
        const err = await response.json();
        detail    = err.detail ?? detail;
      } catch (_) { /* keep default */ }
      throw new Error(detail);
    }

    const blob    = await response.blob();
    const cd      = response.headers.get('Content-Disposition') ?? '';
    const match   = cd.match(/filename="?([^"]+)"?/);
    const filename = match ? match[1] : `hallticket_${payload.student.hall_ticket}.pdf`;

    hideOverlay(true);
    downloadBlob(blob, filename);

    showNotification(
      'success',
      `Hall ticket generated successfully. Downloading <strong>${filename}</strong>.`,
      'Success'
    );

  } catch (err) {
    hideOverlay(false);
    showNotification('error', `Generation failed: ${err.message}`, 'Error');
    console.error('[HallTicket] Error:', err);

  } finally {
    setLoading(false);
  }
});


/* ═══════════════════════════════════════════════════════════
   SECTION 8 — AUTO-FILL CERT NAME FROM STUDENT NAME
═══════════════════════════════════════════════════════════ */
document.getElementById('student_name').addEventListener('input', function () {
  const certName = document.getElementById('cert_name');
  if (!certName.dataset.touched) {
    certName.value = this.value;
  }
});
document.getElementById('cert_name').addEventListener('input', function () {
  this.dataset.touched = '1';
});


/* ═══════════════════════════════════════════════════════════
   SECTION 9 — LIVE FIELD VALIDATION (clear error on input)
═══════════════════════════════════════════════════════════ */
FIELDS.forEach(f => {
  document.getElementById(f.input)?.addEventListener('input', () => {
    setFieldError(f.wrap, false);
  });
  document.getElementById(f.input)?.addEventListener('change', () => {
    setFieldError(f.wrap, false);
  });
});
