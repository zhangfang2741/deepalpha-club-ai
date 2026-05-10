
import time
import bcrypt

def test_bcrypt():
    password = "Password123!"
    start = time.time()
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password.encode(), salt)
    end = time.time()
    print(f"Hash time (rounds=12): {end - start:.4f}s")
    
    start = time.time()
    bcrypt.checkpw(password.encode(), hashed)
    end = time.time()
    print(f"Verify time: {end - start:.4f}s")

if __name__ == "__main__":
    test_bcrypt()
