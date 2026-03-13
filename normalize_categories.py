import json
import os

# Define the source file and backup
SOURCE_FILE = 'backend/sources.json'
OUTPUT_FILE = 'backend/sources_normalized.json'

# The Mapping: Old/Specific -> New/Super-Category
category_map = {
    # 🕵️ INVESTIGATIVE & INTEL
    "Investigative & Accountability": "Intelligence & Security",
    "Investigative Journalism & Society": "Intelligence & Security",
    "Investigative": "Intelligence & Security",
    "Intelligence": "Intelligence & Security",
    "Threat Intelligence": "Intelligence & Security",
    "Threat Intelligence Analysis": "Intelligence & Security",
    "Threat Research": "Intelligence & Security",
    "Vulnerability Intelligence": "Intelligence & Security",
    "Cybercrime Intelligence": "Intelligence & Security",
    "Disinformation Intelligence": "Intelligence & Security",

    # 🚜 AGRICULTURE
    "Farming Crisis": "Farming & Agriculture",

    # 💻 TECH & AI
    "Big Tech": "Technology & AI",
    "AI & ML": "Technology & AI",
    "AI & Computing": "Technology & AI",
    "AI & Philosophy": "Technology & AI",
    "AI and Civility": "Technology & AI",
    "Programming": "Technology & AI",
    "Linux & OS": "Technology & AI",
    "Enterprise SaaS": "Technology & AI",
    "Cloud & DevOps": "Technology & AI",
    "Semiconductors": "Deep Tech & Hardware",

    # ⚖️ GOVERNANCE & LEGAL
    "Government and Politics": "Governance & Policy",
    "Politics & Opinion": "Governance & Policy",
    "US Regulation": "Governance & Policy",
    "Global Regulation": "Governance & Policy",
    "UK Regulation": "Governance & Policy",
    "EU Regulation": "Governance & Policy",
    "Asia Regulation": "Governance & Policy",
    "Legal & Judicial": "Governance & Policy",
    "Government Oversight": "Governance & Policy",

    # 🏥 HEALTH
    "Health & Medicine": "Medical & Public Health",
    "Science & Health": "Medical & Public Health",

    # 🍷 LUXURY & CULTURE
    "Men's Luxury": "Luxury Lifestyle",
    "Luxury Travel": "Luxury Lifestyle",
    "Luxury Real Estate": "Luxury Lifestyle",
    "Luxury Automobiles": "Luxury Lifestyle",
    "Luxury Watches": "Luxury Lifestyle",
    "Watch Reviews": "Luxury Lifestyle",
    "Watch News": "Luxury Lifestyle",
    "Wine & Culinary Arts": "Wine & Gastronomy",
    "Wine & Lifestyle": "Wine & Gastronomy",
    "Wine Market": "Wine & Gastronomy",

    # 🌍 GEOPOLITICS (Regional merging)
    "Africa News": "Regional Geopolitics",
    "Oceania News": "Regional Geopolitics",
    "India News": "Regional Geopolitics",
    "Middle East News": "Regional Geopolitics",
    "South America News": "Regional Geopolitics",
    "Latin America News": "Regional Geopolitics",
    "Indonesia News": "Regional Geopolitics",
    "Philippines News": "Regional Geopolitics",
    "Nepal News": "Regional Geopolitics",
    "Bhutan News": "Regional Geopolitics",
    "Bangladesh News": "Regional Geopolitics",
    "Vietnam News": "Regional Geopolitics",
    "UAE News": "Regional Geopolitics",
    "Thailand News": "Regional Geopolitics",
    "Malaysia News": "Regional Geopolitics",
    "Kenya News": "Regional Geopolitics"
}

def normalize():
    if not os.path.exists(SOURCE_FILE):
        print(f"Error: {SOURCE_FILE} not found.")
        return

    with open(SOURCE_FILE, 'r') as f:
        data = json.load(f)

    modified_count = 0
    for entry in data:
        old_cat = entry.get('category')
        if old_cat in category_map:
            entry['category'] = category_map[old_cat]
            modified_count += 1

    with open(OUTPUT_FILE, 'w') as f:
        json.dump(data, f, indent=2)

    print(f"Normalization complete.")
    print(f"Total entries processed: {len(data)}")
    print(f"Entries re-categorized: {modified_count}")
    print(f"Output written to: {OUTPUT_FILE}")

if __name__ == "__main__":
    normalize()
