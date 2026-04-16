import logging
from flask import Flask, request, jsonify

from api.config import validate, API_KEY

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def create_app() -> Flask:
    validate()  # fail fast on missing env vars

    app = Flask(__name__)

    @app.before_request
    def _require_api_key():
        # Allow unauthenticated health checks
        if request.path == "/health":
            return
        key = request.headers.get("X-API-Key")
        if key != API_KEY:
            return jsonify({"error": "Unauthorized — provide a valid X-API-Key header"}), 401

    @app.get("/health")
    def health():
        return jsonify({"status": "ok"})

    from api.routes.upload import upload_bp
    from api.routes.stream import stream_bp

    app.register_blueprint(upload_bp)
    app.register_blueprint(stream_bp)

    return app


if __name__ == "__main__":
    create_app().run(debug=True)
