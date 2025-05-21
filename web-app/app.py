import os
import requests
from flask import Flask, render_template, request, flash, redirect, url_for, session

app = Flask(__name__)
# Garante que a sessão seja criptografada
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev_secret_key")

FUNCTION_URL = os.getenv("FUNCTION_URL")

@app.route("/", methods=["GET"])
def home():
    # Sempre limpa sessão antiga ao voltar para home
    session.pop("posts", None)
    session.pop("search_params", None)
    return render_template("index.html", posts=None)

@app.route("/search", methods=["GET"])
def search():
    subreddit = request.args.get("subreddit", "").strip()
    sort = request.args.get("sort", "hot").strip()
    limit_str = request.args.get("limit", "10").strip()

    # Valida limit
    try:
        limit = int(limit_str)
    except ValueError:
        flash("O campo 'Número de posts' deve ser um número inteiro.", "warning")
        return redirect(url_for("home"))

    # Chama Azure Function
    try:
        resp = requests.get(
            FUNCTION_URL,
            params={"subreddit": subreddit, "sort": sort, "limit": limit},
            timeout=30
        )
        resp.raise_for_status()
        data = resp.json()
        posts = data.get("posts", data)  # aceita tanto {"posts": [...]} quanto [...]
    except Exception as e:
        flash(f"Erro ao buscar dados: {e}", "danger")
        return redirect(url_for("home"))

    # Guarda posts e parâmetros na sessão
    session["posts"] = posts
    session["search_params"] = {
        "subreddit": subreddit,
        "sort": sort,
        "limit": limit
    }

    # Renderiza index.html com posts
    return render_template(
        "index.html",
        posts=posts,
        subreddit=subreddit,
        sort=sort,
        limit=limit
    )

@app.route("/detail_all", methods=["GET"])
def detail_all():
    """Exibe todos os posts em detalhe a partir da sessão."""
    posts = session.get("posts")
    params = session.get("search_params", {})
    if not posts:
        flash("Nenhum post disponível. Faça uma busca primeiro.", "warning")
        return redirect(url_for("home"))

    return render_template(
        "detail_all.html",
        posts=posts,
        **params
    )

@app.route("/details/<post_id>", methods=["GET"])
def details(post_id):
    """Exibe detalhes de um único post, filtrando pela ID a partir da sessão."""
    posts = session.get("posts")
    params = session.get("search_params", {})

    if not posts:
        flash("Nenhum post disponível. Faça uma busca primeiro.", "warning")
        return redirect(url_for("home"))

    # Filtra o post pela sua chave 'id'
    post = next((p for p in posts if str(p.get("id")) == str(post_id)), None)
    if not post:
        flash(f"Post com ID {post_id} não encontrado.", "warning")
        return redirect(url_for("detail_all"))

    return render_template(
        "details.html",
        post=post,
        **params
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
