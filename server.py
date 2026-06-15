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

# --- 2. BULLETPROOF JSON DATA ENDPOINT ---
        elif clean_path == "/game-data":
            # If the file is missing, return a safe, empty JSON array instead of a 404 error
            if not os.path.exists(PGN_PATH):
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.send_header("Cache-Control", "no-cache, no-store")
                self.end_headers()
                self.wfile.write(json.dumps({"total_plies": 0, "moves": []}).encode("utf-8"))
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
            except Exception as e:
                # If the file is locked while writing, send empty JSON instead of crashing
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"total_plies": 0, "moves": []}).encode("utf-8"))

        # --- 3. THE INTERACTIVE DASHBOARD ---
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
                        font-family: 'Segoe UI', Tahoma, sans-serif;
                        display: flex; 
                        height: 100vh; 
                        overflow: hidden; 
                    }
                    #board-container {
                        flex: 1; 
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        padding: 2vmin;
                    }
                    #board-container svg { 
                        width: 100%; 
                        height: 100%; 
                        max-height: 95vh; 
                        object-fit: contain; 
                        filter: drop-shadow(0px 10px 30px rgba(0,0,0,0.6));
                    }
                    #sidebar {
                        width: 320px;
                        background-color: #242424;
                        display: flex;
                        flex-direction: column;
                        border-left: 1px solid #333;
                    }
                    .header {
                        padding: 15px;
                        background-color: #111;
                        color: #bbb;
                        font-weight: bold;
                        text-align: center;
                        letter-spacing: 1px;
                        text-transform: uppercase;
                        display: flex;
                        justify-content: space-between;
                        align-items: center;
                    }
                    #live-btn {
                        background: #2a5c8a;
                        color: white;
                        border: none;
                        padding: 4px 10px;
                        border-radius: 4px;
                        cursor: pointer;
                        font-size: 0.8rem;
                        display: none; 
                    }
                    #live-btn:hover { background: #3b76ad; }
                    #moves-container {
                        flex: 1;
                        padding: 15px 20px;
                        overflow-y: auto;
                        font-size: 1.15rem;
                        line-height: 2;
                    }
                    .turn-number { color: #666; font-size: 0.85em; margin-right: 5px; }
                    .move-span { 
                        cursor: pointer; 
                        padding: 3px 6px; 
                        border-radius: 4px; 
                        transition: background 0.1s;
                    }
                    .move-span:hover { background: #444; }
                    .move-active { background: #2a5c8a !important; color: white; }
                </style>
            </head>
            <body>
                <div id="board-container"></div>
                <div id="sidebar">
                    <div class="header">
                        <span>Notation</span>
                        <button id="live-btn" onclick="goLive()">Go Live</button>
                    </div>
                    <div id="moves-container">Waiting for game...</div>
                </div>

                <script>
                    let totalPlies = 0;
                    let currentViewPly = -1; 
                    let lastMovesData = [];

                    function goLive() {
                        currentViewPly = -1;
                        document.getElementById('live-btn').style.display = 'none';
                        updateBoard();
                        renderMovesList();
                        const container = document.getElementById('moves-container');
                        container.scrollTop = container.scrollHeight;
                    }

                    function viewPly(ply) {
                        currentViewPly = ply;
                        if (ply === totalPlies) {
                            goLive();
                            return;
                        }
                        document.getElementById('live-btn').style.display = 'block';
                        updateBoard();
                        renderMovesList();
                    }

                    function updateBoard() {
                        const noCache = '&t=' + Date.now();
                        const target = (currentViewPly === -1) ? '' : '?ply=' + currentViewPly;
                        const url = '/board.svg' + (target ? target + noCache : '?t=' + Date.now());
                        
                        fetch(url)
                            .then(r => r.text())
                            .then(svg => { 
                                document.getElementById('board-container').innerHTML = svg; 
                            })
                            .catch(err => console.error("Board load skipped"));
                    }

                    function renderMovesList() {
                        if (lastMovesData.length === 0) return;
                        
                        let html = '';
                        let activePly = (currentViewPly === -1) ? totalPlies : currentViewPly;

                        for(let i = 0; i < lastMovesData.length; i += 2) {
                            let turn = Math.floor(i / 2) + 1;
                            let white = lastMovesData[i];
                            let black = lastMovesData[i+1];
                            
                            html += `<div><span class="turn-number">${turn}.</span>`;
                            
                            let wClass = (white.ply === activePly) ? 'move-active' : '';
                            html += `<span class="move-span ${wClass}" onclick="viewPly(${white.ply})">${white.san}</span> `;
                            
                            if (black) {
                                let bClass = (black.ply === activePly) ? 'move-active' : '';
                                html += `<span class="move-span ${bClass}" onclick="viewPly(${black.ply})">${black.san}</span>`;
                            }
                            html += `</div>`;
                        }
                        
                        document.getElementById('moves-container').innerHTML = html;
                    }

                    function fetchState() {
                        fetch('/game-data?t=' + Date.now())
                            .then(r => {
                                if (!r.ok) throw new Error("Data not ready");
                                return r.json();
                            })
                            .then(data => {
                                // Added strict checks to prevent unhandled JS crashes
                                if (!data || typeof data.total_plies === 'undefined') return;

                                if (data.total_plies !== totalPlies) {
                                    totalPlies = data.total_plies;
                                    lastMovesData = data.moves;
                                    
                                    if (currentViewPly === -1) {
                                        updateBoard();
                                        renderMovesList();
                                        const container = document.getElementById('moves-container');
                                        container.scrollTop = container.scrollHeight;
                                    } else {
                                        renderMovesList();
                                    }
                                }
                            })
                            .catch(err => {
                                // Silently catch errors so the interval loop never dies
                            });
                    }

                    document.addEventListener('keydown', (e) => {
                        if (totalPlies === 0) return;
                        let current = (currentViewPly === -1) ? totalPlies : currentViewPly;
                        if (e.key === 'ArrowLeft') {
                            if (current > 0) viewPly(current - 1);
                        } else if (e.key === 'ArrowRight') {
                            if (current < totalPlies) viewPly(current + 1);
                        }
                    });

                    setInterval(fetchState, 1000);
                    fetchState(); 
                    updateBoard();
                </script>
            </body>
            </html>
            """
            self.send_response(200)
            # Add cache control here as well so the browser doesn't trap old javascript
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(html_content.encode("utf-8"))

with socketserver.TCPServer(("", PORT), ChessHandler) as httpd:
    print(f"Serving interactive chess board on port {PORT}")
    httpd.serve_forever()