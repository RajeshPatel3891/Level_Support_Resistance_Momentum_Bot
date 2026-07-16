import os
import sys
import json
import time
from datetime import datetime

# --- DYNAMIC TKINTER IMPORT GUARD (Headless Server Resilience) ---
TK_AVAILABLE = True
try:
    import tkinter as tk
    from tkinter import ttk
except ImportError:
    TK_AVAILABLE = False

# Set base Tk class dynamically based on environment capabilities
BaseTkClass = tk.Tk if TK_AVAILABLE else object

# --- PALETTE CONFIGURATION (Dark Slate High-Contrast) ---
BG_COLOR = "#020617"          # Rich dark background
PANEL_COLOR = "#0d1527"       # Muted navy panel
TEXT_MAIN = "#f1f5f9"         # Clean off-white
TEXT_MUTED = "#94a3b8"        # Slate grey
ACCENT_BLUE = "#38bdf8"       # Cyan telemetry highlight
ACCENT_GREEN = "#10b981"      # Success execute green
ACCENT_RED = "#ef4444"        # Defensive block red
BORDER_COLOR = "#1e293b"      # Panel separator slate

MANIFEST_DATA = {
    "src/LiveBot.py": {
        "title": "WebSocket Execution Orchestrator",
        "desc": "The central production controller. Establishes a persistent TCP socket to massive.com, processes trades against support/resistance thresholds, assembles the CSO conviction matrix, and deploys Discord alerts."
    },
    "src/AlpacaPipeline.py": {
        "title": "Production Order Router",
        "desc": "Integrates directly with the Alpaca API. Receives cleared buy/sell triggers from the sentry engine, translates them into order parameters, and manages direct market routing."
    },
    "src/SupportEngine.py": {
        "title": "Support Absorption Evaluator",
        "desc": "Monitors depth of book liquidity and volume-holding configurations directly inside support bounds. Asserts if institutional buyers are stepping in."
    },
    "src/DarkPoolManager.py": {
        "title": "Sequential Block & Odd-Lot Tracker",
        "desc": "Monitors hidden market interactions. Isolates Condition 15 (block prints) and Condition 38 (odd-lot trades) to verify institutional footprints ahead of execution."
    },
    "TradeManagerLogic.py": {
        "title": "State Locks & Dynamic Stop Optimizer",
        "desc": "Enforces strict binary mutex locks on active tickers to prevent consecutive-tick double entries. Scales stop-loss and trailing take-profit thresholds dynamically using historical asset beta tables."
    },
    "simulate_cso_matrix.py": {
        "title": "Gemini Macro Sentinel Crawler",
        "desc": "The asynchronous news sidecar daemon. Searches and crawls macroeconomic sentiment indicators using Gemini-2.5-Flash + Search Grounding, writing atomic state changes directly to macro_state.json."
    },
    "macro_state.json": {
        "title": "Asynchronous State Manifest",
        "desc": "A lightweight, shared JSON structure. Stores the live macro regime, primary catalysts, active risk bias, and operational directives used as a gateway override by the bot."
    },
    "trading_levels.json": {
        "title": "Static Coordinate Base",
        "desc": "Houses static coordinates for support, resistance, and pivots, alongside manual tactical coefficients configured by risk management."
    }
}

class SpyBotDashboard(BaseTkClass):
    def __init__(self):
        if not TK_AVAILABLE:
            return
        super().__init__()
        self.title("Alpaca Sentry Bot: Interactive Systems Dashboard")
        self.geometry("1100x750")
        self.configure(bg=BG_COLOR)
        
        # State tracker
        self.current_sentiment = 'RISK_OFF_LIQUIDATION'
        self.animating = False
        self.particle = None
        
        self.style = ttk.Style()
        self.style.theme_use('clam')
        self.style.configure(".", background=BG_COLOR, foreground=TEXT_MAIN)
        
        self.setup_ui()
        self.set_sentiment('RISK_OFF_LIQUIDATION')
        self.update_log("[*] [SYSTEM] - Sentry Bot telemetry UI initialized on local terminal.")
        self.select_manifest_file("src/LiveBot.py")

    def setup_ui(self):
        # Header Layout
        header = tk.Frame(self, bg=PANEL_COLOR, height=70, bd=0, highlightbackground=BORDER_COLOR, highlightthickness=1)
        header.pack(fill=tk.X, side=tk.TOP)
        header.pack_propagate(False)
        
        lbl_title = tk.Label(header, text="ALPACA SENTRY BOT", font=("Urbanist", 16, "bold"), fg="#ffffff", bg=PANEL_COLOR)
        lbl_title.pack(side=tk.LEFT, padx=20, pady=10)
        
        lbl_subtitle = tk.Label(header, text="High-Frequency Systems Blueprint", font=("Urbanist", 9), fg=TEXT_MUTED, bg=PANEL_COLOR)
        lbl_subtitle.pack(side=tk.LEFT, pady=18)
        
        self.lbl_active_context = tk.Label(header, text="CONTEXT: ALGO_TRADING_BOT", font=("Courier", 9, "bold"), fg=ACCENT_BLUE, bg="#0d1e3d", padx=10, pady=5)
        self.lbl_active_context.pack(side=tk.RIGHT, padx=20)

        # Main Workspace Wrapper
        workspace = tk.Frame(self, bg=BG_COLOR)
        workspace.pack(fill=tk.BOTH, expand=True, side=tk.TOP)
        
        # Left Panel (Simulation & Diagram Canvas)
        left_panel = tk.Frame(workspace, bg=BG_COLOR, width=680)
        left_panel.pack(fill=tk.BOTH, expand=True, side=tk.LEFT, padx=15, pady=15)
        
        # Right Panel (File Manifest Explorer)
        right_panel = tk.Frame(workspace, bg=PANEL_COLOR, width=380, highlightbackground=BORDER_COLOR, highlightthickness=1)
        right_panel.pack(fill=tk.BOTH, side=tk.RIGHT, padx=15, pady=15)
        right_panel.pack_propagate(False)
        
        self.setup_left_panel(left_panel)
        self.setup_right_panel(right_panel)

    def setup_left_panel(self, container):
        # Controls Group Card
        ctrl_card = tk.Frame(container, bg=PANEL_COLOR, highlightbackground=BORDER_COLOR, highlightthickness=1)
        ctrl_card.pack(fill=tk.X, side=tk.TOP, pb=10)
        
        lbl_ctrl_title = tk.Label(ctrl_card, text="CSO SENTINEL STATE CONTROLLER", font=("Urbanist", 11, "bold"), fg=TEXT_MAIN, bg=PANEL_COLOR)
        lbl_ctrl_title.pack(anchor=tk.W, padx=15, pady=(12, 5))
        
        lbl_ctrl_desc = tk.Label(ctrl_card, text="Simulate how the background news crawler intercepts execution gates under different sentiment regimes.", font=("Urbanist", 9), fg=TEXT_MUTED, bg=PANEL_COLOR, justify=tk.LEFT)
        lbl_ctrl_desc.pack(anchor=tk.W, padx=15, pady=(0, 10))
        
        btn_frame = tk.Frame(ctrl_card, bg=PANEL_COLOR)
        btn_frame.pack(fill=tk.X, padx=15, pady=5)
        
        self.btn_neutral = tk.Button(btn_frame, text="NEUTRAL REGIME\n(Long scalps approved)", font=("Urbanist", 9, "bold"), bg="#1e293b", fg=TEXT_MUTED, bd=0, activebackground=BORDER_COLOR, activeforeground=TEXT_MAIN, command=lambda: self.set_sentiment("NEUTRAL"))
        self.btn_neutral.pack(side=tk.LEFT, expand=True, fill=tk.BOTH, padx=5, ipady=8)
        
        self.btn_riskon = tk.Button(btn_frame, text="RISK_ON MOMENTUM\n(Support levels active)", font=("Urbanist", 9, "bold"), bg="#1e293b", fg=TEXT_MUTED, bd=0, activebackground=BORDER_COLOR, activeforeground=TEXT_MAIN, command=lambda: self.set_sentiment("RISK_ON"))
        self.btn_riskon.pack(side=tk.LEFT, expand=True, fill=tk.BOTH, padx=5, ipady=8)
        
        self.btn_riskoff = tk.Button(btn_frame, text="RISK_OFF OVERRULE\n(Defensive hard-stop)", font=("Urbanist", 9, "bold"), bg="#7f1d1d", fg=ACCENT_RED, bd=0, activebackground="#ef4444", activeforeground="#ffffff", command=lambda: self.set_sentiment("RISK_OFF_LIQUIDATION"))
        self.btn_riskoff.pack(side=tk.LEFT, expand=True, fill=tk.BOTH, padx=5, ipady=8)
        
        # Signal Trigger Button Row
        trigger_row = tk.Frame(ctrl_card, bg=PANEL_COLOR)
        trigger_row.pack(fill=tk.X, padx=15, pady=(10, 15))
        
        lbl_state_file = tk.Label(trigger_row, text="Active Context: macro_state.json", font=("Courier", 9, "bold"), fg=ACCENT_BLUE, bg="#020617", padx=8, pady=4)
        lbl_state_file.pack(side=tk.LEFT)
        
        self.btn_fire = tk.Button(trigger_row, text="Fire Scalp Signal Sim ⚡", font=("Urbanist", 10, "bold"), bg=ACCENT_GREEN, fg="#ffffff", bd=0, activebackground="#059669", relief=tk.FLAT, command=self.trigger_signal_animation)
        self.btn_fire.pack(side=tk.RIGHT, padx=5)

        self.canvas = tk.Canvas(container, bg="#030712", highlightthickness=1, highlightbackground=BORDER_COLOR)
        self.canvas.pack(fill=tk.BOTH, expand=True, pady=(15, 0))
        self.draw_diagram()
        
        # Terminal Output Log
        self.txt_term = tk.Text(container, bg="#020617", fg=ACCENT_GREEN, font=("Courier", 9), insertbackground=ACCENT_GREEN, state=tk.DISABLED, highlightthickness=1, highlightbackground=BORDER_COLOR, height=8)
        self.txt_term.pack(fill=tk.X, pady=(15, 0))

    def setup_right_panel(self, container):
        lbl_man_title = tk.Label(container, text="SYSTEM FILES MANIFEST", font=("Urbanist", 11, "bold"), fg=TEXT_MAIN, bg=PANEL_COLOR)
        lbl_man_title.pack(anchor=tk.W, padx=15, pady=(15, 5))
        
        lbl_man_desc = tk.Label(container, text="Select a component script below to audit its dynamic role within the Sentry network architecture.", font=("Urbanist", 9), fg=TEXT_MUTED, bg=PANEL_COLOR, justify=tk.LEFT, wraplength=340)
        lbl_man_desc.pack(anchor=tk.W, padx=15, pady=(0, 15))
        
        # Simple Listbox for file manifest navigation
        self.file_listbox = tk.Listbox(container, bg="#020617", fg=TEXT_MAIN, selectbackground=ACCENT_BLUE, selectforeground="#020617", font=("Courier", 10), bd=0, highlightthickness=1, highlightcolor=BORDER_COLOR, selectmode=tk.SINGLE)
        self.file_listbox.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)
        
        for file_path in MANIFEST_DATA.keys():
            self.file_listbox.insert(tk.END, file_path)
            
        self.file_listbox.bind('<<ListboxSelect>>', self.on_listbox_select)
        
        # Details Panel
        self.man_detail_frame = tk.Frame(container, bg="#020617", highlightbackground=BORDER_COLOR, highlightthickness=1)
        self.man_detail_frame.pack(fill=tk.X, side=tk.BOTTOM, padx=15, pady=15)
        
        self.lbl_man_file_title = tk.Label(self.man_detail_frame, text="", font=("Urbanist", 11, "bold"), fg=ACCENT_BLUE, bg="#020617", anchor="w")
        self.lbl_man_file_title.pack(fill=tk.X, padx=12, pady=(12, 4))
        
        self.lbl_man_file_desc = tk.Label(self.man_detail_frame, text="", font=("Urbanist", 9), fg=TEXT_MUTED, bg="#020617", justify=tk.LEFT, anchor="w", wraplength=310)
        self.lbl_man_file_desc.pack(fill=tk.X, padx=12, pady=(0, 12))

    def draw_diagram(self):
        self.canvas.delete("all")
        
        # Draw background grids
        for i in range(0, 700, 20):
            self.canvas.create_line(i, 0, i, 350, fill="#090f1d", width=1)
        for i in range(0, 350, 20):
            self.canvas.create_line(0, i, 700, i, fill="#090f1d", width=1)

        # Pipeline Flow Lines (Ingest -> Sentry -> Gate)
        self.canvas.create_line(110, 150, 220, 150, fill="#334155", width=2, arrow=tk.LAST, dash=(5, 3))
        self.canvas.create_line(320, 150, 420, 150, fill="#334155", width=2, arrow=tk.LAST, dash=(5, 3))
        
        # Path forks from Gate
        # 1. Clear Route (to Execute Node)
        self.line_ok = self.canvas.create_line(500, 150, 600, 150, fill="#334155", width=2.5, arrow=tk.LAST, tags="line_ok")
        # 2. Rejection Route (up to Safe/Reject Exit Node)
        self.line_block = self.canvas.create_line(460, 110, 460, 60, 600, 60, fill="#334155", width=2.5, arrow=tk.LAST, tags="line_block")

        # Custom rounded rectangle nodes using polygons
        self.draw_node(30, 110, 110, 190, "INGESTION\nConnection.py", ACCENT_BLUE, "ingest")
        self.draw_node(220, 110, 320, 190, "SENTRY CORE\nLiveBot.py", "#818cf8", "sentry")
        self.draw_gate_node(420, 110, 500, 190)
        self.draw_node(600, 110, 700, 190, "EXECUTE\nAlpaca Order", ACCENT_GREEN, "execute")
        self.draw_node(600, 20, 700, 100, "REJECT / SAFE\ndebug_trace.log", ACCENT_RED, "reject")

        # Live telemetry badge inside canvas
        self.badge_id = self.canvas.create_text(350, 20, text=f"STATE: {self.current_sentiment}", font=("Courier", 10, "bold"), fill=ACCENT_RED, anchor="n")

    def draw_node(self, x1, y1, x2, y2, text, outline_color, module_key):
        # Background polygon mapping round corners
        radius = 8
        pts = [x1+radius, y1, x2-radius, y1, x2, y1, x2, y1+radius, x2, y2-radius, x2, y2, x2-radius, y2, x1+radius, y2, x1, y2, x1, y2-radius, x1, y1+radius, x1, y1]
        self.canvas.create_polygon(pts, fill="#0d1527", outline=outline_color, width=1.5, smooth=True, tags=f"node_{module_key}")
        # Labels
        self.canvas.create_text((x1+x2)/2, (y1+y2)/2, text=text, fill=TEXT_MAIN, font=("Urbanist", 8, "bold"), justify=tk.CENTER)
        
    def draw_gate_node(self, x1, y1, x2, y2):
        radius = 8
        pts = [x1+radius, y1, x2-radius, y1, x2, y1, x2, y1+radius, x2, y2-radius, x2, y2, x2-radius, y2, x1+radius, y2, x1, y2, x1, y2-radius, x1, y1+radius, x1, y1]
        gate_border_color = ACCENT_RED if self.current_sentiment == 'RISK_OFF_LIQUIDATION' else ACCENT_GREEN
        gate_fill_color = "#3b0712" if self.current_sentiment == 'RISK_OFF_LIQUIDATION' else "#064e3b"
        icon = "X" if self.current_sentiment == 'RISK_OFF_LIQUIDATION' else "✔"
        
        self.canvas.create_polygon(pts, fill=gate_fill_color, outline=gate_border_color, width=2, smooth=True, tags="gate_rect")
        # Central gate status icon
        self.canvas.create_text((x1+x2)/2, y1+25, text=icon, fill=gate_border_color, font=("Urbanist", 16, "bold"), tags="gate_icon")
        # Sub-caption
        self.canvas.create_text((x1+x2)/2, y1+55, text="MACRO GATE", fill=TEXT_MUTED, font=("Urbanist", 7, "bold"))

    def set_sentiment(self, sentiment):
        self.current_sentiment = sentiment
        
        # Reset State Buttons Styling
        self.btn_neutral.configure(bg="#1e293b", fg=TEXT_MUTED)
        self.btn_riskon.configure(bg="#1e293b", fg=TEXT_MUTED)
        self.btn_riskoff.configure(bg="#7f1d1d", fg=ACCENT_RED)
        
        if sentiment == 'NEUTRAL':
            self.btn_neutral.configure(bg=ACCENT_BLUE, fg="#020617")
        elif sentiment == 'RISK_ON':
            self.btn_riskon.configure(bg=ACCENT_GREEN, fg="#020617")
        elif sentiment == 'RISK_OFF_LIQUIDATION':
            self.btn_riskoff.configure(bg=ACCENT_RED, fg="#ffffff")
            
        self.update_log(f"[CSO_STATE_UPDATE] - macro_state.json updated dynamically with Bias: {sentiment}")
        self.draw_diagram()

    def update_log(self, text):
        if not TK_AVAILABLE:
            return
        self.txt_term.configure(state=tk.NORMAL)
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.txt_term.insert(tk.END, f"[{timestamp}] {text}\n")
        self.txt_term.see(tk.END)
        self.txt_term.configure(state=tk.DISABLED)

    def trigger_signal_animation(self):
        if self.animating:
            return
        
        self.animating = True
        self.btn_fire.configure(state=tk.DISABLED, bg="#334155")
        
        self.update_log("[*] [LIVEBOT] - Real-time trade detected on Socket Connection.")
        
        # Spawn signal particle at Node 1 (Ingest)
        self.particle = self.canvas.create_oval(60, 140, 80, 160, fill="#ffffff", outline=ACCENT_BLUE, width=2)
        
        # Segment 1: Ingest to Sentry Core (x: 70 -> 270)
        self.animate_along_path(70, 150, 270, 150, steps=25, callback=self.on_sentry_arrived)

    def animate_along_path(self, x_start, y_start, x_end, y_end, steps, callback, index=0):
        if index > steps:
            callback()
            return
        
        t = index / steps
        curr_x = x_start + (x_end - x_start) * t
        curr_y = y_start + (y_end - y_start) * t
        
        self.canvas.coords(self.particle, curr_x-8, curr_y-8, curr_x+8, curr_y+8)
        self.after(20, lambda: self.animate_along_path(x_start, y_start, x_end, y_end, steps, callback, index+1))

    def on_sentry_arrived(self):
        self.update_log("[*] [SUPPORTENGINE] - Proximity checked. $SPY coordinates matching static coordinates.")
        # Segment 2: Sentry Core to Macro Gate (x: 270 -> 460)
        self.animate_along_path(270, 150, 460, 150, steps=25, callback=self.on_gate_arrived)

    def on_gate_arrived(self):
        self.update_log("[*] [LIVEBOT] - Querying async news conditions inside macro_state.json...")
        
        # Decide path depending on active gate status
        if self.current_sentiment == 'RISK_OFF_LIQUIDATION':
            # Block path to Rejection Exit Node (up and over to x: 650, y: 60)
            self.after(500, lambda: self.update_log("[ALERT] [LIVEBOT] - News Intercept Engaged. Sentiment contradicts conviction."))
            self.after(500, lambda: self.animate_along_path(460, 150, 460, 60, steps=15, callback=self.on_gate_fork_up))
        else:
            # Clear path directly to Alpaca execution layer (x: 650, y: 150)
            self.after(500, lambda: self.update_log("[✓] [LIVEBOT] - Sentiment alignment matches. Clearing signal for routing."))
            self.after(500, lambda: self.animate_along_path(460, 150, 650, 150, steps=25, callback=self.on_simulation_complete))

    def on_gate_fork_up(self):
        # Finish drawing path to rejection box
        self.animate_along_path(460, 60, 650, 60, steps=20, callback=self.on_simulation_complete)

    def on_simulation_complete(self):
        if self.current_sentiment == 'RISK_OFF_LIQUIDATION':
            self.update_log("[ALERT] [REJECTION_EXIT] - Bypassing execution pipelines. Safe logged.")
        else:
            self.update_log("[✓] [TRADEMANAGER] - Core locks acquired. Order dispatched to Alpaca.")
            self.update_log("[✓] [PINGDISCORD] - Discord telemetry logs written.")
            
        self.canvas.delete(self.particle)
        self.particle = None
        self.animating = False
        self.btn_fire.configure(state=tk.NORMAL, bg=ACCENT_GREEN)

    def on_listbox_select(self, event):
        widget = event.widget
        selection = widget.curselection()
        if selection:
            index = selection[0]
            file_name = widget.get(index)
            self.select_manifest_file(file_name)

    def select_manifest_file(self, file_name):
        data = MANIFEST_DATA[file_name]
        self.lbl_man_file_title.configure(text=data["title"].upper())
        self.lbl_man_file_desc.configure(text=data["desc"])

if __name__ == "__main__":
    if not TK_AVAILABLE:
        print("\n" + "="*80)
        print("🚨 HEADLESS ENVIRONMENT DETECTED (No tkinter library installed)")
        print("="*80)
        print("\nTkinter GUI applications require a local graphical desktop environment to render windows.")
        print("To run the interactive visual dashboard, download this script and run it locally:")
        print("   python3 SystemDiagram.py")
        print("\nOr install tkinter on your Ubuntu server via:")
        print("   sudo apt-get update && sudo apt-get install -y python3-tk")
        print("\n" + "-"*80)
        print("🎛️ CURRENT SPY BOT SYSTEM STATE (CLI Fallback Mode)")
        print("-"*80)
        print("Active Context : ALGO_TRADING_BOT")
        print("CSO Risk State : RISK_OFF_LIQUIDATION")
        print("News Intercept : ACTIVE (Long Trades Blocked)")
        print("\nACTIVE FILE ARCHITECTURE MANIFEST:")
        for filepath, info in MANIFEST_DATA.items():
            print(f"• {filepath:<25} | {info['title']}")
        print("="*80 + "\n")
        sys.exit(0)
        
    try:
        app = SpyBotDashboard()
        app.mainloop()
    except Exception as e:
        print("\n" + "="*80)
        print("🚨 WINDOWS SYSTEM DISPLAY ERROR")
        print("="*80)
        print(f"Error Details: {e}")
        print("\nFalling back to CLI status report...")
        print("\n" + "-"*80)
        print("🎛️ CURRENT SPY BOT SYSTEM STATE (CLI Fallback Mode)")
        print("-"*80)
        print("Active Context : ALGO_TRADING_BOT")
        print("CSO Risk State : RISK_OFF_LIQUIDATION")
        print("News Intercept : ACTIVE (Long Trades Blocked)")
        print("\nACTIVE FILE ARCHITECTURE MANIFEST:")
        for filepath, info in MANIFEST_DATA.items():
            print(f"• {filepath:<25} | {info['title']}")
        print("="*80 + "\n")
