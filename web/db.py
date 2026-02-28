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
            """)
    finally:
        conn.close()


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
