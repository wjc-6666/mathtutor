import sqlite3
from app.config import DATA

def connect():
    c=sqlite3.connect(DATA/'mathtutor.sqlite3',timeout=30)
    c.row_factory=sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    c.executescript("""
    CREATE TABLE IF NOT EXISTS documents(id TEXT PRIMARY KEY,path TEXT UNIQUE,name TEXT,subject TEXT,digest TEXT,embedding TEXT,status TEXT);
    CREATE TABLE IF NOT EXISTS chunks(id TEXT PRIMARY KEY,doc TEXT REFERENCES documents(id) ON DELETE CASCADE,title TEXT,page INTEGER,section TEXT,subsection TEXT,text TEXT,vector TEXT);
    CREATE TABLE IF NOT EXISTS chats(id TEXT PRIMARY KEY,title TEXT);
    CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY AUTOINCREMENT,chat TEXT REFERENCES chats(id) ON DELETE CASCADE,role TEXT,content TEXT,sources TEXT);
    """)
    additions={'documents':{'title':'TEXT','diagnostics':'TEXT','index_revision':'TEXT'},'chunks':{'chapter':'TEXT','content_type':'TEXT','label':'TEXT','page_end':'INTEGER','printed_page':'TEXT','method':'TEXT'}}
    for table,columns in additions.items():
        present={row[1] for row in c.execute('PRAGMA table_info('+table+')')}
        for column,kind in columns.items():
            if column not in present:
                try:c.execute(f'ALTER TABLE {table} ADD COLUMN {column} {kind}')
                except sqlite3.OperationalError as e:
                    if 'duplicate column' not in str(e):raise
    c.commit()
    return c
