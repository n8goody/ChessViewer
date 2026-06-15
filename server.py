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
        elif self.path == "/live-board":
            html_content = """
            <!DOCTYPE html>
            <html>
            <head>
                <style>
                    /* Centers the board perfectly and matches HA dark mode */
                    body { 
                        margin: 0; 
                        background-color: #1c1c1c; 
                        display: flex; 
                        justify-content: center; 
                        align-items: center; 
                        height: 100vh; 
                        overflow: hidden; 
                    }
                    svg { max-height: 100%; max-width: 100%; }
                </style>
            </head>
            <body>
                <div id="board-container"></div>
                <script>
                    function fetchBoard() {
                        // The '?t=' trick forces the browser to ignore its cache and pull a fresh image
                        fetch('/board.svg?t=' + new Date().getTime())
                            .then(response => response.text())
                            .then(svg => { 
                                document.getElementById('board-container').innerHTML = svg; 
                            })
                            .catch(err => console.error("Waiting for board..."));
                    }
                    // Fetch a new board every 1000 milliseconds (1 second)
                    setInterval(fetchBoard, 1000);
                    fetchBoard(); // Load instantly on page open
                </script>
            </body>
            </html>
            """
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(html_content.encode("utf-8"))
        # --- NEW NOTATION ENDPOINT ---
        elif self.path == "/moves":
            if not os.path.exists(PGN_PATH):
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"No game found.")
                return
            
            try:
                with open(PGN_PATH, "r") as pgn_file:
                    game = chess.pgn.read_game(pgn_file)
                    if game is None:
                        moves_text = "Waiting for first move..."
                    else:
                        # Extract ONLY the moves, stripping out headers like [Site]
                        exporter = chess.pgn.StringExporter(headers=False, variations=False, comments=False)
                        moves_text = game.accept(exporter)
                
                # Create an auto-refreshing HTML page that auto-scrolls to the newest move
                html_content = f"""
                
                
                
                    
                    
                
                
                    
{moves_text}

                    
                
                
                """
                
                self.send_response(200)
                self.send_header("Content-type", "text/html")
                # Force bypass all caches
                self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                self.end_headers()
                self.wfile.write(html_content.encode("utf-8"))
                
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(f"Error: {e}".encode("utf-8"))
        
        # --- CATCH ALL ---
        else:
            self.send_response(404)
            self.end_headers()

with socketserver.TCPServer(("", PORT), ChessHandler) as httpd:
    print(f"Serving interactive chess board on port {PORT}")
    httpd.serve_forever()