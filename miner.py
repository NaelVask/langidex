"""Langdex Protocol: One-Click Validator Node Miner.
Allows users to verify GitHub and package registry telemetry
and participate in daily epoch validation.
Strict consensus: Missing an epoch means the reward window is closed.
"""
import os, sys, datetime as dt, hashlib
from db import init, conn, backup_db
from collector import collect, verify_and_record_proofs
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
    print("Verify multi-source Git telemetry for the active daily epoch.")
    print("Protocol Hard Cap: 20,502,006 DEK")
    print("=" * 64)
    print()

    while True:
        raw = input("Enter your Langdex Node Address:\n> ").strip()
        if not raw:
            print("[!] Address cannot be empty. Please try again.\n")
            continue

        addr = raw

        with open(WALLET_FILE, "w", encoding="utf-8") as f:
            f.write(addr)
        print(f"[+] Wallet address saved to {WALLET_FILE}. You will not need to enter it again.\n")
        return addr

def run_miner():
    init()
    wallet_addr = get_or_prompt_wallet()

    # Strict consensus: Only the active yesterday epoch is open for validation
    epoch_day = (dt.date.today() - dt.timedelta(days=1)).isoformat()

    print("-" * 64)
    print(f"[*] Validator Wallet:   {wallet_addr}")
    print(f"[*] Active Epoch Block: {epoch_day}")
    print("-" * 64)

    # Check if this node has already sealed this epoch
    with conn() as c:
        u = c.execute("SELECT id, dek FROM users WHERE token=?", (wallet_addr,)).fetchone()
        if u:
            reason = f"Oracle block reward for epoch {epoch_day}"
            already_rewarded = c.execute("SELECT id FROM dek_ledger WHERE user_id=? AND reason=?",
                                         (u["id"], reason)).fetchone()
            if already_rewarded:
                print(f"[!] Epoch {epoch_day} has already been sealed and credited for this wallet.")
                print(f"    Current Balance: {u['dek']:.2f} DEK")
                print("    Next epoch block window opens after 00:00 UTC.")
                return

    print("\n[1/5] Ingesting multi-source telemetry (GitHub, PyPI, npm, crates.io)...")
    collect(epoch_day)

    print("\n[2/5] Computing anti-sybil filters and rebuilding index prices...")
    rebuild_prices()

    print("\n[3/5] Running PoTOP proof-of-telemetry verification (Git Smart HTTP)...")
    proof_count = verify_and_record_proofs(wallet_addr, epoch_day)
    print(f"      {proof_count} repository commit proofs sealed into the attestation ledger.")

    print("\n[4/5] Minting validator block reward...")
    latest_bal = award_oracle_reward(wallet_addr, epoch_day)

    print("\n[5/5] Creating rolling ACID ledger backup...")
    backup_file = backup_db()

    summary = tokenomics_summary()

    print("\n" + "=" * 64)
    print("                    VALIDATION SUCCESS RECEIPT                    ")
    print("=" * 64)
    print(f"Epoch Verified:       {epoch_day}")
    print(f"Block Height:         #{summary['block_height']}")
    print(f"Reward Minted:        +50.00 DEK")
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
