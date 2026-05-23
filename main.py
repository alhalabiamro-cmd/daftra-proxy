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
            resp = requests.get(
                f"{DAFTRA_BASE}/invoices",
                headers={'APIKEY': APIKEY},
                params={'payment_status': '0', 'limit': 50, 'page': page}
            )
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

def match_payment_to_invoices(amount, open_invoices, tolerance=0.05):
    matches = []
    for inv in open_invoices:
        try:
            inv_data = inv.get('Invoice', {})
            unpaid = float(inv_data.get('summary_unpaid', 0))
            total = float(inv_data.get('summary_total', 0))
            inv_amount = unpaid if unpaid > 0 else total
            if inv_amount <= 0:
                continue
            diff = abs(amount - inv_amount) / inv_amount
            if diff <= tolerance:
                matches.append({
                    'invoice_id': inv_data.get('id'),
                    'invoice_no': inv_data.get('no'),
                    'client': inv_data.get('client_business_name') or inv_data.get('Client', {}).get('first_name', ''),
                    'amount': inv_amount,
                    'confidence': 'exact' if diff < 0.01 else 'close'
                })
        except:
            continue
    
    # Try combining invoices for partial payments
    if not matches and len(open_invoices) > 1:
        for i in range(len(open_invoices)):
            for j in range(i+1, len(open_invoices)):
                try:
                    inv1 = open_invoices[i].get('Invoice', {})
                    inv2 = open_invoices[j].get('Invoice', {})
                    unpaid1 = float(inv1.get('summary_unpaid', 0)) or float(inv1.get('summary_total', 0))
                    unpaid2 = float(inv2.get('summary_unpaid', 0)) or float(inv2.get('summary_total', 0))
                    combined = unpaid1 + unpaid2
                    if combined > 0:
                        diff = abs(amount - combined) / combined
                        if diff <= tolerance:
                            matches.append({
                                'invoice_id': f"{inv1.get('id')},{inv2.get('id')}",
                                'invoice_no': f"{inv1.get('no')} + {inv2.get('no')}",
                                'client': inv1.get('client_business_name', ''),
                                'amount': combined,
                                'confidence': 'combined'
                            })
                except:
                    continue
    return matches

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
    
    # Get open invoices from Daftra
    open_invoices = get_open_invoices()
    
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    prompt = """You are an accountant for Maaly Qurtoba Marble Company in Saudi Arabia.

IMPORTANT BANKING RULE: AlRajhi Bank labels transfers between AlRajhi accounts as "عملية تحويل داخلية" (internal transfer). This does NOT mean it is an internal company transfer. If money is coming IN, it is likely a client_payment. If money is going OUT, classify based on who receives it.

Known employees - always classify as salary:
- SALAMUDDIN = Installation Manager Riyadh
- SIKANDAR = Installation Manager Dammam
- TAUFEEK or TAUFEEQ = Driver
- YAZEEN or يزن = Branch Manager Qassim
- MALIK or مالك = Freelance Installer Qassim

Known transportation - always classify as transportation:
- IBRAHIM or ابراهيم = Truck/Freight
- عبدالحسيب = Internal delivery driver Riyadh and Eastern Province

Known local suppliers - always classify as local_supplier:
- شركة السنا للرخام والسراميك = Al-Sana marble supplier
- شركة مصنع واهوي للرخام = Wahhawe marble factory
- شركة قمم الشام للتجارة = local marble supplier
- شركة بيتي الانيق للتجارة = marble supplier
- شركة نرجس للتجارة = marble supplier
- القصر الانيق = marble supplier
- مؤسسة جنى مارين للتجارة = marble supplier

Known clients - always classify as client_payment when money comes IN:
- مؤسسة ريميندر = client
- مؤسسة مهجة التجارية = client
- MISHARY ADEL ALZAMIL = client
- SHARAF AMER ALTALHI = client
- هشام المسيند = client
- نور البنعلى = client
- اسامه زيد العنزي = client
- وليد الجحيش = client
- سفيان زامل الزامل = client

Owner personal draws - classify as personal:
- AMRO or عمرو الحلبي = Owner
- اميرة = Owner's mother

Other known classifications:
- سليمان المهوس = rent (Buraydah Branch)
- مؤسسة جي مارين للتجارة = rent (Riyadh Branch)
- China Supplier or GBOUEO02 = china_supplier
- وزارة العدل = legal
- Traffic violations = government
- Sadad payments = government
- Al Rajhi loan installments LOANFLEET = loan
- Mudud payroll = salary
- نقاط بيع MALI QURTOBA = POS income (client_payment)
- Bank fees and commissions = bank_fee

Analyze this bank statement and classify each transaction. Categories: client_payment, china_supplier, local_supplier, salary, rent, personal, government, bank_fee, transportation, loan, legal, other. Return ONLY valid JSON: {"bank":"","period":"","opening":0,"closing":0,"transactions":[{"date":"YYYY-MM-DD","description":"","amount":0,"direction":"in or out","category":"","party":"","daftra_action":"record_payment or record_expense or skip","notes":""}]}"""
    
    try:
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=8000,
            messages=[{"role": "user", "content": prompt + "\n\n" + bank_text[:8000]}]
        )
        raw = msg.content[0].text
        m = re.search(r'\{[\s\S]*\}', raw)
        result = json.loads(m.group() if m else raw)
        
        # Match incoming payments to open invoices
        transactions = result.get('transactions', [])
        for tx in transactions:
            if tx.get('direction') == 'in' and tx.get('category') == 'client_payment':
                amount = float(tx.get('amount', 0))
                matches = match_payment_to_invoices(amount, open_invoices)
                if matches:
                    tx['invoice_matches'] = matches
                    tx['daftra_action'] = 'match_invoice'
                else:
                    tx['invoice_matches'] = []
                    tx['daftra_action'] = 'waiting_list'
        
        result['transactions'] = transactions
        return cors(make_response(jsonify(result), 200))
    except Exception as e:
        return cors(make_response(jsonify({'error': str(e)}), 500))

@app.route('/open-invoices', methods=['GET', 'OPTIONS'])
def open_invoices_endpoint():
    if request.method == 'OPTIONS':
        return cors(make_response('', 200))
    invoices = get_open_invoices()
    return cors(make_response(jsonify({'invoices': invoices, 'count': len(invoices)}), 200))

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
