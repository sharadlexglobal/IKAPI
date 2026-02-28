let currentQuery = "";
let currentPage = 0;
let totalResults = 0;
var PAGE_SIZE = 10;
var isSmartSearchLoading = false;
var selectedTids = new Set();

var searchInput = document.getElementById("searchInput");
var searchBtn = document.getElementById("searchBtn");
var smartSearchBtn = document.getElementById("smartSearchBtn");
var smartStatus = document.getElementById("smartStatus");
var filtersToggle = document.getElementById("filtersToggle");
var filtersPanel = document.getElementById("filtersPanel");
var tipsToggle = document.getElementById("tipsToggle");
var tipsPanel = document.getElementById("tipsPanel");
var resultsArea = document.getElementById("resultsArea");
var docOverlay = document.getElementById("docOverlay");
var docTitle = document.getElementById("docTitle");
var docBody = document.getElementById("docBody");
var docClose = document.getElementById("docClose");
var docCachedBadge = document.getElementById("docCachedBadge");

searchBtn.addEventListener("click", function () { doSearch(0); });
searchInput.addEventListener("keydown", function (e) {
    if (e.key === "Enter") {
        if (isSmartSearchLoading) return;
        doSearch(0);
    }
});

smartSearchBtn.addEventListener("click", doSmartSearch);

filtersToggle.addEventListener("click", function () {
    filtersPanel.classList.toggle("active");
    filtersToggle.textContent = filtersPanel.classList.contains("active")
        ? "Hide filters"
        : "Show filters";
});

tipsToggle.addEventListener("click", function () {
    tipsPanel.classList.toggle("active");
    tipsToggle.textContent = tipsPanel.classList.contains("active")
        ? "Hide tips"
        : "Search tips & examples";
});

document.querySelectorAll(".example-btn").forEach(function (btn) {
    btn.addEventListener("click", function () {
        searchInput.value = btn.getAttribute("data-query");
        searchInput.focus();
    });
});

docClose.addEventListener("click", closeDoc);
docOverlay.addEventListener("click", function (e) {
    if (e.target === docOverlay) closeDoc();
});

document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") {
        closeDoc();
        closeTemplateModal();
    }
});

document.querySelectorAll(".nav-tab").forEach(function (tab) {
    tab.addEventListener("click", function () {
        var view = tab.getAttribute("data-view");
        document.querySelectorAll(".nav-tab").forEach(function (t) { t.classList.remove("active"); });
        tab.classList.add("active");
        document.querySelectorAll(".view-panel").forEach(function (p) { p.classList.remove("active"); });
        document.getElementById(view + "View").classList.add("active");
        if (view === "analysis") {
            loadSavedQueries();
            loadTemplates();
        }
        if (view === "genomeLab") {
            loadCachedJudgments();
        }
    });
});

function doSmartSearch() {
    var q = searchInput.value.trim();
    if (!q) return;

    isSmartSearchLoading = true;
    smartSearchBtn.disabled = true;
    searchBtn.disabled = true;
    smartSearchBtn.textContent = "Thinking...";
    smartStatus.textContent = "AI is interpreting your query...";
    smartStatus.className = "smart-status active";

    fetch("/api/smart-search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: q })
    })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            isSmartSearchLoading = false;
            smartSearchBtn.disabled = false;
            searchBtn.disabled = false;
            smartSearchBtn.textContent = "Smart Search";

            if (data.error) {
                smartStatus.textContent = "Error: " + data.error;
                smartStatus.className = "smart-status active error";
                return;
            }

            searchInput.value = data.query || q;

            document.getElementById("filterDoctype").value = "";
            document.getElementById("filterFrom").value = "";
            document.getElementById("filterTo").value = "";
            document.getElementById("filterSort").value = "";

            if (data.doctype) {
                document.getElementById("filterDoctype").value = data.doctype;
            }
            if (data.fromdate) {
                document.getElementById("filterFrom").value = data.fromdate;
            }
            if (data.todate) {
                document.getElementById("filterTo").value = data.todate;
            }
            if (data.sortby) {
                document.getElementById("filterSort").value = data.sortby;
            }

            if (data.doctype || data.fromdate || data.todate || data.sortby) {
                filtersPanel.classList.add("active");
                filtersToggle.textContent = "Hide filters";
            }

            smartStatus.textContent = "Query formatted! Review and click Search to execute.";
            smartStatus.className = "smart-status active success";

            searchInput.focus();
        })
        .catch(function (err) {
            isSmartSearchLoading = false;
            smartSearchBtn.disabled = false;
            searchBtn.disabled = false;
            smartSearchBtn.textContent = "Smart Search";
            smartStatus.textContent = "Something went wrong: " + err.message;
            smartStatus.className = "smart-status active error";
        });
}

function doSearch(page) {
    var q = searchInput.value.trim();
    if (!q) return;

    currentQuery = q;
    currentPage = page;

    smartStatus.textContent = "";
    smartStatus.className = "smart-status";

    var params = new URLSearchParams({ q: q, page: page });

    var doctype = document.getElementById("filterDoctype").value.trim();
    var fromdate = document.getElementById("filterFrom").value.trim();
    var todate = document.getElementById("filterTo").value.trim();
    var sortby = document.getElementById("filterSort").value;

    if (doctype) params.set("doctype", doctype);
    if (fromdate) params.set("fromdate", fromdate);
    if (todate) params.set("todate", todate);
    if (sortby) params.set("sortby", sortby);

    searchBtn.disabled = true;
    searchBtn.textContent = "Searching...";

    resultsArea.innerHTML =
        '<div class="loading"><div class="spinner"></div><p>Searching Indian legal database...</p></div>';

    fetch("/api/search?" + params)
        .then(function (r) { return r.json(); })
        .then(function (data) {
            searchBtn.disabled = false;
            searchBtn.textContent = "Search";
            renderResults(data);
        })
        .catch(function (err) {
            searchBtn.disabled = false;
            searchBtn.textContent = "Search";
            var el = document.createElement("div");
            el.className = "error-msg";
            el.textContent = "Something went wrong: " + err.message;
            resultsArea.innerHTML = "";
            resultsArea.appendChild(el);
        });
}

function renderResults(data) {
    if (data.error || data.errmsg) {
        var el = document.createElement("div");
        el.className = "error-msg";
        el.textContent = data.error || data.errmsg;
        resultsArea.innerHTML = "";
        resultsArea.appendChild(el);
        return;
    }

    if (!data.docs || data.docs.length === 0) {
        resultsArea.innerHTML =
            '<div class="empty-state"><h3>No results found</h3><p>Try a different query or adjust your filters.</p></div>';
        return;
    }

    totalResults = data.total || 0;
    var totalPages = Math.ceil(totalResults / PAGE_SIZE);

    var html = '<div class="results-info">Showing <strong>' +
        escapeHtml(data.found || "") +
        '</strong> for "<strong>' +
        escapeHtml(currentQuery) +
        '</strong>"</div>';

    if (data.mostcited_note) {
        html += '<div class="mostcited-note">' + escapeHtml(data.mostcited_note) + '</div>';
    }

    for (var i = 0; i < data.docs.length; i++) {
        var doc = data.docs[i];
        html += '<div class="result-card" onclick="openDoc(' + doc.tid + ')">' +
            '<div class="result-title">' + (doc.title || "Untitled") + '</div>' +
            '<div class="result-meta">' +
            '<span>' + escapeHtml(doc.docsource || "") + '</span>' +
            '<span>' + escapeHtml(doc.publishdate || "") + '</span>' +
            (doc.numcites ? '<span>Cites: ' + doc.numcites + '</span>' : '') +
            (doc.numcitedby ? '<span>Cited by: ' + doc.numcitedby + '</span>' : '') +
            '</div>' +
            '<div class="result-snippet">' + (doc.headline || "") + '</div>' +
            '<div class="result-actions">' +
            '<button class="save-btn" onclick="event.stopPropagation(); saveDoc(' + doc.tid + ', this)">Save for Analysis</button>' +
            '</div>' +
            '</div>';
    }

    if (!data.mostcited_note) {
        html += renderPagination(totalPages);
    }
    resultsArea.innerHTML = html;
}

function renderPagination(totalPages) {
    if (totalPages <= 1) return "";

    var html = '<div class="pagination">';

    if (currentPage > 0) {
        html += '<button class="page-btn" onclick="doSearch(' + (currentPage - 1) + ')">Previous</button>';
    }

    var start = Math.max(0, currentPage - 3);
    var end = Math.min(totalPages, currentPage + 4);

    for (var i = start; i < end; i++) {
        html += '<button class="page-btn ' + (i === currentPage ? "active" : "") +
            '" onclick="doSearch(' + i + ')">' + (i + 1) + '</button>';
    }

    if (currentPage < totalPages - 1) {
        html += '<button class="page-btn" onclick="doSearch(' + (currentPage + 1) + ')">Next</button>';
    }

    html += "</div>";
    return html;
}

function openDoc(docid) {
    docOverlay.classList.add("active");
    document.body.style.overflow = "hidden";
    docTitle.textContent = "Loading...";
    docCachedBadge.style.display = "none";
    document.getElementById("docExtractGenomeBtn").style.display = "none";
    _currentDocTid = null;
    docBody.innerHTML =
        '<div class="loading"><div class="spinner"></div><p>Fetching document...</p></div>';

    fetch("/api/doc/" + docid)
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (data.error || data.errmsg) {
                docTitle.textContent = "Error";
                var p = document.createElement("p");
                p.textContent = data.error || data.errmsg;
                docBody.innerHTML = "";
                docBody.appendChild(p);
                return;
            }
            docTitle.innerHTML = data.title || "Document";
            docBody.innerHTML = data.doc || "<p>No content available.</p>";
            if (data.cached) {
                docCachedBadge.style.display = "inline-block";
                document.getElementById("docExtractGenomeBtn").style.display = "inline-block";
                _currentDocTid = docid;
            }
        })
        .catch(function (err) {
            docTitle.textContent = "Error";
            var p = document.createElement("p");
            p.textContent = err.message;
            docBody.innerHTML = "";
            docBody.appendChild(p);
        });
}

function closeDoc() {
    docOverlay.classList.remove("active");
    document.body.style.overflow = "";
}

function saveDoc(docid, btn) {
    btn.disabled = true;
    btn.textContent = "Saving...";
    fetch("/api/save-doc/" + docid, { method: "POST" })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (data.success) {
                btn.textContent = "Saved";
                btn.classList.add("saved");
            } else {
                btn.textContent = "Error";
                btn.disabled = false;
            }
        })
        .catch(function () {
            btn.textContent = "Error";
            btn.disabled = false;
        });
}

function loadSavedQueries() {
    var sel = document.getElementById("querySelect");
    fetch("/api/saved-queries")
        .then(function (r) { return r.json(); })
        .then(function (data) {
            sel.innerHTML = '<option value="">-- Select a search query --</option>';
            if (Array.isArray(data)) {
                data.forEach(function (q) {
                    var opt = document.createElement("option");
                    opt.value = q.id;
                    var label = q.query_text;
                    if (q.doctype_filter) label += " [" + q.doctype_filter + "]";
                    label += " (" + q.result_count + " results)";
                    opt.textContent = label;
                    sel.appendChild(opt);
                });
            }
        });
}

document.getElementById("querySelect").addEventListener("change", function () {
    var qid = this.value;
    var list = document.getElementById("judgmentsList");
    var actions = document.getElementById("judgmentsActions");
    selectedTids.clear();

    if (!qid) {
        list.innerHTML = '<div class="empty-state small"><p>Select a saved search query above.</p></div>';
        actions.style.display = "none";
        updateAnalyzeState();
        return;
    }

    list.innerHTML = '<div class="loading"><div class="spinner"></div></div>';

    fetch("/api/query-judgments/" + qid)
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (!Array.isArray(data) || data.length === 0) {
                list.innerHTML = '<div class="empty-state small"><p>No judgments found for this query.</p></div>';
                actions.style.display = "none";
                return;
            }
            var html = "";
            data.forEach(function (j) {
                html += '<label class="judgment-item">' +
                    '<input type="checkbox" value="' + j.tid + '" class="judgment-cb" ' +
                    (j.has_full_text ? 'data-cached="true"' : '') + '>' +
                    '<div class="judgment-info">' +
                    '<div class="judgment-title">' + escapeHtml(j.title) + '</div>' +
                    '<div class="judgment-meta">' +
                    (j.court_source ? '<span>' + escapeHtml(j.court_source) + '</span>' : '') +
                    (j.publish_date ? '<span>' + escapeHtml(j.publish_date) + '</span>' : '') +
                    (j.num_cited_by ? '<span>Cited by: ' + j.num_cited_by + '</span>' : '') +
                    (j.has_full_text ? '<span class="cached-badge small">Cached</span>' : '') +
                    '</div></div></label>';
            });
            list.innerHTML = html;
            actions.style.display = "flex";

            list.querySelectorAll(".judgment-cb").forEach(function (cb) {
                cb.addEventListener("change", function () {
                    if (this.checked) {
                        selectedTids.add(parseInt(this.value));
                    } else {
                        selectedTids.delete(parseInt(this.value));
                    }
                    updateSelectedCount();
                    updateAnalyzeState();
                });
            });
        });
});

document.getElementById("selectAllBtn").addEventListener("click", function () {
    document.querySelectorAll(".judgment-cb").forEach(function (cb) {
        cb.checked = true;
        selectedTids.add(parseInt(cb.value));
    });
    updateSelectedCount();
    updateAnalyzeState();
});

document.getElementById("deselectAllBtn").addEventListener("click", function () {
    document.querySelectorAll(".judgment-cb").forEach(function (cb) {
        cb.checked = false;
    });
    selectedTids.clear();
    updateSelectedCount();
    updateAnalyzeState();
});

function updateSelectedCount() {
    document.getElementById("selectedCount").textContent = selectedTids.size + " selected";
}

function updateAnalyzeState() {
    var prompt = document.getElementById("promptEditor").value.trim();
    document.getElementById("analyzeBtn").disabled = selectedTids.size === 0 || !prompt;
}

function loadTemplates() {
    var sel = document.getElementById("templateSelect");
    fetch("/api/prompt-templates")
        .then(function (r) { return r.json(); })
        .then(function (data) {
            sel.innerHTML = '<option value="">-- Select a template --</option>';
            window._templates = data;
            if (Array.isArray(data)) {
                data.forEach(function (t) {
                    var opt = document.createElement("option");
                    opt.value = t.id;
                    opt.textContent = t.name;
                    opt.setAttribute("data-prompt", t.prompt_text);
                    sel.appendChild(opt);
                });
            }
        });
}

document.getElementById("templateSelect").addEventListener("change", function () {
    var opt = this.options[this.selectedIndex];
    var prompt = opt.getAttribute("data-prompt") || "";
    document.getElementById("promptEditor").value = prompt;
    var hasSelection = !!this.value;
    document.getElementById("editTemplateBtn").style.display = hasSelection ? "inline-block" : "none";
    document.getElementById("deleteTemplateBtn").style.display = hasSelection ? "inline-block" : "none";
    updateAnalyzeState();
});

document.getElementById("promptEditor").addEventListener("input", updateAnalyzeState);

var _editingTemplateId = null;

document.getElementById("newTemplateBtn").addEventListener("click", function () {
    _editingTemplateId = null;
    document.getElementById("templateNameInput").value = "";
    document.getElementById("templateTextInput").value = "";
    document.getElementById("templateModalTitle").textContent = "New Prompt Template";
    document.getElementById("templateSaveBtn").textContent = "Save Template";
    document.getElementById("templateModal").classList.add("active");
});

document.getElementById("editTemplateBtn").addEventListener("click", function () {
    var sel = document.getElementById("templateSelect");
    var tid = sel.value;
    if (!tid) return;
    _editingTemplateId = parseInt(tid);
    var tmpl = (window._templates || []).find(function (t) { return t.id === _editingTemplateId; });
    if (!tmpl) return;
    document.getElementById("templateNameInput").value = tmpl.name;
    document.getElementById("templateTextInput").value = tmpl.prompt_text;
    document.getElementById("templateModalTitle").textContent = "Edit Prompt Template";
    document.getElementById("templateSaveBtn").textContent = "Update Template";
    document.getElementById("templateModal").classList.add("active");
});

document.getElementById("deleteTemplateBtn").addEventListener("click", function () {
    var sel = document.getElementById("templateSelect");
    var tid = sel.value;
    if (!tid) return;
    if (!confirm("Delete this prompt template?")) return;
    fetch("/api/prompt-templates/" + tid, { method: "DELETE" })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (data.success) {
                document.getElementById("promptEditor").value = "";
                document.getElementById("editTemplateBtn").style.display = "none";
                document.getElementById("deleteTemplateBtn").style.display = "none";
                loadTemplates();
            }
        });
});

document.getElementById("templateModalClose").addEventListener("click", closeTemplateModal);
document.getElementById("templateCancelBtn").addEventListener("click", closeTemplateModal);

document.getElementById("templateModal").addEventListener("click", function (e) {
    if (e.target === this) closeTemplateModal();
});

function closeTemplateModal() {
    document.getElementById("templateModal").classList.remove("active");
}

document.getElementById("templateSaveBtn").addEventListener("click", function () {
    var name = document.getElementById("templateNameInput").value.trim();
    var text = document.getElementById("templateTextInput").value.trim();
    if (!name || !text) return;

    this.disabled = true;
    this.textContent = "Saving...";
    var btn = this;

    var url = "/api/prompt-templates";
    var method = "POST";
    if (_editingTemplateId) {
        url = "/api/prompt-templates/" + _editingTemplateId;
        method = "PUT";
    }

    fetch(url, {
        method: method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: name, prompt_text: text })
    })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            btn.disabled = false;
            btn.textContent = _editingTemplateId ? "Update Template" : "Save Template";
            if (data.id) {
                closeTemplateModal();
                loadTemplates();
            }
        })
        .catch(function () {
            btn.disabled = false;
            btn.textContent = _editingTemplateId ? "Update Template" : "Save Template";
        });
});

document.getElementById("analyzeBtn").addEventListener("click", function () {
    if (selectedTids.size === 0) return;
    var prompt = document.getElementById("promptEditor").value.trim();
    if (!prompt) return;

    var btn = this;
    btn.disabled = true;
    btn.textContent = "Analyzing...";
    var resultArea = document.getElementById("analysisResult");
    resultArea.innerHTML = '<div class="loading"><div class="spinner"></div><p>Gemini is analyzing judgments... This may take a moment.</p></div>';

    var templateSel = document.getElementById("templateSelect");
    var templateId = templateSel.value ? parseInt(templateSel.value) : null;

    var body = {
        tids: Array.from(selectedTids),
        custom_prompt: prompt,
    };
    if (templateId) {
        body.prompt_template_id = templateId;
    }

    fetch("/api/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body)
    })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            btn.disabled = false;
            btn.textContent = "Analyze with Gemini";
            if (data.error) {
                resultArea.innerHTML = '<div class="error-msg">' + escapeHtml(data.error) + '</div>';
                return;
            }
            var html = '<div class="analysis-output">' +
                '<div class="analysis-header">' +
                '<span>' + data.judgments_analyzed + ' judgment(s) analyzed</span>' +
                '<button class="btn-sm" onclick="copyAnalysis()">Copy</button>' +
                '</div>' +
                '<div id="analysisText" class="analysis-text">' + formatAnalysis(data.analysis) + '</div>' +
                '</div>';
            resultArea.innerHTML = html;
        })
        .catch(function (err) {
            btn.disabled = false;
            btn.textContent = "Analyze with Gemini";
            resultArea.innerHTML = '<div class="error-msg">' + escapeHtml(err.message) + '</div>';
        });
});

function formatAnalysis(text) {
    if (!text) return "";
    var escaped = escapeHtml(text);
    escaped = escaped.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    escaped = escaped.replace(/^### (.+)$/gm, '<h4>$1</h4>');
    escaped = escaped.replace(/^## (.+)$/gm, '<h3>$1</h3>');
    escaped = escaped.replace(/^# (.+)$/gm, '<h2>$1</h2>');
    escaped = escaped.replace(/^\* (.+)$/gm, '<li>$1</li>');
    escaped = escaped.replace(/^- (.+)$/gm, '<li>$1</li>');
    escaped = escaped.replace(/^\d+\. (.+)$/gm, '<li>$1</li>');
    escaped = escaped.replace(/\n/g, '<br>');
    return escaped;
}

function copyAnalysis() {
    var el = document.getElementById("analysisText");
    if (!el) return;
    var text = el.innerText || el.textContent;
    navigator.clipboard.writeText(text).then(function () {
        var btn = el.parentElement.querySelector(".btn-sm");
        if (btn) {
            btn.textContent = "Copied!";
            setTimeout(function () { btn.textContent = "Copy"; }, 2000);
        }
    });
}

function escapeHtml(text) {
    var el = document.createElement("span");
    el.textContent = text;
    return el.innerHTML;
}

var _currentDocTid = null;

var _currentGenomeData = null;
var _currentQuestionsData = null;

document.querySelectorAll(".genome-sub-tab").forEach(function (tab) {
    tab.addEventListener("click", function () {
        var subtab = tab.getAttribute("data-subtab");
        document.querySelectorAll(".genome-sub-tab").forEach(function (t) { t.classList.remove("active"); });
        tab.classList.add("active");
        document.querySelectorAll(".genome-panel").forEach(function (p) { p.classList.remove("active"); });
        document.getElementById(subtab + "Panel").classList.add("active");
    });
});

document.querySelectorAll(".source-btn").forEach(function (btn) {
    btn.addEventListener("click", function () {
        var source = btn.getAttribute("data-source");
        document.querySelectorAll(".source-btn").forEach(function (b) { b.classList.remove("active"); });
        btn.classList.add("active");
        document.querySelectorAll(".genome-source").forEach(function (s) { s.classList.remove("active"); });
        document.getElementById(source === "cached" ? "genomeCachedSource" : "genomePasteSource").classList.add("active");
        updateGenomeExtractState();
    });
});

document.getElementById("genomeCachedSelect").addEventListener("change", updateGenomeExtractState);
document.getElementById("genomeTextInput").addEventListener("input", updateGenomeExtractState);

function updateGenomeExtractState() {
    var btn = document.getElementById("extractGenomeBtn");
    var cachedActive = document.querySelector(".source-btn.active").getAttribute("data-source") === "cached";
    if (cachedActive) {
        btn.disabled = !document.getElementById("genomeCachedSelect").value;
    } else {
        btn.disabled = document.getElementById("genomeTextInput").value.trim().length < 200;
    }
}

function loadCachedJudgments() {
    var sel = document.getElementById("genomeCachedSelect");
    fetch("/api/cached-judgments")
        .then(function (r) { return r.json(); })
        .then(function (data) {
            sel.innerHTML = '<option value="">-- Select a judgment --</option>';
            if (Array.isArray(data) && data.length > 0) {
                data.forEach(function (j) {
                    var opt = document.createElement("option");
                    opt.value = j.tid;
                    var label = j.title || "Untitled";
                    if (label.length > 80) label = label.substring(0, 80) + "...";
                    if (j.court_source) label += " [" + j.court_source + "]";
                    opt.textContent = label;
                    sel.appendChild(opt);
                });
            } else if (Array.isArray(data) && data.length === 0) {
                var opt = document.createElement("option");
                opt.value = "";
                opt.textContent = "No cached judgments found. View documents first.";
                sel.appendChild(opt);
            }
        })
        .catch(function () {
            sel.innerHTML = '<option value="">Error loading judgments</option>';
        });
}

document.getElementById("extractGenomeBtn").addEventListener("click", function () {
    var btn = this;
    var cachedActive = document.querySelector(".source-btn.active").getAttribute("data-source") === "cached";
    var body = {};

    if (cachedActive) {
        body.tid = parseInt(document.getElementById("genomeCachedSelect").value);
    } else {
        body.judgment_text = document.getElementById("genomeTextInput").value.trim();
        body.citation = document.getElementById("genomeCitationInput").value.trim();
    }

    btn.disabled = true;
    btn.textContent = "Extracting...";
    document.getElementById("genomeProgress").style.display = "block";
    document.getElementById("genomeError").style.display = "none";
    document.getElementById("genomeViewerEmpty").style.display = "none";
    document.getElementById("genomeViewerContent").style.display = "none";

    fetch("/api/genome/extract", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body)
    })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            btn.disabled = false;
            btn.textContent = "Extract Genome";
            document.getElementById("genomeProgress").style.display = "none";

            if (data.error) {
                document.getElementById("genomeError").textContent = data.error;
                document.getElementById("genomeError").style.display = "block";
                document.getElementById("genomeViewerEmpty").style.display = "block";
                return;
            }

            _currentGenomeData = data.genome;
            renderGenome(data);
        })
        .catch(function (err) {
            btn.disabled = false;
            btn.textContent = "Extract Genome";
            document.getElementById("genomeProgress").style.display = "none";
            document.getElementById("genomeError").textContent = err.message;
            document.getElementById("genomeError").style.display = "block";
            document.getElementById("genomeViewerEmpty").style.display = "block";
        });
});

function renderGenome(data) {
    var genome = data.genome;
    document.getElementById("genomeViewerEmpty").style.display = "none";
    document.getElementById("genomeViewerContent").style.display = "block";

    var metaHtml = "";
    if (data.cached) metaHtml += '<span class="cached-badge">Cached</span> ';
    var cert = "";
    try { cert = genome.dimension_6_audit.final_certification.certification_level || ""; } catch(e) {}
    if (cert) metaHtml += '<span class="cert-badge cert-' + cert + '">' + cert.replace(/_/g, " ") + '</span> ';
    var durability = 0;
    try { durability = genome.dimension_4_weaponizable.vulnerability_map.overall_durability_score || 0; } catch(e) {}
    if (durability) {
        var color = durability >= 7 ? "#00b894" : durability >= 4 ? "#fdcb6e" : "#e17055";
        metaHtml += '<span class="durability-score">' + durability + '/10 <span class="score-bar"><span class="score-fill" style="width:' + (durability * 10) + '%;background:' + color + '"></span></span></span> ';
    }
    if (data.extraction_date) metaHtml += '<span>' + data.extraction_date.split("T")[0] + '</span>';
    document.getElementById("genomeMetaInfo").innerHTML = metaHtml;

    var cheatSheet = null;
    try { cheatSheet = genome.dimension_5_synthesis.practitioners_cheat_sheet; } catch(e) {}
    var csHtml = "";
    if (cheatSheet) {
        csHtml = '<div class="cheat-sheet-title">Practitioner\'s Cheat Sheet</div>';
        if (cheatSheet.cite_when && cheatSheet.cite_when.length) {
            csHtml += '<div class="cheat-item"><div class="cheat-label">Cite When</div><ul class="cheat-list">';
            cheatSheet.cite_when.forEach(function (item) { csHtml += '<li>' + escapeHtml(item) + '</li>'; });
            csHtml += '</ul></div>';
        }
        if (cheatSheet.do_not_cite_when && cheatSheet.do_not_cite_when.length) {
            csHtml += '<div class="cheat-item"><div class="cheat-label">Do NOT Cite When</div><ul class="cheat-list">';
            cheatSheet.do_not_cite_when.forEach(function (item) { csHtml += '<li>' + escapeHtml(item) + '</li>'; });
            csHtml += '</ul></div>';
        }
        if (cheatSheet.killer_paragraph) {
            csHtml += '<div class="cheat-item"><div class="cheat-label">Killer Paragraph</div><div class="cheat-value">' + escapeHtml(cheatSheet.killer_paragraph) + '</div></div>';
        }
        if (cheatSheet.hidden_gem) {
            csHtml += '<div class="cheat-item"><div class="cheat-label">Hidden Gem</div><div class="cheat-value">' + escapeHtml(cheatSheet.hidden_gem) + '</div></div>';
        }
    }
    document.getElementById("genomeCheatSheet").innerHTML = csHtml;
    document.getElementById("genomeCheatSheet").style.display = csHtml ? "block" : "none";

    var dims = [
        { num: "1", label: "Visible", key: "dimension_1_visible" },
        { num: "2", label: "Structural", key: "dimension_2_structural" },
        { num: "3", label: "Invisible", key: "dimension_3_invisible" },
        { num: "4", label: "Weaponizable", key: "dimension_4_weaponizable" },
        { num: "5", label: "Synthesis", key: "dimension_5_synthesis" },
        { num: "6", label: "Audit", key: "dimension_6_audit" },
    ];

    var tabsHtml = "";
    dims.forEach(function (d, i) {
        tabsHtml += '<button class="dim-tab' + (i === 0 ? ' active' : '') + '" data-dim="' + d.num + '" data-key="' + d.key + '">D' + d.num + ': ' + d.label + '</button>';
    });
    document.getElementById("genomeDimTabs").innerHTML = tabsHtml;

    renderDimension(genome, dims[0].key);

    document.querySelectorAll(".dim-tab").forEach(function (tab) {
        tab.addEventListener("click", function () {
            document.querySelectorAll(".dim-tab").forEach(function (t) { t.classList.remove("active"); });
            tab.classList.add("active");
            renderDimension(genome, tab.getAttribute("data-key"));
        });
    });
}

function renderDimension(genome, dimKey) {
    var dimData = genome[dimKey];
    if (!dimData) {
        document.getElementById("genomeDimContent").innerHTML = '<div class="empty-state small"><p>No data for this dimension.</p></div>';
        return;
    }

    var html = "";
    var keys = Object.keys(dimData);
    keys.forEach(function (sectionKey) {
        var sectionData = dimData[sectionKey];
        if (sectionData === null || sectionData === undefined) return;
        var sectionLabel = sectionKey.replace(/_/g, " ").replace(/\b\w/g, function (c) { return c.toUpperCase(); });
        html += '<div class="genome-section">';
        html += '<div class="genome-section-header" onclick="this.parentElement.classList.toggle(\'open\')">';
        html += '<span>' + sectionLabel + '</span>';
        html += '<span class="toggle-icon">\u25B6</span>';
        html += '</div>';
        html += '<div class="genome-section-body">';
        html += renderSectionContent(sectionKey, sectionData);
        html += '</div></div>';
    });

    document.getElementById("genomeDimContent").innerHTML = html;
}

function renderSectionContent(key, data) {
    if (data === null || data === undefined) return '<span class="kv-val" style="color:#b2bec3;">N/A</span>';
    if (typeof data === "string") return '<div class="cheat-value">' + escapeHtml(data) + '</div>';
    if (typeof data === "number" || typeof data === "boolean") return '<div class="cheat-value">' + String(data) + '</div>';

    if (Array.isArray(data)) {
        if (data.length === 0) return '<span style="color:#b2bec3;">None</span>';
        if (typeof data[0] === "string") {
            var listHtml = '<ul class="cheat-list">';
            data.forEach(function (item) { listHtml += '<li>' + escapeHtml(item) + '</li>'; });
            listHtml += '</ul>';
            return listHtml;
        }
        var tableHtml = '';
        data.forEach(function (item, idx) {
            tableHtml += '<div class="genome-section" style="margin-bottom:8px;">';
            tableHtml += '<div class="genome-section-header" onclick="this.parentElement.classList.toggle(\'open\')" style="font-size:12px;">';
            var itemLabel = item.label || item.case_name || item.provision_id || item.scenario || item.stage || item.the_argument || item.observation || item.question_id || item.the_question || item.action || item.weak_point || item.what_court_assumes || ("#" + (idx + 1));
            if (typeof itemLabel === "string" && itemLabel.length > 100) itemLabel = itemLabel.substring(0, 100) + "...";
            var idStr = item.syllogism_id || item.ratio_id || item.obiter_id || item.assumption_id || item.argument_id || item.cf_id || item.alt_id || item.use_case_id || item.scenario_id || item.vuln_id || item.strategy_id || item.transplant_id || item.question_id || "";
            if (idStr) itemLabel = '<span style="color:#6c5ce7;font-weight:700;">' + escapeHtml(idStr) + '</span> ' + escapeHtml(String(itemLabel));
            else itemLabel = escapeHtml(String(itemLabel));
            var confBadge = "";
            if (item.confidence) confBadge = ' <span class="confidence-badge conf-' + item.confidence + '">' + item.confidence + '</span>';
            tableHtml += '<span>' + itemLabel + confBadge + '</span>';
            tableHtml += '<span class="toggle-icon">\u25B6</span>';
            tableHtml += '</div>';
            tableHtml += '<div class="genome-section-body">';
            tableHtml += renderObjectKV(item);
            tableHtml += '</div></div>';
        });
        return tableHtml;
    }

    if (typeof data === "object") {
        return renderObjectKV(data);
    }

    return '<div class="cheat-value">' + escapeHtml(JSON.stringify(data)) + '</div>';
}

function renderObjectKV(obj) {
    if (!obj || typeof obj !== "object") return escapeHtml(String(obj));
    var html = '<div class="genome-kv">';
    Object.keys(obj).forEach(function (k) {
        var v = obj[k];
        var label = k.replace(/_/g, " ").replace(/\b\w/g, function (c) { return c.toUpperCase(); });
        html += '<div class="kv-key">' + escapeHtml(label) + '</div>';

        if (v === null || v === undefined) {
            html += '<div class="kv-val" style="color:#b2bec3;">N/A</div>';
        } else if (k === "stress_test" && typeof v === "object") {
            html += '<div class="kv-val">' + renderStressTest(v) + '</div>';
        } else if (k === "gate_7_validation" && typeof v === "object") {
            html += '<div class="kv-val">' + renderObjectKV(v) + '</div>';
        } else if (k === "source_paragraph" || k === "source_paragraphs") {
            html += '<div class="kv-val"><span class="source-para-ref">\u00B6 ' + escapeHtml(String(v)) + '</span></div>';
        } else if (k === "confidence") {
            html += '<div class="kv-val"><span class="confidence-badge conf-' + v + '">' + v + '</span></div>';
        } else if (Array.isArray(v)) {
            if (v.length === 0) {
                html += '<div class="kv-val" style="color:#b2bec3;">None</div>';
            } else if (typeof v[0] === "string") {
                html += '<div class="kv-val"><ul class="cheat-list">';
                v.forEach(function (item) { html += '<li>' + escapeHtml(item) + '</li>'; });
                html += '</ul></div>';
            } else {
                html += '<div class="kv-val">' + renderSectionContent(k, v) + '</div>';
            }
        } else if (typeof v === "object") {
            html += '<div class="kv-val">' + renderObjectKV(v) + '</div>';
        } else {
            html += '<div class="kv-val">' + escapeHtml(String(v)) + '</div>';
        }
    });
    html += '</div>';
    return html;
}

function renderStressTest(st) {
    var html = '<div class="stress-test-block">';
    if (st.step_1_statutory_basis) {
        html += '<div class="st-label">Step 1: Statutory Basis</div><div>' + escapeHtml(st.step_1_statutory_basis) + '</div>';
    }
    if (st.step_2_structural_validity) {
        html += '<div class="st-label" style="margin-top:4px;">Step 2: Structural Validity</div><div>' + escapeHtml(st.step_2_structural_validity) + '</div>';
    }
    if (st.step_3_adversarial_challenge) {
        html += '<div class="st-label" style="margin-top:4px;">Step 3: Adversarial Challenge</div><div>' + escapeHtml(st.step_3_adversarial_challenge) + '</div>';
    }
    if (st.verdict) {
        html += '<div class="st-verdict verdict-' + st.verdict + '">' + st.verdict.replace(/_/g, " ") + '</div>';
    }
    html += '</div>';
    return html;
}

document.getElementById("downloadGenomeBtn").addEventListener("click", function () {
    if (!_currentGenomeData) return;
    var blob = new Blob([JSON.stringify(_currentGenomeData, null, 2)], { type: "application/json" });
    var url = URL.createObjectURL(blob);
    var a = document.createElement("a");
    a.href = url;
    var caseName = "";
    try { caseName = _currentGenomeData.dimension_1_visible.case_identity.case_name || "genome"; } catch(e) { caseName = "genome"; }
    a.download = caseName.replace(/[^a-zA-Z0-9]/g, "_").substring(0, 50) + "_genome.json";
    a.click();
    URL.revokeObjectURL(url);
});

document.getElementById("questionTextInput").addEventListener("input", function () {
    document.getElementById("extractQuestionsBtn").disabled = this.value.trim().length < 200;
});

document.getElementById("extractQuestionsBtn").addEventListener("click", function () {
    var btn = this;
    var body = {
        pleading_text: document.getElementById("questionTextInput").value.trim(),
        pleading_type: document.getElementById("questionTypeSelect").value,
        citation: document.getElementById("questionCitationInput").value.trim(),
    };

    btn.disabled = true;
    btn.textContent = "Extracting...";
    document.getElementById("questionProgress").style.display = "block";
    document.getElementById("questionError").style.display = "none";
    document.getElementById("questionViewerEmpty").style.display = "none";
    document.getElementById("questionViewerContent").style.display = "none";

    fetch("/api/questions/extract", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body)
    })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            btn.disabled = false;
            btn.textContent = "Extract Research Questions";
            document.getElementById("questionProgress").style.display = "none";

            if (data.error) {
                document.getElementById("questionError").textContent = data.error;
                document.getElementById("questionError").style.display = "block";
                document.getElementById("questionViewerEmpty").style.display = "block";
                return;
            }

            _currentQuestionsData = data.questions;
            renderQuestions(data);
        })
        .catch(function (err) {
            btn.disabled = false;
            btn.textContent = "Extract Research Questions";
            document.getElementById("questionProgress").style.display = "none";
            document.getElementById("questionError").textContent = err.message;
            document.getElementById("questionError").style.display = "block";
            document.getElementById("questionViewerEmpty").style.display = "block";
        });
});

function renderQuestions(data) {
    var q = data.questions;
    document.getElementById("questionViewerEmpty").style.display = "none";
    document.getElementById("questionViewerContent").style.display = "block";

    var metaHtml = "";
    if (data.cached) metaHtml += '<span class="cached-badge">Cached</span> ';
    metaHtml += '<span>' + (data.question_count || 0) + ' questions</span>';
    document.getElementById("questionMetaInfo").innerHTML = metaHtml;

    var summary = q.extraction_summary || {};
    var sumHtml = '<h4>Extraction Summary</h4>';
    sumHtml += '<div class="qs-stats">';
    sumHtml += '<div class="qs-stat">' + (summary.total_questions || 0) + '<span>Total Questions</span></div>';
    sumHtml += '<div class="qs-stat">' + (summary.critical_questions_count || 0) + '<span>Critical</span></div>';
    sumHtml += '<div class="qs-stat">' + (summary.gate_questions_count || 0) + '<span>Gate Questions</span></div>';
    sumHtml += '</div>';
    if (summary.what_judge_will_ask_first) {
        sumHtml += '<div class="qs-note"><strong>What the Judge Will Ask First:</strong> ' + escapeHtml(summary.what_judge_will_ask_first) + '</div>';
    }
    if (summary.biggest_vulnerability) {
        sumHtml += '<div class="qs-note"><strong>Biggest Vulnerability:</strong> ' + escapeHtml(summary.biggest_vulnerability) + '</div>';
    }
    if (summary.advocate_note) {
        sumHtml += '<div class="qs-note"><strong>Senior Advocate\'s Note:</strong> ' + escapeHtml(summary.advocate_note) + '</div>';
    }
    document.getElementById("questionSummary").innerHTML = sumHtml;

    var gatesHtml = "";
    var dt = q.decision_tree || {};
    var gates = dt.gate_questions || [];
    if (gates.length > 0) {
        gatesHtml += '<h4 style="margin-bottom:10px;font-size:14px;color:#e17055;">Gate Questions (Answer These First)</h4>';
        gates.forEach(function (g) {
            gatesHtml += '<div class="gate-card">';
            gatesHtml += '<div class="gate-label">' + escapeHtml(g.gate_question_id || "") + '</div>';
            gatesHtml += '<div class="gate-q">' + escapeHtml(g.question_text || "") + '</div>';
            gatesHtml += '<div class="gate-outcomes">';
            if (g.if_favourable) gatesHtml += '<div style="color:#00b894;"><strong>If Favourable:</strong> ' + escapeHtml(g.if_favourable.implication || "") + '</div>';
            if (g.if_unfavourable) gatesHtml += '<div style="color:#e17055;"><strong>If Unfavourable:</strong> ' + escapeHtml(g.if_unfavourable.implication || "") + '</div>';
            gatesHtml += '</div></div>';
        });
    }
    document.getElementById("questionGates").innerHTML = gatesHtml;

    var cats = q.question_categories || {};
    var catOrder = [
        ["jurisdictional_maintainability", "Jurisdictional & Maintainability"],
        ["limitation_delay_laches", "Limitation, Delay & Laches"],
        ["statutory_interpretation", "Statutory Interpretation"],
        ["constitutional_law", "Constitutional Law"],
        ["substantive_law_merits", "Substantive Law (Merits)"],
        ["procedural_law", "Procedural Law"],
        ["interim_relief_stay", "Interim Relief & Stay"],
        ["evidence_documentary", "Evidence & Documentary"],
        ["opposing_party_anticipation", "Opposing Party Anticipation"],
        ["precedent_chain_analysis", "Precedent Chain Analysis"],
        ["equitable_discretionary", "Equitable & Discretionary"],
        ["court_specific", "Court-Specific"],
        ["strategic_tactical", "Strategic & Tactical"],
        ["cross_statute_regulatory", "Cross-Statute & Regulatory"],
    ];

    var catsHtml = "";
    catOrder.forEach(function (c) {
        var catData = cats[c[0]];
        if (!catData || !catData.questions || catData.questions.length === 0) return;
        var questions = catData.questions;
        catsHtml += '<div class="question-category-section">';
        catsHtml += '<div class="qcat-header" onclick="this.parentElement.classList.toggle(\'open\')">';
        catsHtml += '<span>' + (catData.category_id || "") + ': ' + c[1] + '</span>';
        catsHtml += '<span class="qcat-count">' + questions.length + '</span>';
        catsHtml += '</div>';
        catsHtml += '<div class="qcat-body">';
        questions.forEach(function (qItem) {
            catsHtml += renderQuestionItem(qItem, c[0] === "opposing_party_anticipation");
        });
        catsHtml += '</div></div>';
    });
    document.getElementById("questionCategories").innerHTML = catsHtml;
}

function renderQuestionItem(q, isAnticipatory) {
    var html = '<div class="q-item">';
    html += '<div class="q-item-header">';
    html += '<span class="q-id">' + escapeHtml(q.question_id || "") + '</span>';
    html += '<span class="q-text">' + escapeHtml(isAnticipatory ? (q.research_question || q.anticipated_argument || "") : (q.question || "")) + '</span>';
    html += '</div>';

    html += '<div class="q-meta">';
    if (q.importance) html += '<span class="q-badge importance-' + q.importance + '">' + q.importance + '</span>';
    if (q.perspective) html += '<span class="q-badge perspective-' + q.perspective + '">' + q.perspective + '</span>';
    if (q.question_type) html += '<span class="q-badge type-' + q.question_type + '">' + q.question_type.replace(/_/g, " ") + '</span>';
    if (q.is_gate_question) html += '<span class="q-badge" style="background:#fff3cd;color:#856404;">GATE</span>';
    if (q.urgency) html += '<span class="q-badge" style="background:#e2e3e5;color:#383d41;">' + q.urgency.replace(/_/g, " ") + '</span>';
    if (q.likelihood) html += '<span class="q-badge" style="background:#f3e5f5;color:#6a1b9a;">' + q.likelihood + '</span>';
    html += '</div>';

    html += '<div class="q-detail">';
    if (isAnticipatory && q.anticipated_argument) {
        html += '<div><strong>Opponent\'s Argument:</strong> ' + escapeHtml(q.anticipated_argument) + '</div>';
    }
    if (q.why_this_matters) html += '<div><strong>Why it matters:</strong> ' + escapeHtml(q.why_this_matters) + '</div>';
    if (q.counter_strategy_direction) html += '<div><strong>Counter Strategy:</strong> ' + escapeHtml(q.counter_strategy_direction) + '</div>';
    if (q.fact_anchor) html += '<div><strong>Fact Anchor:</strong> ' + escapeHtml(q.fact_anchor) + '</div>';
    if (q.research_direction && !isAnticipatory) html += '<div><strong>Research Direction:</strong> ' + escapeHtml(q.research_direction) + '</div>';
    if (q.source_paragraphs) html += '<div><span class="source-para-ref">\u00B6 ' + escapeHtml(q.source_paragraphs) + '</span></div>';
    html += '</div>';

    if (q.sub_questions && q.sub_questions.length > 0) {
        html += '<div class="q-sub-questions">';
        q.sub_questions.forEach(function (sq) {
            html += '<div class="sub-q"><span class="sub-id">' + escapeHtml(sq.sub_id || "") + '</span> ' + escapeHtml(sq.sub_question || "") + '</div>';
        });
        html += '</div>';
    }

    html += '</div>';
    return html;
}

document.getElementById("downloadQuestionsBtn").addEventListener("click", function () {
    if (!_currentQuestionsData) return;
    var blob = new Blob([JSON.stringify(_currentQuestionsData, null, 2)], { type: "application/json" });
    var url = URL.createObjectURL(blob);
    var a = document.createElement("a");
    a.href = url;
    a.download = "research_questions.json";
    a.click();
    URL.revokeObjectURL(url);
});

document.getElementById("docExtractGenomeBtn").addEventListener("click", function () {
    if (!_currentDocTid) return;
    closeDoc();
    document.querySelectorAll(".nav-tab").forEach(function (t) { t.classList.remove("active"); });
    document.querySelector('.nav-tab[data-view="genomeLab"]').classList.add("active");
    document.querySelectorAll(".view-panel").forEach(function (p) { p.classList.remove("active"); });
    document.getElementById("genomeLabView").classList.add("active");
    loadCachedJudgments();
    setTimeout(function () {
        document.getElementById("genomeCachedSelect").value = String(_currentDocTid);
        updateGenomeExtractState();
    }, 500);
});
