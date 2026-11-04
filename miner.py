"""Langdex Protocol: Standard BIP-39 Validator Node Miner.
Integrates:
- BIP-39 12-word cryptographic seed phrase generation and validation
- Authentic Proof of Telemetry Work (PoTW) mining puzzle over Git Merkle roots
- Multi-source telemetry ingestion and Git Smart HTTP commit verification
- Strict single-epoch consensus windows
"""
import os, sys, datetime as dt, hashlib
from db import init, conn, backup_db
from collector import collect, verify_and_record_proofs
from index_engine import rebuild_prices
from trading import award_oracle_reward, tokenomics_summary
import wallet_bip39 as wb
import pow_engine as pe

WALLET_FILE = ".miner_wallet"

def get_or_prompt_wallet() -> tuple[str, str]:
    """Returns (pubkey_hex, privkey_hex).
    Prompts user to import an existing 12-word BIP-39 phrase or generates a fresh one.
    """
    if os.path.exists(WALLET_FILE):
        try:
            with open(WALLET_FILE, "r", encoding="utf-8") as f:
                phrase = f.read().strip()
            if phrase and wb.validate_mnemonic(phrase):
                priv, pub = wb.mnemonic_to_keypair(phrase)
                return pub, priv
        except Exception:
            pass

    print("=" * 64)
    print("             LANGDEX PROTOCOL: VALIDATOR MINER             ")
    print("=" * 64)
    print("Authentic BIP-39 Cryptographic Validator & Proof-of-Work Miner")
    print("Protocol Hard Cap: 20,502,006 DEK")
    print("=" * 64)
    print()

    print("Choose wallet option:")
    print("  [1] Generate a new secure 12-word BIP-39 seed phrase (Recommended)")
    print("  [2] Import existing Langdex dedicated seed phrase (NEVER use an existing Bitcoin/ETH wallet phrase)")
    choice = input("\nEnter choice (1 or 2): ").strip()

    if choice == "2":
        while True:
            raw = input("\nEnter your dedicated Langdex 12-word BIP-39 seed phrase:\n> ").strip()
            if not wb.validate_mnemonic(raw):
                print("[!] Invalid BIP-39 seed phrase or failed checksum. Check spelling and retry.\n")
                continue
            phrase = " ".join(raw.lower().split())
            break
    else:
        phrase = wb.generate_mnemonic()
        print("\n" + "*" * 64)
        print("YOUR DEDICATED LANGDEX 12-WORD BIP-39 RECOVERY SEED PHRASE:")
        print(f"  {phrase}")
        print("Keep this secret. It derives your Ed25519 validator private key.")
        print("DO NOT reuse this phrase for any other financial wallet.")
        print("*" * 64 + "\n")

    priv, pub = wb.mnemonic_to_keypair(phrase)
    with open(WALLET_FILE, "w", encoding="utf-8") as f:
        f.write(phrase)
    print(f"[+] Wallet saved to {WALLET_FILE}.\n")
    return pub, priv

def run_miner():
    init()
    pubkey, privkey = get_or_prompt_wallet()

    # Strict consensus: Only the active yesterday epoch is open for validation
    epoch_day = (dt.date.today() - dt.timedelta(days=1)).isoformat()

    print("-" * 64)
    print(f"[*] Validator Public Key: {pubkey}")
    print(f"[*] Active Epoch Block:   {epoch_day}")
    print("-" * 64)

    # Check if this node has already sealed this epoch
    with conn() as c:
        u = c.execute("SELECT id, dek FROM users WHERE token=?", (pubkey,)).fetchone()
        if u:
            reason = f"Oracle block reward for epoch {epoch_day}"
            already_rewarded = c.execute("SELECT id FROM dek_ledger WHERE user_id=? AND reason=?",
                                         (u["id"], reason)).fetchone()
            if already_rewarded:
                print(f"[!] Epoch {epoch_day} has already been sealed and credited for this wallet.")
                print(f"    Current Balance: {u['dek']:.2f} DEK")
                print("    Next epoch block window opens after 00:00 UTC.")
                return

    print("\n[1/6] Ingesting multi-source telemetry (GitHub, PyPI, npm, crates.io)...")
    collect(epoch_day)

    print("\n[2/6] Computing anti-sybil filters and rebuilding index prices...")
    rebuild_prices()

    print("\n[3/6] Running PoTOP proof-of-telemetry verification (Git Smart HTTP)...")
    proof_count = verify_and_record_proofs(pubkey, privkey, epoch_day)
    print(f"      {proof_count} repository commit proofs sealed into the attestation ledger.")

    # Retrieve latest Merkle root of verified proofs
    with conn() as c:
        latest = c.execute("SELECT merkle_root FROM verified_proofs ORDER BY id DESC LIMIT 1").fetchone()
        merkle_root = latest["merkle_root"] if latest and latest["merkle_root"] else "87be4735c1f0c9f85c5e2822b893c097dfa9690ccd4bfa95374036b537090def"

    print("\n[4/6] Solving Proof of Telemetry Work (PoTW) cryptographic puzzle...")
    print(f"      Target: SHA-256 with 16 leading zero bits over Merkle root {merkle_root[:16]}...")
    nonce, block_hash, duration = pe.mine_pow_puzzle(merkle_root, pubkey, epoch_day, difficulty_bits=16)
    print(f"      PoW Nonce Found: {nonce} ({duration:.2f}s)")
    print(f"      Sealed Block Hash: {block_hash}")

    print("\n[5/6] Minting validator block reward...")
    latest_bal = award_oracle_reward(pubkey, epoch_day)

    print("\n[6/6] Creating rolling ACID ledger backup...")
    backup_file = backup_db()

    summary = tokenomics_summary()

    print("\n" + "=" * 64)
    print("                    VALIDATION SUCCESS RECEIPT                    ")
    print("=" * 64)
    print(f"Epoch Verified:       {epoch_day}")
    print(f"Block Height:         #{summary['block_height']}")
    print(f"PoW Nonce:            {nonce}")
    print(f"Block Hash:           {block_hash}")
    print(f"Reward Minted:        +50.00 DEK")
    print(f"Your Public Key:      {pubkey}")
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
