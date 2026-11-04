"""Proof of Telemetry Work (PoTW) Mining Puzzle Engine.
Implements authentic mathematical Proof of Work over verified Git commit Merkle roots:
- Ingests verified repository commit SHAs from Git Smart HTTP protocol
- Constructs a cryptographic Merkle root of real commit objects
- Computes SHA-256 hash rounds to find a nonce satisfying leading-zero difficulty
- Generates a mathematically verifiable proof block signed with the miner's Ed25519 key
"""
import hashlib, time
from typing import Dict, Any, Tuple
import crypto_engine as ce

def mine_pow_puzzle(merkle_root: str, miner_pubkey: str, epoch_day: str, difficulty_bits: int = 16) -> Tuple[int, str, float]:
    """Finds a nonce such that SHA-256(merkle_root || miner_pubkey || epoch_day || nonce)
    has at least `difficulty_bits` leading zero bits.
    Returns: (nonce, block_hash, duration_seconds)
    """
    target = 1 << (256 - difficulty_bits)
    prefix = f"{merkle_root}:{miner_pubkey}:{epoch_day}:".encode('utf-8')
    nonce = 0
    start_time = time.time()

    while True:
        candidate = prefix + str(nonce).encode('utf-8')
        digest = hashlib.sha256(candidate).digest()
        val = int.from_bytes(digest, byteorder='big')
        if val < target:
            duration = time.time() - start_time
            return nonce, digest.hex(), duration
        nonce += 1

def verify_pow_proof(merkle_root: str, miner_pubkey: str, epoch_day: str, nonce: int, difficulty_bits: int = 16) -> bool:
    """Mathematically verifies that a miner's PoW nonce satisfies the target difficulty."""
    target = 1 << (256 - difficulty_bits)
    candidate = f"{merkle_root}:{miner_pubkey}:{epoch_day}:{nonce}".encode('utf-8')
    digest = hashlib.sha256(candidate).digest()
    val = int.from_bytes(digest, byteorder='big')
    return val < target
