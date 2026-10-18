"""Convert DDIV Comprehensive DOCX report to PDF using Word COM automation."""

import argparse
import os
from pathlib import Path
import win32com.client


def convert_to_pdf(docx_path, pdf_path):
  docx_file = Path(docx_path).resolve()
  pdf_file = Path(pdf_path).resolve()

  print(f"Opening {docx_file}...")
  word = win32com.client.DispatchEx("Word.Application")
  word.Visible = False
  try:
    doc = word.Documents.Open(str(docx_file))
    print(f"Exporting to {pdf_file}...")
    doc.SaveAs2(str(pdf_file), FileFormat=17)  # 17 = wdFormatPDF
    doc.Close()
    print(f"Success! Generated PDF of size {os.path.getsize(pdf_file):,} bytes.")
  except Exception as e:
    print("Error:", e)
    raise
  finally:
    word.Quit()


def main():
  parser = argparse.ArgumentParser(
      description="Convert DOCX to PDF via Word COM."
  )
  parser.add_argument(
      "--docx",
      type=str,
      default=r"D:\PROJECTS\DDIV\results\ddiv_comprehensive_benchmark_report_corrected_20261017\DDIV_Complete_QuixBugs_Benchmark_Report.docx",
      help="Source DOCX path.",
  )
  parser.add_argument(
      "--pdf",
      type=str,
      default=r"D:\PROJECTS\DDIV\results\ddiv_comprehensive_benchmark_report_corrected_20261017\DDIV_Complete_QuixBugs_Benchmark_Report.pdf",
      help="Target PDF path.",
  )
  args = parser.parse_args()
  convert_to_pdf(args.docx, args.pdf)


if __name__ == "__main__":
  main()
