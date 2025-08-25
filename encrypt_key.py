from cryptography.fernet import Fernet
import os

def get_encryption_key():
    key_path = "encryption_key.key"
    if os.path.exists(key_path):
        with open(key_path, "rb") as f:
            key = f.read()
    else:
        key = Fernet.generate_key()
        with open(key_path, "wb") as f:
            f.write(key)
    return Fernet(key)

# API key Groq yang Anda berikan
groq_api_key = "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"
fernet = get_encryption_key()
encrypted_key = fernet.encrypt(groq_api_key.encode()).decode()
print(f"ENCRYPTED_GROQ_API_KEY: {encrypted_key}")