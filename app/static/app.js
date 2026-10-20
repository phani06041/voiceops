let loadedCases=[],selected=null,lastAnswer='';const $=id=>document.getElementById(id);const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
// Pagination state
let currentPage = 1;
const casesPerPage = 6;
let filteredCases = [];

async function api(url,opts={}) {
    const headers = {...(opts.headers||{})};
    if(!(opts.body instanceof FormData) && opts.body!==undefined && !headers['Content-Type']) {
        headers['Content-Type'] = 'application/json';
    }

    try {
        const r = await fetch(url, {...opts, headers});
        let data;
        const contentType = r.headers.get('content-type') || '';
        if (contentType.includes('application/json')) {
            data = await r.json();
        } else {
            data = await r.blob();
        }

        if (!r.ok) {
            // Try to get error message from response
            let errorMessage = 'Request failed';
            if (data && typeof data === 'object' && data.detail) {
                errorMessage = data.detail;
            } else if (typeof data === 'string') {
                errorMessage = data;
            }
            throw new Error(errorMessage);
        }
        return data;
    } catch (error) {
        // Re-throw to be caught by caller
        throw error;
    }
}

function showLoading(button, isLoading) {
    if (isLoading) {
        button.disabled = true;
        button.originalText = button.textContent;
        button.innerHTML = '<span class="spinner"></span> Processing...';
    } else {
        button.disabled = false;
        if (button.originalText) {
            button.textContent = button.originalText;
        }
    }
}

function showError(element, message) {
    // Remove any existing error
    const existingError = element.parentElement.querySelector('.error-message');
    if (existingError) {
        existingError.remove();
    }

    if (message) {
        const errorDiv = document.createElement('div');
        errorDiv.className = 'error-message';
        errorDiv.style.color = 'var(--danger-color)';
        errorDiv.style.fontSize = '0.875rem';
        errorDiv.style.marginTop = '0.5rem';
        errorDiv.textContent = message;
        element.parentElement.appendChild(errorDiv);
    }
}

function clearError(element) {
    const error = element.parentElement.querySelector('.error-message');
    if (error) {
        error.remove();
    }
}

async function init() {
    try {
        const [s, c] = await Promise.all([
            api('/stats'),
            api('/cases?limit=500')
        ]);

        $('stats').innerHTML = [
            ['All cases', s.total_cases],
            ['Healthcare', s.healthcare_cases],
            ['Mortgage', s.mortgage_cases],
            ['Needs review', s.manual_review_cases],
            ['Resolved', s.resolved_cases]
        ].map(([l, v]) => `
            <div class="stat">
                <div class="label">${l}</div>
                <div class="value">${v}</div>
            </div>
        `).join('');

        // Ensure loadedCases is an array
        loadedCases = [];
        if (c && c.items && Array.isArray(c.items)) {
            loadedCases = c.items;
        }
        // Reset filters to show all cases by default
        $('domain').value = '';
        $('review').value = '';
        $('search').value = '';
        // Reset pagination
        currentPage = 1;
        renderRows();

        // Update voice status indicator
        const voiceStatusIndicator = $('voiceStatusIndicator');
        if (s.voice_configured) {
            voiceStatusIndicator.innerHTML = '<span class="status-dot"></span> System Ready';
            voiceStatusIndicator.style.backgroundColor = 'rgba(16, 185, 129, 0.2)';
            voiceStatusIndicator.querySelector('.status-dot').style.backgroundColor = 'var(--success-color)';
        } else {
            voiceStatusIndicator.innerHTML = '<span class="status-dot"></span> Voice Not Configured';
            voiceStatusIndicator.style.backgroundColor = 'rgba(239, 68, 68, 0.2)';
            voiceStatusIndicator.querySelector('.status-dot').style.backgroundColor = 'var(--danger-color)';
        }
    } catch (e) {
        $('rows').innerHTML = `<tr><td colspan="6">${esc(e.message)}</tr>`;
        console.error('Initialization error:', e);
    }
}

function formatStatus(status) {
    const s = String(status || '').toLowerCase().replace(/ /g, '_');
    const map = {
        'new': '<span class="tag info">New</span>',
        'open': '<span class="tag info">Open</span>',
        'in_review': '<span class="tag warn">In Review</span>',
        'pending_document': '<span class="tag auto-reviewed">Pending Doc</span>',
        'pending_specialist': '<span class="tag warn">Specialist</span>',
        'resolved': '<span class="tag success">Resolved</span>',
        'closed': '<span class="tag danger">Closed</span>'
    };
    return map[s] || `<span class="tag">${esc(status)}</span>`;
}

function formatAction(action) {
    if (!action) return '—';
    const a = String(action).toLowerCase().replace(/ /g, '_');
    const map = {
        'request_missing_document': 'Request Missing Document',
        'propose_field_correction': 'Propose Field Correction',
        'route_to_specialist': 'Route to Specialist',
        'await_document_submission': 'Await Document Submission',
        'abstain': 'Abstain (Escalate)',
        'close_case': 'Close Case',
        'archived': 'Archived'
    };
    return map[a] || action.replace(/_/g, ' ');
}

function formatReviewQueueStatus(processing) {
    const rq = processing?.review_queue_status;
    if (rq === 'Review Needed') {
        return '<span class="tag warn">Review Needed</span>';
    } else if (rq === 'Resolved' || rq === 'Reviewed') {
        return '<span class="tag success">Resolved</span>';
    } else if (rq === 'Awaiting Doc') {
        return '<span class="tag auto-reviewed">Awaiting Doc</span>';
    } else if (rq === 'Closed') {
        return '<span class="tag danger">Closed</span>';
    } else if (rq === 'Automated') {
        return '<span class="tag" style="background-color:#e5e7eb;color:#374151">Automated</span>';
    }
    return processing?.manual_review_required ? '<span class="tag warn">Review Needed</span>' : '<span class="tag" style="background-color:#e5e7eb;color:#374151">—</span>';
}

function renderRows() {
    const domain = $('domain').value;
    const review = $('review').value;
    const term = $('search').value.toLowerCase();

    // Filter cases based on domain, review status, and search term
    filteredCases = loadedCases.filter(function(c) {
        if (domain && c.domain !== domain) {
            return false;
        }
        if (review !== '' && String(c.processing?.manual_review_required) !== review) {
            return false;
        }
        if (term && !(c.case_id + ' ' + c.exception_text).toLowerCase().includes(term)) {
            return false;
        }
        return true;
    });

    // Calculate pagination
    const totalPages = Math.max(1, Math.ceil(filteredCases.length / casesPerPage));
    if (currentPage > totalPages) {
        currentPage = totalPages;
    }
    if (currentPage < 1) {
        currentPage = 1;
    }

    // Get cases for current page
    const startIndex = (currentPage - 1) * casesPerPage;
    const endIndex = startIndex + casesPerPage;
    const paginatedCases = filteredCases.slice(startIndex, endIndex);

    // Render table rows
    $('rows').innerHTML = paginatedCases.map(c => {
        const isSel = selected && c.case_id === selected.case_id;
        return `
        <tr data-id="${esc(c.case_id)}" class="${isSel ? 'selected' : ''}">
            <td>
                <div class="caseid-wrapper">
                    ${isSel ? '<span class="selected-indicator-dot" title="Active Case"></span>' : '<span class="selected-indicator-placeholder"></span>'}
                    <span class="caseid">${esc(c.case_id)}</span>
                </div>
            </td>
            <td><span class="tag">${esc(c.domain)}</span></td>
            <td>${esc(c.exception_text)}</td>
            <td>${formatStatus(c.status)}</td>
            <td>${esc(formatAction(c.processing?.recommended_action))}</td>
            <td>${formatReviewQueueStatus(c.processing)}</td>
        </tr>
    `;
    }).join('') || '<tr><td colspan="6">No matching cases.</td></tr>';

    // Render pagination controls
    renderPaginationControls(totalPages);

    // Add click handlers to rows
    document.querySelectorAll('#rows tr[data-id]').forEach(tr => {
        tr.onclick = () => openCase(tr.dataset.id);
        // Highlight selected row
        if (selected && tr.dataset.id === selected.case_id) {
            tr.classList.add('selected');
        } else {
            tr.classList.remove('selected');
        }
    });
}

async function openCase(id) {
    try {
        const sourceRow = document.querySelector(`#rows tr[data-id="${id}"]`);
        selected = await api('/cases/' + encodeURIComponent(id));
        updateSelectedCaseBanner(selected, sourceRow);

        const detailPanel = $('detail');
        if (detailPanel) {
            detailPanel.classList.add('is-active-case');
        }

        // Initialize flags if not present

        $('detail').innerHTML = `
            <div class="panel-header">
                <h2>
                    ${esc(selected.case_id)}
                    <span class="tag">${esc(selected.domain)}</span>
                    <span class="active-case-badge"><span class="pulse-dot"></span> Active Case</span>
                </h2>
            </div>
            <div class="panel-content">
                <div class="eyebrow" style="color:#387a67">CASE DETAILS</div>
                <h2>${esc(selected.case_id)} <span class="tag">${esc(selected.domain)}</span></h2>
                <p>${esc(selected.exception_text)}</p>
                <div class="detailgrid">
                    <div class="field">
                        <div class="field-label">Exception type</div>
                        <div>${esc(selected.processing?.exception_type)}</div>
                    </div>
                    <div class="field">
                        <div class="field-label">Recommended action</div>
                        <div>${esc(selected.processing?.recommended_action)}</div>
                    </div>
                    <div class="field">
                        <div class="field-label">Status</div>
                        <div id="detailStatusDisplay">${formatStatus(selected.status)}</div>
                    </div>
                    <div class="field">
                        <div class="field-label">Authorization type</div>
                        <div>${esc(selected.domain === 'healthcare' ? selected.authorization_type : 'Not applicable')}</div>
                    </div>
                    <div class="field">
                        <div class="field-label">Confidence (heuristic)</div>
                        <div>${Math.round((selected.confidence_score ?? 0) * 100)}% — not a calibrated probability</div>
                    </div>
                    <div class="field">
                        <div class="field-label">Human review</div>
                        <div id="detailReviewDisplay">${formatReviewQueueStatus(selected.processing)}</div>
                    </div>
                </div>
                <h3>Missing fields / documents</h3>
                <p class="muted">${esc((selected.missing_fields || []).join(', ')||'No structured missing-field list recorded.')}</p>
                <h3>Supporting evidence</h3>
                <ul class="evidence">${(selected.processing?.supporting_evidence || []).map(x=>`<li>${esc(x)}</li>`).join('')||'<li>No evidence supplied.</li>'}</ul>
                <h3>Reviewer notes</h3>
                <div class="note-section">
                    <ul class="evidence">
                        ${(selected.reviewer_notes||[]).map(n=>`<li>${esc(n.note)} <span class="muted">${esc(n.created_at)}</span></li>`).join('')||'<li>None yet.</li>'}
                    </ul>
                    <div class="noteform">
                        <label for="noteInput">Reviewer Note</label>
                        <input id="noteInput" placeholder="Add reviewer note">
                        <button id="saveNote" class="button-primary">Save note</button>
                    </div>
                </div>
                <div class="statusform">
                    <label for="newStatus">New Status</label>
                    <select id="newStatus">
                        <option value="in_review">In Review</option>
                        <option value="pending_document">Pending Document</option>
                        <option value="pending_specialist">Pending Specialist</option>
                        <option value="resolved">Resolved</option>
                        <option value="open">Open</option>
                        <option value="closed">Closed</option>
                    </select>
                    <label for="statusReason">Reason for Change</label>
                    <input id="statusReason" placeholder="Reason for status change"/>
                    <button id="saveStatus" class="button-primary">Update status</button>
                </div>
            </div>
        `;

        // Set the status dropdown to show the current status
        const statusSelect = document.getElementById('newStatus');
        if (statusSelect) {
            statusSelect.value = selected.status;
        }

        if (detailPanel) {
            const existingIndicator = detailPanel.querySelector('.case-selector-indicator');
            if (existingIndicator) {
                existingIndicator.remove();
            }
        }

        // Reattach event listeners for the newly created elements
        $('saveNote').onclick = async () => {
            const noteInput = $('noteInput');
            const note = noteInput.value.trim();

            // Save form state to preserve after re-render
            const savedStatusSelect = $('newStatus').value;
            const savedStatusReason = $('statusReason').value;
            const savedQuestion = $('question').value;

            // Clear previous errors
            clearError(noteInput);

            // Validate input
            if (!note) {
                showError(noteInput, 'Please enter a note');
                return;
            }

            showLoading($('saveNote'), true);
            try {
                await api(`/cases/${encodeURIComponent(id)}/notes`, {
                    method: 'POST',
                    body: JSON.stringify({ note })
                });
                noteInput.value = '';
                clearError(noteInput);

                // Create a new note object (we don't have the timestamp from the server, so we'll use client-side for now)
                const newNote = {
                    note: note,
                    created_at: new Date().toISOString()
                };

                // Add the new note to the beginning of the reviewer_notes array
                selected.reviewer_notes = [newNote, ...(selected.reviewer_notes || [])];

                // Update review queue status to Reviewed because the auditor added a note
                if (selected.processing) {
                    selected.processing.review_queue_status = 'Reviewed';
                }

                // Update the UI: we will add a new list item to the notes list
                const notesListElement = document.querySelector('.note-section ul.evidence');
                if (notesListElement) {
                    const newItem = document.createElement('li');
                    newItem.innerHTML = `${esc(note)} <span class="muted">${esc(new Date().toLocaleString())}</span>`;
                    notesListElement.prepend(newItem);
                } else {
                    // If we can't find the list, we fall back to re-rendering the note section
                    // But we want to preserve the form state, so we will re-render the case details after saving the form state
                    await openCase(id);
                    // After re-rendering, restore the form state (except noteInput which we cleared)
                    $('newStatus').value = savedStatusSelect;
                    $('statusReason').value = savedStatusReason;
                    $('question').value = savedQuestion;
                    return; // Exit early to avoid double restoration
                }
            } catch (e) {
                showError(noteInput, e.message || 'Failed to save note');
                console.error('Note save error:', e);
            } finally {
                showLoading($('saveNote'), false);
            }

            // Restore form state after successful note save (if we didn't take the fallback above)
            $('newStatus').value = savedStatusSelect;
            $('statusReason').value = savedStatusReason;
            $('question').value = savedQuestion;

            // Update the case in loadedCases and re-render the queue to show the updated review status
            const caseIndex = loadedCases.findIndex(c => c.case_id === id);
            if (caseIndex !== -1) {
                loadedCases[caseIndex] = { ...loadedCases[caseIndex], ...selected };
                renderRows();
                updateSelectedCaseBanner(selected);
            }
        };

        $('saveStatus').onclick = async () => {
            const statusSelect = $('newStatus');
            const reasonInput = $('statusReason');
            const status = statusSelect.value;
            const reason = reasonInput.value.trim();

            // Save form state to preserve after re-render
            const savedNoteInput = $('noteInput').value;
            const savedQuestion = $('question').value;

            // Clear previous errors
            clearError(statusSelect);
            clearError(reasonInput);

            // Validate input
            let isValid = true;
            if (!status) {
                showError(statusSelect, 'Please select a status');
                isValid = false;
            }

            if (!reason) {
                showError(reasonInput, 'Please provide a reason for the status change');
                isValid = false;
            } else if (reason.length < 2) {
                showError(reasonInput, 'Reason must be at least 2 characters long');
                isValid = false;
            }

            if (!isValid) {
                return;
            }

            showLoading($('saveStatus'), true);
            try {
                await api(`/cases/${encodeURIComponent(id)}/status`, {
                    method: 'POST',
                    body: JSON.stringify({ status, reason })
                });
                reasonInput.value = '';
                clearError(reasonInput);
                // We do not clear the statusSelect; we leave it as the selected status.

                // Update the selected case object with the new status
                selected.status = status;

                // Update review queue status to Reviewed because the auditor updated the status
                if (selected.processing) {
                    selected.processing.review_queue_status = 'Reviewed';
                }

                // Update the status display in the case details
                const statusDisplay = $('detailStatusDisplay');
                if (statusDisplay) {
                    statusDisplay.innerHTML = formatStatus(status);
                }

                // Update the human review display in the case details
                const humanReviewDisplay = $('detailReviewDisplay');
                if (humanReviewDisplay) {
                    humanReviewDisplay.innerHTML = formatReviewQueueStatus(selected.processing);
                }

                // Now, we need to update the case in the loadedCases array so that the queue reflects the changes.
                // We will find the case in loadedCases by case_id and update it.
                const caseIndex = loadedCases.findIndex(c => c.case_id === id);
                if (caseIndex !== -1) {
                    loadedCases[caseIndex] = { ...loadedCases[caseIndex], ...selected };
                    renderRows();
                    updateSelectedCaseBanner(selected);
                } else {
                    // If we can't find it, we fall back to calling init() to reload from the server.
                    await init();
                }

            } catch (e) {
                showError(statusSelect, e.message || 'Failed to update status');
                console.error('Status update error:', e);
            } finally {
                showLoading($('saveStatus'), false);
            }

            // Restore form state after successful status save
            $('noteInput').value = savedNoteInput;
            $('question').value = savedQuestion;
        };

        $('question').placeholder = `Ask about ${id}…`;
        $('question').value = 'What is missing, and what should happen next?';
        $('speak').disabled = !lastAnswer;

        // Add selected class to the row in the table and update indicators
        const rows = document.querySelectorAll('#rows tr[data-id]');
        rows.forEach(tr => {
            const isTarget = tr.dataset.id === id;
            if (isTarget) {
                tr.classList.add('selected');
            } else {
                tr.classList.remove('selected');
            }
            const wrapper = tr.querySelector('.caseid-wrapper');
            if (wrapper) {
                const existingDot = wrapper.querySelector('.selected-indicator-dot');
                const existingPlaceholder = wrapper.querySelector('.selected-indicator-placeholder');
                if (isTarget) {
                    if (existingPlaceholder) {
                        existingPlaceholder.className = 'selected-indicator-dot';
                        existingPlaceholder.title = 'Active Case';
                    } else if (!existingDot) {
                        wrapper.insertAdjacentHTML('afterbegin', '<span class="selected-indicator-dot" title="Active Case"></span>');
                    }
                } else {
                    if (existingDot) {
                        existingDot.className = 'selected-indicator-placeholder';
                        existingDot.removeAttribute('title');
                    }
                }
            }
        });

        // Scroll case details panel into view
        if (detailPanel) {
            detailPanel.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }

        // Ensure selected row is visible within table wrap
        const tableWrap = document.querySelector('.tablewrap');
        const selectedRow = document.querySelector(`#rows tr[data-id="${id}"]`);
        if (tableWrap && selectedRow) {
            tableWrap.scrollTop = selectedRow.offsetTop - tableWrap.clientTop;
        }
    } catch (e) {
        $('detail').innerHTML = `<p>${esc(e.message)}</p>`;
        console.error('Error loading case:', e);
    }
}

// Inline microphone for the Ask VoiceOps question field. It records, sends audio to SLNG Nova 3,
// and inserts the transcript into the question box without submitting it automatically.
let questionRecorder=null,questionChunks=[],questionStream=null,questionMicBusy=false;
$('questionMic').onclick=async()=>{
  const button=$('questionMic'),status=$('questionMicStatus');
  if(questionRecorder&&questionRecorder.state==='recording'){
    button.disabled=true;button.textContent='Transcribing…';status.textContent='Finishing recording and sending it to SLNG Nova 3…';questionRecorder.stop();return;
  }
  if(questionMicBusy)return;
  try{
    if(!navigator.mediaDevices?.getUserMedia||!window.MediaRecorder)throw new Error('Microphone recording is not supported in this browser. Use a recent Chrome browser on localhost.');
    questionStream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true}});
    questionChunks=[];
    const mime=['audio/webm;codecs=opus','audio/webm','audio/mp4'].find(t=>MediaRecorder.isTypeSupported(t));
    questionRecorder=new MediaRecorder(questionStream,mime?{mimeType:mime}:undefined);
    questionRecorder.ondataavailable=e=>{if(e.data.size)questionChunks.push(e.data)};
    questionRecorder.onerror=()=>{status.textContent='Recording failed. Please try again.';resetQuestionMic()};
    questionRecorder.onstop=async()=>{
      const blob=new Blob(questionChunks,{type:questionRecorder?.mimeType||'audio/webm'});
      questionStream?.getTracks().forEach(t=>t.stop());questionStream=null;
      if(!blob.size){status.textContent='No audio was captured. Please try again.';resetQuestionMic();return;}
      questionMicBusy=true;
      try{
        status.textContent='Transcribing your question with SLNG Nova 3…';
        const form=new FormData();const ext=blob.type.includes('mp4')?'m4a':'webm';form.append('audio',blob,`voice-question.${ext}`);
        const result=await api('/voice/transcribe',{method:'POST',body:form});
        const transcript=(result.transcript||'').trim();
        if(!transcript)throw new Error('No speech was recognized. Please try again.');
        $('question').value=transcript;$('question').focus();
        status.textContent='Question captured. Review it, then select Ask.';
      }catch(e){status.textContent=`Could not transcribe question: ${e.message}`}
      finally{questionMicBusy=false;resetQuestionMic()}
    };
    questionRecorder.start(250);button.textContent='⏹ Stop & transcribe';button.classList.add('recording');button.setAttribute('aria-label','Stop recording and transcribe');status.textContent='Listening… ask your question, then press Stop & transcribe.';
  }catch(e){status.textContent=e.message;questionStream?.getTracks().forEach(t=>t.stop());questionStream=null;resetQuestionMic()}
};

function resetQuestionMic(){const button=$('questionMic');button.disabled=false;button.textContent='🎙 Speak question';button.classList.remove('recording');button.setAttribute('aria-label','Speak your question');}

// ==========================================================================
// Floating Transparent Pop-Out Banner for Selected Case
// ==========================================================================
let isBannerDismissed = false;

function animateRowPopOut(sourceTr, onComplete) {
    if (!sourceTr) {
        if (onComplete) onComplete();
        return;
    }

    try {
        const rect = sourceTr.getBoundingClientRect();
        const ghost = document.createElement('div');
        ghost.className = 'popout-row-ghost';
        ghost.style.top = `${rect.top}px`;
        ghost.style.left = `${rect.left}px`;
        ghost.style.width = `${rect.width}px`;
        ghost.style.height = `${rect.height}px`;

        // Clone the row content inside a flexible container
        ghost.innerHTML = `
            <div style="display: flex; align-items: center; justify-content: space-between; padding: 0.65rem 1rem; width: 100%; height: 100%; gap: 1rem; font-size: 0.875rem;">
                ${sourceTr.innerHTML}
            </div>
        `;
        document.body.appendChild(ghost);

        // Force browser layout reflow before triggering transition
        ghost.getBoundingClientRect();

        // Animate flying up towards the top banner
        requestAnimationFrame(() => {
            ghost.classList.add('flying');
            setTimeout(() => {
                ghost.remove();
                if (onComplete) onComplete();
            }, 380);
        });
    } catch (e) {
        console.warn('Pop-out animation error:', e);
        if (onComplete) onComplete();
    }
}

function checkBannerVisibility() {
    const banner = $('selectedCaseBanner');
    if (!banner || !selected || isBannerDismissed) {
        if (banner) {
            banner.classList.remove('visible');
            banner.classList.add('faded-out');
        }
        return;
    }

    const queueTable = document.querySelector('.tablewrap') || $('rows');
    if (!queueTable) return;

    const rect = queueTable.getBoundingClientRect();
    // When the Case Queue table is visible in the viewport, fade out the banner
    // so it doesn't duplicate the row sitting right in front of the reviewer.
    // When scrolled down into Case Details / VoiceOps, fade the banner in.
    const inQueueArea = rect.bottom > 140 && rect.top < (window.innerHeight - 100);

    if (inQueueArea) {
        banner.classList.remove('visible');
        banner.classList.add('faded-out');
    } else {
        banner.classList.add('visible');
        banner.classList.remove('faded-out');
    }
}

function updateSelectedCaseBanner(caseData, animateSourceTr = null) {
    const banner = $('selectedCaseBanner');
    if (!banner || !caseData) return;

    isBannerDismissed = false;
    banner.hidden = false;

    // Populate case details into banner
    $('bannerCaseId').textContent = caseData.case_id;
    $('bannerDomain').textContent = caseData.domain;
    $('bannerDomain').className = `tag banner-domain ${caseData.domain}`;
    $('bannerDesc').textContent = caseData.exception_text;
    $('bannerDesc').title = caseData.exception_text;
    $('bannerStatus').innerHTML = formatStatus(caseData.status);
    $('bannerAction').textContent = formatAction(caseData.processing?.recommended_action);
    $('bannerReview').innerHTML = formatReviewQueueStatus(caseData.processing);

    // Button actions
    $('bannerToDetailsBtn').onclick = () => {
        const detailPanel = $('detail');
        if (detailPanel) {
            detailPanel.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
    };

    $('bannerToQueueBtn').onclick = () => {
        const targetRow = document.querySelector(`#rows tr[data-id="${caseData.case_id}"]`);
        if (targetRow) {
            targetRow.scrollIntoView({ behavior: 'smooth', block: 'center' });
        } else {
            const tableWrap = document.querySelector('.tablewrap');
            if (tableWrap) tableWrap.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
    };

    $('bannerCloseBtn').onclick = () => {
        isBannerDismissed = true;
        banner.classList.remove('visible');
        banner.classList.add('faded-out');
    };

    if (animateSourceTr) {
        animateRowPopOut(animateSourceTr, () => {
            checkBannerVisibility();
        });
    } else {
        checkBannerVisibility();
    }
}

window.addEventListener('scroll', checkBannerVisibility, { passive: true });
window.addEventListener('resize', checkBannerVisibility, { passive: true });

function renderPaginationControls(totalPages) {
    const paginationContainer = $('pagination');
    if (!paginationContainer) return;

    if (totalPages <= 1) {
        paginationContainer.innerHTML = '';
        return;
    }

    let paginationHTML = '<div class="pagination-controls">';

    // Previous button
    paginationHTML += `
        <button id="prevPage" ${currentPage === 1 ? 'disabled' : ''}>
            ‹ Previous
        </button>
    `;

    // Page numbers (show max 5 pages at once)
    let startPage = Math.max(1, currentPage - 2);
    const endPage = Math.min(totalPages, startPage + 4);

    // Adjust startPage if we're near the end
    if (endPage - startPage < 4 && startPage > 1) {
        startPage = Math.max(1, endPage - 4);
    }

    for (let page = startPage; page <= endPage; page++) {
        paginationHTML += `
            <button class="page-number ${page === currentPage ? 'active' : ''}"
                    data-page="${page}">
                ${page}
            </button>
        `;
    }

    // Next button
    paginationHTML += `
        <button id="nextPage" ${currentPage === totalPages ? 'disabled' : ''}>
            Next ›
        </button>
    `;

    paginationHTML += '</div>';

    // Add page info
    paginationHTML += `<div class="page-info">
        Page ${currentPage} of ${totalPages}
        (<strong>${filteredCases.length}</strong> cases total)
    </div>`;

    paginationContainer.innerHTML = paginationHTML;

    // Add event listeners
    const prevButton = $('prevPage');
    const nextButton = $('nextPage');

    if (prevButton) {
        prevButton.addEventListener('click', () => {
            if (currentPage > 1) {
                currentPage--;
                renderRows();
            }
        });
    }

    if (nextButton) {
        nextButton.addEventListener('click', () => {
            if (currentPage < totalPages) {
                currentPage++;
                renderRows();
            }
        });
    }

    // Add event listeners for page number buttons
    const pageButtons = document.querySelectorAll('.page-number');
    pageButtons.forEach(button => {
        button.addEventListener('click', () => {
            const page = parseInt(button.dataset.page);
            if (page !== currentPage) {
                currentPage = page;
                renderRows();
            }
        });
    });
}

$('ask').onclick=async()=>{try{const q=$('question').value.trim();if(!q)throw new Error('Enter a question first.');const data=selected?await api(`/cases/${encodeURIComponent(selected.case_id)}/query`,{method:'POST',body:JSON.stringify({question:q})}):await api('/query',{method:'POST',body:JSON.stringify({question:q})});lastAnswer=data.answer;$('answer').textContent=data.answer+(data.evidence?.length?'\n\nEvidence:\n• '+data.evidence.join('\n• '):'');$('speak').disabled=false}catch(e){$('answer').textContent=e.message}}
;
$('speak').onclick=async()=>{try{const blob=await api('/voice/speak',{method:'POST',body:JSON.stringify({text:lastAnswer})});const player=$('player');player.src=URL.createObjectURL(blob);player.hidden=false;await player.play();$('voiceStatus').textContent='Speech playback started.'}catch(e){$('voiceStatus').textContent=e.message}}
;
$('stop').onclick=()=>{$('player').pause();$('player').currentTime=0};
['domain','review','search'].forEach(id=>$(id).addEventListener(id==='search'?'input':'change',renderRows));
init();