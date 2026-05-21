from flask import Flask, request, jsonify, make_response, send_file
import requests
import os
import anthropic

app = Flask(__name__)

DAFTRA_BASE = 'https://maealequrtoba.daftra.com/api2'
APIKEY = os.environ.get('APIKEY', 'c4c035341dbe1da1531b227d89f6e2f481252766')
ANTHROPIC_KEY = os.environ.get('ANTHROPIC_API_KEY', '')

def cors(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, APIKEY'
    return response

@app.route('/bank-sync')
def bank_sync():
    response = make_response(send_file('app.html'))
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response

@app.route('/analyze-bank', methods=['POST', 'OPTIONS'])
def analyze_bank():
    if request.method == 'OPTIONS':
        return cors(make_response('', 200))
    data = request.get_json()
    bank_text = data.get('text', '')
    if not bank_text:
        return cors(make_response(jsonify({'error': 'No text provided'}), 400))
    if not ANTHROPIC_KEY:
        return cors(make_response(jsonify({'error': 'No API key configured'}), 500))
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    system_prompt = """You are an expert accountant for Maaly Qurtoba Marble Company in Saudi Arabia.
Analyze bank statements and classify each transaction.
Categories: client_payment, china_supplier, local_supplier, salary, rent, personal, government, bank_fee, internal, other
Return ONLY valid JSON:
{"bank":"","period":"","opening":0,"closing":0,"transactions":[{"date":"YYYY-MM-DD","description":"","amount":0,"direction":"in or out","category":"","party":"","daftra_action":"record_payment or record_expense or skip","notes":""}]}"""
    text_chunk = bank_text[:8000]
    try:
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=8000,
            system=system_prompt,
            messages=[{"role": "user", "content": f"Analyze this bank statement:\n\n{text_chunk}"}]
        )
        raw = message.content[0].text
        import json, re
        json_match = re.search(r'\{[\s\S]*\}', raw)
        result = json.loads(json_match.group() if json_match else raw)
        return cors(make_response(jsonify(result), 200))
    except Exception as e:
        return cors(make_response(jsonify({'error': str(e)}), 500))

@app.route('/<path:endpoint>', methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'])
def proxy(endpoint):
    if request.method == 'OPTIONS':
        return cors(make_response('', 200))
    url = f"{DAFTRA_BASE}/{endpoint}"
    headers = {'APIKEY': APIKEY, 'Content-Type': 'application/json'}
    try:
        if request.method == 'GET':
            resp = requests.get(url, headers=headers, params=request.args, timeout=30)
        elif request.method == 'POST':
            resp = requests.post(url, headers=headers, json=request.get_json(), timeout=30)
        elif request.method == 'PUT':
            resp = requests.put(url, headers=headers, json=request.get_json(), timeout=30)
        elif request.method == 'DELETE':
            resp = requests.delete(url, headers=headers, timeout=30)
        return cors(make_response(jsonify(resp.json()), resp.status_code))
    except Exception as e:
        return cors(make_response(jsonify({'error': str(e)}), 500))

@app.route('/')
def health():
    return cors(make_response(jsonify({'status': 'ok'}), 200))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
