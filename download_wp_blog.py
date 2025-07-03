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
    # Decode HTML entities
    title = html.unescape(title)
    # Remove forbidden characters: * " \ / < > : | ?
    forbidden = r'[\*\\"\/<>\:\|\?]'
    title = re.sub(forbidden, '', title)
    # Remove leading/trailing whitespace and dots
    title = title.strip(' .')
    # Collapse whitespace
    title = re.sub(r'\s+', ' ', title)
    # Fallback if title is empty after cleaning
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

def save_post_as_markdown(post, existing_filenames):
    title = post['title']
    content_html = post['content']
    date_full = post['date']  # Example: '2012-07-24T18:05:41+00:00'
    filename_title = clean_title_for_filename(title)
    filename = f"{filename_title}.md"
    # Ensure filename is unique in the folder
    counter = 1
    base_filename = filename_title
    while filename in existing_filenames:
        filename = f"{base_filename} ({counter}).md"
        counter += 1
    existing_filenames.add(filename)
    filepath = os.path.join(OUTPUT_DIR, filename)
    content_md = md(content_html)
    # YAML front matter: title, date, tags, cssclasses (wide-page)
    front_matter = (
        f"---\n"
        f'title: "{title}"\n'
        f"date: {date_full}\n"
        f"tags: faith, religion, church, orthodoxy, orthodox, spiritual, bible, prayer, christianity, catholicism\n"
        f"cssclasses: wide-page\n"
        f"---\n\n"
    )
    # Add [[Sam Shamoun]] at the end
    full_content = front_matter + content_md.strip() + "\n\n[[Sam Shamoun]]\n"
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(full_content)
    # Set file modification and access times to the post's date
    dt = datetime.strptime(date_full, '%Y-%m-%dT%H:%M:%S%z')
    timestamp = dt.timestamp()
    os.utime(filepath, (timestamp, timestamp))

def main():
    posts = fetch_all_posts()
    print(f"Found {len(posts)} posts. Downloading and converting to Markdown...")
    existing_filenames = set()
    for post in tqdm(posts):
        save_post_as_markdown(post, existing_filenames)
    print(f"All posts saved to '{OUTPUT_DIR}'.")

if __name__ == "__main__":
    main()
