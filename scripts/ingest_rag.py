import os
import json
import re
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("OPENAI_API_KEY")

ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = ROOT / "docs"
OUT_FILE = ROOT / "data" / "embeddings.json"
OUT_FILE.parent.mkdir(exist_ok=True)

def list_docs():
	"""Lista apenas o documento PDF específico da Copa do Mundo."""
	# Procura especificamente pelo PDF da Copa do Mundo 2026
	target_pdf = DOCS_DIR / "Seminar_DCSD_Foot_20170126.pdf"
	docs = []
	
	if target_pdf.exists():
		docs.append(str(target_pdf))
		print(f"Encontrado documento alvo: {target_pdf.name}")
	else:
		print("❌ Arquivo 'Seminar_DCSD_Foot_20170126.pdf' não encontrado na raiz do projeto.")
		print("Por favor, certifique-se de que o arquivo está na raiz do projeto.")
	
	return docs

def extract_pages_from_pdf(pdf_path):
	"""Extrai texto por página de um PDF usando PyPDF2."""
	try:
		import PyPDF2
		with open(pdf_path, 'rb') as f:
			reader = PyPDF2.PdfReader(f)
			pages = []
			for idx, page in enumerate(reader.pages, start=1):
				page_text = page.extract_text() or ""
				pages.append((idx, page_text))
		return pages
	except ImportError:
		print("PyPDF2 não instalado. Instale com: pip install PyPDF2")
		return []
	except Exception as e:
		print(f"Erro ao ler PDF {pdf_path}: {e}")
		return []

def chunk_text(text, chunk_size=500, overlap=100):
	"""Divide texto em chunks com overlap."""
	words = text.split()
	chunks = []
	for i in range(0, len(words), chunk_size - overlap):
		chunk = " ".join(words[i:i + chunk_size])
		if chunk.strip():
			chunks.append(chunk)
	return chunks

def generate_embeddings(texts):
	try:
		import requests
		import json
		
		if not API_KEY:
			raise ValueError("OPENAI_API_KEY não configurada")
		
		# Usa requests diretamente para evitar problemas de proxy com openai v1.9.0
		api_url = "https://api.openai.com/v1/embeddings"
		headers = {
			"Authorization": f"Bearer {API_KEY}",
			"Content-Type": "application/json"
		}
		payload = {
			"model": "text-embedding-3-small",
			"input": texts
		}
		
		resp = requests.post(api_url, json=payload, headers=headers, timeout=30)
		
		if resp.status_code != 200:
			raise Exception(f"OpenAI API error: {resp.status_code} {resp.text}")
		
		resp_data = resp.json()
		return [item['embedding'] for item in resp_data['data']]
	except Exception as e:
		print(f"Erro ao gerar embeddings: {e}")
		# fallback simples (não semântico) — apenas para testes locais
		return [[float(abs(hash(t)) % 1000) for _ in range(8)] for t in texts]

def ingest():
	"""Processa documentos, gera embeddings e salva."""
	docs = list_docs()
	if not docs:
		return
	
	print(f"Processando {len(docs)} documento(s)...")
	entries = []
	
	for path in docs:
		print(f"Processando: {path}")
		path_obj = Path(path)
		
		if path_obj.suffix.lower() == ".pdf":
			pages = extract_pages_from_pdf(path)
			content = "\n".join([p[1] for p in pages]) if pages else ""
		else:
			try:
				with open(path, "r", encoding="utf-8") as f:
					content = f.read()
			except Exception as e:
				print(f"Erro ao ler {path}: {e}")
				content = ""
		
		if not content.strip():
			print(f"Nenhum conteúdo extraído de {path}")
			continue
		
		# Divide o documento em chunks
		try:
			chunk_size = int(os.getenv("CHUNK_SIZE", "500"))
		except Exception:
			chunk_size = 500
		try:
			overlap = int(os.getenv("CHUNK_OVERLAP", "100"))
		except Exception:
			overlap = 100
		if path_obj.suffix.lower() == ".pdf" and pages:
			total_chunks = 0
			for page_num, page_text in pages:
				page_chunks = chunk_text(page_text, chunk_size=chunk_size, overlap=overlap)
				for chunk in page_chunks:
					entries.append({
						"path": str(path_obj.name),
						"chunk_id": len(entries),
						"text": chunk,
						"page": page_num,
					})
				total_chunks += len(page_chunks)
			print(f"  -> {total_chunks} chunks criados (com página)")
		else:
			chunks = chunk_text(content, chunk_size=chunk_size, overlap=overlap)
			print(f"  -> {len(chunks)} chunks criados")
			# Cria entrada para cada chunk
			for i, chunk in enumerate(chunks):
				entries.append({
					"path": str(path_obj.name),
					"chunk_id": i,
					"text": chunk
				})
	
	if not entries:
		print("Nenhum conteúdo para processar.")
		return
	
	print(f"\nGerando embeddings para {len(entries)} chunks...")
	texts = [e["text"] for e in entries]
	
	# Processa em lotes para evitar exceder limites da API
	batch_size = 100
	all_embeddings = []
	for i in range(0, len(texts), batch_size):
		batch = texts[i:i + batch_size]
		print(f"  Processando lote {i//batch_size + 1}/{(len(texts)-1)//batch_size + 1}...")
		embs = generate_embeddings(batch)
		all_embeddings.extend(embs)
	
	# Adiciona embeddings às entradas
	for e, emb in zip(entries, all_embeddings):
		e["embedding"] = emb
	
	# Salva resultado
	with open(OUT_FILE, "w", encoding="utf-8") as fh:
		json.dump(entries, fh, ensure_ascii=False, indent=2)
	print(f"\n✅ Sucesso! {len(entries)} chunks salvos em {OUT_FILE}")
	print("➡️ Próximo passo recomendado: python3 scripts/build_faiss_index.py")

if __name__ == "__main__":
	ingest()
