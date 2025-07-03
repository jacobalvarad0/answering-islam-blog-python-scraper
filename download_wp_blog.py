import os
import requests
from markdownify import markdownify as md
from tqdm import tqdm
import re
from datetime import datetime
import html

BLOG_ID = "answeringislamblog.wordpress.com"
API_URL = f"https://public-api.wordpress.com/rest/v1.1/sites/{BLOG_ID}/posts/"
OUTPUT_DIR = "downloaded_posts"
POSTS_PER_PAGE = 100

os.makedirs(OUTPUT_DIR, exist_ok=True)

def clean_title_for_filename(title):
    title = html.unescape(title)
    forbidden = r'[\*\\"\/<>\:\|\?]'
    title = re.sub(forbidden, '', title)
    title = title.strip(' .')
    title = re.sub(r'\s+', ' ', title)
    if not title:
        title = "untitled"
    return title

def fetch_all_posts():
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

def remove_author_footnotes(content_md):
    # Remove inline references like [^1], [^note], etc.
    content_md = re.sub(r'\[\^([^\]]+)\]', '', content_md)
    # Remove footnote definitions at the end: [^1]: ... or [^note]: ...
    content_md = re.sub(r'^\[\^([^\]]+)\]:.*(?:\n(?:[ ]{2,}.*|\t.*))*', '', content_md, flags=re.MULTILINE)
    return content_md

def build_url_to_filename_map(posts):
    url_to_filename = {}
    for post in posts:
        # Use the canonical URL (strip trailing slash)
        url = post.get('URL', post.get('URL', '')).rstrip('/')
        filename = clean_title_for_filename(post['title']) + '.md'
        url_to_filename[url] = filename
    return url_to_filename

def replace_links_with_footnotes(content_md):
    link_pattern = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')
    footnotes = []
    footnote_map = {}

    def link_replacer(match):
        text, url = match.group(1), match.group(2)
        key = (text, url)
        if key not in footnote_map:
            footnotes.append((text, url))
            footnote_number = len(footnotes)
            footnote_map[key] = footnote_number
        else:
            footnote_number = footnote_map[key]
        return f"{text}[^{footnote_number}]"

    content_with_footnotes = link_pattern.sub(link_replacer, content_md)
    return content_with_footnotes, footnotes

def format_obsidian_footnotes(footnotes, url_to_filename):
    if not footnotes:
        return ""
    lines = ["\n"]
    for idx, (text, url) in enumerate(footnotes, 1):
        url_canon = url.rstrip('/')
        if url_canon in url_to_filename:
            # Convert to Obsidian link using the file name (without .md)
            file_name = url_to_filename[url_canon][:-3]
            lines.append(f"[^{idx}]: [[{file_name}]]")
        else:
            lines.append(f"[^{idx}]: {url}")
    return "\n".join(lines)

def save_post_as_markdown(post, existing_filenames, url_to_filename):
    title = post['title']
    content_html = post['content']
    date_full = post['date']
    filename_title = clean_title_for_filename(title)
    filename = f"{filename_title}.md"
    counter = 1
    base_filename = filename_title
    while filename in existing_filenames:
        filename = f"{base_filename} ({counter}).md"
        counter += 1
    existing_filenames.add(filename)
    filepath = os.path.join(OUTPUT_DIR, filename)
    content_md = md(content_html)
    # Remove all author footnotes
    content_no_footnotes = remove_author_footnotes(content_md)
    # Replace links with Obsidian-style footnotes
    content_with_footnotes, footnotes = replace_links_with_footnotes(content_no_footnotes)
    footnotes_block = format_obsidian_footnotes(footnotes, url_to_filename)
    front_matter = (
        f"---\n"
        f'title: "{title}"\n'
        f"date: {date_full}\n"
        f"tags: faith, religion, church, orthodoxy, orthodox, spiritual, bible, prayer, christianity, catholicism\n"
        f"cssclasses: wide-page\n"
        f"---\n\n"
    )
    full_content = (
        front_matter
        + content_with_footnotes.strip()
        + "\n\n[[Sam Shamoun]]\n"
        + footnotes_block
    )
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(full_content)
    dt = datetime.strptime(date_full, '%Y-%m-%dT%H:%M:%S%z')
    timestamp = dt.timestamp()
    os.utime(filepath, (timestamp, timestamp))

def main():
    posts = fetch_all_posts()
    print(f"Found {len(posts)} posts. Downloading and converting to Markdown...")
    url_to_filename = build_url_to_filename_map(posts)
    existing_filenames = set()
    for post in tqdm(posts):
        save_post_as_markdown(post, existing_filenames, url_to_filename)
    print(f"All posts saved to '{OUTPUT_DIR}'.")

if __name__ == "__main__":
    main()
