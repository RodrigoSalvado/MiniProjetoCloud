from flask import Flask, render_template, request, flash, redirect, url_for
import os, requests

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY")
FUNCTION_URL = os.getenv("FUNCTION_URL")

@app.route("/", methods=["GET"])
def home():
    # apenas renderiza o formulário; posts são passados pela rota search
    return render_template("index.html", posts=None)

@app.route("/search", methods=["GET"])
def search():
    subreddit = request.args.get("subreddit", "").strip()
    limit_str = request.args.get("limit", "10")
    try:
        limit = int(limit_str)
    except ValueError:
        flash("O campo 'Número de posts' deve ser um número inteiro.", "warning")
        return redirect(url_for("home"))

    # Chama a Azure Function server-side
    try:
        resp = requests.get(
            FUNCTION_URL,
            params={"subreddit": subreddit, "limit": limit},
            timeout=30
        )
        resp.raise_for_status()
        data = resp.json()
        posts = data.get("posts", data)
    except Exception as e:
        flash(f"Erro ao buscar dados: {e}", "danger")
        return redirect(url_for("home"))

    # Renderiza index.html com posts preenchidos
    return render_template("index.html", posts=posts, subreddit=subreddit, limit=limit)
