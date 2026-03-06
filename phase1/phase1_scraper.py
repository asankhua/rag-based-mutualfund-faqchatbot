#!/usr/bin/env python3
"""
Phase 1 Scraper for RAG-Based Mutual Fund FAQ Chatbot

This module scrapes mutual fund data from INDMoney URLs and saves
canonical JSON representations for downstream processing.
"""

import json
import re
import os
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright


# Allowlisted URLs for the 8 HDFC mutual funds
ALLOWLISTED_URLS = [
    "https://www.indmoney.com/mutual-funds/hdfc-flexi-cap-fund-direct-plan-growth-option-3184",
    "https://www.indmoney.com/mutual-funds/hdfc-small-cap-fund-direct-growth-option-3580",
    "https://www.indmoney.com/mutual-funds/hdfc-nifty-midcap-150-index-fund-direct-growth-1043788",
    "https://www.indmoney.com/mutual-funds/hdfc-mid-cap-fund-direct-plan-growth-option-3097",
    "https://www.indmoney.com/mutual-funds/hdfc-banking-financial-services-fund-direct-growth-1006661",
    "https://www.indmoney.com/mutual-funds/hdfc-defence-fund-direct-growth-1043873",
    "https://www.indmoney.com/mutual-funds/hdfc-nifty-private-bank-etf-1042349",
    "https://www.indmoney.com/mutual-funds/hdfc-focused-fund-direct-plan-growth-option-2795",
]


def extract_scheme_id_from_url(url: str) -> str:
    """Extract scheme ID from the URL path."""
    parsed = urlparse(url)
    path_parts = parsed.path.strip("/").split("/")
    if len(path_parts) >= 2 and path_parts[0] == "mutual-funds":
        return path_parts[1]
    raise ValueError(f"Could not extract scheme_id from URL: {url}")


def extract_scheme_name(soup: BeautifulSoup) -> str:
    """Extract the scheme name from the page."""
    # Try to find the main heading
    h1 = soup.find("h1")
    if h1:
        return h1.get_text(strip=True)
    
    # Try meta tags
    meta_title = soup.find("meta", property="og:title")
    if meta_title and meta_title.get("content"):
        return meta_title["content"]
    
    # Fallback to title tag
    title = soup.find("title")
    if title:
        return title.get_text(strip=True).split("|")[0].strip()
    
    return "Unknown Scheme"


def extract_nav(soup: BeautifulSoup) -> Dict[str, Any]:
    """Extract NAV and date information."""
    nav_data = {"value": None, "date": None}
    
    # Look for NAV patterns in the page
    nav_patterns = [
        r"NAV.*?(₹[\d,]+\.?\d*)",
        r"₹([\d,]+\.?\d*)\s*as on",
        r"NAV\s*₹?\s*([\d,]+\.?\d*)",
    ]
    
    # Search in the entire page text
    page_text = soup.get_text()
    
    for pattern in nav_patterns:
        match = re.search(pattern, page_text, re.IGNORECASE)
        if match:
            nav_data["value"] = match.group(1) if "₹" in match.group(1) else f"₹{match.group(1)}"
            break
    
    # Look for NAV date
    date_pattern = r"as on\s+(\d{1,2}\s+[A-Za-z]+\s+\d{4})"
    date_match = re.search(date_pattern, page_text, re.IGNORECASE)
    if date_match:
        nav_data["date"] = date_match.group(1)
    
    return nav_data


def extract_returns(soup: BeautifulSoup) -> Dict[str, Any]:
    """Extract returns data (1Y, 3Y, 5Y, Since Inception)."""
    returns = {
        "1y": None,
        "3y": None,
        "5y": None,
        "since_inception": None
    }
    
    page_text = soup.get_text()
    
    # Clean up the text - remove year patterns that might be concatenated with percentages
    # e.g., "202616.69%" -> " 16.69%" 
    cleaned_text = re.sub(r'(\d{4})(\d+\.\d+%)', r' \2', page_text)
    
    # Pattern for returns since inception - look for specific format
    # e.g., "16.69%/per year Since Inception" or "16.69% per year Since Inception"
    inception_patterns = [
        r"(\d+\.\d+)%\s*/?\s*(?:per\s*year|p\.a\.)\s*(?:Since\s*Inception|since\s*inception)",
        r"(?:Since\s*Inception|since\s*inception)\s*:?\s*(\d+\.\d+)%",
        r"Since\s*Inception.*?/(\d+\.\d+)%",
    ]
    
    for pattern in inception_patterns:
        match = re.search(pattern, cleaned_text, re.IGNORECASE | re.DOTALL)
        if match:
            returns["since_inception"] = f"{match.group(1)}%/per year Since Inception"
            break
    
    # Look for 1Y, 3Y, 5Y returns - avoid matching the "Since Inception" line
    return_patterns = [
        (r"1\s*Y(?:ear|r)?\s*(?:return)?\s*:?\s*([+-]?\d+\.\d+)%", "1y"),
        (r"3\s*Y(?:ear|r)?\s*(?:return)?\s*:?\s*([+-]?\d+\.\d+)%", "3y"),
        (r"5\s*Y(?:ear|r)?\s*(?:return)?\s*:?\s*([+-]?\d+\.\d+)%", "5y"),
    ]
    
    for pattern, key in return_patterns:
        match = re.search(pattern, cleaned_text, re.IGNORECASE)
        if match:
            returns[key] = f"{match.group(1)}%"
    
    return returns


def extract_expense_ratio(soup: BeautifulSoup) -> Optional[str]:
    """Extract expense ratio."""
    page_text = soup.get_text()
    
    patterns = [
        r"Expense\s*[Rr]atio\s*-?\s*(\d+\.?\d*)%",
        r"Expense\s*[Rr]atio\s*:?\s*(\d+\.?\d*)%",
    ]
    
    for pattern in patterns:
        match = re.search(pattern, page_text)
        if match:
            return f"{match.group(1)}%"
    
    return None


def extract_benchmark(soup: BeautifulSoup) -> Optional[str]:
    """Extract benchmark information."""
    page_text = soup.get_text()
    
    patterns = [
        r"Benchmark\s*-?\s*([A-Za-z\s\d]+?(?:TR\s*INR|TRI|Index))",
        r"Benchmark\s*:?\s*([A-Za-z\s\d]+?(?:TR\s*INR|TRI|Index))",
    ]
    
    for pattern in patterns:
        match = re.search(pattern, page_text)
        if match:
            return match.group(1).strip()
    
    return None


def extract_aum(soup: BeautifulSoup) -> Optional[str]:
    """Extract AUM (Assets Under Management)."""
    page_text = soup.get_text()
    
    patterns = [
        r"AUM\s*-?\s*₹?\s*([\d,]+(?:\.?\d*)?\s*(?:Cr|Crore))",
        r"AUM\s*:?\s*₹?\s*([\d,]+(?:\.?\d*)?\s*(?:Cr|Crore))",
    ]
    
    for pattern in patterns:
        match = re.search(pattern, page_text, re.IGNORECASE)
        if match:
            return f"₹{match.group(1)}"
    
    return None


def extract_inception_date(soup: BeautifulSoup) -> Optional[str]:
    """Extract fund inception date."""
    page_text = soup.get_text()
    
    patterns = [
        r"Inception\s*[Dd]ate\s*-?\s*(\d{1,2}\s+[A-Za-z]+,?\s+\d{4})",
        r"Inception\s*[Dd]ate\s*:?\s*(\d{1,2}\s+[A-Za-z]+,?\s+\d{4})",
    ]
    
    for pattern in patterns:
        match = re.search(pattern, page_text)
        if match:
            return match.group(1)
    
    return None


def extract_min_investment(soup: BeautifulSoup) -> Dict[str, Any]:
    """Extract minimum lumpsum and SIP investment amounts."""
    min_invest = {"lumpsum": None, "sip": None}
    
    page_text = soup.get_text()
    
    # Pattern for Min Lumpsum/SIP
    patterns = [
        r"Min\s*[Ll]umpsum\s*/\s*SIP\s*-?\s*₹?\s*(\d+)\s*/\s*₹?\s*(\d+)",
        r"Min\s*[Ll]umpsum\s*:?\s*₹?\s*(\d+)",
        r"Minimum\s*[Ll]umpsum\s*:?\s*₹?\s*(\d+)",
        r"Minimum\s*SIP\s*:?\s*₹?\s*(\d+)",
    ]
    
    # Try combined pattern first
    combined_match = re.search(patterns[0], page_text, re.IGNORECASE)
    if combined_match:
        min_invest["lumpsum"] = f"₹{combined_match.group(1)}"
        min_invest["sip"] = f"₹{combined_match.group(2)}"
        return min_invest
    
    # Try individual patterns
    lumpsum_match = re.search(patterns[1], page_text, re.IGNORECASE)
    if lumpsum_match:
        min_invest["lumpsum"] = f"₹{lumpsum_match.group(1)}"
    
    alt_lumpsum = re.search(patterns[2], page_text, re.IGNORECASE)
    if alt_lumpsum and not min_invest["lumpsum"]:
        min_invest["lumpsum"] = f"₹{alt_lumpsum.group(1)}"
    
    sip_match = re.search(patterns[3], page_text, re.IGNORECASE)
    if sip_match:
        min_invest["sip"] = f"₹{sip_match.group(1)}"
    
    return min_invest


def extract_exit_load(soup: BeautifulSoup) -> Optional[str]:
    """Extract exit load information."""
    page_text = soup.get_text()
    
    patterns = [
        r"Exit\s*[Ll]oad\s*-?\s*(\d+\.?\d*%)",
        r"Exit\s*[Ll]oad\s*:?\s*(\d+\.?\d*%)",
    ]
    
    for pattern in patterns:
        match = re.search(pattern, page_text)
        if match:
            return match.group(1)
    
    return None


def extract_lock_in(soup: BeautifulSoup) -> Optional[str]:
    """Extract lock-in period information."""
    page_text = soup.get_text()
    
    patterns = [
        r"Lock\s*[Ii]n\s*-?\s*(No\s*Lock-in|None|\d+\s*(?:years?|Y))",
        r"Lock\s*[Ii]n\s*:?\s*(No\s*Lock-in|None|\d+\s*(?:years?|Y))",
    ]
    
    for pattern in patterns:
        match = re.search(pattern, page_text, re.IGNORECASE)
        if match:
            result = match.group(1)
            if result.lower() in ["no lock-in", "none"]:
                return "No Lock-in"
            return result
    
    return None


def extract_turnover(soup: BeautifulSoup) -> Optional[str]:
    """Extract portfolio turnover information."""
    page_text = soup.get_text()
    
    patterns = [
        r"Turnover\s*-?\s*(\d+\.?\d*)%",
        r"Turnover\s*:?\s*(\d+\.?\d*)%",
    ]
    
    for pattern in patterns:
        match = re.search(pattern, page_text, re.IGNORECASE)
        if match:
            return f"{match.group(1)}%"
    
    return None


def extract_risk(soup: BeautifulSoup) -> Optional[str]:
    """Extract risk category/riskometer information."""
    page_text = soup.get_text()
    
    patterns = [
        r"Risk\s*-?\s*(Very\s*High\s*Risk|High\s*Risk|Moderate\s*Risk|Low\s*Risk)",
        r"Risk\s*:?\s*(Very\s*High\s*Risk|High\s*Risk|Moderate\s*Risk|Low\s*Risk)",
        r"Riskometer\s*:?\s*(Very\s*High|High|Moderate|Low)",
    ]
    
    for pattern in patterns:
        match = re.search(pattern, page_text, re.IGNORECASE)
        if match:
            risk = match.group(1)
            if "Risk" not in risk:
                risk = f"{risk} Risk"
            return risk
    
    return None


async def fetch_page_with_playwright(url: str) -> str:
    """
    Fetch page content using Playwright browser automation.
    
    Args:
        url: The URL to fetch
        
    Returns:
        HTML content of the page
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
        )
        page = await context.new_page()
        
        try:
            await page.goto(url, wait_until="networkidle", timeout=60000)
            # Wait a bit for any dynamic content to load
            await asyncio.sleep(2)
            content = await page.content()
        finally:
            await browser.close()
        
        return content


async def scrape_fund_data_async(url: str) -> Dict[str, Any]:
    """
    Scrape mutual fund data from an INDMoney URL.
    
    Args:
        url: The INDMoney fund URL to scrape
        
    Returns:
        Dictionary containing structured fund data
    """
    # Validate URL is in allowlist
    if url not in ALLOWLISTED_URLS:
        raise ValueError(f"URL not in allowlist: {url}")
    
    print(f"Scraping: {url}")
    
    # Fetch the page using Playwright
    html_content = await fetch_page_with_playwright(url)
    
    # Parse HTML
    soup = BeautifulSoup(html_content, "lxml")
    
    # Extract scheme ID and name
    scheme_id = extract_scheme_id_from_url(url)
    scheme_name = extract_scheme_name(soup)
    
    # Extract NAV
    nav_data = extract_nav(soup)
    nav_str = None
    if nav_data["value"] and nav_data["date"]:
        nav_str = f"{nav_data['value']} (as on {nav_data['date']})"
    elif nav_data["value"]:
        nav_str = nav_data["value"]
    
    # Extract returns
    returns = extract_returns(soup)
    
    # Extract minimum investment
    min_invest = extract_min_investment(soup)
    min_lumpsum_sip = None
    if min_invest["lumpsum"] and min_invest["sip"]:
        min_lumpsum_sip = f"{min_invest['lumpsum']}/{min_invest['sip']}"
    
    # Build the canonical data structure
    fund_data = {
        "scheme_id": scheme_id,
        "name": scheme_name,
        "source_url": url,
        "overview": {
            "nav": nav_str,
            "returns_since_inception": returns.get("since_inception"),
            "returns_1y": returns.get("1y"),
            "returns_3y": returns.get("3y"),
            "returns_5y": returns.get("5y"),
            "expense_ratio": extract_expense_ratio(soup),
            "benchmark": extract_benchmark(soup),
            "aum": extract_aum(soup),
            "inception_date": extract_inception_date(soup),
            "min_lumpsum": min_invest.get("lumpsum"),
            "min_sip": min_invest.get("sip"),
            "exit_load": extract_exit_load(soup),
            "lock_in": extract_lock_in(soup),
            "turnover": extract_turnover(soup),
            "risk": extract_risk(soup),
        },
        "last_scraped_at": datetime.utcnow().isoformat() + "Z"
    }
    
    return fund_data


def save_fund_data(fund_data: Dict[str, Any], output_dir: str = "data/phase1") -> str:
    """
    Save fund data to a JSON file.
    
    Args:
        fund_data: The fund data dictionary
        output_dir: Directory to save the JSON file
        
    Returns:
        Path to the saved file
    """
    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)
    
    # Build filename from scheme_id
    filename = f"{fund_data['scheme_id']}.json"
    filepath = os.path.join(output_dir, filename)
    
    # Save JSON
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(fund_data, f, indent=2, ensure_ascii=False)
    
    print(f"Saved: {filepath}")
    return filepath


def scrape_fund_data(url: str) -> Dict[str, Any]:
    """
    Synchronous wrapper for scrape_fund_data_async.
    
    Args:
        url: The INDMoney fund URL to scrape
        
    Returns:
        Dictionary containing structured fund data
    """
    return asyncio.run(scrape_fund_data_async(url))


async def scrape_all_funds_async(output_dir: str = "data/phase1") -> list:
    """
    Scrape all allowlisted fund URLs and save their data.
    
    Args:
        output_dir: Directory to save JSON files
        
    Returns:
        List of saved file paths
    """
    saved_files = []
    
    for url in ALLOWLISTED_URLS:
        try:
            fund_data = await scrape_fund_data_async(url)
            filepath = save_fund_data(fund_data, output_dir)
            saved_files.append(filepath)
        except Exception as e:
            print(f"Error scraping {url}: {e}")
    
    return saved_files


def scrape_all_funds(output_dir: str = "data/phase1") -> list:
    """
    Synchronous wrapper for scrape_all_funds_async.
    
    Args:
        output_dir: Directory to save JSON files
        
    Returns:
        List of saved file paths
    """
    return asyncio.run(scrape_all_funds_async(output_dir))


async def main_async():
    """Async main entry point for the scraper."""
    print("Starting Phase 1 Scraper...")
    print(f"Total URLs to scrape: {len(ALLOWLISTED_URLS)}")
    print("-" * 60)
    
    saved_files = await scrape_all_funds_async()
    
    print("-" * 60)
    print(f"Scraping complete. Saved {len(saved_files)} files.")
    
    return saved_files


def main():
    """Main entry point for the scraper."""
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
