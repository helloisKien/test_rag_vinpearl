"""DA10 — cấu hình tập trung, đọc từ .env (Phase 0)."""
from __future__ import annotations
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Postgres
    pg_host: str = "localhost"
    pg_port: int = 5432
    pg_user: str = "da10"
    pg_password: str = "da10"
    pg_db: str = "da10"

    # OpenSearch
    os_host: str = "localhost"
    os_port: int = 9200
    os_index: str = "idx_hotel_chunks_v1.0"
    os_alias: str = "hotel_chunks"

    # Qdrant
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection: str = "col_documents_v1.0"

    # Models
    embed_model: str = "BAAI/bge-m3"
    rerank_model: str = "BAAI/bge-reranker-v2-m3"
    embed_dim: int = 1024
    index_version: str = "v1.0"

    # Paths
    data_dir: str = "data"
    ontology_dir: str = "ontology"
    golden_set: str = "golden_dataset/golden_set_v1.json"

    @property
    def pg_dsn(self) -> str:
        return f"host={self.pg_host} port={self.pg_port} user={self.pg_user} password={self.pg_password} dbname={self.pg_db}"


settings = Settings()
