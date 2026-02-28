let currentQuery = "";
let currentPage = 0;
let totalFound = "";

const searchInput = document.getElementById("searchInput");
const searchBtn = document.getElementById("searchBtn");
const filtersToggle = document.getElementById("filtersToggle");
const filtersPanel = document.getElementById("filtersPanel");
const resultsArea = document.getElementById("resultsArea");
const docOverlay = document.getElementById("docOverlay");
const docTitle = document.getElementById("docTitle");
const docBody = document.getElementById("docBody");
const docClose = document.getElementById("docClose");

searchBtn.addEventListener("click", () => doSearch(0));
searchInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") doSearch(0);
});

filtersToggle.addEventListener("click", () => {
    filtersPanel.classList.toggle("active");
    filtersToggle.textContent = filtersPanel.classList.contains("active")
        ? "Hide filters"
        : "Show filters";
});

docClose.addEventListener("click", closeDoc);
docOverlay.addEventListener("click", (e) => {
    if (e.target === docOverlay) closeDoc();
});

document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeDoc();
});

function doSearch(page) {
    const q = searchInput.value.trim();
    if (!q) return;

    currentQuery = q;
    currentPage = page;

    const params = new URLSearchParams({ q, page });

    const doctype = document.getElementById("filterDoctype").value.trim();
    const fromdate = document.getElementById("filterFrom").value.trim();
    const todate = document.getElementById("filterTo").value.trim();
    const sortby = document.getElementById("filterSort").value;

    if (doctype) params.set("doctype", doctype);
    if (fromdate) params.set("fromdate", fromdate);
    if (todate) params.set("todate", todate);
    if (sortby) params.set("sortby", sortby);

    searchBtn.disabled = true;
    searchBtn.textContent = "Searching...";

    resultsArea.innerHTML =
        '<div class="loading"><div class="spinner"></div><p>Searching Indian legal database...</p></div>';

    fetch(`/api/search?${params}`)
        .then((r) => r.json())
        .then((data) => {
            searchBtn.disabled = false;
            searchBtn.textContent = "Search";
            renderResults(data);
        })
        .catch((err) => {
            searchBtn.disabled = false;
            searchBtn.textContent = "Search";
            resultsArea.innerHTML = `<div class="error-msg">Something went wrong: ${err.message}</div>`;
        });
}

function renderResults(data) {
    if (data.error || data.errmsg) {
        resultsArea.innerHTML = `<div class="error-msg">${data.error || data.errmsg}</div>`;
        return;
    }

    if (!data.docs || data.docs.length === 0) {
        resultsArea.innerHTML =
            '<div class="empty-state"><h3>No results found</h3><p>Try a different query or adjust your filters.</p></div>';
        return;
    }

    totalFound = data.found || "";

    let html = `<div class="results-info">Showing <strong>${totalFound}</strong> for "<strong>${escapeHtml(currentQuery)}</strong>"</div>`;

    for (const doc of data.docs) {
        html += `
      <div class="result-card" onclick="openDoc(${doc.tid})">
        <div class="result-title">${doc.title || "Untitled"}</div>
        <div class="result-meta">
          <span>${doc.docsource || ""}</span>
          <span>${doc.publishdate || ""}</span>
          ${doc.numcites ? `<span>Cites: ${doc.numcites}</span>` : ""}
          ${doc.numcitedby ? `<span>Cited by: ${doc.numcitedby}</span>` : ""}
        </div>
        <div class="result-snippet">${doc.headline || ""}</div>
      </div>`;
    }

    html += renderPagination(data.docs.length);
    resultsArea.innerHTML = html;
}

function renderPagination(docCount) {
    let html = '<div class="pagination">';

    if (currentPage > 0) {
        html += `<button class="page-btn" onclick="doSearch(${currentPage - 1})">Previous</button>`;
    }

    const start = Math.max(0, currentPage - 3);
    const end = currentPage + 4;

    for (let i = start; i < end; i++) {
        if (i < currentPage || docCount === 10) {
            html += `<button class="page-btn ${i === currentPage ? "active" : ""}" onclick="doSearch(${i})">${i + 1}</button>`;
        } else if (i === currentPage) {
            html += `<button class="page-btn active">${i + 1}</button>`;
        }
    }

    if (docCount === 10) {
        html += `<button class="page-btn" onclick="doSearch(${currentPage + 1})">Next</button>`;
    }

    html += "</div>";
    return html;
}

function openDoc(docid) {
    docOverlay.classList.add("active");
    docTitle.textContent = "Loading...";
    docBody.innerHTML =
        '<div class="loading"><div class="spinner"></div><p>Fetching document...</p></div>';

    fetch(`/api/doc/${docid}`)
        .then((r) => r.json())
        .then((data) => {
            if (data.error || data.errmsg) {
                docTitle.textContent = "Error";
                docBody.innerHTML = `<p>${data.error || data.errmsg}</p>`;
                return;
            }
            docTitle.textContent = data.title || "Document";
            docBody.innerHTML = data.doc || "<p>No content available.</p>";
        })
        .catch((err) => {
            docTitle.textContent = "Error";
            docBody.innerHTML = `<p>${err.message}</p>`;
        });
}

function closeDoc() {
    docOverlay.classList.remove("active");
}

function escapeHtml(text) {
    const el = document.createElement("span");
    el.textContent = text;
    return el.innerHTML;
}
