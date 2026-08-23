#!/usr/bin/env python3
import sys
import os
import sqlite3
import argparse
import datetime

DEFAULT_HERMES_DIR = os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))
DB_PATH = os.environ.get("MEMPALACE_DB", os.path.join(DEFAULT_HERMES_DIR, "mempalace.db"))
STATE_DB = os.environ.get("STATE_DB", os.path.join(DEFAULT_HERMES_DIR, "state.db"))

def init_db():
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS memory_drawers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        wing TEXT NOT NULL,
        content TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    """)
    cur.execute("""
    CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
        wing, content, content=memory_drawers, content_rowid=id
    );
    """)
    cur.execute("""
    CREATE TRIGGER IF NOT EXISTS memory_ai AFTER INSERT ON memory_drawers BEGIN
        INSERT INTO memory_fts(rowid, wing, content) VALUES (new.id, new.wing, new.content);
    END;
    """)
    con.commit()
    con.close()

def save_memory(wing, content):
    init_db()
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur.execute("INSERT INTO memory_drawers (wing, content, created_at) VALUES (?, ?, ?)", (wing, content, now))
    con.commit()
    con.close()
    print(f"SUCCESS: Stored memory drawer in [{wing}] at {now}")

def search_memory(query):
    init_db()
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    try:
        cur.execute("""
        SELECT d.id, d.wing, d.content, d.created_at
        FROM memory_fts f
        JOIN memory_drawers d ON f.rowid = d.id
        WHERE memory_fts MATCH ?
        ORDER BY rank
        LIMIT 10;
        """, (query,))
        rows = cur.fetchall()
    except Exception:
        rows = []
        
    if not rows:
        terms = query.split()
        like_clauses = " AND ".join(["(content LIKE ? OR wing LIKE ?)" for _ in terms])
        params = []
        for t in terms:
            params.extend([f"%{t}%", f"%{t}%"])
        cur.execute(f"SELECT id, wing, content, created_at FROM memory_drawers WHERE {like_clauses} ORDER BY id DESC LIMIT 10", params)
        rows = cur.fetchall()
        
    con.close()
    if not rows:
        print(f"No memories found matching '{query}'.")
        return
        
    print(f"=== FOUND {len(rows)} RELEVANT MEMORY DRAWERS ===")
    for row in rows:
        print(f"[{row[1].upper()} | {row[3]}]")
        print(f"{row[2]}")
        print("-" * 40)

def list_memories():
    init_db()
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("SELECT id, wing, content, created_at FROM memory_drawers ORDER BY id DESC LIMIT 20")
    rows = cur.fetchall()
    con.close()
    if not rows:
        print("MemPalace is currently empty.")
        return
    print(f"=== LATEST {len(rows)} MEMORY DRAWERS ===")
    for row in rows:
        print(f"#{row[0]} [{row[1].upper()} | {row[3]}] {row[2][:120]}...")

def get_recent_cross_channel(limit=10):
    if not os.path.exists(STATE_DB):
        print(f"State database not found at {STATE_DB}")
        return
    con = sqlite3.connect(STATE_DB)
    cur = con.cursor()
    cur.execute("SELECT s.source, m.role, m.content, m.timestamp FROM messages m JOIN sessions s ON m.session_id = s.id ORDER BY m.timestamp DESC LIMIT ?", (limit,))
    rows = cur.fetchall()
    con.close()
    
    if not rows:
        print("No recent messages found.")
        return
        
    print(f"=== LAST {len(rows)} MESSAGES ACROSS ALL PLATFORMS ===")
    for src, role, content, ts in reversed(rows):
        t_str = datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S") if ts else "N/A"
        clean_c = (content or "").strip().replace("\n", " ")
        if len(clean_c) > 160:
            clean_c = clean_c[:160] + "..."
        print(f"[{t_str} | {src.upper()} | {role}]: {clean_c}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Hermes MemPalace & Cross-Channel Memory Helper")
    sub = parser.add_subparsers(dest="cmd")
    
    p_save = sub.add_parser("save")
    p_save.add_argument("--wing", default="general", help="Category / Wing (infra, devices, fixes, prefs, general)")
    p_save.add_argument("content", help="Verbatim memory content")
    
    p_search = sub.add_parser("search")
    p_search.add_argument("query", help="Search query")
    
    p_list = sub.add_parser("list")
    
    p_recent = sub.add_parser("recent")
    p_recent.add_argument("--limit", type=int, default=10, help="Number of recent messages to fetch")
    
    args = parser.parse_args()
    if args.cmd == "save":
        save_memory(args.wing, args.content)
    elif args.cmd == "search":
        search_memory(args.query)
    elif args.cmd == "list":
        list_memories()
    elif args.cmd == "recent":
        get_recent_cross_channel(args.limit)
    else:
        parser.print_help()
