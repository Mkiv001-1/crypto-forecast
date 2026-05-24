import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'core'))
from sqlite_manager import SQLiteManager

def _get_db_path():
    from scripts.server.config import get_db_path
    return get_db_path()


db = SQLiteManager(_get_db_path())

targets = ('claude-opus', 'gpt-4o')
with db._connect() as con:
    for name in targets:
        con.execute('UPDATE providers SET max_tokens=1000 WHERE name=?', (name,))
    rows = con.execute('SELECT name, max_tokens FROM providers WHERE type="ai"').fetchall()

print('Current max_tokens for all AI providers:')
for r in rows:
    print(f'  {r[0]}: {r[1]}')

