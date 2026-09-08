import requests

# Ensure virtual position on mock gateway has standard Tradier fields
payload = {
    "symbol": "NKE",
    "option_symbol": "NKE260904P00080000",
    "quantity": 1,
    "cost_basis": 54.00,
    "date_acquired": "2026-09-01T20:00:00.000Z"
}
