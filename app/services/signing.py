"""Ed25519 signing for provenance entries.

On first run we generate a service signing keypair and write it to keys/ (gitignored).
Subsequent runs load the existing key. The public key is shipped inside every
rights-holder statement so the recipient can verify offline without trusting us.
"""

from __future__ import annotations

from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from app.config import KEYS_DIR, PRIVATE_KEY_PATH, PUBLIC_KEY_PATH


def ensure_keypair() -> None:
    """Generate the service signing keypair if one isn't already on disk."""
    KEYS_DIR.mkdir(parents=True, exist_ok=True)
    if PRIVATE_KEY_PATH.exists() and PUBLIC_KEY_PATH.exists():
        return

    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    PRIVATE_KEY_PATH.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    PUBLIC_KEY_PATH.write_bytes(
        public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    # Permission tightening on the private key — best-effort; harmless if no-op.
    try:
        PRIVATE_KEY_PATH.chmod(0o600)
    except OSError:
        pass


def _load_private_key() -> Ed25519PrivateKey:
    ensure_keypair()
    data = PRIVATE_KEY_PATH.read_bytes()
    key = serialization.load_pem_private_key(data, password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise TypeError("service key is not Ed25519")
    return key


def _load_public_key() -> Ed25519PublicKey:
    ensure_keypair()
    data = PUBLIC_KEY_PATH.read_bytes()
    key = serialization.load_pem_public_key(data)
    if not isinstance(key, Ed25519PublicKey):
        raise TypeError("service public key is not Ed25519")
    return key


def sign(message: bytes) -> bytes:
    return _load_private_key().sign(message)


def verify(signature: bytes, message: bytes, public_key_pem: bytes | None = None) -> bool:
    """Verify a signature. Pass a specific public-key PEM to verify offline."""
    if public_key_pem is not None:
        pub = serialization.load_pem_public_key(public_key_pem)
        if not isinstance(pub, Ed25519PublicKey):
            return False
    else:
        pub = _load_public_key()
    try:
        pub.verify(signature, message)
    except InvalidSignature:
        return False
    return True


def public_key_pem() -> str:
    return PUBLIC_KEY_PATH.read_bytes().decode("ascii") if PUBLIC_KEY_PATH.exists() else (
        _public_key_pem_from_loaded()
    )


def _public_key_pem_from_loaded() -> str:
    ensure_keypair()
    return Path(PUBLIC_KEY_PATH).read_bytes().decode("ascii")
