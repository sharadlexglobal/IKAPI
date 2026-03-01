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
        if (typeof closePipelineModal === "function") closePipelineModal();
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
            var activeSubtab = document.querySelector(".genome-sub-tab.active");
            if (activeSubtab && activeSubtab.getAttribute("data-subtab") === "genomeDatabase") {
                loadGenomeDatabase();
            }
        }
        if (view === "pipeline") {
            loadPipelineJobs();
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
        if (subtab === "genomeDatabase") {
            loadGenomeDatabase();
        }
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

var _pipelinePollingTimer = null;
var _currentPipelineJobId = null;
var _currentMemoData = null;

var PIPELINE_STEPS_DEF = [
    { name: "EXTRACTING_QUESTIONS", label: "Questions" },
    { name: "GENERATING_QUERIES", label: "Queries" },
    { name: "SEARCHING", label: "Search" },
    { name: "FILTERING", label: "Filter" },
    { name: "FETCHING_DOCS", label: "Fetch" },
    { name: "EXTRACTING_GENOMES", label: "Genomes" },
    { name: "SYNTHESIZING", label: "Synthesis" }
];

function loadPipelineJobs() {
    fetch("/api/pipeline/list")
        .then(function (r) { return r.json(); })
        .then(function (jobs) {
            var container = document.getElementById("pipelineJobsList");
            if (!jobs || jobs.length === 0) {
                container.innerHTML = '<div class="empty-state"><h3>No Research Jobs</h3><p>Submit a pleading to start an autonomous legal research pipeline.</p></div>';
                return;
            }
            var html = "";
            jobs.forEach(function (j) {
                var title = j.citation || j.client_name || "Untitled Research";
                var timeStr = j.created_at ? new Date(j.created_at).toLocaleString() : "";
                var miniSteps = renderMiniSteps(j);
                html += '<div class="pipeline-job-card" onclick="viewPipelineJob(\'' + j.job_id + '\')">';
                html += '<div class="pipeline-job-info">';
                html += '<h4>' + escapeHtml(title) + '</h4>';
                html += '<div class="job-meta">';
                if (j.pleading_type) html += '<span>' + j.pleading_type.replace(/_/g, " ") + '</span>';
                if (j.court) html += '<span>' + escapeHtml(j.court) + '</span>';
                html += '<span>' + timeStr + '</span>';
                html += '</div>';
                html += miniSteps;
                html += '</div>';
                html += '<div class="pipeline-job-right">';
                var safeJobStatus = (j.status || "").replace(/[^A-Z_]/g, "");
                html += '<span class="pipeline-status-badge status-' + safeJobStatus + '">' + escapeHtml((j.status || "").replace(/_/g, " ")) + '</span>';
                if (j.relevant_judgments) html += '<div class="job-stats">' + j.relevant_judgments + ' judgments</div>';
                if (j.genomes_extracted) html += '<div class="job-stats">' + j.genomes_extracted + ' genomes</div>';
                if (j.cost_inr > 0) html += '<div class="job-stats cost-display">\u20B9' + j.cost_inr.toFixed(2) + ' ($' + j.cost_usd.toFixed(4) + ')</div>';
                html += '</div>';
                html += '</div>';
            });
            container.innerHTML = html;
        })
        .catch(function (e) {
            console.error("Failed to load pipeline jobs:", e);
        });
}

function renderMiniSteps(job) {
    var html = '<div class="pipeline-mini-steps">';
    var stepTimestamps = [
        job.questions_completed_at, job.queries_completed_at, job.searches_completed_at,
        job.filtering_completed_at, job.fetching_completed_at, job.genomes_completed_at,
        job.synthesis_completed_at
    ];
    for (var i = 0; i < 7; i++) {
        var cls = "pipeline-mini-step";
        if (stepTimestamps[i]) {
            cls += " mini-done";
        } else if (job.current_step === PIPELINE_STEPS_DEF[i].name) {
            cls += " mini-active";
        } else if (job.status === "FAILED" && job.current_step === PIPELINE_STEPS_DEF[i].name) {
            cls += " mini-failed";
        }
        html += '<div class="' + cls + '"></div>';
    }
    html += '</div>';
    return html;
}

function viewPipelineJob(jobId) {
    _currentPipelineJobId = jobId;
    _currentMemoData = null;
    document.getElementById("pipelineJobsList").style.display = "none";
    document.getElementById("pipelineDetail").style.display = "block";
    document.querySelector(".pipeline-header-row").style.display = "none";
    document.getElementById("pipelineMemoSection").style.display = "none";
    document.getElementById("pipelineMemoContent").innerHTML = "";
    document.getElementById("pipelineErrorBox").style.display = "none";
    var costBd = document.getElementById("pipelineCostBreakdown");
    if (costBd) { costBd.innerHTML = ""; costBd.style.display = "none"; }
    fetchPipelineStatus(jobId);
    startPipelinePolling(jobId);
}

function closePipelineDetail() {
    stopPipelinePolling();
    _currentPipelineJobId = null;
    document.getElementById("pipelineJobsList").style.display = "";
    document.getElementById("pipelineDetail").style.display = "none";
    document.querySelector(".pipeline-header-row").style.display = "";
    loadPipelineJobs();
}

document.getElementById("pipelineBackBtn").addEventListener("click", closePipelineDetail);

function fetchPipelineStatus(jobId) {
    fetch("/api/pipeline/status/" + jobId)
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (data.error) return;
            renderPipelineDetail(data);
            if (data.status === "COMPLETED" || data.status === "FAILED") {
                stopPipelinePolling();
                if (data.status === "COMPLETED") {
                    loadPipelineMemo(jobId);
                }
            }
        })
        .catch(function (e) { console.error("Pipeline status fetch failed:", e); });
}

function startPipelinePolling(jobId) {
    stopPipelinePolling();
    _pipelinePollingTimer = setInterval(function () {
        fetchPipelineStatus(jobId);
    }, 5000);
}

function stopPipelinePolling() {
    if (_pipelinePollingTimer) {
        clearInterval(_pipelinePollingTimer);
        _pipelinePollingTimer = null;
    }
}

function renderPipelineDetail(data) {
    var title = data.citation || "Research Job";
    document.getElementById("pipelineDetailTitle").textContent = title;

    var meta = "";
    if (data.pleading_type) meta += '<span>' + escapeHtml(data.pleading_type.replace(/_/g, " ")) + '</span>';
    if (data.created_at) meta += '<span>Started: ' + new Date(data.created_at).toLocaleString() + '</span>';
    if (data.completed_at) meta += '<span>Completed: ' + new Date(data.completed_at).toLocaleString() + '</span>';
    document.getElementById("pipelineDetailMeta").innerHTML = meta;

    var safeStatus = (data.status || "").replace(/[^A-Z_]/g, "");
    var statusEl = document.getElementById("pipelineDetailStatus");
    statusEl.className = "pipeline-status-badge status-" + safeStatus;
    statusEl.textContent = (data.status || "").replace(/_/g, " ");

    var retryBtn = document.getElementById("pipelineRetryBtn");
    retryBtn.style.display = data.status === "FAILED" ? "" : "none";

    var stepsHtml = "";
    var steps = data.steps || [];
    steps.forEach(function (s) {
        var cls = "pipeline-step";
        if (s.status === "COMPLETED") cls += " step-done";
        else if (s.status === "IN_PROGRESS") cls += " step-active";
        else if (data.status === "FAILED" && data.current_step === s.name) cls += " step-failed";
        else cls += " step-pending";

        var countText = "";
        if (s.name === "EXTRACTING_QUESTIONS" && data.stats.total_questions) countText = data.stats.total_questions + " found";
        if (s.name === "GENERATING_QUERIES" && data.stats.total_queries) countText = data.stats.total_queries + " queries";
        if (s.name === "SEARCHING" && data.stats.total_searches) countText = data.stats.total_searches + " done";
        if (s.name === "FILTERING" && (data.stats.total_results || data.stats.relevant_judgments)) countText = (data.stats.relevant_judgments || 0) + "/" + (data.stats.total_results || 0);
        if (s.name === "EXTRACTING_GENOMES" && data.stats.genomes_extracted) countText = data.stats.genomes_extracted + " done";

        stepsHtml += '<div class="' + cls + '">';
        stepsHtml += '<span class="step-label">' + s.label + '</span>';
        if (countText) stepsHtml += '<span class="step-count">' + countText + '</span>';
        stepsHtml += '</div>';
    });
    document.getElementById("pipelineStepsBar").innerHTML = stepsHtml;

    var statsHtml = "";
    var statItems = [
        { value: data.stats.total_questions || 0, label: "Questions" },
        { value: data.stats.total_queries || 0, label: "Queries" },
        { value: data.stats.total_results || 0, label: "Results" },
        { value: data.stats.relevant_judgments || 0, label: "Relevant" },
        { value: data.stats.genomes_extracted || 0, label: "Genomes" }
    ];
    statItems.forEach(function (s) {
        statsHtml += '<div class="pipeline-stat-card"><span class="stat-value">' + s.value + '</span><span class="stat-label">' + s.label + '</span></div>';
    });

    var costData = data.cost || {};
    var costInr = costData.total_inr || 0;
    var costUsd = costData.total_usd || 0;
    if (costInr > 0 || costUsd > 0) {
        statsHtml += '<div class="pipeline-stat-card cost-stat-card"><span class="stat-value">\u20B9' + costInr.toFixed(2) + '</span><span class="stat-label">Cost ($' + costUsd.toFixed(4) + ')</span></div>';
    }

    document.getElementById("pipelineStatsGrid").innerHTML = statsHtml;

    var costBreakdownEl = document.getElementById("pipelineCostBreakdown");
    if (costBreakdownEl) {
        var bd = costData.breakdown || {};
        if (costInr > 0) {
            var bdHtml = '<div class="cost-breakdown-section"><h5>Cost Breakdown</h5><table class="cost-breakdown-table"><thead><tr><th>Step</th><th>Type</th><th>Details</th><th>Cost (INR)</th><th>Cost (USD)</th></tr></thead><tbody>';
            var stepOrder = ["question_extraction", "query_generation", "ik_search", "relevance_filtering", "doc_fetching", "genome_extraction", "synthesis"];
            var stepLabels = {
                "question_extraction": "Question Extraction",
                "query_generation": "Query Generation",
                "ik_search": "IK Search",
                "relevance_filtering": "Relevance Filtering",
                "doc_fetching": "Doc Fetching",
                "genome_extraction": "Genome Extraction",
                "synthesis": "Synthesis"
            };
            stepOrder.forEach(function (key) {
                var step = bd[key];
                if (!step) return;
                var stepTotal = step.step_total_usd || 0;
                if (stepTotal <= 0 && !(step.search_count > 0 || step.document_count > 0)) return;
                var typeStr = step.claude_usd ? "Claude API" : "IK API";
                var detailParts = [];
                if (step.input_tokens) detailParts.push(step.input_tokens.toLocaleString() + " in");
                if (step.output_tokens) detailParts.push(step.output_tokens.toLocaleString() + " out");
                if (step.api_calls) detailParts.push(step.api_calls + " calls");
                if (step.search_count) detailParts.push(step.search_count + " searches");
                if (step.document_count) detailParts.push(step.document_count + " docs");
                if (step.model) detailParts.push(step.model.replace("claude-", "").replace("-20240307", "").replace("-20250514", ""));
                bdHtml += '<tr><td>' + (stepLabels[key] || key) + '</td><td>' + typeStr + '</td><td>' + detailParts.join(", ") + '</td><td>\u20B9' + (step.step_total_inr || 0).toFixed(2) + '</td><td>$' + stepTotal.toFixed(4) + '</td></tr>';
            });
            bdHtml += '<tr class="cost-total-row"><td colspan="3"><strong>Total</strong></td><td><strong>\u20B9' + costInr.toFixed(2) + '</strong></td><td><strong>$' + costUsd.toFixed(4) + '</strong></td></tr>';
            bdHtml += '</tbody></table><div class="cost-rate-note">Exchange rate: 1 USD = \u20B995.00</div></div>';
            costBreakdownEl.innerHTML = bdHtml;
            costBreakdownEl.style.display = "";
        } else {
            costBreakdownEl.innerHTML = "";
            costBreakdownEl.style.display = "none";
        }
    }

    var errorBox = document.getElementById("pipelineErrorBox");
    if (data.error_message) {
        errorBox.innerHTML = '<strong>Error:</strong> ' + escapeHtml(data.error_message);
        errorBox.style.display = "";
    } else {
        errorBox.style.display = "none";
    }
}

function loadPipelineMemo(jobId) {
    fetch("/api/pipeline/result/" + jobId)
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (!data.research_memo) return;
            _currentMemoData = data.research_memo;
            document.getElementById("pipelineMemoSection").style.display = "";
            renderMemo(data.research_memo);
        })
        .catch(function (e) { console.error("Failed to load memo:", e); });
}

function renderMemo(memo) {
    var container = document.getElementById("pipelineMemoContent");
    var html = "";

    if (memo.executive_summary) {
        html += '<div class="memo-executive">' + escapeHtml(memo.executive_summary).replace(/\n/g, "<br>") + '</div>';
    }

    if (memo.overall_case_strength) {
        html += '<div class="memo-strength ' + memo.overall_case_strength + '">' + memo.overall_case_strength.replace(/_/g, " ") + '</div>';
    }

    if (memo.advocate_perspective) {
        html += '<div class="memo-section"><h4>Advocate Perspective</h4>';
        var ap = memo.advocate_perspective;
        if (ap.strongest_arguments) {
            ap.strongest_arguments.forEach(function (arg) {
                html += '<div class="memo-argument-card">';
                html += '<h5>' + escapeHtml(arg.argument || "") + '<span class="confidence-tag ' + (arg.confidence || "") + '">' + (arg.confidence || "") + '</span></h5>';
                if (arg.supporting_judgments) {
                    arg.supporting_judgments.forEach(function (j) {
                        html += '<div class="memo-judgment-ref"><span class="tid-link" onclick="openDoc(' + j.tid + ')">' + escapeHtml(j.case_name || "TID " + j.tid) + '</span>';
                        if (j.why_helpful) html += ' — ' + escapeHtml(j.why_helpful);
                        if (j.durability_score) html += ' (Durability: ' + j.durability_score + '/10)';
                        html += '</div>';
                    });
                }
                html += '</div>';
            });
        }
        if (ap.recommended_citation_strategy) {
            html += '<p style="margin-top:10px;font-size:13px;color:#636e72;"><strong>Citation Strategy:</strong> ' + escapeHtml(ap.recommended_citation_strategy) + '</p>';
        }
        html += '</div>';
    }

    if (memo.opponent_perspective) {
        html += '<div class="memo-section"><h4>Opponent Perspective</h4>';
        var op = memo.opponent_perspective;
        if (op.likely_counter_arguments) {
            op.likely_counter_arguments.forEach(function (arg) {
                html += '<div class="memo-argument-card opponent">';
                html += '<h5>' + escapeHtml(arg.argument || "") + '<span class="confidence-tag ' + (arg.severity || "") + '">' + (arg.severity || "") + '</span></h5>';
                if (arg.dangerous_judgments) {
                    arg.dangerous_judgments.forEach(function (j) {
                        html += '<div class="memo-judgment-ref"><span class="tid-link" onclick="openDoc(' + j.tid + ')">' + escapeHtml(j.case_name || "TID " + j.tid) + '</span>';
                        if (j.how_opponent_will_use) html += ' — ' + escapeHtml(j.how_opponent_will_use);
                        html += '</div>';
                        if (j.counter_strategy) html += '<div class="memo-judgment-ref" style="color:#155724;">Counter: ' + escapeHtml(j.counter_strategy) + '</div>';
                    });
                }
                html += '</div>';
            });
        }
        if (op.weakest_points_in_pleading && op.weakest_points_in_pleading.length) {
            html += '<div style="margin-top:12px;"><strong style="font-size:13px;">Weakest Points:</strong>';
            op.weakest_points_in_pleading.forEach(function (p) {
                html += '<div class="memo-gap-item">' + escapeHtml(p) + '</div>';
            });
            html += '</div>';
        }
        html += '</div>';
    }

    if (memo.judicial_perspective) {
        html += '<div class="memo-section"><h4>Judicial Perspective</h4>';
        var jp = memo.judicial_perspective;
        if (jp.likely_first_questions && jp.likely_first_questions.length) {
            html += '<strong style="font-size:13px;">Likely First Questions from Bench:</strong>';
            jp.likely_first_questions.forEach(function (q) {
                html += '<div class="memo-action-item">' + escapeHtml(q) + '</div>';
            });
        }
        if (jp.what_will_persuade_bench) {
            html += '<p style="margin-top:10px;font-size:13px;"><strong>What Will Persuade:</strong> ' + escapeHtml(jp.what_will_persuade_bench) + '</p>';
        }
        html += '</div>';
    }

    if (memo.issue_wise_analysis && memo.issue_wise_analysis.length) {
        html += '<div class="memo-section"><h4>Issue-Wise Analysis</h4>';
        memo.issue_wise_analysis.forEach(function (issue) {
            html += '<div class="memo-issue-card">';
            html += '<div class="issue-header"><h5>' + escapeHtml(issue.issue || "") + '</h5>';
            html += '<div class="memo-issue-badges">';
            if (issue.gate_question) html += '<span class="risk-badge" style="background:#fff3cd;color:#856404;">GATE</span>';
            if (issue.risk_level) html += '<span class="risk-badge ' + issue.risk_level + '">' + issue.risk_level + '</span>';
            if (issue.likely_outcome) html += '<span class="risk-badge" style="background:#e8f0fe;color:#1a56db;">' + issue.likely_outcome + '</span>';
            html += '</div></div>';
            if (issue.for_petitioner && issue.for_petitioner.argument_chain) {
                html += '<div style="font-size:13px;margin-bottom:8px;"><strong>For Petitioner:</strong> ' + escapeHtml(issue.for_petitioner.argument_chain) + '</div>';
            }
            if (issue.for_respondent && issue.for_respondent.argument_chain) {
                html += '<div style="font-size:13px;"><strong>For Respondent:</strong> ' + escapeHtml(issue.for_respondent.argument_chain) + '</div>';
            }
            html += '</div>';
        });
        html += '</div>';
    }

    if (memo.citation_matrix) {
        html += '<div class="memo-section"><h4>Citation Matrix</h4>';
        html += '<table class="memo-citation-table"><thead><tr><th>Category</th><th>Case</th><th>Notes</th></tr></thead><tbody>';
        var cm = memo.citation_matrix;
        if (cm.must_cite) cm.must_cite.forEach(function (c) {
            html += '<tr><td style="color:#155724;font-weight:600;">Must Cite</td><td><span class="tid-link" onclick="openDoc(' + c.tid + ')">' + escapeHtml(c.case_name || "TID " + c.tid) + '</span></td><td>' + escapeHtml(c.reason || "") + '</td></tr>';
        });
        if (cm.good_to_cite) cm.good_to_cite.forEach(function (c) {
            html += '<tr><td style="color:#0369a1;">Good to Cite</td><td><span class="tid-link" onclick="openDoc(' + c.tid + ')">' + escapeHtml(c.case_name || "TID " + c.tid) + '</span></td><td>' + escapeHtml(c.reason || "") + '</td></tr>';
        });
        if (cm.cite_with_caution) cm.cite_with_caution.forEach(function (c) {
            html += '<tr><td style="color:#856404;">Caution</td><td><span class="tid-link" onclick="openDoc(' + c.tid + ')">' + escapeHtml(c.case_name || "TID " + c.tid) + '</span></td><td>' + escapeHtml(c.risk || "") + '</td></tr>';
        });
        if (cm.opponent_will_cite) cm.opponent_will_cite.forEach(function (c) {
            html += '<tr><td style="color:#721c24;">Opponent</td><td><span class="tid-link" onclick="openDoc(' + c.tid + ')">' + escapeHtml(c.case_name || "TID " + c.tid) + '</span></td><td>' + escapeHtml(c.counter || "") + '</td></tr>';
        });
        html += '</tbody></table></div>';
    }

    if (memo.research_gaps && memo.research_gaps.length) {
        html += '<div class="memo-section"><h4>Research Gaps</h4>';
        memo.research_gaps.forEach(function (g) {
            html += '<div class="memo-gap-item">' + escapeHtml(g) + '</div>';
        });
        html += '</div>';
    }

    if (memo.action_items && memo.action_items.length) {
        html += '<div class="memo-section"><h4>Action Items</h4>';
        memo.action_items.forEach(function (a) {
            html += '<div class="memo-action-item">' + escapeHtml(a) + '</div>';
        });
        html += '</div>';
    }

    container.innerHTML = html;
}

document.getElementById("downloadMemoBtn").addEventListener("click", function () {
    if (!_currentMemoData) return;
    var blob = new Blob([JSON.stringify(_currentMemoData, null, 2)], { type: "application/json" });
    var url = URL.createObjectURL(blob);
    var a = document.createElement("a");
    a.href = url;
    a.download = "research_memo.json";
    a.click();
    URL.revokeObjectURL(url);
});

document.getElementById("newPipelineBtn").addEventListener("click", function () {
    document.getElementById("pipelineSubmitModal").classList.add("active");
});

document.getElementById("pipelineModalClose").addEventListener("click", closePipelineModal);
document.getElementById("pipelineCancelBtn").addEventListener("click", closePipelineModal);

document.getElementById("pipelineSubmitModal").addEventListener("click", function (e) {
    if (e.target === this) closePipelineModal();
});

function closePipelineModal() {
    document.getElementById("pipelineSubmitModal").classList.remove("active");
}

var plTextInput = document.getElementById("plText");
var plCharCount = document.getElementById("plCharCount");
var pipelineSubmitBtn = document.getElementById("pipelineSubmitBtn");

plTextInput.addEventListener("input", function () {
    var len = plTextInput.value.length;
    plCharCount.textContent = len + " characters";
    pipelineSubmitBtn.disabled = len < 200;
});

pipelineSubmitBtn.addEventListener("click", function () {
    var text = plTextInput.value.trim();
    if (text.length < 200) return;

    var reliefLines = document.getElementById("plReliefs").value.trim();
    var reliefs = reliefLines ? reliefLines.split("\n").filter(function (l) { return l.trim(); }) : [];

    var payload = {
        pleading_text: text,
        pleading_type: document.getElementById("plPleadingType").value,
        citation: document.getElementById("plCitation").value.trim(),
        court: document.getElementById("plCourt").value.trim(),
        client_name: document.getElementById("plClientName").value.trim(),
        client_side: document.getElementById("plClientSide").value,
        opposite_party: document.getElementById("plOpposite").value.trim(),
        reliefs_sought: reliefs,
        callback_url: document.getElementById("plCallbackUrl").value.trim() || undefined
    };

    pipelineSubmitBtn.disabled = true;
    pipelineSubmitBtn.textContent = "Submitting...";

    fetch("/api/pipeline/submit", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
    })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (data.error) {
                alert("Error: " + data.error);
                pipelineSubmitBtn.disabled = false;
                pipelineSubmitBtn.textContent = "Submit for Research";
                return;
            }
            closePipelineModal();
            plTextInput.value = "";
            plCharCount.textContent = "0 characters";
            pipelineSubmitBtn.disabled = true;
            pipelineSubmitBtn.textContent = "Submit for Research";
            document.getElementById("plCitation").value = "";
            document.getElementById("plCourt").value = "";
            document.getElementById("plClientName").value = "";
            document.getElementById("plOpposite").value = "";
            document.getElementById("plReliefs").value = "";
            document.getElementById("plCallbackUrl").value = "";
            viewPipelineJob(data.job_id);
        })
        .catch(function (e) {
            alert("Submission failed: " + e.message);
            pipelineSubmitBtn.disabled = false;
            pipelineSubmitBtn.textContent = "Submit for Research";
        });
});

var _importValidated = false;

document.getElementById("importGenomeText").addEventListener("input", function () {
    _importValidated = false;
    document.getElementById("importGenomeBtn").disabled = true;
});

document.getElementById("validateGenomeBtn").addEventListener("click", function () {
    var raw = document.getElementById("importGenomeText").value.trim();
    if (!raw) {
        showImportValidation(false, ["No JSON pasted"]);
        return;
    }
    var btn = this;
    btn.disabled = true;
    btn.textContent = "Validating...";
    fetch("/api/genome/validate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ genome_json: raw })
    })
    .then(function (r) { return r.json(); })
    .then(function (data) {
        btn.disabled = false;
        btn.textContent = "Validate";
        if (data.error) {
            showImportValidation(false, [data.error]);
            return;
        }
        showImportValidation(data.valid, data.errors || []);
        if (data.valid) {
            _importValidated = true;
            document.getElementById("importGenomeBtn").disabled = false;
        }
    })
    .catch(function (e) {
        btn.disabled = false;
        btn.textContent = "Validate";
        showImportValidation(false, ["Request failed: " + e.message]);
    });
});

function showImportValidation(valid, errors) {
    var panel = document.getElementById("importValidationResult");
    if (valid) {
        var raw = document.getElementById("importGenomeText").value.trim();
        var parsed = {};
        try { parsed = JSON.parse(raw); } catch(e) {}
        var dims = ["dimension_1_visible", "dimension_2_structural", "dimension_3_invisible",
                     "dimension_4_weaponizable", "dimension_5_synthesis", "dimension_6_audit"];
        var dimStatus = "";
        dims.forEach(function(d) {
            var present = parsed[d] && typeof parsed[d] === "object";
            var count = present ? Object.keys(parsed[d]).length : 0;
            var label = d.replace("dimension_", "D").replace(/_/g, " ").replace(/\b\w/g, function(c) { return c.toUpperCase(); });
            dimStatus += '<div class="validation-dim ' + (present ? 'valid' : 'missing') + '">';
            dimStatus += '<span class="validation-icon">' + (present ? '\u2713' : '\u2717') + '</span> ';
            dimStatus += label;
            if (present) dimStatus += ' (' + count + ' sections)';
            dimStatus += '</div>';
        });
        var citation = "";
        try { citation = parsed.extraction_metadata.judgment_citation || ""; } catch(e) {}
        panel.innerHTML = '<div class="validation-success">' +
            '<h3>\u2713 Genome Valid</h3>' +
            '<p>Schema version: ' + (parsed.schema_version || "unknown") + '</p>' +
            (citation ? '<p>Citation: ' + escapeHtml(citation) + '</p>' : '') +
            '<div class="validation-dims">' + dimStatus + '</div>' +
            '<p class="validation-ready">Ready to save to database.</p>' +
            '</div>';
    } else {
        var errHtml = '<div class="validation-failure"><h3>\u2717 Validation Failed</h3><ul>';
        errors.forEach(function(e) { errHtml += '<li>' + escapeHtml(e) + '</li>'; });
        errHtml += '</ul></div>';
        panel.innerHTML = errHtml;
    }
}

document.getElementById("importCourtSelect").addEventListener("change", function () {
    var customInput = document.getElementById("importCourtInput");
    if (this.value === "custom") {
        customInput.style.display = "";
        customInput.focus();
    } else {
        customInput.style.display = "none";
        customInput.value = "";
    }
});

function getImportCourt() {
    var sel = document.getElementById("importCourtSelect").value;
    if (sel === "custom") return { court: document.getElementById("importCourtInput").value.trim(), doctype: "" };
    if (!sel) return { court: "", doctype: "" };
    if (sel.startsWith("delhidc:")) return { court: sel.substring(8), doctype: "delhidc" };
    return { court: sel, doctype: "" };
}

document.getElementById("importGenomeBtn").addEventListener("click", function () {
    if (!_importValidated) return;
    var raw = document.getElementById("importGenomeText").value.trim();
    var tid = document.getElementById("importTidInput").value.trim();
    var title = document.getElementById("importTitleInput").value.trim();
    var courtInfo = getImportCourt();
    var model = document.getElementById("importModelInput").value.trim() || "manual-import";
    var btn = this;
    btn.disabled = true;
    btn.textContent = "Saving...";
    document.getElementById("importProgress").style.display = "block";
    submitGenomeImport(raw, tid, title, courtInfo.court, model, false, btn, courtInfo.doctype);
});

function submitGenomeImport(raw, tid, title, court, model, overwrite, btn, doctype) {
    fetch("/api/genome/import", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            genome_json: raw,
            tid: tid || null,
            title: title,
            court: court,
            extraction_model: model,
            overwrite: overwrite,
            doctype: doctype || ""
        })
    })
    .then(function (r) { return r.json().then(function(d) { return {status: r.status, data: d}; }); })
    .then(function (resp) {
        var data = resp.data;
        btn.textContent = "Save to Database";
        document.getElementById("importProgress").style.display = "none";
        if (resp.status === 409 && data.error === "exists") {
            var doOverwrite = confirm("A genome already exists for TID " + tid + ". Do you want to overwrite it?");
            if (doOverwrite) {
                btn.disabled = true;
                btn.textContent = "Overwriting...";
                document.getElementById("importProgress").style.display = "block";
                submitGenomeImport(raw, tid, title, court, model, true, btn, doctype);
            } else {
                btn.disabled = false;
                showImportValidation(false, [data.message]);
            }
            return;
        }
        if (data.error) {
            var errMsg = data.error;
            if (data.validation_errors) errMsg += ": " + data.validation_errors.join(", ");
            showImportValidation(false, [errMsg]);
            btn.disabled = false;
            return;
        }
        var dcNote = doctype === "delhidc" ? '<p class="validation-ready">Also visible in the District Court tab.</p>' : '';
        var panel = document.getElementById("importValidationResult");
        panel.innerHTML = '<div class="validation-success">' +
            '<h3>\u2713 Genome Saved Successfully</h3>' +
            '<p>TID: ' + data.tid + '</p>' +
            '<p>Title: ' + escapeHtml(data.title) + '</p>' +
            '<p>' + escapeHtml(data.message) + '</p>' +
            '<p class="validation-ready">You can view it in the Genome Database tab.</p>' +
            dcNote +
            '</div>';
        document.getElementById("importGenomeText").value = "";
        document.getElementById("importTidInput").value = "";
        document.getElementById("importTitleInput").value = "";
        document.getElementById("importCourtSelect").value = "";
        document.getElementById("importCourtInput").value = "";
        document.getElementById("importCourtInput").style.display = "none";
        _importValidated = false;
    })
    .catch(function (e) {
        btn.disabled = false;
        btn.textContent = "Save to Database";
        document.getElementById("importProgress").style.display = "none";
        showImportValidation(false, ["Save failed: " + e.message]);
    });
}

var _genomeDbData = [];
var _currentDbGenome = null;

function loadGenomeDatabase(query) {
    var url = "/api/genome/database";
    if (query) url += "?q=" + encodeURIComponent(query);
    fetch(url)
    .then(function(r) { return r.json(); })
    .then(function(data) {
        if (data.error) {
            document.getElementById("genomeDbList").innerHTML = '<div class="empty-state"><p>Error: ' + escapeHtml(data.error) + '</p></div>';
            return;
        }
        _genomeDbData = data;
        renderGenomeDbList(data);
        var stats = document.getElementById("genomeDbStats");
        stats.innerHTML = data.length + ' genome' + (data.length !== 1 ? 's' : '') + ' in database';
    })
    .catch(function(e) {
        document.getElementById("genomeDbList").innerHTML = '<div class="empty-state"><p>Failed to load: ' + e.message + '</p></div>';
    });
}

function renderGenomeDbList(genomes) {
    var container = document.getElementById("genomeDbList");
    if (!genomes.length) {
        container.innerHTML = '<div class="empty-state"><h3>No Genomes Found</h3><p>Import genomes using the Import Genome tab or run genome extraction from the pipeline.</p></div>';
        return;
    }
    var html = '<div class="genome-db-grid">';
    genomes.forEach(function(g) {
        var durColor = "#b2bec3";
        var dur = g.overall_durability_score;
        if (dur) {
            durColor = dur >= 7 ? "#00b894" : dur >= 4 ? "#fdcb6e" : "#e17055";
        }
        var provHtml = "";
        if (g.provisions && g.provisions.length) {
            provHtml = '<div class="genome-card-provisions">';
            g.provisions.slice(0, 4).forEach(function(p) {
                provHtml += '<span class="provision-tag">' + escapeHtml(p) + '</span>';
            });
            if (g.provisions.length > 4) provHtml += '<span class="provision-tag more">+' + (g.provisions.length - 4) + '</span>';
            provHtml += '</div>';
        }
        html += '<div class="genome-card" data-tid="' + g.tid + '">';
        html += '<div class="genome-card-header">';
        html += '<div class="genome-card-title">' + escapeHtml(g.title) + '</div>';
        if (dur) html += '<div class="genome-card-durability" style="color:' + durColor + '">' + dur + '/10</div>';
        html += '</div>';
        html += '<div class="genome-card-meta">';
        if (g.court) html += '<span>' + escapeHtml(g.court) + '</span>';
        if (g.decided_date) html += '<span>' + escapeHtml(g.decided_date) + '</span>';
        if (g.num_cited_by) html += '<span>Cited by ' + g.num_cited_by + '</span>';
        html += '</div>';
        if (g.core_ratio) {
            html += '<div class="genome-card-ratio">' + escapeHtml(g.core_ratio.substring(0, 200)) + (g.core_ratio.length > 200 ? '...' : '') + '</div>';
        }
        html += provHtml;
        if (g.extraction_model) {
            html += '<div class="genome-card-footer"><span class="model-tag">' + escapeHtml(g.extraction_model) + '</span>';
            if (g.extraction_date) html += '<span class="date-tag">' + g.extraction_date.split("T")[0] + '</span>';
            html += '</div>';
        }
        html += '</div>';
    });
    html += '</div>';
    container.innerHTML = html;
    document.querySelectorAll(".genome-card").forEach(function(card) {
        card.addEventListener("click", function() {
            var tid = parseInt(card.getAttribute("data-tid"));
            openGenomeDbViewer(tid);
        });
    });
}

function openGenomeDbViewer(tid) {
    document.getElementById("genomeDbList").style.display = "none";
    document.getElementById("genomeDbViewer").style.display = "block";
    fetch("/api/genome/" + tid)
    .then(function(r) { return r.json(); })
    .then(function(data) {
        if (data.error) {
            document.getElementById("genomeDbViewer").innerHTML = '<p>Error: ' + escapeHtml(data.error) + '</p>';
            return;
        }
        _currentDbGenome = data;
        renderGenomeInContainer(data, "genomeDb");
    })
    .catch(function(e) {
        document.getElementById("genomeDbViewer").innerHTML = '<p>Failed: ' + e.message + '</p>';
    });
}

function renderGenomeInContainer(data, prefix) {
    var genome = data.genome;
    var metaHtml = "";
    var cert = "";
    try { cert = genome.dimension_6_audit.final_certification.certification_level || ""; } catch(e) {}
    if (cert) metaHtml += '<span class="cert-badge cert-' + cert + '">' + cert.replace(/_/g, " ") + '</span> ';
    var durability = 0;
    try { durability = genome.dimension_4_weaponizable.vulnerability_map.overall_durability_score || 0; } catch(e) {}
    if (!durability) try { durability = data.overall_durability_score || 0; } catch(e) {}
    if (durability) {
        var color = durability >= 7 ? "#00b894" : durability >= 4 ? "#fdcb6e" : "#e17055";
        metaHtml += '<span class="durability-score">' + durability + '/10 <span class="score-bar"><span class="score-fill" style="width:' + (durability * 10) + '%;background:' + color + '"></span></span></span> ';
    }
    if (data.extraction_date) metaHtml += '<span>' + data.extraction_date.split("T")[0] + '</span>';
    document.getElementById(prefix + "MetaInfo").innerHTML = metaHtml;
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
    document.getElementById(prefix + "CheatSheet").innerHTML = csHtml;
    document.getElementById(prefix + "CheatSheet").style.display = csHtml ? "block" : "none";
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
        tabsHtml += '<button class="dim-tab ' + prefix + '-dim-tab' + (i === 0 ? ' active' : '') + '" data-dim="' + d.num + '" data-key="' + d.key + '">D' + d.num + ': ' + d.label + '</button>';
    });
    document.getElementById(prefix + "DimTabs").innerHTML = tabsHtml;
    renderDimensionInContainer(genome, dims[0].key, prefix);
    document.querySelectorAll("." + prefix + "-dim-tab").forEach(function (tab) {
        tab.addEventListener("click", function () {
            document.querySelectorAll("." + prefix + "-dim-tab").forEach(function (t) { t.classList.remove("active"); });
            tab.classList.add("active");
            renderDimensionInContainer(genome, tab.getAttribute("data-key"), prefix);
        });
    });
}

function renderDimensionInContainer(genome, dimKey, prefix) {
    var dimData = genome[dimKey];
    var target = document.getElementById(prefix + "DimContent");
    if (!dimData) {
        target.innerHTML = '<div class="empty-state small"><p>No data for this dimension.</p></div>';
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
    target.innerHTML = html;
}

document.getElementById("genomeDbBackBtn").addEventListener("click", function() {
    document.getElementById("genomeDbViewer").style.display = "none";
    document.getElementById("genomeDbList").style.display = "block";
});

document.getElementById("genomeDbDownloadBtn").addEventListener("click", function() {
    if (!_currentDbGenome) return;
    var blob = new Blob([JSON.stringify(_currentDbGenome.genome, null, 2)], { type: "application/json" });
    var url = URL.createObjectURL(blob);
    var a = document.createElement("a");
    a.href = url;
    a.download = "genome_" + _currentDbGenome.tid + ".json";
    a.click();
    URL.revokeObjectURL(url);
});

document.getElementById("genomeDbSearchBtn").addEventListener("click", function() {
    var query = document.getElementById("genomeDbSearch").value.trim();
    loadGenomeDatabase(query);
});

document.getElementById("genomeDbSearch").addEventListener("keydown", function(e) {
    if (e.key === "Enter") loadGenomeDatabase(this.value.trim());
});

document.getElementById("genomeDbRefreshBtn").addEventListener("click", function() {
    document.getElementById("genomeDbSearch").value = "";
    loadGenomeDatabase();
});

document.getElementById("pipelineRetryBtn").addEventListener("click", function () {
    if (!_currentPipelineJobId) return;
    var btn = this;
    btn.disabled = true;
    btn.textContent = "Retrying...";
    fetch("/api/pipeline/retry/" + _currentPipelineJobId, { method: "POST" })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            btn.disabled = false;
            btn.textContent = "Retry";
            if (data.error) {
                alert("Retry failed: " + data.error);
                return;
            }
            startPipelinePolling(_currentPipelineJobId);
            fetchPipelineStatus(_currentPipelineJobId);
        })
        .catch(function (e) {
            btn.disabled = false;
            btn.textContent = "Retry";
            alert("Retry failed: " + e.message);
        });
});

var _taxonomyActiveCat = null;
var _taxonomyActiveTopic = null;

function loadTaxonomyStats() {
    fetch("/api/taxonomy/stats")
        .then(function (r) { return r.json(); })
        .then(function (data) {
            var bar = document.getElementById("taxonomyStatsBar");
            if (!bar) return;
            var untagged = (data.total_genomes || 0) - (data.tagged_genomes || 0);
            bar.innerHTML =
                '<div class="taxonomy-stat-item"><span class="taxonomy-stat-value">' + (data.total_categories || 0) + '</span><span class="taxonomy-stat-label">Categories</span></div>' +
                '<div class="taxonomy-stat-item"><span class="taxonomy-stat-value">' + (data.total_topics || 0) + '</span><span class="taxonomy-stat-label">Topics</span></div>' +
                '<div class="taxonomy-stat-item"><span class="taxonomy-stat-value">' + (data.total_provisions || 0) + '</span><span class="taxonomy-stat-label">Provisions</span></div>' +
                '<div class="taxonomy-stat-item"><span class="taxonomy-stat-value">' + (data.tagged_genomes || 0) + '</span><span class="taxonomy-stat-label">Tagged Genomes</span></div>' +
                (untagged > 0 ? '<div class="taxonomy-stat-item"><span class="taxonomy-stat-value" style="color:#ffcc00">' + untagged + '</span><span class="taxonomy-stat-label">Untagged</span></div>' : '');
        });
}

function loadTaxonomyCategories() {
    fetch("/api/taxonomy/categories")
        .then(function (r) { return r.json(); })
        .then(function (cats) {
            var list = document.getElementById("taxonomyCategoryList");
            if (!list) return;
            if (!cats.length) {
                list.innerHTML = '<div style="padding:16px;color:#999;font-size:0.85rem;">No categories yet. Run the seed script first.</div>';
                return;
            }
            var html = "";
            cats.forEach(function (c) {
                var isActive = _taxonomyActiveCat === c.id;
                html += '<div class="taxonomy-cat-item' + (isActive ? ' active' : '') + '" data-cat-id="' + c.id + '">' +
                    '<span class="taxonomy-cat-name">' + escapeHtml(c.name) + '</span>' +
                    '<span class="taxonomy-cat-count">' + c.genome_count + '</span></div>';
            });
            list.innerHTML = html;
            list.querySelectorAll(".taxonomy-cat-item").forEach(function (el) {
                el.addEventListener("click", function () {
                    var catId = this.getAttribute("data-cat-id");
                    _taxonomyActiveCat = catId;
                    list.querySelectorAll(".taxonomy-cat-item").forEach(function (e) { e.classList.remove("active"); });
                    this.classList.add("active");
                    document.getElementById("taxonomySearchResults").style.display = "none";
                    document.getElementById("taxonomyGenomeList").style.display = "none";
                    document.getElementById("taxonomySynthesisPanel").style.display = "none";
                    document.getElementById("taxonomyConflictPanel").style.display = "none";
                    document.getElementById("taxonomyComparePanel").style.display = "none";
                    document.getElementById("taxonomyTopicList").style.display = "";
                    loadTaxonomyTopicsWithActions(catId);
                });
            });
        });
}

function loadTaxonomyGenomes(type, id, label) {
    document.getElementById("taxonomyTopicList").style.display = "none";
    document.getElementById("taxonomySearchResults").style.display = "none";
    document.getElementById("taxonomySynthesisPanel").style.display = "none";
    document.getElementById("taxonomyConflictPanel").style.display = "none";
    document.getElementById("taxonomyComparePanel").style.display = "none";
    var genomeSection = document.getElementById("taxonomyGenomeList");
    genomeSection.style.display = "";
    document.getElementById("taxonomyGenomeListTitle").textContent = label;
    var cardsDiv = document.getElementById("taxonomyGenomeCards");
    cardsDiv.innerHTML = '<div class="empty-state"><p>Loading genomes...</p></div>';

    var url = type === "topic"
        ? "/api/taxonomy/topics/" + encodeURIComponent(id) + "/genomes"
        : "/api/taxonomy/categories/" + encodeURIComponent(id) + "/genomes";

    fetch(url)
        .then(function (r) { return r.json(); })
        .then(function (genomes) {
            if (!genomes.length) {
                cardsDiv.innerHTML = '<div class="empty-state"><p>No genomes linked to this ' + type + '.</p></div>';
                return;
            }
            var html = "";
            genomes.forEach(function (g) {
                var ds = g.durability_score;
                var dsColor = ds >= 8 ? "#27ae60" : ds >= 6 ? "#f39c12" : ds >= 4 ? "#e67e22" : "#e74c3c";
                var dsWidth = ds ? (ds * 10) + "%" : "0%";
                html += '<div class="taxonomy-genome-card" data-tid="' + g.tid + '">' +
                    '<div class="taxonomy-genome-title">' + escapeHtml(g.title || 'TID ' + g.tid) + '</div>' +
                    '<div class="taxonomy-genome-meta">' +
                    (g.court_source ? '<span>' + escapeHtml(g.court_source) + '</span>' : '') +
                    (g.publish_date ? '<span>' + g.publish_date + '</span>' : '') +
                    (g.num_cited_by ? '<span>Cited: ' + g.num_cited_by + '</span>' : '') +
                    (ds ? '<span>Durability: ' + ds + '/10</span>' : '') +
                    (g.confidence && g.confidence < 1 ? '<span class="taxonomy-confidence-badge" style="background:#fff3e0;color:#e65100;">Match: ' + Math.round(g.confidence * 100) + '%</span>' : '') +
                    '</div>' +
                    (ds ? '<div class="taxonomy-durability-bar"><div class="taxonomy-durability-fill" style="width:' + dsWidth + ';background:' + dsColor + '"></div></div>' : '') +
                    '</div>';
            });
            cardsDiv.innerHTML = html;
            cardsDiv.querySelectorAll(".taxonomy-genome-card").forEach(function (el) {
                el.addEventListener("click", function () {
                    var tid = parseInt(this.getAttribute("data-tid"));
                    showGenomeFromDb(tid);
                });
            });
        });
}

function taxonomySearch(query) {
    if (!query || query.length < 2) return;
    document.getElementById("taxonomyTopicList").style.display = "none";
    document.getElementById("taxonomyGenomeList").style.display = "none";
    var resultsDiv = document.getElementById("taxonomySearchResults");
    resultsDiv.style.display = "";
    resultsDiv.innerHTML = '<div class="empty-state"><p>Searching...</p></div>';

    fetch("/api/taxonomy/search?q=" + encodeURIComponent(query))
        .then(function (r) { return r.json(); })
        .then(function (results) {
            if (!results.length) {
                resultsDiv.innerHTML = '<div class="empty-state"><p>No results found for "' + escapeHtml(query) + '"</p></div>';
                return;
            }
            var html = "";
            results.forEach(function (r) {
                var typeClass = r.result_type === "category" ? "type-category" : r.result_type === "topic" ? "type-topic" : "type-provision";
                html += '<div class="taxonomy-search-result" data-type="' + r.result_type + '" data-id="' + r.id + '">' +
                    '<span class="taxonomy-result-type ' + typeClass + '">' + r.result_type + '</span>' +
                    '<span class="taxonomy-result-name">' + escapeHtml(r.name) + '</span>' +
                    (r.detail ? '<span class="taxonomy-result-detail">' + escapeHtml(r.detail) + '</span>' : '') +
                    (r.genome_count > 0 ? '<span class="taxonomy-result-count">' + r.genome_count + ' genome' + (r.genome_count !== 1 ? 's' : '') + '</span>' : '') +
                    '</div>';
            });
            resultsDiv.innerHTML = html;
            resultsDiv.querySelectorAll(".taxonomy-search-result").forEach(function (el) {
                el.addEventListener("click", function () {
                    var type = this.getAttribute("data-type");
                    var id = this.getAttribute("data-id");
                    var name = this.querySelector(".taxonomy-result-name").textContent;
                    if (type === "category") {
                        _taxonomyActiveCat = id;
                        loadTaxonomyCategories();
                        resultsDiv.style.display = "none";
                        document.getElementById("taxonomyTopicList").style.display = "";
                        loadTaxonomyTopics(id);
                    } else if (type === "topic") {
                        loadTaxonomyGenomes("topic", id, name);
                    } else if (type === "provision") {
                        fetch("/api/taxonomy/provisions")
                            .then(function (r) { return r.json(); })
                            .then(function (provs) {
                                var prov = provs.find(function (p) { return p.id === id; });
                                if (prov && prov.category_id) {
                                    _taxonomyActiveCat = prov.category_id;
                                    loadTaxonomyCategories();
                                    resultsDiv.style.display = "none";
                                    document.getElementById("taxonomyTopicList").style.display = "";
                                    loadTaxonomyTopics(prov.category_id);
                                }
                            });
                    }
                });
            });
        });
}



function showGenomeFromDb(tid) {
    var genomeSubTabs = document.querySelectorAll(".genome-sub-tab");
    genomeSubTabs.forEach(function (t) { t.classList.remove("active"); });
    var dbTab = document.querySelector('[data-subtab="genomeDatabase"]');
    if (dbTab) dbTab.classList.add("active");
    document.querySelectorAll(".genome-panel").forEach(function (p) { p.classList.remove("active"); });
    var dbPanel = document.getElementById("genomeDatabasePanel");
    if (dbPanel) dbPanel.classList.add("active");

    var list = document.getElementById("genomeDbList");
    var viewer = document.getElementById("genomeDbViewer");
    if (list) list.style.display = "none";
    if (viewer) viewer.style.display = "";

    fetch("/api/genome/" + tid)
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (data.error) {
                alert("Could not load genome: " + data.error);
                return;
            }
            if (typeof renderGenomeInContainer === "function") {
                renderGenomeInContainer(data, "genomeDb");
            }
        });
}

var taxonomySearchBtn = document.getElementById("taxonomySearchBtn");
var taxonomySearchInput = document.getElementById("taxonomySearchInput");
if (taxonomySearchBtn) {
    taxonomySearchBtn.addEventListener("click", function () {
        taxonomySearch(taxonomySearchInput.value.trim());
    });
}
if (taxonomySearchInput) {
    taxonomySearchInput.addEventListener("keypress", function (e) {
        if (e.key === "Enter") taxonomySearch(this.value.trim());
    });
}

var taxonomyBackBtn = document.getElementById("taxonomyBackToTopics");
if (taxonomyBackBtn) {
    taxonomyBackBtn.addEventListener("click", function () {
        document.getElementById("taxonomyGenomeList").style.display = "none";
        document.getElementById("taxonomySearchResults").style.display = "none";
        document.getElementById("taxonomyTopicList").style.display = "";
        if (_taxonomyActiveCat) loadTaxonomyTopics(_taxonomyActiveCat);
    });
}

var taxonomyRetagBtn = document.getElementById("taxonomyRetagBtn");
if (taxonomyRetagBtn) {
    taxonomyRetagBtn.addEventListener("click", function () {
        if (!confirm("Re-tag all genomes? This will re-run the auto-tagger on all genomes.")) return;
        this.disabled = true;
        this.textContent = "Re-tagging...";
        var btn = this;
        fetch("/api/taxonomy/retag", { method: "POST" })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                btn.disabled = false;
                btn.textContent = "Re-tag All";
                if (data.error) { alert("Error: " + data.error); return; }
                alert("Tagged " + data.tagged + "/" + data.total + " genomes (" + data.categories_assigned + " categories, " + data.topics_assigned + " topics)");
                loadTaxonomyStats();
                loadTaxonomyCategories();
            })
            .catch(function (e) {
                btn.disabled = false;
                btn.textContent = "Re-tag All";
                alert("Re-tag failed: " + e.message);
            });
    });
}

document.querySelectorAll(".genome-sub-tab").forEach(function (tab) {
    tab.addEventListener("click", function () {
        if (this.getAttribute("data-subtab") === "taxonomyBrowser") {
            loadTaxonomyStats();
            loadTaxonomyCategories();
        }
    });
});

var _heatmapVisible = false;
var heatmapToggle = document.getElementById("heatmapToggleBtn");
if (heatmapToggle) {
    heatmapToggle.addEventListener("click", function () {
        _heatmapVisible = !_heatmapVisible;
        var dash = document.getElementById("heatmapDashboard");
        dash.style.display = _heatmapVisible ? "" : "none";
        this.textContent = _heatmapVisible ? "Hide Dashboard" : "Coverage Dashboard";
        if (_heatmapVisible) loadHeatmap();
    });
}

function loadHeatmap() {
    var grid = document.getElementById("heatmapGrid");
    var summary = document.getElementById("heatmapSummary");
    grid.innerHTML = '<div class="empty-state"><p>Loading coverage data...</p></div>';
    fetch("/api/taxonomy/heatmap")
        .then(function (r) { return r.json(); })
        .then(function (cats) {
            var totalTopics = 0, coveredTopics = 0, totalGaps = 0, strengthSum = 0, strengthCount = 0;
            cats.forEach(function (c) {
                c.topics.forEach(function (t) {
                    totalTopics++;
                    if (t.genome_count > 0) { coveredTopics++; strengthSum += t.avg_durability; strengthCount++; }
                    if (t.strength === "GAP") totalGaps++;
                });
            });
            var avgStr = strengthCount > 0 ? (strengthSum / strengthCount).toFixed(1) : "N/A";
            summary.innerHTML =
                '<div class="heatmap-stat"><span class="heatmap-stat-val">' + coveredTopics + '/' + totalTopics + '</span><span class="heatmap-stat-lbl">Topics Covered</span></div>' +
                '<div class="heatmap-stat"><span class="heatmap-stat-val">' + avgStr + '</span><span class="heatmap-stat-lbl">Avg Strength</span></div>' +
                '<div class="heatmap-stat"><span class="heatmap-stat-val' + (totalGaps > 0 ? ' heatmap-gap-count' : '') + '">' + totalGaps + '</span><span class="heatmap-stat-lbl">Gaps</span></div>';

            var html = "";
            cats.forEach(function (c) {
                if (!c.topics.length) return;
                html += '<div class="heatmap-category"><div class="heatmap-cat-header">' +
                    '<span class="heatmap-cat-name">' + escapeHtml(c.name) + '</span>' +
                    '<span class="heatmap-cat-coverage">' + c.topic_coverage + ' topics</span></div>' +
                    '<div class="heatmap-cells">';
                c.topics.forEach(function (t) {
                    var cls = "heatmap-cell heatmap-" + t.strength.toLowerCase();
                    html += '<div class="' + cls + '" data-topic-id="' + t.id + '" title="' +
                        escapeHtml(t.name) + '\nGenomes: ' + t.genome_count + '\nAvg Durability: ' + t.avg_durability +
                        (t.min_durability ? '\nRange: ' + t.min_durability + '-' + t.max_durability : '') + '">' +
                        '<span class="heatmap-cell-name">' + escapeHtml(t.name) + '</span>' +
                        '<span class="heatmap-cell-stats">' + t.genome_count + ' | ' + t.avg_durability + '</span>' +
                        '</div>';
                });
                html += '</div></div>';
            });
            grid.innerHTML = html;
            grid.querySelectorAll(".heatmap-cell").forEach(function (el) {
                el.addEventListener("click", function () {
                    var topicId = this.getAttribute("data-topic-id");
                    var topicName = this.querySelector(".heatmap-cell-name").textContent;
                    _heatmapVisible = false;
                    document.getElementById("heatmapDashboard").style.display = "none";
                    heatmapToggle.textContent = "Coverage Dashboard";
                    loadTaxonomyGenomesWithCompare("topic", topicId, topicName);
                });
            });
        });
}

var _selectedCompareGenomes = [];

function loadTaxonomyTopicsWithActions(catId) {
    var container = document.getElementById("taxonomyTopicList");
    container.innerHTML = '<div class="empty-state"><p>Loading topics...</p></div>';
    fetch("/api/taxonomy/topics?category_id=" + encodeURIComponent(catId))
        .then(function (r) { return r.json(); })
        .then(function (topics) {
            if (!topics.length) {
                container.innerHTML = '<div class="empty-state"><p>No topics defined for this category yet.</p></div>';
                return;
            }
            var html = "";
            topics.forEach(function (t) {
                var kwHtml = "";
                if (t.keywords && t.keywords.length) {
                    t.keywords.slice(0, 8).forEach(function (kw) {
                        kwHtml += '<span class="taxonomy-keyword-tag">' + escapeHtml(kw) + '</span>';
                    });
                    if (t.keywords.length > 8) kwHtml += '<span class="taxonomy-keyword-tag">+' + (t.keywords.length - 8) + ' more</span>';
                }
                html += '<div class="taxonomy-topic-card" data-topic-id="' + t.id + '">' +
                    '<div class="taxonomy-topic-header"><span class="taxonomy-topic-name">' + escapeHtml(t.name) + '</span>' +
                    '<span class="taxonomy-topic-count">' + t.genome_count + ' genome' + (t.genome_count !== 1 ? 's' : '') + '</span></div>' +
                    (t.description ? '<div class="taxonomy-topic-desc">' + escapeHtml(t.description) + '</div>' : '') +
                    (kwHtml ? '<div class="taxonomy-topic-keywords">' + kwHtml + '</div>' : '') +
                    '<div class="taxonomy-topic-actions">' +
                    '<button class="btn-sm topic-synth-btn" data-topic-id="' + t.id + '" data-topic-name="' + escapeHtml(t.name) + '">Synthesize</button>' +
                    '<button class="btn-sm btn-secondary topic-conflict-btn" data-topic-id="' + t.id + '" data-topic-name="' + escapeHtml(t.name) + '">Conflict Radar</button>' +
                    '</div></div>';
            });
            container.innerHTML = html;
            container.querySelectorAll(".taxonomy-topic-card").forEach(function (el) {
                el.addEventListener("click", function (e) {
                    if (e.target.classList.contains("topic-synth-btn") || e.target.classList.contains("topic-conflict-btn")) return;
                    var topicId = this.getAttribute("data-topic-id");
                    var topicName = this.querySelector(".taxonomy-topic-name").textContent;
                    _taxonomyActiveTopic = topicId;
                    loadTaxonomyGenomesWithCompare("topic", topicId, topicName);
                });
            });
            container.querySelectorAll(".topic-synth-btn").forEach(function (btn) {
                btn.addEventListener("click", function (e) {
                    e.stopPropagation();
                    triggerTopicSynthesis(this.getAttribute("data-topic-id"), this.getAttribute("data-topic-name"));
                });
            });
            container.querySelectorAll(".topic-conflict-btn").forEach(function (btn) {
                btn.addEventListener("click", function (e) {
                    e.stopPropagation();
                    triggerConflictScan(this.getAttribute("data-topic-id"), this.getAttribute("data-topic-name"));
                });
            });
        });
}

function triggerTopicSynthesis(topicId, topicName) {
    var panel = document.getElementById("taxonomySynthesisPanel");
    document.getElementById("taxonomyTopicList").style.display = "none";
    document.getElementById("taxonomyGenomeList").style.display = "none";
    document.getElementById("taxonomySearchResults").style.display = "none";
    document.getElementById("taxonomyConflictPanel").style.display = "none";
    document.getElementById("taxonomyComparePanel").style.display = "none";
    panel.style.display = "";
    panel.innerHTML = '<button class="btn-sm taxonomy-back-btn" id="synthBackBtn">Back to Topics</button>' +
        '<h3>Topic Synthesis: ' + escapeHtml(topicName) + '</h3>' +
        '<div class="synth-loading"><div class="spinner"></div><p>Checking for cached synthesis...</p></div>';

    document.getElementById("synthBackBtn").addEventListener("click", function () {
        panel.style.display = "none";
        document.getElementById("taxonomyTopicList").style.display = "";
        if (_taxonomyActiveCat) loadTaxonomyTopicsWithActions(_taxonomyActiveCat);
    });

    fetch("/api/taxonomy/topics/" + encodeURIComponent(topicId) + "/synthesis")
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (data.exists) {
                renderSynthesis(panel, topicName, data.synthesis, data.created_at, topicId);
            } else {
                panel.innerHTML = '<button class="btn-sm taxonomy-back-btn" id="synthBackBtn2">Back to Topics</button>' +
                    '<h3>Topic Synthesis: ' + escapeHtml(topicName) + '</h3>' +
                    '<div class="synth-loading"><div class="spinner"></div><p>Generating synthesis with AI... This may take 30-60 seconds.</p></div>';
                document.getElementById("synthBackBtn2").addEventListener("click", function () {
                    panel.style.display = "none";
                    document.getElementById("taxonomyTopicList").style.display = "";
                    if (_taxonomyActiveCat) loadTaxonomyTopicsWithActions(_taxonomyActiveCat);
                });
                fetch("/api/taxonomy/topics/" + encodeURIComponent(topicId) + "/synthesize", { method: "POST" })
                    .then(function (r) { return r.json(); })
                    .then(function (result) {
                        if (result.error) { panel.innerHTML = '<button class="btn-sm taxonomy-back-btn" onclick="document.getElementById(\'taxonomySynthesisPanel\').style.display=\'none\';document.getElementById(\'taxonomyTopicList\').style.display=\'\';">Back</button><div class="empty-state"><p>Error: ' + escapeHtml(result.error) + '</p></div>'; return; }
                        renderSynthesis(panel, topicName, result.synthesis, null, topicId);
                    });
            }
        });
}

function renderSynthesis(panel, topicName, s, createdAt, topicId) {
    var html = '<button class="btn-sm taxonomy-back-btn" id="synthBackBtnR">Back to Topics</button>';
    html += '<div class="synth-header"><h3>Topic Synthesis: ' + escapeHtml(topicName) + '</h3>';
    if (createdAt) html += '<span class="synth-date">Generated: ' + new Date(createdAt).toLocaleDateString() + '</span>';
    html += '<button class="btn-sm btn-secondary" id="synthRefreshBtn" data-topic-id="' + topicId + '" data-topic-name="' + escapeHtml(topicName) + '">Refresh</button></div>';

    var badge = s.strength_assessment || "N/A";
    var badgeCls = badge === "STRONG" ? "badge-strong" : badge === "MODERATE" ? "badge-moderate" : badge === "WEAK" ? "badge-weak" : "badge-dev";
    html += '<div class="synth-strength-badge ' + badgeCls + '">' + badge + '</div>';

    if (s.current_legal_position) {
        html += '<div class="synth-section"><h4>Current Legal Position</h4><div class="synth-text">' + escapeHtml(s.current_legal_position).replace(/\n/g, '<br>') + '</div></div>';
    }

    if (s.evolution_timeline && s.evolution_timeline.length) {
        html += '<div class="synth-section"><h4>Evolution Timeline</h4><div class="synth-timeline">';
        s.evolution_timeline.forEach(function (e) {
            html += '<div class="synth-timeline-item"><span class="synth-tl-year">' + escapeHtml(e.year_range || '') + '</span>' +
                '<span class="synth-tl-text">' + escapeHtml(e.development || '') +
                (e.key_case_tid ? ' <a class="synth-tid-link" data-tid="' + e.key_case_tid + '">[TID ' + e.key_case_tid + ']</a>' : '') +
                '</span></div>';
        });
        html += '</div></div>';
    }

    if (s.settled_propositions && s.settled_propositions.length) {
        html += '<div class="synth-section"><h4>Settled Propositions</h4>';
        s.settled_propositions.forEach(function (p) {
            var confCls = p.confidence === "HIGH" ? "conf-high" : p.confidence === "MEDIUM" ? "conf-med" : "conf-low";
            html += '<div class="synth-prop"><span class="synth-conf ' + confCls + '">' + (p.confidence || '') + '</span>' +
                '<span>' + escapeHtml(p.proposition || '') + '</span>';
            if (p.supporting_tids && p.supporting_tids.length) {
                html += '<span class="synth-tids">[TIDs: ' + p.supporting_tids.join(', ') + ']</span>';
            }
            html += '</div>';
        });
        html += '</div>';
    }

    if (s.open_questions && s.open_questions.length) {
        html += '<div class="synth-section"><h4>Open Questions</h4>';
        s.open_questions.forEach(function (q) {
            html += '<div class="synth-question"><div class="synth-q-text">' + escapeHtml(q.question || '') + '</div>';
            if (q.competing_views) {
                q.competing_views.forEach(function (v) {
                    html += '<div class="synth-view"><span class="synth-view-arrow">&#8627;</span>' + escapeHtml(v.view || '') +
                        (v.supporting_tids && v.supporting_tids.length ? ' <span class="synth-tids">[TIDs: ' + v.supporting_tids.join(', ') + ']</span>' : '') + '</div>';
                });
            }
            html += '</div>';
        });
        html += '</div>';
    }

    if (s.killer_argument) {
        html += '<div class="synth-section"><h4>Killer Arguments</h4><div class="synth-killer-grid">' +
            '<div class="synth-killer-card synth-killer-pet"><div class="synth-killer-label">For Petitioner</div>' +
            '<div class="synth-killer-text">' + escapeHtml(s.killer_argument.for_petitioner || '') + '</div></div>' +
            '<div class="synth-killer-card synth-killer-res"><div class="synth-killer-label">For Respondent</div>' +
            '<div class="synth-killer-text">' + escapeHtml(s.killer_argument.for_respondent || '') + '</div></div></div></div>';
    }

    if (s.practice_advisory) {
        html += '<div class="synth-section synth-advisory"><h4>Practice Advisory</h4><div class="synth-text">' + escapeHtml(s.practice_advisory).replace(/\n/g, '<br>') + '</div></div>';
    }

    panel.innerHTML = html;
    document.getElementById("synthBackBtnR").addEventListener("click", function () {
        panel.style.display = "none";
        document.getElementById("taxonomyTopicList").style.display = "";
        if (_taxonomyActiveCat) loadTaxonomyTopicsWithActions(_taxonomyActiveCat);
    });
    var refreshBtn = document.getElementById("synthRefreshBtn");
    if (refreshBtn) {
        refreshBtn.addEventListener("click", function () {
            panel.innerHTML = '<button class="btn-sm taxonomy-back-btn" onclick="document.getElementById(\'taxonomySynthesisPanel\').style.display=\'none\';document.getElementById(\'taxonomyTopicList\').style.display=\'\';">Back</button>' +
                '<h3>Refreshing synthesis...</h3><div class="synth-loading"><div class="spinner"></div><p>Regenerating with AI...</p></div>';
            fetch("/api/taxonomy/topics/" + encodeURIComponent(this.getAttribute("data-topic-id")) + "/synthesize", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ force: true }) })
                .then(function (r) { return r.json(); })
                .then(function (result) {
                    if (result.synthesis) renderSynthesis(panel, topicName, result.synthesis, null, topicId);
                });
        });
    }
    panel.querySelectorAll(".synth-tid-link").forEach(function (link) {
        link.addEventListener("click", function (e) {
            e.preventDefault();
            showGenomeFromDb(parseInt(this.getAttribute("data-tid")));
        });
    });
}

function triggerConflictScan(topicId, topicName) {
    var panel = document.getElementById("taxonomyConflictPanel");
    document.getElementById("taxonomyTopicList").style.display = "none";
    document.getElementById("taxonomyGenomeList").style.display = "none";
    document.getElementById("taxonomySearchResults").style.display = "none";
    document.getElementById("taxonomySynthesisPanel").style.display = "none";
    document.getElementById("taxonomyComparePanel").style.display = "none";
    panel.style.display = "";
    panel.innerHTML = '<button class="btn-sm taxonomy-back-btn" id="conflictBackBtn">Back to Topics</button>' +
        '<h3>Conflict Radar: ' + escapeHtml(topicName) + '</h3>' +
        '<div class="synth-loading"><div class="spinner"></div><p>Checking for cached scan...</p></div>';

    document.getElementById("conflictBackBtn").addEventListener("click", function () {
        panel.style.display = "none";
        document.getElementById("taxonomyTopicList").style.display = "";
        if (_taxonomyActiveCat) loadTaxonomyTopicsWithActions(_taxonomyActiveCat);
    });

    fetch("/api/taxonomy/topics/" + encodeURIComponent(topicId) + "/conflicts")
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (data.exists) {
                renderConflicts(panel, topicName, data.scan, data.created_at, topicId);
            } else {
                panel.innerHTML = '<button class="btn-sm taxonomy-back-btn" id="conflictBackBtn2">Back to Topics</button>' +
                    '<h3>Conflict Radar: ' + escapeHtml(topicName) + '</h3>' +
                    '<div class="synth-loading"><div class="spinner"></div><p>Scanning for conflicts with AI... This may take 30-60 seconds.</p></div>';
                document.getElementById("conflictBackBtn2").addEventListener("click", function () {
                    panel.style.display = "none";
                    document.getElementById("taxonomyTopicList").style.display = "";
                    if (_taxonomyActiveCat) loadTaxonomyTopicsWithActions(_taxonomyActiveCat);
                });
                fetch("/api/taxonomy/topics/" + encodeURIComponent(topicId) + "/scan-conflicts", { method: "POST" })
                    .then(function (r) { return r.json(); })
                    .then(function (result) {
                        if (result.error) { panel.innerHTML = '<button class="btn-sm taxonomy-back-btn" onclick="document.getElementById(\'taxonomyConflictPanel\').style.display=\'none\';document.getElementById(\'taxonomyTopicList\').style.display=\'\';">Back</button><div class="empty-state"><p>Error: ' + escapeHtml(result.error) + '</p></div>'; return; }
                        renderConflicts(panel, topicName, result.scan, null, topicId);
                    });
            }
        });
}

function renderConflicts(panel, topicName, scan, createdAt, topicId) {
    var html = '<button class="btn-sm taxonomy-back-btn" id="conflictBackBtnR">Back to Topics</button>';
    html += '<div class="synth-header"><h3>Conflict Radar: ' + escapeHtml(topicName) + '</h3>';
    if (createdAt) html += '<span class="synth-date">' + new Date(createdAt).toLocaleDateString() + '</span>';
    html += '<button class="btn-sm btn-secondary" id="conflictRescanBtn">Rescan</button></div>';

    var coh = scan.overall_coherence || "CONSISTENT";
    var cohCls = coh === "CONSISTENT" ? "badge-strong" : coh === "MINOR_TENSIONS" ? "badge-moderate" : coh === "SIGNIFICANT_CONFLICTS" ? "badge-weak" : "badge-dev";
    html += '<div class="conflict-coherence ' + cohCls + '">' + coh.replace(/_/g, ' ') + '</div>';
    html += '<div class="conflict-count">' + (scan.conflicts ? scan.conflicts.length : 0) + ' conflict' + ((scan.conflicts && scan.conflicts.length !== 1) ? 's' : '') + ' found in ' + (scan.total_genomes_scanned || 0) + ' genomes</div>';

    if (scan.conflicts && scan.conflicts.length) {
        scan.conflicts.sort(function (a, b) { var ord = { HIGH: 0, MEDIUM: 1, LOW: 2 }; return (ord[a.severity] || 3) - (ord[b.severity] || 3); });
        scan.conflicts.forEach(function (c) {
            var sevCls = c.severity === "HIGH" ? "sev-high" : c.severity === "MEDIUM" ? "sev-med" : "sev-low";
            html += '<div class="conflict-card">' +
                '<div class="conflict-card-header">' +
                '<span class="conflict-sev ' + sevCls + '">' + c.severity + '</span>' +
                '<span class="conflict-type">' + (c.type || '').replace(/_/g, ' ') + '</span>' +
                '</div>' +
                '<div class="conflict-desc">' + escapeHtml(c.description || '') + '</div>' +
                '<div class="conflict-positions">' +
                '<div class="conflict-pos conflict-pos-a"><span class="conflict-pos-label">Position A (TID ' + (c.genome_a ? c.genome_a.tid : '') + ')</span>' +
                '<span class="conflict-pos-case">' + escapeHtml(c.genome_a ? c.genome_a.case_name || '' : '') + '</span>' +
                '<span class="conflict-pos-text">' + escapeHtml(c.genome_a ? c.genome_a.position || '' : '') + '</span></div>' +
                '<div class="conflict-pos conflict-pos-b"><span class="conflict-pos-label">Position B (TID ' + (c.genome_b ? c.genome_b.tid : '') + ')</span>' +
                '<span class="conflict-pos-case">' + escapeHtml(c.genome_b ? c.genome_b.case_name || '' : '') + '</span>' +
                '<span class="conflict-pos-text">' + escapeHtml(c.genome_b ? c.genome_b.position || '' : '') + '</span></div></div>' +
                '<div class="conflict-resolution"><strong>Resolution:</strong> ' + escapeHtml(c.resolution_strategy || '') + '</div>' +
                '<div class="conflict-action"><strong>Action:</strong> ' + escapeHtml(c.advocate_action || '') + '</div>' +
                '</div>';
        });
    } else {
        html += '<div class="empty-state"><p>No conflicts detected. The case law on this topic appears consistent.</p></div>';
    }

    panel.innerHTML = html;
    document.getElementById("conflictBackBtnR").addEventListener("click", function () {
        panel.style.display = "none";
        document.getElementById("taxonomyTopicList").style.display = "";
        if (_taxonomyActiveCat) loadTaxonomyTopicsWithActions(_taxonomyActiveCat);
    });
    var rescan = document.getElementById("conflictRescanBtn");
    if (rescan) {
        rescan.addEventListener("click", function () {
            panel.innerHTML = '<button class="btn-sm taxonomy-back-btn" onclick="document.getElementById(\'taxonomyConflictPanel\').style.display=\'none\';document.getElementById(\'taxonomyTopicList\').style.display=\'\';">Back</button><h3>Rescanning...</h3><div class="synth-loading"><div class="spinner"></div></div>';
            fetch("/api/taxonomy/topics/" + encodeURIComponent(topicId) + "/scan-conflicts", { method: "POST" })
                .then(function (r) { return r.json(); })
                .then(function (result) {
                    if (result.scan) renderConflicts(panel, topicName, result.scan, null, topicId);
                });
        });
    }
}

function loadTaxonomyGenomesWithCompare(type, id, label) {
    document.getElementById("taxonomyTopicList").style.display = "none";
    document.getElementById("taxonomySearchResults").style.display = "none";
    document.getElementById("taxonomySynthesisPanel").style.display = "none";
    document.getElementById("taxonomyConflictPanel").style.display = "none";
    document.getElementById("taxonomyComparePanel").style.display = "none";
    var genomeSection = document.getElementById("taxonomyGenomeList");
    genomeSection.style.display = "";
    document.getElementById("taxonomyGenomeListTitle").textContent = label;
    var cardsDiv = document.getElementById("taxonomyGenomeCards");
    cardsDiv.innerHTML = '<div class="empty-state"><p>Loading genomes...</p></div>';
    _selectedCompareGenomes = [];
    updateCompareBtn();

    var url = type === "topic"
        ? "/api/taxonomy/topics/" + encodeURIComponent(id) + "/genomes"
        : "/api/taxonomy/categories/" + encodeURIComponent(id) + "/genomes";

    fetch(url)
        .then(function (r) { return r.json(); })
        .then(function (genomes) {
            if (!genomes.length) {
                cardsDiv.innerHTML = '<div class="empty-state"><p>No genomes linked to this ' + type + '.</p></div>';
                return;
            }
            var html = "";
            genomes.forEach(function (g) {
                var ds = g.durability_score;
                var dsColor = ds >= 8 ? "#27ae60" : ds >= 6 ? "#f39c12" : ds >= 4 ? "#e67e22" : "#e74c3c";
                var dsWidth = ds ? (ds * 10) + "%" : "0%";
                html += '<div class="taxonomy-genome-card" data-tid="' + g.tid + '">' +
                    '<div class="taxonomy-genome-card-top">' +
                    '<label class="compare-checkbox-label" onclick="event.stopPropagation();">' +
                    '<input type="checkbox" class="compare-cb" data-tid="' + g.tid + '" data-title="' + escapeHtml(g.title || 'TID ' + g.tid) + '"> Compare</label></div>' +
                    '<div class="taxonomy-genome-title">' + escapeHtml(g.title || 'TID ' + g.tid) + '</div>' +
                    '<div class="taxonomy-genome-meta">' +
                    (g.court_source ? '<span>' + escapeHtml(g.court_source) + '</span>' : '') +
                    (g.publish_date ? '<span>' + g.publish_date + '</span>' : '') +
                    (g.num_cited_by ? '<span>Cited: ' + g.num_cited_by + '</span>' : '') +
                    (ds ? '<span>Durability: ' + ds + '/10</span>' : '') +
                    (g.confidence && g.confidence < 1 ? '<span class="taxonomy-confidence-badge" style="background:#fff3e0;color:#e65100;">Match: ' + Math.round(g.confidence * 100) + '%</span>' : '') +
                    '</div>' +
                    (ds ? '<div class="taxonomy-durability-bar"><div class="taxonomy-durability-fill" style="width:' + dsWidth + ';background:' + dsColor + '"></div></div>' : '') +
                    '</div>';
            });
            cardsDiv.innerHTML = html;
            cardsDiv.querySelectorAll(".taxonomy-genome-card").forEach(function (el) {
                el.addEventListener("click", function () {
                    var tid = parseInt(this.getAttribute("data-tid"));
                    showGenomeFromDb(tid);
                });
            });
            cardsDiv.querySelectorAll(".compare-cb").forEach(function (cb) {
                cb.addEventListener("change", function () {
                    var tid = parseInt(this.getAttribute("data-tid"));
                    if (this.checked) {
                        if (_selectedCompareGenomes.length >= 3) { this.checked = false; return; }
                        _selectedCompareGenomes.push(tid);
                    } else {
                        _selectedCompareGenomes = _selectedCompareGenomes.filter(function (t) { return t !== tid; });
                    }
                    updateCompareBtn();
                });
            });
        });
}

function updateCompareBtn() {
    var btn = document.getElementById("taxonomyCompareBtn");
    if (!btn) return;
    if (_selectedCompareGenomes.length >= 2) {
        btn.style.display = "";
        btn.textContent = "Compare " + _selectedCompareGenomes.length + " Genomes";
    } else {
        btn.style.display = "none";
    }
}

var compareBtn = document.getElementById("taxonomyCompareBtn");
if (compareBtn) {
    compareBtn.addEventListener("click", function () {
        if (_selectedCompareGenomes.length < 2) return;
        loadComparison(_selectedCompareGenomes);
    });
}

function loadComparison(tids) {
    var panel = document.getElementById("taxonomyComparePanel");
    document.getElementById("taxonomyGenomeList").style.display = "none";
    document.getElementById("taxonomyTopicList").style.display = "none";
    document.getElementById("taxonomySynthesisPanel").style.display = "none";
    document.getElementById("taxonomyConflictPanel").style.display = "none";
    panel.style.display = "";
    panel.innerHTML = '<div class="synth-loading"><div class="spinner"></div><p>Loading comparison...</p></div>';

    fetch("/api/taxonomy/compare", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ tids: tids }) })
        .then(function (r) { return r.json(); })
        .then(function (genomes) {
            if (genomes.error) { panel.innerHTML = '<div class="empty-state"><p>' + escapeHtml(genomes.error) + '</p></div>'; return; }
            renderComparison(panel, genomes);
        });
}

function renderComparison(panel, genomes) {
    var colCount = genomes.length;
    var html = '<button class="btn-sm taxonomy-back-btn" id="compareBackBtn">Back to Genomes</button>';
    html += '<h3>Genome Comparison (' + colCount + ' judgments)</h3>';
    html += '<div class="compare-grid compare-cols-' + colCount + '">';

    html += '<div class="compare-row compare-header-row">';
    genomes.forEach(function (g) {
        html += '<div class="compare-col-header"><div class="compare-case-name">' + escapeHtml(g.title || 'TID ' + g.tid) + '</div>' +
            '<div class="compare-meta">' + (g.court_source || '') + ' | ' + (g.publish_date || '') + '</div>' +
            '<div class="compare-durability">Durability: ' + (g.durability_score || 'N/A') + '/10</div></div>';
    });
    html += '</div>';

    html += _compareSection("Ratio Decidendi", genomes, function (g) {
        var ratios = g.ratio_decidendi || [];
        return ratios.map(function (r) {
            return '<div class="compare-item"><strong>' + escapeHtml(r.label || '') + '</strong><br>' + escapeHtml(r.proposition || '') + '</div>';
        }).join('') || '<em>None</em>';
    });

    html += _compareSection("Provisions Engaged", genomes, function (g) {
        var provs = g.provisions_engaged || [];
        return provs.map(function (p) {
            return '<span class="compare-prov-tag">' + escapeHtml(p.provision_id || p.parent_statute || '') + '</span>';
        }).join(' ') || '<em>None</em>';
    });

    html += _compareSection("Sword Uses", genomes, function (g) {
        var swords = g.sword_uses || [];
        return swords.map(function (s) {
            return '<div class="compare-item">' + escapeHtml(s.scenario || '') + '</div>';
        }).join('') || '<em>None</em>';
    });

    html += _compareSection("Shield Uses", genomes, function (g) {
        var shields = g.shield_uses || [];
        return shields.map(function (s) {
            return '<div class="compare-item">' + escapeHtml(s.attack_being_faced || s.scenario || '') + '</div>';
        }).join('') || '<em>None</em>';
    });

    html += _compareSection("Vulnerability", genomes, function (g) {
        var vm = g.vulnerability_map || {};
        var vulns = vm.vulnerabilities || vm.attack_vectors || [];
        return vulns.map(function (v) {
            return '<div class="compare-item compare-vuln">' + escapeHtml(v.weak_point || '') + '</div>';
        }).join('') || '<em>None identified</em>';
    });

    html += _compareSection("Cheat Sheet", genomes, function (g) {
        var cs = g.cheat_sheet || {};
        var out = '';
        var cw = cs.cite_when;
        if (cw) {
            if (Array.isArray(cw)) out += '<div class="compare-cite"><strong>Cite when:</strong> ' + cw.map(function (c) { return escapeHtml(String(c)); }).join('; ') + '</div>';
            else out += '<div class="compare-cite"><strong>Cite when:</strong> ' + escapeHtml(String(cw)) + '</div>';
        }
        var dc = cs.do_not_cite_when || cs.dont_cite_when;
        if (dc) {
            if (Array.isArray(dc)) out += '<div class="compare-nocite"><strong>Don\'t cite:</strong> ' + dc.map(function (c) { return escapeHtml(String(c)); }).join('; ') + '</div>';
            else out += '<div class="compare-nocite"><strong>Don\'t cite:</strong> ' + escapeHtml(String(dc)) + '</div>';
        }
        var kp = cs.killer_paragraph;
        if (kp) out += '<div class="compare-killer"><strong>Killer para:</strong> ' + escapeHtml(String(kp).substring(0, 300)) + '</div>';
        return out || '<em>None</em>';
    });

    html += '</div>';
    panel.innerHTML = html;

    document.getElementById("compareBackBtn").addEventListener("click", function () {
        panel.style.display = "none";
        document.getElementById("taxonomyGenomeList").style.display = "";
    });
}

function _compareSection(title, genomes, extractFn) {
    var html = '<div class="compare-row"><div class="compare-row-label">' + title + '</div>';
    genomes.forEach(function (g) {
        html += '<div class="compare-cell">' + extractFn(g) + '</div>';
    });
    html += '</div>';
    return html;
}

var _dcActiveJudge = null;
var _dcActiveCourt = null;
var _dcInitialized = false;

function initDistrictCourt() {
    if (_dcInitialized) {
        return;
    }
    _dcInitialized = true;

    var citySelect = document.getElementById("dcCitySelect");
    var courtSelect = document.getElementById("dcCourtSelect");
    if (!citySelect) return;

    loadDcCourts(citySelect.value);
    citySelect.addEventListener("change", function () {
        loadDcCourts(this.value);
    });
    courtSelect.addEventListener("change", function () {
        var courtId = this.value;
        _dcActiveCourt = courtId || null;
        if (courtId) loadDcJudges(courtId);
        else document.getElementById("dcJudgeList").innerHTML = '<div class="empty-state"><p>Select a court.</p></div>';
    });

    document.getElementById("dcAddJudgeBtn").addEventListener("click", function () {
        if (!_dcActiveCourt) { alert("Select a court first."); return; }
        document.getElementById("dcAddJudgeModal").style.display = "";
    });
    document.getElementById("dcJudgeModalClose").addEventListener("click", function () {
        document.getElementById("dcAddJudgeModal").style.display = "none";
    });
    document.getElementById("dcJudgeCancelBtn").addEventListener("click", function () {
        document.getElementById("dcAddJudgeModal").style.display = "none";
    });
    document.getElementById("dcJudgeSaveBtn").addEventListener("click", function () {
        var name = document.getElementById("dcJudgeName").value.trim();
        var designation = document.getElementById("dcJudgeDesignation").value.trim();
        if (!name) { alert("Name is required."); return; }
        fetch("/api/district/judges", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name: name, designation: designation, court_id: parseInt(_dcActiveCourt) })
        }).then(function (r) { return r.json(); }).then(function (data) {
            if (data.error) { alert(data.error); return; }
            document.getElementById("dcAddJudgeModal").style.display = "none";
            document.getElementById("dcJudgeName").value = "";
            document.getElementById("dcJudgeDesignation").value = "";
            loadDcJudges(_dcActiveCourt);
        });
    });

    document.querySelectorAll(".dc-tab").forEach(function (tab) {
        tab.addEventListener("click", function () {
            document.querySelectorAll(".dc-tab").forEach(function (t) { t.classList.remove("active"); });
            this.classList.add("active");
            document.querySelectorAll(".dc-tab-content").forEach(function (c) { c.classList.remove("active"); });
            var target = this.getAttribute("data-dctab");
            document.getElementById("dcTab" + target.charAt(0).toUpperCase() + target.slice(1)).classList.add("active");
        });
    });

    document.getElementById("dcSaveOrderBtn").addEventListener("click", saveDcOrder);

    document.getElementById("dcRefreshFetchedBtn").addEventListener("click", loadDcFetchedJudgments);
    loadDcFetchedJudgments();
}

function loadDcCourts(city) {
    fetch("/api/district/courts?city=" + encodeURIComponent(city))
        .then(function (r) { return r.json(); })
        .then(function (courts) {
            var select = document.getElementById("dcCourtSelect");
            select.innerHTML = '<option value="">All Courts</option>';
            courts.forEach(function (c) {
                select.innerHTML += '<option value="' + c.id + '">' + escapeHtml(c.name) + '</option>';
            });
        });
}

function loadDcJudges(courtId) {
    fetch("/api/district/courts/" + courtId + "/judges")
        .then(function (r) { return r.json(); })
        .then(function (judges) {
            var list = document.getElementById("dcJudgeList");
            if (!judges.length) {
                list.innerHTML = '<div class="empty-state"><p>No judges added yet. Click "+ Add Judge" to start.</p></div>';
                return;
            }
            var html = "";
            judges.forEach(function (j) {
                html += '<div class="dc-judge-item' + (_dcActiveJudge === j.id ? ' active' : '') + '" data-judge-id="' + j.id + '">' +
                    '<div class="dc-judge-name">' + escapeHtml(j.name) + '</div>' +
                    '<div class="dc-judge-meta">' + escapeHtml(j.designation || '') + ' | ' + j.order_count + ' orders</div></div>';
            });
            list.innerHTML = html;
            list.querySelectorAll(".dc-judge-item").forEach(function (el) {
                el.addEventListener("click", function () {
                    _dcActiveJudge = parseInt(this.getAttribute("data-judge-id"));
                    list.querySelectorAll(".dc-judge-item").forEach(function (e) { e.classList.remove("active"); });
                    this.classList.add("active");
                    loadDcJudgeProfile(_dcActiveJudge);
                });
            });
        });
}

function loadDcJudgeProfile(judgeId) {
    document.getElementById("dcWelcome").style.display = "none";
    document.getElementById("dcJudgeProfile").style.display = "";

    fetch("/api/district/judges/" + judgeId)
        .then(function (r) { return r.json(); })
        .then(function (judge) {
            var header = document.getElementById("dcJudgeHeader");
            header.innerHTML = '<h3>' + escapeHtml(judge.name) + '</h3>' +
                '<div class="dc-judge-detail">' +
                '<span>' + escapeHtml(judge.designation || '') + '</span>' +
                '<span>' + escapeHtml(judge.court_name || '') + '</span>' +
                '<span>' + (judge.order_count || 0) + ' orders</span>' +
                '<span>' + (judge.genome_count || 0) + ' genomes</span></div>';
        });

    loadDcOrders(judgeId);

    fetch("/api/district/judges/" + judgeId + "/profile")
        .then(function (r) { return r.json(); })
        .then(function (data) {
            var content = document.getElementById("dcProfileContent");
            if (data.exists && data.profile) {
                content.innerHTML = '<pre class="dc-profile-json">' + escapeHtml(JSON.stringify(data.profile, null, 2)) + '</pre>';
            } else {
                content.innerHTML = '<div class="empty-state"><h3>Judge Mind Map</h3><p>Import at least 10 orders to enable behavioral analysis.</p>' +
                    '<button class="btn-sm" id="dcAnalyzeBtn" disabled>Analyze Judge (Coming Soon)</button></div>';
            }
        });
}

function loadDcOrders(judgeId, page) {
    page = page || 1;
    fetch("/api/district/judges/" + judgeId + "/orders?page=" + page)
        .then(function (r) { return r.json(); })
        .then(function (data) {
            var list = document.getElementById("dcOrdersList");
            if (!data.orders || !data.orders.length) {
                list.innerHTML = '<div class="empty-state"><p>No orders imported yet. Use the Import tab to add orders.</p></div>';
                return;
            }
            var html = '<table class="dc-orders-table"><thead><tr><th>Date</th><th>Case No.</th><th>Type</th><th>Parties</th></tr></thead><tbody>';
            data.orders.forEach(function (o) {
                var typeCls = "dc-type-" + (o.case_type || "misc");
                html += '<tr><td>' + (o.order_date || '') + '</td><td>' + escapeHtml(o.case_number || '') + '</td>' +
                    '<td><span class="dc-case-type-badge ' + typeCls + '">' + escapeHtml(o.case_type || '') + '</span></td>' +
                    '<td>' + escapeHtml((o.petitioner || '') + ' v. ' + (o.respondent || '')) + '</td></tr>';
            });
            html += '</tbody></table>';
            if (data.total > 20) {
                html += '<div class="dc-pagination">';
                if (page > 1) html += '<button class="btn-sm" onclick="loadDcOrders(' + judgeId + ',' + (page - 1) + ')">Prev</button>';
                html += '<span>Page ' + page + ' of ' + Math.ceil(data.total / 20) + '</span>';
                if (page * 20 < data.total) html += '<button class="btn-sm" onclick="loadDcOrders(' + judgeId + ',' + (page + 1) + ')">Next</button>';
                html += '</div>';
            }
            list.innerHTML = html;
        });
}

function saveDcOrder() {
    if (!_dcActiveJudge || !_dcActiveCourt) { alert("Select a judge first."); return; }
    var data = {
        judge_id: _dcActiveJudge,
        court_id: parseInt(_dcActiveCourt),
        case_number: document.getElementById("dcOrderCaseNum").value.trim(),
        order_date: document.getElementById("dcOrderDate").value,
        case_type: document.getElementById("dcOrderType").value,
        petitioner: document.getElementById("dcOrderPetitioner").value.trim(),
        respondent: document.getElementById("dcOrderRespondent").value.trim(),
        order_text: document.getElementById("dcOrderText").value.trim(),
    };
    if (!data.order_text) { alert("Order text is required."); return; }
    fetch("/api/district/orders", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data)
    }).then(function (r) { return r.json(); }).then(function (result) {
        if (result.error) { alert(result.error); return; }
        alert("Order saved successfully.");
        document.getElementById("dcOrderCaseNum").value = "";
        document.getElementById("dcOrderDate").value = "";
        document.getElementById("dcOrderPetitioner").value = "";
        document.getElementById("dcOrderRespondent").value = "";
        document.getElementById("dcOrderText").value = "";
        loadDcOrders(_dcActiveJudge);
        loadDcJudges(_dcActiveCourt);
    });
}

function loadDcFetchedJudgments() {
    var section = document.getElementById("dcFetchedSection");
    var listDiv = document.getElementById("dcFetchedList");
    listDiv.innerHTML = '<div class="empty-state"><p>Loading...</p></div>';

    fetch("/api/district/fetched-judgments")
        .then(function (r) { return r.json(); })
        .then(function (judgments) {
            if (!judgments.length) {
                section.style.display = "none";
                return;
            }
            section.style.display = "";
            var html = '<table class="dc-orders-table"><thead><tr>' +
                '<th>TID</th><th>Case Title</th><th>Text Size</th><th>Genome</th><th>Actions</th>' +
                '</tr></thead><tbody>';
            judgments.forEach(function (j) {
                var sizeKb = Math.round((j.html_length || 0) / 1024);
                var genomeBadge = j.has_genome
                    ? '<span class="dc-case-type-badge dc-type-final">Genome ' + (j.durability_score || '?') + '/10</span>'
                    : '<span class="dc-case-type-badge dc-type-misc">No Genome</span>';
                html += '<tr>' +
                    '<td><a href="#" class="dc-tid-link" data-tid="' + j.tid + '">' + j.tid + '</a></td>' +
                    '<td>' + escapeHtml((j.title || '').substring(0, 80)) + '</td>' +
                    '<td>' + sizeKb + ' KB</td>' +
                    '<td>' + genomeBadge + '</td>' +
                    '<td><button class="btn-sm dc-view-doc-btn" data-tid="' + j.tid + '">View</button></td>' +
                    '</tr>';
            });
            html += '</tbody></table>';
            listDiv.innerHTML = html;

            listDiv.querySelectorAll(".dc-tid-link, .dc-view-doc-btn").forEach(function (el) {
                el.addEventListener("click", function (e) {
                    e.preventDefault();
                    var tid = this.getAttribute("data-tid");
                    fetch("/api/doc/" + tid)
                        .then(function (r) { return r.json(); })
                        .then(function (data) {
                            document.getElementById("docTitle").textContent = data.title || "TID " + tid;
                            document.getElementById("docBody").innerHTML = data.doc || "<p>No content</p>";
                            document.getElementById("docOverlay").classList.add("active");
                        });
                });
            });
        });
}

document.querySelectorAll(".nav-tab").forEach(function (tab) {
    tab.addEventListener("click", function () {
        if (this.getAttribute("data-view") === "districtCourt") {
            initDistrictCourt();
        }
    });
});
