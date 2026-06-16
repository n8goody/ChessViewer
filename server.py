import http.server
import socketserver
import urllib.parse
import json
import chess
import chess.pgn
import chess.svg
import database

PORT = 8080

class ChessHandler(http.server.SimpleHTTPRequestHandler):

    def do_POST(self):
        parsed_url = urllib.parse.urlparse(self.path)
        if parsed_url.path == "/api/game/update":
            content_length = int(self.headers['Content-Length'])
            post_data = json.loads(self.rfile.read(content_length).decode('utf-8'))
            
            database.update_game_action(post_data)
            
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"status":"success"}')

    def do_GET(self):
        database.sync_pgns_to_db() 
        
        parsed_url = urllib.parse.urlparse(self.path)
        clean_path = parsed_url.path
        query_components = urllib.parse.parse_qs(parsed_url.query)
        
        filename = query_components.get("file", ["live.pgn"])[0]
        pgn_path = database.get_actual_path(filename)

        if clean_path == "/board.svg":
            target_ply = int(query_components["ply"][0]) if "ply" in query_components else None
            is_flipped = query_components.get("flipped", ["false"])[0] == "true"
            best_move_san = query_components.get("bestmove", [None])[0]
            orientation = chess.BLACK if is_flipped else chess.WHITE
            
            try:
                with open(pgn_path, "r") as pgn_file: game = chess.pgn.read_game(pgn_file)
                node = game
                ply_count = 0
                if target_ply is not None:
                    while node.variations and ply_count < target_ply:
                        node = node.variation(0)
                        ply_count += 1
                else: node = game.end()
                
                # FEATURE: Draw Best Move Arrow
                arrows = []
                if best_move_san:
                    try:
                        move = node.board().parse_san(best_move_san)
                        # #48bb7899 is a translucent green arrow
                        arrows.append(chess.svg.Arrow(move.from_square, move.to_square, color="#48bb7899"))
                    except ValueError: pass
                
                svg_data = chess.svg.board(board=node.board(), lastmove=node.move, orientation=orientation, arrows=arrows)
                self.send_response(200)
                self.send_header("Content-type", "image/svg+xml")
                self.end_headers()
                self.wfile.write(svg_data.encode("utf-8"))
            except Exception: pass

        elif clean_path == "/game-data":
            try:
                with open(pgn_path, "r") as pgn_file: game = chess.pgn.read_game(pgn_file)
                moves = []
                ply = 0
                
                def calc_material(board):
                    score = 0
                    for p in board.piece_map().values():
                        val = {"P":1, "N":3, "B":3, "R":5, "Q":9}.get(p.symbol().upper(), 0)
                        score += val if p.color == chess.WHITE else -val
                    return score

                if game:
                    moves.append({"ply": 0, "san": "Start", "fen": game.board().fen(), "material": calc_material(game.board())})
                    node = game
                    while node.variations:
                        next_node = node.variation(0)
                        ply += 1
                        moves.append({
                            "ply": ply, "san": node.board().san(next_node.move), 
                            "fen": next_node.board().fen(), "material": calc_material(next_node.board())
                        })
                        node = next_node
                        
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"total_plies": ply, "moves": moves}).encode("utf-8"))
            except Exception:
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"total_plies": 0, "moves": []}')

        elif clean_path == "/api/games":
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(database.get_all_games()).encode("utf-8"))

        elif clean_path == "/" or clean_path == "/analysis":
            try:
                with open("index.html", "r", encoding="utf-8") as f:
                    html_content = f.read()
                self.send_response(200)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                self.wfile.write(html_content.encode("utf-8"))
            except FileNotFoundError:
                self.send_error(404, "index.html not found in server directory")

with socketserver.TCPServer(("", PORT), ChessHandler) as httpd:
    print(f"Serving Ultimate Homelab Chess (v2.1) on port {PORT}")
    httpd.serve_forever()