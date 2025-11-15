#!/usr/bin/env python3
"""
sermon_lib.py - Sermon search agent (refactored as importable module)
Searches SermonAudio and other sources for sermon MP3s
"""

import re
import requests
from typing import Optional, Dict, List
from urllib.parse import quote_plus, urljoin
from bs4 import BeautifulSoup
from datetime import datetime

from response_schema import AgentResponse, sermon_response, error_response


# =============================================================================
# CONFIGURATION
# =============================================================================

SERMONAUDIO_SEARCH_URL = "https://www.sermonaudio.com/search.asp?keyword="
SERMONAUDIO_BASE = "https://www.sermonaudio.com"

# Headers to handle CloudFront signed URLs properly
REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://www.sermonaudio.com/",
    "Accept": "audio/mp3,audio/*;q=0.9,*/*;q=0.8",
    "Accept-Encoding": "identity",
}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def extract_sermon_metadata(soup: BeautifulSoup, url: str) -> Dict[str, Optional[str]]:
    """
    Extract sermon metadata from SermonAudio detail page.
    Returns: {title, speaker, date, topic, mp3_url}
    """
    metadata = {
        "title": None,
        "speaker": None,
        "date": None,
        "topic": None,
        "mp3_url": None
    }
    
    # Title - usually in <h1> or <title>
    title_tag = soup.find("h1", class_=re.compile(r"title|sermon", re.I))
    if not title_tag:
        title_tag = soup.find("title")
    if title_tag:
        metadata["title"] = title_tag.get_text(strip=True)
    
    # Speaker - look for "preacher", "pastor", "speaker" labels
    for label in ["preacher", "pastor", "speaker", "by"]:
        speaker_elem = soup.find(text=re.compile(label, re.I))
        if speaker_elem and speaker_elem.parent:
            # Get next sibling or link
            next_elem = speaker_elem.parent.find_next()
            if next_elem:
                metadata["speaker"] = next_elem.get_text(strip=True)
                break
    
    # Date - look for date patterns
    date_pattern = r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4}\b'
    date_match = re.search(date_pattern, soup.get_text(), re.I)
    if date_match:
        metadata["date"] = date_match.group(0)
    
    # MP3 URL - look for .mp3 links
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if ".mp3" in href.lower():
            # Could be relative or absolute
            if href.startswith("http"):
                metadata["mp3_url"] = href
            else:
                metadata["mp3_url"] = urljoin(url, href)
            break
    
    # Also check <audio> tags
    if not metadata["mp3_url"]:
        audio_tag = soup.find("audio")
        if audio_tag:
            src = audio_tag.get("src")
            if not src:
                source_tag = audio_tag.find("source")
                if source_tag:
                    src = source_tag.get("src")
            if src:
                metadata["mp3_url"] = urljoin(url, src) if not src.startswith("http") else src
    
    return metadata


def validate_mp3_url(url: str) -> bool:
    """
    Validate that URL points to a playable MP3.
    Uses HEAD request to check headers without downloading.
    """
    try:
        session = requests.Session()
        session.headers.update(REQUEST_HEADERS)
        
        # Try HEAD request first (faster)
        resp = session.head(url, timeout=10, allow_redirects=True)
        if resp.status_code in (200, 206):
            content_type = resp.headers.get("Content-Type", "").lower()
            if "audio" in content_type or "octet-stream" in content_type:
                return True
        
        # Fallback: Try range request (for CloudFront signed URLs)
        resp = session.get(
            url,
            headers={"Range": "bytes=0-1023"},
            stream=True,
            timeout=10
        )
        if resp.status_code in (200, 206):
            content_type = resp.headers.get("Content-Type", "").lower()
            return "audio" in content_type or "octet-stream" in content_type
        
        return False
    
    except Exception as e:
        print(f"  [Sermon Agent] URL validation error: {e}")
        return False


# =============================================================================
# SEARCH FUNCTIONS
# =============================================================================

def search_sermonaudio(query: str, max_results: int = 5) -> List[Dict]:
    """
    Search SermonAudio.com for sermons.
    Returns: List of {title, speaker, date, topic, mp3_url} dicts
    """
    search_url = SERMONAUDIO_SEARCH_URL + quote_plus(query)
    print(f"  [Sermon Agent] Searching SermonAudio: {query}")
    
    results = []
    
    try:
        session = requests.Session()
        session.headers.update(REQUEST_HEADERS)
        
        # Get search results page
        resp = session.get(search_url, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        
        # Find sermon links (pattern varies, look for sermon detail pages)
        sermon_links = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            # SermonAudio detail pages typically contain "sermoninfo" or similar
            if "sermon" in href.lower() and "sermoninfo" in href.lower():
                full_url = urljoin(SERMONAUDIO_BASE, href)
                if full_url not in sermon_links:
                    sermon_links.append(full_url)
        
        # If no specific sermon links, look for any links with sermon-related text
        if not sermon_links:
            for a in soup.find_all("a", href=True):
                text = a.get_text(strip=True).lower()
                if any(kw in text for kw in ["sermon", "preaching", "message"]):
                    href = a["href"]
                    if href.startswith("/"):
                        full_url = urljoin(SERMONAUDIO_BASE, href)
                        if full_url not in sermon_links:
                            sermon_links.append(full_url)
        
        print(f"  [Sermon Agent] Found {len(sermon_links)} potential sermon pages")
        
        # Extract metadata from each sermon page (limit to max_results)
        for link in sermon_links[:max_results * 2]:  # Check extra in case some fail
            try:
                resp2 = session.get(link, timeout=12)
                resp2.raise_for_status()
                sermon_soup = BeautifulSoup(resp2.text, "html.parser")
                
                metadata = extract_sermon_metadata(sermon_soup, link)
                
                # Only include if we got an MP3 URL
                if metadata["mp3_url"]:
                    # Validate URL (optional but recommended)
                    if validate_mp3_url(metadata["mp3_url"]):
                        results.append(metadata)
                        print(f"  [Sermon Agent] ✓ Found: {metadata.get('title', 'Untitled')}")
                    else:
                        print(f"  [Sermon Agent] ✗ Invalid MP3 URL: {metadata['mp3_url'][:50]}...")
                
                if len(results) >= max_results:
                    break
            
            except Exception as e:
                print(f"  [Sermon Agent] Error processing {link}: {e}")
                continue
    
    except Exception as e:
        print(f"  [Sermon Agent] SermonAudio search error: {e}")
    
    print(f"  [Sermon Agent] → {len(results)} valid sermons found")
    return results


# =============================================================================
# MAIN SEARCH FUNCTION (PUBLIC API)
# =============================================================================

def search_sermon(
    query: str,
    filters: Optional[Dict[str, str]] = None
) -> AgentResponse:
    """
    Search for a sermon across available sources.
    
    Args:
        query: Search term (topic, speaker name, etc.)
        filters: Optional filters like {"speaker": "John Piper", "topic": "grace"}
    
    Returns:
        AgentResponse with playback URL and metadata
    """
    print(f"\n[Sermon Agent] Searching for: '{query}'")
    
    if not query or not query.strip():
        return error_response("Please provide a sermon topic or speaker.", error_code="EMPTY_QUERY")
    
    # Apply filters to query if provided
    search_query = query
    if filters:
        if "speaker" in filters:
            search_query += f" {filters['speaker']}"
        if "topic" in filters:
            search_query += f" {filters['topic']}"
    
    # Search SermonAudio
    results = search_sermonaudio(search_query, max_results=5)
    
    if not results:
        return error_response(
            f"I couldn't find any sermons about '{query}'. Try a different topic or speaker.",
            error_code="SERMON_NOT_FOUND"
        )
    
    # Get best match
    best = results[0]
    
    # Clean up title (remove site name suffixes)
    title = best.get("title", "Untitled Sermon")
    title = re.sub(r'\s*[-|]\s*SermonAudio.*$', '', title, flags=re.I)
    
    # Calculate confidence
    confidence = 0.85  # Default for first search result
    if best.get("speaker") and query.lower() in best["speaker"].lower():
        confidence = 0.95  # Higher if speaker matches query
    
    print(f"  [Sermon Agent] ✓ Best match: {title}")
    print(f"  [Sermon Agent] Speaker: {best.get('speaker', 'Unknown')}")
    print(f"  [Sermon Agent] Confidence: {confidence:.2f}")
    
    return sermon_response(
        url=best["mp3_url"],
        title=title,
        speaker=best.get("speaker"),
        date=best.get("date"),
        topic=best.get("topic"),
        confidence=confidence
    )


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def search_sermon_by_speaker(speaker: str) -> AgentResponse:
    """Search for sermons by a specific speaker"""
    return search_sermon(f"sermons by {speaker}", filters={"speaker": speaker})


def search_sermon_by_topic(topic: str) -> AgentResponse:
    """Search for sermons on a specific topic"""
    return search_sermon(f"sermon on {topic}", filters={"topic": topic})


# =============================================================================
# EXAMPLE USAGE
# =============================================================================

if __name__ == "__main__":
    import sys
    
    # Test the search function
    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "forgiveness"
    
    response = search_sermon(query)
    
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
        print(f"  Speaker: {response.metadata.speaker}")
        print(f"  Date: {response.metadata.date}")
        print(f"  Source: {response.metadata.source}")
    
    print("\n" + "="*70)
