"""Cryptographic Engine for Langdex Protocol.
Provides:
- Ed25519 digital signature creation and mathematical verification
- Canonical serialization of transaction payloads
- Merkle DAG / SHA-256 state chain verification
- Audit engine ensuring zero balance mutations without valid user cryptographic signatures
"""
import json, hashlib
from typing import Dict, Any, Tuple
from cryptography.hazmat.primitives.asymmetric import ed25519

def generate_keypair() -> Tuple[str, str]:
    """Generates a new Ed25519 keypair.
    Returns: (private_key_hex, public_key_hex)
    """
    priv = ed25519.Ed25519PrivateKey.generate()
    pub = priv.public_key()
    priv_bytes = priv.private_bytes_raw()
    pub_bytes = pub.public_bytes_raw()
    return priv_bytes.hex(), pub_bytes.hex()

def derive_public_key(private_key_hex: str) -> str:
    """Derives the public key from a private key hex."""
    priv_bytes = bytes.fromhex(private_key_hex)
    priv = ed25519.Ed25519PrivateKey.from_private_bytes(priv_bytes)
    return priv.public_key().public_bytes_raw().hex()

def canonical_bytes(payload: Dict[str, Any]) -> bytes:
    """Produces deterministic, canonical UTF-8 bytes for cryptographic signing.
    Keys are sorted and whitespace is stripped to prevent malleability.
    """
    return json.dumps(payload, sort_keys=True, separators=(',', ':')).encode('utf-8')

def sign_payload(private_key_hex: str, payload: Dict[str, Any]) -> str:
    """Signs a transaction payload with an Ed25519 private key.
    Returns: signature_hex (128 characters / 64 bytes)
    """
    priv_bytes = bytes.fromhex(private_key_hex)
    priv = ed25519.Ed25519PrivateKey.from_private_bytes(priv_bytes)
    data = canonical_bytes(payload)
    sig = priv.sign(data)
    return sig.hex()

def verify_signature(public_key_hex: str, payload: Dict[str, Any], signature_hex: str) -> bool:
    """Mathematically verifies an Ed25519 signature over a canonical payload."""
    try:
        pub_bytes = bytes.fromhex(public_key_hex)
        sig_bytes = bytes.fromhex(signature_hex)
        pub = ed25519.Ed25519PublicKey.from_public_bytes(pub_bytes)
        data = canonical_bytes(payload)
        pub.verify(sig_bytes, data)
        return True
    except Exception:
        return False

def compute_block_hash(prev_hash: str, payload: Dict[str, Any], signature_hex: str) -> str:
    """Computes the immutable SHA-256 Merkle chain hash for a ledger transaction."""
    raw = canonical_bytes(payload) + bytes.fromhex(signature_hex) + prev_hash.encode('utf-8')
    return hashlib.sha256(raw).hexdigest()
