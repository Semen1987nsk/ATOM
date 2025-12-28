from pypdf import PdfReader
import re

reader = PdfReader("/workspaces/ATOM/broker-report-2025-12-01-2025-12-23.pdf")
text = ""
for page in reader.pages:
    text += page.extract_text() + "\n"

print(text)