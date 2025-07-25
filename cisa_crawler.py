#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CISA News Crawler
Crawl tin tức từ trang chính thức của CISA: https://www.cisa.gov/news-events/news
"""

import requests
import json
import time
import re
import logging
import sys
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from datetime import datetime

# Cấu hình logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('crawler.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

class CISACrawler:
    def __init__(self):
        self.base_url = "https://www.cisa.gov/news-events/news"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        })
        self.articles = []
        self.visited_urls = set()
        
    def get_page_content(self, url, max_retries=3):
        """Lấy nội dung trang web với retry mechanism"""
        for attempt in range(max_retries):
            try:
                logging.info(f"Đang crawl: {url} (lần thử {attempt + 1}/{max_retries})")
                response = self.session.get(url, timeout=30)
                response.raise_for_status()
                logging.info(f"Thành công crawl: {url}")
                return response.text
            except requests.RequestException as e:
                logging.warning(f"Lần thử {attempt + 1} thất bại cho {url}: {e}")
                if attempt < max_retries - 1:
                    time.sleep(5)  # Đợi 5 giây trước khi thử lại
                else:
                    logging.error(f"Tất cả {max_retries} lần thử đều thất bại cho {url}")
                    return None
        return None
    
    def extract_article_links(self, html_content, page_url):
        """Trích xuất các link bài viết từ trang"""
        if not html_content:
            return []
        
        soup = BeautifulSoup(html_content, 'html.parser')
        articles = []
        
        # Tìm các bài viết trong trang CISA - dựa trên cấu trúc thực tế
        # Các bài viết thường có dạng: Apr 01, 2025 Blog Title
        article_elements = soup.find_all(['div', 'article'], class_=re.compile(r'news|article|content|item|entry'))
        
        # Nếu không tìm thấy, thử tìm tất cả link có chứa /news-events/news/
        if not article_elements:
            article_links = soup.find_all('a', href=re.compile(r'/news-events/news/'))
            for link in article_links:
                url = link.get('href')
                if url:
                    absolute_url = urljoin(page_url, url)
                    title = link.get_text(strip=True)
                    if title and len(title) > 10:
                        articles.append({
                            'title': title,
                            'url': absolute_url
                        })
                        logging.info(f"Tìm thấy bài viết: {title}")
        
        # Nếu vẫn không tìm thấy, thử tìm theo pattern khác
        if not articles:
            # Tìm tất cả link có thể là bài viết
            all_links = soup.find_all('a', href=True)
            seen_urls = set()
            
            for link in all_links:
                url = link.get('href')
                if not url:
                    continue
                    
                absolute_url = urljoin(page_url, url)
                
                # Kiểm tra xem có phải là link bài viết không
                if (self.is_article_url(absolute_url) and 
                    absolute_url not in seen_urls and 
                    absolute_url not in self.visited_urls):
                    
                    title = link.get_text(strip=True)
                    if title and len(title) > 10:
                        articles.append({
                            'title': title,
                            'url': absolute_url
                        })
                        seen_urls.add(absolute_url)
                        logging.info(f"Tìm thấy bài viết: {title}")
        
        return articles
    
    def is_article_url(self, url):
        """Kiểm tra xem URL có phải là bài viết không"""
        # URL bài viết CISA thường có dạng /news-events/news/...
        return ('cisa.gov' in url and 
                '/news-events/news/' in url and
                not url.endswith('.pdf') and
                not url.endswith('.doc') and
                not url.endswith('.docx'))
    
    def extract_title(self, link_element, parent_element):
        """Trích xuất tiêu đề bài viết"""
        # Thử tìm tiêu đề trong link
        title = link_element.get_text(strip=True)
        if title and len(title) > 10:
            return title
        
        # Thử tìm tiêu đề trong parent element
        title_elements = parent_element.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
        for title_elem in title_elements:
            title = title_elem.get_text(strip=True)
            if title and len(title) > 10:
                return title
        
        # Thử tìm trong các class có chứa 'title'
        title_elem = parent_element.find(class_=re.compile(r'title|headline'))
        if title_elem:
            title = title_elem.get_text(strip=True)
            if title and len(title) > 10:
                return title
        
        return None
    
    def extract_article_metadata(self, html_content):
        """Trích xuất metadata của bài viết (tác giả, ngày release)"""
        if not html_content:
            return {}, {}
        
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Tìm ngày release
        release_date = ""
        date_selectors = [
            'time',
            '.date',
            '.release-date',
            '.published-date',
            '[datetime]'
        ]
        
        for selector in date_selectors:
            date_elem = soup.select_one(selector)
            if date_elem:
                # Thử lấy từ datetime attribute
                release_date = date_elem.get('datetime', '')
                if not release_date:
                    release_date = date_elem.get_text(strip=True)
                if release_date:
                    break
        
        # Nếu không tìm thấy, thử tìm text chứa "Released"
        if not release_date:
            text_content = soup.get_text()
            released_match = re.search(r'Released\s*([A-Za-z]+\s+\d{1,2},\s+\d{4})', text_content)
            if released_match:
                release_date = released_match.group(1)
        
        # Tìm tác giả
        author = ""
        author_selectors = [
            '.author',
            '.byline',
            '.writer',
            'cite',
            '.author-name'
        ]
        
        for selector in author_selectors:
            author_elem = soup.select_one(selector)
            if author_elem:
                author = author_elem.get_text(strip=True)
                if author:
                    break
        
        # Nếu không tìm thấy, thử tìm text chứa "By"
        if not author:
            text_content = soup.get_text()
            by_match = re.search(r'By\s+([^,]+(?:,\s*[^,]+)*)', text_content)
            if by_match:
                author = by_match.group(1).strip()
        
        return {
            'release_date': release_date,
            'author': author
        }
    
    def extract_article_content(self, html_content):
        """Trích xuất nội dung bài viết"""
        if not html_content:
            return ""
        
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Loại bỏ các element không cần thiết
        for unwanted in soup.find_all(['nav', 'header', 'footer', 'aside', 'script', 'style', 
                                      'noscript', '.navigation', '.sidebar', '.comments', 
                                      '.social-share', '.related-posts']):
            unwanted.decompose()
        
        # Tìm nội dung chính
        content_selectors = [
            'main',
            'article',
            '.content',
            '.post-content',
            '.article-content',
            '.entry-content',
            '#content',
            '.main-content'
        ]
        
        content = ""
        for selector in content_selectors:
            content_elem = soup.select_one(selector)
            if content_elem:
                content = content_elem.get_text(separator='\n', strip=True)
                if len(content) > 200:  # Nội dung phải đủ dài
                    break
        
        # Nếu không tìm thấy, thử lấy toàn bộ body
        if not content or len(content) < 200:
            body = soup.find('body')
            if body:
                content = body.get_text(separator='\n', strip=True)
        
        # Làm sạch nội dung
        if content:
            # Loại bỏ các dòng trống và khoảng trắng thừa
            content = re.sub(r'\n\s*\n', '\n\n', content)
            content = re.sub(r' +', ' ', content)
            content = re.sub(r'\n +', '\n', content)
            # Loại bỏ các dòng quá ngắn (có thể là navigation)
            lines = content.split('\n')
            cleaned_lines = [line.strip() for line in lines if len(line.strip()) > 20]
            content = '\n'.join(cleaned_lines)
        
        return content
    
    def crawl_article(self, article_info):
        """Crawl nội dung một bài viết"""
        url = article_info['url']
        
        if url in self.visited_urls:
            return None
        
        self.visited_urls.add(url)
        
        html_content = self.get_page_content(url)
        if not html_content:
            return None
        
        # Trích xuất metadata (tác giả, ngày release)
        metadata = self.extract_article_metadata(html_content)
        
        # Trích xuất nội dung
        content = self.extract_article_content(html_content)
        
        if not content or len(content) < 100:
            logging.warning(f"Nội dung quá ngắn cho bài viết: {article_info['title']}")
            return None
        
        article_data = {
            'title': article_info['title'],
            'url': url,
            'author': metadata.get('author', ''),
            'release_date': metadata.get('release_date', ''),
            'content': content,
            'crawl_date': datetime.now().isoformat()
        }
        
        logging.info(f"Đã crawl thành công: {article_info['title']} - Tác giả: {metadata.get('author', 'N/A')} - Ngày: {metadata.get('release_date', 'N/A')}")
        return article_data
    
    def get_max_pages(self, html_content):
        """Tìm số trang tối đa từ pagination"""
        if not html_content:
            return 1
        
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Tìm pagination links
        pagination_links = soup.find_all('a', href=re.compile(r'page=\d+'))
        
        max_page = 1
        for link in pagination_links:
            href = link.get('href', '')
            page_match = re.search(r'page=(\d+)', href)
            if page_match:
                page_num = int(page_match.group(1))
                max_page = max(max_page, page_num)
        
        # Nếu không tìm thấy, thử tìm trong text
        if max_page == 1:
            page_text = soup.get_text()
            page_matches = re.findall(r'page\s*(\d+)', page_text, re.IGNORECASE)
            if page_matches:
                max_page = max(int(p) for p in page_matches)
        
        return max_page
    
    def crawl_all_pages(self, max_articles=None, max_pages=None):
        """Crawl tất cả các trang"""
        logging.info("Bắt đầu crawl tất cả các trang...")
        
        # Bắt đầu từ page 1
        page_num = 1
        total_pages = 1  # Mặc định 1 trang, sẽ cập nhật sau
        
        while True:
            if max_articles and len(self.articles) >= max_articles:
                logging.info(f"Đã đạt giới hạn {max_articles} bài viết")
                break
            
            if max_pages and page_num > max_pages:
                logging.info(f"Đã đạt giới hạn {max_pages} trang")
                break
            
            page_url = f"{self.base_url}?page={page_num}"
            html_content = self.get_page_content(page_url)
            
            if not html_content:
                logging.warning(f"Không thể crawl trang {page_num}")
                break
            
            # Trích xuất các link bài viết
            article_links = self.extract_article_links(html_content, page_url)
            
            if not article_links:
                logging.warning(f"Không tìm thấy bài viết nào ở trang {page_num}")
                # Thử kiểm tra xem có phải trang cuối không
                if page_num == 1:
                    logging.error("Không tìm thấy bài viết nào ở trang đầu tiên")
                    break
                else:
                    logging.info(f"Đã đến trang cuối (trang {page_num-1})")
                    break
            
            logging.info(f"Trang {page_num}: Tìm thấy {len(article_links)} bài viết")
            
            # Crawl từng bài viết
            for article_info in article_links:
                if max_articles and len(self.articles) >= max_articles:
                    break
                
                article_data = self.crawl_article(article_info)
                if article_data:
                    self.articles.append(article_data)
                
                # Delay để tránh spam
                time.sleep(1)
            
            # Delay giữa các trang
            time.sleep(2)
            page_num += 1
        
        logging.info(f"Hoàn thành crawl. Tổng số bài viết: {len(self.articles)}")
    
    def save_to_json(self, filename='cisa_news.json'):
        """Lưu kết quả vào file JSON"""
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump({
                    'total_articles': len(self.articles),
                    'crawl_date': datetime.now().isoformat(),
                    'source_url': self.base_url,
                    'articles': self.articles
                }, f, ensure_ascii=False, indent=2)
            
            logging.info(f"Đã lưu {len(self.articles)} bài viết vào {filename}")
        except Exception as e:
            logging.error(f"Lỗi khi lưu file: {e}")
    
    def run(self, max_articles=None, max_pages=None):
        """Chạy crawler"""
        logging.info("=== BẮT ĐẦU CRAWL CISA NEWS ===")
        
        self.crawl_all_pages(max_articles, max_pages)
        self.save_to_json()
        
        logging.info("=== HOÀN THÀNH CRAWL ===")

def main():
    # Xử lý command line arguments
    max_articles = None
    max_pages = None
    
    if len(sys.argv) > 1:
        if '--max' in sys.argv:
            try:
                max_idx = sys.argv.index('--max')
                if max_idx + 1 < len(sys.argv):
                    max_articles = int(sys.argv[max_idx + 1])
            except (ValueError, IndexError):
                pass
        
        if '--pages' in sys.argv:
            try:
                pages_idx = sys.argv.index('--pages')
                if pages_idx + 1 < len(sys.argv):
                    max_pages = int(sys.argv[pages_idx + 1])
            except (ValueError, IndexError):
                pass
    
    crawler = CISACrawler()
    crawler.run(max_articles, max_pages)

if __name__ == "__main__":
    main() 