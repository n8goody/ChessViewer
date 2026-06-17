import sqlite3
import os
import glob
import chess
import chess.pgn
import datetime
import shutil

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
        needs_review BOOLEAN DEFAULT 0,
        exclude_stats BOOLEAN DEFAULT 0,
        total_plies INTEGER DEFAULT 0,
        notes TEXT DEFAULT ''
    )''')
    
    try: c.execute("ALTER TABLE games ADD COLUMN needs_review BOOLEAN DEFAULT 0")
    except sqlite3.OperationalError: pass
    try: c.execute("ALTER TABLE games ADD COLUMN exclude_stats BOOLEAN DEFAULT 0")
    except sqlite3.OperationalError: pass
    try: c.execute("ALTER TABLE games ADD COLUMN total_plies INTEGER DEFAULT 0")
    except sqlite3.OperationalError: pass
    try: c.execute("ALTER TABLE games ADD COLUMN notes TEXT DEFAULT ''")
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
                plies = node.board().ply()
                is_empty = plies == 0
                
                if is_empty and filename != "live.pgn":
                    try:
                        os.remove(f)
                        c.execute("DELETE FROM games WHERE filename=?", (filename,))
                    except OSError: pass
                    continue
                
                c.execute("SELECT total_plies FROM games WHERE filename=?", (filename,))
                row = c.fetchone()
                
                if row and row[0] == 0 and plies > 0:
                    c.execute("UPDATE games SET total_plies=? WHERE filename=?", (plies, filename))
                
                if not row:
                    white = game.headers.get("White", "Unknown")
                    black = game.headers.get("Black", "Unknown")
                    result = game.headers.get("Result", "*")
                    notes = game.headers.get("Notes", "")
                    
                    d_str = game.headers.get("Date", "")
                    t_str = game.headers.get("Time", "00:00:00")
                    if not d_str or d_str == "????.??.??":
                        date_str = datetime.datetime.fromtimestamp(os.path.getmtime(f)).strftime("%Y-%m-%d %H:%M:%S")
                    else:
                        date_str = f"{d_str.replace('.', '-')} {t_str}".strip()
                    
                    is_checkmate = node.board().is_checkmate()
                    
                    if is_checkmate and result == "*":
                        result = "0-1" if node.board().turn == chess.WHITE else "1-0"
                    
                    needs_review = 1 if filename != "live.pgn" else 0
                    
                    c.execute('''INSERT INTO games 
                        (filename, white, black, result, date_played, is_empty, is_checkmate, needs_review, total_plies, notes) 
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', 
                        (filename, white, black, result, date_str, is_empty, is_checkmate, needs_review, plies, notes))
        except Exception as e:
            print(f"Error parsing {filename}: {e}")
            
    conn.commit()
    conn.close()

def get_all_games():
    conn = init_db()
    c = conn.cursor()
    c.execute("""
        SELECT * FROM games 
        ORDER BY 
            needs_review DESC,
            CASE WHEN date_played = '' OR date_played LIKE '%????%' THEN 1 ELSE 0 END ASC,
            date_played DESC, 
            filename DESC
    """)
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
        new_name = post_data.get("new_name")
        exclude = post_data.get("exclude_stats", 0)
        date_played = post_data.get("date_played", "")
        notes = post_data.get("notes", "")
        
        target_filename = filename
        if new_name and new_name != filename:
            if not new_name.endswith(".pgn"): new_name += ".pgn"
            try: 
                shutil.move(get_actual_path(filename), get_actual_path(new_name))
                c.execute("UPDATE games SET filename=? WHERE filename=?", (new_name, filename))
                target_filename = new_name
            except OSError: pass

        c.execute("UPDATE games SET white=?, black=?, result=?, exclude_stats=?, date_played=?, needs_review=0, notes=? WHERE filename=?", 
                  (w, b, res, exclude, date_played, notes, target_filename))
        
        path = get_actual_path(target_filename)
        if os.path.exists(path):
            try:
                with open(path, "r") as f: game = chess.pgn.read_game(f)
                if game:
                    game.headers["White"] = w
                    game.headers["Black"] = b
                    game.headers["Result"] = res
                    if notes: game.headers["Notes"] = notes
                    elif "Notes" in game.headers: del game.headers["Notes"]
                    
                    dp_parts = date_played.split(" ")
                    game.headers["Date"] = dp_parts[0].replace("-", ".") if len(dp_parts) > 0 else "????.??.??"
                    game.headers["Time"] = dp_parts[1] if len(dp_parts) > 1 else "00:00:00"
                    
                    with open(path, "w") as f: f.write(str(game))
            except Exception: pass

    elif action == "mark_review":
        c.execute("UPDATE games SET needs_review = NOT needs_review WHERE filename=?", (filename,))
    elif action == "toggle_exclude":
        c.execute("UPDATE games SET exclude_stats = NOT exclude_stats WHERE filename=?", (filename,))
    
    elif action == "save_raw":
        path = get_actual_path(filename)
        with open(path, "w") as f: f.write(post_data.get("raw_text", ""))
        c.execute("DELETE FROM games WHERE filename=?", (filename,))
        conn.commit()
        sync_pgns_to_db()
        
    elif action == "create_game":
        if not filename.endswith(".pgn"): filename += ".pgn"
        path = get_actual_path(filename)
        with open(path, "w") as f: f.write(post_data.get("raw_text", ""))
        conn.commit()
        sync_pgns_to_db()

    elif action == "archive_live":
        new_name = post_data.get("new_name")
        if not new_name.endswith(".pgn"): new_name += ".pgn"
        try: shutil.move(get_actual_path("live.pgn"), get_actual_path(new_name))
        except OSError: pass
        
        # Clear out live.pgn
        with open(get_actual_path("live.pgn"), "w") as f: f.write("")
        c.execute("DELETE FROM games WHERE filename='live.pgn'")
        conn.commit()
        sync_pgns_to_db()

    elif action == "favorite":
        c.execute("UPDATE games SET is_favorite = NOT is_favorite WHERE filename=?", (filename,))
    elif action == "delete":
        c.execute("DELETE FROM games WHERE filename=?", (filename,))
        try: os.remove(get_actual_path(filename))
        except OSError: pass

    if action not in ["save_raw", "create_game", "archive_live"]:
        conn.commit()
    conn.close()