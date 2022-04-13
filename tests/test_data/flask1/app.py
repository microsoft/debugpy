import os
from flask import Flask
from flask import render_template


app = Flask(__name__)
exiting = False


@app.route("/")
def home():
    content = "Flask-Jinja-Test"
    print("break here")  # @bphome
    return render_template("hello.html", title="Hello", content=content)


@app.route("/handled")
def bad_route_handled():
    try:
        raise ArithmeticError("Hello")  # @exc_handled
    except Exception:
        pass
    return render_template("hello.html", title="Hello", content="Flask-Jinja-Test")


@app.route("/unhandled")
def bad_route_unhandled():
    raise ArithmeticError("Hello")  # @exc_unhandled
    return render_template("hello.html", title="Hello", content="Flask-Jinja-Test")


@app.route("/badtemplate")
def bad_template():
    return render_template("bad.html", title="Hello", content="Flask-Jinja-Test")


@app.route("/exit")
def exit_app():
    global exiting
    exiting = True
    return "Done"


@app.teardown_request
def teardown(exception):
    if exiting:
        os._exit(0)
