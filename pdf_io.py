"""Read the six structured tables from a single template-format PDF and create PDF reports."""
from io import BytesIO
from xml.sax.saxutils import escape
import pandas as pd
import pdfplumber
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, LongTable, TableStyle, KeepTogether
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from scheduler import REQUIRED, seating_table

SECTION_NAMES = {name: name.upper() for name in REQUIRED}

def parse_input_pdf(upload):
    """Require selectable-text, template-style PDF tables with section headings."""
    result = {}
    current = None
    with pdfplumber.open(upload) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ''
            lines = [x.strip().upper() for x in text.splitlines()]
            sections = [name for name, heading in SECTION_NAMES.items() if heading in lines]
            if len(sections) > 1:
                raise ValueError('More than one section heading on a page. Use the downloadable template.')
            if sections:
                current = sections[0]
                if current in result:
                    raise ValueError(f'Duplicate section: {current}.')
            if current is None:
                raise ValueError('Missing section heading on the first page. Use the template.')
            tables = page.extract_tables()
            if len(tables) != 1 or not tables[0] or len(tables[0]) < 2:
                raise ValueError(f'Could not read a table on page {page.page_number}. Use a text-based PDF template.')
            header = [(v or '').strip() for v in tables[0][0]]
            if len(set(header)) != len(header):
                raise ValueError(f'Duplicate column names on page {page.page_number}.')
            df = pd.DataFrame(tables[0][1:], columns=header)
            df = df.apply(lambda col: col.map(lambda v: v.strip() if isinstance(v, str) else v))
            df = df.replace('', None).dropna(how='all').reset_index(drop=True)
            if current in result:
                if list(result[current].columns) != header:
                    raise ValueError(f'Column headers changed on page {page.page_number}.')
                result[current] = pd.concat([result[current], df], ignore_index=True)
            else:
                result[current] = df
    missing = set(REQUIRED) - set(result)
    if missing:
        raise ValueError('PDF is missing sections: ' + ', '.join(sorted(missing)))
    return result

def _make_pdf(sections, title):
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=28, rightMargin=28, topMargin=32, bottomMargin=32)
    styles = getSampleStyleSheet()
    styles['Title'].alignment = TA_CENTER
    body = []
    body.append(Paragraph(escape(title), styles['Title']))
    body.append(Spacer(1, 14))
    for name, df in sections:
        body.append(Paragraph(escape(name), styles['Heading2']))
        body.append(Spacer(1, 6))
        values = [[str(c) for c in df.columns]] + [[str(v) if pd.notna(v) else '' for v in row] for row in df.itertuples(index=False, name=None)]
        if len(df.columns) == 0:
            continue
        width = doc.width / len(df.columns)
        small = styles['BodyText'].clone('small_' + str(len(body)))
        small.fontSize = 9
        small.leading = 12
        table_data = [[Paragraph(escape(v), small) for v in row] for row in values]
        table = LongTable(table_data, colWidths=[width]*len(df.columns), repeatRows=1, hAlign='LEFT')
        table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#DCE9F4')),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#F5F8FB')]),
            ('GRID', (0,0), (-1,-1), 0.25, colors.HexColor('#C7D3DF')),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('LEFTPADDING', (0,0), (-1,-1), 5),
            ('RIGHTPADDING', (0,0), (-1,-1), 5),
            ('TOPPADDING', (0,0), (-1,-1), 5),
            ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ]))
        body.append(table)
        body.append(Spacer(1, 20))
    def footer(canvas, doc):
        canvas.setFont("Helvetica", 9)
        canvas.setFillColor(colors.HexColor("#526477"))
        canvas.drawString(28, 16, "ExamFlow | Examination Management")
        canvas.drawRightString(doc.pagesize[0]-28, 16, f"Page {doc.page}")
    doc.build(body, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()

def make_template_pdf(data):
    # Each section starts on a new page so extraction remains unambiguous.
    from reportlab.platypus import PageBreak
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=28, rightMargin=28, topMargin=32, bottomMargin=32)
    styles = getSampleStyleSheet()
    story = []
    for idx, (name, df) in enumerate(data.items()):
        if idx: story.append(PageBreak())
        story.append(Paragraph(name.upper(), styles['Heading1']))
        story.append(Paragraph('Required columns: ' + ', '.join(REQUIRED[name]), styles['Normal']))
        story.append(Spacer(1, 12))
        width = doc.width / len(df.columns)
        rows = [[str(c) for c in df.columns]] + [[str(v) if pd.notna(v) else "" for v in row] for row in df.itertuples(index=False, name=None)]
        table = LongTable(rows, colWidths=[width]*len(df.columns), repeatRows=1)
        table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#DCE9F4')),('GRID',(0,0),(-1,-1),0.4,colors.grey),('FONTSIZE',(0,0),(-1,-1),9),('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7)]))
        story.append(table)
    doc.build(story)
    return buf.getvalue()

def make_report_pdf(schedule, history, issues):
    summary = pd.DataFrame([{'Examinations':schedule.SubjectID.nunique(), 'Fitness':f'{history.iloc[-1].Fitness:.4f}', 'Validation': 'PASS' if not issues else 'REVIEW', 'Issues':len(issues)}])
    sections = [('Summary',summary),('Final timetable and allocations',schedule[['SubjectName','Date','Session','StartTime','EndTime','RoomID','RoomCapacity','AllocatedStudents','UnallocatedStudents','InvigilatorID']])]
    if issues:
        sections.append(('Validation issues',pd.DataFrame({'Issue':issues})))
    return _make_pdf(sections, 'Exam Timetable and Invigilation Report')

def audience_pdf(schedule, data, audience, issues=None):
    df = schedule.copy()
    if audience == 'students':
        df = seating_table(schedule, data)
        cols = ['StudentID','StudentName','Date','StartTime','EndTime','SubjectName','RoomID','SeatNo']
        df = df.sort_values(['StudentID','Date','StartTime'])[cols]
        df.columns = ['Register no.','Student','Date','Starts','Ends','Subject','Room','Seat']
        title = 'Student examination timetable'
    else:
        df = df[df['AllocatedStudents'] > 0].merge(data['invigilators'][['InvigilatorID','InvigilatorName']], on='InvigilatorID', how='left')
        df = df.sort_values(['InvigilatorID','Date','StartTime'])[['InvigilatorID','InvigilatorName','Date','StartTime','EndTime','SubjectName','RoomID']]
        df.columns = ['Faculty ID','Teacher','Date','Starts','Ends','Subject','Room']
        title = 'Teacher invigilation duties'
    df = df.fillna('UNASSIGNED').replace('', 'UNASSIGNED')
    return _make_pdf([('DRAFT - validation issues exist' if issues else 'Examination schedule - all implemented checks passed', df)], title)
