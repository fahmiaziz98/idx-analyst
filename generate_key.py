import secrets
from src.core.security import SecureAPIKeyManager


def generate_secure_api_key(prefix: str = "sk") -> str:
    """
    Generate cryptographically secure API key.
    
    Args:
        prefix: Key prefix (default: 'sk' for secret key)
        
    Returns:
        Secure random API key
    """
    random_bytes = secrets.token_urlsafe(32)
    return f"{prefix}_{random_bytes}"


# CLI utility functions for key management
def encrypt_keys_cli():
    """CLI utility to encrypt API keys."""
    print("🔐 API Key Encryption Utility")
    print("=" * 50)

    keys_input = input("Enter API keys (comma-separated): ")
    keys = [k.strip() for k in keys_input.split(",") if k.strip()]

    if not keys:
        print("❌ No keys provided")
        return

    manager = SecureAPIKeyManager()
    encrypted = manager.encrypt_api_keys(keys)

    print("\n✅ Keys encrypted successfully!")
    print("\nAdd this to your .env file:")
    print(f"API_KEYS_ENCRYPTED={encrypted}")
    print("\nAnd the encryption key:")
    print(f"ENCRYPTION_KEY={manager.encryption_key.decode()}")


def generate_key_cli():
    """CLI utility to generate new API key."""
    print("🔑 API Key Generation Utility")
    print("=" * 50)

    new_key = generate_secure_api_key()
    print(f"\n✅ Generated API key:\n{new_key}")
    print("\n⚠️  Save this key securely - it cannot be recovered!")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        if sys.argv[1] == "encrypt":
            encrypt_keys_cli()
        elif sys.argv[1] == "generate":
            generate_key_cli()
        else:
            print("Usage: python security.py [encrypt|generate]")
    else:
        print("Usage: python security.py [encrypt|generate]")