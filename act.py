#!/usr/bin/env python3
"""
Dynamic AJAX Website Crawler
A comprehensive script for scraping content from AJAX-based websites
"""

import time
import json
import csv
from typing import List, Dict, Optional, Any
from urllib.parse import urljoin, urlparse
import logging

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from bs4 import BeautifulSoup
import requests

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class AjaxCrawler:
    def __init__(self, headless=True, wait_timeout=10):
        """
        Initialize the AJAX crawler
        
        Args:
            headless (bool): Run browser in headless mode
            wait_timeout (int): Default timeout for waiting operations
        """
        self.wait_timeout = wait_timeout
        self.driver = self._setup_driver(headless)
        self.wait = WebDriverWait(self.driver, wait_timeout)
        self.session = requests.Session()
        
    def _setup_driver(self, headless: bool) -> webdriver.Chrome:
        """Setup Chrome WebDriver with optimal settings"""
        options = Options()
        if headless:
            options.add_argument('--headless')
        
        # Performance and stealth options
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1920,1080')
        options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        
        # Disable images and CSS for faster loading (optional)
        # options.add_argument('--disable-images')
        
        return webdriver.Chrome(options=options)
    
    def wait_for_ajax(self, timeout: int = None) -> bool:
        """
        Wait for AJAX requests to complete
        
        Args:
            timeout (int): Custom timeout value
            
        Returns:
            bool: True if AJAX completed, False if timeout
        """
        timeout = timeout or self.wait_timeout
        try:
            WebDriverWait(self.driver, timeout).until(
                lambda driver: driver.execute_script("return jQuery.active == 0") if 
                driver.execute_script("return typeof jQuery != 'undefined'") else True
            )
            return True
        except TimeoutException:
            logger.warning("AJAX requests may still be pending")
            return False
    
    def wait_for_element(self, selector: str, by: By = By.CSS_SELECTOR, timeout: int = None) -> Optional[Any]:
        """
        Wait for element to be present and visible
        
        Args:
            selector (str): Element selector
            by (By): Selenium By method
            timeout (int): Custom timeout
            
        Returns:
            WebElement or None
        """
        timeout = timeout or self.wait_timeout
        try:
            element = WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((by, selector))
            )
            return element
        except TimeoutException:
            logger.warning(f"Element not found: {selector}")
            return None
    
    def scroll_to_load_timeline_content(self, max_items: int = 100, pause_time: float = 3) -> None:
        """
        Scroll specifically within timeline to load more content
        
        Args:
            max_items (int): Stop when this many items are loaded
            pause_time (float): Time to pause between scrolls
        """
        timeline = self.driver.find_element(By.CSS_SELECTOR, 'div.timeline')
        last_count = 0
        scroll_attempts = 0
        max_scroll_attempts = 20
        
        while scroll_attempts < max_scroll_attempts:
            # Count current timeline items
            current_items = len(self.driver.find_elements(By.CSS_SELECTOR, 'div.timeline > *'))
            
            if current_items >= max_items:
                logger.info(f"Reached maximum items limit: {max_items}")
                break
            
            if current_items == last_count and scroll_attempts > 2:
                # No new content loaded, try different scroll strategies
                logger.info("Trying alternative scroll methods...")
                
                # Method 1: Scroll to bottom of timeline div
                self.driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", timeline)
                time.sleep(pause_time)
                
                # Method 2: Scroll page to bottom
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(pause_time)
                
                # Method 3: Scroll to last timeline item
                last_items = self.driver.find_elements(By.CSS_SELECTOR, 'div.timeline > *')
                if last_items:
                    self.driver.execute_script("arguments[0].scrollIntoView();", last_items[-1])
                    time.sleep(pause_time)
                
                # Check if any method worked
                new_count = len(self.driver.find_elements(By.CSS_SELECTOR, 'div.timeline > *'))
                if new_count == current_items:
                    logger.info("No more timeline content to load")
                    break
            else:
                # Regular scroll
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(pause_time)
            
            last_count = current_items
            scroll_attempts += 1
            
            # Wait for any AJAX requests
            self.wait_for_ajax(timeout=5)
            
            logger.info(f"Scroll {scroll_attempts}: Found {current_items} timeline items")
        
        final_count = len(self.driver.find_elements(By.CSS_SELECTOR, 'div.timeline > *'))
        logger.info(f"Timeline scrolling complete. Total items: {final_count}")

    def crawl_timeline(self, url: str, scroll_to_load: bool = True, 
                       max_dates: int = 30, remove_duplicates: bool = True) -> List[Dict]:
        """
        Specifically crawl timeline content from a given URL
        
        Args:
            url (str): URL to crawl
            scroll_to_load (bool): Whether to scroll to load more content
            max_items (int): Maximum items to collect
            remove_duplicates (bool): Whether to remove duplicate items

        Returns:
            List of timeline items
        """
        logger.info(f"Starting timeline crawl for: {url}")
        
        try:
            # Navigate to the page
            self.driver.get(url)
            
            # Wait for initial page load
            time.sleep(2)
            
            # Wait for timeline to appear
            timeline = self.wait_for_element('div.timeline', timeout=15)
            if not timeline:
                logger.error("Timeline div not found on the page")
                return []
            
            # Wait for AJAX to complete
            self.wait_for_ajax()
            
            # Scroll to load more content if needed
            if scroll_to_load:
                logger.info("Scrolling to load timeline content...")
                self.scroll_to_load_timeline_content(max_dates)
            
            # Extract all timeline data
            timeline_data = self.extract_page_data()
            
            logger.info(f"Successfully extracted {len(timeline_data)} timeline items")
            
            # remove duplicate on this list of items
            
            # Remove duplicates while preserving order
            if remove_duplicates:
                seen_links = set()
                unique_timeline_items = []
                for item in timeline_data:
                    link = item.get("link")
                    if link not in seen_links:
                        unique_timeline_items.append(item)
                        seen_links.add(link)
            
                timeline_data = unique_timeline_items
                logger.info(f"Post dup-removal {len(timeline_data)} timeline items")

                return timeline_data
        
            return timeline_data
        
        except Exception as e:
            logger.error(f"Error crawling timeline: {e}")
            return []
    
    def extract_timeline_item(self, element) -> List[Dict]:
        """
        Extract data from a timeline item element
        
        Args:
            element: Selenium WebElement representing a timeline item
            
        Returns:
            Dict: Extracted timeline item data
        """
        try:
            
            item_data = {
                'title': None,
                'period': None,
                'link': None,
                'type': None,
                'place': None,
                'view': None,
                'signup_status': None,
            }
            
            # extract date
            time_selectors = ['.timeline-date']
            for selector in time_selectors:
                time_elem = element.find_elements(By.CSS_SELECTOR, selector)
                if time_elem:
                    logger.info('timeline-date: ' + time_elem[0].text.strip())
                    break
            
            # Extract main content
            content_selectors = ['.timeline-content']
            for selector in content_selectors:
                content_elem = element.find_elements(By.CSS_SELECTOR, selector)
                if content_elem:
                    logger.info('extracting activity that cover this period')
                    item_datas=[]
                    # find all <li>
                    li_elements = content_elem[0].find_elements(By.CSS_SELECTOR, 'li')
                    for li in li_elements:
                        # extract title and period
                        title_elem = li.find_element(By.CSS_SELECTOR, '.title')
                        period_elem = li.find_element(By.CSS_SELECTOR, '.period')
                        link_elem = title_elem.find_element(By.CSS_SELECTOR, 'a')
                        logger.debug('title: ' + title_elem.text.strip())
                        logger.debug(f'period: {period_elem.text.strip()}')
                        # link is at href
                        logger.debug('link: ' + link_elem.get_attribute('href'))
                        # extract type under img on alt
                        type_elem = li.find_element(By.CSS_SELECTOR, 'img').get_attribute('alt')
                        logger.debug('type: ' + type_elem)
                        # place and view under this li
                        place_elem = li.find_element(By.CSS_SELECTOR, '.place')
                        view_elem = li.find_element(By.CSS_SELECTOR, '.view')
                        logger.debug('place: ' + place_elem.text.strip())
                        logger.debug('view: ' + view_elem.text.strip())  
                        # signup status
                        signup_elem = li.find_element(By.CSS_SELECTOR, '.sign_up')
                        if signup_elem:
                            # span class = status
                            status_elem = signup_elem.find_element(By.CSS_SELECTOR, 'span')
                            logger.debug('signup status: ' + status_elem.text.strip())
                        # add to item_datas
                        item_datas.append({
                            'title': title_elem.text.strip(),
                            'period': period_elem.text.strip(),
                            'link': link_elem.get_attribute('href'),
                            'type': type_elem,
                            'place': place_elem.text.strip(),
                            'view': view_elem.text.strip(),
                            'signup_status': status_elem.text.strip() if signup_elem else None
                        })
                    break
            
            
            # Clean up empty values
            for item_data in item_datas:
                item_data = {k: v for k, v in item_data.items() if v}
            
            return item_datas
            
        except Exception as e:
            logger.error(f"Error extracting timeline item data: {e}")
            return []
    
    def handle_pagination(self, next_button_selector: str, max_pages: int = 10) -> List[Dict]:
        """
        Handle paginated content
        
        Args:
            next_button_selector (str): Next page button selector
            max_pages (int): Maximum pages to crawl
            
        Returns:
            List of all extracted data
        """
        all_data = []
        page = 1
        
        while page <= max_pages:
            logger.info(f"Processing page {page}")
            
            # Extract current page data
            page_data = self.extract_page_data()
            all_data.extend(page_data)
            
            # Try to go to next page
            try:
                next_button = self.wait_for_element(next_button_selector)
                if next_button and next_button.is_enabled():
                    self.driver.execute_script("arguments[0].click();", next_button)
                    self.wait_for_ajax()
                    time.sleep(2)
                    page += 1
                else:
                    logger.info("No more pages available")
                    break
            except Exception as e:
                logger.error(f"Error navigating to next page: {e}")
                break
                
        return all_data
    
    def extract_page_data(self) -> List[Dict]:
        """
        Extract data from current page - specifically from timeline div
        
        Returns:
            List of extracted data
        """
        timeline_items = []
        
        # Wait for timeline to load
        timeline = self.wait_for_element('div.timeline')
        if not timeline:
            logger.warning("Timeline div not found")
            return []
        
        # Find all timeline items (common patterns)
        item_selectors = [
            #'div.timeline .timeline-item',
            'div.timeline .item',
            #'div.timeline .post',
            #'div.timeline .entry',
            #'div.timeline > div',
            #'div.timeline li',
            #'div.timeline article'
        ]
        
        items = []
        for selector in item_selectors:
            found_items = self.driver.find_elements(By.CSS_SELECTOR, selector)
            if found_items:
                items = found_items
                logger.info(f"Found {len(items)} timeline items using selector: {selector}")
                break
        
        if not items:
            logger.warning("No timeline items found with common selectors")
            return []
        
        # Extract data from timeline items
        for item in items:
            item_datas = self.extract_timeline_item(item)
            logger.info(f'extract {len(item_datas)} items')
            if item_datas:
                timeline_items.extend(item_datas)
        
        return timeline_items
    
    def intercept_ajax_requests(self, url_pattern: str = None) -> List[Dict]:
        """
        Intercept and capture AJAX requests
        
        Args:
            url_pattern (str): Pattern to filter URLs
            
        Returns:
            List of intercepted requests
        """
        # Enable browser logging
        self.driver.execute_cdp_cmd('Network.enable', {})
        
        # Navigate and wait for requests
        time.sleep(3)
        
        # Get network logs
        logs = self.driver.get_log('performance')
        ajax_requests = []
        
        for log in logs:
            message = json.loads(log['message'])
            if message['message']['method'] == 'Network.responseReceived':
                url = message['message']['params']['response']['url']
                if not url_pattern or url_pattern in url:
                    ajax_requests.append({
                        'url': url,
                        'method': message['message']['params']['response']['mimeType'],
                        'status': message['message']['params']['response']['status']
                    })
        
        return ajax_requests
    
    def crawl_spa(self, base_url: str, routes: List[str]) -> Dict[str, List[Dict]]:
        """
        Crawl Single Page Application with multiple routes
        
        Args:
            base_url (str): Base URL of the SPA
            routes (List[str]): List of routes to crawl
            
        Returns:
            Dict mapping routes to extracted data
        """
        results = {}
        
        for route in routes:
            logger.info(f"Crawling route: {route}")
            full_url = urljoin(base_url, route)
            
            try:
                self.driver.get(full_url)
                self.wait_for_ajax()
                time.sleep(2)
                
                # Extract data for this route
                route_data = self.extract_page_data()
                results[route] = route_data
                
            except Exception as e:
                logger.error(f"Error crawling route {route}: {e}")
                results[route] = []
        
        return results
    
    def save_data(self, data: List[Dict], filename: str, format: str = 'json') -> None:
        """
        Save extracted data to file
        
        Args:
            data: Data to save
            filename: Output filename
            format: Output format ('json' or 'csv')
        """
        if format.lower() == 'json':
            with open(f"{filename}.json", 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        
        elif format.lower() == 'csv' and data:
            with open(f"{filename}.csv", 'w', newline='', encoding='utf-8') as f:
                if data:
                    writer = csv.DictWriter(f, fieldnames=data[0].keys())
                    writer.writeheader()
                    writer.writerows(data)
        
        logger.info(f"Data saved to {filename}.{format}")
    
    def close(self) -> None:
        """Clean up resources"""
        if self.driver:
            self.driver.quit()
        if self.session:
            self.session.close()

# Example usage
def scrape_ddm_activities(max_dates: int = 14):
    """Example of how to use the AjaxCrawler for timeline content"""
    crawler = AjaxCrawler(headless=True)  # Set to False to see browser action
    
    try:
        # Example 1: Basic timeline crawling
        # url = "https://example.com/timeline"
        url = 'https://www.ddm.org.tw/xcevent?xsmsid=0K293423255300198901'

        # set max_items to 2 for debug
        timeline_data = crawler.crawl_timeline(url, scroll_to_load=True, max_dates=max_dates)
        
        if timeline_data:
            
            # Save the timeline data
            crawler.save_data(timeline_data, 'timeline_data', 'json')
            crawler.save_data(timeline_data, 'timeline_data', 'csv')
            
            # Print summary
            print(f"Successfully extracted {len(timeline_data)} timeline items")
            print(f"Sample item: {timeline_data[0] if timeline_data else 'None'}")
        else:
            print("No timeline data found")
        
        # Example 2: Manual timeline extraction (if you're already on the page)
        # crawler.driver.get("https://your-timeline-site.com")
        # crawler.wait_for_element('div.timeline')
        # timeline_items = crawler.extract_page_data()
        # print(f"Found {len(timeline_items)} timeline items")
        
    except Exception as e:
        logger.error(f"Timeline crawling error: {e}")
    
    finally:
        crawler.close()


if __name__ == "__main__":
    scrape_ddm_activities()