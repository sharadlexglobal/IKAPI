let currentQuery = "";
let currentPage = 0;
let totalResults = 0;
var PAGE_SIZE = 10;
var isSmartSearchLoading = false;

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
    if (e.key === "Escape") closeDoc();
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
            '</div>';
    }

    html += renderPagination(totalPages);
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

function escapeHtml(text) {
    var el = document.createElement("span");
    el.textContent = text;
    return el.innerHTML;
}
