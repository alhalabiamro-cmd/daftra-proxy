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
    'حباب': 'مؤسسة الجبر',
    'الحباب': 'مؤسسة الجبر',
    'ماهر حباب': 'مؤسسة الجبر',
    'ماهر عبدالله': 'مؤسسة الجبر',
}

# Known bank account numbers -> classification
ACCOUNT_TO_CLIENT = {
    # Clients (incoming payments)
    '129000010006086890598': 'ريميندر',
    '12900608016890598': 'ريميندر',
    '200000010006080174447': 'علي سعود',

    # Employees - salary
    '640000010006087461738': 'SALAMUDDIN',
    '077050010006087399166': 'SIKANDAR',
    '077050010006087400188': 'TAUFEEK',
    '697000010006086135855': 'يزن',
    '192000010006080456273': 'مالك',
    'MOATAZ': 'معتز',

    # Transportation
    '331000010006086567547': 'عبدالحسيب',
    'AMRO_BADAWI': 'عمرو بدوي',

    # Known suppliers
    '377000010006080000888': 'شركة السنا للرخام والسيراميك',
    '538000010006080000223': 'شركة الفرات للرخام',
    '602000010006080654780': 'شركة اسوار الخليج',
    '487000010006085245725': 'شركة هواهوي ستون',

    # Rent
    '599000010006080888888': 'سليمان المهوس',

    # Government/PRO services
    '282000010006086606237': 'مؤسسة قوس قزح',

    # Personal (owner)
    '077050010006084823853': 'عمرو الحلبي',
    '539000010006085772890': 'اميرة',
}

ACCOUNT_CATEGORY = {
    '129000010006086890598': 'client_payment',
    '12900608016890598': 'client_payment',
    '200000010006080174447': 'client_payment',
    '640000010006087461738': 'salary',
    '077050010006087399166': 'salary',
    '077050010006087400188': 'salary',
    '697000010006086135855': 'salary',
    '192000010006080456273': 'salary',
    'MOATAZ': 'salary',
    '331000010006086567547': 'transportation',
    'AMRO_BADAWI': 'transportation',
    '377000010006080000888': 'local_supplier',
    '538000010006080000223': 'local_supplier',
    '602000010006080654780': 'local_supplier',
    '487000010006085245725': 'local_supplier',
    '599000010006080888888': 'rent',
    '282000010006086606237': 'government',
    '077050010006084823853': 'personal',
    '539000010006085772890': 'personal',
}

# Map our categories to Daftra chart-of-accounts IDs (from the screenshot)
# #56 = مصروف الرواتب والاجور
# #52 = مصروفات إدارية وعمومية
# #54 = مصروفات أخرى
EXPENSE_ACCOUNT_ID = {
    'salary':         '56',   # مصروف الرواتب والاجور
    'rent':           '52',   # مصروفات إدارية وعمومية
    'transportation': '52',   # مصروفات إدارية وعمومية
    'government':     '52',   # مصروفات إدارية وعمومية
    'bank_fee':       '52',   # مصروفات إدارية وعمومية
    'personal':       '54',   # مصروفات أخرى
    'loan':           '54',   # مصروفات أخرى
    'other':          '54',   # مصروفات أخرى
}

def cors(r):
    r.headers['Access-Control-Allow-Origin'] = '*'
    r.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    r.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, APIKEY'
    return r

def get_open_invoices(invoice_type='sales'):
    try:
        all_invoices = []
        endpoint = 'invoices' if invoice_type == 'sales' else 'purchase_invoices'
        for status in ['0', '2']:
            page = 1
            while True:
                resp = requests.get(
                    f"{DAFTRA_BASE}/{endpoint}",
                    headers={'APIKEY': APIKEY},
                    params={'payment_status': status, 'limit': 50, 'page': page}
                )
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
            key = 'Invoice' if invoice_type == 'sales' else 'PurchaseInvoice'
            inv_id = inv.get(key, {}).get('id')
            if inv_id and inv_id not in seen:
                seen.add(inv_id)
                unique.append(inv)
        return unique
    except:
        return []

def normalize_name(name):
    name = (name or '').lower().strip()
    for alias, canonical in CLIENT_ALIASES.items():
        if alias in name:
            return canonical.lower()
    return name

def extract_account_from_text(text):
    text = text or ''
    m = re.search(r'(?:FRACCT|TOACCT|FROMACCT)[/\\](\d{10,})', text)
    if m:
        return m.group(1)
    m = re.search(r'CA:\s*(\d{10,})', text)
    if m:
        return m.group(1)
    return None

def client_name_matches(party, inv_client):
    if not party or not inv_client:
        return False
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

def match_payment(amount, open_invoices, party='', description='', invoice_key='Invoice'):
    combined_text = f"{party} {description}"
    acc = extract_account_from_text(combined_text)
    if acc and acc in ACCOUNT_TO_CLIENT:
        party = ACCOUNT_TO_CLIENT[acc]

    client_field = 'client_business_name' if invoice_key == 'Invoice' else 'supplier_name'
    client_invoices = [
        inv for inv in open_invoices
        if client_name_matches(combined_text, inv.get(invoice_key, {}).get(client_field, ''))
    ]
    search_pools = [client_invoices, open_invoices] if client_invoices else [open_invoices]

    for pool in search_pools:
        matches = []
        for inv in pool:
            inv_data = inv.get(invoice_key, {})
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
                    'client': inv_data.get(client_field, ''),
                    'amount': inv_amount,
                    'confidence': 'exact' if diff < 0.01 else 'close'
                })
        if matches:
            return matches

        for i in range(len(pool)):
            for j in range(i + 1, len(pool)):
                inv1 = pool[i].get(invoice_key, {})
                inv2 = pool[j].get(invoice_key, {})
                a1 = float(inv1.get('summary_unpaid', 0) or inv1.get('summary_total', 0) or 0)
                a2 = float(inv2.get('summary_unpaid', 0) or inv2.get('summary_total', 0) or 0)
                combined = a1 + a2
                if combined > 0 and abs(amount - combined) / combined <= 0.05:
                    return [{
                        'invoice_id': f"{inv1.get('id')},{inv2.get('id')}",
                        'invoice_no': f"{inv1.get('no')} + {inv2.get('no')}",
                        'client': inv1.get(client_field, ''),
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
    invoices = get_open_invoices('sales')
    return cors(make_response(jsonify({'invoices': invoices, 'count': len(invoices)}), 200))

@app.route('/open-purchase-invoices', methods=['GET', 'OPTIONS'])
def open_purchase_invoices_endpoint():
    if request.method == 'OPTIONS':
        return cors(make_response('', 200))
    invoices = get_open_invoices('purchase')
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

        if pay_resp.status_code in [200, 201] or pay_data.get("result") == "successful":
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

@app.route('/record-purchase-payment', methods=['POST', 'OPTIONS'])
def record_purchase_payment():
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
        payload = {
            "PurchaseInvoicePayment": {
                "purchase_invoice_id": str(invoice_id),
                "amount": float(amount),
                "date": date,
                "payment_method": "3",
                "notes": notes
            }
        }
        resp = requests.post(f"{DAFTRA_BASE}/purchase_invoice_payments", headers=headers, json=payload, timeout=30)
        resp_data = resp.json()
        if resp.status_code in [200, 201] or resp_data.get("result") == "successful":
            return cors(make_response(jsonify({'success': True, 'data': resp_data}), 200))
        return cors(make_response(jsonify({'error': resp_data}), resp.status_code))
    except Exception as e:
        return cors(make_response(jsonify({'error': str(e)}), 500))

@app.route('/record-expense', methods=['POST', 'OPTIONS'])
def record_expense():
    if request.method == 'OPTIONS':
        return cors(make_response('', 200))
    data = request.get_json()
    amount = data.get('amount')
    date = data.get('date')
    description = data.get('description', '')
    category = data.get('category', 'other')
    notes = data.get('notes', '')

    headers = {'APIKEY': APIKEY, 'Content-Type': 'application/json'}
    try:
        # Use chart-of-accounts ID directly
        account_id = EXPENSE_ACCOUNT_ID.get(category, '54')

        payload = {
            "Expense": {
                "amount": float(amount),
                "date": date,
                "description": description,
                "notes": notes,
                "expense_category_id": account_id
            }
        }

        resp = requests.post(f"{DAFTRA_BASE}/expenses", headers=headers, json=payload, timeout=30)
        resp_data = resp.json()
        if resp.status_code in [200, 201, 202] or resp_data.get("result") == "successful":
            return cors(make_response(jsonify({'success': True, 'account_id_used': account_id, 'data': resp_data}), 200))
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

    open_sales = get_open_invoices('sales')
    open_purchases = get_open_invoices('purchase')
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

    prompt = """You are an accountant for Maaly Qurtoba Marble Company in Saudi Arabia.

IMPORTANT BANKING RULE: AlRajhi Bank labels transfers between AlRajhi accounts as عملية تحويل داخلية which does NOT mean internal company transfer. If money is coming IN, it is likely a client_payment. If money is going OUT, classify based on who receives it.

Known employees always classify as salary: SALAMUDDIN is Installation Manager Riyadh, SIKANDAR is Installation Manager Dammam, TAUFEEK or TAUFEEQ is Driver, YAZEEN or يزن is Branch Manager Qassim, MALIK or مالك is Freelance Installer Qassim, معتز or MOATAZ or معتز محمد أحمد عاشور is former employee salary.

Known transportation always classify as transportation: IBRAHIM or ابراهيم is Truck or Freight, عبدالحسيب is Internal delivery driver Riyadh and Eastern Province, عمرو علي حسن بدوي or بدوي or عمرو بدوي is Dyna truck driver transportation.

Known local suppliers classify as local_supplier (they have purchase invoices in the system): شركة مصنع واهوي للرخام, واهوي, مصنع واهوي, أسوار الخليج, اسوار الخليج, شركة قمم الشام للتجارة, شركة السنا للرخام والسراميك, مؤسسة جنى مارين للتجارة.

Known china suppliers classify as china_supplier (they have purchase invoices in the system): GBOUEO02 or any transfer with reference to China or CNY.

Known clients always classify as client_payment when money comes IN: مؤسسة ريميندر, مؤسسة مهجة التجارية, MISHARY ADEL ALZAMIL, SHARAF AMER ALTALHI, هشام المسيند, نور البنعلى, اسامه زيد العنزي, وليد الجحيش, سفيان زامل الزامل, مؤسسة الخدمات التجارية المتكاملة, علي سعود عبدالله بن عسكر, ماهر عبدالله حباب جبر or مؤسسة الجبر or الجبر or الحباب.

Account number 12900608016890598 is always مؤسسة ريميندر — classify as client_payment.
Owner personal draws classify as personal: AMRO or عمرو الحلبي is Owner, اميرة is Owner mother.
Other: سليمان المهوس is rent Buraydah Branch, مؤسسة جي مارين للتجارة is rent Riyadh Branch, Traffic violations is government, LOANFLEET is loan, Mudud payroll is salary, نقاط بيع MALI QURTOBA is client_payment, Bank fees is bank_fee. خصم مستحقات البطاقات الائتمانية or بطاقة ائتمانية is bank_fee. قوس قزح is government (PRO services company).

For daftra_action use:
- client_payment IN → "match_invoice"
- local_supplier or china_supplier OUT → "match_purchase_invoice"
- salary/rent/transportation/government/bank_fee/personal/loan OUT → "record_expense"
- unknown or skip → "skip"

Analyze this bank statement and classify each transaction.
Categories: client_payment, china_supplier, local_supplier, salary, rent, personal, government, bank_fee, transportation, loan, other.
Return ONLY valid JSON: {"bank":"","period":"","opening":0,"closing":0,"transactions":[{"date":"YYYY-MM-DD","description":"","amount":0,"direction":"in or out","category":"","party":"","daftra_action":"match_invoice or match_purchase_invoice or record_expense or skip","notes":""}]}"""

    try:
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=8000,
            messages=[{"role": "user", "content": prompt + "\n\n" + bank_text[:8000]}]
        )
        raw = msg.content[0].text
        m = re.search(r'\{[\s\S]*\}', raw)
        result = json.loads(m.group() if m else raw)
        transactions = result.get('transactions', [])

        for tx in transactions:
            amt = float(tx.get('amount', 0))
            party = tx.get('party', '') or ''
            description = tx.get('description', '') or ''

            if tx.get('direction') == 'in' and tx.get('category') == 'client_payment':
                matches = match_payment(amt, open_sales, party, description, 'Invoice')
                tx['invoice_matches'] = matches
                tx['daftra_action'] = 'match_invoice' if matches else 'waiting_list'

            elif tx.get('direction') == 'out' and tx.get('category') in ['local_supplier', 'china_supplier']:
                matches = match_payment(amt, open_purchases, party, description, 'PurchaseInvoice')
                tx['purchase_invoice_matches'] = matches
                tx['daftra_action'] = 'match_purchase_invoice' if matches else 'waiting_list_purchase'

        result['transactions'] = transactions
        return cors(make_response(jsonify(result), 200))
    except Exception as e:
        return cors(make_response(jsonify({'error': str(e)}), 500))

EXCLUDE_KEYWORDS = ['ديزل', 'محروقات', 'diesel', 'fuel']
CLEANUP_CUTOFF = '2026-04-01'

def should_exclude(text):
    text = (text or '').lower()
    return any(kw.lower() in text for kw in EXCLUDE_KEYWORDS)

def fetch_all_pages(endpoint):
    items = []
    page = 1
    while True:
        r = requests.get(f"{DAFTRA_BASE}/{endpoint}", headers={'APIKEY': APIKEY},
                         params={'limit': 50, 'page': page}, timeout=30)
        data = r.json().get('data', [])
        if not data:
            break
        items.extend(data)
        if len(data) < 50:
            break
        page += 1
    return items

@app.route('/preview-deletions', methods=['GET', 'OPTIONS'])
def preview_deletions():
    if request.method == 'OPTIONS':
        return cors(make_response('', 200))
    try:
        # Invoice payments
        payments = fetch_all_pages('invoice_payments')
        to_delete_payments = []
        keep_payments = []
        for p in payments:
            ip = p.get('InvoicePayment', p)
            date = ip.get('date', '')
            notes = ip.get('notes', '') or ''
            if date >= CLEANUP_CUTOFF:
                if should_exclude(notes):
                    keep_payments.append({'id': ip.get('id'), 'date': date, 'amount': ip.get('amount'), 'notes': notes[:50]})
                else:
                    to_delete_payments.append({'id': ip.get('id'), 'date': date, 'amount': ip.get('amount'), 'notes': notes[:50]})

        # Expenses
        expenses = fetch_all_pages('expenses')
        to_delete_expenses = []
        keep_expenses = []
        for e in expenses:
            exp = e.get('Expense', e)
            date = exp.get('date', '')
            desc = (exp.get('description', '') or '')
            notes = (exp.get('notes', '') or '')
            combined = f"{desc} {notes}"
            if date >= CLEANUP_CUTOFF:
                if should_exclude(combined):
                    keep_expenses.append({'id': exp.get('id'), 'date': date, 'amount': exp.get('amount'), 'description': desc[:50]})
                else:
                    to_delete_expenses.append({'id': exp.get('id'), 'date': date, 'amount': exp.get('amount'), 'description': desc[:50]})

        return cors(make_response(jsonify({
            'to_delete': {
                'invoice_payments': to_delete_payments,
                'invoice_payments_count': len(to_delete_payments),
                'expenses': to_delete_expenses,
                'expenses_count': len(to_delete_expenses),
                'total': len(to_delete_payments) + len(to_delete_expenses)
            },
            'to_keep': {
                'invoice_payments': keep_payments,
                'expenses': keep_expenses
            }
        }), 200))
    except Exception as e:
        return cors(make_response(jsonify({'error': str(e)}), 500))

@app.route('/execute-deletions', methods=['POST', 'OPTIONS'])
def execute_deletions():
    if request.method == 'OPTIONS':
        return cors(make_response('', 200))
    try:
        headers = {'APIKEY': APIKEY}
        deleted_payments = 0
        deleted_expenses = 0
        errors = []

        # Delete invoice payments
        payments = fetch_all_pages('invoice_payments')
        for p in payments:
            ip = p.get('InvoicePayment', p)
            date = ip.get('date', '')
            notes = (ip.get('notes', '') or '')
            if date >= CLEANUP_CUTOFF and not should_exclude(notes):
                r = requests.delete(f"{DAFTRA_BASE}/invoice_payments/{ip.get('id')}", headers=headers, timeout=30)
                if r.status_code in [200, 201, 204] or r.json().get('result') == 'successful':
                    deleted_payments += 1
                else:
                    errors.append(f"payment {ip.get('id')}: {r.text[:50]}")

        # Delete expenses
        expenses = fetch_all_pages('expenses')
        for e in expenses:
            exp = e.get('Expense', e)
            date = exp.get('date', '')
            desc = (exp.get('description', '') or '')
            notes = (exp.get('notes', '') or '')
            combined = f"{desc} {notes}"
            if date >= CLEANUP_CUTOFF and not should_exclude(combined):
                r = requests.delete(f"{DAFTRA_BASE}/expenses/{exp.get('id')}", headers=headers, timeout=30)
                if r.status_code in [200, 201, 204] or r.json().get('result') == 'successful':
                    deleted_expenses += 1
                else:
                    errors.append(f"expense {exp.get('id')}: {r.text[:50]}")

        return cors(make_response(jsonify({
            'deleted_payments': deleted_payments,
            'deleted_expenses': deleted_expenses,
            'total_deleted': deleted_payments + deleted_expenses,
            'errors': errors
        }), 200))
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
