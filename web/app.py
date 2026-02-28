import os
import json
import http.client
import urllib.parse
from flask import Flask, render_template, request, jsonify
from bs4 import BeautifulSoup

app = Flask(__name__)

API_HOST = "api.indiankanoon.org"
API_TOKEN = os.environ.get("IK_API_TOKEN", "")

UNSAFE_TAGS = {"script", "style", "iframe", "object", "embed", "form", "input", "textarea", "button", "link", "meta"}


def sanitize_html(html_str):
    if not html_str:
        return html_str
    soup = BeautifulSoup(html_str, "html.parser")
    for tag in soup.find_all(UNSAFE_TAGS):
        tag.decompose()
    for tag in soup.find_all(True):
        for attr in list(tag.attrs):
            if attr.startswith("on") or attr in ("srcdoc", "action"):
                del tag[attr]
            elif attr in ("href", "src") and tag.get(attr, "").strip().lower().startswith("javascript:"):
                del tag[attr]
    return str(soup)


def call_ik_api(url):
    headers = {
        "Authorization": f"Token {API_TOKEN}",
        "Accept": "application/json",
    }
    connection = http.client.HTTPSConnection(API_HOST)
    connection.request("POST", url, headers=headers)
    response = connection.getresponse()
    data = response.read()
    if isinstance(data, bytes):
        data = data.decode("utf8")
    return data


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/search")
def api_search():
    q = request.args.get("q", "").strip()
    page = request.args.get("page", "0")
    doctype = request.args.get("doctype", "").strip()
    fromdate = request.args.get("fromdate", "").strip()
    todate = request.args.get("todate", "").strip()
    sortby = request.args.get("sortby", "").strip()

    if not q:
        return jsonify({"error": "Query is required"}), 400

    form_input = q
    if doctype:
        form_input += f" doctypes: {doctype}"
    if fromdate:
        form_input += f" fromdate: {fromdate}"
    if todate:
        form_input += f" todate: {todate}"
    if sortby:
        form_input += f" sortby: {sortby}"

    encoded = urllib.parse.quote_plus(form_input)
    url = f"/search/?formInput={encoded}&pagenum={page}"

    try:
        raw = call_ik_api(url)
        data = json.loads(raw)
        if "docs" in data:
            for doc in data["docs"]:
                if "headline" in doc:
                    doc["headline"] = sanitize_html(doc["headline"])
                if "title" in doc:
                    doc["title"] = sanitize_html(doc["title"])
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/doc/<int:docid>")
def api_doc(docid):
    try:
        raw = call_ik_api(f"/doc/{docid}/")
        data = json.loads(raw)
        if "doc" in data:
            data["doc"] = sanitize_html(data["doc"])
        if "title" in data:
            data["title"] = sanitize_html(data["title"])
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
