from app import app
from config import PORT


if __name__ == "__main__":
    app.run(debug=app.config.get("DEBUG", False), port=PORT)
