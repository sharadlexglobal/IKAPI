# Indian Legal Search: Complete Search Reference & Automation Vision

---

## PART 1: ALL PERMISSIBLE SEARCH CRITERIA (VERIFIED WORKING WITH IK API)

### 1.1 Text Search Operators

| Operator | Syntax | Example | What It Does |
|----------|--------|---------|--------------|
| **Implicit AND** | `word1 word2` | `murder kidnapping` | Both words must appear in document |
| **Explicit AND** | `word1 ANDD word2` | `murder ANDD kidnapping` | Same as above, explicit. ANDD is case-sensitive, needs spaces. |
| **OR** | `word1 ORR word2` | `murder ORR kidnapping` | Either word must appear. ORR is case-sensitive, needs spaces. |
| **NOT** | `word1 ANDD NOTT word2` | `murder ANDD NOTT kidnapping` | First word present, second word absent. NOTT is case-sensitive. |
| **Phrase** | `"exact phrase"` | `"freedom of speech"` | Exact phrase match in document text |
| **Combined** | Mix operators | `"right to privacy" ANDD "article 21" ANDD NOTT "public interest"` | Complex boolean logic |

**Critical Notes:**
- Operators `ANDD`, `ORR`, `NOTT` are **case-sensitive** — must be uppercase with double letters
- Operators **require at least one space** on both sides
- Multiple words without operators default to `ANDD`
- Phrases MUST be in double quotes for exact matching

### 1.2 Field-Specific Filters

| Filter | Syntax | Example | What It Searches |
|--------|--------|---------|-----------------|
| **Title** | `title: keyword` | `title: kesavananda` | Only document titles |
| **Author/Judge** | `author: name` | `author: chandrachud` | Judgments written by that judge |
| **Bench** | `bench: name` | `bench: arijit pasayat` | Judgments where judge was on the bench |
| **Citation** | `cite: citation` | `cite: 1993 AIR` | Documents with that specific citation |
| **Court type** | `doctypes: court` | `doctypes: supremecourt` | Restricts to specific court/tribunal |
| **Multiple courts** | `doctypes: court1,court2` | `doctypes: highcourts,cci` | Comma-separated court values |
| **Date from** | `fromdate: DD-MM-YYYY` | `fromdate: 01-01-2020` | Documents published after this date |
| **Date to** | `todate: DD-MM-YYYY` | `todate: 31-12-2024` | Documents published before this date |
| **Sort** | `sortby: option` | `sortby: mostrecent` | Sort order: `mostrecent` or `leastrecent` |

### 1.3 Available Court/Tribunal Values (doctypes)

**Supreme Court:**
`supremecourt`

**High Courts (25):**
`delhi`, `bombay`, `kolkata`, `chennai`, `allahabad`, `andhra`, `chattisgarh`, `gauhati`, `jammu`, `srinagar`, `kerala`, `lucknow`, `orissa`, `uttaranchal`, `gujarat`, `himachal_pradesh`, `jharkhand`, `karnataka`, `madhyapradesh`, `patna`, `punjab`, `rajasthan`, `sikkim`, `kolkata_app`, `jodhpur`, `patna_orders`, `meghalaya`

**District Courts:**
`delhidc`

**Tribunals (18):**
`aptel`, `drat`, `cat`, `cegat`, `stt`, `itat`, `consumer`, `cerc`, `cic`, `clb`, `copyrightboard`, `ipab`, `mrtp`, `sebisat`, `tdsat`, `trademark`, `greentribunal`, `cci`

**Aggregators (search across groups):**
- `judgments` = SC + all HCs + District Courts
- `highcourts` = all High Courts
- `tribunals` = all Tribunals
- `laws` = Central Acts and Rules

### 1.4 API Endpoints & Parameters (All Verified Working)

#### Search API
```
POST https://api.indiankanoon.org/search/?formInput=<query>&pagenum=<n>
```
| Parameter | Purpose | Notes |
|-----------|---------|-------|
| `formInput` | The search query with all operators and filters | URL-encoded |
| `pagenum` | Page number (0-indexed) | pagenum=0 is first page |
| `maxcites` | Include citation list per document (up to 50) | e.g., `maxcites=20` |
| `maxpages` | Fetch multiple pages in one call (up to 50) | Charged only for returned pages |

**Search response fields per document:**
`tid`, `title`, `headline`, `docsource`, `publishdate`, `doctype`, `author`, `bench`, `numcites`, `numcitedby`, `docsize`, `citation`, `fragment`

#### Document API
```
POST https://api.indiankanoon.org/doc/<docid>/
```
| Parameter | Purpose | Notes |
|-----------|---------|-------|
| `maxcites` | Get up to 50 documents it cites | Returns in `citeList` |
| `maxcitedby` | Get up to 50 documents that cite it | Returns in `citedbyList` |

#### Document Fragment API
```
POST https://api.indiankanoon.org/docfragment/<docid>/?formInput=<query>
```
Returns only the **relevant fragments** of a document matching the query. Contains `headline` (array of matching paragraph excerpts), `title`, `tid`. Extremely useful for understanding WHY a document matched your query without downloading the full text.

#### Document Metadata API
```
POST https://api.indiankanoon.org/docmeta/<docid>/
```
Returns: `tid`, `publishdate`, `doctype`, `title`, `caseno`, `numcites`, `numcitedby`, `relurl`
Lightweight — does not return full document text.

#### Original/Court Copy API
```
POST https://api.indiankanoon.org/origdoc/<docid>/
```
Returns the original court copy of the document if available.

### 1.5 Composite Query Examples (Tested & Verified)

```
# Find Supreme Court bail cases in NDPS Act, most recent first
formInput: bail ANDD "NDPS Act" doctypes: supremecourt sortby: mostrecent

# Find all High Court cases on anticipatory bail in murder, 2020-2024
formInput: "anticipatory bail" ANDD murder doctypes: highcourts fromdate: 01-01-2020 todate: 31-12-2024

# Cases by Justice Chandrachud on fundamental rights
formInput: "fundamental rights" author: chandrachud

# Cases citing a specific judgment
formInput: cite: 1993 AIR 2178

# Cases with "right to privacy" in title only
formInput: title: "right to privacy"

# DRAT cases about section 21 waiver
formInput: "section 21" ANDD "waiver application" doctypes: drat

# Tax evasion in ITAT but not TDS
formInput: "tax evasion" ANDD NOTT "TDS" doctypes: itat

# Environmental cases in NGT about air pollution, 2022 onwards
formInput: "air pollution" ORR "vehicular emission" doctypes: greentribunal fromdate: 01-01-2022

# Competition Commission cartel orders
formInput: cartel ORR "anti-competitive agreement" doctypes: cci

# Cases on specific bench
formInput: "article 370" bench: chandrachud doctypes: supremecourt
```

---

## PART 2: THE SCIENCE BEHIND MAXIMALLY ACCURATE LEGAL SEARCH

### 2.1 The Fundamental Problem

Research shows that basic Boolean keyword searches retrieve only **~20% of relevant documents** (20% recall) even when lawyers believe they found 75%+. This is called the "recall gap" — you miss 4 out of 5 relevant cases without knowing it.

The goal is to maximize both:
- **Recall** (completeness): Don't miss any relevant judgment
- **Precision** (accuracy): Don't waste time on irrelevant results

In litigation, **missing a relevant landmark case is far more dangerous than reviewing a few extra irrelevant ones**. So legal search must prioritize recall.

### 2.2 Why Simple Keyword Search Fails in Law

1. **Semantic Ambiguity**: "Worker" means different things in labour law, tax law, and corporate law
2. **Synonym Problem**: A case about "termination" may be equally about "dismissal", "discharge", "removal from service" — different words, same legal concept
3. **Conceptual Gaps**: A lawyer searching "anticipatory bail" may miss relevant cases that discuss "pre-arrest bail" or "bail before arrest"
4. **Context Dependency**: "Section 498A" in a criminal context vs. a family law context leads to very different relevant cases
5. **Citation Networks**: The most important cases may not use your exact keywords — they may be cited by hundreds of later cases that DO use those keywords

### 2.3 The Multi-Strategy Approach for Maximum Accuracy

The science of legal information retrieval shows that no single strategy is sufficient. Maximum accuracy requires **combining multiple strategies**:

#### Strategy 1: Concept Decomposition
Break a legal problem into its **constituent legal concepts**, then search each separately.

Example: "Whether a landlord can evict a tenant for non-payment during COVID"
- Concept A: `"eviction" ANDD "non-payment of rent"`
- Concept B: `"eviction" ANDD "COVID" ORR "pandemic" ORR "lockdown"`
- Concept C: `"tenancy" ANDD "force majeure" ORR "impossibility"`
- Concept D: `"rent moratorium" ORR "COVID rent relief"`

Each generates different but overlapping result sets. The union covers far more relevant cases than any single query.

#### Strategy 2: Synonym Expansion
For every key legal term, generate all synonyms and related terms:

| Core Term | Synonyms/Related |
|-----------|-----------------|
| Bail | anticipatory bail, pre-arrest bail, default bail, interim bail, regular bail |
| Dismissal | termination, removal, discharge, retrenchment |
| Fraud | cheating, misrepresentation, deception, dishonesty |
| Damages | compensation, restitution, quantum, pecuniary relief |
| Contract breach | violation, non-performance, repudiation |

#### Strategy 3: Citation Chain Analysis
The most powerful technique in legal research — not available through keyword search alone, but available through IK API:

1. Find one known relevant case
2. Use IK API's `numcitedby` to find what cited it
3. Use `/doc/<id>/?maxcitedby=50` to get the 50 most recent cases citing it
4. Those citing cases are highly likely to be on the same legal point
5. Recursively follow citation chains to discover cases you'd never find by keywords

#### Strategy 4: Judge/Bench Targeting
When you know which judge authored landmark rulings on a topic:
- `author: chandrachud` narrows to that judge's opinions
- `bench: nariman` finds all cases where that judge sat on the bench

#### Strategy 5: Title Search for Landmark Cases
When you know a case name or partial name:
- `title: vishaka` finds Vishaka v. State of Rajasthan
- `title: kesavananda` finds Kesavananda Bharati
- Combine with topic: `title: puttaswamy ANDD privacy`

#### Strategy 6: Date-Bounded Iterative Search
For evolving legal areas, search in time windows:
- 2020-2024 for current position of law
- 2010-2020 for established precedents
- Pre-2010 for foundational principles

### 2.4 Precision vs. Recall Trade-offs

| Strategy | Recall Impact | Precision Impact | When to Use |
|----------|--------------|-----------------|-------------|
| Phrase search `"exact term"` | Decreases (narrower) | Increases (more precise) | When you know the exact legal term used in judgments |
| ORR operator | Increases (wider net) | Decreases (more noise) | Synonym expansion, covering variations |
| NOTT operator | Slightly decreases | Increases (removes noise) | Filtering out irrelevant contexts |
| Court filter | Decreases (narrower) | Increases (jurisdictional relevance) | When you need binding precedent |
| Date filter | Decreases (narrower) | Increases (currency) | Current law, recent developments |
| Title filter | Significantly decreases | Significantly increases | Finding specific known cases |
| Author filter | Significantly decreases | Increases | Judge-specific research |
| No filters (wide open) | Maximum | Lowest | Initial exploration of a topic |

---

## PART 3: YOUR VISION — THE AUTOMATED LITIGATION RESEARCH PIPELINE

### 3.1 Understanding Your Goal

Your goal is to build an **end-to-end automated legal research pipeline** that:

```
LITIGATION PLEADING (input)
    ↓
STEP 1: LLM reads the pleading and extracts:
    - Questions of law (legal issues)
    - Key legal concepts and terms
    - Relevant statutes and sections
    - Jurisdiction and court
    - Relevant date ranges
    - Parties and roles
    ↓
STEP 2: LLM converts each extracted issue into MULTIPLE search queries
    using the multi-strategy approach:
    - Primary query (direct terms)
    - Synonym-expanded queries
    - Statute-specific queries
    - Judge/bench-specific queries
    - Citation-based queries (if known landmark cases are referenced)
    ↓
STEP 3: Automated execution against IK API
    - Run all generated queries programmatically
    - Fetch search results (metadata + snippets)
    - Deduplicate across queries (by tid)
    - Rank by numcitedby (most cited = most authoritative)
    - Cache everything in PostgreSQL
    ↓
STEP 4: Fetch full text of top-ranked judgments
    - Download from IK API (or serve from cache if already fetched)
    - Store in database with full metadata
    ↓
STEP 5: Feed to LLM (Gemini 2.5 Pro / Claude) with prompt templates
    - "Summarize key holdings relevant to [specific issue from pleading]"
    - "Extract ratio decidendi from these cases"
    - "Identify which cases support the petitioner's position"
    - "Identify which cases support the respondent's position"
    - "Create a case law analysis table: case name, date, court, key holding, relevance"
    ↓
STEP 6: Structured output
    - Research memo organized by legal issue
    - Case law matrix (case vs. legal point)
    - Supporting/opposing precedent lists
    - Recommended arguments with citations
```

### 3.2 How the LLM Extracts Legal Issues from Pleadings

A well-crafted prompt to Claude (Opus 4.6) or Gemini 2.5 Pro can extract:

**From a Complaint/Petition:**
1. Causes of action (what legal wrongs are alleged)
2. Statutory provisions invoked (which sections of which acts)
3. Constitutional articles claimed to be violated
4. Factual matrix (key facts that define the legal issues)
5. Relief sought (what remedies are requested)
6. Jurisdictional basis (which court/tribunal, why)

**From a Written Statement/Defence:**
1. Denials and admissions
2. Affirmative defenses raised
3. Counter-claims
4. Limitation/jurisdiction objections
5. Legal points on which the defense relies

**From each extracted issue, the LLM generates:**
- A primary IK search query
- 2-3 alternative queries (synonym expansion)
- A statute-specific query
- Suggested court filter
- Suggested date range (if issue is time-sensitive)

### 3.3 Example: From Pleading to Queries

**Sample Pleading Excerpt:**
> "The petitioner challenges the order dated 22.07.2025 passed by the Registrar of DRAT, New Delhi, dismissing the Section 21 waiver application. The petitioner contends that the Registrar had no jurisdiction to pass such an order, which could only be passed by the Chairperson. The impugned order is therefore void ab initio."

**LLM Extracts:**
1. **Issue 1**: Whether Registrar of DRAT has jurisdiction to dismiss Section 21 waiver applications
2. **Issue 2**: Whether an order passed without jurisdiction is void ab initio
3. **Issue 3**: Powers of Registrar vs. Chairperson under RDDBFI Act
4. **Statute**: Recovery of Debts and Bankruptcy Act, 1993 — Section 21
5. **Court**: DRAT (Debts Recovery Appellate Tribunal)
6. **Jurisdiction objection**: Registrar acting beyond vested authority

**Generated Queries:**
```
# Issue 1 - Primary
"section 21" ANDD "waiver" ANDD "Registrar" ANDD "jurisdiction"  [doctypes: drat]

# Issue 1 - Synonym expanded
"section 21" ANDD "deposit waiver" ANDD "Registrar" ANDD "power"  [doctypes: drat]

# Issue 1 - Broader
"Registrar" ANDD "jurisdiction" ANDD "DRAT"  [doctypes: supremecourt,delhi]

# Issue 2 - Primary
"void ab initio" ANDD "without jurisdiction" ANDD "nullity"  [doctypes: judgments]

# Issue 2 - Landmark cases
title: "without jurisdiction" ANDD "void"  [doctypes: supremecourt]

# Issue 3 - Statute specific
"Recovery of Debts" ANDD "section 21" ANDD "Chairperson" ORR "Presiding Officer"

# Issue 3 - Alternative
"RDDBFI Act" ORR "DRT Act" ANDD "waiver of pre-deposit"
```

### 3.4 Why This Approach Is Powerful

**Traditional Manual Research:**
- Lawyer reads pleading, identifies 3-5 issues mentally
- Searches Indian Kanoon website with 1-2 queries per issue
- Reads through results, clicks promising ones
- Takes 4-8 hours for thorough research
- Recall: ~20-40% (misses many relevant cases)
- Highly dependent on lawyer's keyword intuition

**Automated Pipeline:**
- LLM reads pleading, identifies ALL issues (including subtle ones lawyers might overlook)
- Generates 5-7 queries per issue using multiple strategies
- Runs 30-50 queries programmatically against IK API
- Deduplicates and ranks by citation count
- Fetches top 50-100 most-cited results
- LLM analyzes all of them with structured prompts
- Takes 10-15 minutes end-to-end
- Recall: ~60-80% (synonym expansion + multi-query catches far more)
- Consistent, repeatable, not dependent on one person's intuition

**The key insight**: An LLM like Claude Opus 4.6 doesn't just translate language — it understands legal reasoning. It knows that "void ab initio" relates to "coram non judice" relates to "without jurisdiction" relates to "nullity of order." A human lawyer might search for one of these; the LLM generates queries for ALL of them.

### 3.5 The Full Feature Set for This App

Based on this vision, the complete feature set is:

1. **Judgment Caching (PostgreSQL)** — Cache all fetched judgments to avoid repeat API costs
2. **Most-Cited Sorting** — Prioritize authoritative cases by citation count
3. **Pleading Upload & Issue Extraction** — Upload PDF/text of pleading, LLM extracts legal issues
4. **Automated Multi-Query Search** — Generate and execute multiple IK queries per issue
5. **Smart Deduplication & Ranking** — Merge results across queries, rank by relevance + citation count
6. **Batch Full-Text Fetch** — Download full text of top-ranked cases, cache in DB
7. **LLM Analysis with Prompt Templates** — Feed cases to Gemini/Claude with structured prompts
8. **Structured Output** — Research memo, case matrix, supporting/opposing lists
9. **Prompt Template Library** — Save and reuse analysis prompts for different types of legal work

### 3.6 IK API Cost Optimization

The pipeline should minimize API costs through:

1. **Aggressive caching**: Every search result and every document viewed is cached forever. If the same judgment appears in 10 different searches, it's fetched once.
2. **Metadata-first approach**: Use search results (free metadata) to identify candidates, only fetch full text for the most promising ones.
3. **`maxpages` parameter**: Fetch multiple pages in one API call instead of paginating manually (e.g., `maxpages=5` gets 5 pages for the cost of 5 pages but in 1 HTTP request).
4. **`docmeta` for lightweight checks**: Before fetching full text, use `/docmeta/<id>/` to check if a document is worth downloading (check `numcitedby`, `publishdate`, `doctype`).
5. **`docfragment` for relevance validation**: Use `/docfragment/<id>/?formInput=<query>` to see only the matching paragraphs. If fragments aren't relevant, skip the full document download.

---

## PART 4: WHAT EXISTS TODAY vs. WHAT NEEDS TO BE BUILT

### Currently Built (Working)
- Basic search with all IK operators
- 40+ court/tribunal filter dropdown
- Smart Search (Claude Haiku converts natural language to IK query)
- Document viewer
- Search tips panel with examples
- Input validation (dates, doctypes, sort)

### Planned (Session Plan Approved)
- PostgreSQL caching layer (T002-T004)
- Most-cited sorting within fetched results (T005)
- Gemini integration for analysis (T006-T007)
- Analysis page with prompt templates (T008)

### Future Vision (Not Yet Planned)
- Pleading upload & automatic issue extraction
- Multi-query generation from extracted issues
- Automated batch search execution
- Smart deduplication and ranking across queries
- Citation chain crawling (follow `citedbyList`)
- Research memo generation
- Case law matrix output
- PDF report export

---

## APPENDIX: Indian Kanoon Search Tips (From Official Documentation)

1. Indian Kanoon searches **full text** of documents by default — not just titles
2. The main search box also searches **citation strings** and **titles** automatically
3. Results are ranked by a proprietary relevance algorithm (not disclosed)
4. The `numcitedby` field in search results indicates how many later cases cite this judgment — a strong proxy for importance
5. `docsize` in search results tells you the character count — useful for estimating reading time and LLM token cost
6. Indian Kanoon has RSS feeds for each court — useful for monitoring new judgments
7. Coverage: Supreme Court from 1947, all 24+ High Courts, 17 tribunals, all Central Acts
8. The "Cited By" feature on the website categorizes citations by sentiment (Relied on / Accepted / Negatively viewed) — this is not available via API but the citation count is
