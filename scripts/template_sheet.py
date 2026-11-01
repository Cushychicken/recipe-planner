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
from docx.shared import Inches, Pt, RGBColor
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


def set_cell(cell, lines, size=9, bold_first=False, secondary_size=None):
    cell.text = ''
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP
    for index, line in enumerate(lines):
        paragraph = cell.paragraphs[0] if index == 0 else cell.add_paragraph()
        paragraph.paragraph_format.space_before = Pt(0)
        paragraph.paragraph_format.space_after = Pt(2)
        paragraph.paragraph_format.line_spacing = 1
        run = paragraph.add_run(line)
        run.font.name = 'Arial'
        run.font.size = Pt(secondary_size if index and secondary_size is not None else size)
        run.font.color.rgb = RGBColor(0, 0, 0)
        run.bold = bold_first and index == 0


def shopping_columns(plan, recipes, format_quantity):
    """Each column contains only the ingredients for the dinner directly above it."""
    from planner import day_shopping, shopping_label
    by_id = {r['id']:r for r in recipes}
    columns = [[] for _ in range(7)]
    for meal in plan['meals']:
        if meal.get('kind') == 'leftovers':
            columns[(date.fromisoformat(meal['day']).weekday()+1)%7] = ['No groceries needed.']
            continue
        recipe = by_id[meal['recipe_id']]
        column = (date.fromisoformat(meal['day']).weekday()+1)%7
        if not meal.get('ingredients_verified', recipe['ingredients_verified']):
            columns[column] = ['DRAFT', 'Ingredients pending verification.']
            continue
        for row in day_shopping(plan,meal,recipe):
            columns[column].append('• ' + shopping_label(row))
    return columns


def render_docx(path, plan, recipes, sources, format_quantity, shopping_size=8.5, compact=False):
    doc = template_document()
    section = doc.sections[0]
    # Use the full printable Letter sheet.  The supplied form left a generous
    # right margin, which made seven ingredient columns unnecessarily narrow.
    section.top_margin = Inches(.25)
    section.bottom_margin = Inches(.25)
    section.left_margin = Inches(.25)
    section.right_margin = Inches(.25)
    # Remove blank body paragraphs/explicit page breaks from the supplied form.
    body = doc._element.body
    table = doc.tables[0]
    for child in list(body):
        if child.tag == qn('w:p') and not ''.join(child.itertext()).strip():
            body.remove(child)
    # Expand the fixed-width source table from 9.75 to 10.5 inches, matching
    # the page width between the new margins.  Resize both the table grid and
    # its cell widths; LibreOffice relies on both when exporting the PDF.
    table_width = 15120
    table.autofit = False
    table_properties = table._tbl.tblPr
    table_width_node = table_properties.find(qn('w:tblW'))
    source_width = int(table_width_node.get(qn('w:w'))) if table_width_node is not None else table_width
    scale = table_width / source_width
    if table_width_node is not None:
        table_width_node.set(qn('w:w'), str(table_width))
    for grid_column in table._tbl.tblGrid.gridCol_lst:
        grid_column.set(qn('w:w'), str(round(int(grid_column.get(qn('w:w'))) * scale)))
    for cell_width in table._tbl.iter(qn('w:tcW')):
        try:
            cell_width.set(qn('w:w'), str(round(int(cell_width.get(qn('w:w'))) * scale)))
        except (TypeError, ValueError):
            pass
    title = doc.paragraphs[0]
    title.text = 'Dinner Plan - Week of ' + date.fromisoformat(plan['week_start']).strftime('%B %d, %Y')
    title.paragraph_format.space_after = Pt(4)
    title.paragraph_format.keep_with_next = True
    for run in title.runs:
        run.font.name = 'Arial'
        run.font.size = Pt(18)
    # A minimum row height preserves writing space without clipping long entries.
    # Prioritize the shopping row: it is the dense, read-at-arm's-length part
    # of the sheet.  Lunch and dinner still retain useful writing space.
    # LibreOffice versions differ slightly in how much room they reserve for
    # table paragraphs. The compact fallback therefore gives that engine more
    # headroom while retaining 9 pt ingredient text.
    heights = (.3, .6, .8, 4.25) if compact else (.3, .8, .95, 5.0)
    for row, height in zip(table.rows, heights):
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
        shade.set(qn('w:fill'),'FFFFFF')
        cell._tc.get_or_add_tcPr().append(shade)
        for run in cell.paragraphs[0].runs:
            run.font.color.rgb = RGBColor(0, 0, 0)
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
                    edge.set(qn('w:color'),'000000')
            shade = cell._tc.get_or_add_tcPr().find(qn('w:shd'))
            if shade is None:
                shade = OxmlElement('w:shd')
                cell._tc.get_or_add_tcPr().append(shade)
            shade.set(qn('w:fill'),'FFFFFF')
    by_id = {r['id']:r for r in recipes}
    for column in range(1,8):
        set_cell(table.cell(2,column), [])
        set_cell(table.cell(3,column), [])
    for meal in plan['meals']:
        if meal.get('kind') == 'leftovers':
            column = (date.fromisoformat(meal['day']).weekday()+1)%7+1
            set_cell(table.cell(2,column), ['Leftovers / takeout'], bold_first=True)
            continue
        recipe = by_id[meal['recipe_id']]
        day = date.fromisoformat(meal['day'])
        column = (day.weekday()+1)%7 + 1
        source = recipe['source']
        if recipe.get('page'):
            source += f" · p. {recipe['page']}"
        set_cell(table.cell(2,column), [recipe['name'], source], size=9.5,
                 secondary_size=10.5, bold_first=True)
    columns = shopping_columns(plan, recipes, format_quantity)
    for column, lines in enumerate(columns, 1):
        set_cell(table.cell(3,column), lines, size=shopping_size)
        for paragraph in table.cell(3,column).paragraphs:
            paragraph.paragraph_format.space_after = Pt(0)
    # Footer-sized legend stays in the page body; no extra trailing page paragraph.
    legend = doc.add_paragraph()
    legend.paragraph_format.space_before = Pt(4)
    legend.paragraph_format.space_after = Pt(0)
    legend.paragraph_format.line_spacing = 1
    used = sorted({by_id[m['recipe_id']]['source'] for m in plan['meals'] if m.get('recipe_id')})
    text = ' | '.join(f"{code}: {sources.get(code, {'name':code})['name']}" for code in used)
    run = legend.add_run(f"{plan['servings']} servings per dinner. " + text)
    run.font.name = 'Arial'
    run.font.size = Pt(7)
    run.font.color.rgb = RGBColor(0, 0, 0)
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
    # Keep ingredients comfortably readable.  The final compact pass gains
    # vertical room before reducing type below 9 pt.
    for shopping_size, compact in ((10,False),(9.5,False),(9,True)):
        render_docx(docx_path,plan,recipes,sources,format_quantity,shopping_size,compact)
        if export_pdf(docx_path,pdf_path) == 1:
            return
    raise ValueError('Shopping list exceeds one page in the weekly template. Shorten item labels before publishing; no items have been dropped.')
