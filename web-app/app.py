import os
from flask import Flask, render_template, request, flash, redirect, url_for
import requests

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev_key")

FUNCTION_URL = os.getenv("FUNCTION_URL", "https://sua-azure-function.azurewebsites.net/api/GetPosts")

def fetch_posts(subreddit, sort, limit):
    """Chama a Azure Function e retorna lista de posts ou None em caso de erro."""
    try:
        resp = requests.get(FUNCTION_URL, params={
            "subreddit": subreddit,
            "sort": sort,
            "limit": limit
        })
        resp.raise_for_status()
        return resp.json()  # espera uma lista de dicts
    except Exception as e:
        flash(f"Erro ao obter posts: {e}", "danger")
        return None

@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")

@app.route("/search", methods=["GET"])
def search():
    subreddit = request.args.get("subreddit", "").strip()
    sort = request.args.get("sort", "hot")
    try:
        limit = int(request.args.get("limit", 10))
    except ValueError:
        flash("O limite deve ser um número inteiro.", "warning")
        return redirect(url_for("index"))

    posts = fetch_posts(subreddit, sort, limit)
    if posts is None:
        return redirect(url_for("index"))

    # Armazena os posts na sessão ou passa diretamente
    return render_template("results.html", posts=posts, subreddit=subreddit, sort=sort, limit=limit)

@app.route("/detail_all", methods=["GET"])
def detail_all():
    """Exibe todos os posts em detalhe."""
    # Você pode obter os mesmos parâmetros de search ou receber a lista via query string/session
    subreddit = request.args.get("subreddit", "")
    sort = request.args.get("sort", "hot")
    try:
        limit = int(request.args.get("limit", 10))
    except ValueError:
        limit = 10

    posts = fetch_posts(subreddit, sort, limit)
    if posts is None:
        return redirect(url_for("index"))

    return render_template("detail_all.html", posts=posts)

@app.route("/details/<post_id>", methods=["GET"])
def details(post_id):
    """Exibe detalhes de um único post, filtrando pela ID."""
    # Para não fazer nova request, poderia ter salvo posts em sessão. Aqui, refazemos fetch.
    subreddit = request.args.get("subreddit", "")
    sort = request.args.get("sort", "hot")
    try:
        limit = int(request.args.get("limit", 10))
    except ValueError:
        limit = 10

    posts = fetch_posts(subreddit, sort, limit)
    if posts is None:
        return redirect(url_for("index"))

    # Busca o post com a ID correspondente
    post = next((p for p in posts if p.get("id") == post_id), None)
    if not post:
        flash(f"Post com ID {post_id} não encontrado.", "warning")
        return redirect(url_for("detail_all", subreddit=subreddit, sort=sort, limit=limit))

    return render_template("details.html", post=post)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
