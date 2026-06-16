import sqlite3
import os
import glob
import chess.pgn
import datetime
import shutil
import re

# Use Environment Variables for split mounting
DATA_DIR = os.getenv("DATA_DIR", "/data")
DB_DIR = os.getenv("DB_DIR", "/db")
os.makedirs(DB_DIR, exist_ok=True)
DB_PATH = os.path.join(DB_DIR, "chess.db")

def get_actual_path(filename):
    if not filename.endswith(".pgn") or "/" in filename or "\\" in filename:
        filename = "live.pgn"
    return os.path.join(DATA_DIR, filename)

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS games (
        filename TEXT PRIMARY KEY, 
        white TEXT, black TEXT, result TEXT, 
        date_played TIMESTAMP, is_favorite BOOLEAN DEFAULT 0, 
        is_empty BOOLEAN DEFAULT 0, is_checkmate BOOLEAN DEFAULT 0,
        needs_review BOOLEAN DEFAULT 0
    )''')
    # Safe migration for existing v2.0 databases
    try: c.execute("ALTER TABLE games ADD COLUMN needs_review BOOLEAN DEFAULT 0")
    except sqlite3.OperationalError: pass
    conn.commit()
    return conn

def sync_pgns_to_db():
    conn = init_db()
    c = conn.cursor()
    files = glob.glob(os.path.join(DATA_DIR, "*.pgn"))
    
    for f in files:
        filename = os.path.basename(f)
        
        try:
            with open(f, "r") as pgn_file: game = chess.pgn.read_game(pgn_file)
            
            if game:
                node = game.end()
                is_empty = node.board().ply() == 0
                
                # Delete empty archived files instantly
                if is_empty and filename != "live.pgn":
                    try:
                        os.remove(f)
                        c.execute("DELETE FROM games WHERE filename=?", (filename,))
                    except OSError: pass
                    continue
                
                c.execute("SELECT filename FROM games WHERE filename=?", (filename,))
                if not c.fetchone():
                    white = game.headers.get("White", "Unknown")
                    black = game.headers.get("Black", "Unknown")
                    result = game.headers.get("Result", "*")
                    date_str = game.headers.get("Date", datetime.datetime.now().strftime("%Y.%m.%d"))
                    is_checkmate = node.board().is_checkmate()
                    
                    # Flag as 'needs review' if it's not the live file
                    needs_review = 1 if filename != "live.pgn" else 0
                    
                    c.execute('''INSERT INTO games 
                        (filename, white, black, result, date_played, is_empty, is_checkmate, needs_review) 
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)''', 
                        (filename, white, black, result, date_str, is_empty, is_checkmate, needs_review))
        except Exception as e:
            print(f"Error parsing {filename}: {e}")
            
    conn.commit()
    conn.close()

def get_all_games():
    conn = init_db()
    c = conn.cursor()
    c.execute("SELECT * FROM games ORDER BY date_played DESC")
    columns = [col[0] for col in c.description]
    games = [dict(zip(columns, row)) for row in c.fetchall()]
    conn.close()
    return games

def update_game_action(post_data):
    action = post_data.get("action")
    filename = post_data.get("filename")
    conn = init_db()
    c = conn.cursor()
    
    if action == "edit_meta":
        w, b, res = post_data.get("white"), post_data.get("black"), post_data.get("result")
        c.execute("UPDATE games SET white=?, black=?, result=?, needs_review=0 WHERE filename=?", (w, b, res, filename))
        
        # Physically edit the PGN headers so changes are portable
        path = get_actual_path(filename)
        if os.path.exists(path):
            with open(path, "r") as f: content = f.read()
            if '[Result' in content: content = re.sub(r'\[Result ".*?"\]', f'[Result "{res}"]', content)
            else: content = f'[Result "{res}"]\n' + content
            if '[White' in content: content = re.sub(r'\[White ".*?"\]', f'[White "{w}"]', content)
            else: content = f'[White "{w}"]\n' + content
            if '[Black' in content: content = re.sub(r'\[Black ".*?"\]', f'[Black "{b}"]', content)
            else: content = f'[Black "{b}"]\n' + content
            with open(path, "w") as f: f.write(content)

    elif action == "save_raw":
        # Completely overwrite the PGN file (for the raw editor)
        path = get_actual_path(filename)
        with open(path, "w") as f: f.write(post_data.get("raw_text", ""))
        c.execute("DELETE FROM games WHERE filename=?", (filename,)) # Force a re-parse on next sync

    elif action == "favorite":
        c.execute("UPDATE games SET is_favorite = NOT is_favorite WHERE filename=?", (filename,))
    elif action == "delete":
        c.execute("DELETE FROM games WHERE filename=?", (filename,))
        try: os.remove(get_actual_path(filename))
        except OSError: pass
    elif action == "rename":
        new_name = post_data.get("new_name")
        if new_name and not new_name.endswith(".pgn"): new_name += ".pgn"
        c.execute("UPDATE games SET filename=? WHERE filename=?", (new_name, filename))
        try: shutil.move(get_actual_path(filename), get_actual_path(new_name))
        except OSError: pass

    conn.commit()
    conn.close()