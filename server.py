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
        clean_path = self.path.split('?')[0]
        if clean_path == "/board.svg":
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
        elif clean_path == "/moves-raw":
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
                        exporter = chess.pgn.StringExporter(headers=False, variations=False, comments=False)
                        moves_text = game.accept(exporter)
                
                self.send_response(200)
                self.send_header("Content-type", "text/plain")
                self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                self.end_headers()
                self.wfile.write(moves_text.encode("utf-8"))
            except Exception as e:
                pass # Silently fail on read-lock errors
                
        # --- 3. THE UNIFIED DASHBOARD ---
        elif clean_path == "/":
            html_content = r"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <style>
                    body { 
                        margin: 0; 
                        background-color: #1c1c1c; 
                        color: #e1e1e1;
                        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                        display: flex; 
                        flex-direction: row;
                        height: 100vh; 
                        overflow: hidden; 
                    }
                    /* Left side: The Board */
                    #board-container {
                        flex: 1;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        padding: 20px;
                        box-sizing: border-box;
                    }
                    #board-container svg { 
                        max-height: 100%; 
                        max-width: 100%; 
                        border-radius: 4px;
                        box-shadow: 0px 10px 30px rgba(0,0,0,0.6); /* Adds depth */
                    }
                    /* Right side: The Moves */
                    #sidebar {
                        width: 300px;
                        background-color: #242424;
                        display: flex;
                        flex-direction: column;
                        border-left: 1px solid #333;
                        box-shadow: -5px 0px 15px rgba(0,0,0,0.3);
                    }
                    .header {
                        padding: 15px;
                        background-color: #111;
                        color: #bbb;
                        font-weight: bold;
                        text-align: center;
                        letter-spacing: 2px;
                        font-size: 0.9rem;
                        text-transform: uppercase;
                        border-bottom: 1px solid #333;
                    }
                    #moves-container {
                        flex: 1;
                        padding: 20px;
                        overflow-y: auto;
                        font-size: 1.15rem;
                        line-height: 1.8;
                    }
                    /* Makes the move numbers (1. 2.) dim so the piece letters pop */
                    .turn-number {
                        color: #666;
                        font-size: 0.85em;
                        margin-right: 5px;
                        margin-left: 8px;
                    }
                </style>
            </head>
            <body>
                <div id="board-container"></div>
                <div id="sidebar">
                    <div class="header">Live Notation</div>
                    <div id="moves-container">Waiting for moves...</div>
                </div>

                <script>
                    let lastMoves = "";

                    function fetchData() {
                        const noCache = '?t=' + new Date().getTime();
                        
                        // Fetch the SVG Board
                        fetch('/board.svg' + noCache)
                            .then(response => response.text())
                            .then(svg => { 
                                document.getElementById('board-container').innerHTML = svg; 
                            });

                        // Fetch the text moves
                        fetch('/moves-raw' + noCache)
                            .then(response => response.text())
                            .then(moves => { 
                                if (moves !== lastMoves && moves !== "No game found.") {
                                    // Use regex to find numbers (e.g., "1.") and wrap them in styling tags
                                    let formattedMoves = moves.replace(/(\d+\.)/g, '<span class="turn-number">$1</span>');
                                    
                                    const container = document.getElementById('moves-container');
                                    container.innerHTML = formattedMoves;
                                    
                                    // Auto-scroll to the bottom ONLY when a new move is actually added
                                    container.scrollTop = container.scrollHeight;
                                    lastMoves = moves;
                                }
                            });
                    }
                    // Fetch fresh data every 1 second
                    setInterval(fetchData, 1000);
                    fetchData(); // Load immediately on open
                </script>
            </body>
            </html>
            """
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(html_content.encode("utf-8"))
        
        # --- CATCH ALL ---
        else:
            self.send_response(404)
            self.end_headers()

with socketserver.TCPServer(("", PORT), ChessHandler) as httpd:
    print(f"Serving interactive chess board on port {PORT}")
    httpd.serve_forever()