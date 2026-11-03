"""Langdex Protocol: One-Click Validator Node Miner.
Allows non-technical users to verify GitHub and package registry telemetry
and mint 50.00 DEK per daily epoch block into their wallet.
"""
import os, sys, datetime as dt, hashlib
from db import init, backup_db
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

    epoch_day = (dt.date.today() - dt.timedelta(days=1)).isoformat()
    print("-" * 64)
    print(f"[*] Starting validation for Epoch Block: {epoch_day}")
    print(f"[*] Mining Target Wallet: {wallet_addr}")
    print("-" * 64)

    print("\n[1/4] Ingesting multi-source telemetry (GitHub, PyPI, npm, crates.io)...")
    collect(epoch_day)

    print("\n[2/4] Computing anti-sybil filters and rebuilding index prices...")
    rebuild_prices()

    print("\n[3/4] Minting validator block reward...")
    bal = award_oracle_reward(wallet_addr, epoch_day)

    print("\n[4/4] Creating rolling ACID ledger backup...")
    backup_file = backup_db()

    summary = tokenomics_summary()

    print("\n" + "=" * 64)
    print("                    VALIDATION SUCCESS RECEIPT                    ")
    print("=" * 64)
    print(f"Epoch Verified:       {epoch_day}")
    print(f"Block Height:         #{summary['block_height']}")
    print(f"Reward Minted:        +50.00 DEK")
    print(f"Your Wallet Address:  {wallet_addr}")
    print(f"Your Total Balance:   {bal:.2f} DEK")
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
