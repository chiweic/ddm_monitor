import asyncio
from playwright.async_api import async_playwright
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ENTRY_URL = "https://www.ddm.org.tw/xcevent?xsmsid=0K293423255300198901"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

async def scrape_activities_list():
    activities = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent=USER_AGENT)
        page = await context.new_page()
        
        # Enable request logging
        page.on("request", lambda request: logger.info(f"Request: {request.url}"))
        page.on("response", lambda response: logger.info(f"Response: {response.url} - {response.status}"))
        
        logger.info(f"Navigating to {ENTRY_URL}")
        await page.goto(ENTRY_URL, wait_until="domcontentloaded", timeout=60000)
        # Manually wait for dynamic content (e.g. 5 seconds) so that the page has time to render.
        await page.wait_for_timeout(5000)
        
        # Log the page content for debugging
        content = await page.content()
        logger.info(f"Page content length: {len(content)}")
        
        # Try different selectors
        selectors = [
            "div.timeline-content ul li",
            "ul.timeline li",
            ".timeline li",
            "li.activity-item"
        ]
        
        found_selector = None
        for selector in selectors:
            try:
                logger.info(f"Trying selector: {selector}")
                await page.wait_for_selector(selector, state="attached", timeout=10000)
                found_selector = selector
                break
            except Exception as e:
                logger.warning(f"Selector {selector} not found: {e}")
                continue
        
        if not found_selector:
            logger.error("No working selector found. Saving HTML and screenshot for debugging.")
            # Save HTML and screenshot for debugging
            with open("debug_ddm.html", "w", encoding="utf-8") as f:
                f.write(content)
            await page.screenshot(path="debug_ddm.png", full_page=True)
            await browser.close()
            return activities
            
        logger.info(f"Using selector: {found_selector}")
        items = await page.query_selector_all(found_selector)
        logger.info(f"Found {len(items)} <li> items.")
        
        for li in items:
            try:
                # Title and detail URL
                title_elem = await li.query_selector(".col_left .cont .title a")
                if not title_elem:
                    logger.warning("No title element found for an item")
                    continue
                    
                title = await title_elem.inner_text()
                href = await title_elem.get_attribute("href")
                detail_url = "https://www.ddm.org.tw" + href if href else ""
                
                # Period (date)
                period_elem = await li.query_selector(".col_left .cont .period")
                date = (await period_elem.inner_text() if period_elem else "").replace("～", "–")
                
                # Location
                place_elem = await li.query_selector(".col_right .info .place")
                location = (await place_elem.inner_text() if place_elem else "")
                
                # Tag
                tag_elem = await li.query_selector(".col_left .img span")
                tag = (await tag_elem.inner_text() if tag_elem else "")
                tags = [tag] if tag else []
                
                activity = {
                    "title": title,
                    "detail_url": detail_url,
                    "date": date,
                    "location": location,
                    "tags": tags
                }
                logger.info(f"Successfully parsed activity: {title}")
                activities.append(activity)
                
            except Exception as e:
                logger.error(f"Error parsing activity: {e}")
                continue
                
        await browser.close()
    return activities

# if __name__ == "__main__":
#     async def main():
#         logger.info("Starting scraper...")
#         acts = await scrape_activities_list()
#         logger.info(f"Scraped {len(acts)} activities")
#         for i, act in enumerate(acts, 1):
#             print(f"{i}. {act['title']} | {act['date']} | {act['location']} | {act['tags']} | {act['detail_url']}")
#     asyncio.run(main()) 