import os
import re
import pandas as pd
import networkx as nx
from bs4 import BeautifulSoup
from urllib.parse import urlparse, unquote
import logging

# Set up logging
logging.basicConfig(
   level=logging.INFO,
   format='%(asctime)s - %(levelname)s - %(message)s',
   handlers=[
       logging.FileHandler('media_ownership_extraction.log'),
       logging.StreamHandler()
   ]
)

class MediaOwnershipExtractor:
   def __init__(self, html_directory):
       self.html_directory = html_directory
       self.owners = {}
       self.entities = {}  # Companies and media outlets
       self.relationships = []
       self.graph = nx.DiGraph()
       
   def extract_all_data(self):
       """Process all HTML files in the directory"""
       html_files = [f for f in os.listdir(self.html_directory) if f.endswith('.html')]
       logging.info(f"Found {len(html_files)} HTML files to process")
       
       for filename in html_files:
           filepath = os.path.join(self.html_directory, filename)
           try:
               logging.info(f"Processing {filename}")
               with open(filepath, 'r', encoding='utf-8') as file:
                   html_content = file.read()
                   self.process_html_file(html_content, filename)
           except Exception as e:
               logging.error(f"Error processing {filename}: {e}")
               
       # Calculate indirect ownership relationships
       self.calculate_indirect_ownership()
       
       return self.build_network()
   
   def process_html_file(self, html_content, filename):
       """Process a single HTML file and extract owner information"""
       soup = BeautifulSoup(html_content, 'html.parser')
       
       # Extract owner name
       owner_name = self.extract_owner_name(soup)
       owner_id = self.sanitize_id(owner_name)
       
       # Extract owner description
       owner_description = self.extract_owner_description(soup)
       
       # Extract owner image URL
       owner_image = self.extract_owner_image(soup)
       
       # Save owner information
       self.owners[owner_id] = {
           'id': owner_id,
           'name': owner_name,
           'description': owner_description,
           'image_url': owner_image,
           'type': 'owner'
       }
       
       # Add owner as a node to the graph
       self.graph.add_node(owner_id, 
                          name=owner_name, 
                          type='owner', 
                          description=owner_description,
                          image_url=owner_image)
       
       # Extract media companies
       self.extract_media_companies(soup, owner_id)
       
       # Extract media outlets
       self.extract_media_outlets(soup, owner_id)
       
       # Extract family relationships
       self.extract_family_relationships(soup, owner_id, owner_name)
   
   def extract_owner_name(self, soup):
       """Extract the owner name from the HTML"""
       try:
           # Try to get from the h1 with class hl1
           h1_element = soup.find('h1', class_='hl1')
           if h1_element:
               return h1_element.text.strip()
           
           # Try to get from the title
           title = soup.find('title')
           if title:
               # Split by pipe and take first part
               return title.text.split('|')[0].strip()
           
       except Exception as e:
           logging.error(f"Error extracting owner name: {e}")
       
       return "Unknown Owner"
   
   def extract_owner_description(self, soup):
       """Extract the owner description from the HTML"""
       try:
           # Look for the description in the div with class "text"
           text_div = soup.find('div', class_='box').find('div', class_='text')
           if text_div:
               return text_div.text.strip()
       except Exception as e:
           logging.error(f"Error extracting owner description: {e}")
       
       return ""
   
   def extract_owner_image(self, soup):
       """Extract the owner image URL from the HTML"""
       try:
           # Look for the image in the figure with class "media owner"
           figure = soup.find('figure', class_='media owner')
           if figure:
               img = figure.find('img')
               if img and 'src' in img.attrs:
                   return img['src']
       except Exception as e:
           logging.error(f"Error extracting owner image: {e}")
       
       return ""
   
   def extract_media_companies(self, soup, owner_id):
       """Extract media companies owned by the owner"""
       try:
           # Find the Media Companies / Groups section
           companies_section = None
           subtitle_divs = soup.find_all('div', class_='subtitle box')
           
           for div in subtitle_divs:
               span = div.find('span', class_='hl2')
               if span and "Media Companies / Groups" in span.text:
                   companies_section = div.find_next_sibling('div', class_='teaser company')
                   break
           
           if not companies_section:
               return
           
           # Process each company
           companies = soup.find_all('div', class_='teaser company')
           for company in companies:
               self.process_media_company(company, owner_id)
               
       except Exception as e:
           logging.error(f"Error extracting media companies: {e}")
   
   def process_media_company(self, company_div, owner_id):
       """Process a single media company div"""
       try:
           # Extract company URL, name, and ownership percentage
           link = company_div.find('a')
           if not link:
               return
           
           company_url = link.get('href', '')
           
           # Extract company name
           name_element = company_div.find('strong', class_='hl4')
           company_name = name_element.text.strip() if name_element else "Unknown Company"
           company_id = self.sanitize_id(company_name)
           
           # Extract ownership percentage
           percentage_div = company_div.find('div', class_='percentage')
           ownership_percentage = 0
           if percentage_div:
               percentage_text = percentage_div.text.strip().replace('%', '')
               try:
                   ownership_percentage = float(percentage_text)
               except ValueError:
                   ownership_percentage = 0
           
           # Extract image URL
           img = company_div.find('img')
           image_url = img['src'] if img and 'src' in img.attrs else ""
           
           # Add company to entities
           self.entities[company_id] = {
               'id': company_id,
               'name': company_name,
               'type': 'company',
               'image_url': image_url
           }
           
           # Add company as a node to the graph
           self.graph.add_node(company_id,
                              name=company_name,
                              type='company',
                              image_url=image_url)
           
           # Create relationship
           relationship = {
               'source_id': owner_id,
               'target_id': company_id,
               'type': 'owns',
               'percentage': ownership_percentage,
               'description': f"Owns {ownership_percentage}% of {company_name}"
           }
           
           # Add relationship to list and as an edge to the graph
           self.relationships.append(relationship)
           self.graph.add_edge(owner_id, company_id, 
                              type='owns', 
                              percentage=ownership_percentage,
                              description=relationship['description'])
           
       except Exception as e:
           logging.error(f"Error processing media company: {e}")
   
   def extract_media_outlets(self, soup, owner_id):
       """Extract media outlets owned by the owner"""
       try:
           # Find the Media Outlets section
           outlets_section = None
           subtitle_divs = soup.find_all('div', class_='subtitle box')
           
           for div in subtitle_divs:
               span = div.find('span', class_='hl2')
               if span and "Media Outlets" in span.text:
                   outlets_section = div.find_next_sibling('div', class_='teaser company')
                   break
           
           if not outlets_section:
               return
           
           # Process each outlet
           outlets = soup.find_all('div', class_='teaser company')
           for outlet in outlets:
               # Skip if this div is before the outlets section
               if outlet.previous_element and "Media Outlets" not in str(outlet.previous_element):
                   continue
               
               self.process_media_outlet(outlet, owner_id)
               
       except Exception as e:
           logging.error(f"Error extracting media outlets: {e}")
   
   def process_media_outlet(self, outlet_div, owner_id):
       """Process a single media outlet div"""
       try:
           # Extract outlet URL, name, type and ownership percentage
           link = outlet_div.find('a')
           if not link:
               return
           
           outlet_url = link.get('href', '')
           
           # Extract outlet name
           name_element = outlet_div.find('strong', class_='hl4')
           outlet_name = name_element.text.strip() if name_element else "Unknown Outlet"
           outlet_id = self.sanitize_id(outlet_name)
           
           # Extract outlet type (print, radio, TV, online)
           mediatype_div = outlet_div.find('div', class_='mediatype')
           outlet_type = mediatype_div.text.strip() if mediatype_div else "unknown"
           
           # Extract ownership percentage
           percentage_div = outlet_div.find('div', class_='percentage')
           ownership_percentage = 0
           if percentage_div:
               percentage_text = percentage_div.text.strip().replace('%', '')
               try:
                   ownership_percentage = float(percentage_text)
               except ValueError:
                   ownership_percentage = 0
           
           # Extract image URL
           img = outlet_div.find('img')
           image_url = img['src'] if img and 'src' in img.attrs else ""
           
           # Add outlet to entities
           self.entities[outlet_id] = {
               'id': outlet_id,
               'name': outlet_name,
               'type': 'media_outlet',
               'media_type': outlet_type.lower(),
               'image_url': image_url
           }
           
           # Add outlet as a node to the graph
           self.graph.add_node(outlet_id,
                              name=outlet_name,
                              type='media_outlet',
                              media_type=outlet_type.lower(),
                              image_url=image_url)
           
           # Create relationship
           relationship = {
               'source_id': owner_id,
               'target_id': outlet_id,
               'type': 'owns',
               'percentage': ownership_percentage,
               'description': f"Owns {ownership_percentage}% of {outlet_name}"
           }
           
           # Add relationship to list and as an edge to the graph
           self.relationships.append(relationship)
           self.graph.add_edge(owner_id, outlet_id, 
                              type='owns', 
                              percentage=ownership_percentage,
                              description=relationship['description'])
           
       except Exception as e:
           logging.error(f"Error processing media outlet: {e}")
   
   def extract_family_relationships(self, soup, owner_id, owner_name):
       """Extract family relationships"""
       try:
           # Find the Family & Friends section
           family_section = None
           accordeon_items = soup.find_all('div', class_='item')
           
           for item in accordeon_items:
               h3 = item.find('h3', class_='hl3')
               if h3 and "Family & Friends" in h3.text:
                   family_section = item
                   break
           
           if not family_section:
               return
           
           # Find all affiliated interests items
           affiliated_items = family_section.find_all('div', class_='item')
           
           for item in affiliated_items:
               h4 = item.find('h4', class_='hl4')
               if h4 and "Affiliated Interests" in h4.text:
                   text_div = item.find('div', class_='text')
                   if text_div:
                       self.process_family_member(text_div.text, owner_id, owner_name)
                       
           # Also check for 'follow' class items which might contain more family members
           follow_items = family_section.find_all('div', class_='item follow')
           for item in follow_items:
               text_div = item.find('div', class_='text')
               if text_div:
                   self.process_family_member(text_div.text, owner_id, owner_name)
               
       except Exception as e:
           logging.error(f"Error extracting family relationships: {e}")
   
   def process_family_member(self, text, owner_id, owner_name):
       """Process text describing a family member relationship"""
       try:
           # This is a simplistic approach - in a real application, you might want to use NLP
           # to extract names and relationships more accurately
           
           # Extract the name (typically at the beginning of the text before the dash)
           if ' – ' in text:
               parts = text.split(' – ', 1)
               family_member_name = parts[0].strip()
               description = parts[1].strip()
           elif ' - ' in text:
               parts = text.split(' - ', 1)
               family_member_name = parts[0].strip()
               description = parts[1].strip()
           else:
               # No clear separator, try to extract the first sentence as the name
               sentences = text.split('.')
               if sentences:
                   family_member_name = sentences[0].strip()
                   description = text[len(family_member_name):].strip()
               else:
                   return
           
           # Skip if we couldn't extract a name or it's too short
           if not family_member_name or len(family_member_name) < 3:
               return
               
           family_member_id = self.sanitize_id(family_member_name)
           
           # Skip if this is actually the owner
           if family_member_id == owner_id:
               return
           
           # Determine relationship type based on the description text
           relationship_type = 'family_relation'
           if any(term in description.lower() for term in ['wife', 'husband', 'spouse']):
               relationship_type = 'spouse'
           elif any(term in description.lower() for term in ['son', 'daughter', 'child']):
               relationship_type = 'child'
           elif any(term in description.lower() for term in ['brother', 'sister', 'sibling']):
               relationship_type = 'sibling'
           elif any(term in description.lower() for term in ['father', 'mother', 'parent']):
               relationship_type = 'parent'
           
           # Add family member as a node if not already present
           if family_member_id not in self.owners and family_member_id not in self.entities:
               self.owners[family_member_id] = {
                   'id': family_member_id,
                   'name': family_member_name,
                   'description': description,
                   'image_url': '',
                   'type': 'owner'
               }
               
               self.graph.add_node(family_member_id,
                                  name=family_member_name,
                                  type='owner',
                                  description=description,
                                  image_url='')
           
           # Create relationship
           relationship = {
               'source_id': owner_id,
               'target_id': family_member_id,
               'type': relationship_type,
               'percentage': 0,
               'description': description
           }
           
           # Add relationship to list and as an edge to the graph
           self.relationships.append(relationship)
           self.graph.add_edge(owner_id, family_member_id, 
                              type=relationship_type,
                              description=description)
           
       except Exception as e:
           logging.error(f"Error processing family member relationship: {e}")
   
   def calculate_indirect_ownership(self):
       """Calculate indirect ownership relationships"""
       try:
           # Get all direct ownership relationships
           ownership_edges = [(u, v, d) for u, v, d in self.graph.edges(data=True) if d.get('type') == 'owns']
           
           # Create a copy of the graph with only ownership edges
           ownership_graph = nx.DiGraph()
           for u, v, d in ownership_edges:
               ownership_graph.add_edge(u, v, percentage=d.get('percentage', 0))
           
           # Calculate indirect ownership for all pairs of nodes
           for owner_id in self.owners:
               for entity_id in self.entities:
                   # Skip if there's already a direct relationship
                   if ownership_graph.has_edge(owner_id, entity_id):
                       continue
                   
                   # Skip if there's no path between owner and entity
                   if not nx.has_path(ownership_graph, owner_id, entity_id):
                       continue
                   
                   # Check all simple paths from owner to entity
                   indirect_percentage = 0
                   for path in nx.all_simple_paths(ownership_graph, owner_id, entity_id, cutoff=3):
                       # Calculate indirect ownership along this path
                       path_percentage = 100.0
                       for i in range(len(path) - 1):
                           edge_percentage = ownership_graph[path[i]][path[i+1]]['percentage']
                           path_percentage = path_percentage * (edge_percentage / 100.0)
                       
                       # Add to total indirect percentage
                       indirect_percentage += path_percentage
                   
                   # If indirect ownership is significant, add it to the graph
                   if indirect_percentage > 1.0:  # Only include if > 1%
                       entity_name = self.entities[entity_id]['name']
                       self.graph.add_edge(owner_id, entity_id, 
                                         type='indirect_owns', 
                                         percentage=indirect_percentage,
                                         description=f"Indirectly owns {indirect_percentage:.2f}% of {entity_name}")
                       
                       # Add to relationships list
                       relationship = {
                           'source_id': owner_id,
                           'target_id': entity_id,
                           'type': 'indirect_owns',
                           'percentage': indirect_percentage,
                           'description': f"Indirectly owns {indirect_percentage:.2f}% of {entity_name}"
                       }
                       self.relationships.append(relationship)
       except Exception as e:
           logging.error(f"Error calculating indirect ownership: {e}")
   
   def sanitize_id(self, name):
       """Create a valid ID from a name"""
       if not name:
           return "unknown"
       
       # Replace spaces and special chars with underscore
       sanitized = re.sub(r'[^a-zA-Z0-9]', '_', name)
       # Convert to lowercase
       sanitized = sanitized.lower()
       # Remove consecutive underscores
       sanitized = re.sub(r'_+', '_', sanitized)
       # Remove leading and trailing underscores
       sanitized = sanitized.strip('_')
       
       return sanitized
   
   def build_network(self):
       """Build a network representation from the extracted data"""
       # Create a DataFrame for the relationships (edges)
       relationships_df = pd.DataFrame(self.relationships)
       
       # Create an adjacency matrix from the graph
       adj_matrix = nx.to_pandas_adjacency(self.graph, weight='percentage')
       
       # Return graph, adjacency matrix, and relationships DataFrame
       return {
           'graph': self.graph,
           'adjacency_matrix': adj_matrix,
           'relationships': relationships_df,
           'owners': pd.DataFrame(list(self.owners.values())),
           'entities': pd.DataFrame(list(self.entities.values()))
       }

def main(html_directory):
   """Main function to run the extraction process"""
   extractor = MediaOwnershipExtractor(html_directory)
   network_data = extractor.extract_all_data()
   
   # Save data to files
   network_data['adjacency_matrix'].to_csv('media_ownership_adjacency_matrix.csv')
   network_data['relationships'].to_csv('media_ownership_relationships.csv', index=False)
   network_data['owners'].to_csv('media_owners.csv', index=False)
   network_data['entities'].to_csv('media_entities.csv', index=False)
   
   # Save the graph in GraphML format for visualization in tools like Gephi
   nx.write_graphml(network_data['graph'], 'media_ownership_network.graphml')
   
   logging.info(f"Extraction complete. Processed {len(network_data['owners'])} owners and {len(network_data['entities'])} entities.")
   logging.info(f"Found {len(network_data['relationships'])} relationships.")
   
   return network_data

if __name__ == "__main__":
   html_directory = "/path/to/html/files"  # Replace with actual directory path
   network_data = main(html_directory)