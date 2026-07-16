import os
import qrcode
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER
from reportlab.lib import colors

# =========================
# CONFIG & DATA
# =========================
QR_FOLDER = "plantorium_qrcodes"
os.makedirs(QR_FOLDER, exist_ok=True)

# Master list: (Common Name, Latin Name, URL)
# The static domain line is replaced by the authentic botanical nomenclature
ALL_PLANTS = [
    # A Plants
    ("Agastache", "Agastache foeniculum", "https://arc-codex.com/article/438d88c46b1c4c761e3c68e99778a8d0"),
    ("Ageratum", "Ageratum houstonianum", "https://arc-codex.com/article/d0486fc67b87d3734be007d898fe9766"),
    ("Alyssum", "Lobularia maritima", "https://arc-codex.com/article/178914b261d3fc5c7f841bf798a1ff0e"),
    ("Amaranth", "Amaranthus cruentus", "https://arc-codex.com/article/4690b39228368549b91cbcf3d0093fad"),
    ("Angelonia", "Angelonia angustifolia", "https://arc-codex.com/article/0bfd85d397f3aab43d5bdce0cf6193f5"),
    ("Argyranthemum", "Argyranthemum frutescens", "https://arc-codex.com/article/ba16821437e05a3b85ecedc2fc1f140e"),
    ("Asparagus Fern", "Asparagus densiflorus", "https://arc-codex.com/article/417adc5ee3c3666413885dc17c2f7090"),
    
    # B Plants
    ("Bacopa", "Sutera cordata", "https://arc-codex.com/article/1601b787cc324690619e6c23323590b9"),
    ("Banana (Musa)", "Musa acuminata", "https://arc-codex.com/article/5588648c764ab3cb7031382ebc980710"),
    ("Begonia Fibrous", "Begonia semperflorens", "https://arc-codex.com/article/1f4996b5fc9e5588129fc0f81f965771"),
    ("Begonia Trailing", "Begonia x tuberhybrida", "https://arc-codex.com/article/8479931d72eb38b1944bbe1faec21dac"),
    ("Begonia Upright", "Begonia boliviensis", "https://arc-codex.com/article/610410d050b4b2804ef8d111839938c1"),
    ("Bidens", "Bidens ferulifolia", "https://arc-codex.com/article/e2d326097107c35b26dd27211e9b39c7"),
    
    # C, D, and E Plants
    ("Caladium", "Caladium bicolor", "https://arc-codex.com/article/9faf2520bd8e292c65878aa5c60960a7"),
    ("Calibrachoa", "Calibrachoa x hybrida", "https://arc-codex.com/article/3ad9a904ebe69572ba85dba2e590fcda"),
    ("Canna Lilies", "Canna indica", "https://arc-codex.com/article/a121020cb3d1b24405560c7eb3670897"),
    ("Celosia", "Celosia argentea", "https://arc-codex.com/article/50958ba4d1ab35a0792b2454c72a10cc"),
    ("Coleus", "Plectranthus scutellarioides", "https://arc-codex.com/article/341df8765db1a202b1a0af7ff9b61aad"),
    ("Cordyline", "Cordyline fruticosa", "https://arc-codex.com/article/dd2ea5684890fe537933f8db1cce9c96"),
    ("Cosmos", "Cosmos bipinnatus", "https://arc-codex.com/article/d5b9b2684f209a03b2518e77d9161570"),
    ("Dahlia", "Dahlia pinnata", "https://arc-codex.com/article/7615e54ffd65a0499e96c3816af08d14"),
    ("Dianthus", "Dianthus caryophyllus", "https://arc-codex.com/article/0cef4b1c4c76217ae57ef311b3d14936"),
    ("Dorotheanthus", "Dorotheanthus bellidiformis", "https://arc-codex.com/article/31c131c497498df832f2e3702e9fd0a2"),
    ("Dracaena", "Dracaena reflexa", "https://arc-codex.com/article/5b52103cb938bc164dca879076e2e77b"),
    ("Dusty Miller", "Jacobaea maritima", "https://arc-codex.com/article/5a18d8e0bcc1eab1bbb5b0b5e62ba856"),
    ("Elephant Ear", "Colocasia esculenta", "https://arc-codex.com/article/fe4d17b603daa66e8f17bf26465f8bb5"),
    ("Decorative Eucalyptus", "Eucalyptus globulus", "https://arc-codex.com/article/b93885b5b7646da838aa904be1c3654a"),
    
    # F, G, H, and I Plants
    ("Felicia", "Felicia amelloides", "https://arc-codex.com/article/16d24398390ff698efb539ce33ef350a"),
    ("Fuchsia Trailing", "Fuchsia magellanica", "https://arc-codex.com/article/eb58dcc7c9ab7387f130d309fafe2778"),
    ("Gaura", "Oenothera lindheimeri", "https://arc-codex.com/article/520b03092c1d4fe69cbff1dfc41798fc"),
    ("Gazania", "Gazania rigens", "https://arc-codex.com/article/53ccc0106840b84b7973060270a6d1d6"),
    ("Geranium", "Pelargonium x hortorum", "https://arc-codex.com/article/3c38b8a68c7d51cd3f8550102fc4b8db"),
    ("Gerbera Daisy", "Gerbera jamesonii", "https://arc-codex.com/article/d6f6d942ff571a20c11e51a86a1bd1f0"),
    ("Gomphrena", "Gomphrena globosa", "https://arc-codex.com/article/ab22739d340deabaf84bf357f41b42ab"),
    ("Heliotropium", "Heliotropium arborescens", "https://arc-codex.com/article/47c9560492d0d6bf34caeac1f84a2672"),
    ("Hypoestes", "Hypoestes phyllostachya", "https://arc-codex.com/article/ab2a3e812604c1a00cbfd27269f8bb13"),
    
    # J to Z Plants
    ("Impatiens", "Impatiens walleriana", "https://arc-codex.com/article/1d26ea242e1bd2d10c267b522eafad8c"),
    ("SunPatiens Compact", "Impatiens x hawkeri", "https://arc-codex.com/article/b13bd46c257f791919fe498a68899d54"),
    ("Sweet Potato Vine", "Ipomoea batatas", "https://arc-codex.com/article/33fe31e6a124f291853361775e79bb57"),
    ("Juncus", "Juncus effusus", "https://arc-codex.com/article/275403ad637f88fd4e5dc26ff82a822c"),
    ("Lantana", "Lantana camara", "https://arc-codex.com/article/e14f7d174f374c7f90d6ed758fdd7dd5"),
    ("Lobelia", "Lobelia erinus", "https://arc-codex.com/article/850aca9e489ece8e7c671f6c472da286"),
    ("Trailing Alyssum", "Lobularia maritima var.", "https://arc-codex.com/article/0f9afe6fc4b4f8c755d87b810983651a"),
    ("Lysimachia", "Lysimachia nummularia", "https://arc-codex.com/article/f1172c5835035f7981386216273eac54"),
    ("Marigold", "Tagetes patula", "https://arc-codex.com/article/2aec5801f5b1418fc034db9437a49937"),
    ("Millet", "Pennisetum glaucum", "https://arc-codex.com/article/f1ebf061b4b20ab083dd090b503129de"),
    ("Nemesia", "Nemesia strumosa", "https://arc-codex.com/article/a31ded7ef98e05eba60edee83c2fdd68"),
    ("Nicotiana", "Nicotiana alata", "https://arc-codex.com/article/eae57105a61fb8cf355cd3b622498ad1"),
    ("Sunscape Daisy", "Osteospermum ecklonis", "https://arc-codex.com/article/4bb5ea29422ea46b9ff41743e50a784c"),
    ("Shrimp Plant", "Justicia brandegeeana", "https://arc-codex.com/article/6efb434812bf54c1b6288808c9e8a127"),
    ("Pansies", "Viola x wittrockiana", "https://arc-codex.com/article/e53ad8fae6d8fbd301281ed899de3e31"),
    ("Pentas", "Pentas lanceolata", "https://arc-codex.com/article/ff062b0342ad33f3e1e2fb93e463583e"),
    ("Mound/Trail Petunia", "Petunia x hybrida (Mound)", "https://arc-codex.com/article/5954363d87919e4ee919f37685224e0f"),
    ("Trailing Petunia", "Petunia x hybrida (Trail)", "https://arc-codex.com/article/1d7527633cef22d5e2f25b7b95285b6c"),
    ("Grandiflora Petunia", "Petunia x hybrida (Grand)", "https://arc-codex.com/article/5cd8fe38d4a37d674ce9e3eddab62669"),
    ("Annual Phlox", "Phlox drummondii", "https://arc-codex.com/article/895860bf6958d8634396b5418ba60657"),
    ("Plectranthus", "Plectranthus amboinicus", "https://arc-codex.com/article/11e5b1759d4948a64d9c010cbd272da2"),
    ("Moss Rose", "Portulaca grandiflora", "https://arc-codex.com/article/d79c5ffa93fe29878412a6d643b7e7e8"),
    ("Pink Mulla Mulla", "Ptilotus exaltatus", "https://arc-codex.com/article/d563a13e3ee25e14f24be776f3f50dbf"),
    ("Rudbeckia", "Rudbeckia hirta", "https://arc-codex.com/article/1286dfb786b77b9faac27b832f787ebf"),
    ("Salvia", "Salvia officinalis", "https://arc-codex.com/article/d28b2259e0c43cb3e6286cadb32a9a94"),
    ("Mealycup Sage", "Salvia farinacea", "https://arc-codex.com/article/2e375c99ba40b0e168a9e09cf76a8cae"),
    ("Salvia Splendens", "Salvia splendens", "https://arc-codex.com/article/31593836f364a49b97a607ae1dfb7af5"),
    ("Senecio", "Senecio cineraria", "https://arc-codex.com/article/f34d4aae0d91dcd77dbaa97da3ae4fa7"),
    ("Purple Heart", "Tradescantia pallida", "https://arc-codex.com/article/1852b99d1ab375a4a6e976824ee00095"),
    ("Snapdragon", "Antirrhinum majus", "https://arc-codex.com/article/be796dcc46f3996a04b84856ea351fe7"),
    ("Stock", "Matthiola incana", "https://arc-codex.com/article/2c21679c935881725e87a89202b14a19"),
    ("Trailing Verbena", "Verbena x hybrida (Trail)", "https://arc-codex.com/article/a4bd5535d3244a7f32eaa77bf28bdb70"),
    ("Upright Verbena", "Verbena x hybrida (Upright)", "https://arc-codex.com/article/81d82a5da956bde54e03693db223ac62"),
    ("Vinca Vine", "Vinca major", "https://arc-codex.com/article/cae9c8103d2a32083281bb8791fff5cf"),
    ("Viola", "Viola cornuta", "https://arc-codex.com/article/d8c3b691cdb6952f783278a563265008"),
    ("Zinnia", "Zinnia elegans", "https://arc-codex.com/article/471d2c8db23fc93754cdd6e345ad0cfb"),
]

# =========================
# STYLES & HELPERS
# =========================
styles = getSampleStyleSheet()
label_style = ParagraphStyle("label", parent=styles['Normal'], fontSize=9, fontName='Helvetica-Bold', alignment=TA_CENTER)
# Latin names styled in italics per standard botanical formatting rules
latin_style = ParagraphStyle("latin", parent=styles['Normal'], fontSize=7.5, fontName='Helvetica-Oblique', alignment=TA_CENTER, textColor=colors.darkgrey)

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
    """Builds an isolated mini-table for a single 3x3 card with standard botanical pairing."""
    qr_path = create_qr(name, url)
    
    # Balanced vertical layout maintaining the strict height budget
    cell_data = [
        [Spacer(1, 4)],
        [Image(qr_path, width=1.1*inch, height=1.1*inch)],
        [Spacer(1, 4)],
        [Paragraph(name.upper(), label_style)],
        [Paragraph(latin, latin_style)]
    ]
    
    card_table = Table(cell_data, colWidths=[2.3*inch], rowHeights=[4, 82, 4, 12, 10])
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
    filename = "plantorium_botanical_guide_master.pdf"
    
    doc = SimpleDocTemplate(filename, pagesize=letter, 
                            rightMargin=36, leftMargin=36, 
                            topMargin=72, bottomMargin=72)
    story = []
    
    # Process dataset into strict blocks of exactly 9 cards per layout sheet
    for i in range(0, len(ALL_PLANTS), 9):
        chunk = ALL_PLANTS[i:i+9]
        page_cards = []
        
        for name, latin, url in chunk:
            card_cell = build_card_cell(name, latin, url)
            page_cards.append(card_cell)
            
        # Pad remaining spaces on the final page to keep grid lines intact
        while len(page_cards) < 9:
            page_cards.append("")
            
        # Map elements cleanly into a 3x3 grid wireframe
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
    print(f"Successfully generated {filename} with 3x3 arrays over exactly 8 pages.")

if __name__ == "__main__":
    generate_master_pdf()