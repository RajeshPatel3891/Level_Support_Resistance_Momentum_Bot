import http.server
import socketserver
import urllib.parse
import json
import sys

PORT = 8080

def calculate_matrix(capital, risk_pct, premium):
    risk_lim = risk_pct / 100.0
    max_allowed_loss = capital * risk_lim
    
    assets_base = {
        "IWM": {"price": 300.61, "rvol": 1.5},
        "NVDA": {"price": 194.51, "rvol": 1.5},
        "SPY": {"price": 743.02, "rvol": 1.5}
    }
    
    rows = []
    allocation_matrix = {}
    
    for ticker, data in assets_base.items():
        price = data["price"]
        rvol = data["rvol"]
        
        dyn_risk_pct = 0.005 * min(rvol, 1.5)
        risk_per_share = price * dyn_risk_pct
        risk_per_contract = risk_per_share * 100 * 0.50
        
        raw_qty = max_allowed_loss / risk_per_contract if risk_per_contract > 0 else 0
        allocated_contracts = int(raw_qty)
        cash_outlay = allocated_contracts * (premium * 100)
        
        sl = price - risk_per_share
        tp1 = price + (risk_per_share * 2)
        tp2 = price + (risk_per_share * 4)
        
        allocation_matrix[ticker] = {
            "contracts": allocated_contracts,
            "risk_per_contract": risk_per_contract
        }
        
        rows.append({
            "ticker": ticker,
            "risk_pct": f"{dyn_risk_pct*100:.2f}%",
            "risk_share": f"${risk_per_share:.2f}",
            "risk_contract": f"${risk_per_contract:.2f}",
            "raw_qty": f"{raw_qty:.2f}",
            "contracts": allocated_contracts,
            "cash_out": f"${cash_outlay:.2f}",
            "sl": f"${sl:.2f}",
            "tp1": f"${tp1:.2f}",
            "tp2": f"${tp2:.2f}"
        })
        
    worst_case = sum(m["contracts"] * m["risk_per_contract"] for m in allocation_matrix.values()) * -1
    moderate_case = sum(m["contracts"] * m["risk_per_contract"] * 2 for m in allocation_matrix.values())
    
    iwm_win = allocation_matrix["IWM"]["contracts"] * allocation_matrix["IWM"]["risk_per_contract"] * 2
    spy_win = allocation_matrix["SPY"]["contracts"] * allocation_matrix["SPY"]["risk_per_contract"] * 2
    nvda_loss = allocation_matrix["NVDA"]["contracts"] * allocation_matrix["NVDA"]["risk_per_contract"] * -1
    expectancy = iwm_win + spy_win + nvda_loss
    
    return rows, worst_case, moderate_case, expectancy

class DashHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        url_parts = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(url_parts.query)
        
        capital = float(params.get('capital', [2000.0])[0])
        risk_pct = float(params.get('risk_pct', [5.0])[0])
        premium = float(params.get('premium', [2.50])[0])
        
        rows, worst_case, moderate_case, expectancy = calculate_matrix(capital, risk_pct, premium)
        
        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Harmonized AI — Risk Optimization Matrix</title>
    <style>
        body {{ font-family: 'Segoe UI', Arial, sans-serif; background-color: #0f172a; color: #f8fafc; margin: 0; padding: 30px; }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        h1 {{ color: #38bdf8; font-family: monospace; border-bottom: 2px solid #334155; padding-bottom: 10px; }}
        .layout {{ display: flex; gap: 30px; margin-top: 20px; }}
        .panel-input {{ flex: 1; background-color: #1e293b; padding: 25px; border-radius: 8px; border: 1px solid #334155; height: fit-content; }}
        .panel-output {{ flex: 2; background-color: #020617; padding: 25px; border-radius: 8px; border: 1px solid #1e293b; font-family: monospace; }}
        .form-group {{ margin-bottom: 15px; display: flex; justify-content: space-between; align-items: center; }}
        label {{ color: #94a3b8; font-size: 14px; }}
        input {{ background-color: #0f172a; color: #fff; border: 1px solid #475569; padding: 8px; border-radius: 4px; width: 100px; text-align: right; }}
        button {{ background-color: #10b981; color: #fff; border: none; padding: 12px; width: 100%; border-radius: 4px; font-weight: bold; cursor: pointer; margin-top: 15px; }}
        button:hover {{ background-color: #059669; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 15px; text-align: left; }}
        th {{ color: #38bdf8; border-bottom: 1px solid #334155; padding: 10px 5px; font-size: 12px; }}
        td {{ padding: 10px 5px; border-bottom: 1px solid #1e293b; font-size: 13px; }}
        .summary-section {{ margin-top: 25px; border-top: 1px dashed #334155; padding-top: 15px; }}
        .scenario {{ display: flex; justify-content: space-between; margin-bottom: 10px; font-size: 14px; }}
        .text-red {{ color: #ef4444; font-weight: bold; }}
        .text-green {{ color: #34d399; font-weight: bold; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>HARM.AI // OPTIONS PORTFOLIO QUANT SIZER</h1>
        <div class="layout">
            <div class="panel-input">
                <h3 style="color: #38bdf8; margin-top:0;">PARAMETER INPUT LAYERS</h3>
                <form method="GET" action="/">
                    <div class="form-group">
                        <label>Total Portfolio Capital ($):</label>
                        <input type="number" name="capital" step="0.01" value="{capital}">
                    </div>
                    <div class="form-group">
                        <label>Max Risk Per Trade (%):</label>
                        <input type="number" name="risk_pct" step="0.1" value="{risk_pct}">
                    </div>
                    <div class="form-group">
                        <label>Contract Premium ($):</label>
                        <input type="number" name="premium" step="0.01" value="{premium}">
                    </div>
                    <button type="submit">RUN MODEL SIMULATION</button>
                </form>
            </div>
            
            <div class="panel-output">
                <div style="color: #64748b; margin-bottom: 15px;">=== DYNAMIC SIZING CALIBRATION LOG OUTPUT ===</div>
                <div style="margin-bottom: 20px;">Total Risk Ceiling Per Position: <span style="color: #10b981;">${capital * (risk_pct/100.0):.2f}</span></div>
                
                <table>
                    <thead>
                        <tr>
                            <th>ASSET</th>
                            <th>RISK %</th>
                            <th>RISK/SH</th>
                            <th>RISK/CON</th>
                            <th>RAW_QTY</th>
                            <th>ALLOC_CON</th>
                            <th>CASH_OUT</th>
                        </tr>
                    </thead>
                    <tbody>
        """
        for r in rows:
            html += f"""
                        <tr>
                            <td style="font-weight:bold; color:#fff;">{r['ticker']}</td>
                            <td>{r['risk_pct']}</td>
                            <td>{r['risk_share']}</td>
                            <td>{r['risk_contract']}</td>
                            <td>{r['raw_qty']}</td>
                            <td style="color:#10b981; font-weight:bold;">{r['contracts']}</td>
                            <td>{r['cash_out']}</td>
                        </tr>
            """
            
        html += f"""
                    </tbody>
                </table>
                
                <div class="summary-section">
                    <div style="color: #64748b; margin-bottom: 10px;">=== DYNAMIC ASSET EXIT LEVEL PLAN ===</div>
        """
        for r in rows:
            html += f'<div>• <b>{r["ticker"]:<4}</b> -> Stop Loss: {r["sl"]} | TP1 (1:2): {r["tp1"]} | TP2 (1:4): {r["tp2"]}</div>'
            
        html += f"""
                </div>
                
                <div class="summary-section">
                    <div style="color: #64748b; margin-bottom: 10px;">=== REVENUE ASYMMETRY PERFORMANCE OPTIMIZATION ===</div>
                    <div class="scenario">
                        <span>SCENARIO A: Complete System Crash (All 3 Hit SL)</span>
                        <span class="text-red">-${abs(worst_case):.2f}</span>
                    </div>
                    <div class="scenario">
                        <span>SCENARIO B: System Alpha Capture (All 3 Hit TP1)</span>
                        <span class="text-green">+${moderate_case:.2f}</span>
                    </div>
                    <div class="scenario">
                        <span>SCENARIO C: Realized Model Expectation (70% WR)</span>
                        <span class="{"text-green" if expectancy >= 0 else "text-red"}">{expectancy:+.2f}</span>
                    </div>
                </div>
            </div>
        </div>
    </div>
</body>
</html>"""
        
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))

    def log_message(self, format, *args):
        pass # Suppress command line log trash to keep your terminal pristine

print(f"[*] Interactive Optimization Web-Engine Launched Successfully.")
print(f"[*] Access URL: http://localhost:{PORT}")
with socketserver.TCPServer(("", PORT), DashHandler) as httpd:
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[*] Shutting down optimization service loop.")
        sys.exit(0)
