import http.server
import socketserver
import chess
import chess.pgn
import chess.svg
import os

PORT = 8080
PGN_PATH = "/data/live.pgn"

class ChessHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/board.svg":
            if not os.path.exists(PGN_PATH):
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"PGN file not found. Make sure your volume is mounted correctly.")
                return

            try:
                with open(PGN_PATH, "r") as pgn_file:
                    game = chess.pgn.read_game(pgn_file)
                    if game is None:
                        # Fallback to an empty starting board if the PGN file is currently empty
                        board = chess.Board()
                    else:
                        board = game.end().board()
                
                # Render the current state as an SVG graphic
                svg_data = chess.svg.board(board=board, size=400)
                
                self.send_response(200)
                self.send_header("Content-type", "image/svg+xml")
                # CRITICAL: Prevent Home Assistant and browsers from caching old board states
                self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                self.send_header("Pragma", "no-cache")
                self.send_header("Expires", "0")
                self.end_headers()
                self.wfile.write(svg_data.encode("utf-8"))
                
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(f"Error processing PGN: {e}".encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

with socketserver.TCPServer(("", PORT), ChessHandler) as httpd:
    print(f"Serving interactive chess board on port {PORT}")
    httpd.serve_forever()