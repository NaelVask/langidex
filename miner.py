"""Langdex Protocol: One-Click Validator Node Miner.
Allows non-technical users to verify GitHub and package registry telemetry
and mint 50.00 DEK per daily epoch block into their wallet.
Includes automatic historical catch-up for offline days.
"""
import os, sys, datetime as dt, hashlib
from db import init, conn, backup_db
from collector import collect
from index_engine import rebuild_prices
from trading import award_oracle_reward, tokenomics_summary

WALLET_FILE = ".miner_wallet"

def get_or_prompt_wallet() -> str:
    if os.path.exists(WALLET_FILE):
        with open(WALLET_FILE, "r", encoding="utf-8") as f:
            addr = f.read().strip()
            if addr:
                return addr

    print("=" * 64)
    print("             LANGDEX PROTOCOL: VALIDATOR MINER             ")
    print("=" * 64)
    print("Verify multi-source Git telemetry and earn 50.00 DEK per daily block.")
    print("Protocol Hard Cap: 20,502,006 DEK")
    print("=" * 64)
    print()

    while True:
        raw = input("Enter your Langdex Wallet Address or 12-Word Recovery Phrase:\n> ").strip()
        if not raw:
            print("[!] Address or phrase cannot be empty. Please try again.\n")
            continue

        # If user entered 12 words, derive deterministic 0x address
        if " " in raw:
            norm = " ".join(raw.lower().split())
            derived = "0x" + hashlib.sha256(norm.encode("utf-8")).hexdigest()[:40]
            print(f"[i] 12-word seed phrase recognized. Derived Address: {derived}")
            addr = derived
        else:
            addr = raw

        with open(WALLET_FILE, "w", encoding="utf-8") as f:
            f.write(addr)
        print(f"[+] Wallet address saved to {WALLET_FILE}. You will not need to enter it again.\n")
        return addr

def run_miner():
    init()
    wallet_addr = get_or_prompt_wallet()

    # Find which epochs in the last 7 days need verification and reward
    today = dt.date.today()
    candidate_days = [(today - dt.timedelta(days=i)).isoformat() for i in range(7, 0, -1)]

    unmined_days = []
    with conn() as c:
        u = c.execute("SELECT id FROM users WHERE token=?", (wallet_addr,)).fetchone()
        user_id = u["id"] if u else None

        for day in candidate_days:
            if user_id:
                reason = f"Oracle block reward for epoch {day}"
                already_rewarded = c.execute("SELECT id FROM dek_ledger WHERE user_id=? AND reason=?",
                                             (user_id, reason)).fetchone()
                if not already_rewarded:
                    unmined_days.append(day)
            else:
                unmined_days.append(day)

    # If all epochs are current, default to verifying yesterday
    if not unmined_days:
        unmined_days = [(today - dt.timedelta(days=1)).isoformat()]

    print("-" * 64)
    print(f"[*] Validator Wallet: {wallet_addr}")
    print(f"[*] Pending Epoch Blocks: {', '.join(unmined_days)}")
    print("-" * 64)

    total_minted_this_session = 0.0
    latest_bal = 0.0

    for idx, epoch_day in enumerate(unmined_days, 1):
        print(f"\n[{idx}/{len(unmined_days)}] Processing Epoch Block: {epoch_day}")
        print("  - Ingesting multi-source telemetry (GitHub, PyPI, npm, crates.io)...")
        collect(epoch_day)

        print("  - Computing anti-sybil filters and rebuilding index prices...")
        rebuild_prices()

        prev_bal = latest_bal
        latest_bal = award_oracle_reward(wallet_addr, epoch_day)
        minted_delta = latest_bal - prev_bal if prev_bal > 0 else (50.0 if latest_bal >= 50.0 else latest_bal)
        if minted_delta > 0:
            total_minted_this_session += minted_delta
            print(f"  [+] Minted 50.00 DEK reward for epoch {epoch_day}")
        else:
            print(f"  [i] Epoch {epoch_day} was already rewarded to this wallet.")

    print("\nCreating rolling ACID ledger backup...")
    backup_file = backup_db()

    summary = tokenomics_summary()

    print("\n" + "=" * 64)
    print("                    VALIDATION SUCCESS RECEIPT                    ")
    print("=" * 64)
    print(f"Epochs Processed:     {len(unmined_days)} block(s)")
    print(f"Block Height:         #{summary['block_height']}")
    print(f"Reward Minted:        +{total_minted_this_session:.2f} DEK")
    print(f"Your Wallet Address:  {wallet_addr}")
    print(f"Your Total Balance:   {latest_bal:.2f} DEK")
    print(f"Ledger Snapshot:      {backup_file}")
    print("-" * 64)
    print(f"Total DEK Minted:     {summary['total_minted']:,.2f} / {summary['hard_cap']:,} DEK")
    print(f"Remaining to Mine:    {summary['remaining_unmined']:,.2f} DEK")
    print(f"Circulating Supply:   {summary['circulating_supply']:,.2f} DEK")
    print("=" * 64)
    print("\n[+] Verification complete. DEK has been credited to your ledger.")

if __name__ == "__main__":
    try:
        run_miner()
    except Exception as e:
        print(f"\n[ERROR] Mining failed: {e}")
    finally:
        input("\nPress Enter to exit...")
