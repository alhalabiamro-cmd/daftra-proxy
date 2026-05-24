from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

DAFTRA_BASE = 'https://maealequrtoba.daftra.com/api2'
APIKEY = '670d593bdb3158eb24684c4342b3e474b9403dc9'

@app.after_request
def add_cors(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    return response

@app.route('/<path:endpoint>', methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'])
def proxy(endpoint):
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    
    url = f"{DAFTRA_BASE}/{endpoint}"
    headers = {'APIKEY': APIKEY, 'Content-Type': 'application/json'}
    
    if request.method == 'GET':
        resp = requests.get(url, headers=headers, params=request.args)
    elif request.method == 'POST':
        resp = requests.post(url, headers=headers, json=request.get_json())
    elif request.method == 'PUT':
        resp = requests.put(url, headers=headers, json=request.get_json())
    elif request.method == 'DELETE':
        resp = requests.delete(url, headers=headers)
    
    return jsonify(resp.json()), resp.status_code

@app.route('/')
def health():
    return jsonify({'status': 'ok', 'message': 'Daftra Proxy is running'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
