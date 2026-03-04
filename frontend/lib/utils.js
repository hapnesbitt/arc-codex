// Filename: /frontend/lib/utils.js
// ✅ UNIFIED SOURCE OF TRUTH

import { clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs) {
  return twMerge(clsx(inputs));
}

// Slugify function remains unchanged
export const slugify = (text = '') => {
  const a = 'àáâäæãåāăąçćčđďèéêëēėęěğǵḧîïíīįìłḿñńǹňôöòóœøōõőṕŕřßśšşșťțûüùúūǘůűųẃẍÿýžźż·/_,:;';
  const b = 'aaaaaaaaaacccddeeeeeeeegghiiiiiilmnnnnoooooooooprrssssssttuuuuuuuuuwxyyzzz------';
  const p = new RegExp(a.split('').join('|'), 'g');
  return text.toString().toLowerCase()
    .replace(/\s+/g, '-')
    .replace(p, c => b.charAt(a.indexOf(c)))
    .replace(/&/g, '-and-')
    .replace(/[^\w\-]+/g, '')
    .replace(/\-\-+/g, '-')
    .replace(/^-+/, '')
    .replace(/-+$/, '');
};

// ✅ THE NEW CONSTITUTION: allDirectives is now the single source of truth for everything.
export const allDirectives = [
  {
    slug: "world-affairs-and-governance",
    displayName: "World Affairs & Governance",
    blue_directives: [{ name: "Geopolitical Strategy & Statecraft" }],
    red_directives: [{ name: "Abuse of Power & Institutional Decay" }]
  },
  {
    slug: "climate-and-environment",
    displayName: "Climate & Environment",
    blue_directives: [{ name: "Oceanic & Earth Systems" }],
    red_directives: [{ name: "Natural Disasters & Ecological Collapse" }]
  },
  {
    slug: "economics-and-wealth",
    displayName: "Economics & Wealth",
    blue_directives: [{ name: "Macroeconomics & Capital Flows" }],
    red_directives: [{ name: "Systemic Financial Risk & Inequality" }]
  },
  {
    slug: "culture-and-truth",
    displayName: "Culture & Truth",
    blue_directives: [{ name: "Arts, Culture, & The Pursuit of Knowledge" }],
    red_directives: [{ name: "Propaganda & The Corruption of Truth" }]
  },
  {
    slug: "nature-and-conservation",
    displayName: "Nature & Conservation",
    blue_directives: [{ name: "Ecology & Conservation" }],
    red_directives: [{ name: "Resource Scarcity & Environmental Conflict" }]
  },
  {
    slug: "governance-and-innovation",
    displayName: "Governance & Innovation",
    blue_directives: [{ name: "Strategic Governance & Civic Innovation" }],
    red_directives: [{ name: "Systemic Stagnation & Flawed Incentives" }]
  },
  {
    slug: "conflict-and-resolution",
    displayName: "Conflict & Resolution",
    blue_directives: [{ name: "Military Strategy & Conflict Resolution" }],
    red_directives: [{ name: "Escalation & Unconventional Warfare" }]
  },
  {
    slug: "technology-and-engineering",
    displayName: "Technology & Engineering",
    blue_directives: [{ name: "Engineering & Technological Progress" }],
    red_directives: [{ name: "Technological Risk & Unintended Consequences" }]
  },
  {
    slug: "networks-and-communication",
    displayName: "Networks & Communication",
    blue_directives: [{ name: "Networks & Systems Thinking" }],
    red_directives: [{ name: "Information Warfare & Systemic Manipulation" }]
  },
  {
    slug: "social-bonds-and-culture",
    displayName: "Social Bonds & Culture",
    blue_directives: [{ name: "Social Dynamics & Human Connection" }],
    red_directives: [{ name: "Social Fragmentation & Alienation" }]
  },
  {
    slug: "chaos-and-emergence",
    displayName: "Chaos & Emergence",
    blue_directives: [{ name: "Emergence & Spontaneous Order" }],
    red_directives: [{ name: "Mass Hysteria & Irrationality" }]
  },
  {
    slug: "sustainability-and-food-systems",
    displayName: "Sustainability & Food Systems",
    blue_directives: [{ name: "Sustainability & Food Systems" }],
    red_directives: [{ name: "Famine & Systemic Neglect" }]
  }
];
