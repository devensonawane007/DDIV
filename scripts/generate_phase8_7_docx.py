#!/usr/bin/env python3
"""
Generate publication-quality Microsoft Word (.docx) report for DDIV Phase 8.7.
Covers BASELINE vs FULL_DDIV comparative forensic audit, complete 40-task table,
statistical analysis, mechanism audit, and embedded high-resolution figures.
"""

import os
import csv
import json
from pathlib import Path

import docx
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml import parse_xml, OxmlElement
from docx.oxml.ns import nsdecls, qn

PROJECT_ROOT = Path("D:/DDIV").resolve()
AUDIT_DIR = (PROJECT_ROOT / "results/quixbugs_baseline_vs_fullddiv_audit_20261016T083103Z").resolve()
OUTPUT_DOCX = AUDIT_DIR / "DDIV_Phase_8_7_Baseline_vs_FULL_DDIV_Forensic_Report.docx"

# Color Palette
HEX_PRIMARY = "1E3A8A"      # Deep Navy Blue
HEX_SECONDARY = "2563EB"    # Royal Blue
HEX_DARK = "111827"         # Near Black for text
HEX_MUTED = "4B5563"        # Slate Gray
HEX_LIGHT_BG = "F3F4F6"     # Table header light gray
HEX_ZEBRA = "F9FAFB"        # Subtle zebra row
HEX_PASS_BG = "DCFCE7"      # Soft Green
HEX_PASS_TXT = "15803D"     # Forest Green
HEX_FAIL_BG = "FEE2E2"      # Soft Red
HEX_FAIL_TXT = "B91C1C"     # Crimson Red
HEX_RECOVER_BG = "E0E7FF"   # Soft Indigo
HEX_RECOVER_TXT = "3730A3"  # Deep Indigo
HEX_CALLOUT_BORDER = "3B82F6" # Blue border
HEX_BORDER = "D1D5DB"       # Cell border gray

COLOR_PRIMARY = RGBColor(30, 58, 138)
COLOR_SECONDARY = RGBColor(37, 99, 235)
COLOR_DARK = RGBColor(17, 24, 39)
COLOR_MUTED = RGBColor(75, 85, 99)

def set_cell_margins(cell, top=100, bottom=100, left=150, right=150):
    """Set cell padding in twips (1 pt = 20 twips)."""
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = parse_xml(
        f'<w:tcMar {nsdecls("w")}>'
        f'<w:top w:w="{top}" w:type="dxa"/>'
        f'<w:bottom w:w="{bottom}" w:type="dxa"/>'
        f'<w:left w:w="{left}" w:type="dxa"/>'
        f'<w:right w:w="{right}" w:type="dxa"/>'
        f'</w:tcMar>'
    )
    tcPr.append(tcMar)

def set_cell_shading(cell, color_hex):
    """Set background color of a cell."""
    tcPr = cell._tc.get_or_add_tcPr()
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{color_hex}"/>')
    tcPr.append(shd)

def set_table_borders(table, color_hex="D1D5DB"):
    """Set subtle cell borders for an entire table."""
    tblPr = table._tbl.tblPr
    borders = parse_xml(
        f'<w:tblBorders {nsdecls("w")}>'
        f'<w:top w:val="single" w:sz="4" w:space="0" w:color="{color_hex}"/>'
        f'<w:bottom w:val="single" w:sz="6" w:space="0" w:color="1E3A8A"/>'
        f'<w:insideH w:val="single" w:sz="4" w:space="0" w:color="{color_hex}"/>'
        f'<w:insideV w:val="none"/>'
        f'<w:left w:val="none"/>'
        f'<w:right w:val="none"/>'
        f'</w:tblBorders>'
    )
    tblPr.append(borders)

def add_callout_box(doc, title, paragraphs, border_hex="3B82F6", bg_hex="F8FAFC"):
    """Add a professional left-bordered callout box."""
    tbl = doc.add_table(rows=1, cols=1)
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl.autofit = False
    cell = tbl.cell(0, 0)
    cell.width = Inches(6.5)
    
    tcPr = cell._tc.get_or_add_tcPr()
    borders = parse_xml(
        f'<w:tcBorders {nsdecls("w")}>'
        f'<w:left w:val="single" w:sz="24" w:space="0" w:color="{border_hex}"/>'
        f'<w:top w:val="none"/>'
        f'<w:bottom w:val="none"/>'
        f'<w:right w:val="none"/>'
        f'</w:tcBorders>'
    )
    tcPr.append(borders)
    set_cell_shading(cell, bg_hex)
    set_cell_margins(cell, top=140, bottom=140, left=200, right=160)
    
    p0 = cell.paragraphs[0]
    p0.paragraph_format.space_before = Pt(0)
    p0.paragraph_format.space_after = Pt(4)
    run_t = p0.add_run(f"★ {title}")
    run_t.bold = True
    run_t.font.name = "Calibri"
    run_t.font.size = Pt(11)
    run_t.font.color.rgb = COLOR_PRIMARY
    
    for text in paragraphs:
        p = cell.add_paragraph()
        p.paragraph_format.space_before = Pt(2)
        p.paragraph_format.space_after = Pt(4)
        run = p.add_run(text)
        run.font.name = "Calibri"
        run.font.size = Pt(9.5)
        run.font.color.rgb = COLOR_DARK
        
    doc.add_paragraph().paragraph_format.space_after = Pt(6)

def build_document():
    doc = Document()
    
    # Page setup - 1 inch margins all around
    sections = doc.sections
    for section in sections:
        section.top_margin = Inches(1.0)
        section.bottom_margin = Inches(1.0)
        section.left_margin = Inches(1.0)
        section.right_margin = Inches(1.0)
        
        # Header & Footer
        header = section.header
        hp = header.paragraphs[0]
        hp.text = "DDIV Phase 8.7 Research Report | BASELINE vs. FULL_DDIV Comparative Forensic Audit"
        hp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        hp.runs[0].font.name = "Calibri"
        hp.runs[0].font.size = Pt(8.5)
        hp.runs[0].font.color.rgb = COLOR_MUTED
        
        footer = section.footer
        fp = footer.paragraphs[0]
        fp.text = "Confidential — Generated for Research Publication & Empirical Verification"
        fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        fp.runs[0].font.name = "Calibri"
        fp.runs[0].font.size = Pt(8.5)
        fp.runs[0].font.color.rgb = COLOR_MUTED

    # Document Styles
    normal_style = doc.styles['Normal']
    normal_style.font.name = 'Calibri'
    normal_style.font.size = Pt(10.5)
    normal_style.font.color.rgb = COLOR_DARK
    normal_style.paragraph_format.line_spacing = 1.15
    normal_style.paragraph_format.space_after = Pt(6)

    # -------------------------------------------------------------------------
    # Title Section
    # -------------------------------------------------------------------------
    title_p = doc.add_paragraph()
    title_p.paragraph_format.space_before = Pt(12)
    title_p.paragraph_format.space_after = Pt(4)
    run_title = title_p.add_run("Automated Program Repair via Dual-Domain Interactive Verification (DDIV)")
    run_title.font.name = "Calibri"
    run_title.font.size = Pt(22)
    run_title.font.bold = True
    run_title.font.color.rgb = COLOR_PRIMARY

    sub_p = doc.add_paragraph()
    sub_p.paragraph_format.space_before = Pt(0)
    sub_p.paragraph_format.space_after = Pt(12)
    run_sub = sub_p.add_run("Phase 8.7: Forensic Analysis, Paired Statistical Comparison & Multi-Attempt Recovery on QuixBugs (BASELINE vs. FULL_DDIV)")
    run_sub.font.name = "Calibri"
    run_sub.font.size = Pt(13)
    run_sub.font.color.rgb = COLOR_SECONDARY

    # Metadata bar
    meta_table = doc.add_table(rows=1, cols=4)
    meta_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    meta_table.autofit = False
    col_widths = [Inches(1.6), Inches(1.6), Inches(1.6), Inches(1.7)]
    for i, w in enumerate(col_widths):
        meta_table.cell(0, i).width = w
    
    meta_items = [
        ("BENCHMARK", "QuixBugs (40 Tasks)"),
        ("EVALUATION SCOPE", "BASELINE vs. FULL_DDIV"),
        ("INFERENCE MODEL", "qwen2.5-coder:7b (Local)"),
        ("COST & CLOUD CALLS", "$0.00 (Zero Cloud APIs)")
    ]
    for i, (label, val) in enumerate(meta_items):
        cell = meta_table.cell(0, i)
        set_cell_shading(cell, HEX_LIGHT_BG)
        set_cell_margins(cell, top=80, bottom=80, left=100, right=100)
        p = cell.paragraphs[0]
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(0)
        rl = p.add_run(f"{label}\n")
        rl.font.size = Pt(7.5)
        rl.font.bold = True
        rl.font.color.rgb = COLOR_MUTED
        rv = p.add_run(val)
        rv.font.size = Pt(8.5)
        rv.font.bold = True
        rv.font.color.rgb = COLOR_PRIMARY

    doc.add_paragraph().paragraph_format.space_after = Pt(12)

    # -------------------------------------------------------------------------
    # Section 1: Executive Summary
    # -------------------------------------------------------------------------
    h1 = doc.add_heading("1. Executive Summary & Core Research Findings", level=1)
    h1.runs[0].font.color.rgb = COLOR_PRIMARY

    doc.add_paragraph(
        "This research report provides an authoritative, strictly read-only comparative evaluation of the completed "
        "Phase 8.6 QuixBugs automated program repair benchmark across all 40 canonical Python programs. The evaluation "
        "compares single-attempt zero-mechanism BASELINE (1 attempt, T=0.0) against multi-attempt supervisory FULL_DDIV "
        "(up to 3 attempts, T=0.0 to 0.2, Supervisor guidance, FailureDetector, Episodic Memory, and Anti-Repetition Gate). "
        "All 80 underlying condition runs utilized strictly local Ollama inference with zero cloud invocations ($0.00 cost) "
        "and strict ground-truth isolation."
    )

    add_callout_box(
        doc,
        "Key Analytical Findings & Statistical Claim Boundaries",
        [
            "1. Resolution Efficacy: FULL_DDIV achieved 13 / 40 resolved tasks (32.5%), delivering an absolute gain of +12.5 percentage points (+62.5% relative improvement) over BASELINE (8 / 40, 20.0%).",
            "2. Zero Regressions: In no instance did BASELINE resolve a defect that FULL_DDIV failed (c = 0, N_both = 8). Enabling DDIV mechanisms introduced zero performance degradation.",
            "3. Multi-Attempt Recovery: Five tasks were uniquely recovered under FULL_DDIV (b = 5: quicksort, kth, reverse_linked_list, breadth_first_search, levenshtein).",
            "4. Statistical Rigor (Exact McNemar p = 0.0625): Because p = 0.0625 > 0.05 on N=40 paired tasks, the result demonstrates a strong positive directional trend but does not achieve formal statistical significance at alpha=0.05 due to bounded sample size.",
            "5. Resource Overhead: FULL_DDIV consumed 225,458 tokens (3.15x) and 1,289.00s execution duration (2.67x) compared to BASELINE (71,558 tokens, 482.99s), with tokens per fix rising from 8,945 to 17,343.",
            "6. Immutable Data Integrity: 4,186 of 4,186 source files verified byte-identical pre- and post-analysis; data/ddiv_memory.db remained untouched."
        ]
    )

    # -------------------------------------------------------------------------
    # Section 2: Master Evaluation Comparison Tables (Tables A - E)
    # -------------------------------------------------------------------------
    h2 = doc.add_heading("2. Master Evaluation Comparison Tables (Tables A to E)", level=1)
    h2.runs[0].font.color.rgb = COLOR_PRIMARY

    doc.add_paragraph("Table 1 summarizes aggregate repair efficacy, attempt dynamics, patch quality, and resource consumption:")

    # Table 1: Aggregate Metrics
    agg_csv = AUDIT_DIR / "aggregate_metrics_comparison.csv"
    with open(agg_csv, "r", encoding="utf-8") as f:
        reader = list(csv.reader(f))
    
    header = reader[0]
    rows = reader[1:]

    t1 = doc.add_table(rows=len(rows) + 1, cols=len(header))
    t1.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(t1)

    # Format Header
    for j, h_text in enumerate(header):
        cell = t1.cell(0, j)
        set_cell_shading(cell, HEX_PRIMARY)
        set_cell_margins(cell, top=100, bottom=100, left=100, right=100)
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER if j >= 2 else WD_ALIGN_PARAGRAPH.LEFT
        run = p.add_run(h_text)
        run.bold = True
        run.font.size = Pt(8.5)
        run.font.color.rgb = RGBColor(255, 255, 255)

    # Format Rows
    for i, row in enumerate(rows):
        bg = HEX_ZEBRA if i % 2 == 1 else "FFFFFF"
        for j, val in enumerate(row):
            cell = t1.cell(i + 1, j)
            set_cell_shading(cell, bg)
            set_cell_margins(cell, top=70, bottom=70, left=90, right=90)
            p = cell.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.RIGHT if j in [2, 3, 4, 5] else WD_ALIGN_PARAGRAPH.LEFT
            run = p.add_run(val)
            run.font.size = Pt(8.0)
            if j == 1 and ("Resolved" in val or "Resolution Rate" in val):
                run.bold = True
                run.font.color.rgb = COLOR_PRIMARY
            elif j == 4 and "+" in val:
                run.bold = True
                run.font.color.rgb = RGBColor(21, 128, 61)

    doc.add_paragraph().paragraph_format.space_after = Pt(10)

    # -------------------------------------------------------------------------
    # Section 3: Mechanism Evidence
    # -------------------------------------------------------------------------
    doc.add_heading("Table 2: FULL_DDIV Mechanism Activation and Observational Recovery Evidence", level=2)
    mech_csv = AUDIT_DIR / "mechanism_evidence.csv"
    with open(mech_csv, "r", encoding="utf-8") as f:
        m_reader = list(csv.reader(f))

    t2 = doc.add_table(rows=len(m_reader), cols=len(m_reader[0]))
    t2.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(t2)

    for j, h_text in enumerate(m_reader[0]):
        cell = t2.cell(0, j)
        set_cell_shading(cell, HEX_PRIMARY)
        set_cell_margins(cell, top=90, bottom=90, left=80, right=80)
        p = cell.paragraphs[0]
        run = p.add_run(h_text)
        run.bold = True
        run.font.size = Pt(8.0)
        run.font.color.rgb = RGBColor(255, 255, 255)

    for i, row in enumerate(m_reader[1:]):
        bg = HEX_ZEBRA if i % 2 == 1 else "FFFFFF"
        for j, val in enumerate(row):
            cell = t2.cell(i + 1, j)
            set_cell_shading(cell, bg)
            set_cell_margins(cell, top=60, bottom=60, left=80, right=80)
            p = cell.paragraphs[0]
            run = p.add_run(val)
            run.font.size = Pt(7.5)
            if j == 0:
                run.bold = True
            elif j == 5 and val != "0":
                run.bold = True
                run.font.color.rgb = RGBColor(21, 128, 61)

    doc.add_paragraph().paragraph_format.space_after = Pt(14)

    # -------------------------------------------------------------------------
    # Section 4: Complete 40-Task Paired Evaluation Table
    # -------------------------------------------------------------------------
    h3 = doc.add_heading("3. Complete 40-Task Paired Outcomes Table", level=1)
    h3.runs[0].font.color.rgb = COLOR_PRIMARY

    doc.add_paragraph(
        "Table 3 presents the paired resolution outcomes across all 40 canonical QuixBugs benchmark tasks. "
        "Tasks in the full_ddiv_only category represent multi-attempt recoveries rescued by supervisory guidance:"
    )

    task_csv = AUDIT_DIR / "task_level_comparison.csv"
    with open(task_csv, "r", encoding="utf-8") as f:
        t_reader = list(csv.reader(f))

    # Selected columns for print formatting: Program, BASELINE, FULL_DDIV, Att(B), Att(F), Paired Category, Recovery Attempt
    display_indices = [1, 2, 3, 4, 5, 6, 18]
    display_headers = ["Program Name", "BASELINE", "FULL_DDIV", "Att (B)", "Att (F)", "Paired Category", "Recovery"]

    t3 = doc.add_table(rows=len(t_reader), cols=len(display_headers))
    t3.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(t3)

    for j, h_text in enumerate(display_headers):
        cell = t3.cell(0, j)
        set_cell_shading(cell, HEX_PRIMARY)
        set_cell_margins(cell, top=80, bottom=80, left=70, right=70)
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER if j in [1, 2, 3, 4, 6] else WD_ALIGN_PARAGRAPH.LEFT
        run = p.add_run(h_text)
        run.bold = True
        run.font.size = Pt(8.0)
        run.font.color.rgb = RGBColor(255, 255, 255)

    for i, row in enumerate(t_reader[1:]):
        paired_cat = row[6]
        is_recovery = (paired_cat == "full_ddiv_only")
        row_bg = HEX_RECOVER_BG if is_recovery else (HEX_ZEBRA if i % 2 == 1 else "FFFFFF")

        for j, col_idx in enumerate(display_indices):
            val = row[col_idx]
            cell = t3.cell(i + 1, j)
            set_cell_shading(cell, row_bg)
            set_cell_margins(cell, top=50, bottom=50, left=70, right=70)
            p = cell.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER if j in [1, 2, 3, 4, 6] else WD_ALIGN_PARAGRAPH.LEFT

            if j in [1, 2]: # BASELINE or FULL_DDIV resolved bool
                if val.lower() == "true":
                    run = p.add_run("PASS")
                    run.bold = True
                    run.font.size = Pt(7.5)
                    run.font.color.rgb = RGBColor(21, 128, 61)
                else:
                    run = p.add_run("FAIL")
                    run.bold = False
                    run.font.size = Pt(7.5)
                    run.font.color.rgb = RGBColor(185, 28, 28)
            elif j == 0:
                run = p.add_run(val)
                run.bold = is_recovery
                run.font.size = Pt(7.5)
                if is_recovery:
                    run.font.color.rgb = RGBColor(55, 48, 163)
            elif j == 5:
                run = p.add_run(val)
                run.font.size = Pt(7.5)
                if is_recovery:
                    run.bold = True
                    run.font.color.rgb = RGBColor(55, 48, 163)
            elif j == 6:
                run = p.add_run(f"Att {val}" if val != "N/A" else "—")
                run.font.size = Pt(7.5)
                if val != "N/A":
                    run.bold = True
                    run.font.color.rgb = RGBColor(55, 48, 163)
            else:
                run = p.add_run(val)
                run.font.size = Pt(7.5)

    doc.add_paragraph().paragraph_format.space_after = Pt(14)

    # -------------------------------------------------------------------------
    # Section 5: Statistical Rigor & Exact McNemar Analysis
    # -------------------------------------------------------------------------
    h4 = doc.add_heading("4. Statistical Rigor, Confidence Intervals & Exact McNemar Test", level=1)
    h4.runs[0].font.color.rgb = COLOR_PRIMARY

    stat_json = json.loads((AUDIT_DIR / "statistical_analysis.json").read_text(encoding="utf-8"))

    doc.add_paragraph(
        "To rigorously assess whether the observed +12.5 percentage point improvement represents a statistically "
        "defensible claim rather than random sampling variation, an offline paired contingency analysis was conducted "
        "using each benchmark task as the paired experimental unit."
    )

    doc.add_heading("2x2 Paired Contingency Matrix (N = 40 Tasks)", level=2)
    cont_tbl = doc.add_table(rows=3, cols=3)
    cont_tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(cont_tbl)

    headers_cont = ["", "FULL_DDIV Resolved", "FULL_DDIV Failed"]
    for j, text in enumerate(headers_cont):
        cell = cont_tbl.cell(0, j)
        set_cell_shading(cell, HEX_PRIMARY)
        set_cell_margins(cell, top=70, bottom=70, left=90, right=90)
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run(text)
        run.bold = True
        run.font.size = Pt(8.5)
        run.font.color.rgb = RGBColor(255, 255, 255)

    matrix_rows = [
        ("BASELINE Resolved", "8 tasks (N_both = 20.0%)", "0 tasks (N_BASE-only = 0.0%)"),
        ("BASELINE Failed", "5 tasks (N_FULL-only = 12.5%)", "27 tasks (N_neither = 67.5%)")
    ]
    for i, (rl, v1, v2) in enumerate(matrix_rows):
        cell_l = cont_tbl.cell(i + 1, 0)
        set_cell_shading(cell_l, HEX_LIGHT_BG)
        set_cell_margins(cell_l, top=70, bottom=70, left=90, right=90)
        p = cell_l.paragraphs[0]
        run = p.add_run(rl)
        run.bold = True
        run.font.size = Pt(8.0)

        for j, v in enumerate([v1, v2]):
            cell = cont_tbl.cell(i + 1, j + 1)
            set_cell_shading(cell, "FFFFFF")
            set_cell_margins(cell, top=70, bottom=70, left=90, right=90)
            p = cell.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = p.add_run(v)
            run.font.size = Pt(8.0)
            if "5 tasks" in v:
                run.bold = True
                run.font.color.rgb = RGBColor(37, 99, 235)

    doc.add_paragraph().paragraph_format.space_after = Pt(6)

    doc.add_paragraph(
        "Statistical Test Formulations and Results:\n"
        "• Discordant Pairs: b = 5 (FULL_DDIV only), c = 0 (BASELINE only). Total discordant pairs: b + c = 5.\n"
        f"• Exact McNemar Two-Sided p-value: p = 2 * (0.5)^5 = {stat_json['mcnemar_test']['exact_binomial_two_sided_p_value']:.4f}.\n"
        f"• Exact McNemar One-Sided p-value: p = (0.5)^5 = {stat_json['mcnemar_test']['exact_binomial_one_sided_p_value']:.4f}.\n"
        f"• Asymptotic McNemar (with continuity correction): chi^2 = (|5 - 0| - 1)^2 / 5 = 16 / 5 = 3.20 (p = {stat_json['mcnemar_test']['asymptotic_continuity_corrected_p_value']:.4f}).\n"
        f"• Wilson 95% Confidence Intervals: BASELINE = [{stat_json['confidence_intervals_95']['BASELINE_wilson'][0]:.1f}%, {stat_json['confidence_intervals_95']['BASELINE_wilson'][1]:.1f}%]; FULL_DDIV = [{stat_json['confidence_intervals_95']['FULL_DDIV_wilson'][0]:.1f}%, {stat_json['confidence_intervals_95']['FULL_DDIV_wilson'][1]:.1f}%].\n"
        f"• Paired Difference 95% CI (Wald): [{stat_json['confidence_intervals_95']['paired_difference_wald_pp'][0]:.2f} pp, {stat_json['confidence_intervals_95']['paired_difference_wald_pp'][1]:.2f} pp]."
    )

    doc.add_paragraph(
        "Critical Research Claim Boundary:\n"
        "Because the exact two-sided McNemar p-value (0.0625) strictly exceeds the conventional threshold alpha = 0.05, "
        "the evaluation does not achieve formal two-sided statistical significance at the 5% level. This is directly attributable "
        "to the bounded sample size of QuixBugs (N=40). In a research publication, authors must transparently characterize this "
        "outcome as a strong positive directional trend with zero regressions, rather than claiming definitive statistical confirmation."
    )

    # -------------------------------------------------------------------------
    # Section 6: Qualitative Recovery Analysis
    # -------------------------------------------------------------------------
    h5 = doc.add_heading("5. Qualitative Analysis: The Five Multi-Attempt Recovered Tasks", level=1)
    h5.runs[0].font.color.rgb = COLOR_PRIMARY

    recoveries = [
        ("quicksort (Recovered on Attempt 2)",
         "Baseline Failure: At T=0.0, the model fell into a symmetric greedy attractor, modifying both partition filters to 'x <= pivot' and 'x >= pivot', which duplicated pivot values.\n"
         "DDIV Supervisory Recovery: The Anti-Repetition Gate detected the repeated patch and the Supervisor injected the negative constraint: 'Modify only ONE of the two partition comprehensions.' On Attempt 2, the model modified only the lesser partition, passing all 13 specification tests."),
        ("kth (Recovered on Attempt 2)",
         "Baseline Failure: Greedy decoding generated an off-by-one sub-array index extraction in quickselect recursion.\n"
         "DDIV Supervisory Recovery: The Supervisor injected failure guidance directing the model to evaluate pivot rank relative to k. Attempt 2 adjusted the recursion offset, passing all specification tests."),
        ("reverse_linked_list (Recovered on Attempt 3)",
         "Baseline Failure: Attempt 1 produced an unparseable diff; Attempt 2 produced an incomplete pointer assignment that created circular references.\n"
         "DDIV Supervisory Recovery: Iterative failure feedback guided the model through the complete 3-step pointer inversion sequence (next_node = node.successor; node.successor = prev_node; prev_node = node; node = next_node), resolving on Attempt 3."),
        ("breadth_first_search (Recovered on Attempt 2)",
         "Baseline Failure: The model failed to mark neighbor nodes as visited upon queue insertion, causing redundant queue expansion.\n"
         "DDIV Supervisory Recovery: Attempt 2 corrected visited set membership and queue insertion logic."),
        ("levenshtein (Recovered on Attempt 2)",
         "Baseline Failure: Off-by-one substring slicing in the recursive substitution branch.\n"
         "DDIV Supervisory Recovery: Attempt 2 adjusted recursive substitution cost parameters, passing all specification tests.")
    ]

    for title, text in recoveries:
        p_t = doc.add_paragraph()
        p_t.paragraph_format.space_before = Pt(4)
        p_t.paragraph_format.space_after = Pt(1)
        r = p_t.add_run(f"• {title}")
        r.bold = True
        r.font.color.rgb = COLOR_SECONDARY
        
        p_b = doc.add_paragraph(text)
        p_b.paragraph_format.space_before = Pt(0)
        p_b.paragraph_format.space_after = Pt(4)

    # -------------------------------------------------------------------------
    # Section 7: Embedded Visualizations (Figures 1 to 7)
    # -------------------------------------------------------------------------
    h6 = doc.add_heading("6. Research-Ready Figures & Graphical Analysis", level=1)
    h6.runs[0].font.color.rgb = COLOR_PRIMARY

    fig_dir = AUDIT_DIR / "figures"
    fig_data = [
        ("Figure 1: QuixBugs 40-Task Benchmark: BASELINE vs. FULL_DDIV Resolution Rate",
         fig_dir / "figure_1_overall_resolution.png",
         "Side-by-side comparison of overall repair resolution rate across all 40 QuixBugs tasks. FULL_DDIV achieved 32.5% (13/40) vs BASELINE 20.0% (8/40), delivering an absolute gain of +12.5 percentage points (+62.5% relative improvement, exact McNemar p = 0.0625)."),
        ("Figure 2: Complete 40-Task Paired Outcomes Matrix",
         fig_dir / "figure_2_task_outcomes_matrix.png",
         "Paired matrix showing individual outcomes for each of the 40 canonical tasks. Green indicates passing 100% of specification tests; red indicates unresolved defects. Red row labels indicate the 5 tasks uniquely recovered by FULL_DDIV."),
        ("Figure 3: Paired Contingency Distribution (N = 40 Tasks)",
         fig_dir / "figure_3_paired_distribution.png",
         "Distribution of paired binary outcomes across the four contingency categories: Both Resolved (8 tasks, 20.0%), FULL_DDIV Only (5 tasks, 12.5%), BASELINE Only (0 tasks, 0.0%), and Neither Resolved (27 tasks, 67.5%)."),
        ("Figure 4: Repair Attempts Distribution and Multi-Attempt Recovery Breakdown",
         fig_dir / "figure_4_attempts_and_recovery.png",
         "Left: Distribution of attempts executed per task under BASELINE (fixed at 1) vs FULL_DDIV (bounded at 3 with early stopping). Right: Resolution stage breakdown for FULL_DDIV (8 on Attempt 1, 4 on Attempt 2, 1 on Attempt 3)."),
        ("Figure 5: Resource and Token Consumption Efficiency Trade-Offs",
         fig_dir / "figure_5_resource_efficiency.png",
         "Comparison of total tokens (71.5k vs 225.5k), tokens per successful fix (8.9k vs 17.3k), total execution duration (483s vs 1289s), and mean per-task latency (12.1s vs 32.2s). All inference executed locally with $0.00 cloud costs."),
        ("Figure 6: Per-Attempt Patch Validity, Application, and Evaluator Failure Breakdown",
         fig_dir / "figure_6_patch_evaluator_outcomes.png",
         "Percentage breakdown of executed attempts across evaluator stages: valid unified diff extracted, patch applied cleanly against git base, specification tests passed, timeout (15s), and AST syntax/indentation failure."),
        ("Figure 7: FULL_DDIV Mechanism Invocations & Observational Recovery Associations",
         fig_dir / "figure_7_mechanism_evidence.png",
         "Inventory of FULL_DDIV mechanism invocations (Supervisor guidance, FailureDetector, anti-repetition gate, episodic memory) alongside observational co-occurrence with task recovery.")
    ]

    for title, img_path, caption in fig_data:
        if img_path.exists():
            hp = doc.add_paragraph()
            hp.paragraph_format.space_before = Pt(8)
            hp.paragraph_format.space_after = Pt(2)
            r = hp.add_run(title)
            r.bold = True
            r.font.size = Pt(10.5)
            r.font.color.rgb = COLOR_PRIMARY

            doc.add_picture(str(img_path), width=Inches(6.2))
            
            cp = doc.add_paragraph()
            cp.paragraph_format.space_before = Pt(2)
            cp.paragraph_format.space_after = Pt(12)
            rc = cp.add_run(f"Caption: {caption}")
            rc.font.size = Pt(8.5)
            rc.font.italic = True
            rc.font.color.rgb = COLOR_MUTED

    # -------------------------------------------------------------------------
    # Section 8: Cryptographic Verification & State Integrity
    # -------------------------------------------------------------------------
    h7 = doc.add_heading("7. Cryptographic Verification & Immutable Data Audit", level=1)
    h7.runs[0].font.color.rgb = COLOR_PRIMARY

    audit_json = json.loads((AUDIT_DIR / "audit_findings.json").read_text(encoding="utf-8"))

    doc.add_paragraph(
        "To satisfy rigorous scientific provenance and reproducibility standards, all underlying source artifacts "
        "were cryptographically audited:\n"
        f"• Source Directory: {audit_json['source_directory']}\n"
        f"• Total Source Files Audited: {audit_json['source_files_count_pre']} files\n"
        f"• Pre- and Post-Analysis File Hashes: {audit_json['source_files_count_post']} files verified byte-identical (0 discrepancies)\n"
        f"• Production Memory Protection: data/ddiv_memory.db remained untouched (36,864 bytes, 0 QuixBugs records)\n"
        "• Network / Inference Boundary: Zero model calls, zero benchmark re-runs, zero cloud API fees ($0.00) during audit."
    )

    doc.save(str(OUTPUT_DOCX))
    print(f"Successfully generated publication-grade Word document at: {OUTPUT_DOCX}")

if __name__ == "__main__":
    build_document()
