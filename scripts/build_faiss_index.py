import json
from pathlib import Path


def build_faiss_index():
    root = Path(__file__).resolve().parents[1]
    embeddings_path = root / "data" / "embeddings.json"
    output_dir = root / "data" / "faiss"
    output_dir.mkdir(parents=True, exist_ok=True)

    if not embeddings_path.exists():
        raise FileNotFoundError(
            f"Arquivo nao encontrado: {embeddings_path}. Rode antes: python3 scripts/ingest_rag.py"
        )

    with open(embeddings_path, "r", encoding="utf-8") as fh:
        entries = json.load(fh)

    if not entries:
        raise ValueError("embeddings.json vazio, nao ha dados para indexar.")

    try:
        import faiss
        import numpy as np
    except Exception as exc:
        raise RuntimeError(
            "Dependencias FAISS indisponiveis. Instale requirements.txt e tente novamente."
        ) from exc

    vectors = np.array([entry["embedding"] for entry in entries], dtype="float32")
    if vectors.ndim != 2:
        raise ValueError("Formato de embeddings invalido.")

    dim = vectors.shape[1]
    faiss.normalize_L2(vectors)

    base_index = faiss.IndexFlatIP(dim)
    index = faiss.IndexIDMap2(base_index)
    ids = np.arange(len(entries), dtype="int64")
    index.add_with_ids(vectors, ids)

    faiss.write_index(index, str(output_dir / "index.faiss"))

    metadata = [
        {
            "path": entry.get("path"),
            "chunk_id": entry.get("chunk_id"),
            "text": entry.get("text", ""),
            "page": entry.get("page"),
        }
        for entry in entries
    ]
    with open(output_dir / "metadata.json", "w", encoding="utf-8") as fh:
        json.dump(metadata, fh, ensure_ascii=False, indent=2)

    print(
        f"Indice FAISS criado com sucesso: {len(entries)} vetores em {output_dir / 'index.faiss'}"
    )


if __name__ == "__main__":
    build_faiss_index()
