import sqlite3
import os
import glob
import chess.pgn
import datetime
import shutil

DATA_DIR = "/data"
DB_PATH = os.path.join(DATA_DIR, "chess.db")

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
        is_empty BOOLEAN DEFAULT 0, is_checkmate BOOLEAN DEFAULT 0
    )''')
    conn.commit()
    return conn

def sync_pgns_to_db():
    conn = init_db()
    c = conn.cursor()
    files = glob.glob(os.path.join(DATA_DIR, "*.pgn"))
    
    for f in files:
        filename = os.path.basename(f)
        
        # Parse the file to check for data
        try:
            with open(f, "r") as pgn_file:
                game = chess.pgn.read_game(pgn_file)
            
            if game:
                node = game.end()
                is_empty = node.board().ply() == 0
                
                # FEATURE: Delete empty PGN files permanently (ignore live.pgn)
                if is_empty and filename != "live.pgn":
                    try:
                        os.remove(f)
                        c.execute("DELETE FROM games WHERE filename=?", (filename,))
                    except OSError: pass
                    continue
                
                # Check if it needs to be added to DB
                c.execute("SELECT filename FROM games WHERE filename=?", (filename,))
                if not c.fetchone():
                    white = game.headers.get("White", "Unknown")
                    black = game.headers.get("Black", "Unknown")
                    result = game.headers.get("Result", "*")
                    date_str = game.headers.get("Date", datetime.datetime.now().strftime("%Y.%m.%d"))
                    is_checkmate = node.board().is_checkmate()
                    
                    c.execute('''INSERT INTO games 
                        (filename, white, black, result, date_played, is_empty, is_checkmate) 
                        VALUES (?, ?, ?, ?, ?, ?, ?)''', 
                        (filename, white, black, result, date_str, is_empty, is_checkmate))
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
    
    if action == "edit_players":
        c.execute("UPDATE games SET white=?, black=? WHERE filename=?", 
                  (post_data.get("white"), post_data.get("black"), filename))
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