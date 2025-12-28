from pypdf import PdfReader

reader = PdfReader("/workspaces/ATOM/broker-report-2025-12-01-2025-12-23.pdf")

found = False
for i, page in enumerate(reader.pages):
    text = page.extract_text()
    if "Система" in text and "Покупка" in text:
        print(f"--- Page {i+1} ---")
        print(text)
        found = True

if not found:
    print("Trade for Sistema not found in the text.")
