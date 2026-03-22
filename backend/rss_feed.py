"""
rss_feed.py - RSS 2.0 Feed Generator for Arc Codex
Register as a Flask blueprint in app.py.

Exposes /rss (or /feed.xml) returning valid RSS 2.0 with A.R.C. analysis
embedded in each item's description.

Usage in app.py:
    from rss_feed import rss_blueprint
    app.register_blueprint(rss_blueprint)
"""

from flask import Blueprint, Response, request
from xml.etree.ElementTree import Element, SubElement, tostring
from datetime import datetime, timezone
import time
import logging

logger = logging.getLogger(__name__)

rss_blueprint = Blueprint('rss', __name__)

# Will be set by app.py after blueprint registration
_redis = None

def init_rss(redis_conn):
    """Initialize the RSS module with a Redis connection."""
    global _redis
    _redis = redis_conn


def build_analysis_html(article):
    """Build HTML content from Red/Blue/Purple analysis for the RSS description."""
    sections = []
    
    red = article.get('red_team_analysis', '').strip()
    blue = article.get('blue_team_analysis', '').strip()
    purple = article.get('purple_team_analysis', '').strip()
    
    if blue:
        sections.append(f"<h3>📋 Executive Summary</h3><p>{blue}</p>")
    if red:
        # Convert bullet-style text to HTML list
        lines = [line.strip().lstrip('•-').strip() for line in red.split('\n') if line.strip()]
        if lines:
            items = ''.join(f'<li>{line}</li>' for line in lines)
            sections.append(f"<h3>🎯 Facts Only</h3><ul>{items}</ul>")
    if purple:
        sections.append(f"<h3>🔮 Full Take</h3><p>{purple}</p>")
    
    # Add chimera score if available
    dossier = article.get('dossier', '')
    if dossier:
        try:
            import json
            d = json.loads(dossier)
            score = d.get('chimera_score')
            if score is not None:
                sections.append(f"<p><em>Chimera Score: {score:.2f}</em></p>")
        except (json.JSONDecodeError, TypeError):
            pass
    
    if not sections:
        # Fall back to original text snippet
        original = article.get('original_text', '')
        if original:
            snippet = original[:500] + ('...' if len(original) > 500 else '')
            sections.append(f"<p>{snippet}</p>")
    
    return '\n'.join(sections)


def format_rss_date(timestamp_str):
    """Convert stored timestamp to RFC 822 format for RSS."""
    if not timestamp_str:
        return datetime.now(timezone.utc).strftime('%a, %d %b %Y %H:%M:%S +0000')
    
    try:
        # Try ISO format first
        dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        return dt.strftime('%a, %d %b %Y %H:%M:%S +0000')
    except (ValueError, AttributeError):
        pass
    
    try:
        # Try common date formats
        for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%b %d, %Y, %I:%M %p'):
            try:
                dt = datetime.strptime(timestamp_str, fmt)
                return dt.strftime('%a, %d %b %Y %H:%M:%S +0000')
            except ValueError:
                continue
    except Exception:
        pass
    
    return datetime.now(timezone.utc).strftime('%a, %d %b %Y %H:%M:%S +0000')


@rss_blueprint.route('/api/rss')
@rss_blueprint.route('/api/feed.xml')
def rss_feed():
    """Generate RSS 2.0 feed from the latest articles."""
    if not _redis:
        return Response("RSS feed unavailable", status=503, mimetype='text/plain')
    
    limit = request.args.get('limit', 25, type=int)
    limit = min(limit, 50)  # Cap at 50
    category = request.args.get('category', '', type=str).strip()
    
    try:
        start = time.perf_counter()
        
        # Fetch latest article IDs
        article_ids = _redis.zrevrange('feed', 0, limit * 2 - 1)  # Fetch extra for filtering
        if not article_ids:
            return _empty_feed()
        
        # Pipeline fetch all articles
        pipe = _redis.pipeline()
        for aid in article_ids:
            pipe.hgetall(f"article:{aid}")
        results = pipe.execute()
        
        # Build RSS XML
        rss = Element('rss', version='2.0')
        rss.set('xmlns:atom', 'http://www.w3.org/2005/Atom')
        channel = SubElement(rss, 'channel')
        
        SubElement(channel, 'title').text = 'Arc Codex — A.R.C. Intelligence Feed'
        SubElement(channel, 'link').text = 'https://arc-codex.com'
        SubElement(channel, 'description').text = (
            'News analysis through the Argumentative Resilience Codex. '
            'Three-team AI analysis: Facts Only, Executive Summary, and Full Take.'
        )
        SubElement(channel, 'language').text = 'en'
        SubElement(channel, 'lastBuildDate').text = datetime.now(timezone.utc).strftime(
            '%a, %d %b %Y %H:%M:%S +0000'
        )
        SubElement(channel, 'generator').text = 'Arc Codex A.R.C. Framework'
        SubElement(channel, 'ttl').text = '30'
        
        # Self-referencing atom link (best practice)
        atom_link = SubElement(channel, 'atom:link')
        atom_link.set('href', 'https://arc-codex.com/api/rss')
        atom_link.set('rel', 'self')
        atom_link.set('type', 'application/rss+xml')
        
        count = 0
        for aid, article in zip(article_ids, results):
            if not article or not article.get('title'):
                continue
            
            # Category filter
            if category and article.get('category', '').lower() != category.lower():
                continue
            
            if count >= limit:
                break
            
            item = SubElement(channel, 'item')
            SubElement(item, 'title').text = article.get('title', 'Untitled')
            
            # Link to article page
            slug = article.get('slug', aid)
            SubElement(item, 'link').text = (
                f"https://arc-codex.com/article/{slug}"
            )
            
            # Use article_id as GUID
            guid = SubElement(item, 'guid')
            guid.text = f"arc-codex-{aid}"
            guid.set('isPermaLink', 'false')
            
            # Publication date
            SubElement(item, 'pubDate').text = format_rss_date(article.get('timestamp'))
            
            # Source attribution
            source_name = article.get('source', '')
            source_url = article.get('sourceUrl', article.get('url', ''))
            if source_name:
                source_el = SubElement(item, 'source')
                source_el.text = source_name
                if source_url:
                    source_el.set('url', source_url)
            
            # Category
            cat = article.get('category', '')
            if cat:
                SubElement(item, 'category').text = cat
            
            # Description: A.R.C. analysis as HTML
            description = build_analysis_html(article)
            SubElement(item, 'description').text = description
            
            count += 1
        
        duration_ms = (time.perf_counter() - start) * 1000
        logger.info(f"📡 RSS feed generated: {count} items in {duration_ms:.0f}ms")
        
        xml_bytes = tostring(rss, encoding='unicode', xml_declaration=False)
        xml_output = '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_bytes
        
        return Response(
            xml_output,
            mimetype='application/xml',
            headers={'Cache-Control': 'public, max-age=300'}  # 5 min cache
        )
        
    except Exception as e:
        logger.error(f"🔥 RSS feed generation failed: {e}", exc_info=True)
        return Response("RSS feed error", status=500, mimetype='text/plain')


def _empty_feed():
    """Return a valid but empty RSS feed."""
    rss = Element('rss', version='2.0')
    channel = SubElement(rss, 'channel')
    SubElement(channel, 'title').text = 'Arc Codex — A.R.C. Intelligence Feed'
    SubElement(channel, 'description').text = 'No articles available.'
    xml_bytes = tostring(rss, encoding='unicode', xml_declaration=False)
    xml_output = '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_bytes
    return Response(xml_output, mimetype='application/xml')
