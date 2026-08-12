import os

seeder_files = [
    "force_dynamodb_batch.py", 
    "force_batch_injector.py", 
    "force_dynamodb_batch_accurate.py",
    "force_trade_injector.py"
]

for fpath in seeder_files:
    if os.path.exists(fpath):
        with open(fpath, "r") as f:
            code = f.read()
        code = code.replace("'ACTIVE'", "'FORCE_CLOSE'").replace('"ACTIVE"', '"FORCE_CLOSE"')
        with open(fpath, "w") as f:
            f.write(code)
        print(f"[✓] Disabled active trade seeding in {fpath}")
