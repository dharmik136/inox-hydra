"""
Search and Documentation API Router
====================================
Sub-millisecond FTS5 offline markdown documentation search and universal search across posts,
leads, specimens, and help playbooks. Zero cloud egress.
"""

import os
import re
from typing import Dict, Any
from fastapi import APIRouter, HTTPException

try:
    from ..paths import get_docs_dir, get_modules_docs_dir
    from ..docs_engine import (
        document_library,
        document_slug,
        section_meta,
        section_kind,
        help_sections,
        search_docs_fts,
        section_hidden,
        hidden_document_paths,
        internal_documents_shown
    )
    from .. import universal_search
    from .. import hook_forms
except (ImportError, ValueError):
    from paths import get_docs_dir, get_modules_docs_dir
    from docs_engine import (
        document_library,
        document_slug,
        section_meta,
        section_kind,
        help_sections,
        search_docs_fts,
        section_hidden,
        hidden_document_paths,
        internal_documents_shown
    )
    import universal_search
    import hook_forms

router = APIRouter()

DOCS_DIR = get_docs_dir()
MODULES_DIR = get_modules_docs_dir()

DOCS_MODULES = [
    {
        "id": "studio-editor",
        "number": "01",
        "title": "Studio & Editor",
        "category": "Core Authoring",
        "icon": "edit",
        "file": "01_STUDIO_AND_EDITOR.md",
        "summary": "Universal top bar telemetry, dynamic glowing fold tracker, 1080×1080 PDF carousel deck, and 6-dimension algorithmic safety audit."
    },
    {
        "id": "schedule-queue",
        "number": "02",
        "title": "Schedule & Queue",
        "category": "Cadence & Timing",
        "icon": "calendar",
        "file": "02_SCHEDULE_AND_QUEUE.md",
        "summary": "Publishing cadence rules, peak smart engagement slots (8:30 AM & 5:30 PM), and local background scheduler daemon."
    },
    {
        "id": "inbound-crm",
        "number": "03",
        "title": "Inbound CRM",
        "category": "Pipeline & Outreach",
        "icon": "users",
        "file": "03_INBOUND_CRM.md",
        "summary": "Relationship pipeline stages, column dictionary, search/filtering, and 3-style contextual DM generator with zero em-dash compliance."
    },
    {
        "id": "viral-swipe-file",
        "number": "04",
        "title": "Viral Swipe File",
        "category": "Research & Blueprints",
        "icon": "zap",
        "file": "04_VIRAL_SWIPE_FILE.md",
        "summary": "356 vaulted blueprints, 13 topic taxonomies, instant search, and Agno Framework autonomous inbound roadmap."
    },
    {
        "id": "analytics",
        "number": "05",
        "title": "Creator Analytics",
        "category": "Performance Telemetry",
        "icon": "bar-chart",
        "file": "05_ANALYTICS.md",
        "summary": "Direct LinkedIn session ingestion (li_at & JSESSIONID), multi-range growth deltas, Chart.js vector curves, and demographics."
    },
    {
        "id": "ai-command",
        "number": "06",
        "title": "AI Command Hub",
        "category": "Dual-Mode Intelligence",
        "icon": "sparkles",
        "file": "06_AI_COMMAND.md",
        "summary": "Dual-mode Gemini 2.5 Flash cloud API + Antigravity local deterministic engine, prompt presets, and direct Studio transfer."
    },
    {
        "id": "enterprise-usage",
        "number": "Master",
        "title": "Enterprise Usage Manual",
        "category": "Master Architecture",
        "icon": "book",
        "file": "ENTERPRISE_USAGE.md",
        "summary": "Master operational reference manual covering all platform capabilities, security, and algorithms."
    }
]


def _docs_catalogue():
    """
    Every openable document, keyed by the one id that opens it.

    Two vocabularies name these files. Seven have a curated id, a title and a
    category written by hand in DOCS_MODULES; all 38 that the search index
    covers have a path derived slug from docs_engine. The curated id wins where
    both exist, so a file has exactly one id and a search hit and a sidebar
    click land on the same document.

    Every value in here was produced by walking the docs directory. A request
    supplies an id, which selects a row; it never contributes a path segment.
    """
    catalogue = {}
    by_path = {}

    library = document_library(DOCS_DIR)
    for entry in library:
        catalogue[entry["id"]] = {
            "id": entry["id"],
            "path": entry["path"],
            "title": entry["title"],
            "category": entry["folder"],
            "words": entry["words"],
            "excerpt": entry["excerpt"],
            "section": entry["section"],
            "module_id": None,
        }
        by_path[entry["path"]] = entry["id"]

    for module in DOCS_MODULES:
        for candidate in ("modules/" + module["file"], module["file"]):
            if candidate not in by_path:
                continue
            slug = by_path[candidate]
            record = dict(catalogue[slug])
            record.update({
                "id": module["id"],
                "title": module["title"],
                "category": module["category"],
                "module_id": module["id"],
            })
            catalogue[module["id"]] = record
            catalogue[slug] = record
            by_path[candidate] = module["id"]
            break

    return catalogue, by_path


@router.get("/api/docs", tags=["Documentation"])
def list_docs_modules(internal: bool = False):
    """
    The documentation suite: the seven curated modules, and the whole library.

    The index has always covered every markdown file under the docs directory
    and this endpoint reported seven of them, so four fifths of what the search
    could match had no route and the interface could not offer the hit it had
    just rendered. "library" closes that: one entry per indexed file, carrying
    the id that opens it and the curated module id when it has one.

    A creator is listed the help articles only. The maintainer and retired
    documents are listed in dev mode, or when asked for with ?internal=1;
    either way each still opens by its id. The seven curated modules are all
    retired manuals, so they are listed on the same terms.
    """
    shown = internal or internal_documents_shown()
    catalogue, by_path = _docs_catalogue()
    library = []
    for path in sorted(by_path):
        record = catalogue[by_path[path]]
        if section_hidden(record["section"], shown):
            continue
        library.append({
            "id": record["id"],
            "path": record["path"],
            "title": record["title"],
            "category": record["category"],
            "words": record["words"],
            "excerpt": record["excerpt"],
            "section": record["section"],
            "module_id": record["module_id"],
        })

    sections = []
    for section in help_sections(DOCS_DIR):
        if section_hidden(section["id"], shown):
            continue
        sections.append({
            "id": section["id"],
            "title": section["title"],
            "blurb": section["blurb"],
            "kind": section["kind"],
            "hidden": False,
            "count": section["count"],
            "words": section["words"],
            "document_ids": [catalogue[by_path[entry["path"]]]["id"] for entry in section["documents"]],
        })

    modules = [module for module in DOCS_MODULES
               if module["id"] in catalogue and not section_hidden(catalogue[module["id"]]["section"], shown)]
    return {
        "status": "success",
        "count": len(modules),
        "modules": modules,
        "library": library,
        "library_count": len(library),
        "sections": sections
    }


@router.get("/api/docs/search", tags=["Documentation"])
def search_documentation(q: str, limit: int = 10, internal: bool = False):
    """
    Sub-millisecond full-text search across all offline Markdown playbooks using SQLite FTS5 (Day 09).
    """
    safe_q = str(q or "")[:300].strip()
    try:
        safe_limit = max(1, min(int(limit), 100))
    except (TypeError, ValueError):
        safe_limit = 10

    # Maintainer and retired documents are not answers for a creator; see
    # docs_engine.section_hidden. Left out in the query, and any hit from a
    # hidden section that is not in the written table is dropped below.
    shown = internal or internal_documents_shown()
    results = search_docs_fts(safe_q, limit=min(100, max(safe_limit * 4, 40)),
                              skip_files=hidden_document_paths(shown))

    catalogue, by_path = _docs_catalogue()
    kept = []
    for hit in results:
        filename = str(hit.get("filename") or "").replace("\\", "/")
        hit["filename"] = filename
        hit["document_id"] = by_path.get(filename) or document_slug(filename)
        record = catalogue.get(hit["document_id"])
        hit["document_title"] = record["title"] if record else filename
        hit["help_section"] = section_meta(record["section"])["title"] if record else ""
        hit["kind"] = section_kind(record["section"]) if record else "help"
        if not (record and section_hidden(record["section"], shown)):
            kept.append(hit)
    results = kept

    rank = {"help": 0, "reference": 1, "retired": 2}
    how = {"word": 0, "prefix": 1}
    results = sorted(
        results, key=lambda hit: (how.get(hit.get("match"), 0), rank.get(hit.get("kind"), 0))
    )[:safe_limit]

    return {
        "status": "success",
        "query": safe_q,
        "count": len(results),
        "results": results
    }


@router.get("/api/v1/search", tags=["Search"])
def search_everything(q: str = "", limit: int = 6):
    """
    One query across posts, leads, Swipe File specimens and the help.
    """
    terms = universal_search.terms_of(q)
    try:
        per_group = max(1, min(int(limit), 20))
    except (TypeError, ValueError):
        per_group = 6

    groups = {"posts": [], "leads": [], "specimens": [], "help": []}
    if not terms:
        return {"status": "success", "query": "", "terms": [], "groups": groups, "total": 0}

    failures = {}
    try:
        groups["posts"] = universal_search.search_posts(terms, limit=per_group)
    except Exception as exc:
        failures["posts"] = str(exc)[:200]
    try:
        groups["leads"] = universal_search.search_leads(terms, limit=per_group)
    except Exception as exc:
        failures["leads"] = str(exc)[:200]

    try:
        found = []
        for template in hook_forms.get_templates(limit=500):
            hook = template.get("hook_text") or ""
            haystack = universal_search.fold(" ".join(str(template.get(key) or "") for key in
                                                      ("hook_text", "archetype", "pacing_style")))
            if all(universal_search.fold(term) in haystack for term in terms):
                found.append({
                    "kind": "specimen",
                    "id": f"tpl-{template.get('id')}",
                    "title": universal_search.snippet_around(hook, terms, radius=45) or "Untitled specimen",
                    "snippet": template.get("pacing_style") or "",
                    "meta": str(template.get("archetype") or "").upper(),
                    # The hook rail is where a form is applied, and the
                    # Swipe File that used to draw the same rows is gone.
                    "opens": "composer",
                })
            if len(found) >= per_group:
                break
        groups["specimens"] = found
    except Exception as exc:
        failures["specimens"] = str(exc)[:200]

    try:
        docs = search_documentation(" ".join(terms), limit=per_group)
        groups["help"] = [{
            "kind": "help",
            "id": hit.get("document_id") or "",
            "title": hit.get("section") or hit.get("document_title") or "",
            "snippet": hit.get("snippet") or "",
            "meta": hit.get("help_section") or "",
            "document_title": hit.get("document_title") or "",
            "anchor_text": hit.get("section") or "",
            "retired": hit.get("kind") == "retired",
            "opens": "docs",
        } for hit in docs.get("results", [])]
    except Exception as exc:
        failures["help"] = str(exc)[:200]

    return {
        "status": "success",
        "query": " ".join(terms),
        "terms": terms,
        "groups": groups,
        "total": sum(len(items) for items in groups.values()),
        "failures": failures,
    }


@router.get("/api/docs/{module_id}", tags=["Documentation"])
def get_doc_module(module_id: str):
    """
    Retrieves the full markdown content of a documentation module by ID or number.
    """
    safe_id = re.sub(r"[^a-zA-Z0-9_-]", "", str(module_id or ""))[:120]
    if not safe_id:
        raise HTTPException(status_code=400, detail="Invalid documentation module ID.")

    catalogue, _ = _docs_catalogue()
    record = catalogue.get(safe_id) or catalogue.get(safe_id.lower())

    if record is None:
        for module in DOCS_MODULES:
            if module["number"] == safe_id:
                record = catalogue.get(module["id"])
                break

    if record is None:
        raise HTTPException(status_code=404, detail=f"Documentation module '{safe_id}' not found.")

    file_path = os.path.join(DOCS_DIR, *record["path"].split("/"))
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"Documentation file for '{safe_id}' not found on disk.")

    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    target = None
    if record["module_id"]:
        for module in DOCS_MODULES:
            if module["id"] == record["module_id"]:
                target = module
                break

    return {
        "status": "success",
        "module": target,
        "id": record["id"],
        "title": record["title"],
        "path": record["path"],
        "category": record["category"],
        "section": section_meta(record["section"])["title"],
        "retired": section_kind(record["section"]) == "retired",
        "words": record["words"],
        "content": content
    }
