import json
import os

SOURCE_FILE = 'backend/sources.json'
OUTPUT_FILE = 'backend/sources_tidy.json'

# Define "Gravity Well" keywords. 
# If a category contains these, it gets pulled into the Super-Category.
gravity_wells = {
    "Technology & AI": ["AI", "Computation", "Programming", "SaaS", "Software"],
    "Intelligence & Security": ["Security", "Threat", "Adversary", "Investigative", "Risk", "Vulnerability"],
    "Governance & Policy": ["Policy", "Regulation", "Legal", "Government"],
    "Luxury Lifestyle": ["Watch", "Yacht", "Automobiles", "Real Estate"],
    "Wine & Gastronomy": ["Wine", "Whisky", "Culinary"]
}

def tidy_tails():
    if not os.path.exists(SOURCE_FILE):
        print("Error: sources.json not found.")
        return

    with open(SOURCE_FILE, 'r') as f:
        data = json.load(f)

    modified_count = 0
    
    for entry in data:
        current_cat = entry.get('category', '')
        
        # Check for gravity matches
        for super_cat, keywords in gravity_wells.items():
            if current_cat == super_cat:
                continue # Already normalized
            
            if any(kw.lower() in current_cat.lower() for kw in keywords):
                entry['category'] = super_cat
                modified_count += 1
                break # Move to next entry once matched

    with open(OUTPUT_FILE, 'w') as f:
        json.dump(data, f, indent=2)

    print(f"Cleanup complete. Collapsed {modified_count} niche categories into Super-Categories.")

if __name__ == "__main__":
    tidy_tails()
