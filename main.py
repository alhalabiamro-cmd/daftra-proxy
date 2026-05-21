from flask import Flask, request, jsonify, make_response, send_file
import requests, os, anthropic, json, re

app = Flask(__name__)

DAFTRA_BASE = 'https://maealequrtoba.daftra.com/api2'
APIKEY = os.environ.get('APIKEY', 'c4c035341dbe1da1531b227d89f6e2f481252766')
ANTHROPIC_KEY = os.environ.get('ANTHROPIC_API_KEY', '')

def cors(r):
    r.headers['Access-Control-Allow-Origin'] = '*'
    r.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    r.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, APIKEY'
    return r

@app.route('/bank-sync')
def bank_sync():
    r = make_response(send_file('app.html'))
    r.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return r

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
prompt = "You are an accountant for Maaly Qurtoba Marble Company in Saudi Arabia. Known employees (always classify as salary): SALAMUDDIN (Installation Manager Riyadh), SIKANDAR (Installation Manager Dammam), TAUFEEK/TAUFEEQ (Driver), YAZEEN/يزن (Branch Manager Qassim), MALIK/مالك (Freelance Installer Qassim), IBRAHIM/ابراهيم (Transportation). Owner personal draws: AMRO/عمرو الحلبي. Analyze this bank statement and classify each transaction. Categories: client_payment, china_supplier, local_supplier, salary, rent, personal, government, bank_fee, internal, other. Return ONLY valid JSON: {\"bank\":\"\",\"period\":\"\",\"opening\":0,\"closing\":0,\"transactions\":[{\"date\":\"YYYY-MM-DD\",\"description\":\"\",\"amount\":0,\"direction\":\"in or out\",\"category\":\"\",\"party\":\"\",\"daftra_action\":\"record_payment or record_expense or skip\",\"notes\":\"\"}]}"
    try:
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=8000,
            messages=[{"role": "user", "content": prompt + "\n\n" + bank_text[:8000]}]
        )
        raw = msg.content[0].text
        m = re.search(r'\{[\s\S]*\}', raw)
        result = json.loads(m.group() if m else raw)
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
