import requests
from bs4 import BeautifulSoup
import json
import time
import re
from urllib.parse import urljoin

class SriLankaMediaScraper:
    def __init__(self, base_url):
        self.base_url = base_url
        self.session = requests.Session()
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        }
        self.companies = []
    
    def fetch_page(self, url):
        """Fetch a page and return BeautifulSoup object."""
        try:
            response = self.session.get(url, headers=self.headers)
            response.raise_for_status()
            return BeautifulSoup(response.text, 'html.parser')
        except Exception as e:
            print(f"Error fetching {url}: {e}")
            return None
    
    def get_company_links(self):
        """Get links to all company detail pages."""
        soup = self.fetch_page(self.base_url)
        if not soup:
            return []
        
        links = []
        # Looking for links that point to company detail pages
        company_links = soup.select('a[href*="/owners/companies/detail/"]')
        
        for link in company_links:
            if 'href' in link.attrs:
                full_url = urljoin(self.base_url, link['href'])
                if full_url not in links:
                    links.append(full_url)
        
        return links
    
    def scrape_company(self, url):
        """Scrape data for a single company."""
        soup = self.fetch_page(url)
        if not soup:
            return None
        
        company_data = {
            "name": "",
            "description": "",
            "key_facts": {},
            "ownership": [],
            "media_outlets": [],
            "other_media_outlets": {
                "print": [],
                "online": []
            },
            "urls": [],
            "source_url": url
        }
        
        # Extract company name
        name_element = soup.select_one('h1')
        if name_element:
            company_data["name"] = name_element.text.strip()
        
        # Extract description
        description_paras = []
        current_element = name_element.find_next_sibling() if name_element else None
        
        while current_element and current_element.name in ['p']:
            if current_element.text.strip():
                description_paras.append(current_element.text.strip())
            current_element = current_element.find_next_sibling()
        
        if description_paras:
            company_data["description"] = ' '.join(description_paras)
        
        # Extract key facts (Business Form, Legal Form, Business Sectors)
        key_facts_section = soup.find('h2', string=lambda s: s and 'Key facts' in s)
        if key_facts_section:
            # Try to find dt/dd pairs
            terms = soup.select('dt')
            for term in terms:
                key = term.text.strip()
                value_elem = term.find_next('dd')
                if value_elem:
                    value = value_elem.text.strip()
                    company_data["key_facts"][key] = value
            
            # If no dt/dd pairs, try to find key-value pairs in table rows
            if not company_data["key_facts"]:
                rows = soup.select('tr')
                for row in rows:
                    cells = row.find_all(['th', 'td'])
                    if len(cells) >= 2:
                        key = cells[0].text.strip()
                        value = cells[1].text.strip()
                        if key and value:
                            company_data["key_facts"][key] = value
        
        # Extract ownership information
        ownership_section = soup.find('h2', string=lambda s: s and 'Ownership' in s)
        if ownership_section:
            # Find elements containing ownership information
            # Based on the sample, ownership info appears to be organized in sections
            ownership_blocks = []
            current_element = ownership_section.find_next_sibling()
            
            while current_element and current_element.name != 'h2':
                # Looking for sections that might contain ownership info
                # These often have headings or percentage indicators
                if current_element.find(string=lambda s: s and '%' in s) or current_element.find(['h3', 'h4', 'strong']):
                    ownership_blocks.append(current_element)
                current_element = current_element.find_next_sibling()
            
            # Process each ownership block
            for block in ownership_blocks:
                owner_data = {}
                
                # Owner name (might be in a heading, strong tag, or specific class)
                name_elem = block.find(['h3', 'h4', 'strong']) or block.select_one('[class*="owner"], [class*="individual"]')
                if name_elem:
                    owner_data["name"] = name_elem.text.strip()
                elif block.select_one('dt'):
                    # Alternative: might be in a definition list
                    name_dt = block.select_one('dt')
                    owner_data["name"] = name_dt.text.strip()
                
                # Description (usually in paragraphs following the name)
                desc_elems = block.find_all('p')
                if desc_elems:
                    owner_data["description"] = ' '.join([p.text.strip() for p in desc_elems])
                
                # Percentage (look for text containing percentage sign)
                percentage_text = block.find(string=lambda s: s and '%' in s)
                if percentage_text:
                    percentage_match = re.search(r'([\d.]+)\s*%', percentage_text.get_text())
                    if percentage_match:
                        owner_data["percentage"] = float(percentage_match.group(1))
                else:
                    # Try to find percentage in specific elements or with specific class
                    percentage_elem = block.select_one('[class*="percent"]')
                    if percentage_elem:
                        percentage_match = re.search(r'([\d.]+)', percentage_elem.text)
                        if percentage_match:
                            owner_data["percentage"] = float(percentage_match.group(1))
                
                if owner_data.get("name"):
                    company_data["ownership"].append(owner_data)
        
        # Extract media outlets
        outlets_section = soup.find('h2', string=lambda s: s and 'Media Outlets' in s)
        if outlets_section:
            # Categories we're looking for
            categories = ["Online", "Print", "Radio", "TV"]
            current_category = None
            
            # Process each element after the "Media Outlets" heading
            current_element = outlets_section.find_next_sibling()
            
            while current_element and current_element.name != 'h2':
                # Check if this element defines a category
                for category in categories:
                    if current_element.find(string=lambda s: s and category in s):
                        current_category = category
                        break
                
                # Look for links which might represent outlets
                links = current_element.find_all('a')
                for link in links:
                    outlet_data = {
                        "name": "",
                        "type": current_category,
                        "url": ""
                    }
                    
                    # Get outlet name (from text, image alt, or other attributes)
                    if link.text.strip():
                        outlet_data["name"] = link.text.strip()
                    elif link.find('img') and link.find('img').get('alt'):
                        outlet_data["name"] = link.find('img').get('alt')
                    
                    # Get URL
                    if 'href' in link.attrs:
                        outlet_url = link['href']
                        outlet_data["url"] = outlet_url
                        if outlet_url not in company_data["urls"]:
                            company_data["urls"].append(outlet_url)
                    
                    if outlet_data.get("name") or outlet_data.get("url"):
                        company_data["media_outlets"].append(outlet_data)
                
                current_element = current_element.find_next_sibling()
        
        # Extract other media outlets
        other_outlets_section = soup.find('h2', string=lambda s: s and 'Other Media Outlets' in s)
        if other_outlets_section:
            # Process print outlets
            print_section = soup.find(string=lambda s: s and 'Other Print Outlets' in s)
            if print_section:
                parent_element = print_section.find_parent()
                current_element = parent_element.find_next_sibling()
                
                while current_element and not current_element.find(string=lambda s: s and 'Other Online Outlets' in s) and current_element.name != 'h2':
                    text_content = current_element.text.strip()
                    if text_content:
                        # Look for pattern: Name (percentage%)
                        match = re.search(r'(.*?)\s*\(([\d.]+)%\)', text_content)
                        if match:
                            outlet_name = match.group(1).strip()
                            percentage = float(match.group(2))
                            company_data["other_media_outlets"]["print"].append({
                                "name": outlet_name,
                                "percentage": percentage
                            })
                        elif text_content and '(missing data)' in text_content:
                            # Handle missing data case
                            outlet_name = text_content.replace('(missing data)', '').strip()
                            company_data["other_media_outlets"]["print"].append({
                                "name": outlet_name,
                                "percentage": None
                            })
                        elif text_content:
                            # Just add the name if no percentage
                            company_data["other_media_outlets"]["print"].append({
                                "name": text_content
                            })
                    
                    current_element = current_element.find_next_sibling()
            
            # Process online outlets
            online_section = soup.find(string=lambda s: s and 'Other Online Outlets' in s)
            if online_section:
                parent_element = online_section.find_parent()
                current_element = parent_element.find_next_sibling()
                
                while current_element and current_element.name != 'h2':
                    for link in current_element.find_all('a'):
                        if 'href' in link.attrs:
                            url = link['href']
                            name = link.text.strip() if link.text.strip() else None
                            
                            company_data["other_media_outlets"]["online"].append({
                                "url": url,
                                "name": name
                            })
                            
                            if url not in company_data["urls"]:
                                company_data["urls"].append(url)
                    
                    current_element = current_element.find_next_sibling()
        
        # Clean up empty data
        for key in list(company_data.keys()):
            if isinstance(company_data[key], (list, dict)) and not company_data[key]:
                del company_data[key]
            elif isinstance(company_data[key], str) and not company_data[key]:
                del company_data[key]
        
        return company_data
    
    def scrape_all_companies(self):
        """Scrape data for all companies."""
        company_links = self.get_company_links()
        
        if not company_links:
            print("No company links found!")
            return False
        
        print(f"Found {len(company_links)} companies to scrape.")
        
        for i, link in enumerate(company_links):
            print(f"Scraping company {i+1}/{len(company_links)}: {link}")
            
            company_data = self.scrape_company(link)
            
            if company_data:
                self.companies.append(company_data)
                print(f"Successfully scraped: {company_data.get('name', 'Unnamed company')}")
            else:
                print(f"Failed to extract data from: {link}")
            
            # Be respectful with a small delay between requests
            time.sleep(2)
        
        return len(self.companies) > 0

    def save_to_json(self, filename="sri_lanka_media_companies.json"):
        """Save the scraped data to a JSON file."""
        output_data = {"companies": self.companies}
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)
        
        print(f"Saved {len(self.companies)} companies to {filename}")
        return filename

# Main execution
if __name__ == "__main__":
    base_url = "https://sri-lanka.mom-gmr.org/en/owners/companies/"
    scraper = SriLankaMediaScraper(base_url)
    
    print("Starting the scraping process...")
    if scraper.scrape_all_companies():
        print("Saving data to JSON...")
        output_file = scraper.save_to_json()
        print(f"Scraping completed successfully! Data saved to {output_file}")
    else:
        print("Scraping failed or no companies were found.")c