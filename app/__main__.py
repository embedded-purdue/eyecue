"""Entry point used by PyInstaller's onefile binary."""
from app.app import create_app
from app.config import FLASK_HOST, FLASK_PORT

if __name__ == "__main__":
    create_app().run(
        debug=False,
        host=FLASK_HOST,
        port=FLASK_PORT,
        use_reloader=False,
        threaded=True,
    )
