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

def get_open_invoices():
    try:
        all_invoices = []
        page = 1
        while True:
            resp = requests.get(f"{DAFTRA_BASE}/invoices", headers={'APIKEY': APIKEY}, params={'payment_status': '0', 'limit': 50, 'page': page})
            data = resp.json()
            invoices = data.get('data', [])
            if not invoices:
                break
            all_invoices.extend(invoices)
            if len(invoices) < 50:
                break
            page += 1
        return all_invoices
    except Exception as e:
        return []

def match_payment(amount, open_invoices):
    matches = []
    for inv in open_invoices:
        inv_data = inv.get('Invoice', {})
        unpaid = float(inv_data.get('summary_unpaid', 0) or 0)
        total = float(inv_data.get('summary_total', 0) or 0)
        inv_amount = unpaid if unpaid > 0 else total
        if inv_amount <= 0:
            continue
        diff = abs(amount - inv_amount) / inv_amount
        if diff <= 0.05:
            matches.append({'invoice_id': inv_data.get('id'), 'invoice_no': inv_data.get('no'), 'client': inv_data.get('client_business_name', ''), 'amount': inv_amount, 'confidence': 'exact' if diff < 0.01 else 'close'})
    if not matches:
        for i in range(len(open_invoices)):
            for j in range(i+1, len(open_invoices)):
                inv1 = open_invoices[i].get('Invoice', {})
                inv2 = open_invoices[j].get('Invoice', {})
                a1 = float(inv1.get('summary_unpaid', 0) or inv1.get('summary_total', 0) or 0)
                a2 = float(inv2.get('summary_unpaid', 0) or inv2.get('summary_total', 0) or 0)
                combined = a1 + a2
                if combined > 0 and abs(amount - combined) / combined <= 0.05:
                    matches.append({'invoice_id': f"{inv1.get('id')},{inv2.get('id')}", 'invoice_no': f"{inv1.get('no')} + {inv2.get('no')}", 'client': inv1.get('client_business_name', ''), 'amount': combined, 'confidence': 'combined'})
    return matches

@app.route('/bank-sync')
def bank_sync():
    r = make_response(send_file('app.html'))
    r.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return r

@app.route('/open-invoices', methods=['GET', 'OPTIONS'])
def open_invoices_endpoint():
    if request.method == 'OPTIONS':
        return cors(make_response('', 200))
    invoices = get_open_invoices()
    return cors(make_response(jsonify({'invoices': invoices, 'count': len(invoices)}), 200))

@app.route('/record-payment', methods=['POST', 'OPTIONS'])
def record_payment():
    """Smart payment recording: fetches invoice to get client_id, then records via invoice_payments"""
    if request.method == 'OPTIONS':
        return cors(make_response('', 200))
    data = request.get_json()
    invoice_id = data.get('invoice_id')
    amount = data.get('amount')
    date = data.get('date')
    notes = data.get('notes', '')

    if not invoice_id or not amount:
        return cors(make_response(jsonify({'error': 'invoice_id and amount required'}), 400))

    headers = {'APIKEY': APIKEY, 'Content-Type': 'application/json'}

    try:
        # Step 1: Get the invoice to find client_id
        inv_resp = requests.get(f"{DAFTRA_BASE}/invoices/{invoice_id}", headers=headers, timeout=30)
        inv_data = inv_resp.json()

        invoice = inv_data.get('data', {})
        if isinstance(invoice, list):
            invoice = invoice[0] if invoice else {}
        inv = invoice.get('Invoice', invoice)

        client_id = inv.get('client_id') or inv.get('ClientId')
        unpaid = float(inv.get('summary_unpaid', 0) or 0)

        # Step 2: Record payment using invoice_payments endpoint
        pay_amount = min(float(amount), unpaid) if unpaid > 0 else float(amount)

        payload = {
            "InvoicePayment": {
                "invoice_id": str(invoice_id),
                "amount": pay_amount,
                "date": date,
                "payment_method": "3",  # bank transfer
                "notes": notes
            }
        }

        # Also try client_payments if we have client_id
        if client_id:
            payload["InvoicePayment"]["client_id"] = str(client_id)

        pay_resp = requests.post(f"{DAFTRA_BASE}/invoice_payments", headers=headers, json=payload, timeout=30)
        pay_data = pay_resp.json()

        if pay_resp.status_code in [200, 201]:
            return cors(make_response(jsonify({'success': True, 'data': pay_data}), 200))
        else:
            # Fallback: try client_payments with client_id
            if client_id:
                cp_payload = {
                    "ClientPayment": {
                        "client_id": str(client_id),
                        "amount": float(amount),
                        "date": date,
                        "payment_method": "3",
                        "notes": notes,
                        "InvoicePayment": [{"invoice_id": str(invoice_id), "amount": pay_amount}]
                    }
                }
                cp_resp = requests.post(f"{DAFTRA_BASE}/client_payments", headers=headers, json=cp_payload, timeout=30)
                if cp_resp.status_code in [200, 201]:
                    return cors(make_response(jsonify({'success': True, 'data': cp_resp.json()}), 200))
                return cors(make_response(jsonify({'error': cp_resp.json(), 'invoice_resp': pay_data}), 400))
            return cors(make_response(jsonify({'error': pay_data}), pay_resp.status_code))

    except Exception as e:
        return cors(make_response(jsonify({'error': str(e)}), 500))

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
    open_invoices = get_open_invoices()
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    prompt = """You are an accountant for Maaly Qurtoba Marble Company in Saudi Arabia. IMPORTANT BANKING RULE: AlRajhi Bank labels transfers between AlRajhi accounts as عملية تحويل داخلية which does NOT mean internal company transfer. If money is coming IN, it is likely a client_payment. If money is going OUT, classify based on who receives it. Known employees always classify as salary: SALAMUDDIN is Installation Manager Riyadh, SIKANDAR is Installation Manager Dammam, TAUFEEK or TAUFEEQ is Driver, YAZEEN or يزن is Branch Manager Qassim, MALIK or مالك is Freelance Installer Qassim. Known transportation always classify as transportation: IBRAHIM or ابراهيم is Truck or Freight, عبدالحسيب is Internal delivery driver Riyadh and Eastern Province. Known local suppliers always classify as local_supplier: شركة مصنع واهوي للرخام, شركة قمم الشام للتجارة, شركة السنا للرخام والسراميك, مؤسسة جنى مارين للتجارة. Known clients always classify as client_payment when money comes IN: مؤسسة ريميندر, مؤسسة مهجة التجارية, MISHARY ADEL ALZAMIL, SHARAF AMER ALTALHI, هشام المسيند, نور البنعلى, اسامه زيد العنزي, وليد الجحيش, سفيان زامل الزامل. Owner personal draws classify as personal: AMRO or عمرو الحلبي is Owner, اميرة is Owner mother. Other: سليمان المهوس is rent Buraydah Branch, مؤسسة جي مارين للتجارة is rent Riyadh Branch, GBOUEO02 is china_supplier, Traffic violations is government, LOANFLEET is loan, Mudud payroll is salary, نقاط بيع MALI QURTOBA is client_payment, Bank fees is bank_fee. Analyze this bank statement and classify each transaction. Categories: client_payment, china_supplier, local_supplier, salary, rent, personal, government, bank_fee, transportation, loan, other. Return ONLY valid JSON: {"bank":"","period":"","opening":0,"closing":0,"transactions":[{"date":"YYYY-MM-DD","description":"","amount":0,"direction":"in or out","category":"","party":"","daftra_action":"record_payment or record_expense or skip","notes":""}]}"""
    try:
        msg = client.messages.create(model="claude-haiku-4-5-20251001", max_tokens=8000, messages=[{"role": "user", "content": prompt + "\n\n" + bank_text[:8000]}])
        raw = msg.content[0].text
        m = re.search(r'\{[\s\S]*\}', raw)
        result = json.loads(m.group() if m else raw)
        transactions = result.get('transactions', [])
        for tx in transactions:
            if tx.get('direction') == 'in' and tx.get('category') == 'client_payment':
                matches = match_payment(float(tx.get('amount', 0)), open_invoices)
                tx['invoice_matches'] = matches
                tx['daftra_action'] = 'match_invoice' if matches else 'waiting_list'
        result['transactions'] = transactions
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
