"""
Web Tools for AI Agent

Real web search and content fetching tools.
Supports: Tavily (primary), DuckDuckGo (fallback), Jina Reader, Wikipedia.
"""

import os
import asyncio
import aiohttp
from typing import Dict, Any, Optional, List
from urllib.parse import urlparse, quote
from langchain_core.tools import tool
import re

from ..logger import agent_logger


# ==================== WEB SEARCH TOOLS ====================

@tool
def tavily_search(query: str, max_results: int = 5) -> str:
    """
    Search the internet using Tavily API to find relevant information.
    
    This is the PRIMARY web search tool. Returns top results with URLs,
    titles, and content snippets. Use fetch_url_content or jina_reader
    to get full content from the URLs.
    
    Args:
        query: The search query string
        max_results: Number of results to return (default: 5, max: 10)
        
    Returns:
        str: Search results with titles, URLs, and snippets
    """
    agent_logger.info(f"🔍 Tool: tavily_search({query[:50]}...)")
    
    try:
        from tavily import TavilyClient
    except ImportError:
        return "Error: tavily package not installed. Run: pip install tavily-python"
    
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        agent_logger.warning("⚠️ TAVILY_API_KEY not set, falling back to DuckDuckGo")
        return duckduckgo_search.invoke({"query": query, "max_results": max_results})
    
    try:
        client = TavilyClient(api_key=api_key)
        response = client.search(query=query, max_results=min(max_results, 10))
        
        results = response.get("results", [])
        
        if not results:
            return f"No results found for: {query}"
        
        # Sort by score and format
        sorted_results = sorted(results, key=lambda x: x.get('score', 0), reverse=True)
        
        formatted = [f"=== Tavily Search Results for: {query} ===\n"]
        for i, res in enumerate(sorted_results[:max_results], 1):
            formatted.append(
                f"{i}. {res.get('title', 'No title')}\n"
                f"   URL: {res.get('url', 'N/A')}\n"
                f"   Snippet: {res.get('content', 'N/A')[:200]}...\n"
            )
        
        formatted.append("\nUse jina_reader or fetch_url_content to read full content from these URLs.")
        
        result = "\n".join(formatted)
        agent_logger.info(f"✅ Tavily returned {len(results)} results")
        return result
        
    except Exception as e:
        agent_logger.error(f"❌ Tavily search error: {e}")
        # Fallback to DuckDuckGo
        agent_logger.info("🔄 Falling back to DuckDuckGo...")
        return duckduckgo_search.invoke({"query": query, "max_results": max_results})


@tool
def duckduckgo_search(query: str, max_results: int = 5) -> str:
    """
    Search the web using DuckDuckGo (free, no API key required).
    
    Use this as a fallback when Tavily is not available, or for
    general web searches. Returns titles, URLs, and snippets.
    
    Args:
        query: Search query string
        max_results: Number of results (default: 5)
        
    Returns:
        str: Search results with titles, URLs, and snippets
    """
    agent_logger.info(f"🦆 Tool: duckduckgo_search({query[:50]}...)")
    
    try:
        from langchain_community.tools import DuckDuckGoSearchResults
        from langchain_community.utilities import DuckDuckGoSearchAPIWrapper
    except ImportError:
        return "Error: langchain-community not installed. Run: pip install langchain-community"
    
    try:
        wrapper = DuckDuckGoSearchAPIWrapper(max_results=max_results)
        search = DuckDuckGoSearchResults(api_wrapper=wrapper, output_format="list")
        
        results = search.invoke(query)
        
        if not results:
            return f"No results found for: {query}"
        
        # Format results
        formatted = [f"=== DuckDuckGo Search Results for: {query} ===\n"]
        
        for i, result in enumerate(results[:max_results], 1):
            if isinstance(result, dict):
                formatted.append(
                    f"{i}. {result.get('title', 'N/A')}\n"
                    f"   URL: {result.get('link', 'N/A')}\n"
                    f"   Snippet: {result.get('snippet', 'N/A')[:200]}...\n"
                )
            else:
                formatted.append(f"{i}. {str(result)[:300]}\n")
        
        formatted.append("\nUse jina_reader or fetch_url_content to read full content from these URLs.")
        
        result = "\n".join(formatted)
        agent_logger.info(f"✅ DuckDuckGo returned {len(results)} results")
        return result
        
    except Exception as e:
        agent_logger.error(f"❌ DuckDuckGo search error: {e}")
        return f"DuckDuckGo search failed: {str(e)}"


# ==================== URL CONTENT TOOLS ====================

@tool
async def jina_reader(url: str) -> str:
    """
    Fetch and parse web page content using Jina Reader API.
    
    Jina Reader extracts clean, readable text from web pages,
    removing ads, navigation, and other clutter. Perfect for
    reading articles, documentation, and blog posts.
    
    Args:
        url: The web page URL to read
        
    Returns:
        str: Clean, readable content from the page
    """
    agent_logger.info(f"📖 Tool: jina_reader({url})")
    
    # Jina Reader API - prepend r.jina.ai to any URL
    jina_url = f"https://r.jina.ai/{url}"
    
    try:
        timeout = aiohttp.ClientTimeout(total=30)
        headers = {
            'User-Agent': 'QUASAR-CLI/1.0',
            'Accept': 'text/plain'
        }
        
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            async with session.get(jina_url) as response:
                if response.status != 200:
                    return f"Error: Jina Reader returned HTTP {response.status}"
                
                content = await response.text()
                
                # Truncate if too long
                max_chars = 8000
                if len(content) > max_chars:
                    content = content[:max_chars] + "\n\n[Content truncated at 8000 characters]"
                
                agent_logger.info(f"✅ Jina Reader fetched {len(content)} chars")
                return f"=== Content from {url} ===\n\n{content}"
                
    except asyncio.TimeoutError:
        return f"Error: Request timed out (30 seconds)"
    except Exception as e:
        agent_logger.error(f"❌ Jina Reader error: {e}")
        return f"Jina Reader failed: {str(e)}"


@tool
async def fetch_url_content(url: str, max_chars: int = 8000) -> str:
    """
    Fetch and parse content from a web page URL.
    
    Basic URL fetcher with HTML cleaning. Use jina_reader for
    better results on complex pages. This is a fallback option.
    
    Args:
        url: URL to fetch content from
        max_chars: Maximum characters to return (default: 8000)
        
    Returns:
        str: Extracted text content from the page
    """
    agent_logger.info(f"🔗 Tool: fetch_url_content({url})")
    
    try:
        # Validate URL
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return "Error: Invalid URL format"
        
        timeout = aiohttp.ClientTimeout(total=15)
        headers = {
            'User-Agent': 'QUASAR-CLI/1.0 (AI Assistant)'
        }
        
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            async with session.get(url) as response:
                if response.status != 200:
                    return f"Error: HTTP {response.status} - {response.reason}"
                
                content = await response.text()
                
                # Basic HTML cleaning
                if 'text/html' in response.headers.get('content-type', ''):
                    # Remove script and style tags
                    content = re.sub(r'<script[^>]*>.*?</script>', '', content, flags=re.DOTALL | re.IGNORECASE)
                    content = re.sub(r'<style[^>]*>.*?</style>', '', content, flags=re.DOTALL | re.IGNORECASE)
                    # Remove HTML tags
                    content = re.sub(r'<[^>]+>', ' ', content)
                    # Clean up whitespace
                    content = re.sub(r'\s+', ' ', content).strip()
                
                # Truncate if too long
                if len(content) > max_chars:
                    content = content[:max_chars] + "\n\n[Content truncated...]"
                
                agent_logger.info(f"✅ Fetched {len(content)} chars from {url}")
                return f"=== Content from {url} ===\n\n{content}"
                
    except asyncio.TimeoutError:
        return "Error: Request timed out (15 seconds)"
    except Exception as e:
        agent_logger.error(f"❌ Fetch URL error: {e}")
        return f"Failed to fetch URL: {str(e)}"


# ==================== KNOWLEDGE BASE TOOLS ====================

@tool
def wikipedia_search(query: str, max_docs: int = 2) -> str:
    """
    Search Wikipedia for comprehensive, reliable general knowledge.
    
    Best for: Definitions, concepts, historical facts, biographies,
    scientific explanations, and general information.
    
    Args:
        query: Topic or concept to search for
        max_docs: Number of articles to return (default: 2)
        
    Returns:
        str: Wikipedia article content with sources
    """
    agent_logger.info(f"📚 Tool: wikipedia_search({query})")
    
    try:
        from langchain_community.document_loaders import WikipediaLoader
    except ImportError:
        return "Error: langchain-community or wikipedia not installed"
    
    try:
        loader = WikipediaLoader(
            query=query,
            load_max_docs=max_docs,
            doc_content_chars_max=4000
        )
        
        docs = loader.load()
        
        if not docs:
            return f"No Wikipedia articles found for: {query}"
        
        # Format results
        formatted = [f"=== Wikipedia: {query} ===\n"]
        
        for i, doc in enumerate(docs, 1):
            title = doc.metadata.get('title', 'Unknown')
            source = doc.metadata.get('source', 'N/A')
            formatted.append(f"\n--- Article {i}: {title} ---")
            formatted.append(f"Source: {source}")
            formatted.append(f"\n{doc.page_content}\n")
        
        result = "\n".join(formatted)
        agent_logger.info(f"✅ Wikipedia returned {len(docs)} articles")
        return result
        
    except Exception as e:
        agent_logger.error(f"❌ Wikipedia search error: {e}")
        return f"Wikipedia search failed: {str(e)}"


@tool  
def arxiv_search(query: str, max_papers: int = 3) -> str:
    """
    Search arXiv for academic research papers and scientific publications.
    
    Best for: Latest research, academic papers, scientific findings,
    AI/ML papers, physics, mathematics, computer science.
    
    Args:
        query: Research topic or paper title to search
        max_papers: Number of papers to return (default: 3)
        
    Returns:
        str: Paper titles, authors, abstracts, and links
    """
    agent_logger.info(f"📄 Tool: arxiv_search({query})")
    
    try:
        from langchain_community.document_loaders import ArxivLoader
    except ImportError:
        return "Error: langchain-community or arxiv not installed"
    
    try:
        loader = ArxivLoader(
            query=query,
            load_max_docs=max_papers
        )
        
        docs = loader.get_summaries_as_docs()
        
        if not docs:
            return f"No arXiv papers found for: {query}"
        
        # Format results
        formatted = [f"=== arXiv Research Papers: {query} ===\n"]
        
        for i, doc in enumerate(docs, 1):
            meta = doc.metadata
            formatted.append(f"\n--- Paper {i} ---")
            formatted.append(f"Title: {meta.get('Title', 'N/A')}")
            formatted.append(f"Authors: {meta.get('Authors', 'N/A')}")
            formatted.append(f"Published: {meta.get('Published', 'N/A')}")
            formatted.append(f"arXiv ID: {meta.get('Entry ID', 'N/A')}")
            formatted.append(f"\nAbstract:\n{doc.page_content[:1500]}...")
            formatted.append("=" * 50)
        
        result = "\n".join(formatted)
        agent_logger.info(f"✅ arXiv returned {len(docs)} papers")
        return result
        
    except Exception as e:
        agent_logger.error(f"❌ arXiv search error: {e}")
        return f"arXiv search failed: {str(e)}"


# ==================== GITHUB TOOL ====================

@tool
async def github_search(query: str, search_type: str = "repositories") -> str:
    """
    Search GitHub for repositories, code, or issues.
    
    Args:
        query: Search query (e.g., "langchain python", "react hooks")
        search_type: Type of search - "repositories", "code", or "issues"
        
    Returns:
        str: GitHub search results with links
    """
    agent_logger.info(f"🐙 Tool: github_search({query}, type={search_type})")
    
    # GitHub Search API
    base_url = "https://api.github.com/search"
    
    endpoints = {
        "repositories": f"{base_url}/repositories",
        "code": f"{base_url}/code",
        "issues": f"{base_url}/issues"
    }
    
    url = endpoints.get(search_type, endpoints["repositories"])
    
    try:
        timeout = aiohttp.ClientTimeout(total=15)
        headers = {
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'QUASAR-CLI'
        }
        
        # Add auth if available
        github_token = os.getenv("GITHUB_TOKEN")
        if github_token:
            headers['Authorization'] = f"token {github_token}"
        
        params = {'q': query, 'per_page': 5}
        
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            async with session.get(url, params=params) as response:
                if response.status != 200:
                    return f"GitHub API error: HTTP {response.status}"
                
                data = await response.json()
                items = data.get('items', [])
                
                if not items:
                    return f"No GitHub {search_type} found for: {query}"
                
                formatted = [f"=== GitHub {search_type.title()} for: {query} ===\n"]
                
                for i, item in enumerate(items[:5], 1):
                    if search_type == "repositories":
                        formatted.append(
                            f"{i}. {item.get('full_name', 'N/A')}\n"
                            f"   ⭐ {item.get('stargazers_count', 0)} | "
                            f"🍴 {item.get('forks_count', 0)}\n"
                            f"   {item.get('description', 'No description')[:100]}\n"
                            f"   URL: {item.get('html_url', 'N/A')}\n"
                        )
                    elif search_type == "issues":
                        formatted.append(
                            f"{i}. {item.get('title', 'N/A')}\n"
                            f"   State: {item.get('state', 'N/A')}\n"
                            f"   URL: {item.get('html_url', 'N/A')}\n"
                        )
                    else:
                        formatted.append(f"{i}. {item.get('name', 'N/A')}\n")
                
                result = "\n".join(formatted)
                agent_logger.info(f"✅ GitHub returned {len(items)} results")
                return result
                
    except Exception as e:
        agent_logger.error(f"❌ GitHub search error: {e}")
        return f"GitHub search failed: {str(e)}"


# ==================== SMART CONTENT EXTRACTION ====================

def _bm25_score(query_terms: List[str], doc_terms: List[str], avg_doc_len: float, k1: float = 1.5, b: float = 0.75) -> float:
    """
    Calculate BM25 score for a document given query terms.
    
    BM25 is a ranking function used by search engines to score documents.
    Fast, no external dependencies, good for keyword matching.
    """
    from collections import Counter
    
    doc_len = len(doc_terms)
    if doc_len == 0 or avg_doc_len == 0:
        return 0.0
    
    term_freqs = Counter(doc_terms)
    score = 0.0
    
    for term in query_terms:
        if term in term_freqs:
            tf = term_freqs[term]
            # BM25 formula
            numerator = tf * (k1 + 1)
            denominator = tf + k1 * (1 - b + b * (doc_len / avg_doc_len))
            score += numerator / denominator
    
    return score


def _tokenize(text: str) -> List[str]:
    """Simple tokenization: lowercase, split on non-alphanumeric."""
    return re.findall(r'\b\w+\b', text.lower())


def _split_into_paragraphs(content: str, min_length: int = 50) -> List[str]:
    """Split content into paragraphs, filtering out short ones."""
    # Split by double newlines or multiple newlines
    paragraphs = re.split(r'\n\s*\n', content)
    
    # Also handle single newlines for dense content
    result = []
    for para in paragraphs:
        para = para.strip()
        if len(para) >= min_length:
            result.append(para)
    
    return result


@tool
async def extract_relevant_content(url: str, query: str, max_paragraphs: int = 5) -> str:
    """
    Extract only the RELEVANT parts of a web page based on your query.
    
    This is the PREFERRED tool for reading web content. It uses BM25 ranking
    to find and return only the paragraphs that are relevant to your query,
    instead of returning the entire page content.
    
    Use this when:
    - You need specific information from a long page
    - You want focused, relevant content
    - The page is too long to read entirely
    
    Falls back to jina_reader if no relevant content is found.
    
    Args:
        url: The web page URL to extract content from
        query: What information you're looking for (be specific!)
        max_paragraphs: Maximum number of relevant paragraphs to return (default: 5)
        
    Returns:
        str: Relevant content excerpts ranked by relevance to your query
    """
    agent_logger.info(f"🎯 Tool: extract_relevant_content({url}, query='{query[:30]}...')")
    
    content = None
    fetch_method = None
    
    # Try multiple fetch methods
    try:
        timeout = aiohttp.ClientTimeout(total=30)
        headers = {
            'User-Agent': 'QUASAR-CLI/1.0',
            'Accept': 'text/plain'
        }
        
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            # Method 1: Try Jina Reader first (cleaner content)
            jina_url = f"https://r.jina.ai/{url}"
            try:
                async with session.get(jina_url) as response:
                    if response.status == 200:
                        content = await response.text()
                        fetch_method = "Jina Reader"
                        agent_logger.info("✅ Fetched via Jina Reader")
            except Exception as jina_error:
                agent_logger.warning(f"⚠️ Jina Reader failed: {jina_error}")
            
            # Method 2: Direct fetch if Jina failed
            if not content or len(content) < 100:
                agent_logger.info("🔄 Trying direct fetch...")
                try:
                    async with session.get(url) as direct_response:
                        if direct_response.status == 200:
                            raw_content = await direct_response.text()
                            # Clean HTML
                            content = re.sub(r'<script[^>]*>.*?</script>', '', raw_content, flags=re.DOTALL | re.IGNORECASE)
                            content = re.sub(r'<style[^>]*>.*?</style>', '', content, flags=re.DOTALL | re.IGNORECASE)
                            content = re.sub(r'<[^>]+>', ' ', content)
                            content = re.sub(r'\s+', ' ', content).strip()
                            fetch_method = "Direct Fetch"
                            agent_logger.info("✅ Fetched via direct fetch")
                        else:
                            agent_logger.warning(f"⚠️ Direct fetch failed: HTTP {direct_response.status}")
                except Exception as direct_error:
                    agent_logger.warning(f"⚠️ Direct fetch failed: {direct_error}")
        
        if not content or len(content) < 100:
            return f"Error: Could not fetch content from {url}. Both Jina Reader and direct fetch failed."
        
        # Split into paragraphs
        paragraphs = _split_into_paragraphs(content)
        
        if not paragraphs:
            agent_logger.warning("⚠️ No paragraphs found, returning truncated content")
            return content[:4000] + "\n\n[Content truncated]"
        
        # Tokenize query and paragraphs
        query_terms = _tokenize(query)
        
        if not query_terms:
            agent_logger.warning("⚠️ Empty query, returning first paragraphs")
            return "\n\n".join(paragraphs[:max_paragraphs])
        
        # Calculate average document length
        all_terms = [_tokenize(p) for p in paragraphs]
        avg_doc_len = sum(len(t) for t in all_terms) / len(all_terms) if all_terms else 1
        
        # Score each paragraph with BM25
        scored_paragraphs = []
        for i, para in enumerate(paragraphs):
            para_terms = all_terms[i]
            score = _bm25_score(query_terms, para_terms, avg_doc_len)
            if score > 0:  # Only include paragraphs with some relevance
                scored_paragraphs.append((score, para))
        
        # Sort by score (highest first)
        scored_paragraphs.sort(key=lambda x: x[0], reverse=True)
        
        # Check if we found relevant content
        if not scored_paragraphs:
            agent_logger.warning(f"⚠️ No relevant content found for query '{query}', returning full content")
            # Return first few paragraphs as fallback
            fallback = "\n\n".join(paragraphs[:max_paragraphs])
            return f"=== Content from {url} ===\n(No paragraphs matched query '{query}', showing first paragraphs)\n\n{fallback}"
        
        # Take top paragraphs
        top_paragraphs = scored_paragraphs[:max_paragraphs]
        
        # Format output
        formatted = [f"=== Relevant Content from {url} ==="]
        formatted.append(f"Query: '{query}'")
        formatted.append(f"Found {len(scored_paragraphs)} relevant sections, showing top {len(top_paragraphs)}:\n")
        
        for i, (score, para) in enumerate(top_paragraphs, 1):
            formatted.append(f"--- Section {i} (relevance: {score:.2f}) ---")
            formatted.append(para[:1500])  # Limit each paragraph
            formatted.append("")
        
        result = "\n".join(formatted)
        agent_logger.info(f"✅ Extracted {len(top_paragraphs)} relevant paragraphs (BM25)")
        return result
        
    except asyncio.TimeoutError:
        return f"Error: Request timed out (30 seconds)"
    except Exception as e:
        agent_logger.error(f"❌ Extract relevant content error: {e}")
        return f"Extraction failed: {str(e)}"


# ==================== EXPORT ====================

WEB_TOOLS = [
    # Smart extraction (PREFERRED for reading URLs)
    extract_relevant_content,
    
    # Primary search
    tavily_search,
    duckduckgo_search,
    
    # Full URL content (fallback)
    jina_reader,
    fetch_url_content,
    
    # Knowledge bases
    wikipedia_search,
    arxiv_search,
    
    # GitHub
    github_search,
]
