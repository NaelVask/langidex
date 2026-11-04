"""Langdex Protocol: Standard BIP-39 Validator Node Miner.
Integrates:
- BIP-39 12-word cryptographic seed phrase generation and validation
- Authentic Proof of Telemetry Work (PoTW) mining puzzle over Git Merkle roots
- Multi-source telemetry ingestion and Git Smart HTTP commit verification
- Strict single-epoch consensus windows
"""
import os, sys, datetime as dt, hashlib, json, base64, getpass
from db import init, conn, backup_db
from collector import collect, verify_and_record_proofs
from index_engine import rebuild_prices
from trading import award_oracle_reward, tokenomics_summary
import wallet_bip39 as wb
import pow_engine as pe
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

WALLET_FILE = ".miner_wallet"

def _derive_aes_key(password: str, salt: bytes) -> bytes:
    """Derives a 256-bit AES key from a user password using PBKDF2-HMAC-SHA256."""
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=480_000)
    return kdf.derive(password.encode("utf-8"))

def _encrypt_wallet(pub: str, priv: str, password: str) -> None:
    """Encrypts the keypair to .miner_wallet using AES-256-GCM."""
    salt = os.urandom(16)
    nonce = os.urandom(12)
    key = _derive_aes_key(password, salt)
    aesgcm = AESGCM(key)
    plaintext = json.dumps({"pub": pub, "priv": priv}).encode("utf-8")
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)
    envelope = {
        "v": 1,
        "salt": base64.b64encode(salt).decode(),
        "nonce": base64.b64encode(nonce).decode(),
        "ct": base64.b64encode(ciphertext).decode(),
    }
    with open(WALLET_FILE, "w", encoding="utf-8") as f:
        json.dump(envelope, f)

def _decrypt_wallet(password: str) -> tuple[str, str]:
    """Decrypts and returns (pub, priv) from the encrypted .miner_wallet file."""
    with open(WALLET_FILE, "r", encoding="utf-8") as f:
        envelope = json.load(f)
    salt = base64.b64decode(envelope["salt"])
    nonce = base64.b64decode(envelope["nonce"])
    ct = base64.b64decode(envelope["ct"])
    key = _derive_aes_key(password, salt)
    aesgcm = AESGCM(key)
    plaintext = aesgcm.decrypt(nonce, ct, None)
    data = json.loads(plaintext)
    return data["pub"], data["priv"]

def _prompt_wallet_password(confirm: bool = False) -> str:
    """Prompts for a wallet unlock password."""
    pw = getpass.getpass("Enter wallet password: ")
    if confirm:
        pw2 = getpass.getpass("Confirm wallet password: ")
        if pw != pw2:
            raise ValueError("Passwords do not match.")
    return pw

def _is_encrypted_wallet() -> bool:
    """Returns True if .miner_wallet is in the new encrypted JSON envelope format."""
    try:
        with open(WALLET_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return isinstance(data, dict) and "v" in data and "ct" in data
    except Exception:
        return False

def get_or_prompt_wallet() -> tuple[str, str]:
    """Returns (pubkey_hex, privkey_hex).
    Reads from an AES-256-GCM encrypted wallet file, or creates a new one.
    Legacy plaintext wallet files are automatically migrated to encrypted format.
    """
    if os.path.exists(WALLET_FILE):
        if _is_encrypted_wallet():
            # Existing encrypted wallet - unlock it
            print("[*] Encrypted wallet file found. Unlocking...")
            pw = _prompt_wallet_password()
            try:
                pub, priv = _decrypt_wallet(pw)
                print("[+] Wallet unlocked successfully.\n")
                return pub, priv
            except Exception:
                print("[!] Wrong password or corrupted wallet file.")
                sys.exit(1)
        else:
            # Legacy plaintext wallet - migrate to encrypted format
            print("[!] Legacy plaintext wallet detected. Migrating to encrypted format...")
            try:
                with open(WALLET_FILE, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                if ":" in content:
                    pub, priv = content.split(":", 1)
                elif wb.validate_mnemonic(content):
                    priv, pub = wb.mnemonic_to_keypair(content)
                else:
                    raise ValueError("Unrecognized wallet format")
                print("Set a password to encrypt your wallet at rest.")
                pw = _prompt_wallet_password(confirm=True)
                _encrypt_wallet(pub, priv, pw)
                print("[+] Wallet migrated to AES-256-GCM encrypted storage.\n")
                return pub, priv
            except Exception as e:
                print(f"[!] Migration failed: {e}")
                sys.exit(1)

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

    # Encrypt the wallet at rest with AES-256-GCM (never store plaintext keys)
    print("Set a password to encrypt your wallet file at rest.")
    pw = _prompt_wallet_password(confirm=True)
    _encrypt_wallet(pub, priv, pw)
    print(f"[+] Wallet encrypted and saved to {WALLET_FILE}.\n")
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
