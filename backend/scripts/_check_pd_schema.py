"""Quick smoke check: pd_consents + User.deletion_requested_at after migration."""
import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "atom.db"
print(f"DB path: {DB}")

c = sqlite3.connect(str(DB))
cur = c.cursor()

print("\nTables:")
for r in cur.execute("select name from sqlite_master where type='table' order by name").fetchall():
    print(" -", r[0])

print("\nusers.deletion_requested_at:")
cur.execute("pragma table_info(users)")
cols = [r[1] for r in cur.fetchall()]
print(" present" if "deletion_requested_at" in cols else " MISSING")

print("\npd_consents columns:")
cur.execute("pragma table_info(pd_consents)")
for r in cur.fetchall():
    print(f" - {r[1]:30} {r[2]}")

print("\nIndexes on pd_consents:")
for r in cur.execute("select name from sqlite_master where type='index' and tbl_name='pd_consents'").fetchall():
    print(" -", r[0])

cur.execute("select count(*) from users")
print(f"\nusers count: {cur.fetchone()[0]}")

if "pd_consents" in [r[0] for r in cur.execute("select name from sqlite_master where type='table'").fetchall()]:
    cur.execute("select count(*) from pd_consents")
    print(f"pd_consents count: {cur.fetchone()[0]}")
else:
    print("pd_consents count: TABLE MISSING")

cur.execute("select version_num from alembic_version")
print(f"alembic_version: {cur.fetchone()[0]}")
