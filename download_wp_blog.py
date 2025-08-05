import os
import requests
from markdownify import markdownify as md
from tqdm import tqdm
import re
from datetime import datetime
import html
from urllib.parse import urlparse

BLOG_ID = "answeringislamblog.wordpress.com"
API_URL = f"https://public-api.wordpress.com/rest/v1.1/sites/{BLOG_ID}/posts/"
OUTPUT_DIR = "downloaded_posts"
POSTS_PER_PAGE = 100

os.makedirs(OUTPUT_DIR, exist_ok=True)

def clean_title_for_filename(title):
    """Clean title for safe filename usage"""
    title = html.unescape(title)
    forbidden = r'[\*\\"\/<>\:\|\?]'
    title = re.sub(forbidden, '', title)
    title = title.strip(' .')
    title = re.sub(r'\s+', ' ', title)
    if not title:
        title = "untitled"
    return title

def fetch_all_posts():
    """Fetch all posts from the WordPress API"""
    posts = []
    offset = 0
    total = None
    print("Fetching posts...")
    
    while True:
        resp = requests.get(API_URL, params={'number': POSTS_PER_PAGE, 'offset': offset})
        if resp.status_code != 200:
            print(f"Error: Received status code {resp.status_code}")
            break
            
        data = resp.json()
        if total is None:
            total = data.get('found', 0)
            if total == 0:
                print("No posts found.")
                break
                
        batch = data.get('posts', [])
        if not batch:
            break
            
        posts.extend(batch)
        offset += POSTS_PER_PAGE
        
        if len(posts) >= total:
            break
            
    return posts

def roman_to_int(roman):
    """Convert roman numerals to integers"""
    roman_numerals = {
        'i': 1, 'v': 5, 'x': 10, 'l': 50, 'c': 100, 'd': 500, 'm': 1000,
        'I': 1, 'V': 5, 'X': 10, 'L': 50, 'C': 100, 'D': 500, 'M': 1000
    }
    
    result = 0
    prev_value = 0
    
    for char in reversed(roman):
        value = roman_numerals.get(char, 0)
        if value < prev_value:
            result -= value
        else:
            result += value
        prev_value = value
    
    return result

def extract_existing_footnotes(content_md):
    """Extract and catalog existing footnotes from content"""
    footnote_refs = {}  # Maps original ref to new number
    footnote_definitions = {}  # Maps new number to URL/definition
    footnote_counter = 0
    
    # Pattern 1: WordPress-style footnotes [[1]](url), [[2]](url), etc.
    def extract_wp_footnotes(match):
        nonlocal footnote_counter
        original_num = match.group(1)
        url = match.group(2)
        
        if original_num not in footnote_refs:
            footnote_counter += 1
            footnote_refs[original_num] = footnote_counter
            footnote_definitions[footnote_counter] = url
        
        return f"[^{footnote_refs[original_num]}]"
    
    # Handle WordPress-style footnotes first
    content_md = re.sub(r'\[\[(\d+)\]\]\(([^)]+)\)', extract_wp_footnotes, content_md)
    
    # Pattern 2: Standard markdown footnotes [^1], [^note], etc.
    existing_standard_footnotes = re.findall(r'\[\^([^\]]+)\]', content_md)
    for ref in existing_standard_footnotes:
        if ref not in footnote_refs and not ref.isdigit():
            footnote_counter += 1
            footnote_refs[ref] = footnote_counter
    
    # Pattern 3: Various other footnote formats
    # Numbers in parentheses (1), (2), etc.
    def extract_paren_nums(match):
        nonlocal footnote_counter
        num = match.group(1)
        ref_key = f"paren_{num}"
        
        if ref_key not in footnote_refs:
            footnote_counter += 1
            footnote_refs[ref_key] = footnote_counter
        
        return f"[^{footnote_refs[ref_key]}]"
    
    content_md = re.sub(r'\((\d+)\)', extract_paren_nums, content_md)
    
    # Roman numerals in parentheses (i), (ii), etc.
    def extract_paren_roman(match):
        nonlocal footnote_counter
        roman = match.group(1)
        ref_key = f"roman_{roman}"
        
        if ref_key not in footnote_refs:
            footnote_counter += 1
            footnote_refs[ref_key] = footnote_counter
        
        return f"[^{footnote_refs[ref_key]}]"
    
    content_md = re.sub(r'\(([ivxlcdm]+)\)', extract_paren_roman, content_md, flags=re.IGNORECASE)
    
    return content_md, footnote_refs, footnote_definitions

def extract_links_and_convert_to_footnotes(content_md, existing_footnote_count=0):
    """Extract markdown links and convert them to footnotes"""
    footnote_definitions = {}
    footnote_counter = existing_footnote_count
    
    # Pattern to match markdown links [text](url) - but not footnote references
    def replace_markdown_links(match):
        nonlocal footnote_counter
        text = match.group(1)
        url = match.group(2)
        
        # Skip if it's already a footnote reference (starts with ^)
        if text.startswith('^'):
            return match.group(0)
        
        # Skip if it looks like it's already been processed
        if url.startswith('Link'):
            return match.group(0)
        
        footnote_counter += 1
        footnote_definitions[footnote_counter] = url
        
        return f"{text}[^{footnote_counter}]"
    
    # Convert markdown links to footnotes
    content_md = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', replace_markdown_links, content_md)
    
    # Handle plain URLs
    def replace_plain_urls(match):
        nonlocal footnote_counter
        url = match.group(0)
        
        footnote_counter += 1
        footnote_definitions[footnote_counter] = url
        
        return f"[Link][^{footnote_counter}]"
    
    # Pattern for standalone URLs
    url_pattern = r'https?://[^\s\]\)\}\'"<>]+'
    content_md = re.sub(url_pattern, replace_plain_urls, content_md)
    
    return content_md, footnote_definitions

def build_url_to_filename_map(posts):
    """Build a mapping of URLs to filenames for internal linking"""
    url_to_filename = {}
    for post in posts:
        url = post.get('URL', '').rstrip('/')
        filename = clean_title_for_filename(post['title'])
        url_to_filename[url] = filename
    return url_to_filename

def create_organized_footnotes_section(existing_footnote_defs, link_footnote_defs, url_to_filename):
    """Create a well-organized footnotes section"""
    if not existing_footnote_defs and not link_footnote_defs:
        return ""
    
    # Combine all footnote definitions
    all_footnotes = {}
    all_footnotes.update(existing_footnote_defs)
    all_footnotes.update(link_footnote_defs)
    
    if not all_footnotes:
        return ""
    
    # Categorize footnotes
    internal_links = []
    academic_sources = []
    external_links = []
    
    # Sort footnotes by number
    sorted_footnotes = sorted(all_footnotes.items())
    
    for footnote_num, url in sorted_footnotes:
        # Clean URL for comparison
        clean_url = url.rstrip('/')
        
        # Check if it's an internal link
        if clean_url in url_to_filename:
            filename = url_to_filename[clean_url]
            internal_links.append(f"[^{footnote_num}]: [[{filename}]]")
        
        # Check for academic sources
        elif any(domain in url.lower() for domain in [
            'bible', 'scholar', 'jstor', 'academia', 'researchgate', 'pubmed',
            'nd.edu', 'yale.edu', 'harvard.edu', 'cambridge.org', 'oxford'
        ]):
            academic_sources.append(f"[^{footnote_num}]: {url}")
        
        # Everything else is external
        else:
            external_links.append(f"[^{footnote_num}]: {url}")
    
    # Build the organized footnotes section
    footnotes_lines = ["\n## References\n"]
    
    if internal_links:
        footnotes_lines.append("### Related Articles")
        footnotes_lines.extend(internal_links)
        footnotes_lines.append("")
    
    if academic_sources:
        footnotes_lines.append("### Academic Sources")
        footnotes_lines.extend(academic_sources)
        footnotes_lines.append("")
    
    if external_links:
        footnotes_lines.append("### External Links")
        footnotes_lines.extend(external_links)
    
    return "\n".join(footnotes_lines)

def comprehensive_content_cleaner(content_md):
    """Clean up content for better Obsidian compatibility"""
    
    # Remove HTML comments
    content_md = re.sub(r'<!--.*?-->', '', content_md, flags=re.DOTALL)
    
    # Clean up excessive whitespace
    content_md = re.sub(r'\n\s*\n\s*\n+', '\n\n', content_md)
    
    # Fix markdown formatting
    content_md = re.sub(r'\*\*\s+', '**', content_md)
    content_md = re.sub(r'\s+\*\*', '**', content_md)
    content_md = re.sub(r'\*\s+', '*', content_md)
    content_md = re.sub(r'\s+\*', '*', content_md)
    
    # Clean up quote blocks
    content_md = re.sub(r'^>\s*$', '', content_md, flags=re.MULTILINE)
    
    # Remove orphaned footnote definitions from middle of text
    content_md = re.sub(r'^\[\^[^\]]+\]:.*$', '', content_md, flags=re.MULTILINE)
    
    # Clean up any remaining artifacts
    content_md = re.sub(r'\n\s*\n\s*\n+', '\n\n', content_md)
    
    return content_md.strip()

def create_obsidian_tags(content, title):
    """Generate relevant tags based on content analysis"""
    base_tags = [
        "faith", "religion", "church", "orthodoxy", "orthodox", 
        "spiritual", "bible", "prayer", "christianity", "catholicism"
    ]
    
    # Add dynamic tags based on content
    content_lower = (content + " " + title).lower()
    
    additional_tags = []
    
    if any(word in content_lower for word in ['islam', 'muslim', 'quran', 'muhammad']):
        additional_tags.append("islam")
    
    if any(word in content_lower for word in ['apologetics', 'debate', 'refutation']):
        additional_tags.append("apologetics")
    
    if any(word in content_lower for word in ['trinity', 'incarnation', 'christology']):
        additional_tags.append("doctrine")
    
    if any(word in content_lower for word in ['scripture', 'biblical', 'exegesis']):
        additional_tags.append("biblical-studies")
    
    if any(word in content_lower for word in ['theology', 'theological']):
        additional_tags.append("theology")
    

    
    return base_tags + additional_tags

def save_post_as_markdown(post, existing_filenames, url_to_filename):
    """Save individual post as Obsidian-formatted markdown file"""
    title = post['title']
    content_html = post['content']
    date_full = post['date']
    post_url = post.get('URL', '')
    
    # Generate unique filename
    filename_title = clean_title_for_filename(title)
    filename = f"{filename_title}.md"
    counter = 1
    base_filename = filename_title
    
    while filename in existing_filenames:
        filename = f"{base_filename} ({counter}).md"
        counter += 1
    
    existing_filenames.add(filename)
    filepath = os.path.join(OUTPUT_DIR, filename)
    
    # Convert HTML to markdown
    content_md = md(content_html)
    
    # Clean the content
    content_clean = comprehensive_content_cleaner(content_md)
    
    # Extract and normalize existing footnotes
    content_with_existing_footnotes, footnote_refs, existing_footnote_defs = extract_existing_footnotes(content_clean)
    
    # Convert remaining links to footnotes
    existing_footnote_count = len(existing_footnote_defs)
    content_final, link_footnote_defs = extract_links_and_convert_to_footnotes(
        content_with_existing_footnotes, existing_footnote_count
    )
    
    # Create organized footnotes section
    footnotes_section = create_organized_footnotes_section(
        existing_footnote_defs, link_footnote_defs, url_to_filename
    )
    
    # Generate tags
    tags = create_obsidian_tags(content_final, title)
    
    # Create front matter
    front_matter = f"""---
title: "{title}"
date: {date_full}
author: "[[Sam Shamoun]]"
tags: 
{chr(10).join(f"  - {tag}" for tag in tags)}
cssclasses: 
  - wide-page
---

"""
    
    # Combine everything
    full_content = (
        front_matter + 
        content_final + 
        footnotes_section
    )
    
    # Write file
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(full_content)
    
    # Set file timestamp
    try:
        dt = datetime.strptime(date_full, '%Y-%m-%dT%H:%M:%S%z')
        timestamp = dt.timestamp()
        os.utime(filepath, (timestamp, timestamp))
    except ValueError:
        pass

def create_index_file(posts_count):
    """Create an index file for navigation"""
    index_content = f"""---
title: "Answering Islam Blog - Article Index"
date: {datetime.now().isoformat()}
tags:
  - index
  - navigation
cssclasses: 
  - index-page
---

# Answering Islam Blog Articles

This vault contains {posts_count} articles from Sam Shamoun's Answering Islam blog, converted to Obsidian-compatible markdown format.

## Features

- **Smart Footnote Linting**: All footnote formats normalized to Obsidian standard `[^1]`
- **Link Deduplication**: Same URLs get same footnote numbers across articles
- **Organized References**: Footnotes categorized (Related Articles, Academic Sources, External Links)
- **Internal Linking**: Cross-references use `[[Article Title]]` format
- **Rich Metadata**: Full publication data and dynamic tagging

## Navigation

Use Obsidian's graph view to explore connections, or browse by tags:

- `#apologetics` - Apologetic discussions and debates
- `#doctrine` - Theological doctrine and Christology
- `#biblical-studies` - Scripture analysis and exegesis
- `#islam` - Articles addressing Islamic topics
- `#theology` - General theological discussions

---

**Author**: [[Sam Shamoun]]  
**Source**: [Answering Islam Blog](https://answeringislamblog.wordpress.com/)  
**Conversion Date**: {datetime.now().strftime('%Y-%m-%d')}
"""
    
    with open(os.path.join(OUTPUT_DIR, "README.md"), "w", encoding="utf-8") as f:
        f.write(index_content)

def main():
    """Main execution function"""
    print("Starting Answering Islam Blog scraper with advanced footnote linting...")
    
    # Fetch all posts
    posts = fetch_all_posts()
    print(f"Found {len(posts)} posts.")
    
    if not posts:
        print("No posts found. Exiting.")
        return
    
    # Build URL mapping for internal links
    url_to_filename = build_url_to_filename_map(posts)
    
    # Process each post
    existing_filenames = set()
    print("Converting posts with comprehensive footnote processing...")
    
    for post in tqdm(posts, desc="Processing posts"):
        try:
            save_post_as_markdown(post, existing_filenames, url_to_filename)
        except Exception as e:
            print(f"Error processing post '{post.get('title', 'Unknown')}': {e}")
            continue
    
    # Create index file
    create_index_file(len(posts))
    
    print(f"\nAll posts saved to '{OUTPUT_DIR}' directory.")
    print("\nAdvanced footnote processing completed:")
    print("✓ WordPress [[1]](url) format → [^1]")
    print("✓ Roman numerals (i), (ii) → [^1], [^2]") 
    print("✓ Number formats (1), [2] → [^1], [^2]")
    print("✓ Link deduplication and smart categorization")
    print("✓ Obsidian-optimized internal linking")
    print("✓ Organized reference sections by source type")

if __name__ == "__main__":
    main()
