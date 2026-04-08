/* =====================================================
   CogniMap v2.0 — Client-Side Application Logic
   ===================================================== */

// Global State
let nodes = new vis.DataSet();
let edges = new vis.DataSet();
let network = null;
let extractedConcepts = []; // Raw tree data from extraction
let selectedConcepts = [];  // User-confirmed concepts
let uploadedFiles = [];     // List of uploaded PDFs

// =====================================================
// vis.js Network Configuration
// =====================================================

function buildVisNodes(concepts) {
    return concepts.map((concept, index) => {
        // Ensure unique ID by combining name and index
        const uniqueId = `node-${index}-${encodeURIComponent(concept.name || 'unknown')}`;
        
        return {
            id: uniqueId,
            label: concept.name,
            size: 20,
            color: {
                background: '#6366f1',
                border: '#818cf8',
                highlight: { background: '#818cf8', border: '#ffffff' }
            },
            shape: 'dot',
            borderWidth: 2,
            font: { size: 14, color: '#ffffff', face: 'Inter' },
            shadow: { enabled: true, color: 'rgba(99, 102, 241, 0.3)', size: 10 },
            title: buildNodeTooltip(concept),
            source: concept.source || 'Unknown',
            page: concept.page || null,
            conceptType: concept.type || 'main_topic'
        };
    });
}

function buildNodeTooltip(concept) {
    let tooltip = `<b>${concept.name}</b>`;
    if (concept.source) {
        tooltip += `<br>Source: ${concept.source}`;
    }
    if (concept.page) {
        tooltip += ` (p. ${concept.page})`;
    }
    return tooltip;
}

function initNetwork() {
    const container = document.getElementById('mynetwork');
    const data = { nodes: nodes, edges: edges };
    const options = {
        nodes: {
            shape: 'dot',
            font: { size: 14, color: '#ffffff', face: 'Inter' },
            borderWidth: 2,
            shadow: true
        },
        edges: {
            width: 2,
            color: { color: '#475569', highlight: '#818cf8', hover: '#818cf8' },
            arrows: { to: { enabled: true, scaleFactor: 0.5 } },
            smooth: { type: 'continuous' },
            shadow: true
        },
        physics: {
            forceAtlas2Based: {
                gravitationalConstant: -250,
                centralGravity: 0.005,
                springLength: 350,
                springConstant: 0.08,
                avoidOverlap: 1
            },
            solver: 'forceAtlas2Based',
            stabilization: { iterations: 1000 }
        },
        interaction: {
            hover: true,
            navigationButtons: true,
            keyboard: true,
            multiselect: false
        }
    };

    if (network) {
        network.destroy();
    }
    network = new vis.Network(container, data, options);
    
    // Click handler (placeholder for future phases)
    network.on('click', function(params) {
        if (params.nodes.length > 0) {
            const nodeId = params.nodes[0];
            console.log('Node clicked:', nodeId);
            // Future: Open right panel with node details
        }
    });
}

function updateGraphData(concepts) {
    console.log('📊 updateGraphData() called with', concepts.length, 'concepts');
    console.log('📦 Concepts data:', concepts);
    
    // Debug: Check DOM state
    const graphContainer = document.getElementById('graph-container');
    const networkDiv = document.getElementById('mynetwork');
    console.log('📐 Graph container:', graphContainer ? `width=${graphContainer.clientWidth}, height=${graphContainer.clientHeight}, display=${graphContainer.style.display || 'block'}` : 'NOT FOUND');
    console.log('📐 Network div:', networkDiv ? `width=${networkDiv.clientWidth}, height=${networkDiv.clientHeight}, display=${networkDiv.style.display || 'block'}` : 'NOT FOUND');
    console.log(' Network object:', network ? 'exists' : 'NULL');
    
    nodes.clear();
    edges.clear();

    const nodesData = buildVisNodes(concepts);
    console.log('🔵 Built', nodesData.length, 'vis nodes');
    
    nodes.add(nodesData);
    console.log('✅ Nodes added to network, total:', nodes.length);

    document.getElementById('node-count').innerText = nodes.length;
    document.getElementById('edge-count').innerText = edges.length;
    
    // Fit view to show all nodes and force redraw
    if (network && nodes.length > 0) {
        network.fit({ animation: { duration: 500, easingFunction: 'easeInOutQuad' } });
        network.redraw();
        console.log('🎯 Network fitted and redrawn');
    } else if (!network) {
        console.error('❌ Network object is null! Cannot fit/redraw');
    }
}

// =====================================================
// PDF Upload Management
// =====================================================

async function refreshFileList() {
    try {
        const resp = await fetch('/api/files');
        const data = await resp.json();
        uploadedFiles = data.files || [];
        renderFileList();
    } catch (err) {
        console.error('Failed to refresh file list:', err);
    }
}

function renderFileList() {
    const listContainer = document.getElementById('file-list');
    
    if (uploadedFiles.length === 0) {
        listContainer.innerHTML = '<div class="file-list-empty">No files uploaded</div>';
        return;
    }
    
    listContainer.innerHTML = uploadedFiles.map(file => `
        <div class="file-item">
            <span>${file}</span>
            <button class="delete-file" onclick="deleteFile('${file}')">&times;</button>
        </div>
    `).join('');
}

async function deleteFile(filename) {
    if (!confirm(`Delete ${filename}?`)) return;
    
    try {
        await fetch(`/api/delete/${encodeURIComponent(filename)}`, { method: 'DELETE' });
        await refreshFileList();
        showStalenessWarning();
    } catch (err) {
        console.error('Failed to delete file:', err);
        alert('Failed to delete file');
    }
}

async function handleFileUpload(event) {
    const status = document.getElementById('upload-status');
    const files = event.target.files;
    
    if (files.length === 0) return;
    
    status.innerText = `⏳ Uploading ${files.length} file(s)...`;
    status.style.color = '#818cf8';
    
    let successCount = 0;
    for (const file of files) {
        const formData = new FormData();
        formData.append('file', file);
        
        try {
            const resp = await fetch('/api/upload', { method: 'POST', body: formData });
            if (resp.ok) {
                successCount++;
            } else {
                const err = await resp.json();
                console.error(`Upload failed for ${file.name}:`, err);
            }
        } catch (err) {
            console.error('Network error during upload:', err);
        }
    }
    
    status.innerText = `✅ Successfully uploaded ${successCount}/${files.length} files.`;
    status.style.color = '#10b981';
    
    // Clear input so selecting the same file again triggers onchange
    event.target.value = '';
    
    setTimeout(() => { status.innerText = ''; }, 5000);
    await refreshFileList();
}

// =====================================================
// Concept Extraction
// =====================================================

async function handleExtractConcepts() {
    if (uploadedFiles.length === 0) {
        alert('Please upload at least one PDF first');
        return;
    }
    
    const btn = document.getElementById('extract-btn');
    btn.disabled = true;
    
    showLoadingOverlay('Extracting concepts from PDFs...');
    
    try {
        const resp = await fetch('/api/extract', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ files: uploadedFiles })
        });
        
        if (!resp.ok) {
            const err = await resp.json();
            throw new Error(err.error || 'Extraction failed');
        }
        
        // Start polling for completion
        await pollExtractionStatus();
        
    } catch (err) {
        hideLoadingOverlay();
        alert(`Extraction failed: ${err.message}`);
        btn.disabled = false;
    }
}

async function pollExtractionStatus() {
    const pollInterval = setInterval(async () => {
        try {
            const resp = await fetch('/api/status');
            const state = await resp.json();
            
            if (state.running) {
                updateLoadingText(state.step || 'Processing...');
            }
            
            if (!state.running) {
                clearInterval(pollInterval);
                
                if (state.error) {
                    hideLoadingOverlay();
                    alert(`Extraction error: ${state.error}`);
                    document.getElementById('extract-btn').disabled = false;
                } else {
                    // Extraction complete, load results
                    await loadExtractedConcepts();
                    hideLoadingOverlay();
                    document.getElementById('extract-btn').disabled = false;
                }
            }
        } catch (err) {
            console.error('Polling error:', err);
            clearInterval(pollInterval);
            hideLoadingOverlay();
            document.getElementById('extract-btn').disabled = false;
        }
    }, 2000);
}

async function loadExtractedConcepts() {
    console.log('📦 Concept Extraction Debug:');
    console.log('✅ Extraction complete, loading results...');
    
    try {
        const resp = await fetch('/api/extracted-concepts');
        const data = await resp.json();
        
        console.log('📄 API response:', data);
        console.log('📊 Headings count:', data.headings ? data.headings.length : 0);

        if (data.headings && data.headings.length > 0) {
            extractedConcepts = data.headings;
            console.log('🌳 Rendering concept tree...');
            renderConceptTree();
            console.log('👁️ Showing review panel...');
            showReviewPanel();
        } else {
            console.warn('⚠️ No headings found in data');
            alert('No concepts extracted. Try uploading a different PDF.');
        }
    } catch (err) {
        console.error('❌ Failed to load extracted concepts:', err);
        alert('Failed to load extracted concepts');
    }
}

// =====================================================
// Concept Tree Rendering
// =====================================================

function renderConceptTree() {
    console.log('🌳 renderConceptTree() called');
    const treeContainer = document.getElementById('concept-tree');
    console.log('📦 Tree container:', treeContainer);

    let totalConcepts = 0;
    let html = '';

    extractedConcepts.forEach((heading, headingIndex) => {
        const conceptCount = heading.concepts ? heading.concepts.length : 0;
        totalConcepts += conceptCount + 1; // +1 for heading itself

        console.log(`  Heading ${headingIndex}: "${heading.name}" (${conceptCount} concepts)`);

        // Heading as a selectable concept (Main Topic)
        const headingId = `heading-${headingIndex}`;
        html += `
            <div class="heading-group" data-heading-index="${headingIndex}">
                <div class="concept-item heading-concept-item">
                    <input type="checkbox"
                           id="cb-${headingId}"
                           checked
                           onchange="toggleHeadingCheckbox(${headingIndex})" />
                    <span class="concept-name heading-name" id="name-${headingId}">
                        <strong>📚 ${heading.name}</strong> <span class="concept-type-badge">(Main Topic)</span>
                    </span>
                    <input type="text"
                           class="concept-edit-input"
                           id="edit-${headingId}"
                           value="${heading.name}" />
                    <button class="btn-edit" onclick="enableEdit('${headingId}')">✏️</button>
                    <button class="btn-toggle-heading" onclick="toggleHeading(${headingIndex})" title="Expand/Collapse sub-topics">
                        <span class="heading-toggle" id="toggle-${headingIndex}">▼</span>
                    </button>
                </div>
                <div class="heading-children" id="children-${headingIndex}">
        `;

        // Sub-concepts
        if (heading.concepts) {
            heading.concepts.forEach((concept, conceptIndex) => {
                const conceptId = `concept-${headingIndex}-${conceptIndex}`;
                html += `
                    <div class="concept-item sub-concept-item" data-parent-heading="${headingIndex}">
                        <input type="checkbox"
                               id="cb-${conceptId}"
                               checked
                               onchange="updateConceptSelection()" />
                        <span class="concept-name" id="name-${conceptId}">
                            ${concept.name} <span class="concept-type-badge">(Sub-topic)</span>
                        </span>
                        <input type="text"
                               class="concept-edit-input"
                               id="edit-${conceptId}"
                               value="${concept.name}" />
                        <button class="btn-edit" onclick="enableEdit('${conceptId}')">✏️</button>
                        <span class="concept-source">${concept.source || ''}${concept.page ? ` (p. ${concept.page})` : ''}</span>
                    </div>
                `;
            });
        }

        html += `
                </div>
            </div>
        `;
    });

    console.log('📝 Injecting HTML into tree container, length:', html.length);
    treeContainer.innerHTML = html;

    // Update stats
    document.getElementById('review-stats').innerText =
        `${totalConcepts} concepts (${extractedConcepts.length} main topics, ${totalConcepts - extractedConcepts.length} sub-topics)`;

    // Initial selection count
    updateConceptSelection();
    console.log('✅ Tree rendering complete');
}

// Toggle heading checkbox - controls all children
function toggleHeadingCheckbox(headingIndex) {
    const headingCheckbox = document.getElementById(`cb-heading-${headingIndex}`);
    const isChecked = headingCheckbox.checked;

    // Find all sub-concept checkboxes under this heading
    const headingGroup = document.querySelector(`[data-heading-index="${headingIndex}"]`);
    const subCheckboxes = headingGroup.querySelectorAll('.sub-concept-item input[type="checkbox"]');

    subCheckboxes.forEach(cb => {
        cb.checked = isChecked;
    });

    updateConceptSelection();
}

// Toggle heading expand/collapse
function toggleHeading(headingIndex) {
    const toggle = document.getElementById(`toggle-${headingIndex}`);
    const children = document.getElementById(`children-${headingIndex}`);

    if (children.classList.contains('collapsed')) {
        children.classList.remove('collapsed');
        toggle.classList.remove('collapsed');
    } else {
        children.classList.add('collapsed');
        toggle.classList.add('collapsed');
    }
}

function enableEdit(conceptId) {
    const nameSpan = document.getElementById(`name-${conceptId}`);
    const editInput = document.getElementById(`edit-${conceptId}`);
    
    nameSpan.classList.add('editing');
    editInput.classList.add('active');
    editInput.focus();
    editInput.select();
    
    // Save on Enter or blur
    editInput.onkeydown = (e) => {
        if (e.key === 'Enter') {
            saveEdit(conceptId);
        }
    };
    editInput.onblur = () => saveEdit(conceptId);
}

function saveEdit(conceptId) {
    const nameSpan = document.getElementById(`name-${conceptId}`);
    const editInput = document.getElementById(`edit-${conceptId}`);
    const newName = editInput.value.trim();
    
    if (newName) {
        nameSpan.innerText = newName;
        
        // Update data structure
        const parts = conceptId.split('-');
        const headingIndex = parseInt(parts[1]);
        const conceptIndex = parseInt(parts[2]);
        
        if (extractedConcepts[headingIndex] && extractedConcepts[headingIndex].concepts[conceptIndex]) {
            extractedConcepts[headingIndex].concepts[conceptIndex].name = newName;
        }
    }
    
    nameSpan.classList.remove('editing');
    editInput.classList.remove('active');
}

function updateConceptSelection() {
    const checkboxes = document.querySelectorAll('#concept-tree input[type="checkbox"]');
    let selectedCount = 0;
    
    checkboxes.forEach(cb => {
        if (cb.checked) selectedCount++;
    });
    
    const confirmBtn = document.getElementById('confirm-btn');
    confirmBtn.disabled = selectedCount === 0;
    confirmBtn.innerText = `✅ Confirm Selection (${selectedCount} concept${selectedCount !== 1 ? 's' : ''})`;
}

function selectAllConcepts() {
    const checkboxes = document.querySelectorAll('#concept-tree input[type="checkbox"]');
    checkboxes.forEach(cb => cb.checked = true);
    updateConceptSelection();
}

function deselectAllConcepts() {
    const checkboxes = document.querySelectorAll('#concept-tree input[type="checkbox"]');
    checkboxes.forEach(cb => cb.checked = false);
    updateConceptSelection();
}

async function confirmSelection() {
    // Collect selected concepts (both headings and sub-concepts)
    const selected = [];

    extractedConcepts.forEach((heading, headingIndex) => {
        // Check if heading itself is selected
        const headingId = `heading-${headingIndex}`;
        const headingCheckbox = document.getElementById(`cb-${headingId}`);

        if (headingCheckbox && headingCheckbox.checked) {
            // Add heading as a concept (Main Topic)
            selected.push({
                id: heading.name,
                name: heading.name,
                source: heading.source,
                page: heading.page,
                type: 'main_topic',
                heading: null
            });
        }

        // Check sub-concepts
        if (heading.concepts) {
            heading.concepts.forEach((concept, conceptIndex) => {
                const conceptId = `concept-${headingIndex}-${conceptIndex}`;
                const checkbox = document.getElementById(`cb-${conceptId}`);

                if (checkbox && checkbox.checked) {
                    selected.push({
                        id: concept.name,
                        name: concept.name,
                        source: concept.source,
                        page: concept.page,
                        type: 'sub_topic',
                        heading: heading.name
                    });
                }
            });
        }
    });
    
    if (selected.length === 0) {
        alert('Please select at least one concept');
        return;
    }
    
    // Send to backend
    try {
        const resp = await fetch('/api/confirm-concepts', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ concepts: selected })
        });
        
        if (!resp.ok) {
            const err = await resp.json();
            throw new Error(err.error || 'Failed to confirm concepts');
        }
        
        // Hide review panel, show graph
        console.log('✅ Confirmation successful, hiding panel and rendering graph...');
        hideReviewPanel();
        selectedConcepts = selected;
        console.log('🔵 Calling updateGraphData with', selected.length, 'concepts');
        updateGraphData(selected);

        console.log('✅ Graph rendering complete');
        
    } catch (err) {
        alert(`Failed to confirm concepts: ${err.message}`);
    }
}

// =====================================================
// Review Panel Management
// =====================================================

function showReviewPanel() {
    console.log('👁️ showReviewPanel() called');
    const panel = document.getElementById('review-panel');
    const backdrop = document.getElementById('review-backdrop');
    
    console.log('📦 Panel element:', panel);
    console.log('📦 Backdrop element:', backdrop);
    
    backdrop.style.display = 'block';
    panel.style.display = 'flex';
    
    console.log('✅ Panel and backdrop displayed');
}

function hideReviewPanel() {
    console.log('👁️ hideReviewPanel() called');
    const panel = document.getElementById('review-panel');
    const backdrop = document.getElementById('review-backdrop');
    
    backdrop.style.display = 'none';
    panel.style.display = 'none';
}

// =====================================================
// Loading Overlay
// =====================================================

function showLoadingOverlay(text = 'Loading...') {
    document.getElementById('loading-text').innerText = text;
    document.getElementById('loading-overlay').style.display = 'flex';
}

function hideLoadingOverlay() {
    document.getElementById('loading-overlay').style.display = 'none';
}

function updateLoadingText(text) {
    document.getElementById('loading-text').innerText = text;
}

// =====================================================
// Staleness Warning
// =====================================================

function showStalenessWarning() {
    document.getElementById('staleness-banner').style.display = 'block';
}

function hideStalenessWarning() {
    document.getElementById('staleness-banner').style.display = 'none';
}

// =====================================================
// Initialization
// =====================================================

window.onload = function() {
    // Initialize vis.js network
    initNetwork();
    
    // Load initial file list
    refreshFileList();
    
    // Event Listeners
    document.getElementById('pdf-upload').onchange = handleFileUpload;
    document.getElementById('extract-btn').onclick = handleExtractConcepts;
    document.getElementById('select-all-btn').onclick = selectAllConcepts;
    document.getElementById('deselect-all-btn').onclick = deselectAllConcepts;
    document.getElementById('confirm-btn').onclick = confirmSelection;
    document.getElementById('close-right-panel').onclick = () => {
        document.getElementById('right-panel').classList.remove('open');
    };
};
