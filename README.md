# Langdex

Langdex is an open-source protocol that tracks active programming language adoption across public version control systems and package registries, turning those metrics into daily index prices.

Instead of relying on search engine trends or subjective surveys, Langdex derives prices from daily git activity and package downloads, settled against an internal accounting unit called DEK.

The protocol runs as an independent reference node over Tor, with validator nodes confirming Git telemetry and solving cryptographic proof-of-work puzzles.

## How It Works

### 1. Data Collection
Every 24 hours, the node samples developer activity across multiple independent sources:
* **Git Smart HTTP Protocol:** Fetches the latest HEAD commit SHAs directly from representative repositories (e.g. CPython, Rust, Go, React, Solidity) via `info/refs?service=git-upload-pack` without relying on third-party scrapers.
* **Package Registries:** Queries daily download metrics from PyPI, npm, and crates.io.
* **Multi-Forge Tracking:** Ingests activity signals from GitHub, GitLab, Codeberg (Gitea API), and Software Heritage persistent identifiers (SWHIDs).

### 2. Index Calculation
Raw counts are normalized through a deterministic pipeline:
1. **Trailing Median Filter:** Daily values are clipped at 2x the 14-day median to suppress artificial spam surges.
2. **Weekend Smoothing:** A 7-day rolling window removes typical weekend drops in developer output.
3. **Ecosystem Share:** Each language's share is calculated as its 7-day moving average divided by total activity across all tracked languages.
4. **Base Price:** Prices are normalized relative to day zero, starting at 100.00 DEK. A language whose relative share doubles moves to 200.00 DEK.

Prices reflect external software production, not order book speculation. Large trades cannot move the underlying adoption price.

### 3. Proof of Telemetry Work (PoTW) Mining
Validator nodes participate in daily consensus and earn block rewards (50 DEK per 24-hour epoch):
1. The validator pulls authentic Git commit hashes for the active day across tracked repositories.
2. The commits are organized into a binary Merkle tree, producing a Merkle root.
3. The node solves a Proof of Work puzzle: finding a 32-bit nonce such that:
   `SHA-256(MerkleRoot + MinerPubKey + EpochDay + Nonce) < TargetDifficulty`
   (Target requires 16 leading zero bits).
4. Finding the nonce proves that the validator processed the Git data and spent computational cycles sealing the epoch.
5. The winning nonce, block hash, and Merkle root are recorded in the local attestation ledger.

### 4. Non-Custodial Cryptography
* **BIP-39 Wallets:** Node keys and user identities are generated from standard 12-word BIP-39 mnemonic seed phrases with SHA-256 checksum validation and PBKDF2 HMAC-SHA512 key stretching.
* **Ed25519 Signatures:** Transactions and mining proofs are signed with Ed25519 private keys. The server validates signatures mathematically before any ledger mutation.
* **Immutable Merkle DAG:** Every transaction links to the previous block hash:
  `BlockHash = SHA-256(CanonicalPayload + Signature + PrevBlockHash)`
  Tampering with any historical entry invalidates all subsequent blocks. Anyone can verify ledger integrity by calling `/api/ledger_audit`.

### 5. Settlement Mechanics
* **Fixed Supply:** DEK has an absolute hard cap of 20,502,006 tokens.
* **No ICO or Presale:** Zero pre-mine, zero investor allocations, zero token sales.
* **Solvency Protection:** Language positions have aggregate open interest limits and individual exposure caps to guarantee protocol reserves cannot be drained.
* **Deflationary Burn:** 50% of trade spread fees are directed to `0x000000000000000000000000000000000000dead`.

## Installation and Quickstart

### Prerequisites
* Python 3.10+
* Git
* SQLite3

### Setup
```bash
git clone https://github.com/NaelVask/langidex.git
cd langidex
pip install -r requirements.txt
```

### Running the API and Web UI
```bash
uvicorn api:app --host 127.0.0.1 --port 8000
```
Open `http://127.0.0.1:8000` in your browser.

### Running a Validator Miner Node
To verify the daily Git telemetry and solve the Proof of Work puzzle:
```bash
python miner.py
```
On first launch, you will be prompted to generate a new 12-word BIP-39 seed phrase or enter an existing one. Your seed phrase is saved to `.miner_wallet`.

### Running Over Tor
Langdex includes hidden service support out of the box. Add the following to your `torrc`:
```text
HiddenServiceDir /var/lib/tor/langdex_service/
HiddenServicePort 80 127.0.0.1:8000
```
Then start the Tor daemon to get your `.onion` address:
```bash
cat /var/lib/tor/langdex_service/hostname
```

## API Reference
* `GET /api/assets` - Real-time language index prices, changes, and historical charts
* `GET /api/oracle_status` - Data source status, multi-source weighting, anti-sybil filters
* `GET /api/tokenomics` - Circulating supply, total mined, block height, burn stats
* `GET /api/verified_proofs` - Sealed Git commit hashes and Merkle roots
* `GET /api/ledger_audit` - Full cryptographic integrity check across all blocks
* `POST /api/signed_tx` - Submit an Ed25519-signed transaction
* `GET /api/p2p/peers` - Active peer nodes on the network

## License
MIT License. Created by Nael Vask.
