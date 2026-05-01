from app import app as flask_app


def create_app():
    return flask_app


app = flask_app
application = flask_app
