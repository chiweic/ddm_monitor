import asyncio
from fastapi import FastAPI, BackgroundTasks, Query
import httpx
from selectolax.parser import HTMLParser
from typing import List, Dict, Optional
import re
import json
import os
from datetime import datetime
import shutil
from pathlib import Path
import pytz  # Add this import at the top if not present
from contextlib import asynccontextmanager
import spacy


ENTRY_URL = "https://www.ddm.org.tw/xmnews?xsmsid=0K297379120077217595"
SCRAPE_INTERVAL = 86400  # seconds (24 hours = 1 day) - obselete, set to certain time of day

# Data directory structure
DATA_DIR = Path("data")
CURRENT_DIR = DATA_DIR / "current"
ARCHIVE_DIR = DATA_DIR / "archive"
POSTS_FILE = CURRENT_DIR / "posts.json"
POSTS_NEW_FILE = CURRENT_DIR / "posts_new.json"

# initialize nlp element
nlp=spacy.load('zh_core_web_lg')

@asynccontextmanager
async def startup_event(app: FastAPI):
    # create task that scrape at this frequency
    asyncio.create_task(periodic_scrape())
    # look over directory for books ingesting
    yield

app = FastAPI(lifespan=startup_event)

# Initialize data directories
DATA_DIR.mkdir(exist_ok=True)
CURRENT_DIR.mkdir(exist_ok=True)
ARCHIVE_DIR.mkdir(exist_ok=True)

def load_current_posts() -> List[Dict]:
    """Load posts from the current JSON file."""
    try:
        if POSTS_FILE.exists():
            with open(POSTS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"Error loading current posts: {str(e)}")
    return []

def save_posts(posts: List[Dict], file_path: Path) -> bool:
    """Save posts to a JSON file."""
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(posts, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"Error saving posts to {file_path}: {str(e)}")
        return False

def archive_current_posts() -> bool:
    """Archive the current posts file with timestamp."""
    if not POSTS_FILE.exists():
        return True
        
    try:
        timestamp = datetime.now().strftime("%Y%m%d")
        archive_file = ARCHIVE_DIR / f"posts_{timestamp}.json"
        
        # If archive file already exists for today, add hour-minute
        if archive_file.exists():
            timestamp = datetime.now().strftime("%Y%m%d_%H%M")
            archive_file = ARCHIVE_DIR / f"posts_{timestamp}.json"
            
        shutil.move(str(POSTS_FILE), str(archive_file))
        return True
    except Exception as e:
        print(f"Error archiving current posts: {str(e)}")
        return False

def update_posts(new_posts: List[Dict]) -> bool:
    """Update posts with atomic file operations."""
    try:
        # Save new posts to temporary file
        if not save_posts(new_posts, POSTS_NEW_FILE):
            return False
            
        # Archive current posts
        if not archive_current_posts():
            return False
            
        # Move new posts to current
        shutil.move(str(POSTS_NEW_FILE), str(POSTS_FILE))
        return True
    except Exception as e:
        print(f"Error updating posts: {str(e)}")
        # Clean up temporary file if it exists
        if POSTS_NEW_FILE.exists():
            try:
                POSTS_NEW_FILE.unlink()
            except:
                pass
        return False

# Load initial posts
latest_posts = load_current_posts()

async def fetch_post_detail(client, url):
    post = {"url": url}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Connection": "keep-alive",
    }
    try:
        print(f"\nFetching detail page: {url}")
        resp = await client.get(url, headers=headers, timeout=20)
        print(f"Response status: {resp.status_code}")
        print(f"Response headers: {dict(resp.headers)}")
        
        if resp.status_code != 200:
            post["error"] = f"HTTP {resp.status_code}"
            print(f"Error: Got non-200 status code: {resp.status_code}")
            return post
            
        tree = HTMLParser(resp.text)
        
        # Get the main content from the district div
        content_elem = tree.css_first('.district')
        if content_elem:
            # Get all text content, preserving paragraphs
            paragraphs = content_elem.css('p')
            if not paragraphs:
                print(f"Warning: No paragraphs found in .district div for {url}")
                if content_elem.html is not None:
                    print("HTML of .district div:", content_elem.html[:200] + "..." if len(content_elem.html) > 200 else content_elem.html)
                else:
                    print("HTML of .district div: None")
            
            content = '\n\n'.join(p.text(strip=True) for p in paragraphs if p.text(strip=True))
            if not content:
                print(f"Warning: No text content found in paragraphs for {url}")
                post["content"] = ""
            else:
                post["content"] = content
                print(f"Successfully extracted content ({len(content)} chars)")
        else:
            post["content"] = ""
            print(f"Warning: No .district div found for {url}")
            print("Available div classes:", [elem.attributes.get('class', '') for elem in tree.css('div')])
        
    except httpx.TimeoutException:
        error_msg = f"Timeout while fetching {url}"
        print(error_msg)
        post["error"] = error_msg
    except httpx.RequestError as e:
        error_msg = f"Request error for {url}: {str(e)}"
        print(error_msg)
        post["error"] = error_msg
    except Exception as e:
        error_msg = f"Unexpected error fetching {url}: {str(e)}"
        print(error_msg)
        post["error"] = error_msg
    return post

async def scrape_ddm_news():
    """Scrape news and update posts with atomic file operations."""
    global latest_posts
    
    # Keep the current posts in memory while scraping
    current_posts = latest_posts.copy()
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Connection": "keep-alive",
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:  # Create client here
        try:
            all_posts = []
            current_url = ENTRY_URL
            page_num = 1
            
            while current_url:
                try:
                    print(f"\nFetching page {page_num}: {current_url}")
                    resp = await client.get(current_url, headers=headers, timeout=20)
                    print(f"Response status: {resp.status_code}")
                    print(f"Response headers: {dict(resp.headers)}")
                    
                    if resp.status_code != 200:
                        print(f"Error: Got non-200 status code: {resp.status_code}")
                        latest_posts = current_posts  # Keep current posts on error
                        return
                        
                    tree = HTMLParser(resp.text)
                    # Get all items but filter out the form elements
                    all_items = tree.css(".item")
                    print(f"Found {len(all_items)} total items")
                    
                    # Skip the first 3 items which are form elements
                    items = [item for item in all_items[3:] if item.css_first('.cont .title a')]
                    print(f"Found {len(items)} actual post items on page {page_num}")
                    
                    if not items:
                        print("Warning: No valid items found on page")
                        print("First few items HTML:", "\n".join(item.html[:200] + "..." for item in all_items[:3]))
                    
                    # Process items on current page
                    for item in items:
                        try:
                            # Get the title and URL from .cont .title a
                            title_elem = item.css_first('.cont .title a')
                            if not title_elem:
                                print(f"Warning: No title element found in item: {item.html[:200]}...")
                                continue
                                
                            title = title_elem.text(strip=True)
                            href = title_elem.attributes.get("href", "")
                            if not href:
                                print(f"Warning: No href found for title: {title}")
                                continue
                                
                            detail_url = "https://www.ddm.org.tw" + href
                            
                            # Get the date from div.date
                            date_elem = item.css_first('.date')
                            date = date_elem.text(strip=True) if date_elem else ""
                            
                            # Get tags from elements with class 'tag'
                            tag_elems = item.css('.tag')
                            tags = [tag.text(strip=True) for tag in tag_elems if tag.text(strip=True)]
                            
                            # Get description from div.desc
                            desc_elem = item.css_first('.desc')
                            description = desc_elem.text(strip=True) if desc_elem else ""
                            
                            # Create initial post with basic info
                            post = {
                                "title": title,
                                "detail_url": detail_url,
                                "date": date,
                                "tags": tags,
                                "description": description,
                            }
                            print(f"Page {page_num} - Title: {title}")
                            all_posts.append(post)
                            
                        except Exception as e:
                            print(f"Error processing item: {str(e)}")
                            print("Item HTML:", item.html[:200] + "..." if len(item.html) > 200 else item.html)
                            continue
                    
                    # Check for next page
                    print("\nChecking pagination HTML:")
                    next_page = tree.css_first('a.next[title="下一頁"]')
                    print(f"\n--- Page {page_num} Summary ---")
                    print(f"Found {len(items)} posts on this page")
                    if next_page:
                        print("Found next page element:", next_page.html)
                        onclick = next_page.attributes.get('onclick', '')
                        if isinstance(onclick, str) and 'pagingHelper.getList' in onclick:
                            match = re.search(r"pagingHelper\.getList\('Q', (\d+)\)", onclick)
                            if match:
                                next_page_num = int(match.group(1))
                                current_url = f"https://www.ddm.org.tw/xmnews?xsmsid=0K297379120077217595&page={next_page_num}"
                                print(f"Found next page link, moving to page {next_page_num}")
                                page_num = next_page_num
                            else:
                                print("Could not extract page number from onclick")
                                current_url = None
                        else:
                            print("No pagingHelper.getList found in onclick")
                            current_url = None
                    else:
                        print("No next page link found in HTML")
                        current_url = None
                    print("----------------------------\n")
                    
                except httpx.TimeoutException:
                    print(f"Timeout while fetching page {page_num}")
                    break
                except httpx.RequestError as e:
                    print(f"Request error on page {page_num}: {str(e)}")
                    break
                except Exception as e:
                    print(f"Unexpected error on page {page_num}: {str(e)}")
                    break
            
            print(f"\nTotal posts found across all pages: {len(all_posts)}")
            
            if all_posts:  # Only proceed if we found any posts
                # Fetch content for all posts concurrently, but in smaller batches
                print("\nFetching content for all posts...")
                batch_size = 5  # Process 5 posts at a time
                for i in range(0, len(all_posts), batch_size):
                    batch = all_posts[i:i + batch_size]
                    print(f"\nProcessing batch {i//batch_size + 1} of {(len(all_posts) + batch_size - 1)//batch_size}")
                    tasks = [fetch_post_detail(client, post["detail_url"]) for post in batch]
                    detail_results = await asyncio.gather(*tasks, return_exceptions=True)
                    
                    # Update posts with content
                    for post, detail in zip(batch, detail_results):
                        if isinstance(detail, Exception):
                            post["error"] = str(detail)
                            print(f"Error fetching content for {post['title']}: {str(detail)}")
                        elif isinstance(detail, dict):
                            if "content" in detail:
                                post["content"] = detail["content"]
                            if "error" in detail:
                                post["error"] = detail["error"]
                
                # After successful scraping, update the posts
                if update_posts(all_posts):
                    latest_posts = all_posts
                    print(f"Successfully updated posts. Total posts: {len(latest_posts)}")
                else:
                    print("Failed to update posts, keeping current data")
                    latest_posts = current_posts
            else:
                print("No posts found, keeping current data")
                latest_posts = current_posts
                
        except Exception as e:
            print(f"Error in scrape_ddm_news: {str(e)}")
            # Keep the current posts if scraping fails
            latest_posts = current_posts

async def periodic_scrape(target_hour=3, target_minute=0, timezone="America/Los_Angeles"):
    """
    Run scrape_ddm_news() at a specific time of day (default: 03:00 AM US West Coast time).
    """
    from datetime import datetime, timedelta

    tz = pytz.timezone(timezone)
    while True:
        now = datetime.now(tz)
        next_run = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
        if now >= next_run:
            next_run += timedelta(days=1)
        wait_seconds = (next_run - now).total_seconds()
        print(f"Waiting {wait_seconds/60:.1f} minutes until next scrape at {next_run.isoformat()}")
        await asyncio.sleep(wait_seconds)
        await scrape_ddm_news()
        # scrape activities
        

@app.get("/posts")
def get_posts(
    offset: Optional[int] = Query(0, ge=0, description="Number of posts to skip"),
    limit: Optional[int] = Query(10, ge=1, le=100, description="Maximum number of posts to return")
):
    """
    Get posts with pagination support.
    
    Parameters:
    - offset: Number of posts to skip (default: 0)
    - limit: Maximum number of posts to return (default: 10, max: 100)
    
    Returns:
    - A dictionary containing:
        - posts: List of posts
        - total: Total number of posts available
        - offset: Current offset
        - limit: Current limit
        - has_more: Whether there are more posts available
        - last_updated: Timestamp of last successful update
    """
    if not latest_posts:
        return {
            "posts": [],
            "total": 0,
            "offset": offset,
            "limit": limit,
            "has_more": False,
            "last_updated": None
        }
    
    # Calculate pagination
    total = len(latest_posts)
    safe_offset = offset if offset is not None else 0
    safe_limit = limit if limit is not None else 10
    end = min(safe_offset + safe_limit, total)
    posts = latest_posts[safe_offset:end]
    has_more = end < total
    
    # Get last update time from archive directory
    last_updated = None
    try:
        archive_files = sorted(ARCHIVE_DIR.glob("posts_*.json"), reverse=True)
        if archive_files:
            # Extract timestamp from filename
            timestamp = archive_files[0].stem.split('_')[1]
            last_updated = datetime.strptime(timestamp, "%Y%m%d").isoformat()
    except Exception as e:
        print(f"Error getting last update time: {str(e)}")
    
    return {
        "posts": posts,
        "total": total,
        "offset": offset,
        "limit": limit,
        "has_more": has_more,
        "last_updated": last_updated
    } 


