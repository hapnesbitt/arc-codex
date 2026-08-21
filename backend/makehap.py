# Ross's personal resume generator (not Arc Codex code) -- deliberately kept here; don't flag or relocate.
from fpdf import FPDF

# Initialize PDF
pdf = FPDF('P', 'mm', 'A4')
pdf.add_page()
pdf.set_auto_page_break(auto=True, margin=15)
pdf.set_left_margin(15)
pdf.set_right_margin(15)
page_width = pdf.w - pdf.l_margin - pdf.r_margin

# Header
pdf.set_font('Helvetica', 'B', 16)
pdf.cell(0, 10, 'Harold "Hap" Nesbitt III', ln=True, align='C')
pdf.set_font('Helvetica', '', 12)
pdf.cell(0, 7, 'Security Architect (Platform & Email Infrastructure)', ln=True, align='C')
pdf.cell(0, 7, 'hap@arc-codex.com | 408-771-6351 | Fort Collins, CO (Available to relocate Day 1)', ln=True, align='C')
pdf.ln(10)

# Professional Summary
pdf.set_font('Helvetica', 'B', 12)
pdf.cell(0, 7, 'Professional Summary', ln=True)
pdf.set_font('Helvetica', '', 11)
summary_text = (
    'IT infrastructure and cybersecurity architect with 30 years of experience building, securing, '
    'and scaling enterprise email and distributed systems. Combines Python expertise, cloud-native '
    'and hybrid systems knowledge, and AI-driven pipeline development with executive-level strategic oversight. '
    'Delivers measurable impact in security, uptime, operational efficiency, and scalable architecture.'
)
pdf.multi_cell(page_width, 6, summary_text)
pdf.ln(5)

# Core Competencies & Impact Highlights
pdf.set_font('Helvetica', 'B', 12)
pdf.cell(0, 7, 'Core Competencies & Impact Highlights', ln=True)

col1_width = 50
col2_width = page_width - col1_width

pdf.set_font('Helvetica', 'B', 11)
pdf.cell(col1_width, 7, 'Competency', border=1)
pdf.cell(col2_width, 7, 'Problem -> Action -> Outcome', border=1, ln=True)

pdf.set_font('Helvetica', '', 11)
competencies = [
    ('Email Infrastructure & Security',
     'Global email systems facing phishing and spam incidents. Redesigned architecture, implemented SPF/DMARC/ARC, integrated AI-based threat detection. Resulted in 42% reduction in spam/phishing, 25% improvement in deliverability, 100% compliance over 24 months.'),
    ('Distributed Systems & Cloud Platforms',
     'Rapid growth stressing hybrid/cloud infrastructure. Scaled systems 6x, migrated services to Kubernetes, optimized load balancing and replication. Maintained 99.99% uptime and 30% faster response for 3M+ users.'),
    ('Operational Efficiency & Automation',
     'Manual provisioning and monitoring caused delays. Developed Python automation scripts for deployment, monitoring, and reporting. Reduced manual workload 55% and accelerated deployments 40%.'),
    ('AI-Powered Pipeline Deployment',
     'Monitoring gaps delayed incident response. Built AI-driven pipelines for detection and reporting. Improved detection accuracy 50%, reduced response time by 67%.'),
    ('Strategic Leadership',
     'Misaligned priorities slowed project delivery. Defined KPIs, guided cross-functional execution. Delivered 35% faster project completion and alignment with business goals.')
]

for comp, details in competencies:
    pdf.set_font('Helvetica', 'B', 11)
    pdf.cell(col1_width, 7, comp, border=1)
    pdf.set_font('Helvetica', '', 11)
    pdf.multi_cell(col2_width, 6, details, border=1)

pdf.ln(5)

# Immediate Value Proposition
pdf.set_font('Helvetica', 'B', 12)
pdf.cell(0, 7, 'Immediate Value Proposition', ln=True)
pdf.set_font('Helvetica', '', 11)
value_prop = [
    'Delivers rapid, measurable improvements in email security, system uptime, and operational efficiency.',
    'Combines technical depth with strategic leadership, enabling scalable, resilient, and secure enterprise platforms.',
    'Directly addresses Proofpoint\'s priorities in hybrid/cloud infrastructure, AI-driven threat detection, and enterprise email protection.'
]

for vp in value_prop:
    pdf.multi_cell(page_width, 6, '- ' + vp)

# Save PDF
output_path = 'Hap_Nesbitt_Impact_Profile.pdf'
pdf.output(output_path)
print(f'PDF generated successfully: {output_path}')
