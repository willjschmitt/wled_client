from flask import Flask
from flask import request
app = Flask(__name__)


@app.route('/holiday-lights', methods=['POST'])
def hello_world():
    print(request.get_json())
    return 'Hello, World!'


if __name__ == '__main__':
    app.run(host='0.0.0.0', port='4321')
