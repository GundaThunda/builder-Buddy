from flask import Flask, jsonify
from website_toolbox import toolbox_routes
from website_builder_buddy import blueprint_routes
from website_silhouette import silhouette_routes
from website_social_structure import social_routes
from website_tips import tips_routes
from website_ron_g import ron_g_routes

app = Flask(__name__)

app.register_blueprint(toolbox_routes, url_prefix="/toolbox")
app.register_blueprint(blueprint_routes, url_prefix="/blueprint")
app.register_blueprint(silhouette_routes, url_prefix="/silhouette")
app.register_blueprint(social_routes, url_prefix="/social")
app.register_blueprint(tips_routes, url_prefix="/tips")
app.register_blueprint(ron_g_routes, url_prefix="/ron-g")


@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "builder-buddy"})


@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "not_found"}), 404


@app.errorhandler(405)
def method_not_allowed(e):
    return jsonify({"error": "method_not_allowed"}), 405


@app.errorhandler(500)
def server_error(e):
    return jsonify({"error": "internal_server_error"}), 500


if __name__ == "__main__":
    app.run(debug=True, port=5000)
