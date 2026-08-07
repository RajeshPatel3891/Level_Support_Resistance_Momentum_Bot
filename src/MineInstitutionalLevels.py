import pandas as pd
import json

def mine_levels(ticker):
    file = f"{ticker}_audit.csv"
    df = pd.read_csv(file)
    # Filter for Dark Pool conditions (15, 38)
    # This assumes your audit includes a 'Conditions' or 'Signal' column
    # If not, we can aggregate by Price where High Conviction occurred
    inst_levels = df[df['Conviction'] == 'HIGH']['Price'].value_counts().head(3)
    return inst_levels.index.tolist()

# Apply to portfolio
manifest = {}
for t in ["SPY", "IWM", "QQQ"]:
    manifest[t] = mine_levels(t)
    print(f"Institutional Support Levels for {t}: {manifest[t]}")
