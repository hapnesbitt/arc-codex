import os
import qrcode
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER
from reportlab.lib import colors

# =========================
# CONFIG & PERENNIAL DATA
# =========================
QR_FOLDER = "plantorium_perennials_qrcodes"
os.makedirs(QR_FOLDER, exist_ok=True)

# Master list for Perennials: (Common Name, Latin Name, URL)
# The first 4 verified rows are locked in below
ALL_PERENNIALS = [
    ("Ajuga", "Ajuga reptans", "https://arc-codex.com/article/9f24d1ad0f4bd2f2d267ca963a62a7d0"),
    ("Cerastium", "Cerastium tomentosum", "https://arc-codex.com/article/0f416dde26e34155e941a16d066384d7"),
    ("Delosperma", "Delosperma cooperi", "https://arc-codex.com/article/67ec198dfdf70495253cd16709a6f25a"),
    ("Galium", "Galium odoratum", "https://arc-codex.com/article/f658f091724f27b7c14fd879bb6d5e93"),
]

# =========================
# STYLES & HELPERS
# =========================
styles = getSampleStyleSheet()
label_style = ParagraphStyle("label", parent=styles['Normal'], fontSize=9, fontName='Helvetica-Bold', alignment=TA_CENTER)
latin_style = ParagraphStyle("latin", parent=styles['Normal'], fontSize=7.5, fontName='Helvetica-Oblique', alignment=TA_CENTER, textColor=colors.darkgrey)
footer_style = ParagraphStyle("footer", parent=styles['Normal'], fontSize=6.5, fontName='Helvetica-Bold', alignment=TA_CENTER, textColor=colors.gray)

def create_qr(name, url):
    """Generates a QR code image for a given URL."""
    slug = name.lower().replace(" ", "_").replace("(", "").replace(")", "").replace("/", "_")
    path = os.path.join(QR_FOLDER, f"qr_{slug}.png")
    
    qr = qrcode.QRCode(version=1, box_size=10, border=1)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    img.save(path)
    return path

def build_card_cell(name, latin, url):
    """Builds an isolated mini-table for a single perennial card with dedicated footer."""
    qr_path = create_qr(name, url)
    
    # Balanced vertical layout incorporating the "PERENNIALS" classification footer
    cell_data = [
        [Spacer(1, 4)],
        [Image(qr_path, width=1.1*inch, height=1.1*inch)],
        [Spacer(1, 3)],
        [Paragraph(name.upper(), label_style)],
        [Paragraph(latin, latin_style)],
        [Spacer(1, 2)],
        [Paragraph("PERENNIALS", footer_style)]
    ]
    
    # Grid dimensions explicitly calibrated to maintain the strict 3x3 blueprint
    card_table = Table(cell_data, colWidths=[2.3*inch], rowHeights=[4, 82, 3, 12, 10, 2, 8])
    card_table.setStyle(TableStyle([
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
        ('TOPPADDING', (0,0), (-1,-1), 0),
        ('BOTTOMPADDING', (0,0), (-1,-1), 0),
    ]))
    return card_table

def generate_master_pdf():
    filename = "plantorium_perennials_master.pdf"
    
    doc = SimpleDocTemplate(filename, pagesize=letter, 
                            rightMargin=36, leftMargin=36, 
                            topMargin=72, bottomMargin=72)
    story = []
    
    # Group array items into uniform batches of 9 for grid placement
    for i in range(0, len(ALL_PERENNIALS), 9):
        chunk = ALL_PERENNIALS[i:i+9]
        page_cards = []
        
        for name, latin, url in chunk:
            card_cell = build_card_cell(name, latin, url)
            page_cards.append(card_cell)
            
        # Maintain wireframe structure on final incomplete pages
        while len(page_cards) < 9:
            page_cards.append("")
            
        grid_data = [
            [page_cards[0], page_cards[1], page_cards[2]],
            [page_cards[3], page_cards[4], page_cards[5]],
            [page_cards[6], page_cards[7], page_cards[8]]
        ]
        
        master_table = Table(grid_data, colWidths=[2.45*inch]*3, rowHeights=[2.9*inch]*3)
        master_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ]))
        
        story.append(master_table)
        story.append(PageBreak())
        
    doc.build(story)
    print(f"Successfully generated {filename} with 3x3 perennial cards.")

if __name__ == "__main__":
    generate_master_pdf()