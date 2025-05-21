import os
import requests
from flask import Flask, render_template, request, flash, redirect, url_for, session

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev_secret_key")
FUNCTION_URL = os.getenv("FUNCTION_URL")

def fetch_posts(subreddit, sort, limit):
    """Chama a Azure Function e retorna lista de posts ou None em caso de erro."""
    try:
        resp = requests.get(
            FUNCTION_URL,
            params={"subreddit": subreddit, "sort": sort, "limit": limit},
            timeout=30
        )
        resp.raise_for_status()
        data = resp.json()
        # aceita tanto {"posts": [...]} quanto diretamente [...]
        return data.get("posts", data)
    except Exception as e:
        flash(f"Erro ao obter posts: {e}", "danger")
        return None

@app.route("/", methods=["GET"])
def home():
    # limpa sessão antiga
    session.clear()
    return render_template("index.html", posts=None)

@app.route("/search", methods=["GET"])
def search():
    subreddit = request.args.get("subreddit", "").strip()
    sort = request.args.get("sort", "hot").strip()
    limit_str = request.args.get("limit", "10").strip()

    try:
        limit = int(limit_str)
    except ValueError:
        flash("O campo 'Número de posts' deve ser um número inteiro.", "warning")
        return redirect(url_for("home"))

    posts = fetch_posts(subreddit, sort, limit)
    if posts is None:
        return redirect(url_for("home"))

    # guarda posts e parâmetros na sessão
    session["posts"] = posts
    session["search_params"] = {"subreddit": subreddit, "sort": sort, "limit": limit}

    return render_template(
        "index.html",
        posts=posts,
        subreddit=subreddit,
        sort=sort,
        limit=limit
    )

@app.route("/detail", methods=["GET"])
def detail():
    """Exibe detalhes de um único post, buscando-o pelo 'id' na sessão."""
    post_id = request.args.get("id")
    if not post_id:
        flash("ID de post não fornecido.", "warning")
        return redirect(url_for("home"))

    posts = session.get("posts")
    if not posts:
        flash("Nenhum post disponível. Faça uma busca primeiro.", "warning")
        return redirect(url_for("home"))

    # filtra o post pelo seu 'id'
    post = next((p for p in posts if str(p.get("id")) == str(post_id)), None)
    if not post:
        flash(f"Post com ID {post_id} não encontrado.", "warning")
        return redirect(url_for("search",
                                subreddit=session["search_params"]["subreddit"],
                                sort=session["search_params"]["sort"],
                                limit=session["search_params"]["limit"]))

    return render_template("details.html", post=post)

@app.route("/detail_all", methods=["POST"])
def detail_all():
    """
    Exibe todos os posts em detalhe.
    Reconstrói a lista a partir dos campos ocultos enviados no form de index.html.
    """
    titles = request.form.getlist("titles[]")
    urls   = request.form.getlist("urls[]")
    scores = request.form.getlist("scores[]")
    ids    = request.form.getlist("ids[]")

    posts = []
    for title, url, score, pid in zip(titles, urls, scores, ids):
        posts.append({
            "title": title,
            "url": url,
            "score": score,
            "id": pid
        })

    if not posts:
        flash("Nenhum post recebido para detalhamento completo.", "warning")
        return redirect(url_for("home"))

    return render_template("detail_all.html", posts=posts)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
