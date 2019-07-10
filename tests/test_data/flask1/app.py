from flask import Flask
from flask import render_template


app = Flask(__name__)


@app.route("/")
def home():
    content = 'Flask-Jinja-Test'
    print('break here') # @bphome
    return render_template(
        "hello.html",
        title='Hello',
        content=content
    )


@app.route("/handled")
def bad_route_handled():
    try:
        raise ArithmeticError('Hello')  # @exc_handled
    except Exception:
        pass
    return render_template(
        "hello.html",
        title='Hello',
        content='Flask-Jinja-Test'
    )


@app.route("/unhandled")
def bad_route_unhandled():
    raise ArithmeticError('Hello')  # @exc_unhandled
    return render_template(
        "hello.html",
        title='Hello',
        content='Flask-Jinja-Test'
    )


@app.route("/badtemplate")
def bad_template():
    return render_template(
        "bad.html",
        title='Hello',
        content='Flask-Jinja-Test'
    )


@app.route("/exit")
def exit_app():
    from flask import request
    func = request.environ.get('werkzeug.server.shutdown')
    if func is None:
        raise RuntimeError('No shutdown')
    func()
    return 'Done'
