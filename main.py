from flask import Flask, request, jsonify, make_response, send_file
import requests, os, anthropic, json, re

app = Flask(__name__)

DAFTRA_BASE = 'https://maealequrtoba.daftra.com/api2'
APIKEY = os.environ.get('APIKEY', 'c4c035341dbe1da1531b227d89f6e2f481252766')
ANTHROPIC_KEY = os.environ.get('ANTHROPIC_API_KEY', '')

# Client name aliases: bank statement name -> daftra name keywords
CLIENT_ALIASES = {
    'مهجة': 'ريميندر',
    'reminder': 'ريميندر',
    'الخدمات التجارية المتكاملة': 'الخدمات التجارية المتكاملة',
    'خدمات متكاملة': 'الخدمات التجارية المتكاملة',
}

# Known bank account numbers -> classification
ACCOUNT_TO_CLIENT = {
    # Clients (incoming payments)
    '129000010006086890598': 'ريميندر',   # مؤسسة مهجة التجارية
    '12900608016890598': 'ريميندر',        # same client (shorter format seen in PDF)
    
    # Employees - salary
    '640000010006087461738': 'SALAMUDDIN', # salary
    '077050010006087399166': 'SIKANDAR',   # salary
    '077050010006087400188': 'TAUFEEK',    # salary
    '697000010006086135855': 'يزن',        # salary
    '192000010006080456273': 'مالك',       # salary
    
    # Transportation
    '331000010006086567547': 'عبدالحسيب',  # transportation - internal delivery
    
    # Known suppliers
    '377000010006080000888': 'شركة السنا للرخام والسيراميك',  # local_supplier
    '538000010006080000223': 'شركة الفرات للرخام',            # local_supplier
    '602000010006080654780': 'شركة اسوار الخليج',             # local_supplier
    '487000010006085245725': 'شركة هواهوي ستون',              # local_supplier (واهوي)
    
    # Rent
    '599000010006080888888': 'سليمان المهوس',   # rent Buraydah
    
    # Government/PRO services
    '282000010006086606237': 'مؤسسة قوس قزح',  # government PRO services
    
    # Personal (owner)
    '077050010006084823853': 'عمرو الحلبي',     # personal - owner
    '539000010006085772890': 'اميرة',           # personal - owner mother
}

# Account number -> category mapping for automatic classification
ACCOUNT_CATEGORY = {
    '129000010006086890598': 'client_payment',
    '12900608016890598': 'client_payment',
    '640000010006087461738': 'salary',
    '077050010006087399166': 'salary',
    '077050010006087400188': 'salary',
    '697000010006086135855': 'salary',
    '192000010006080456273': 'salary',
    '331000010006086567547': 'transportation',
    '377000010006080000888': 'local_supplier',
    '538000010006080000223': 'local_supplier',
    '602000010006080654780': 'local_supplier',
    '487000010006085245725': 'local_supplier',
    '599000010006080888888': 'rent',
    '282000010006086606237': 'government',
    '077050010006084823853': 'personal',
    '539000010006085772890': 'personal',
}

# Daftra expense category IDs for salaries/transportation
EXPENSE_CATEGORIES = {
    'salary': '22',        # رواتب - update this ID if different in your Daftra
    'transportation': '23', # نقل
    'rent': '24',           # إيجار
    'other': '1',           # مصروفات أخرى
}

def cors(r):
    r.headers['Access-Control-Allow-Origin'] = '*'
    r.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    r.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, APIKEY'
    return r

def get_open_invoices():
    try:
        all_invoices = []
        for status in ['0', '2']:
            page = 1
            while True:
                resp = requests.get(f"{DAFTRA_BASE}/invoices", headers={'APIKEY': APIKEY}, params={'payment_status': status, 'limit': 50, 'page': page})
                data = resp.json()
                invoices = data.get('data', [])
                if not invoices:
                    break
                all_invoices.extend(invoices)
                if len(invoices) < 50:
                    break
                page += 1
        seen = set()
        unique = []
        for inv in all_invoices:
            inv_id = inv.get('Invoice', {}).get('id')
            if inv_id and inv_id not in seen:
                seen.add(inv_id)
                unique.append(inv)
        return unique
    except Exception as e:
        return []

def normalize_name(name):
    name = (name or '').lower().strip()
    for alias, canonical in CLIENT_ALIASES.items():
        if alias in name:
            return canonical.lower()
    return name

def extract_account_from_text(text):
    """Extract account number from bank transaction text"""
    text = text or ''
    # Try FRACCT/TOACCT format (PDF)
    m = re.search(r'(?:FRACCT|TOACCT|FROMACCT)[/\\](\d{10,})', text)
    if m:
        return m.group(1)
    # Try CA: format (Excel)
    m = re.search(r'CA:\s*(\d{10,})', text)
    if m:
        return m.group(1)
    return None

def client_name_matches(party, inv_client):
    if not party or not inv_client:
        return False
    # Check account number first
    acc = extract_account_from_text(party)
    if acc and acc in ACCOUNT_TO_CLIENT:
        canonical = ACCOUNT_TO_CLIENT[acc].lower()
        return canonical in normalize_name(inv_client)
    p = normalize_name(party)
    c = normalize_name(inv_client)
    p_words = [w for w in p.split() if len(w) >= 4]
    c_words = [w for w in c.split() if len(w) >= 4]
    for pw in p_words:
        if pw in c:
            return True
    for cw in c_words:
        if cw in p:
            return True
    return False

def match_payment(amount, open_invoices, party='', description=''):
    combined_text = f"{party} {description}"
    # Check if account number maps to a known client
    acc = extract_account_from_text(combined_text)
    if acc and acc in ACCOUNT_TO_CLIENT:
        party = ACCOUNT_TO_CLIENT[acc]

    client_invoices = [inv for inv in open_invoices if client_name_matches(combined_text, inv.get('Invoice', {}).get('client_business_name', ''))]
    search_pools = [client_invoices, open_invoices] if client_invoices else [open_invoices]

    for pool in search_pools:
        matches = []
        for inv in pool:
            inv_data = inv.get('Invoice', {})
            unpaid = float(inv_data.get('summary_unpaid', 0) or 0)
            total = float(inv_data.get('summary_total', 0) or 0)
            inv_amount = unpaid if unpaid > 0 else total
            if inv_amount <= 0:
                continue
            diff = abs(amount - inv_amount) / inv_amount
            if diff <= 0.05:
                matches.append({
                    'invoice_id': inv_data.get('id'),
                    'invoice_no': inv_data.get('no'),
                    'client': inv_data.get('client_business_name', ''),
                    'amount': inv_amount,
                    'confidence': 'exact' if diff < 0.01 else 'close'
                })
        if matches:
            return matches

        for i in range(len(pool)):
            for j in range(i+1, len(pool)):
                inv1 = pool[i].get('Invoice', {})
                inv2 = pool[j].get('Invoice', {})
                a1 = float(inv1.get('summary_unpaid', 0) or inv1.get('summary_total', 0) or 0)
                a2 = float(inv2.get('summary_unpaid', 0) or inv2.get('summary_total', 0) or 0)
                combined = a1 + a2
                if combined > 0 and abs(amount - combined) / combined <= 0.05:
                    return [{
                        'invoice_id': f"{inv1.get('id')},{inv2.get('id')}",
                        'invoice_no': f"{inv1.get('no')} + {inv2.get('no')}",
                        'client': inv1.get('client_business_name', ''),
                        'amount': combined,
                        'confidence': 'combined'
                    }]
    return []

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
        inv_resp = requests.get(f"{DAFTRA_BASE}/invoices/{invoice_id}", headers=headers, timeout=30)
        inv_data = inv_resp.json()
        invoice = inv_data.get('data', {})
        if isinstance(invoice, list):
            invoice = invoice[0] if invoice else {}
        inv = invoice.get('Invoice', invoice)
        client_id = inv.get('client_id') or inv.get('ClientId')
        unpaid = float(inv.get('summary_unpaid', 0) or 0)
        pay_amount = min(float(amount), unpaid) if unpaid > 0 else float(amount)

        payload = {
            "InvoicePayment": {
                "invoice_id": str(invoice_id),
                "amount": pay_amount,
                "date": date,
                "payment_method": "3",
                "notes": notes
            }
        }
        if client_id:
            payload["InvoicePayment"]["client_id"] = str(client_id)

        pay_resp = requests.post(f"{DAFTRA_BASE}/invoice_payments", headers=headers, json=payload, timeout=30)
        pay_data = pay_resp.json()

        if pay_resp.status_code in [200, 201] or pay_data.get("result") == "successful" or (isinstance(pay_data.get("error"), dict) and pay_data["error"].get("result") == "successful"):
            return cors(make_response(jsonify({'success': True, 'data': pay_data}), 200))
        else:
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
                if cp_resp.status_code in [200, 201] or cp_resp.json().get("result") == "successful":
                    return cors(make_response(jsonify({'success': True, 'data': cp_resp.json()}), 200))
                return cors(make_response(jsonify({'error': cp_resp.json(), 'invoice_resp': pay_data}), 400))
            return cors(make_response(jsonify({'error': pay_data}), pay_resp.status_code))

    except Exception as e:
        return cors(make_response(jsonify({'error': str(e)}), 500))

@app.route('/record-expense', methods=['POST', 'OPTIONS'])
def record_expense():
    """Record expense with correct category based on transaction type"""
    if request.method == 'OPTIONS':
        return cors(make_response('', 200))
    data = request.get_json()
    amount = data.get('amount')
    date = data.get('date')
    description = data.get('description', '')
    category = data.get('category', 'other')  # salary, transportation, rent, other
    notes = data.get('notes', '')

    headers = {'APIKEY': APIKEY, 'Content-Type': 'application/json'}

    # First get expense categories from Daftra to find correct ID
    try:
        cat_resp = requests.get(f"{DAFTRA_BASE}/expense_categories", headers=headers, timeout=30)
        cat_data = cat_resp.json()
        categories = cat_data.get('data', [])

        # Find matching category
        category_id = None
        category_keywords = {
            'salary': ['راتب', 'رواتب', 'salary', 'salaries', 'payroll'],
            'transportation': ['نقل', 'مواصلات', 'transport'],
            'rent': ['إيجار', 'ايجار', 'rent'],
        }

        if category in category_keywords:
            keywords = category_keywords[category]
            for cat in categories:
                cat_item = cat.get('ExpenseCategory', cat)
                cat_name = (cat_item.get('name', '') or '').lower()
                if any(kw.lower() in cat_name for kw in keywords):
                    category_id = cat_item.get('id')
                    break

        payload = {
            "Expense": {
                "amount": float(amount),
                "date": date,
                "description": description,
                "notes": notes
            }
        }
        if category_id:
            payload["Expense"]["expense_category_id"] = str(category_id)

        resp = requests.post(f"{DAFTRA_BASE}/expenses", headers=headers, json=payload, timeout=30)
        resp_data = resp.json()

        if resp.status_code in [200, 201, 202] or resp_data.get("result") == "successful":
            return cors(make_response(jsonify({'success': True, 'data': resp_data}), 200))
        return cors(make_response(jsonify({'error': resp_data}), resp.status_code))

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
    prompt = """You are an accountant for Maaly Qurtoba Marble Company in Saudi Arabia. IMPORTANT BANKING RULE: AlRajhi Bank labels transfers between AlRajhi accounts as عملية تحويل داخلية which does NOT mean internal company transfer. If money is coming IN, it is likely a client_payment. If money is going OUT, classify based on who receives it. Known employees always classify as salary: SALAMUDDIN is Installation Manager Riyadh, SIKANDAR is Installation Manager Dammam, TAUFEEK or TAUFEEQ is Driver, YAZEEN or يزن is Branch Manager Qassim, MALIK or مالك is Freelance Installer Qassim. Known transportation always classify as transportation: IBRAHIM or ابراهيم is Truck or Freight, عبدالحسيب is Internal delivery driver Riyadh and Eastern Province. Known local suppliers always classify as local_supplier: شركة مصنع واهوي للرخام, واهوي, مصنع واهوي, أسوار الخليج, اسوار الخليج, شركة قمم الشام للتجارة, شركة السنا للرخام والسراميك, مؤسسة جنى مارين للتجارة. Known clients always classify as client_payment when money comes IN: مؤسسة ريميندر, مؤسسة مهجة التجارية, MISHARY ADEL ALZAMIL, SHARAF AMER ALTALHI, هشام المسيند, نور البنعلى, اسامه زيد العنزي, وليد الجحيش, سفيان زامل الزامل, مؤسسة الخدمات التجارية المتكاملة. Account number 12900608016890598 is always مؤسسة ريميندر — classify as client_payment. Owner personal draws classify as personal: AMRO or عمرو الحلبي is Owner, اميرة is Owner mother. Other: سليمان المهوس is rent Buraydah Branch, مؤسسة جي مارين للتجارة is rent Riyadh Branch, GBOUEO02 is china_supplier, Traffic violations is government, LOANFLEET is loan, Mudud payroll is salary, نقاط بيع MALI QURTOBA is client_payment, Bank fees is bank_fee. خصم مستحقات البطاقات الائتمانية or بطاقة ائتمانية is bank_fee. قوس قزح is government (PRO services company). Analyze this bank statement and classify each transaction. Categories: client_payment, china_supplier, local_supplier, salary, rent, personal, government, bank_fee, transportation, loan, other. Return ONLY valid JSON: {"bank":"","period":"","opening":0,"closing":0,"transactions":[{"date":"YYYY-MM-DD","description":"","amount":0,"direction":"in or out","category":"","party":"","daftra_action":"record_payment or record_expense or skip","notes":""}]}"""
    try:
        msg = client.messages.create(model="claude-haiku-4-5-20251001", max_tokens=8000, messages=[{"role": "user", "content": prompt + "\n\n" + bank_text[:8000]}])
        raw = msg.content[0].text
        m = re.search(r'\{[\s\S]*\}', raw)
        result = json.loads(m.group() if m else raw)
        transactions = result.get('transactions', [])
        for tx in transactions:
            if tx.get('direction') == 'in' and tx.get('category') == 'client_payment':
                party = tx.get('party', '') or ''
                description = tx.get('description', '') or ''
                matches = match_payment(float(tx.get('amount', 0)), open_invoices, party, description)
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
