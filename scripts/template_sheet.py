"""Fill the supplied household template and export a strictly one-page PDF."""
from datetime import date
from io import BytesIO
from pathlib import Path
import shutil
import subprocess
import tempfile
from zipfile import ZipFile, ZIP_DEFLATED

from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_ROW_HEIGHT_RULE
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt
from lxml import etree
from pypdf import PdfReader

TEMPLATE = Path(__file__).resolve().parents[1]/'templates/weekly-plan.docx'


def template_document():
    # Word accepts decimal twip widths in this uploaded file; python-docx expects
    # integer twips. Normalize these without changing the physical dimensions.
    buffer = BytesIO()
    with ZipFile(TEMPLATE) as original, ZipFile(buffer, 'w', ZIP_DEFLATED) as clean:
        for name in original.namelist():
            value = original.read(name)
            if name == 'word/document.xml':
                xml = etree.fromstring(value)
                for node in xml.iter():
                    for attribute, text in list(node.attrib.items()):
                        if attribute in (qn('w:w'), qn('w:h')):
                            try:
                                node.set(attribute, str(round(float(text))))
                            except ValueError:
                                pass
                value = etree.tostring(xml, xml_declaration=True, encoding='UTF-8', standalone=True)
            clean.writestr(name, value)
    buffer.seek(0)
    return Document(buffer)


def set_cell(cell, lines, size=9, bold_first=False):
    cell.text = ''
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP
    for index, line in enumerate(lines):
        paragraph = cell.paragraphs[0] if index == 0 else cell.add_paragraph()
        paragraph.paragraph_format.space_before = Pt(0)
        paragraph.paragraph_format.space_after = Pt(2)
        paragraph.paragraph_format.line_spacing = 1
        run = paragraph.add_run(line)
        run.font.name = 'Arial'
        run.font.size = Pt(size)
        run.bold = bold_first and index == 0


def shopping_columns(plan, recipes, format_quantity):
    """Each column contains only the ingredients for the dinner directly above it."""
    from planner import day_shopping
    by_id = {r['id']:r for r in recipes}
    columns = [[] for _ in range(7)]
    for meal in plan['meals']:
        recipe = by_id[meal['recipe_id']]
        column = (date.fromisoformat(meal['day']).weekday()+1)%7
        if not meal.get('ingredients_verified', recipe['ingredients_verified']):
            columns[column] = ['DRAFT', 'Ingredients pending verification.']
            continue
        previous = None
        for row in day_shopping(plan,meal,recipe):
            category = 'Pantry check' if row['pantry'] else row['category']
            if category != previous:
                columns[column].append(category.upper())
                previous = category
            columns[column].append(f"[ ] {row['item']} - {format_quantity(row)}")
    return columns


def render_docx(path, plan, recipes, sources, format_quantity, shopping_size=8.5):
    doc = template_document()
    section = doc.sections[0]
    section.bottom_margin = Inches(.4)
    # Remove blank body paragraphs/explicit page breaks from the supplied form.
    body = doc._element.body
    table = doc.tables[0]
    for child in list(body):
        if child.tag == qn('w:p') and not ''.join(child.itertext()).strip():
            body.remove(child)
    title = doc.paragraphs[0]
    title.text = 'Dinner Plan - Week of ' + date.fromisoformat(plan['week_start']).strftime('%B %d, %Y')
    title.paragraph_format.space_after = Pt(7)
    title.paragraph_format.keep_with_next = True
    for run in title.runs:
        run.font.name = 'Arial'
        run.font.size = Pt(20)
    # A minimum row height preserves writing space without clipping long entries.
    for row, height in zip(table.rows, (.3, 1.05, 1.2, 3.5)):
        row.height = Inches(height)
        row.height_rule = WD_ROW_HEIGHT_RULE.AT_LEAST
        props = row._tr.get_or_add_trPr()
        if props.find(qn('w:cantSplit')) is None:
            props.append(OxmlElement('w:cantSplit'))
    # The seven day headings remain aligned with the dinner row.
    for index, day in enumerate(('Day','Sun','Mon','Tues','Weds','Thurs','Fri','Sat')):
        set_cell(table.cell(0,index), [day], size=10, bold_first=index == 0)
        cell = table.cell(0,index)
        shade = OxmlElement('w:shd')
        shade.set(qn('w:fill'),'365E47')
        cell._tc.get_or_add_tcPr().append(shade)
        for run in cell.paragraphs[0].runs:
            from docx.shared import RGBColor
            run.font.color.rgb = RGBColor.from_string('FFFFFF')
    # Keep both merged lunch areas blank for handwriting; no lunch data was supplied.
    set_cell(table.cell(1,0), ['Lunch Options'], size=10, bold_first=True)
    set_cell(table.cell(1,4), ['Lunch Ingredients'], size=10, bold_first=True)
    set_cell(table.cell(2,0), ['Dinner'], size=10, bold_first=True)
    set_cell(table.cell(3,0), ['Shopping','List','(by day)'], size=9, bold_first=True)
    for row in table.rows:
        for cell in row.cells:
            borders = cell._tc.get_or_add_tcPr().find(qn('w:tcBorders'))
            if borders is not None:
                for edge in borders:
                    edge.set(qn('w:color'),'C9CCBF')
    by_id = {r['id']:r for r in recipes}
    for column in range(1,8):
        set_cell(table.cell(2,column), [])
        set_cell(table.cell(3,column), [])
    for meal in plan['meals']:
        recipe = by_id[meal['recipe_id']]
        day = date.fromisoformat(meal['day'])
        column = (day.weekday()+1)%7 + 1
        source = recipe['source']
        if recipe.get('page'):
            source += f", p. {recipe['page']}"
        set_cell(table.cell(2,column), [recipe['name'], source], bold_first=True)
    columns = shopping_columns(plan, recipes, format_quantity)
    for column, lines in enumerate(columns, 1):
        set_cell(table.cell(3,column), lines, size=shopping_size)
    # Footer-sized legend stays in the page body; no extra trailing page paragraph.
    legend = doc.add_paragraph()
    legend.paragraph_format.space_before = Pt(4)
    legend.paragraph_format.space_after = Pt(0)
    legend.paragraph_format.line_spacing = 1
    used = sorted({by_id[m['recipe_id']]['source'] for m in plan['meals']})
    text = ' | '.join(f"{code}: {sources.get(code, {'name':code})['name']}" for code in used)
    run = legend.add_run(f"{plan['servings']} servings per dinner. " + text)
    run.font.name = 'Arial'
    run.font.size = Pt(7)
    doc.core_properties.title = f"Dinner plan week of {plan['week_start']}"
    doc.save(path)


def export_pdf(docx_path, pdf_path):
    soffice = shutil.which('soffice') or shutil.which('libreoffice')
    if not soffice:
        raise RuntimeError('LibreOffice is required for template PDF export. Install libreoffice-writer.')
    with tempfile.TemporaryDirectory(prefix='meal-plan-') as directory:
        temporary = Path(directory)
        result = subprocess.run([
            soffice, '-env:UserInstallation='+(temporary/'profile').as_uri(),
            '--headless', '--convert-to', 'pdf:writer_pdf_Export',
            '--outdir', str(temporary), str(docx_path.resolve())
        ], capture_output=True, text=True, timeout=90)
        exported = temporary/(docx_path.stem+'.pdf')
        if result.returncode or not exported.exists():
            raise RuntimeError(f'Template PDF conversion failed: {result.stdout} {result.stderr}')
        pages = len(PdfReader(exported).pages)
        if pages == 1:
            shutil.copyfile(exported,pdf_path)
        return pages


def render_template_sheet(docx_path, pdf_path, plan, recipes, sources, format_quantity):
    for shopping_size in (8.5,8,7.5):
        render_docx(docx_path,plan,recipes,sources,format_quantity,shopping_size)
        if export_pdf(docx_path,pdf_path) == 1:
            return
    raise ValueError('Shopping list exceeds one page in the weekly template. Shorten item labels before publishing; no items have been dropped.')
