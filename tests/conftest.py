import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://aries:test-password@127.0.0.1:5432/aries"
)
os.environ.setdefault("MINIO_ACCESS_KEY", "aries-test")
os.environ.setdefault("MINIO_SECRET_KEY", "test-minio-password")
os.environ.setdefault("API_BEARER_TOKEN", "test-api-bearer-token")
