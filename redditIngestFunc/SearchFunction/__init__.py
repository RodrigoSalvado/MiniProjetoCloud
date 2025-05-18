import os
import logging
import json
import requests
from requests.auth import HTTPBasicAuth
import azure.functions as func
from azure.cosmos import CosmosClient

# Import das funções de tradução de outro módulo
from translator import detect_language, translate_to_english

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Leitura flexível de credenciais Reddit ---
CLIENT_ID = (
    os.environ.get("CLIENT_ID")
    or os.environ.get("REDDIT_CLIENT_ID")
)
CLIENT_SECRET = (
    os.environ.get("SECRET")
    or os.environ.get("REDDIT_CLIENT_SECRET")
)
REDDIT_USER = os.environ.get("REDDIT_USER")
REDDIT_PASSWORD = os.environ.get("REDDIT_PASSWORD")

# --- Azure Translator Config (não usado aqui, mas obrigatórias no módulo translation) ---
TRANSLATOR_KEY = os.environ.get("TRANSLATOR_KEY")
TRANSLATOR_ENDPOINT = os.environ.get("TRANSLATOR_ENDPOINT")
TRANSLATOR_REGION = os.environ.get("TRANSLATOR_REGION", "francecentral")

# --- Cosmos DB ---
COSMOS_ENDPOINT = os.environ.get("COSMOS_ENDPOINT")
COSMOS_KEY      = os.environ.get("COSMOS_KEY")
COSMOS_DATABASE = os.environ.get("COSMOS_DATABASE", "RedditApp")
COSMOS_CONTAINER = os.environ.get("COSMOS_CONTAINER", "posts")

# --- Log de presença das variáveis (sem vazar dados) ---
logger.info(f"Credenciais Reddit: CLIENT_ID={'OK' if CLIENT_ID else 'MISSING'}, "
            f"CLIENT_SECRET={'OK' if CLIENT_SECRET else 'MISSING'}, "
            f"REDDIT_USER={'OK' if REDDIT_USER else 'MISSING'}, "
            f"REDDIT_PASSWORD={'OK' if REDDIT_PASSWORD else 'MISSING'}")
logger.info(f"Cosmos DB: ENDPOINT={'OK' if COSMOS_ENDPOINT else 'MISSING'}, "
            f"KEY={'OK' if COSMOS_KEY else 'MISSING'}")
logger.info(f"Translator Module: IMPORT OK (funções em translation.py)")


def main(req: func.HttpRequest) -> func.HttpResponse:
    logger.info("HTTP trigger recebido para buscar Reddit e gravar no Cosmos")

    subreddit = req.params.get("subreddit")
    if not subreddit:
        return func.HttpResponse(
            json.dumps({"error": "Falta parâmetro 'subreddit'."}, ensure_ascii=False),
            status_code=400, mimetype="application/json"
        )

    try:
        limit = int(req.params.get("limit", "10"))
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "Parâmetro 'limit' deve ser inteiro."}, ensure_ascii=False),
            status_code=400, mimetype="application/json"
        )

    sort = req.params.get("sort", "hot")

    if not all([CLIENT_ID, CLIENT_SECRET, REDDIT_USER, REDDIT_PASSWORD]):
        missing = [k for k,v in {
            "CLIENT_ID":CLIENT_ID, "CLIENT_SECRET":CLIENT_SECRET,
            "REDDIT_USER":REDDIT_USER, "REDDIT_PASSWORD":REDDIT_PASSWORD
        }.items() if not v]
        msg = f"Faltam estas app settings: {', '.join(missing)}"
        logger.error(msg)
        return func.HttpResponse(
            json.dumps({"error": msg}, ensure_ascii=False),
            status_code=500, mimetype="application/json"
        )

    try:
        posts = _fetch_and_store(subreddit, sort, limit)
    except Exception as e:
        logger.error(f"Erro interno na ingestão: {e}", exc_info=e)
        return func.HttpResponse(
            json.dumps({"error": str(e)}, ensure_ascii=False),
            status_code=500, mimetype="application/json"
        )

    sanitized = []
    for p in posts:
        sanitized.append({
            "id": p.get("id"),
            "subreddit": p.get("subreddit"),
            "title": p.get("title"),
            "title_eng": p.get("title_eng"),
            "url": p.get("url"),
            "score": p.get("score")
        })

    body = json.dumps({"posts": sanitized}, ensure_ascii=False)
    return func.HttpResponse(body, status_code=200, mimetype="application/json")


def _fetch_and_store(subreddit: str, sort: str, limit: int):
    # Autenticação OAuth2 no Reddit
    auth = HTTPBasicAuth(CLIENT_ID, CLIENT_SECRET)
    token_res = requests.post(
        "https://www.reddit.com/api/v1/access_token",
        auth=auth,
        data={
            "grant_type": "password",
            "username": REDDIT_USER,
            "password": REDDIT_PASSWORD
        },
        headers={"User-Agent": f"{REDDIT_USER}/0.1"}
    )
    token_res.raise_for_status()
    token = token_res.json().get("access_token")
    if not token:
        raise RuntimeError("Não obteve access_token do Reddit.")

    # Fetch de posts
    res = requests.get(
        f"https://oauth.reddit.com/r/{subreddit}/{sort}",
        headers={
            "Authorization": f"bearer {token}",
            "User-Agent": f"{REDDIT_USER}/0.1"
        },
        params={"limit": limit}
    )
    res.raise_for_status()
    children = res.json().get("data", {}).get("children", [])
    if not isinstance(children, list):
        raise RuntimeError("Resposta inesperada da API do Reddit.")

    client = CosmosClient(COSMOS_ENDPOINT, COSMOS_KEY)
    db     = client.create_database_if_not_exists(COSMOS_DATABASE)
    cont   = db.create_container_if_not_exists(
        id=COSMOS_CONTAINER,
        partition_key={"path": "/subreddit"}
    )

    posts = []
    for c in children:
        d = c.get("data", {})
        rid = d.get("id")
        if not rid:
            continue
        title = d.get("title", "")
        # 1) Detecta idioma e traduz via módulo importado
        lang = detect_language(title)
        title_eng = translate_to_english(title, from_lang=lang)

        item = {
            "id":        f"{subreddit}_{rid}",
            "subreddit": subreddit,
            "title":     title,
            "title_eng": title_eng,
            "url":       d.get("url", ""),
            "score":     d.get("score", 0)
        }
        cont.upsert_item(item)
        logger.info(f"Upserted item: {item['id']}")
        posts.append(item)

    return posts
