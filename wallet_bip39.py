"""BIP-39 Standard Cryptographic Wallet & Key Derivation for Langdex.
Implements:
- Standard 2,048-word English dictionary with SHA-256 4-bit checksum validation
- PBKDF2 HMAC-SHA512 2,048-iteration master seed derivation
- Ed25519 asymmetric keypair derivation for signing transactions and PoW blocks
"""
import mnemonic
from cryptography.hazmat.primitives.asymmetric import ed25519
from typing import Tuple

_m = mnemonic.Mnemonic('english')

def generate_mnemonic() -> str:
    """Generates a cryptographically secure 12-word BIP-39 mnemonic seed phrase."""
    return _m.generate(strength=128)

def validate_mnemonic(phrase: str) -> bool:
    """Mathematically verifies the BIP-39 checksum across all 12 words."""
    clean = " ".join(phrase.strip().lower().split())
    return _m.check(clean)

def mnemonic_to_keypair(phrase: str, passphrase: str = "") -> Tuple[str, str]:
    """Derives standard Ed25519 private key hex and public key hex from a BIP-39 seed phrase.
    Returns: (private_key_hex, public_key_hex)
    """
    clean = " ".join(phrase.strip().lower().split())
    if not validate_mnemonic(clean):
        raise ValueError("Invalid BIP-39 mnemonic phrase or failed checksum.")

    seed_bytes = _m.to_seed(clean, passphrase=passphrase)
    # Use first 32 bytes of the 512-bit master seed as Ed25519 private key seed
    priv_bytes = seed_bytes[:32]
    priv = ed25519.Ed25519PrivateKey.from_private_bytes(priv_bytes)
    pub = priv.public_key()
    return priv.private_bytes_raw().hex(), pub.public_bytes_raw().hex()
