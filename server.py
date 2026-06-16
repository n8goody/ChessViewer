import http.server
import socketserver
import os
import glob
import chess
import chess.pgn
import chess.svg
import urllib.parse
import json

PORT = 8080
DATA_DIR = "/data" # Base directory for all your PGNs

class ChessHandler(http.server.SimpleHTTPRequestHandler):
    def get_actual_path(self, query_components):
        # Default to live.pgn, but allow selecting archived games
        requested_file = query_components.get("file", ["live.pgn"])[0]
        # Basic security: prevent directory traversal
        if not requested_file.endswith(".pgn") or "/" in requested_file or "\\" in requested_file:
            requested_file = "live.pgn"
        return os.path.join(DATA_DIR, requested_file)

    def do_GET(self):
        parsed_url = urllib.parse.urlparse(self.path)
        clean_path = parsed_url.path
        query_components = urllib.parse.parse_qs(parsed_url.query)
        
        pgn_path = self.get_actual_path(query_components)

        # --- 1. TIME-TRAVEL & FLIPPED BOARD ENDPOINT ---
        if clean_path == "/board.svg":
            target_ply = int(query_components["ply"][0]) if "ply" in query_components else None
            is_flipped = query_components.get("flipped", ["false"])[0] == "true"
            orientation = chess.BLACK if is_flipped else chess.WHITE
            
            if not os.path.exists(pgn_path):
                self.send_response(404)
                self.end_headers()
                return

            try:
                with open(pgn_path, "r") as pgn_file:
                    game = chess.pgn.read_game(pgn_file)
                    
                if game:
                    node = game
                    ply_count = 0
                    
                    if target_ply is not None:
                        while node.variations and ply_count < target_ply:
                            node = node.variation(0)
                            ply_count += 1
                    else:
                        node = game.end()
                    
                    board = node.board()
                    last_move = node.move
                    svg_data = chess.svg.board(board=board, lastmove=last_move, orientation=orientation)
                    
                    self.send_response(200)
                    self.send_header("Content-type", "image/svg+xml")
                    self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                    self.end_headers()
                    self.wfile.write(svg_data.encode("utf-8"))
            except Exception:
                pass

        # --- 2. GAME DATA ENDPOINT (Now includes FEN for Stockfish) ---
        elif clean_path == "/game-data":
            if not os.path.exists(pgn_path):
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"total_plies": 0, "moves": []}).encode("utf-8"))
                return
                
            try:
                with open(pgn_path, "r") as pgn_file:
                    game = chess.pgn.read_game(pgn_file)
                    
                moves = []
                ply = 0
                if game:
                    node = game
                    # Always include the starting FEN at ply 0
                    moves.append({"ply": 0, "san": "Start", "fen": node.board().fen()})
                    while node.variations:
                        next_node = node.variation(0)
                        ply += 1
                        san = node.board().san(next_node.move)
                        fen = next_node.board().fen()
                        moves.append({"ply": ply, "san": san, "fen": fen})
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
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"total_plies": 0, "moves": []}).encode("utf-8"))

        # --- 3. ARCHIVE SCANNER ---
        elif clean_path == "/games-list":
            files = glob.glob(os.path.join(DATA_DIR, "*.pgn"))
            basenames = [os.path.basename(f) for f in files]
            if "live.pgn" not in basenames: 
                basenames.insert(0, "live.pgn")
            
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(list(set(basenames))).encode("utf-8"))

        # --- 4. THE INTERACTIVE DASHBOARD (Live & Analysis) ---
        elif clean_path == "/" or clean_path == "/analysis":
            is_analysis = "true" if clean_path == "/analysis" else "false"
            
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0"> <title>Chess Dashboard</title>
                <style>
                    body {{ 
                        margin: 0; 
                        background-color: #1c1c1c; 
                        color: #e1e1e1;
                        font-family: 'Segoe UI', Tahoma, sans-serif;
                        display: flex; 
                        height: 100vh; 
                        overflow: hidden; 
                    }}
                    
                    /* Analysis Eval Bar */
                    #eval-container {{
                        width: 30px;
                        background: #333;
                        display: none; /* Hidden by default */
                        flex-direction: column;
                        justify-content: flex-end;
                        margin: 2vmin 0 2vmin 2vmin;
                        border-radius: 4px;
                        overflow: hidden;
                        position: relative;
                    }}
                    #eval-fill {{
                        width: 100%;
                        background: #f0d9b5; /* White advantage */
                        height: 50%; /* Center start */
                        transition: height 0.5s ease-in-out;
                    }}
                    #eval-score {{
                        position: absolute;
                        width: 100%;
                        text-align: center;
                        top: 50%;
                        transform: translateY(-50%);
                        font-weight: bold;
                        color: #888;
                        font-size: 0.8rem;
                        mix-blend-mode: difference;
                    }}

                    #board-container {{
                        flex: 1; 
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        padding: 2vmin;
                    }}
                    #board-container svg {{ 
                        width: 100%; 
                        height: 100%; 
                        max-height: 95vh; 
                        object-fit: contain; 
                        filter: drop-shadow(0px 10px 30px rgba(0,0,0,0.6));
                    }}
                    
                    #sidebar {{
                        width: 340px;
                        background-color: #242424;
                        display: flex;
                        flex-direction: column;
                        border-left: 1px solid #333;
                    }}
                    
                    /* Controls UI */
                    .controls-bar {{
                        padding: 10px;
                        background-color: #111;
                        display: flex;
                        flex-direction: column;
                        gap: 10px;
                        border-bottom: 1px solid #333;
                    }}
                    .controls-row {{
                        display: flex;
                        justify-content: space-between;
                        gap: 8px;
                    }}
                    select, button {{
                        background: #2a5c8a;
                        color: white;
                        border: none;
                        padding: 6px 10px;
                        border-radius: 4px;
                        cursor: pointer;
                        font-size: 0.9rem;
                        flex: 1;
                    }}
                    select {{ background: #333; border: 1px solid #555; }}
                    button:hover {{ background: #3b76ad; }}
                    
                    /* Stockfish Engine Readout */
                    #engine-readout {{
                        display: none;
                        padding: 10px;
                        background: #1a365d;
                        font-size: 0.9rem;
                        border-bottom: 1px solid #333;
                    }}
                    .best-move {{ color: #63b3ed; font-weight: bold; font-size: 1.1rem; }}

                    #moves-container {{
                        flex: 1;
                        padding: 15px 20px;
                        overflow-y: auto;
                        font-size: 1.15rem;
                        line-height: 2;
                    }}
                    .turn-number {{ color: #666; font-size: 0.85em; margin-right: 5px; }}
                    .move-span {{ 
                        cursor: pointer; 
                        padding: 3px 6px; 
                        border-radius: 4px; 
                        transition: background 0.1s;
                    }}
                    .move-span:hover {{ background: #444; }}
                    .move-active {{ background: #2a5c8a !important; color: white; }}

                    /* MOBILE RESPONSIVE STACKING */
                    @media (max-width: 768px) {{
                        body {{ flex-direction: column; overflow: auto; }}
                        #eval-container {{ display: none !important; }} /* Hide eval bar on mobile to save space */
                        #board-container {{ padding: 10px; min-height: 50vh; }}
                        #sidebar {{ width: 100%; border-left: none; border-top: 2px solid #111; }}
                        #moves-container {{ max-height: 40vh; }}
                    }}
                </style>
            </head>
            <body>
                <div id="eval-container">
                    <div id="eval-score">0.0</div>
                    <div id="eval-fill"></div>
                </div>
                
                <div id="board-container"></div>
                
                <div id="sidebar">
                    <div class="controls-bar">
                        <select id="game-selector" onchange="changeGame()"></select>
                        <div class="controls-row">
                            <button onclick="toggleFlip()">Flip Board</button>
                            <button id="live-btn" style="display:none;" onclick="goLive()">Go Live</button>
                            <button onclick="window.location.href='{ '/analysis' if clean_path == '/' else '/' }'">
                                { 'Analyze Engine' if clean_path == '/' else 'Live View' }
                            </button>
                        </div>
                    </div>
                    
                    <div id="engine-readout">
                        <div>Eval: <span id="engine-eval">--</span></div>
                        <div>Best: <span id="engine-best" class="best-move">--</span></div>
                    </div>
                    
                    <div id="moves-container">Waiting for data...</div>
                </div>

                <script>
                    const IS_ANALYSIS = {is_analysis};
                    let totalPlies = 0;
                    let currentViewPly = -1; 
                    let lastMovesData = [];
                    let isFlipped = false;
                    let currentGameFile = 'live.pgn';

                    // Initialize layout based on mode
                    if (IS_ANALYSIS) {{
                        document.getElementById('eval-container').style.display = 'flex';
                        document.getElementById('engine-readout').style.display = 'block';
                    }}

                    // --- ARCHIVE LOGIC ---
                    function loadGamesList() {{
                        fetch('/games-list')
                            .then(r => r.json())
                            .then(files => {{
                                const sel = document.getElementById('game-selector');
                                sel.innerHTML = '';
                                files.forEach(f => {{
                                    const opt = document.createElement('option');
                                    opt.value = f;
                                    opt.innerText = f;
                                    if(f === 'live.pgn') opt.selected = true;
                                    sel.appendChild(opt);
                                }});
                            }});
                    }}
                    
                    function changeGame() {{
                        currentGameFile = document.getElementById('game-selector').value;
                        totalPlies = 0; // Reset
                        goLive();
                    }}

                    // --- UI ACTIONS ---
                    function toggleFlip() {{
                        isFlipped = !isFlipped;
                        updateBoard();
                    }}

                    function goLive() {{
                        currentViewPly = -1;
                        document.getElementById('live-btn').style.display = 'none';
                        updateBoard();
                        renderMovesList();
                        
                        // Force engine update for the newest move
                        if (IS_ANALYSIS && lastMovesData.length > 0) {{
                            analyzePosition(lastMovesData[lastMovesData.length - 1].fen);
                        }}
                        
                        const container = document.getElementById('moves-container');
                        container.scrollTop = container.scrollHeight;
                    }}

                    function viewPly(ply) {{
                        currentViewPly = ply;
                        if (ply === totalPlies && currentGameFile === 'live.pgn') {{
                            goLive();
                            return;
                        }}
                        document.getElementById('live-btn').style.display = 'block';
                        updateBoard();
                        renderMovesList();
                        
                        // Analyze historical move
                        if (IS_ANALYSIS) {{
                            const moveObj = lastMovesData.find(m => m.ply === ply);
                            if(moveObj) analyzePosition(moveObj.fen);
                        }}
                    }}

                    // --- RENDERING ---
                    function updateBoard() {{
                        const fileTarget = `file=${{currentGameFile}}`;
                        const plyTarget = (currentViewPly === -1) ? '' : `&ply=${{currentViewPly}}`;
                        const flipTarget = `&flipped=${{isFlipped}}`;
                        
                        const url = `/board.svg?${{fileTarget}}${{plyTarget}}${{flipTarget}}&t=${{Date.now()}}`;
                        
                        fetch(url)
                            .then(r => r.text())
                            .then(svg => {{ 
                                document.getElementById('board-container').innerHTML = svg; 
                            }})
                            .catch(err => console.error("Board load skipped"));
                    }}

                    function renderMovesList() {{
                        if (lastMovesData.length === 0) return;
                        
                        let html = '';
                        let activePly = (currentViewPly === -1) ? totalPlies : currentViewPly;

                        // Start loop at 1 to skip the ply:0 Start FEN placeholder
                        for(let i = 1; i < lastMovesData.length; i += 2) {{
                            let turn = Math.floor(i / 2) + 1;
                            let white = lastMovesData[i];
                            let black = lastMovesData[i+1];
                            
                            html += `<div><span class="turn-number">${{turn}}.</span>`;
                            
                            let wClass = (white.ply === activePly) ? 'move-active' : '';
                            html += `<span class="move-span ${{wClass}}" onclick="viewPly(${{white.ply}})">${{white.san}}</span> `;
                            
                            if (black) {{
                                let bClass = (black.ply === activePly) ? 'move-active' : '';
                                html += `<span class="move-span ${{bClass}}" onclick="viewPly(${{black.ply}})">${{black.san}}</span>`;
                            }}
                            html += `</div>`;
                        }}
                        
                        document.getElementById('moves-container').innerHTML = html;
                    }}

                    // --- STOCKFISH API LOGIC ---
                    function analyzePosition(fen) {{
                        if (!fen) return;
                        
                        document.getElementById('engine-eval').innerText = "Calculating...";
                        document.getElementById('engine-best').innerText = "--";

                        fetch("https://chess-api.com/v1", {{
                            method: "POST",
                            headers: {{ "Content-Type": "application/json" }},
                            body: JSON.stringify({{ fen: fen, depth: 12 }}) // Moderate depth for speed
                        }})
                        .then(r => r.json())
                        .then(data => {{
                            // Format eval
                            let evalText = "";
                            let rawScore = 0;
                            
                            if (data.mate) {{
                                evalText = `M${{data.mate}}`;
                                rawScore = data.mate > 0 ? 10 : -10; // Max out bar for mate
                            }} else {{
                                // API returns centipawns. Convert to standard +1.5 formatting
                                const score = (data.eval / 100).toFixed(2);
                                evalText = score > 0 ? `+${{score}}` : score;
                                rawScore = score;
                            }}

                            document.getElementById('engine-eval').innerText = evalText;
                            document.getElementById('engine-best').innerText = data.san;
                            
                            // Update Visual Bar (Mapping roughly -5 to +5 onto 0% to 100%)
                            const percentage = Math.max(0, Math.min(100, 50 + (rawScore * 10)));
                            document.getElementById('eval-fill').style.height = `${{percentage}}%`;
                            
                            // If board is flipped, invert the bar colors mathematically
                            if (isFlipped) {{
                                document.getElementById('eval-fill').style.height = `${{100 - percentage}}%`;
                                document.getElementById('eval-fill').style.background = '#333';
                                document.getElementById('eval-container').style.background = '#f0d9b5';
                            }} else {{
                                document.getElementById('eval-fill').style.background = '#f0d9b5';
                                document.getElementById('eval-container').style.background = '#333';
                            }}
                        }});
                    }}

                    function fetchState() {{
                        fetch(`/game-data?file=${{currentGameFile}}&t=${{Date.now()}}`)
                            .then(r => r.json())
                            .then(data => {{
                                if (!data || typeof data.total_plies === 'undefined') return;

                                if (data.total_plies !== totalPlies) {{
                                    totalPlies = data.total_plies;
                                    lastMovesData = data.moves;
                                    
                                    if (currentViewPly === -1) {{
                                        updateBoard();
                                        renderMovesList();
                                        const container = document.getElementById('moves-container');
                                        container.scrollTop = container.scrollHeight;
                                        
                                        // Auto-analyze the newest live move
                                        if (IS_ANALYSIS && lastMovesData.length > 0) {{
                                            analyzePosition(lastMovesData[lastMovesData.length - 1].fen);
                                        }}
                                    }} else {{
                                        renderMovesList();
                                    }}
                                }}
                            }})
                            .catch(err => {{}});
                    }}

                    // --- INIT ---
                    document.addEventListener('keydown', (e) => {{
                        if (totalPlies === 0) return;
                        let current = (currentViewPly === -1) ? totalPlies : currentViewPly;
                        if (e.key === 'ArrowLeft') {{
                            if (current > 0) viewPly(current - 1);
                        }} else if (e.key === 'ArrowRight') {{
                            if (current < totalPlies) viewPly(current + 1);
                        }}
                    }});

                    loadGamesList();
                    setInterval(fetchState, 1000);
                    fetchState(); 
                    updateBoard();
                </script>
            </body>
            </html>
            """
            self.send_response(200)
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(html_content.encode("utf-8"))

with socketserver.TCPServer(("", PORT), ChessHandler) as httpd:
    print(f"Serving interactive chess board on port {PORT}")
    httpd.serve_forever()