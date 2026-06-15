import http.server
import socketserver
import os
import chess
import chess.pgn
import chess.svg
import urllib.parse  # NEW: For parsing ?ply=10
import json          # NEW: For sending structured data

PORT = 8080
PGN_PATH = "/data/live.pgn"

class ChessHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed_url = urllib.parse.urlparse(self.path)
        clean_path = parsed_url.path
        query_components = urllib.parse.parse_qs(parsed_url.query)
        
        # --- 1. TIME-TRAVEL BOARD ENDPOINT ---
        if clean_path == "/board.svg":
            target_ply = int(query_components["ply"][0]) if "ply" in query_components else None
            
            if not os.path.exists(PGN_PATH):
                self.send_response(404)
                self.end_headers()
                return

            try:
                with open(PGN_PATH, "r") as pgn_file:
                    game = chess.pgn.read_game(pgn_file)
                    
                if game:
                    node = game
                    ply_count = 0
                    
                    # If looking at history, traverse the game tree up to the requested ply
                    if target_ply is not None:
                        while node.variations and ply_count < target_ply:
                            node = node.variation(0)
                            ply_count += 1
                    else:
                        # Otherwise, go to the very end of the live game
                        node = game.end()
                    
                    board = node.board()
                    last_move = node.move
                    svg_data = chess.svg.board(board=board, lastmove=last_move)
                    
                    self.send_response(200)
                    self.send_header("Content-type", "image/svg+xml")
                    self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                    self.end_headers()
                    self.wfile.write(svg_data.encode("utf-8"))
            except Exception as e:
                pass

        # --- 2. JSON GAME DATA ENDPOINT ---
        elif clean_path == "/game-data":
            if not os.path.exists(PGN_PATH):
                self.send_response(404)
                self.end_headers()
                return
                
            try:
                with open(PGN_PATH, "r") as pgn_file:
                    game = chess.pgn.read_game(pgn_file)
                    
                moves = []
                ply = 0
                if game:
                    node = game
                    while node.variations:
                        next_node = node.variation(0)
                        ply += 1
                        san = node.board().san(next_node.move)
                        moves.append({"ply": ply, "san": san})
                        node = next_node
                        
                data = {
                    "total_plies": ply,
                    "moves": moves
                }
                
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.send_header("Cache-Control", "no-cache, no-store")
                self.end_headers()
                self.wfile.write(json.dumps(data).encode("utf-8"))
            except Exception:
                pass

        # --- 3. THE INTERACTIVE DASHBOARD ---
        elif clean_path == "/":
            html_content = r"""
            
            
            
                
                
            
            
                
                
                    
                        Notation
                        Go Live
                    
                    Waiting for game...
                

                
            
            
            """
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(html_content.encode("utf-8"))

with socketserver.TCPServer(("", PORT), ChessHandler) as httpd:
    print(f"Serving interactive chess board on port {PORT}")
    httpd.serve_forever()