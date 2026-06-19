import sqlite3
import os
import glob
import chess
import chess.pgn
import datetime
import shutil
import io

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
        notes TEXT DEFAULT '',
        raw_pgn TEXT DEFAULT ''
    )''')
    
    # Safely add new columns if they don't exist
    for col in ["needs_review BOOLEAN DEFAULT 0", "exclude_stats BOOLEAN DEFAULT 0", 
                "total_plies INTEGER DEFAULT 0", "notes TEXT DEFAULT ''", "raw_pgn TEXT DEFAULT ''"]:
        try: c.execute(f"ALTER TABLE games ADD COLUMN {col}")
        except sqlite3.OperationalError: pass
    
    conn.commit()
    return conn

# New API function for ChessCam to write directly to the DB
def update_live_game(pgn_string, local_timestamp):
    conn = init_db()
    c = conn.cursor()
    
    # Parse the incoming PGN string to extract stats
    pgn_io = io.StringIO(pgn_string)
    game = chess.pgn.read_game(pgn_io)
    
    if not game:
        return {"status": "error", "message": "Invalid PGN"}
        
    node = game.end()
    plies = node.board().ply()
    is_checkmate = node.board().is_checkmate()
    
    white = game.headers.get("White", "Unknown")
    black = game.headers.get("Black", "Unknown")
    result = game.headers.get("Result", "*")
    
    c.execute("""
        INSERT INTO games (filename, white, black, result, date_played, is_empty, is_checkmate, needs_review, total_plies, raw_pgn) 
        VALUES ('live.pgn', ?, ?, ?, ?, ?, ?, 0, ?, ?)
        ON CONFLICT(filename) DO UPDATE SET
        white=excluded.white, black=excluded.black, result=excluded.result, 
        date_played=excluded.date_played, is_empty=excluded.is_empty, 
        is_checkmate=excluded.is_checkmate, total_plies=excluded.total_plies, raw_pgn=excluded.raw_pgn
    """, (white, black, result, local_timestamp, plies == 0, is_checkmate, plies, pgn_string))
    
    conn.commit()
    conn.close()
    return {"status": "success"}

def get_all_games():
    conn = init_db()
    c = conn.cursor()
    c.execute("""
        SELECT filename, white, black, result, date_played, is_favorite, is_empty, 
               is_checkmate, needs_review, exclude_stats, total_plies, notes 
        FROM games 
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

def get_raw_pgn(filename):
    conn = init_db()
    c = conn.cursor()
    c.execute("SELECT raw_pgn FROM games WHERE filename=?", (filename,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else ""

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
            c.execute("UPDATE games SET filename=? WHERE filename=?", (new_name, filename))
            target_filename = new_name

        c.execute("UPDATE games SET white=?, black=?, result=?, exclude_stats=?, date_played=?, needs_review=0, notes=? WHERE filename=?", 
                  (w, b, res, exclude, date_played, notes, target_filename))

    elif action == "mark_review":
        c.execute("UPDATE games SET needs_review = NOT needs_review WHERE filename=?", (filename,))
    elif action == "toggle_exclude":
        c.execute("UPDATE games SET exclude_stats = NOT exclude_stats WHERE filename=?", (filename,))
    elif action == "save_raw":
        c.execute("UPDATE games SET raw_pgn=? WHERE filename=?", (post_data.get("raw_text", ""), filename))
    elif action == "create_game":
        if not filename.endswith(".pgn"): filename += ".pgn"
        c.execute("INSERT INTO games (filename, raw_pgn, needs_review) VALUES (?, ?, 1)", (filename, post_data.get("raw_text", "")))
    elif action == "archive_live":
        new_name = post_data.get("new_name")
        if not new_name.endswith(".pgn"): new_name += ".pgn"
        
        # Move live to archive, keep data intact
        c.execute("UPDATE games SET filename=?, needs_review=1 WHERE filename='live.pgn'", (new_name,))
        # Create empty live template
        c.execute("INSERT INTO games (filename, white, black, is_empty, total_plies, raw_pgn) VALUES ('live.pgn', 'Unknown', 'Unknown', 1, 0, '')")
        
    elif action == "favorite":
        c.execute("UPDATE games SET is_favorite = NOT is_favorite WHERE filename=?", (filename,))
    elif action == "delete":
        c.execute("DELETE FROM games WHERE filename=?", (filename,))

    conn.commit()
    conn.close()