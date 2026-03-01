import json
import os
import psycopg2
import psycopg2.extras


def get_db_connection():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not configured")
    conn = psycopg2.connect(url)
    conn.autocommit = True
    return conn


def init_db():
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS judgments (
                    tid BIGINT PRIMARY KEY,
                    title TEXT NOT NULL,
                    doctype TEXT,
                    court_source TEXT,
                    publish_date DATE,
                    case_number TEXT,
                    num_cites INT DEFAULT 0,
                    num_cited_by INT DEFAULT 0,
                    full_text TEXT,
                    full_text_html TEXT,
                    fetched_at TIMESTAMP DEFAULT NOW(),
                    metadata_only BOOLEAN DEFAULT FALSE
                );
                CREATE TABLE IF NOT EXISTS search_queries (
                    id SERIAL PRIMARY KEY,
                    query_text TEXT NOT NULL,
                    doctype_filter TEXT,
                    from_date TEXT,
                    to_date TEXT,
                    sort_by TEXT,
                    total_results INT,
                    searched_at TIMESTAMP DEFAULT NOW()
                );
                CREATE TABLE IF NOT EXISTS search_query_results (
                    id SERIAL PRIMARY KEY,
                    search_query_id INT REFERENCES search_queries(id) ON DELETE CASCADE,
                    tid BIGINT REFERENCES judgments(tid),
                    position INT,
                    headline TEXT
                );
                CREATE TABLE IF NOT EXISTS prompt_templates (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    prompt_text TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_judgments_cited_by ON judgments(num_cited_by DESC);
                CREATE INDEX IF NOT EXISTS idx_judgments_publish_date ON judgments(publish_date);
                CREATE INDEX IF NOT EXISTS idx_search_queries_text ON search_queries(query_text);

                CREATE TABLE IF NOT EXISTS judgment_genomes (
                    id SERIAL PRIMARY KEY,
                    tid BIGINT REFERENCES judgments(tid),
                    genome_json JSONB NOT NULL,
                    schema_version TEXT DEFAULT '3.1.0',
                    extraction_model TEXT,
                    extraction_date TIMESTAMP DEFAULT NOW(),
                    document_id TEXT,
                    certification_level TEXT,
                    overall_durability_score INT,
                    UNIQUE(tid)
                );
                CREATE INDEX IF NOT EXISTS idx_genomes_tid ON judgment_genomes(tid);

                CREATE TABLE IF NOT EXISTS question_extractions (
                    id SERIAL PRIMARY KEY,
                    pleading_text_hash TEXT NOT NULL,
                    pleading_type TEXT,
                    citation TEXT,
                    questions_json JSONB NOT NULL,
                    question_count INT,
                    extraction_model TEXT,
                    extracted_at TIMESTAMP DEFAULT NOW(),
                    UNIQUE(pleading_text_hash)
                );

                CREATE EXTENSION IF NOT EXISTS pgcrypto;

                CREATE TABLE IF NOT EXISTS research_jobs (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    status TEXT NOT NULL DEFAULT 'RECEIVED',
                    pleading_text TEXT NOT NULL,
                    pleading_type TEXT,
                    citation TEXT,
                    client_name TEXT,
                    client_side TEXT,
                    opposite_party TEXT,
                    court TEXT,
                    reliefs_sought JSONB,
                    callback_url TEXT,
                    webhook_secret TEXT,
                    priority TEXT DEFAULT 'NORMAL',
                    question_extraction_id INT,
                    total_questions INT DEFAULT 0,
                    total_queries_generated INT DEFAULT 0,
                    total_searches_completed INT DEFAULT 0,
                    total_results_found INT DEFAULT 0,
                    total_relevant_judgments INT DEFAULT 0,
                    total_genomes_extracted INT DEFAULT 0,
                    research_memo JSONB,
                    cost_estimate_usd FLOAT DEFAULT 0,
                    created_at TIMESTAMP DEFAULT NOW(),
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    failed_at TIMESTAMP,
                    error_message TEXT,
                    current_step TEXT,
                    questions_completed_at TIMESTAMP,
                    queries_completed_at TIMESTAMP,
                    searches_completed_at TIMESTAMP,
                    filtering_completed_at TIMESTAMP,
                    fetching_completed_at TIMESTAMP,
                    genomes_completed_at TIMESTAMP,
                    synthesis_completed_at TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_research_jobs_status ON research_jobs(status);

                CREATE TABLE IF NOT EXISTS pipeline_queries (
                    id SERIAL PRIMARY KEY,
                    job_id UUID REFERENCES research_jobs(id) ON DELETE CASCADE,
                    question_id TEXT,
                    question_text TEXT,
                    question_category TEXT,
                    question_importance TEXT,
                    generated_ik_query TEXT,
                    ik_doctype TEXT DEFAULT '',
                    ik_sort TEXT DEFAULT '',
                    search_completed BOOLEAN DEFAULT FALSE,
                    results_count INT DEFAULT 0,
                    relevant_count INT DEFAULT 0,
                    created_at TIMESTAMP DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_pipeline_queries_job ON pipeline_queries(job_id);

                CREATE TABLE IF NOT EXISTS pipeline_results (
                    id SERIAL PRIMARY KEY,
                    job_id UUID REFERENCES research_jobs(id) ON DELETE CASCADE,
                    query_id INT REFERENCES pipeline_queries(id),
                    tid BIGINT,
                    title TEXT,
                    headline TEXT,
                    relevance_score FLOAT DEFAULT 0,
                    relevance_reasoning TEXT,
                    is_relevant BOOLEAN DEFAULT FALSE,
                    genome_extracted BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT NOW(),
                    UNIQUE(job_id, tid)
                );
                CREATE INDEX IF NOT EXISTS idx_pipeline_results_job ON pipeline_results(job_id);
                CREATE INDEX IF NOT EXISTS idx_pipeline_results_relevant ON pipeline_results(job_id, is_relevant);
            """)
            cur.execute("""
                ALTER TABLE research_jobs ADD COLUMN IF NOT EXISTS cost_breakdown_json JSONB DEFAULT '{}';
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS taxonomy_categories (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    parent_statute TEXT,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS taxonomy_topics (
                    id TEXT PRIMARY KEY,
                    category_id TEXT REFERENCES taxonomy_categories(id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    description TEXT,
                    keywords TEXT[] DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_taxonomy_topics_category ON taxonomy_topics(category_id);
                CREATE INDEX IF NOT EXISTS idx_taxonomy_topics_keywords ON taxonomy_topics USING GIN(keywords);

                CREATE TABLE IF NOT EXISTS genome_categories (
                    genome_tid BIGINT REFERENCES judgment_genomes(tid) ON DELETE CASCADE,
                    category_id TEXT REFERENCES taxonomy_categories(id) ON DELETE CASCADE,
                    auto_tagged BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT NOW(),
                    PRIMARY KEY (genome_tid, category_id)
                );
                CREATE INDEX IF NOT EXISTS idx_genome_categories_cat ON genome_categories(category_id);

                CREATE TABLE IF NOT EXISTS genome_topics (
                    genome_tid BIGINT REFERENCES judgment_genomes(tid) ON DELETE CASCADE,
                    topic_id TEXT REFERENCES taxonomy_topics(id) ON DELETE CASCADE,
                    auto_tagged BOOLEAN DEFAULT TRUE,
                    confidence FLOAT DEFAULT 1.0,
                    created_at TIMESTAMP DEFAULT NOW(),
                    PRIMARY KEY (genome_tid, topic_id)
                );
                CREATE INDEX IF NOT EXISTS idx_genome_topics_topic ON genome_topics(topic_id);

                CREATE TABLE IF NOT EXISTS provision_index (
                    id TEXT PRIMARY KEY,
                    canonical_name TEXT NOT NULL,
                    parent_statute TEXT,
                    aliases TEXT[] DEFAULT '{}',
                    category_id TEXT REFERENCES taxonomy_categories(id) ON DELETE SET NULL,
                    created_at TIMESTAMP DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_provision_index_aliases ON provision_index USING GIN(aliases);
                CREATE INDEX IF NOT EXISTS idx_provision_index_category ON provision_index(category_id);
            """)

            cur.execute("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.table_constraints
                        WHERE constraint_name = 'fk_genome_categories_tid'
                    ) THEN
                        ALTER TABLE genome_categories
                            ADD CONSTRAINT fk_genome_categories_tid
                            FOREIGN KEY (genome_tid) REFERENCES judgment_genomes(tid) ON DELETE CASCADE;
                    END IF;
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.table_constraints
                        WHERE constraint_name = 'fk_genome_topics_tid'
                    ) THEN
                        ALTER TABLE genome_topics
                            ADD CONSTRAINT fk_genome_topics_tid
                            FOREIGN KEY (genome_tid) REFERENCES judgment_genomes(tid) ON DELETE CASCADE;
                    END IF;
                END $$;
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS topic_syntheses (
                    id SERIAL PRIMARY KEY,
                    topic_id TEXT REFERENCES taxonomy_topics(id) ON DELETE CASCADE,
                    synthesis_json JSONB NOT NULL,
                    model TEXT,
                    genome_count INT DEFAULT 0,
                    created_at TIMESTAMP DEFAULT NOW(),
                    UNIQUE(topic_id)
                );

                CREATE TABLE IF NOT EXISTS conflict_scans (
                    id SERIAL PRIMARY KEY,
                    topic_id TEXT REFERENCES taxonomy_topics(id) ON DELETE SET NULL,
                    category_id TEXT REFERENCES taxonomy_categories(id) ON DELETE SET NULL,
                    scan_json JSONB NOT NULL,
                    model TEXT,
                    genome_count INT DEFAULT 0,
                    created_at TIMESTAMP DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_conflict_scans_topic ON conflict_scans(topic_id);

                CREATE TABLE IF NOT EXISTS district_courts (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    city TEXT NOT NULL,
                    state TEXT NOT NULL,
                    court_code TEXT UNIQUE,
                    created_at TIMESTAMP DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS district_judges (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    designation TEXT,
                    court_id INT REFERENCES district_courts(id) ON DELETE CASCADE,
                    current_bench TEXT,
                    specializations TEXT[] DEFAULT '{}',
                    active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_district_judges_court ON district_judges(court_id);

                CREATE TABLE IF NOT EXISTS district_court_orders (
                    id SERIAL PRIMARY KEY,
                    order_reference TEXT,
                    judge_id INT REFERENCES district_judges(id) ON DELETE CASCADE,
                    court_id INT REFERENCES district_courts(id) ON DELETE SET NULL,
                    order_date DATE,
                    case_type TEXT,
                    case_number TEXT,
                    petitioner TEXT,
                    respondent TEXT,
                    order_text TEXT,
                    order_source_url TEXT,
                    tid BIGINT,
                    created_at TIMESTAMP DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_dc_orders_judge ON district_court_orders(judge_id);
                CREATE INDEX IF NOT EXISTS idx_dc_orders_court ON district_court_orders(court_id);
                CREATE INDEX IF NOT EXISTS idx_dc_orders_case_type ON district_court_orders(case_type);

                CREATE TABLE IF NOT EXISTS judge_genomes (
                    id SERIAL PRIMARY KEY,
                    judge_id INT REFERENCES district_judges(id) ON DELETE CASCADE,
                    order_id INT REFERENCES district_court_orders(id) ON DELETE CASCADE,
                    genome_json JSONB NOT NULL,
                    schema_version TEXT DEFAULT '3.1.0',
                    extraction_model TEXT,
                    extraction_date TIMESTAMP DEFAULT NOW(),
                    durability_score INT
                );
                CREATE INDEX IF NOT EXISTS idx_judge_genomes_judge ON judge_genomes(judge_id);

                CREATE TABLE IF NOT EXISTS judge_profiles (
                    judge_id INT REFERENCES district_judges(id) ON DELETE CASCADE UNIQUE,
                    profile_json JSONB,
                    total_orders_analyzed INT DEFAULT 0,
                    last_updated TIMESTAMP DEFAULT NOW(),
                    model_used TEXT
                );
            """)

            _seed_delhi_courts(cur)
    finally:
        conn.close()


def _seed_delhi_courts(cur):
    cur.execute("SELECT COUNT(*) FROM district_courts WHERE city = 'Delhi'")
    if cur.fetchone()[0] > 0:
        return
    delhi_courts = [
        ("Saket District Court", "Delhi", "Delhi", "DEL_SAKET"),
        ("Patiala House Courts", "Delhi", "Delhi", "DEL_PATIALA"),
        ("Tis Hazari Courts", "Delhi", "Delhi", "DEL_TISHAZARI"),
        ("Rohini Courts", "Delhi", "Delhi", "DEL_ROHINI"),
        ("Dwarka Courts", "Delhi", "Delhi", "DEL_DWARKA"),
        ("Karkardooma Courts", "Delhi", "Delhi", "DEL_KARKARDOOMA"),
    ]
    for name, city, state, code in delhi_courts:
        cur.execute(
            "INSERT INTO district_courts (name, city, state, court_code) VALUES (%s, %s, %s, %s) ON CONFLICT (court_code) DO NOTHING",
            (name, city, state, code)
        )


def get_cached_judgment(tid):
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM judgments WHERE tid = %s AND metadata_only = FALSE",
                (tid,)
            )
            return cur.fetchone()
    finally:
        conn.close()


def save_judgment_metadata(tid, title, doctype=None, court_source=None,
                           publish_date=None, case_number=None,
                           num_cites=0, num_cited_by=0):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO judgments (tid, title, doctype, court_source, publish_date,
                                      case_number, num_cites, num_cited_by, metadata_only)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, TRUE)
                ON CONFLICT (tid) DO UPDATE SET
                    title = COALESCE(EXCLUDED.title, judgments.title),
                    doctype = COALESCE(EXCLUDED.doctype, judgments.doctype),
                    court_source = COALESCE(EXCLUDED.court_source, judgments.court_source),
                    publish_date = COALESCE(EXCLUDED.publish_date, judgments.publish_date),
                    case_number = COALESCE(EXCLUDED.case_number, judgments.case_number),
                    num_cites = COALESCE(EXCLUDED.num_cites, judgments.num_cites),
                    num_cited_by = COALESCE(EXCLUDED.num_cited_by, judgments.num_cited_by)
                WHERE judgments.metadata_only = TRUE
            """, (tid, title, doctype, court_source, publish_date,
                  case_number, num_cites or 0, num_cited_by or 0))
    finally:
        conn.close()


def save_judgment_full_text(tid, title, full_text_html):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO judgments (tid, title, full_text_html, metadata_only)
                VALUES (%s, %s, %s, FALSE)
                ON CONFLICT (tid) DO UPDATE SET
                    title = COALESCE(EXCLUDED.title, judgments.title),
                    full_text_html = EXCLUDED.full_text_html,
                    metadata_only = FALSE,
                    fetched_at = NOW()
            """, (tid, title, full_text_html))
    finally:
        conn.close()


def save_search_query(query_text, doctype_filter="", from_date="",
                      to_date="", sort_by="", total_results=0, result_docs=None):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO search_queries (query_text, doctype_filter, from_date, to_date,
                                            sort_by, total_results)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (query_text, doctype_filter, from_date, to_date, sort_by, total_results))
            query_id = cur.fetchone()[0]

            if result_docs:
                for i, doc in enumerate(result_docs):
                    tid = doc.get("tid")
                    if tid:
                        cur.execute("""
                            INSERT INTO search_query_results (search_query_id, tid, position, headline)
                            VALUES (%s, %s, %s, %s)
                            ON CONFLICT DO NOTHING
                        """, (query_id, tid, i, doc.get("headline", "")))
            return query_id
    finally:
        conn.close()


def get_saved_queries(limit=50):
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT sq.id, sq.query_text, sq.doctype_filter, sq.from_date, sq.to_date,
                       sq.sort_by, sq.total_results, sq.searched_at,
                       COUNT(sqr.id) AS result_count
                FROM search_queries sq
                LEFT JOIN search_query_results sqr ON sq.id = sqr.search_query_id
                GROUP BY sq.id
                ORDER BY sq.searched_at DESC
                LIMIT %s
            """, (limit,))
            return cur.fetchall()
    finally:
        conn.close()


def get_judgments_for_query(search_query_id):
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT j.tid, j.title, j.doctype, j.court_source, j.publish_date,
                       j.num_cited_by, j.metadata_only, j.full_text_html,
                       sqr.position, sqr.headline
                FROM search_query_results sqr
                JOIN judgments j ON sqr.tid = j.tid
                WHERE sqr.search_query_id = %s
                ORDER BY sqr.position
            """, (search_query_id,))
            return cur.fetchall()
    finally:
        conn.close()


def get_judgments_by_tids(tids):
    if not tids:
        return []
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM judgments WHERE tid = ANY(%s)",
                (tids,)
            )
            return cur.fetchall()
    finally:
        conn.close()


def get_prompt_templates():
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM prompt_templates ORDER BY created_at")
            return cur.fetchall()
    finally:
        conn.close()


def save_prompt_template(name, prompt_text):
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                INSERT INTO prompt_templates (name, prompt_text)
                VALUES (%s, %s)
                RETURNING *
            """, (name, prompt_text))
            return cur.fetchone()
    finally:
        conn.close()


def update_prompt_template(template_id, name, prompt_text):
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                UPDATE prompt_templates SET name = %s, prompt_text = %s, updated_at = NOW()
                WHERE id = %s RETURNING *
            """, (name, prompt_text, template_id))
            return cur.fetchone()
    finally:
        conn.close()


def delete_prompt_template(template_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM prompt_templates WHERE id = %s", (template_id,))
            return cur.rowcount > 0
    finally:
        conn.close()


def get_cached_genome(tid):
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM judgment_genomes WHERE tid = %s", (tid,))
            return cur.fetchone()
    finally:
        conn.close()


def save_genome(tid, genome_json, model=None, schema_version="3.1.0",
                doc_id=None, cert_level=None, durability=None):
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                INSERT INTO judgment_genomes (tid, genome_json, extraction_model, schema_version,
                                              document_id, certification_level, overall_durability_score)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (tid) DO UPDATE SET
                    genome_json = EXCLUDED.genome_json,
                    extraction_model = EXCLUDED.extraction_model,
                    schema_version = EXCLUDED.schema_version,
                    document_id = EXCLUDED.document_id,
                    certification_level = EXCLUDED.certification_level,
                    overall_durability_score = EXCLUDED.overall_durability_score,
                    extraction_date = NOW()
                RETURNING *
            """, (tid, json.dumps(genome_json), model, schema_version,
                  doc_id, cert_level, durability))
            return cur.fetchone()
    finally:
        conn.close()


def get_all_genomes():
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT g.id, g.tid, g.schema_version, g.extraction_model,
                       g.extraction_date, g.document_id, g.certification_level,
                       g.overall_durability_score, j.title
                FROM judgment_genomes g
                JOIN judgments j ON g.tid = j.tid
                ORDER BY g.extraction_date DESC
            """)
            return cur.fetchall()
    finally:
        conn.close()


def get_all_genomes_rich():
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT g.id, g.tid, g.schema_version, g.extraction_model,
                       g.extraction_date, g.document_id, g.certification_level,
                       g.overall_durability_score, g.genome_json,
                       j.title, j.court_source, j.publish_date, j.num_cited_by
                FROM judgment_genomes g
                LEFT JOIN judgments j ON g.tid = j.tid
                ORDER BY g.extraction_date DESC
            """)
            return cur.fetchall()
    finally:
        conn.close()


def search_genomes(query_text):
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            like_pattern = f"%{query_text}%"
            cur.execute("""
                SELECT g.id, g.tid, g.schema_version, g.extraction_model,
                       g.extraction_date, g.document_id, g.certification_level,
                       g.overall_durability_score, g.genome_json,
                       j.title, j.court_source, j.publish_date, j.num_cited_by
                FROM judgment_genomes g
                LEFT JOIN judgments j ON g.tid = j.tid
                WHERE j.title ILIKE %s
                   OR g.genome_json::text ILIKE %s
                ORDER BY g.extraction_date DESC
                LIMIT 100
            """, (like_pattern, like_pattern))
            return cur.fetchall()
    finally:
        conn.close()


def ensure_judgment_exists(tid, title, court_source=None):
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT tid FROM judgments WHERE tid = %s", (tid,))
            if cur.fetchone():
                return True
            cur.execute("""
                INSERT INTO judgments (tid, title, court_source, metadata_only)
                VALUES (%s, %s, %s, TRUE)
                ON CONFLICT (tid) DO NOTHING
            """, (tid, title, court_source))
            return True
    finally:
        conn.close()


def get_cached_judgments_with_fulltext():
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT tid, title, doctype, court_source, publish_date,
                       num_cited_by, fetched_at
                FROM judgments
                WHERE metadata_only = FALSE AND full_text_html IS NOT NULL
                ORDER BY fetched_at DESC
            """)
            return cur.fetchall()
    finally:
        conn.close()


def save_question_extraction(text_hash, pleading_type, citation, questions_json,
                              question_count, model=None):
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                INSERT INTO question_extractions (pleading_text_hash, pleading_type, citation,
                                                   questions_json, question_count, extraction_model)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (pleading_text_hash) DO UPDATE SET
                    questions_json = EXCLUDED.questions_json,
                    question_count = EXCLUDED.question_count,
                    extraction_model = EXCLUDED.extraction_model,
                    extracted_at = NOW()
                RETURNING *
            """, (text_hash, pleading_type, citation,
                  json.dumps(questions_json), question_count, model))
            return cur.fetchone()
    finally:
        conn.close()


def get_question_extraction(text_hash):
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM question_extractions WHERE pleading_text_hash = %s", (text_hash,))
            return cur.fetchone()
    finally:
        conn.close()


def create_research_job(pleading_text, pleading_type=None, citation=None,
                        client_name=None, client_side=None, opposite_party=None,
                        court=None, reliefs_sought=None, callback_url=None,
                        webhook_secret=None, priority="NORMAL"):
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                INSERT INTO research_jobs (pleading_text, pleading_type, citation,
                    client_name, client_side, opposite_party, court, reliefs_sought,
                    callback_url, webhook_secret, priority)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
            """, (pleading_text, pleading_type, citation,
                  client_name, client_side, opposite_party, court,
                  json.dumps(reliefs_sought) if reliefs_sought else None,
                  callback_url, webhook_secret, priority))
            return cur.fetchone()
    finally:
        conn.close()


def get_research_job(job_id):
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM research_jobs WHERE id = %s", (str(job_id),))
            return cur.fetchone()
    finally:
        conn.close()


def update_research_job(job_id, **kwargs):
    if not kwargs:
        return
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            sets = []
            vals = []
            for k, v in kwargs.items():
                sets.append(f"{k} = %s")
                if k in ("reliefs_sought", "research_memo", "cost_breakdown_json") and isinstance(v, (dict, list)):
                    vals.append(json.dumps(v))
                else:
                    vals.append(v)
            vals.append(str(job_id))
            cur.execute(f"UPDATE research_jobs SET {', '.join(sets)} WHERE id = %s", vals)
    finally:
        conn.close()


def get_all_research_jobs(limit=50):
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT id, status, citation, client_name, pleading_type, court,
                       total_questions, total_queries_generated, total_searches_completed,
                       total_relevant_judgments, total_genomes_extracted,
                       cost_estimate_usd, cost_breakdown_json, current_step,
                       created_at, started_at, completed_at, failed_at, error_message,
                       questions_completed_at, queries_completed_at, searches_completed_at,
                       filtering_completed_at, fetching_completed_at, genomes_completed_at,
                       synthesis_completed_at
                FROM research_jobs ORDER BY created_at DESC LIMIT %s
            """, (limit,))
            return cur.fetchall()
    finally:
        conn.close()


def save_pipeline_query(job_id, question_id, question_text, question_category,
                         question_importance, generated_ik_query, ik_doctype="", ik_sort=""):
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                INSERT INTO pipeline_queries (job_id, question_id, question_text,
                    question_category, question_importance, generated_ik_query, ik_doctype, ik_sort)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
            """, (str(job_id), question_id, question_text, question_category,
                  question_importance, generated_ik_query, ik_doctype, ik_sort))
            return cur.fetchone()
    finally:
        conn.close()


def get_pipeline_queries(job_id):
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM pipeline_queries WHERE job_id = %s ORDER BY id",
                        (str(job_id),))
            return cur.fetchall()
    finally:
        conn.close()


def update_pipeline_query(query_id, **kwargs):
    if not kwargs:
        return
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            sets = []
            vals = []
            for k, v in kwargs.items():
                sets.append(f"{k} = %s")
                vals.append(v)
            vals.append(query_id)
            cur.execute(f"UPDATE pipeline_queries SET {', '.join(sets)} WHERE id = %s", vals)
    finally:
        conn.close()


def save_pipeline_result(job_id, query_id, tid, title, headline=""):
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                INSERT INTO pipeline_results (job_id, query_id, tid, title, headline)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (job_id, tid) DO NOTHING
                RETURNING *
            """, (str(job_id), query_id, tid, title, headline))
            return cur.fetchone()
    finally:
        conn.close()


def get_pipeline_results(job_id, relevant_only=False):
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            query = "SELECT * FROM pipeline_results WHERE job_id = %s"
            if relevant_only:
                query += " AND is_relevant = TRUE"
            query += " ORDER BY relevance_score DESC"
            cur.execute(query, (str(job_id),))
            return cur.fetchall()
    finally:
        conn.close()


def update_pipeline_result(result_id, **kwargs):
    if not kwargs:
        return
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            sets = []
            vals = []
            for k, v in kwargs.items():
                sets.append(f"{k} = %s")
                vals.append(v)
            vals.append(result_id)
            cur.execute(f"UPDATE pipeline_results SET {', '.join(sets)} WHERE id = %s", vals)
    finally:
        conn.close()


def bulk_update_relevance(job_id, relevance_data):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            for tid, score, reasoning, is_relevant in relevance_data:
                cur.execute("""
                    UPDATE pipeline_results
                    SET relevance_score = %s, relevance_reasoning = %s, is_relevant = %s
                    WHERE job_id = %s AND tid = %s
                """, (score, reasoning, is_relevant, str(job_id), tid))
    finally:
        conn.close()


def upsert_taxonomy_category(cat_id, name, parent_statute=None, description=None):
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                INSERT INTO taxonomy_categories (id, name, parent_statute, description)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name,
                    parent_statute = COALESCE(EXCLUDED.parent_statute, taxonomy_categories.parent_statute),
                    description = COALESCE(EXCLUDED.description, taxonomy_categories.description)
                RETURNING *
            """, (cat_id, name, parent_statute, description))
            return cur.fetchone()
    finally:
        conn.close()


def upsert_taxonomy_topic(topic_id, category_id, name, description=None, keywords=None):
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                INSERT INTO taxonomy_topics (id, category_id, name, description, keywords)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name,
                    category_id = EXCLUDED.category_id,
                    description = COALESCE(EXCLUDED.description, taxonomy_topics.description),
                    keywords = EXCLUDED.keywords
                RETURNING *
            """, (topic_id, category_id, name, description, keywords or []))
            return cur.fetchone()
    finally:
        conn.close()


def upsert_provision(prov_id, canonical_name, parent_statute=None, aliases=None, category_id=None):
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                INSERT INTO provision_index (id, canonical_name, parent_statute, aliases, category_id)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    canonical_name = EXCLUDED.canonical_name,
                    parent_statute = COALESCE(EXCLUDED.parent_statute, provision_index.parent_statute),
                    aliases = EXCLUDED.aliases,
                    category_id = COALESCE(EXCLUDED.category_id, provision_index.category_id)
                RETURNING *
            """, (prov_id, canonical_name, parent_statute, aliases or [], category_id))
            return cur.fetchone()
    finally:
        conn.close()


def tag_genome_category(genome_tid, category_id, auto_tagged=True):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO genome_categories (genome_tid, category_id, auto_tagged)
                VALUES (%s, %s, %s)
                ON CONFLICT (genome_tid, category_id) DO NOTHING
            """, (genome_tid, category_id, auto_tagged))
    finally:
        conn.close()


def tag_genome_topic(genome_tid, topic_id, auto_tagged=True, confidence=1.0):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO genome_topics (genome_tid, topic_id, auto_tagged, confidence)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (genome_tid, topic_id) DO UPDATE SET
                    confidence = GREATEST(genome_topics.confidence, EXCLUDED.confidence)
            """, (genome_tid, topic_id, auto_tagged, confidence))
    finally:
        conn.close()


def clear_genome_tags(genome_tid, auto_only=True):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            if auto_only:
                cur.execute("DELETE FROM genome_categories WHERE genome_tid = %s AND auto_tagged = TRUE", (genome_tid,))
                cur.execute("DELETE FROM genome_topics WHERE genome_tid = %s AND auto_tagged = TRUE", (genome_tid,))
            else:
                cur.execute("DELETE FROM genome_categories WHERE genome_tid = %s", (genome_tid,))
                cur.execute("DELETE FROM genome_topics WHERE genome_tid = %s", (genome_tid,))
    finally:
        conn.close()


def get_all_taxonomy_categories():
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT c.*, COUNT(gc.genome_tid) AS genome_count
                FROM taxonomy_categories c
                LEFT JOIN genome_categories gc ON c.id = gc.category_id
                GROUP BY c.id
                ORDER BY genome_count DESC, c.name
            """)
            return cur.fetchall()
    finally:
        conn.close()


def get_taxonomy_topics(category_id=None):
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if category_id:
                cur.execute("""
                    SELECT t.*, COUNT(gt.genome_tid) AS genome_count
                    FROM taxonomy_topics t
                    LEFT JOIN genome_topics gt ON t.id = gt.topic_id
                    WHERE t.category_id = %s
                    GROUP BY t.id
                    ORDER BY genome_count DESC, t.name
                """, (category_id,))
            else:
                cur.execute("""
                    SELECT t.*, COUNT(gt.genome_tid) AS genome_count
                    FROM taxonomy_topics t
                    LEFT JOIN genome_topics gt ON t.id = gt.topic_id
                    GROUP BY t.id
                    ORDER BY genome_count DESC, t.name
                """)
            return cur.fetchall()
    finally:
        conn.close()


def get_genomes_for_category(category_id):
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT g.tid, g.overall_durability_score, g.extraction_model,
                       g.extraction_date, g.certification_level,
                       j.title, j.court_source, j.publish_date, j.num_cited_by
                FROM genome_categories gc
                JOIN judgment_genomes g ON gc.genome_tid = g.tid
                LEFT JOIN judgments j ON g.tid = j.tid
                WHERE gc.category_id = %s
                ORDER BY g.overall_durability_score DESC NULLS LAST
            """, (category_id,))
            return cur.fetchall()
    finally:
        conn.close()


def get_genomes_for_topic(topic_id):
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT g.tid, g.overall_durability_score, g.extraction_model,
                       g.extraction_date, g.certification_level,
                       gt.confidence,
                       j.title, j.court_source, j.publish_date, j.num_cited_by
                FROM genome_topics gt
                JOIN judgment_genomes g ON gt.genome_tid = g.tid
                LEFT JOIN judgments j ON g.tid = j.tid
                WHERE gt.topic_id = %s
                ORDER BY gt.confidence DESC, g.overall_durability_score DESC NULLS LAST
            """, (topic_id,))
            return cur.fetchall()
    finally:
        conn.close()


def get_all_provisions():
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT p.*, c.name AS category_name
                FROM provision_index p
                LEFT JOIN taxonomy_categories c ON p.category_id = c.id
                ORDER BY p.parent_statute, p.canonical_name
            """)
            return cur.fetchall()
    finally:
        conn.close()


def find_provision_by_alias(alias):
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT * FROM provision_index
                WHERE %s = ANY(aliases) OR id = %s
            """, (alias, alias))
            return cur.fetchone()
    finally:
        conn.close()


def search_taxonomy(query_text):
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            escaped = query_text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            like = f"%{escaped}%"
            cur.execute("""
                SELECT 'category' AS result_type, c.id, c.name, c.parent_statute AS detail,
                       COUNT(gc.genome_tid) AS genome_count
                FROM taxonomy_categories c
                LEFT JOIN genome_categories gc ON c.id = gc.category_id
                WHERE c.name ILIKE %s ESCAPE '\\' OR c.parent_statute ILIKE %s ESCAPE '\\' OR c.description ILIKE %s ESCAPE '\\'
                GROUP BY c.id
                UNION ALL
                SELECT 'topic' AS result_type, t.id, t.name, tc.name AS detail,
                       COUNT(gt.genome_tid) AS genome_count
                FROM taxonomy_topics t
                LEFT JOIN taxonomy_categories tc ON t.category_id = tc.id
                LEFT JOIN genome_topics gt ON t.id = gt.topic_id
                WHERE t.name ILIKE %s ESCAPE '\\' OR t.description ILIKE %s ESCAPE '\\'
                      OR EXISTS (SELECT 1 FROM unnest(t.keywords) kw WHERE kw ILIKE %s ESCAPE '\\')
                GROUP BY t.id, tc.name
                UNION ALL
                SELECT 'provision' AS result_type, p.id, p.canonical_name AS name,
                       p.parent_statute AS detail, 0 AS genome_count
                FROM provision_index p
                WHERE p.canonical_name ILIKE %s ESCAPE '\\' OR p.parent_statute ILIKE %s ESCAPE '\\'
                      OR p.id ILIKE %s ESCAPE '\\'
                      OR EXISTS (SELECT 1 FROM unnest(p.aliases) a WHERE a ILIKE %s ESCAPE '\\')
                ORDER BY genome_count DESC
                LIMIT 50
            """, (like, like, like, like, like, like, like, like, like, like))
            return cur.fetchall()
    finally:
        conn.close()


def get_genome_tags(genome_tid):
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT c.id, c.name, c.parent_statute, gc.auto_tagged
                FROM genome_categories gc
                JOIN taxonomy_categories c ON gc.category_id = c.id
                WHERE gc.genome_tid = %s
            """, (genome_tid,))
            categories = cur.fetchall()
            cur.execute("""
                SELECT t.id, t.name, t.category_id, gt.auto_tagged, gt.confidence,
                       c.name AS category_name
                FROM genome_topics gt
                JOIN taxonomy_topics t ON gt.topic_id = t.id
                LEFT JOIN taxonomy_categories c ON t.category_id = c.id
                WHERE gt.genome_tid = %s
            """, (genome_tid,))
            topics = cur.fetchall()
            return {"categories": categories, "topics": topics}
    finally:
        conn.close()


def get_taxonomy_stats():
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT
                    (SELECT COUNT(*) FROM taxonomy_categories) AS total_categories,
                    (SELECT COUNT(*) FROM taxonomy_topics) AS total_topics,
                    (SELECT COUNT(*) FROM provision_index) AS total_provisions,
                    (SELECT COUNT(DISTINCT genome_tid) FROM genome_categories) AS tagged_genomes,
                    (SELECT COUNT(*) FROM judgment_genomes) AS total_genomes
            """)
            return cur.fetchone()
    finally:
        conn.close()


def get_coverage_heatmap():
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT c.id AS category_id, c.name AS category_name, c.parent_statute,
                       t.id AS topic_id, t.name AS topic_name,
                       COUNT(gt.genome_tid) AS genome_count,
                       ROUND(AVG(g.overall_durability_score)::numeric, 1) AS avg_durability,
                       MIN(g.overall_durability_score) AS min_durability,
                       MAX(g.overall_durability_score) AS max_durability
                FROM taxonomy_categories c
                LEFT JOIN taxonomy_topics t ON t.category_id = c.id
                LEFT JOIN genome_topics gt ON gt.topic_id = t.id
                LEFT JOIN judgment_genomes g ON gt.genome_tid = g.tid
                GROUP BY c.id, c.name, c.parent_statute, t.id, t.name
                ORDER BY c.name, t.name
            """)
            rows = cur.fetchall()

            categories = {}
            for r in rows:
                cid = r["category_id"]
                if cid not in categories:
                    categories[cid] = {
                        "id": cid, "name": r["category_name"],
                        "parent_statute": r["parent_statute"], "topics": []
                    }
                if r["topic_id"]:
                    gc = int(r["genome_count"] or 0)
                    avg_d = float(r["avg_durability"]) if r["avg_durability"] else 0
                    if gc == 0:
                        strength = "GAP"
                    elif avg_d >= 7 and gc >= 3:
                        strength = "STRONG"
                    elif avg_d >= 5 and gc >= 2:
                        strength = "MODERATE"
                    else:
                        strength = "WEAK"
                    categories[cid]["topics"].append({
                        "id": r["topic_id"], "name": r["topic_name"],
                        "genome_count": gc,
                        "avg_durability": avg_d,
                        "min_durability": r["min_durability"],
                        "max_durability": r["max_durability"],
                        "strength": strength,
                    })

            result = []
            for cat in categories.values():
                topics = cat["topics"]
                covered = sum(1 for t in topics if t["genome_count"] > 0)
                gaps = sum(1 for t in topics if t["strength"] == "GAP")
                avg_str_vals = [t["avg_durability"] for t in topics if t["avg_durability"] > 0]
                cat["topic_coverage"] = f"{covered}/{len(topics)}"
                cat["gap_count"] = gaps
                cat["avg_strength"] = round(sum(avg_str_vals) / len(avg_str_vals), 1) if avg_str_vals else 0
                result.append(cat)
            return result
    finally:
        conn.close()


def get_topic_genomes_with_json(topic_id):
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT g.tid, g.genome_json, g.overall_durability_score,
                       g.extraction_model, g.certification_level,
                       j.title, j.court_source, j.publish_date, j.num_cited_by
                FROM genome_topics gt
                JOIN judgment_genomes g ON gt.genome_tid = g.tid
                LEFT JOIN judgments j ON g.tid = j.tid
                WHERE gt.topic_id = %s
                ORDER BY g.overall_durability_score DESC NULLS LAST
            """, (topic_id,))
            return cur.fetchall()
    finally:
        conn.close()


def save_topic_synthesis(topic_id, synthesis_json, model, genome_count):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO topic_syntheses (topic_id, synthesis_json, model, genome_count)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (topic_id) DO UPDATE SET
                    synthesis_json = EXCLUDED.synthesis_json,
                    model = EXCLUDED.model,
                    genome_count = EXCLUDED.genome_count,
                    created_at = NOW()
            """, (topic_id, json.dumps(synthesis_json), model, genome_count))
    finally:
        conn.close()


def get_topic_synthesis(topic_id):
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT ts.*, t.name AS topic_name
                FROM topic_syntheses ts
                JOIN taxonomy_topics t ON ts.topic_id = t.id
                WHERE ts.topic_id = %s
            """, (topic_id,))
            return cur.fetchone()
    finally:
        conn.close()


def get_genomes_for_comparison(tids):
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT g.tid, g.genome_json, g.overall_durability_score,
                       g.extraction_model, g.certification_level,
                       j.title, j.court_source, j.publish_date, j.num_cited_by
                FROM judgment_genomes g
                LEFT JOIN judgments j ON g.tid = j.tid
                WHERE g.tid = ANY(%s)
            """, (list(tids),))
            return cur.fetchall()
    finally:
        conn.close()


def save_conflict_scan(topic_id, category_id, scan_json, model, genome_count):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            if topic_id:
                cur.execute("DELETE FROM conflict_scans WHERE topic_id = %s", (topic_id,))
            cur.execute("""
                INSERT INTO conflict_scans (topic_id, category_id, scan_json, model, genome_count)
                VALUES (%s, %s, %s, %s, %s)
            """, (topic_id, category_id, json.dumps(scan_json), model, genome_count))
    finally:
        conn.close()


def get_conflict_scan(topic_id):
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT * FROM conflict_scans
                WHERE topic_id = %s
                ORDER BY created_at DESC LIMIT 1
            """, (topic_id,))
            return cur.fetchone()
    finally:
        conn.close()


def get_district_courts(city=None):
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if city:
                cur.execute("SELECT * FROM district_courts WHERE city = %s ORDER BY name", (city,))
            else:
                cur.execute("SELECT * FROM district_courts ORDER BY city, name")
            return cur.fetchall()
    finally:
        conn.close()


def get_district_judges(court_id=None):
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if court_id:
                cur.execute("""
                    SELECT dj.*, dc.name AS court_name,
                           (SELECT COUNT(*) FROM district_court_orders WHERE judge_id = dj.id) AS order_count
                    FROM district_judges dj
                    LEFT JOIN district_courts dc ON dj.court_id = dc.id
                    WHERE dj.court_id = %s
                    ORDER BY dj.name
                """, (court_id,))
            else:
                cur.execute("""
                    SELECT dj.*, dc.name AS court_name,
                           (SELECT COUNT(*) FROM district_court_orders WHERE judge_id = dj.id) AS order_count
                    FROM district_judges dj
                    LEFT JOIN district_courts dc ON dj.court_id = dc.id
                    ORDER BY dj.name
                """)
            return cur.fetchall()
    finally:
        conn.close()


def get_district_judge(judge_id):
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT dj.*, dc.name AS court_name, dc.city,
                       (SELECT COUNT(*) FROM district_court_orders WHERE judge_id = dj.id) AS order_count,
                       (SELECT COUNT(*) FROM judge_genomes WHERE judge_id = dj.id) AS genome_count
                FROM district_judges dj
                LEFT JOIN district_courts dc ON dj.court_id = dc.id
                WHERE dj.id = %s
            """, (judge_id,))
            return cur.fetchone()
    finally:
        conn.close()


def add_district_judge(name, designation, court_id, specializations=None):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO district_judges (name, designation, court_id, specializations)
                VALUES (%s, %s, %s, %s) RETURNING id
            """, (name, designation, court_id, specializations or []))
            return cur.fetchone()[0]
    finally:
        conn.close()


def add_district_order(judge_id, court_id, order_date, case_type, case_number,
                       petitioner, respondent, order_text, order_source_url=None, tid=None):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO district_court_orders
                    (judge_id, court_id, order_date, case_type, case_number,
                     petitioner, respondent, order_text, order_source_url, tid)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
            """, (judge_id, court_id, order_date, case_type, case_number,
                  petitioner, respondent, order_text, order_source_url, tid))
            return cur.fetchone()[0]
    finally:
        conn.close()


def get_district_orders(judge_id, page=1, per_page=20):
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            offset = (page - 1) * per_page
            cur.execute("""
                SELECT *, (SELECT COUNT(*) FROM district_court_orders WHERE judge_id = %s) AS total
                FROM district_court_orders
                WHERE judge_id = %s
                ORDER BY order_date DESC NULLS LAST
                LIMIT %s OFFSET %s
            """, (judge_id, judge_id, per_page, offset))
            return cur.fetchall()
    finally:
        conn.close()


def get_judge_profile(judge_id):
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM judge_profiles WHERE judge_id = %s", (judge_id,))
            return cur.fetchone()
    finally:
        conn.close()


def seed_default_templates():
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM prompt_templates")
            count = cur.fetchone()[0]
            if count == 0:
                defaults = [
                    ("Summarize Key Holdings",
                     "Analyze the following Indian court judgment(s) and extract the key legal holdings. For each judgment:\n1. Identify the core legal issue(s)\n2. State the holding/decision of the court\n3. Note any important observations or directions\n4. Highlight the legal principles established\n\nProvide a clear, structured summary suitable for legal research."),
                    ("Extract Ratio Decidendi",
                     "For each of the following Indian court judgment(s), identify and extract the ratio decidendi (the legal principle that forms the basis of the decision). For each case:\n1. State the material facts\n2. Identify the legal question(s) before the court\n3. Extract the ratio decidendi — the binding legal principle\n4. Distinguish from obiter dicta (remarks made in passing)\n\nPresent the analysis in a structured format useful for legal argumentation."),
                    ("Compare Legal Reasoning",
                     "Compare and contrast the legal reasoning across the following Indian court judgment(s). Your analysis should cover:\n1. Points of agreement between the judgments\n2. Points of divergence or conflict\n3. Evolution of legal reasoning over time (if applicable)\n4. Which judgment provides the strongest precedent and why\n5. Practical implications for future cases\n\nProvide a comprehensive comparative analysis suitable for litigation strategy."),
                ]
                for name, text in defaults:
                    cur.execute(
                        "INSERT INTO prompt_templates (name, prompt_text) VALUES (%s, %s)",
                        (name, text)
                    )
    finally:
        conn.close()


def get_fetched_dc_judgments(limit=50):
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT j.tid, j.title, j.court_source, j.publish_date,
                       LENGTH(j.full_text_html) as html_length,
                       CASE WHEN g.tid IS NOT NULL THEN TRUE ELSE FALSE END as has_genome,
                       g.overall_durability_score
                FROM judgments j
                LEFT JOIN judgment_genomes g ON j.tid = g.tid
                WHERE j.full_text_html IS NOT NULL
                  AND j.doctype = 'delhidc'
                ORDER BY j.fetched_at DESC NULLS LAST
                LIMIT %s
            """, (limit,))
            return cur.fetchall()
    finally:
        conn.close()
