#!/usr/bin/env python3
"""Local RAG index helpers for Memoria."""

import fnmatch
import glob
import hashlib
import json
import math
import os
import re
import sqlite3
import tempfile
from collections import Counter, defaultdict
from datetime import datetime, timezone

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECTS_DIR = os.path.join(REPO_ROOT, "projects")

RAG_SCHEMA_VERSION = "3"
RAG_DEFAULTS = {
    "enabled": True,
    "indexDirName": ".memoria",
    "databaseName": "rag.sqlite",
    "include": ["README.md", "resources/**/*.md", "log.jsonl"],
    "exclude": ["inventory.md", ".memoria/**"],
    "maxFileBytes": 1024 * 1024,
    "chunk": {"targetChars": 1800, "overlapChars": 240, "maxChars": 2600},
    "retrieval": {"candidateLimit": 80, "defaultLimit": 10, "graphExpansionDepth": 1},
    "embedding": {"provider": "sparse-hash-v1", "dimensions": 4096, "charNgrams": [3, 4]},
}

STOPWORDS = {
    "a", "about", "above", "across", "after", "afterwards", "again", "against", "all", "almost",
    "alone", "along", "already", "also", "although", "always", "am", "among", "amongst", "amoungst",
    "amount", "an", "and", "another", "any", "anyhow", "anyone", "anything", "anyway", "anywhere",
    "are", "around", "as", "at", "back", "be", "became", "because", "become", "becomes", "becoming",
    "been", "before", "beforehand", "behind", "being", "below", "beside", "besides", "between", "beyond",
    "both", "bottom", "but", "by", "call", "can", "cannot", "cant", "co", "con", "could", "couldnt",
    "cry", "de", "describe", "detail", "did", "do", "does", "doing", "done", "down", "due", "during",
    "each", "eg", "eight", "either", "eleven", "else", "elsewhere", "empty", "enough", "etc", "even",
    "ever", "every", "everyone", "everything", "everywhere", "except", "few", "fifteen", "fifty", "fill",
    "find", "fire", "first", "five", "for", "former", "formerly", "forty", "found", "four", "from",
    "front", "full", "further", "get", "give", "go", "had", "has", "hasnt", "have", "he", "hence",
    "her", "here", "hereafter", "hereby", "herein", "hereupon", "hers", "herself", "him", "himself",
    "his", "how", "however", "hundred", "i", "ie", "if", "in", "inc", "indeed", "into", "is", "it",
    "its", "itself", "just", "keep", "last", "latter", "latterly", "least", "less", "ltd", "made", "many",
    "may", "me", "meanwhile", "might", "mill", "mine", "more", "moreover", "most", "mostly", "move",
    "much", "must", "my", "myself", "name", "namely", "neither", "never", "nevertheless", "next", "nine",
    "no", "nobody", "none", "noone", "nor", "not", "nothing", "now", "nowhere", "of", "off", "often",
    "on", "once", "one", "only", "onto", "or", "other", "others", "otherwise", "our", "ours", "ourselves",
    "out", "over", "own", "part", "per", "perhaps", "please", "put", "rather", "re", "same", "see",
    "seem", "seemed", "seeming", "seems", "serious", "several", "she", "should", "show", "side", "since",
    "sincere", "six", "sixty", "so", "some", "somehow", "someone", "something", "sometime", "sometimes",
    "somewhere", "still", "such", "take", "ten", "than", "that", "the", "their", "them", "themselves",
    "then", "thence", "there", "thereafter", "thereby", "therefore", "therein", "thereupon", "these", "they",
    "thick", "thin", "third", "this", "those", "though", "three", "through", "throughout", "thru", "thus",
    "to", "together", "too", "top", "toward", "towards", "twelve", "twenty", "two", "un", "under", "until",
    "up", "upon", "us", "very", "via", "was", "we", "well", "were", "what", "whatever", "when", "whence",
    "whenever", "where", "whereafter", "whereas", "whereby", "wherein", "whereupon", "wherever", "whether",
    "which", "while", "whither", "who", "whoever", "whole", "whom", "whose", "why", "will", "with", "within",
    "without", "would", "yet", "you", "your", "yours", "yourself", "yourselves",
}

def utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def relpath(path, base):
    return os.path.relpath(path, base).replace(os.sep, "/")


def project_dir(slug):
    return os.path.join(PROJECTS_DIR, slug)


def require_project_dir(slug):
    path = project_dir(slug)
    if not os.path.isdir(path):
        raise SystemExit("project not found: projects/%s/" % slug)
    return path


def parse_frontmatter(text):
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return None, text
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return None, text
    fields = {}
    for line in lines[1:end]:
        if not line.strip():
            continue
        m = re.match(r"^([A-Za-z0-9_-]+):(?:\s+(.*))?$", line)
        if not m:
            continue
        fields[m.group(1)] = _parse_scalar((m.group(2) or "").strip())
    body = "\n".join(lines[end + 1:])
    if body.startswith("\n"):
        body = body[1:]
    return fields, body


def _parse_scalar(raw):
    if raw == "":
        return ""
    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1].strip()
        if not inner:
            return []
        return [x.strip().strip('"').strip("'") for x in inner.split(",") if x.strip()]
    if len(raw) >= 2 and raw[0] == '"' and raw[-1] == '"':
        return raw[1:-1].replace('\\"', '"')
    if len(raw) >= 2 and raw[0] == "'" and raw[-1] == "'":
        return raw[1:-1].replace("''", "'")
    return raw


def frontmatter_body_line_offset(text):
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return 0
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return index + 1 + (1 if index + 1 < len(lines) and lines[index + 1] == "" else 0)
    return 0


def unique_preserving(values):
    seen = set()
    out = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def load_json_file(path):
    with open(path, encoding="utf-8") as f:
        text = f.read().strip()
    return json.loads(text) if text else {}


def deep_merge(base, overrides):
    if not isinstance(base, dict) or not isinstance(overrides, dict):
        return overrides
    merged = dict(base)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_rag_config():
    path = os.path.join(REPO_ROOT, "memoria.config.yml")
    config = load_json_file(path) if os.path.isfile(path) else {}
    return deep_merge(RAG_DEFAULTS, config.get("rag", {}))


def rag_dir_for_project(slug, config=None):
    config = config or load_rag_config()
    return os.path.join(project_dir(slug), config["indexDirName"])


def rag_db_path(slug, config=None):
    config = config or load_rag_config()
    return os.path.join(rag_dir_for_project(slug, config), config["databaseName"])


def ensure_rag_dir(slug, config=None):
    path = rag_dir_for_project(slug, config)
    os.makedirs(path, exist_ok=True)
    return path


def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def is_probably_binary(path):
    with open(path, "rb") as f:
        sample = f.read(4096)
    return b"\x00" in sample


def normalize_path_text(value):
    return (value or "").replace("\\", "/")


def normalize_text(text):
    return re.sub(r"\s+", " ", text or "").strip()


def tokenize(text):
    tokens = re.findall(r"[a-z0-9]+(?:[._/-][a-z0-9]+)*", (text or "").lower())
    return [t for t in tokens if t not in STOPWORDS]


def build_fts_queries(text):
    terms = tokenize(text)
    if not terms:
        return []
    phrases = ['"%s"' % term.replace('"', '""') for term in unique_preserving(terms)]
    if len(phrases) == 1:
        return phrases
    queries = [" ".join(phrases)]
    if len(phrases) <= 4:
        queries.append(" OR ".join(phrases))
    else:
        strong = phrases[:4]
        fallback = phrases[:8]
        queries.append(" ".join(strong))
        queries.append(" OR ".join(fallback))
    return unique_preserving(queries)


def build_fts_query(text):
    queries = build_fts_queries(text)
    return queries[0] if queries else None


def hash_feature(feature, dims):
    digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big") % dims


def text_to_vector(text, config):
    dims = config["embedding"]["dimensions"]
    char_ngrams = config["embedding"].get("charNgrams", [3, 4])
    tokens = tokenize(text)
    feats = Counter(tokens)
    feats.update("%s__%s" % (a, b) for a, b in zip(tokens, tokens[1:]))
    for token in tokens:
        compact = token.replace("/", "").replace("-", "").replace("_", "").replace(".", "")
        for n in char_ngrams:
            if len(compact) >= n:
                feats.update("c%d:%s" % (n, compact[i:i + n]) for i in range(0, len(compact) - n + 1))
    dense = defaultdict(float)
    for feature, weight in feats.items():
        dense[hash_feature(feature, dims)] += float(weight)
    norm = math.sqrt(sum(v * v for v in dense.values())) or 1.0
    vector = {k: v / norm for k, v in dense.items() if v}
    return vector, norm


def vector_to_json(vector):
    return json.dumps([[k, round(v, 6)] for k, v in sorted(vector.items())], separators=(",", ":"))


def vector_from_json(text):
    return {int(k): float(v) for k, v in (json.loads(text) if text else [])}


def cosine_similarity(vec_a, vec_b):
    if len(vec_a) > len(vec_b):
        vec_a, vec_b = vec_b, vec_a
    return sum(weight * vec_b.get(dim, 0.0) for dim, weight in vec_a.items())


def fts5_available(conn):
    try:
        conn.execute("CREATE VIRTUAL TABLE temp._fts5_probe USING fts5(x)")
        conn.execute("DROP TABLE temp._fts5_probe")
        return True
    except sqlite3.OperationalError:
        return False


def connect_db(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def create_schema(conn, use_fts5=True):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS meta (
          key TEXT PRIMARY KEY,
          value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS files (
          id INTEGER PRIMARY KEY,
          project TEXT NOT NULL,
          path TEXT NOT NULL,
          sha256 TEXT NOT NULL,
          mtime_ns INTEGER NOT NULL,
          size INTEGER NOT NULL,
          kind TEXT NOT NULL,
          title TEXT,
          resource_type TEXT,
          source TEXT,
          source_ref TEXT,
          connector TEXT,
          tags_json TEXT NOT NULL DEFAULT '[]',
          summary TEXT,
          updated TEXT,
          indexed_at TEXT NOT NULL,
          UNIQUE(project, path)
        );
        CREATE TABLE IF NOT EXISTS chunks (
          id INTEGER PRIMARY KEY,
          file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
          ordinal INTEGER NOT NULL,
          heading_path TEXT,
          line_start INTEGER NOT NULL,
          line_end INTEGER NOT NULL,
          text TEXT NOT NULL,
          vector_norm REAL NOT NULL DEFAULT 1.0,
          vector_json TEXT NOT NULL,
          UNIQUE(file_id, ordinal)
        );
        CREATE TABLE IF NOT EXISTS chunk_terms (
          chunk_id INTEGER NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
          term_hash INTEGER NOT NULL,
          weight REAL NOT NULL,
          PRIMARY KEY(chunk_id, term_hash)
        );
        CREATE INDEX IF NOT EXISTS idx_chunk_terms_hash ON chunk_terms(term_hash);
        CREATE TABLE IF NOT EXISTS file_edges (
          src_file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
          dst_file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
          kind TEXT NOT NULL,
          weight REAL NOT NULL,
          evidence TEXT,
          PRIMARY KEY(src_file_id, dst_file_id, kind, evidence)
        );
        CREATE INDEX IF NOT EXISTS idx_file_edges_src ON file_edges(src_file_id);
        CREATE INDEX IF NOT EXISTS idx_file_edges_dst ON file_edges(dst_file_id);
        """
    )
    if use_fts5:
        conn.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS chunk_fts USING fts5(path, title, heading_path, tags, summary, text)"
        )
    conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('schema_version', ?)", (RAG_SCHEMA_VERSION,))
    conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('fts5_enabled', ?)", ("1" if use_fts5 else "0",))
    conn.commit()


def schema_version(conn):
    row = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
    return row[0] if row else None


def fts_enabled(conn):
    row = conn.execute("SELECT value FROM meta WHERE key='fts5_enabled'").fetchone()
    return bool(row and row[0] == "1")


def path_is_excluded(rel_path, exclude_patterns):
    return any(
        fnmatch.fnmatch(rel_path, pattern) or fnmatch.fnmatch(rel_path + "/", pattern.rstrip("/"))
        for pattern in exclude_patterns
    )


def discover_project_files(slug, config=None, include_log=True):
    config = config or load_rag_config()
    pdir = project_dir(slug)
    include_patterns = list(config.get("include", []))
    if not include_log:
        include_patterns = [pattern for pattern in include_patterns if pattern != "log.jsonl"]
    exclude_patterns = list(config.get("exclude", []))
    out = set()
    for pattern in include_patterns:
        full_pattern = os.path.join(pdir, pattern)
        for path in glob.glob(full_pattern, recursive=True):
            if os.path.isdir(path):
                continue
            rel = relpath(path, pdir)
            if path_is_excluded(rel, exclude_patterns):
                continue
            out.add(path)
    return sorted(out, key=lambda path: relpath(path, pdir))


def build_metadata_prefix(meta, heading_path=None):
    lines = []
    if meta.get("title"):
        lines.append("Title: %s" % meta["title"])
    if meta.get("resource_type"):
        lines.append("Type: %s" % meta["resource_type"])
    if meta.get("tags"):
        lines.append("Tags: %s" % ", ".join(meta["tags"]))
    if meta.get("summary"):
        lines.append("Summary: %s" % meta["summary"])
    if heading_path:
        lines.append("Heading: %s" % heading_path)
    return ("\n".join(lines).strip() + "\n\n") if lines else ""


def chunk_markdown_text(body, meta, config, line_offset=0):
    lines = body.splitlines()
    sections = []
    current_heading = []
    current_start = 1 + line_offset
    current_lines = []
    current_heading_text = ""

    def flush(end_line):
        if current_lines or current_heading_text:
            sections.append({
                "heading_path": " > ".join(current_heading),
                "line_start": current_start,
                "line_end": max(current_start, end_line),
                "lines": list(current_lines),
                "heading_line": current_heading_text,
            })

    for idx, line in enumerate(lines, start=1 + line_offset):
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            flush(idx - 1)
            level = len(m.group(1))
            current_heading = current_heading[:level - 1] + [m.group(2).strip()]
            current_heading_text = line
            current_start = idx
            current_lines = [line]
        else:
            current_lines.append(line)
    flush(len(lines) + line_offset)
    if not sections:
        sections = [{
            "heading_path": "",
            "line_start": 1 + line_offset,
            "line_end": max(1 + line_offset, len(lines) + line_offset),
            "lines": lines,
            "heading_line": "",
        }]

    chunks = []
    ordinal = 0
    target = int(config["chunk"]["targetChars"])
    max_chars = int(config["chunk"]["maxChars"])
    overlap = int(config["chunk"]["overlapChars"])

    for section in sections:
        block = [{"line_no": section["line_start"] + i, "text": text} for i, text in enumerate(section["lines"])]
        start = 0
        while start < len(block):
            total = 0
            end = start
            while end < len(block):
                next_total = total + len(block[end]["text"]) + 1
                if end > start and next_total > target:
                    break
                total = next_total
                end += 1
                if total >= max_chars:
                    break
            if end <= start:
                end = start + 1
            subset = block[start:end]
            body_text = "\n".join(item["text"] for item in subset).strip("\n")
            prefix = build_metadata_prefix(meta, section["heading_path"])
            chunks.append({
                "ordinal": ordinal,
                "heading_path": section["heading_path"],
                "line_start": subset[0]["line_no"],
                "line_end": subset[-1]["line_no"],
                "text": prefix + body_text,
                "snippet": body_text,
            })
            ordinal += 1
            if end >= len(block):
                break
            overlap_chars = 0
            next_start = end
            while next_start > start and overlap_chars < overlap:
                next_start -= 1
                overlap_chars += len(block[next_start]["text"]) + 1
            start = max(start + 1, next_start)
    return chunks


def chunk_log_text(text, config):
    lines = [ln for ln in text.splitlines() if ln.strip()]
    chunks = []
    batch = []
    batch_text_len = 0
    ordinal = 0
    for idx, line in enumerate(lines, start=1):
        try:
            obj = json.loads(line)
        except ValueError:
            obj = {"kind": "unknown", "summary": line}
        rendered = "[{ts}] {kind} {summary}".format(
            ts=obj.get("ts", ""), kind=obj.get("kind", ""), summary=obj.get("summary", "")
        )
        if obj.get("resource"):
            rendered += " resource=%s" % obj["resource"]
        if obj.get("tags"):
            rendered += " tags=%s" % ", ".join(obj["tags"])
        batch.append((idx, rendered))
        batch_text_len += len(rendered) + 1
        if len(batch) >= 40 or batch_text_len >= config["chunk"]["targetChars"]:
            chunk_text = "\n".join(item[1] for item in batch)
            chunks.append({
                "ordinal": ordinal,
                "heading_path": "activity log",
                "line_start": batch[0][0],
                "line_end": batch[-1][0],
                "text": "Log entries\n\n" + chunk_text,
                "snippet": chunk_text,
            })
            ordinal += 1
            batch = []
            batch_text_len = 0
    if batch:
        chunk_text = "\n".join(item[1] for item in batch)
        chunks.append({
            "ordinal": ordinal,
            "heading_path": "activity log",
            "line_start": batch[0][0],
            "line_end": batch[-1][0],
            "text": "Log entries\n\n" + chunk_text,
            "snippet": chunk_text,
        })
    return chunks


def parse_file_for_index(slug, abs_path, config):
    pdir = require_project_dir(slug)
    rel = relpath(abs_path, pdir)
    size = os.path.getsize(abs_path)
    if size > int(config["maxFileBytes"]):
        return {"status": "skipped", "reason": "max-bytes", "path": rel, "size": size}
    if is_probably_binary(abs_path):
        return {"status": "skipped", "reason": "binary", "path": rel, "size": size}
    with open(abs_path, encoding="utf-8") as f:
        text = f.read()
    mtime_ns = os.stat(abs_path).st_mtime_ns
    sha256 = file_sha256(abs_path)

    kind = "markdown"
    meta = {
        "title": os.path.basename(rel),
        "resource_type": "document",
        "source": "local",
        "source_ref": rel,
        "connector": "",
        "tags": [],
        "summary": "",
        "updated": "",
    }
    graph = {"links": [], "mentions": [], "tags": [], "source_ref": "", "connector": "", "source": ""}

    if rel == "log.jsonl":
        kind = "log"
        meta["title"] = "Activity log"
        meta["resource_type"] = "log"
        chunks = chunk_log_text(text, config)
        for line in text.splitlines():
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            resource = normalize_path_text(obj.get("resource", ""))
            if resource:
                graph["links"].append(resource)
            graph["tags"].extend(obj.get("tags") or [])
        graph["links"] = unique_preserving(graph["links"])
        graph["tags"] = unique_preserving(graph["tags"])
    else:
        fields, body = parse_frontmatter(text)
        body_line_offset = frontmatter_body_line_offset(text)
        meta.update({
            "title": (fields or {}).get("title") or (fields or {}).get("project") or os.path.basename(rel),
            "resource_type": (fields or {}).get("type") or ("readme" if rel == "README.md" else "document"),
            "source": (fields or {}).get("source") or "local",
            "source_ref": (fields or {}).get("source-ref") or rel,
            "connector": (fields or {}).get("connector") or "",
            "tags": (fields or {}).get("tags") or [],
            "summary": (fields or {}).get("summary") or "",
            "updated": (fields or {}).get("updated") or "",
        })
        chunks = chunk_markdown_text(body, meta, config, line_offset=body_line_offset)
        graph["source_ref"] = meta["source_ref"]
        graph["connector"] = meta["connector"]
        graph["source"] = meta["source"]
        graph["tags"] = unique_preserving(list(meta["tags"]))
        for link in re.findall(r"\[[^\]]+\]\(([^)]+)\)", body):
            if re.match(r"^[a-z]+://", link):
                continue
            link_path = normalize_path_text(link.split("#", 1)[0])
            if not link_path:
                continue
            norm = os.path.normpath(os.path.join(os.path.dirname(rel), link_path)).replace(os.sep, "/")
            graph["links"].append(norm)
        for mention in re.findall(r"(?:README\.md|log\.jsonl|resources/[A-Za-z0-9_./-]+\.md)", body):
            graph["mentions"].append(normalize_path_text(mention))
        graph["links"] = unique_preserving(graph["links"])
        graph["mentions"] = unique_preserving(graph["mentions"])
    return {
        "status": "ok",
        "path": rel,
        "abs_path": abs_path,
        "kind": kind,
        "size": size,
        "mtime_ns": mtime_ns,
        "sha256": sha256,
        "meta": meta,
        "chunks": chunks,
        "graph": graph,
    }


def delete_file_index(conn, file_id):
    chunk_ids = [row[0] for row in conn.execute("SELECT id FROM chunks WHERE file_id=?", (file_id,)).fetchall()]
    if chunk_ids and fts_enabled(conn):
        conn.executemany("DELETE FROM chunk_fts WHERE rowid=?", [(chunk_id,) for chunk_id in chunk_ids])
    conn.execute("DELETE FROM files WHERE id=?", (file_id,))


def include_log_for_args(args):
    return not getattr(args, "no_log", False)


def upsert_file_index(conn, slug, record, config):
    row = conn.execute("SELECT id FROM files WHERE project=? AND path=?", (slug, record["path"])).fetchone()
    if row:
        delete_file_index(conn, row[0])
    meta = record["meta"]
    conn.execute(
        """
        INSERT INTO files(project, path, sha256, mtime_ns, size, kind, title, resource_type, source, source_ref,
                          connector, tags_json, summary, updated, indexed_at)
        VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            slug, record["path"], record["sha256"], record["mtime_ns"], record["size"], record["kind"],
            meta.get("title"), meta.get("resource_type"), meta.get("source"), meta.get("source_ref"),
            meta.get("connector"), json.dumps(meta.get("tags") or [], separators=(",", ":")), meta.get("summary"),
            meta.get("updated"), utc_now(),
        ),
    )
    file_id = conn.execute("SELECT id FROM files WHERE project=? AND path=?", (slug, record["path"])).fetchone()[0]
    for chunk in record["chunks"]:
        vector, norm = text_to_vector(chunk["text"], config)
        conn.execute(
            "INSERT INTO chunks(file_id, ordinal, heading_path, line_start, line_end, text, vector_norm, vector_json) VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
            (file_id, chunk["ordinal"], chunk["heading_path"], chunk["line_start"], chunk["line_end"], chunk["text"], norm, vector_to_json(vector)),
        )
        chunk_id = conn.execute("SELECT id FROM chunks WHERE file_id=? AND ordinal=?", (file_id, chunk["ordinal"])).fetchone()[0]
        conn.executemany(
            "INSERT INTO chunk_terms(chunk_id, term_hash, weight) VALUES(?, ?, ?)",
            [(chunk_id, dim, weight) for dim, weight in vector.items()],
        )
        if fts_enabled(conn):
            conn.execute(
                "INSERT INTO chunk_fts(rowid, path, title, heading_path, tags, summary, text) VALUES(?, ?, ?, ?, ?, ?, ?)",
                (
                    chunk_id,
                    record["path"],
                    meta.get("title") or "",
                    chunk["heading_path"] or "",
                    ", ".join(meta.get("tags") or []),
                    meta.get("summary") or "",
                    chunk["text"],
                ),
            )
    return {
        "file_id": file_id,
        "path": record["path"],
        "kind": record["kind"],
        "meta": record["meta"],
        "graph": record["graph"],
    }


def existing_file_rows(conn, slug):
    return {row["path"]: row for row in conn.execute("SELECT * FROM files WHERE project=?", (slug,)).fetchall()}


def init_db(path):
    conn = connect_db(path)
    create_schema(conn, use_fts5=fts5_available(conn))
    return conn


def ensure_project_index(slug, config=None):
    require_project_dir(slug)
    config = config or load_rag_config()
    path = rag_db_path(slug, config)
    if os.path.isfile(path):
        conn = connect_db(path)
        if schema_version(conn) == RAG_SCHEMA_VERSION:
            return conn
        conn.close()
    ensure_rag_dir(slug, config)
    return rebuild_index(slug, config=config, return_conn=True)


def rebuild_graph(conn, slug, file_infos):
    conn.execute("DELETE FROM file_edges")
    path_to_id = {row["path"]: row["id"] for row in conn.execute("SELECT id, path FROM files WHERE project=?", (slug,)).fetchall()}
    tag_buckets = defaultdict(list)
    source_ref_buckets = defaultdict(list)
    connector_buckets = defaultdict(list)
    for info in file_infos:
        tags = info["meta"].get("tags") or info["graph"].get("tags") or []
        for tag in tags:
            tag_buckets[tag].append(info["path"])
        source_ref = normalize_text(info["graph"].get("source_ref", "").lower())
        if source_ref and source_ref not in {"manual", "local", info["path"].lower()}:
            source_ref_buckets[source_ref].append(info["path"])
        connector_id = (info["graph"].get("connector", "") or "").strip()
        source_name = (info["graph"].get("source", "") or "").strip()
        if connector_id:
            connector_buckets["%s::%s" % (connector_id, source_name)].append(info["path"])

    def add_edge(src, dst, kind, weight, evidence):
        if src == dst or src not in path_to_id or dst not in path_to_id:
            return
        conn.execute(
            "INSERT OR REPLACE INTO file_edges(src_file_id, dst_file_id, kind, weight, evidence) VALUES(?, ?, ?, ?, ?)",
            (path_to_id[src], path_to_id[dst], kind, weight, evidence),
        )

    for info in file_infos:
        src = info["path"]
        for dst in info["graph"].get("links") or []:
            add_edge(src, dst, "markdown-link", 1.0, dst)
        for dst in info["graph"].get("mentions") or []:
            add_edge(src, dst, "mentions-path", 0.45, dst)

    for source_ref, paths in source_ref_buckets.items():
        if len(paths) < 2:
            continue
        for src in paths:
            for dst in paths:
                if src != dst:
                    add_edge(src, dst, "source-ref", 0.8, source_ref)

    for connector, paths in connector_buckets.items():
        if len(paths) < 2:
            continue
        for src in paths:
            for dst in paths:
                if src != dst:
                    add_edge(src, dst, "connector", 0.35, connector)

    for tag, paths in tag_buckets.items():
        if len(paths) < 2:
            continue
        rarity_weight = max(0.15, min(0.6, 1.0 / len(paths)))
        for src in paths:
            for dst in paths:
                if src != dst:
                    add_edge(src, dst, "tag", rarity_weight, tag)
    conn.commit()


def rebuild_index(slug, config=None, include_log=True, return_conn=False):
    require_project_dir(slug)
    config = config or load_rag_config()
    ensure_rag_dir(slug, config)
    final_path = rag_db_path(slug, config)
    fd, temp_path = tempfile.mkstemp(prefix="rag-", suffix=".sqlite", dir=rag_dir_for_project(slug, config))
    os.close(fd)
    conn = None
    stats = {"indexed_files": 0, "indexed_chunks": 0, "skipped": []}
    try:
        conn = init_db(temp_path)
        files = discover_project_files(slug, config, include_log=include_log)
        indexed_infos = []
        for path in files:
            record = parse_file_for_index(slug, path, config)
            if record["status"] != "ok":
                stats["skipped"].append({"path": record["path"], "reason": record["reason"]})
                continue
            info = upsert_file_index(conn, slug, record, config)
            indexed_infos.append(info)
            stats["indexed_files"] += 1
            stats["indexed_chunks"] += len(record["chunks"])
        rebuild_graph(conn, slug, indexed_infos)
        conn.commit()
        conn.close()
        conn = None
        os.replace(temp_path, final_path)
        if return_conn:
            return connect_db(final_path)
        return stats
    finally:
        if conn is not None:
            conn.close()
        if os.path.exists(temp_path):
            os.remove(temp_path)


def update_index(slug, config=None, include_log=True):
    require_project_dir(slug)
    config = config or load_rag_config()
    path = rag_db_path(slug, config)
    if not os.path.isfile(path):
        stats = rebuild_index(slug, config=config, include_log=include_log)
        stats["rebuilt"] = True
        return stats
    conn = connect_db(path)
    if schema_version(conn) != RAG_SCHEMA_VERSION:
        conn.close()
        stats = rebuild_index(slug, config=config, include_log=include_log)
        stats["rebuilt"] = True
        return stats
    existing = existing_file_rows(conn, slug)
    current_paths = discover_project_files(slug, config, include_log=include_log)
    current_rel_paths = {relpath(p, project_dir(slug)): p for p in current_paths}
    stats = {"indexed_files": 0, "indexed_chunks": 0, "removed_files": 0, "skipped": [], "rebuilt": False}

    for rel, row in list(existing.items()):
        if rel not in current_rel_paths:
            delete_file_index(conn, row["id"])
            stats["removed_files"] += 1

    for rel, abs_path in current_rel_paths.items():
        st = os.stat(abs_path)
        row = existing.get(rel)
        should_index = row is None or int(row["mtime_ns"]) != int(st.st_mtime_ns) or int(row["size"]) != int(st.st_size)
        if not should_index:
            continue
        record = parse_file_for_index(slug, abs_path, config)
        if record["status"] != "ok":
            if row is not None:
                delete_file_index(conn, row["id"])
            stats["skipped"].append({"path": rel, "reason": record["reason"]})
            continue
        if row is not None and row["sha256"] == record["sha256"] and int(row["size"]) == int(record["size"]):
            conn.execute(
                "UPDATE files SET mtime_ns=?, indexed_at=? WHERE id=?",
                (record["mtime_ns"], utc_now(), row["id"]),
            )
            continue
        upsert_file_index(conn, slug, record, config)
        stats["indexed_files"] += 1
        stats["indexed_chunks"] += len(record["chunks"])

    all_infos = []
    for row in conn.execute("SELECT path FROM files WHERE project=? ORDER BY path", (slug,)).fetchall():
        abs_path = os.path.join(project_dir(slug), row["path"])
        if os.path.isfile(abs_path):
            parsed = parse_file_for_index(slug, abs_path, config)
            if parsed["status"] == "ok":
                all_infos.append({"path": parsed["path"], "meta": parsed["meta"], "graph": parsed["graph"]})
    rebuild_graph(conn, slug, all_infos)
    conn.commit()
    conn.close()
    return stats


def fetch_candidates(conn, query, candidate_limit, query_vector):
    candidates = {}
    query_dims = list(query_vector.items())
    if fts_enabled(conn):
        for fts_query in build_fts_queries(query):
            try:
                rows = conn.execute(
                    """
                    SELECT c.id, c.file_id, c.heading_path, c.line_start, c.line_end, c.text, c.vector_json,
                           f.path, f.title, f.tags_json, f.summary, bm25(chunk_fts) AS bm25
                    FROM chunk_fts
                    JOIN chunks c ON c.id = chunk_fts.rowid
                    JOIN files f ON f.id = c.file_id
                    WHERE chunk_fts MATCH ?
                    ORDER BY bm25(chunk_fts)
                    LIMIT ?
                    """,
                    (fts_query, candidate_limit),
                ).fetchall()
            except sqlite3.OperationalError:
                continue
            total = len(rows)
            for index, row in enumerate(rows):
                score = 1.0 if total <= 1 else 1.0 - (index / float(total - 1))
                chunk = candidates.setdefault(row["id"], dict(row))
                chunk["fts_score"] = max(float(chunk.get("fts_score", 0.0) or 0.0), score)
            if len(candidates) >= candidate_limit:
                break
    if not candidates and query_dims:
        dim_weights = {dim: weight for dim, weight in query_dims}
        placeholders = ",".join("?" for _ in dim_weights)
        rows = conn.execute(
            """
            SELECT c.id, c.file_id, c.heading_path, c.line_start, c.line_end, c.text, c.vector_json,
                   f.path, f.title, f.tags_json, f.summary, ct.term_hash, ct.weight
            FROM chunk_terms ct
            JOIN chunks c ON c.id = ct.chunk_id
            JOIN files f ON f.id = c.file_id
            WHERE ct.term_hash IN (""" + placeholders + """)
            """,
            tuple(dim_weights.keys()),
        ).fetchall()
        scored = {}
        for row in rows:
            chunk = scored.setdefault(row["id"], dict(row))
            chunk["approx_score"] = chunk.get("approx_score", 0.0) + float(row["weight"]) * dim_weights.get(row["term_hash"], 0.0)
        for row in sorted(scored.values(), key=lambda item: item.get("approx_score", 0.0), reverse=True)[:candidate_limit]:
            candidates[row["id"]] = row
            candidates[row["id"]]["fts_score"] = 0.0
    return list(candidates.values())


def metadata_match_score(query_tokens, row):
    haystack = " ".join([
        row.get("path", "") or "",
        row.get("title", "") or "",
        row.get("summary", "") or "",
        " ".join(json.loads(row.get("tags_json") or "[]")),
        row.get("heading_path", "") or "",
    ]).lower()
    if not query_tokens:
        return 0.0, []
    hits = [token for token in query_tokens if token in haystack]
    return min(1.0, len(hits) / max(1, len(query_tokens))), hits[:4]


def build_why(result, graph_evidence):
    why = []
    if result["fts_score"] > 0.1:
        why.append("fts")
    if result["sparse_score"] > 0.15:
        why.append("semantic")
    if result["metadata_hits"]:
        why.append("metadata: %s" % ", ".join(result["metadata_hits"]))
    graph_kinds = sorted(set(graph_evidence.get(result["file_id"], [])))
    if graph_kinds:
        why.append("graph: %s" % ", ".join(graph_kinds))
    return why


def overlaps_existing_path(result, selected):
    return any(item["path"] == result["path"] for item in selected)


def graph_boosts(conn, base_results):
    file_scores = defaultdict(float)
    top_file_ids = []
    for result in sorted(base_results, key=lambda item: item["base_score"], reverse=True)[:10]:
        file_id = result["file_id"]
        if file_id not in file_scores:
            top_file_ids.append(file_id)
        file_scores[file_id] = max(file_scores[file_id], result["base_score"])
    boosts = defaultdict(float)
    evidence = defaultdict(list)
    for file_id in top_file_ids:
        rows = conn.execute(
            "SELECT dst_file_id, kind, weight, evidence FROM file_edges WHERE src_file_id=?",
            (file_id,),
        ).fetchall()
        for row in rows:
            boost = file_scores[file_id] * float(row["weight"]) * 0.2
            boosts[row["dst_file_id"]] = max(boosts[row["dst_file_id"]], boost)
            evidence[row["dst_file_id"]].append(row["kind"])
    return boosts, evidence


def snippet_from_text(text):
    parts = text.split("\n\n", 1)
    body = parts[1] if len(parts) == 2 and parts[0].startswith(("Title:", "Type:", "Tags:", "Summary:", "Heading:")) else text
    return normalize_text(body)[:280]


def search_index(slug, query, limit=None, candidate_limit=None, no_refresh=False, include_log=True):
    config = load_rag_config()
    if not no_refresh:
        update_index(slug, config=config, include_log=include_log)
    conn = ensure_project_index(slug, config=config)
    limit = limit or config["retrieval"]["defaultLimit"]
    candidate_limit = candidate_limit or config["retrieval"]["candidateLimit"]
    query_vector, _ = text_to_vector(query, config)
    query_tokens = tokenize(query)
    candidates = fetch_candidates(conn, query, candidate_limit, query_vector)
    base_results = []
    for row in candidates:
        vector = vector_from_json(row["vector_json"])
        sparse = cosine_similarity(query_vector, vector)
        meta_score, meta_hits = metadata_match_score(query_tokens, row)
        fts_score = float(row.get("fts_score", 0.0) or 0.0)
        base_score = 0.5 * fts_score + 0.35 * sparse + 0.10 * meta_score
        base_results.append({
            "chunk_id": row["id"],
            "file_id": row["file_id"],
            "path": row["path"],
            "title": row["title"],
            "heading_path": row["heading_path"],
            "line_start": row["line_start"],
            "line_end": row["line_end"],
            "text": row["text"],
            "snippet": snippet_from_text(row["text"]),
            "fts_score": fts_score,
            "sparse_score": sparse,
            "metadata_score": meta_score,
            "metadata_hits": meta_hits,
            "base_score": base_score,
        })
    boosts, graph_evidence = graph_boosts(conn, base_results)
    ranked = []
    for result in base_results:
        graph_score = boosts.get(result["file_id"], 0.0)
        payload = dict(result)
        payload["graph_score"] = graph_score
        payload["score"] = result["base_score"] + 0.05 * graph_score
        payload["why"] = build_why(payload, graph_evidence)
        ranked.append(payload)
    ranked.sort(
        key=lambda item: (
            -item["score"],
            -item["fts_score"],
            -item["sparse_score"],
            item["path"],
            item["line_start"],
            item["chunk_id"],
        )
    )

    results = []
    for result in ranked:
        if overlaps_existing_path(result, results):
            continue
        results.append(result)
        if len(results) >= limit:
            break

    conn.close()
    return results


def related_files(slug, rel_path, limit=20):
    conn = ensure_project_index(slug)
    row = conn.execute("SELECT id, path FROM files WHERE project=? AND path=?", (slug, rel_path)).fetchone()
    if not row:
        conn.close()
        raise ValueError("path is not indexed: %s" % rel_path)
    rows = conn.execute(
        """
        SELECT path, kind, weight, evidence
        FROM (
          SELECT other.path AS path, e.kind AS kind, e.weight AS weight, e.evidence AS evidence
          FROM file_edges e
          JOIN files other ON other.id = e.dst_file_id
          WHERE e.src_file_id=?
          UNION ALL
          SELECT other.path AS path, e.kind AS kind, e.weight AS weight, e.evidence AS evidence
          FROM file_edges e
          JOIN files other ON other.id = e.src_file_id
          WHERE e.dst_file_id=?
        )
        ORDER BY weight DESC, path ASC, kind ASC, evidence ASC
        """,
        (row["id"], row["id"]),
    ).fetchall()
    conn.close()
    grouped = {}
    for item in rows:
        entry = grouped.setdefault(item["path"], {"path": item["path"], "weight": 0.0, "kinds": [], "evidence": []})
        entry["weight"] = max(entry["weight"], float(item["weight"]))
        if item["kind"] and item["kind"] not in entry["kinds"]:
            entry["kinds"].append(item["kind"])
        if item["evidence"] and item["evidence"] not in entry["evidence"]:
            entry["evidence"].append(item["evidence"])
    return sorted(grouped.values(), key=lambda item: (-item["weight"], item["path"]))[:limit]


def stats_for_project(slug):
    conn = ensure_project_index(slug)
    edge_counts = {row["kind"]: row["count"] for row in conn.execute("SELECT kind, COUNT(*) AS count FROM file_edges GROUP BY kind").fetchall()}
    data = {
        "files": conn.execute("SELECT COUNT(*) FROM files WHERE project=?", (slug,)).fetchone()[0],
        "chunks": conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0],
        "edge_counts": edge_counts,
        "db_path": rag_db_path(slug),
        "db_size": os.path.getsize(rag_db_path(slug)) if os.path.isfile(rag_db_path(slug)) else 0,
        "indexed_at_oldest": conn.execute("SELECT MIN(indexed_at) FROM files WHERE project=?", (slug,)).fetchone()[0],
        "indexed_at_newest": conn.execute("SELECT MAX(indexed_at) FROM files WHERE project=?", (slug,)).fetchone()[0],
        "fts5_enabled": fts_enabled(conn),
        "schema_version": schema_version(conn),
    }
    conn.close()
    return data


def doctor_for_project(slug):
    require_project_dir(slug)
    config = load_rag_config()
    db_path = rag_db_path(slug, config)
    issues = []
    if not os.path.isfile(db_path):
        issues.append("index missing — run `bin/memoria rag rebuild --project %s`" % slug)
        return {"ok": False, "issues": issues, "db_path": db_path}
    conn = connect_db(db_path)
    if schema_version(conn) != RAG_SCHEMA_VERSION:
        issues.append("schema version mismatch — rebuild recommended")
    if not fts_enabled(conn):
        issues.append("FTS5 unavailable — search falls back to sparse term matching")
    discovered = {relpath(path, project_dir(slug)) for path in discover_project_files(slug, config)}
    indexed = {row["path"] for row in conn.execute("SELECT path FROM files WHERE project=?", (slug,)).fetchall()}
    stale = sorted(discovered.symmetric_difference(indexed))
    if stale:
        issues.append("index is stale for %d path(s)" % len(stale))
    conn.close()
    return {"ok": not issues, "issues": issues, "stale_paths": stale[:20], "db_path": db_path}


def format_human_results(results):
    lines = []
    for idx, item in enumerate(results, start=1):
        lines.append("%d. %s:%s-%s  score=%.3f" % (idx, item["path"], item["line_start"], item["line_end"], item["score"]))
        if item.get("title"):
            lines.append("   title: %s" % item["title"])
        if item.get("why"):
            lines.append("   why: %s" % "; ".join(item["why"]))
        lines.append("   snippet: %s" % item["snippet"])
        lines.append("")
    return "\n".join(lines).rstrip() or "No results"


def format_context_results(slug, results):
    lines = ["# Memoria RAG context for project %s" % slug, ""]
    for idx, item in enumerate(results, start=1):
        lines.extend([
            "## Hit %d" % idx,
            "path: %s" % item["path"],
            "lines: %s-%s" % (item["line_start"], item["line_end"]),
            "score: %.3f" % item["score"],
            "why: %s" % (", ".join(item["why"]) if item["why"] else "n/a"),
            "",
            item["snippet"],
            "",
        ])
    return "\n".join(lines).rstrip()


def cmd_rag_rebuild(args):
    config = load_rag_config()
    stats = rebuild_index(args.project, config=config, include_log=include_log_for_args(args))
    if args.json:
        print(json.dumps(stats, indent=2, ensure_ascii=False))
        return
    print("Indexed %d files, %d chunks" % (stats["indexed_files"], stats["indexed_chunks"]))
    for skipped in stats["skipped"]:
        print("Skipped %s (%s)" % (skipped["path"], skipped["reason"]))


def cmd_rag_update(args):
    config = load_rag_config()
    stats = update_index(args.project, config=config, include_log=include_log_for_args(args))
    if args.json:
        print(json.dumps(stats, indent=2, ensure_ascii=False))
        return
    if stats.get("rebuilt"):
        print("Index rebuilt")
    print("Updated %d files, %d chunks; removed %d files" % (stats["indexed_files"], stats["indexed_chunks"], stats["removed_files"]))
    for skipped in stats["skipped"]:
        print("Skipped %s (%s)" % (skipped["path"], skipped["reason"]))


def cmd_rag_search(args):
    results = search_index(
        args.project,
        args.query,
        limit=args.limit,
        candidate_limit=args.candidate_limit,
        no_refresh=args.no_refresh,
        include_log=include_log_for_args(args),
    )
    if args.paths_only:
        seen = []
        for item in results:
            if item["path"] not in seen:
                seen.append(item["path"])
        print("\n".join(seen))
        return
    if args.json:
        payload = []
        for item in results:
            data = {k: item[k] for k in ["path", "line_start", "line_end", "score", "snippet", "why", "title", "heading_path"]}
            if args.debug:
                data.update({k: item[k] for k in ["fts_score", "sparse_score", "metadata_score", "graph_score"]})
            payload.append(data)
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    if args.format == "context":
        print(format_context_results(args.project, results))
        return
    print(format_human_results(results))


def cmd_rag_related(args):
    try:
        rows = related_files(args.project, args.path, limit=args.limit)
    except ValueError as exc:
        raise SystemExit(str(exc))
    if args.json:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
        return
    if not rows:
        print("No related files")
        return
    for row in rows:
        print("- %s" % row["path"])
        print("  kinds: %s" % ", ".join(row.get("kinds") or []))
        print("  weight: %.3f" % row["weight"])
        if row.get("evidence"):
            print("  evidence: %s" % "; ".join(row["evidence"]))


def cmd_rag_stats(args):
    data = stats_for_project(args.project)
    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return
    print("files: %d" % data["files"])
    print("chunks: %d" % data["chunks"])
    print("db: %s (%d bytes)" % (relpath(data["db_path"], REPO_ROOT), data["db_size"]))
    print("fts5: %s" % ("enabled" if data["fts5_enabled"] else "disabled"))
    print("schema: %s" % data["schema_version"])
    print("indexed_at oldest: %s" % data["indexed_at_oldest"])
    print("indexed_at newest: %s" % data["indexed_at_newest"])
    print("edges:")
    for kind, count in sorted(data["edge_counts"].items()):
        print("- %s: %d" % (kind, count))


def cmd_rag_doctor(args):
    data = doctor_for_project(args.project)
    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return
    print("db: %s" % relpath(data["db_path"], REPO_ROOT))
    if data["ok"]:
        print("ok")
        return
    for issue in data["issues"]:
        print("- %s" % issue)
    for path in data.get("stale_paths", []):
        print("  stale: %s" % path)


def add_log_toggle(parser, help_text):
    parser.set_defaults(no_log=False)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--include-log", dest="no_log", action="store_false", help="include log.jsonl")
    group.add_argument("--no-log", dest="no_log", action="store_true", help=help_text)



def add_rag_subparser(subparsers, add_project):
    p = subparsers.add_parser("rag", help="local retrieval index")
    rsub = p.add_subparsers(dest="rag_command", required=True)

    c = rsub.add_parser("rebuild", help="rebuild the local project RAG index")
    add_project(c)
    c.add_argument("--force", action="store_true", help="accepted for compatibility; rebuild already replaces the DB")
    c.add_argument("--json", action="store_true", help="emit machine-readable output")
    add_log_toggle(c, "skip indexing log.jsonl")
    c.set_defaults(func=cmd_rag_rebuild)

    c = rsub.add_parser("update", help="incrementally refresh the local project RAG index")
    add_project(c)
    c.add_argument("--json", action="store_true", help="emit machine-readable output")
    add_log_toggle(c, "skip indexing log.jsonl")
    c.set_defaults(func=cmd_rag_update)

    c = rsub.add_parser("search", help="search the local project RAG index")
    add_project(c)
    c.add_argument("--query", required=True, help="search query")
    c.add_argument("--limit", type=int, help="result limit")
    c.add_argument("--candidate-limit", type=int, help="candidate pool size before reranking")
    c.add_argument("--json", action="store_true", help="emit JSON results")
    c.add_argument("--format", choices=["human", "context"], default="human", help="output format")
    c.add_argument("--no-refresh", action="store_true", help="skip the stale check/update before searching")
    c.add_argument("--paths-only", action="store_true", help="only print unique file paths")
    c.add_argument("--debug", action="store_true", help="include component scores in JSON output")
    add_log_toggle(c, "skip indexing log.jsonl during auto-refresh")
    c.set_defaults(func=cmd_rag_search)

    c = rsub.add_parser("related", help="show related files from the local file graph")
    add_project(c)
    c.add_argument("--path", required=True, help="project-relative file path")
    c.add_argument("--limit", type=int, default=20, help="max related files to return")
    c.add_argument("--json", action="store_true", help="emit JSON results")
    c.set_defaults(func=cmd_rag_related)

    c = rsub.add_parser("stats", help="show index stats")
    add_project(c)
    c.add_argument("--json", action="store_true", help="emit JSON output")
    c.set_defaults(func=cmd_rag_stats)

    c = rsub.add_parser("doctor", help="diagnose index health")
    add_project(c)
    c.add_argument("--json", action="store_true", help="emit JSON output")
    c.set_defaults(func=cmd_rag_doctor)

    return p
