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
