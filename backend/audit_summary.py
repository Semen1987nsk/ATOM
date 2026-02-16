"""Wrapper that runs audit and shows ONLY the error table + summary."""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Capture output
from io import StringIO
import contextlib

buf = StringIO()
with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(StringIO()):
    from audit_trades import run_audit
    run_audit()

output = buf.getvalue()
lines = output.split('\n')

# Print only the table + summary sections, skip raw data dumps
printing = False
skip_section = False

for line in lines:
    # Start printing at the first ===== header (the table)
    if '=====' in line and not skip_section:
        printing = True
    
    # Stop at raw data dumps
    if 'ПОЛНЫЕ ДАННЫЕ' in line or 'ДАННЫЕ ИЗ БД' in line:
        skip_section = True
        printing = False
    
    # Resume at final summary line
    if 'Аудит завершён' in line:
        printing = True
        skip_section = False
    
    if printing:
        print(line)
