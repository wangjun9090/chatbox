#!/usr/bin/env python3
"""
hymn_lib.py - Hymn search agent (refactored as importable module)
Searches online databases and local files for hymn MP3s
"""

import re
import requests
from pathlib import Path
from typing import List, Optional, Tuple
from bs4 import BeautifulSoup
from urllib.parse import quote_plus, urljoin

from response_schema import AgentResponse, hymn_response, error_response, clarification_response


# =============================================================================
# CONFIGURATION
# =============================================================================

SMALL_CHURCH_SEARCH_URL = "https://www.smallchurchmusic.com/Song_Display-New.php?Search="

ARCHIVE_SOURCES = {
    "Baptist Music": "https://archive.org/details/BaptistMusic",
    "Mighty Fortress": "https://archive.org/details/lp_a-mighty-fortress_mormon-tabernacle-choir-richard-p-condi",
}

LOCAL_HYMNS_DIR = Path("./hymns")

# Priority order for hymn types (lower = better)
PRIORITY = {"choir": 0, "band": 1, "piano": 2, "organ": 3, "instrumental": 4}

KIND_LABEL = {
    "choir": "Choir",
    "band": "Band",
    "piano": "Piano",
    "organ": "Organ",
    "instrumental": "Instrumental",
}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def normalize(text: str) -> str:
    """Normalize text for comparison"""
    return (text or "").strip().lower()


def classify_kind(text: str) -> str:
    """
    Classify hymn type from text description.
    Returns: "choir", "band", "piano", "organ", or "instrumental"
    """
    t = normalize(text)
    
    # Special case: "vocals and band" = choir
    if "vocals and band" in t or "vocals & band" in t:
        return "choir"
    
    # Choir keywords
    choir_kw = ("choir", "vocal", "vocals", "vocalist", "sung", "singing",
                "singers", "chorus", "quartet", "congregation", "worship team",
                "acapella", "a capella")
    if any(k in t for k in choir_kw):
        return "choir"
    
    # Band
    if "band" in t or "small band" in t or "praise team" in t:
        return "band"
    
    # Piano
    if "piano" in t:
        return "piano"
    
    # Organ
    if "organ" in t:
        return "organ"
    
    # Default
    return "instrumental"


def extract_context(a_tag) -> str:
    """Extract surrounding text context from an anchor tag"""
    texts = []
    if a_tag.parent:
        texts.append(a_tag.parent.get_text(" ", strip=True))
    if a_tag.previous_sibling:
        texts.append(str(a_tag.previous_sibling).strip())
    if a_tag.next_sibling:
        texts.append(str(a_tag.next_sibling).strip())
    return " ".join(t for t in texts if t)


def find_mp3_links(soup: BeautifulSoup, base_url: str) -> List[Tuple[str, str, str]]:
    """
    Find all MP3 links in HTML soup.
    Returns: List of (title, url, context) tuples
    """
    results = []
    
    # Method 1: <audio> tags
    for audio in soup.find_all("audio"):
        parent_text = audio.get_text(" ", strip=True)
        for src in audio.find_all("source"):
            href = src.get("src") or src.get("data-src")
            if href and href.lower().endswith(".mp3"):
                full = urljoin(base_url, href)
                title = src.get("title") or Path(href).name
                results.append((title, full, parent_text))
        
        # Check audio src attribute
        href = audio.get("src")
        if href and href.lower().endswith(".mp3"):
            full = urljoin(base_url, href)
            results.append((Path(href).name, full, parent_text))
    
    # Method 2: <a> tags
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.lower().endswith(".mp3"):
            title = a.get_text(" ", strip=True) or Path(href).name
            context = extract_context(a)
            full = urljoin(base_url, href)
            results.append((title, full, context))
    
    # Method 3: Markdown links in text
    text = soup.get_text()
    for title, url in re.findall(r'\[([^\]]+)\]\((https?://[^)]+\.mp3)\)', text, re.I):
        results.append((title, url, title))
    
    # Method 4: Raw URLs
    for url in set(re.findall(r'(https?://[^\s"\'<>]+\.mp3)', text, re.I)):
        results.append((Path(url).name, url, ""))
    
    return results


def prioritize_results(results: List[dict]) -> List[dict]:
    """Sort results by priority (choir > band > piano > organ > instrumental)"""
    return sorted(results, key=lambda x: PRIORITY.get(x["kind"], 9))


def deduplicate(results: List[dict]) -> List[dict]:
    """Remove duplicate URLs"""
    seen = set()
    unique = []
    for r in results:
        if r["url"] not in seen:
            seen.add(r["url"])
            unique.append(r)
    return unique


# =============================================================================
# ONLINE SEARCH FUNCTIONS
# =============================================================================

def search_small_church(query: str) -> List[dict]:
    """
    Search SmallChurchMusic.com for hymns.
    Returns: List of {title, url, kind, source} dicts
    """
    url = SMALL_CHURCH_SEARCH_URL + quote_plus(query)
    print(f"  [Hymn Agent] Searching SmallChurchMusic: {query}")
    
    results = []
    try:
        r = requests.get(url, timeout=12)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        mp3s = find_mp3_links(soup, url)
        
        # Follow detail pages (up to 10)
        detail_links = set()
        for a in soup.find_all("a", href=re.compile(r"Song_Display|Songs?\.php", re.I)):
            detail_links.add(urljoin(url, a["href"]))
        
        for link in list(detail_links)[:10]:
            try:
                r2 = requests.get(link, timeout=10)
                r2.raise_for_status()
                mp3s.extend(find_mp3_links(BeautifulSoup(r2.text, "html.parser"), link))
            except:
                continue
        
        # Convert to standard format
        for title, href, context in mp3s:
            kind = classify_kind(f"{title} {context}")
            results.append({
                "title": title,
                "url": href,
                "kind": kind,
                "source": "SmallChurchMusic"
            })
    
    except Exception as e:
        print(f"  [Hymn Agent] SmallChurchMusic error: {e}")
    
    results = deduplicate(results)
    print(f"  [Hymn Agent] → {len(results)} results from SmallChurchMusic")
    return results


def search_archive(query: str) -> List[dict]:
    """
    Search Archive.org collections for hymns.
    Returns: List of {title, url, kind, source} dicts
    """
    q = query.lower()
    results = []
    print(f"  [Hymn Agent] Searching Archive.org...")
    
    for name, base_url in ARCHIVE_SOURCES.items():
        try:
            r = requests.get(base_url, timeout=12)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            
            for title, href, ctx in find_mp3_links(soup, base_url):
                # Filter by query relevance
                if q not in title.lower() and q not in href.lower():
                    continue
                
                kind = classify_kind(f"{title} {ctx}")
                results.append({
                    "title": title,
                    "url": href,
                    "kind": kind,
                    "source": f"Archive:{name}"
                })
        
        except Exception as e:
            print(f"  [Hymn Agent] Archive {name} error: {e}")
    
    results = deduplicate(results)
    print(f"  [Hymn Agent] → {len(results)} results from Archive.org")
    return results


# =============================================================================
# LOCAL SEARCH FUNCTION
# =============================================================================

def fuzzy_score(query: str, text: str) -> float:
    """
    Calculate fuzzy match score between query and text.
    Returns: 0.0-1.0 (higher = better match)
    """
    q = query.lower()
    t = re.sub(r'[^a-z0-9]', '', text.lower())
    q_clean = re.sub(r'[^a-z0-9]', '', q)
    
    if not q_clean or not t:
        return 0.0
    
    # Exact substring match = very high score
    if q_clean in t:
        bonus = 0.05 if query.lower() in text.lower() else 0
        return 0.95 + bonus
    
    # Word-by-word overlap
    q_words = set(q.split())
    t_words = set(text.lower().split())
    overlap = len(q_words & t_words)
    if overlap > 0:
        return 0.3 + (overlap / max(len(q_words), len(t_words))) * 0.6
    
    return 0.0


def search_local_hymns(query: str) -> List[dict]:
    """
    Search local ./hymns/ folder for MP3 files.
    Returns: List of {title, url, kind, source, score, path} dicts
    """
    if not LOCAL_HYMNS_DIR.exists() or not LOCAL_HYMNS_DIR.is_dir():
        print(f"  [Hymn Agent] Local folder not found: {LOCAL_HYMNS_DIR}")
        return []
    
    print(f"  [Hymn Agent] Searching local hymns folder...")
    candidates = []
    
    for file_path in LOCAL_HYMNS_DIR.rglob("*.mp3"):
        stem = file_path.stem
        filename = file_path.name
        
        score = fuzzy_score(query, stem)
        if score < 0.35:  # Threshold
            continue
        
        kind = classify_kind(filename)
        candidates.append({
            "title": filename,
            "url": str(file_path.absolute()),
            "kind": kind,
            "source": "Local File",
            "score": score,
            "path": file_path
        })
    
    if not candidates:
        print(f"  [Hymn Agent] No local matches found")
        return []
    
    # Sort by score then priority
    candidates.sort(key=lambda x: (-x["score"], PRIORITY.get(x["kind"], 9)))
    print(f"  [Hymn Agent] → {len(candidates)} local file(s), best score: {candidates[0]['score']:.3f}")
    return candidates[:10]


# =============================================================================
# MAIN SEARCH FUNCTION (PUBLIC API)
# =============================================================================

def search_hymn(query: str, prefer_kind: Optional[str] = None) -> AgentResponse:
    """
    Search for a hymn across all sources (online + local).
    
    Args:
        query: Hymn title or search term
        prefer_kind: Optional preference ("choir", "piano", etc.)
    
    Returns:
        AgentResponse with playback URL and metadata
    """
    print(f"\n[Hymn Agent] Searching for: '{query}'")
    
    if not query or not query.strip():
        return error_response("Please provide a hymn title.", error_code="EMPTY_QUERY")
    
    # Step 1: Search online sources
    scm_results = search_small_church(query)
    
    # If SmallChurchMusic has good results, use only those
    if any(x["kind"] in ("choir", "band", "piano", "organ") for x in scm_results):
        all_results = prioritize_results(scm_results)
    else:
        # Otherwise, also check Archive.org
        arc_results = search_archive(query)
        all_results = prioritize_results(scm_results + arc_results)
    
    # Step 2: If no online results, search local
    if not all_results:
        print("  [Hymn Agent] No online results → checking local files...")
        local_results = search_local_hymns(query)
        if local_results:
            all_results = local_results
        else:
            return error_response(
                f"I couldn't find '{query}'. Try rephrasing or check the hymn title.",
                error_code="HYMN_NOT_FOUND"
            )
    
    # Step 3: Apply preference filter if specified
    if prefer_kind:
        preferred = [r for r in all_results if r["kind"] == prefer_kind]
        if preferred:
            all_results = preferred + [r for r in all_results if r["kind"] != prefer_kind]
    
    # Step 4: Get top 5 results
    top_results = all_results[:5]
    
    # Step 5: Return best match
    best = top_results[0]
    
    # Calculate confidence based on source and position
    confidence = 0.9 if best["source"] != "Local File" else 0.95
    if "score" in best and best["score"] < 0.7:
        confidence *= 0.8
    
    # Prepare alternatives for clarification if needed
    alternatives = []
    if len(top_results) > 1:
        alternatives = [
            {
                "title": r["title"],
                "url": r["url"],
                "kind": r["kind"],
                "source": r["source"]
            }
            for r in top_results[1:]
        ]
    
    print(f"  [Hymn Agent] ✓ Best match: {best['title']} ({best['kind']})")
    print(f"  [Hymn Agent] Confidence: {confidence:.2f}")
    
    return hymn_response(
        url=best["url"],
        title=best["title"],
        kind=best["kind"],
        source=best["source"],
        confidence=confidence,
        alternatives=alternatives
    )


# =============================================================================
# EXAMPLE USAGE
# =============================================================================

if __name__ == "__main__":
    import sys
    
    # Test the search function
    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "Amazing Grace"
    
    response = search_hymn(query)
    
    print("\n" + "="*70)
    print("RESULT:")
    print("="*70)
    print(f"Success: {response.success}")
    print(f"Type: {response.type.value}")
    print(f"Content: {response.content}")
    print(f"URL: {response.url}")
    print(f"Confidence: {response.confidence:.2f}")
    print(f"Action: {response.action.value}")
    
    if response.metadata:
        print(f"\nMetadata:")
        print(f"  Title: {response.metadata.title}")
        print(f"  Kind: {response.metadata.kind}")
        print(f"  Source: {response.metadata.source}")
    
    if response.alternatives:
        print(f"\nAlternatives: {len(response.alternatives)}")
        for i, alt in enumerate(response.alternatives[:3], 1):
            print(f"  {i}. {alt['title']} ({alt['kind']})")
