from flask import Flask, request, jsonify, make_response, send_file
import requests, os, anthropic, json, re, threading, uuid

app = Flask(__name__)

DAFTRA_BASE = 'https://maealequrtoba.daftra.com/api2'
APIKEY = os.environ.get('APIKEY', 'c4c035341dbe1da1531b227d89f6e2f481252766')
ANTHROPIC_KEY = os.environ.get('ANTHROPIC_API_KEY', '')

_jobs = {}

CLIENT_ALIASES = {
    'مهجة': 'ريميندر', 'reminder': 'ريميندر',
    'الخدمات التجارية المتكاملة': 'الخدمات التجارية المتكاملة',
    'خدمات متكاملة': 'الخدمات التجارية المتكاملة',
    'حباب': 'مؤسسة الجبر', 'الحباب': 'مؤسسة الجبر',
    'ماهر حباب': 'مؤسسة الجبر', 'ماهر عبدالله': 'مؤسسة الجبر',
    'الجبر': 'مؤسسة الجبر',
}

EMPLOYEE_IDS = {
    '2229429275': 'عمرو الحلبي', '2155703453': 'بلال جلال غانم',
    '2500894296': 'MD ANIS', '2549846075': 'MD JAULHAS MOLLA',
    '1123351007': 'محمد المجيدل', '2544919612': 'TAUFEEK AHMAD',
    '2544919596': 'TAREKH HUSEN', '1131768192': 'فهد البطي',
    '2568475756': 'احمد محمد حماد', '1126192390': 'فهد العليان',
    '2602072692': 'RAMJAN MANSHUR', '2602072783': 'NOORUL HODA KHAN',
    '2612225173': 'AFROJ SALMANI', '2229429267': 'اميرة',
    '2619122530': 'SAVEJ ABDUL RAHMAN', '2630277883': 'SADDAM KHAN',
    '2630277933': 'MD ARIF HOSSAIN', '2636857225': 'WAJID ALI',
    '1136786959': 'احمد الفضل', '2576905463': 'MD AMAN ULLAH',
    '2229429291': 'يزن الحلبي', '2551964485': 'KAMAL HOSSAIN',
    '2574846610': 'SIKANDAR GUPTA',
}

EMPLOYEE_CATEGORY = {
    '2229429275': 'personal', '2229429267': 'personal',
    '2155703453': 'salary', '2500894296': 'salary', '2549846075': 'salary',
    '1123351007': 'salary', '2544919612': 'salary', '2544919596': 'salary',
    '1131768192': 'salary', '2568475756': 'salary', '1126192390': 'salary',
    '2602072692': 'salary', '2602072783': 'salary', '2612225173': 'salary',
    '2619122530': 'salary', '2630277883': 'salary', '2630277933': 'salary',
    '2636857225': 'salary', '1136786959': 'salary', '2576905463': 'salary',
    '2229429291': 'salary', '2551964485': 'salary', '2574846610': 'salary',
}

ACCOUNT_TO_CLIENT = {
    '129000010006086890598': 'ريميندر', '12900608016890598': 'ريميندر',
    '200000010006080174447': 'علي سعود',
    '640000010006087461738': 'SALAMUDDIN', '077050010006087399166': 'SIKANDAR',
    '077050010006087400188': 'TAUFEEK', '697000010006086135855': 'يزن',
    '192000010006080456273': 'مالك', 'MOATAZ': 'معتز',
    '331000010006086567547': 'عبدالحسيب', 'AMRO_BADAWI': 'عمرو بدوي',
    '377000010006080000888': 'شركة السنا للرخام والسيراميك',
    '538000010006080000223': 'شركة الفرات للرخام',
    '602000010006080654780': 'شركة اسوار الخليج',
    '487000010006085245725': 'شركة هواهوي ستون',
    '599000010006080888888': 'سليمان المهوس',
    '282000010006086606237': 'مؤسسة قوس قزح',
    '077050010006084823853': 'عمرو الحلبي', '539000010006085772890': 'اميرة',
}

ACCOUNT_CATEGORY = {
    '129000010006086890598': 'client_payment', '12900608016890598': 'client_payment',
    '200000010006080174447': 'client_payment',
    '640000010006087461738': 'salary', '077050010006087399166': 'salary',
    '077050010006087400188': 'salary', '697000010006086135855': 'salary',
    '192000010006080456273': 'salary', 'MOATAZ': 'salary',
    '331000010006086567547': 'transportation', 'AMRO_BADAWI': 'transportation',
    '377000010006080000888': 'local_supplier', '538000010006080000223': 'local_supplier',
    '602000010006080654780': 'local_supplier', '487000010006085245725': 'local_supplier',
    '599000010006080888888': 'rent', '282000010006086606237': 'government',
    '077050010006084823853': 'personal', '539000010006085772890': 'personal',
}

# ✅ FIX: These are Daftra expense_category_id values (not account IDs)
EXPENSE_CATEGORY_ID = {
    'salary': '1282',
    'rent': '866',
    'transportation': '1285',
    'government': '904',
    'bank_fee': '1284',
    'personal': '1263',
    'loan': '1263',
    'other': '1263',
}

# ✅ NEW: Known vendors (supplier payments, not expenses)
VENDOR_NAMES = {
    'بيتي النيق': {'supplier_name': 'بيتي النيق', 'daftra_action': 'match_purchase_invoice'},
}

EXCLUDE_KEYWORDS = ['ديزل', 'محروقات', 'diesel', 'fuel']
CLEANUP_CUTOFF = '2026-04-01'

def should_exclude(text):
    return any(kw in (text or '').lower() for kw in EXCLUDE_KEYWORDS)

def fetch_all_pages(endpoint):
    items, page = [], 1
    while True:
        r = requests.get(f"{DAFTRA_BASE}/{endpoint}", headers={'APIKEY': APIKEY},
                         params={'limit': 50, 'page': page}, timeout=30)
        data = r.json().get('data', [])
        if not data: break
        items.extend(data)
        if len(data) < 50: break
        page += 1
    return items

def cors(r):
    r.headers['Access-Control-Allow-Origin'] = '*'
    r.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    r.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, APIKEY'
    return r

def get_open_invoices(invoice_type='sales'):
    try:
        all_invoices, endpoint = [], 'invoices' if invoice_type == 'sales' else 'purchase_invoices'
        for status in ['0', '1', '2', '3', '4']:
            page = 1
            while True:
                resp = requests.get(f"{DAFTRA_BASE}/{endpoint}", headers={'APIKEY': APIKEY},
                                    params={'payment_status': status, 'limit': 50, 'page': page})
                invoices = resp.json().get('data', [])
                if not invoices: break
                all_invoices.extend(invoices)
                if len(invoices) < 50: break
                page += 1
        seen, unique = set(), []
        key = 'Invoice' if invoice_type == 'sales' else 'PurchaseInvoice'
        for inv in all_invoices:
            inv_id = inv.get(key, {}).get('id')
            if inv_id and inv_id not in seen:
                seen.add(inv_id); unique.append(inv)
        return unique
    except:
        return []

def normalize_name(name):
    name = (name or '').lower().strip()
    for alias, canonical in CLIENT_ALIASES.items():
        if alias in name: return canonical.lower()
    return name

def extract_account_from_text(text):
    text = text or ''
    m = re.search(r'(?:FRACCT|TOACCT|FROMACCT)[/\\](\d{10,})', text)
    if m: return m.group(1)
    m = re.search(r'CA:\s*(\d{10,})', text)
    if m: return m.group(1)
    return None

def extract_id_from_text(text):
    m = re.search(r'\b([12]\d{9})\b', text or '')
    return m.group(1) if m else None

def client_name_matches(party, inv_client):
    if not party or not inv_client: return False
    acc = extract_account_from_text(party)
    if acc and acc in ACCOUNT_TO_CLIENT:
        return ACCOUNT_TO_CLIENT[acc].lower() in normalize_name(inv_client)
    p, c = normalize_name(party), normalize_name(inv_client)
    for pw in [w for w in p.split() if len(w) >= 4]:
        if pw in c: return True
    for cw in [w for w in c.split() if len(w) >= 4]:
        if cw in p: return True
    return False

def match_payment(amount, open_invoices, party='', description='', invoice_key='Invoice'):
    combined_text = f"{party} {description}"
    acc = extract_account_from_text(combined_text)
    if acc and acc in ACCOUNT_TO_CLIENT: party = ACCOUNT_TO_CLIENT[acc]
    client_field = 'client_business_name' if invoice_key == 'Invoice' else 'supplier_name'
    client_invoices = [inv for inv in open_invoices
                       if client_name_matches(combined_text, inv.get(invoice_key, {}).get(client_field, ''))]
    search_pools = [client_invoices, open_invoices] if client_invoices else [open_invoices]
    for pool in search_pools:
        matches = []
        for inv in pool:
            inv_data = inv.get(invoice_key, {})
            unpaid = float(inv_data.get('summary_unpaid', 0) or 0)
            total = float(inv_data.get('summary_total', 0) or 0)
            inv_amount = unpaid if unpaid > 0 else total
            if inv_amount <= 0: continue
            diff = abs(amount - inv_amount) / inv_amount
            if diff <= 0.05:
                matches.append({'invoice_id': inv_data.get('id'), 'invoice_no': inv_data.get('no'),
                                 'client': inv_data.get(client_field, ''), 'amount': inv_amount,
                                 'confidence': 'exact' if diff < 0.01 else 'close'})
        if matches: return matches
        for i in range(len(pool)):
            for j in range(i+1, len(pool)):
                inv1, inv2 = pool[i].get(invoice_key, {}), pool[j].get(invoice_key, {})
                a1 = float(inv1.get('summary_unpaid', 0) or inv1.get('summary_total', 0) or 0)
                a2 = float(inv2.get('summary_unpaid', 0) or inv2.get('summary_total', 0) or 0)
                combined = a1 + a2
                if combined > 0 and abs(amount - combined) / combined <= 0.05:
                    return [{'invoice_id': f"{inv1.get('id')},{inv2.get('id')}",
                              'invoice_no': f"{inv1.get('no')} + {inv2.get('no')}",
                              'client': inv1.get(client_field, ''), 'amount': combined, 'confidence': 'combined'}]
    return []

PROMPT = """You are an accountant for Maaly Qurtoba Marble Company in Saudi Arabia.

CRITICAL RULE: Every incoming payment (direction=in) is ALWAYS a client_payment. No exceptions.
CRITICAL RULE: اعمال الشوري is a client REFUND (direction=out, category=other, daftra_action=skip).
AlRajhi internal transfers: ignore the label, classify by direction and recipient.

EMPLOYEES (salary): بلال جلال غانم(2155703453), MD ANIS(2500894296), MD JAULHAS MOLLA(2549846075), محمد المجيدل(1123351007), TAUFEEK AHMAD(2544919612), TAREKH HUSEN(2544919596), فهد البطي(1131768192), احمد محمد حماد(2568475756), فهد العليان(1126192390), RAMJAN MANSHUR(2602072692), NOORUL HODA KHAN(2602072783), AFROJ SALMANI(2612225173), SAVEJ ABDUL RAHMAN(2619122530), SADDAM KHAN(2630277883), MD ARIF HOSSAIN(2630277933), WAJID ALI(2636857225), احمد الفضل(1136786959), MD AMAN ULLAH(2576905463), يزن الحلبي(2229429291), KAMAL HOSSAIN(2551964485), SIKANDAR GUPTA(2574846610), SALAMUDDIN, سلام مبلط, صلاح مبلط, ابو ريناد, مالك نواف, ابو حسين, عبد الله فرع الرياض, مالك, معتز, MOATAZ
PERSONAL (owner draws): عمرو الحلبي(2229429275), اميرة(2229429267)
TRANSPORTATION: عبدالحسيب, عمرو بدوي, IBRAHIM
LOCAL SUPPLIERS (vendor payments): واهوي, أسوار الخليج, اسوار الخليج, السنا للرخام, الفرات للرخام, جنى مارين, قمم الشام, بيتي النيق
CHINA SUPPLIERS: GBOUEO02, SHENYANG, China/CNY transfers
CLIENTS: ريميندر, مهجة, MISHARY ALZAMIL, SHARAF ALTALHI, هشام المسيند, نور البنعلى, اسامه العنزي, وليد الجحيش, سفيان الزامل, الخدمات التجارية المتكاملة, علي سعود, ماهر حباب, مؤسسة الجبر, شركة ذكي للدعاية, CAMBNI ALROMEH
OTHER: سليمان المهوس=rent Buraydah, جي مارين=rent Riyadh, LOANFLEET=loan, Mudud=salary, نقاط بيع MALI QURTOBA=client_payment, بطاقة ائتمانية=bank_fee, قوس قزح=government, Ministry of Labor=government, Expatriate Renew Iqama=government

NOTES: always include ID numbers, names, references. Example: "تجديد إقامة - بلال جلال غانم - ID: 2155703453"

daftra_action: client_payment IN→match_invoice | local/china supplier OUT→match_purchase_invoice | salary/rent/transport/gov/fee/personal/loan→record_expense | else→skip

Return ONLY valid JSON: {"bank":"","period":"","opening":0,"closing":0,"transactions":[{"date":"YYYY-MM-DD","description":"","amount":0,"direction":"in or out","category":"","party":"","daftra_action":"","notes":""}]}"""

def _do_analysis(bank_text):
    """Synchronous analysis — runs in request thread with extended timeout."""
    ai_client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    msg = ai_client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=8000,
        messages=[{"role": "user", "content": PROMPT + "\n\n" + bank_text[:50000]}]
    )
    raw = msg.content[0].text
    m = re.search(r'\{[\s\S]*\}', raw)
    result = json.loads(m.group() if m else raw)
    transactions = result.get('transactions', [])

    needs_sales = any(t.get('direction') == 'in' and t.get('category') == 'client_payment' for t in transactions)
    needs_purchases = any(t.get('direction') == 'out' and t.get('category') in ['local_supplier', 'china_supplier'] for t in transactions)
    open_sales = get_open_invoices('sales') if needs_sales else []
    open_purchases = get_open_invoices('purchase') if needs_purchases else []

    for tx in transactions:
        amt = float(tx.get('amount', 0))
        party = tx.get('party', '') or ''
        description = tx.get('description', '') or ''
        combined = f"{party} {description}"

        # ✅ FIX: Check for known vendors first (بيتي النيق etc.)
        for vendor_key, vendor_info in VENDOR_NAMES.items():
            if vendor_key in combined:
                tx['category'] = 'local_supplier'
                tx['party'] = vendor_info['supplier_name']
                tx['daftra_action'] = vendor_info['daftra_action']
                break

        emp_id = extract_id_from_text(combined)
        if emp_id and emp_id in EMPLOYEE_IDS:
            emp_name = EMPLOYEE_IDS[emp_id]
            emp_cat = EMPLOYEE_CATEGORY.get(emp_id, 'salary')
            tx['category'] = emp_cat
            tx['party'] = emp_name
            if not tx.get('notes'):
                tx['notes'] = f"{description} - {emp_name} - ID: {emp_id}"
            tx['daftra_action'] = 'record_expense'

        if tx.get('direction') == 'in' and tx.get('category') == 'client_payment':
            matches = match_payment(amt, open_sales, party, description, 'Invoice')
            tx['invoice_matches'] = matches
            tx['daftra_action'] = 'match_invoice' if matches else 'waiting_list'
        elif tx.get('direction') == 'out' and tx.get('category') in ['local_supplier', 'china_supplier']:
            matches = match_payment(amt, open_purchases, party, description, 'PurchaseInvoice')
            tx['purchase_invoice_matches'] = matches
            tx['daftra_action'] = 'match_purchase_invoice' if matches else 'waiting_list_purchase'

    result['transactions'] = transactions
    return result

# ✅ Keep async job system for backward compat but also support sync
def _run_analysis(job_id, bank_text):
    try:
        _jobs[job_id] = {'status': 'running'}
        result = _do_analysis(bank_text)
        _jobs[job_id] = {'status': 'done', 'result': result}
    except Exception as e:
        _jobs[job_id] = {'status': 'error', 'error': str(e)}

@app.route('/bank-sync')
def bank_sync():
    r = make_response(send_file('app.html'))
    r.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return r

@app.route('/open-invoices', methods=['GET', 'OPTIONS'])
def open_invoices_endpoint():
    if request.method == 'OPTIONS': return cors(make_response('', 200))
    return cors(make_response(jsonify({'invoices': get_open_invoices('sales')}), 200))

@app.route('/open-purchase-invoices', methods=['GET', 'OPTIONS'])
def open_purchase_invoices_endpoint():
    if request.method == 'OPTIONS': return cors(make_response('', 200))
    return cors(make_response(jsonify({'invoices': get_open_invoices('purchase')}), 200))

# ✅ NEW: Synchronous analyze endpoint — returns result directly, no polling needed
@app.route('/analyze-bank-sync', methods=['POST', 'OPTIONS'])
def analyze_bank_sync():
    if request.method == 'OPTIONS': return cors(make_response('', 200))
    data = request.get_json()
    bank_text = data.get('text', '')
    if not bank_text: return cors(make_response(jsonify({'error': 'No text provided'}), 400))
    if not ANTHROPIC_KEY: return cors(make_response(jsonify({'error': 'No API key configured'}), 500))
    try:
        result = _do_analysis(bank_text)
        return cors(make_response(jsonify({'status': 'done', 'result': result}), 200))
    except Exception as e:
        return cors(make_response(jsonify({'status': 'error', 'error': str(e)}), 500))

# Keep old async endpoint for compatibility
@app.route('/analyze-bank', methods=['POST', 'OPTIONS'])
def analyze_bank():
    if request.method == 'OPTIONS': return cors(make_response('', 200))
    data = request.get_json()
    bank_text = data.get('text', '')
    if not bank_text: return cors(make_response(jsonify({'error': 'No text provided'}), 400))
    if not ANTHROPIC_KEY: return cors(make_response(jsonify({'error': 'No API key configured'}), 500))
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {'status': 'pending'}
    threading.Thread(target=_run_analysis, args=(job_id, bank_text), daemon=True).start()
    return cors(make_response(jsonify({'job_id': job_id, 'status': 'pending'}), 200))

@app.route('/analysis-result/<job_id>', methods=['GET', 'OPTIONS'])
def analysis_result(job_id):
    if request.method == 'OPTIONS': return cors(make_response('', 200))
    job = _jobs.get(job_id)
    if not job: return cors(make_response(jsonify({'status': 'not_found'}), 404))
    return cors(make_response(jsonify(job), 200))

@app.route('/record-payment', methods=['POST', 'OPTIONS'])
def record_payment():
    if request.method == 'OPTIONS': return cors(make_response('', 200))
    data = request.get_json()
    invoice_id, amount, date, notes = data.get('invoice_id'), data.get('amount'), data.get('date'), data.get('notes', '')
    if not invoice_id or not amount: return cors(make_response(jsonify({'error': 'invoice_id and amount required'}), 400))
    headers = {'APIKEY': APIKEY, 'Content-Type': 'application/json'}
    try:
        inv_resp = requests.get(f"{DAFTRA_BASE}/invoices/{invoice_id}", headers=headers, timeout=30)
        inv_data = inv_resp.json().get('data', {})
        if isinstance(inv_data, list): inv_data = inv_data[0] if inv_data else {}
        inv = inv_data.get('Invoice', inv_data)
        client_id = inv.get('client_id') or inv.get('ClientId')
        unpaid = float(inv.get('summary_unpaid', 0) or 0)
        pay_amount = min(float(amount), unpaid) if unpaid > 0 else float(amount)
        payload = {"InvoicePayment": {"invoice_id": str(invoice_id), "amount": pay_amount, "date": date, "payment_method": "3", "notes": notes}}
        if client_id: payload["InvoicePayment"]["client_id"] = str(client_id)
        pay_resp = requests.post(f"{DAFTRA_BASE}/invoice_payments", headers=headers, json=payload, timeout=30)
        pay_data = pay_resp.json()
        if pay_resp.status_code in [200, 201] or pay_data.get("result") == "successful":
            return cors(make_response(jsonify({'success': True, 'data': pay_data}), 200))
        if client_id:
            cp_resp = requests.post(f"{DAFTRA_BASE}/client_payments", headers=headers, timeout=30,
                json={"ClientPayment": {"client_id": str(client_id), "amount": float(amount), "date": date,
                                        "payment_method": "3", "notes": notes,
                                        "InvoicePayment": [{"invoice_id": str(invoice_id), "amount": pay_amount}]}})
            if cp_resp.status_code in [200, 201] or cp_resp.json().get("result") == "successful":
                return cors(make_response(jsonify({'success': True, 'data': cp_resp.json()}), 200))
        return cors(make_response(jsonify({'error': pay_data}), pay_resp.status_code))
    except Exception as e:
        return cors(make_response(jsonify({'error': str(e)}), 500))

@app.route('/record-purchase-payment', methods=['POST', 'OPTIONS'])
def record_purchase_payment():
    if request.method == 'OPTIONS': return cors(make_response('', 200))
    data = request.get_json()
    headers = {'APIKEY': APIKEY, 'Content-Type': 'application/json'}
    try:
        resp = requests.post(f"{DAFTRA_BASE}/purchase_invoice_payments", headers=headers, timeout=30,
            json={"PurchaseInvoicePayment": {"purchase_invoice_id": str(data.get('invoice_id')),
                                              "amount": float(data.get('amount')), "date": data.get('date'),
                                              "payment_method": "3", "notes": data.get('notes', '')}})
        resp_data = resp.json()
        if resp.status_code in [200, 201] or resp_data.get("result") == "successful":
            return cors(make_response(jsonify({'success': True, 'data': resp_data}), 200))
        return cors(make_response(jsonify({'error': resp_data}), resp.status_code))
    except Exception as e:
        return cors(make_response(jsonify({'error': str(e)}), 500))

@app.route('/record-expense', methods=['POST', 'OPTIONS'])
def record_expense():
    if request.method == 'OPTIONS': return cors(make_response('', 200))
    data = request.get_json()
    amount = data.get('amount')
    date = data.get('date')
    description = data.get('description', '')
    category = data.get('category', 'other')
    notes = data.get('notes', '')
    # ✅ FIX: Use correct Daftra expense_category_id
    expense_category_id = EXPENSE_CATEGORY_ID.get(category, '1263')
    rich_notes = f"{description} | {notes}" if notes and notes != description else (description or notes)
    headers = {'APIKEY': APIKEY, 'Content-Type': 'application/json'}
    try:
        resp = requests.post(f"{DAFTRA_BASE}/expenses", headers=headers, timeout=30,
            json={"Expense": {
                "amount": float(amount),
                "date": date,
                "description": description,
                "notes": rich_notes,
                "expense_category_id": expense_category_id
            }})
        resp_data = resp.json()
        if resp.status_code in [200, 201, 202] or resp_data.get("result") == "successful":
            return cors(make_response(jsonify({'success': True, 'data': resp_data}), 200))
        return cors(make_response(jsonify({'error': resp_data}), resp.status_code))
    except Exception as e:
        return cors(make_response(jsonify({'error': str(e)}), 500))

# ✅ NEW: Edit expense category
@app.route('/edit-expense/<expense_id>', methods=['PUT', 'OPTIONS'])
def edit_expense(expense_id):
    if request.method == 'OPTIONS': return cors(make_response('', 200))
    data = request.get_json()
    category = data.get('category', 'other')
    expense_category_id = EXPENSE_CATEGORY_ID.get(category, '1263')
    headers = {'APIKEY': APIKEY, 'Content-Type': 'application/json'}
    try:
        # Build update payload — only send fields provided
        payload = {"Expense": {"expense_category_id": expense_category_id}}
        if 'description' in data: payload['Expense']['description'] = data['description']
        if 'amount' in data: payload['Expense']['amount'] = float(data['amount'])
        if 'date' in data: payload['Expense']['date'] = data['date']
        if 'notes' in data: payload['Expense']['notes'] = data['notes']
        resp = requests.put(f"{DAFTRA_BASE}/expenses/{expense_id}", headers=headers, json=payload, timeout=30)
        resp_data = resp.json()
        if resp.status_code in [200, 201] or resp_data.get("result") == "successful":
            return cors(make_response(jsonify({'success': True, 'data': resp_data}), 200))
        return cors(make_response(jsonify({'error': resp_data}), resp.status_code))
    except Exception as e:
        return cors(make_response(jsonify({'error': str(e)}), 500))

@app.route('/preview-deletions', methods=['GET', 'OPTIONS'])
def preview_deletions():
    if request.method == 'OPTIONS': return cors(make_response('', 200))
    try:
        to_del_p, keep_p = [], []
        for p in fetch_all_pages('invoice_payments'):
            ip = p.get('InvoicePayment', p)
            d, n = ip.get('date', ''), ip.get('notes', '') or ''
            if d >= CLEANUP_CUTOFF:
                (keep_p if should_exclude(n) else to_del_p).append({'id': ip.get('id'), 'date': d, 'amount': ip.get('amount'), 'notes': n[:50]})
        to_del_e, keep_e = [], []
        for e in fetch_all_pages('expenses'):
            exp = e.get('Expense', e)
            d = exp.get('date', '')
            desc, n = exp.get('description', '') or '', exp.get('notes', '') or ''
            if d >= CLEANUP_CUTOFF:
                (keep_e if should_exclude(f"{desc} {n}") else to_del_e).append({'id': exp.get('id'), 'date': d, 'amount': exp.get('amount'), 'description': desc[:50]})
        return cors(make_response(jsonify({'to_delete': {'invoice_payments': to_del_p, 'invoice_payments_count': len(to_del_p), 'expenses': to_del_e, 'expenses_count': len(to_del_e), 'total': len(to_del_p)+len(to_del_e)}, 'to_keep': {'invoice_payments': keep_p, 'expenses': keep_e}}), 200))
    except Exception as e:
        return cors(make_response(jsonify({'error': str(e)}), 500))

@app.route('/execute-deletions', methods=['POST', 'OPTIONS'])
def execute_deletions():
    if request.method == 'OPTIONS': return cors(make_response('', 200))
    try:
        headers, del_p, del_e, errors = {'APIKEY': APIKEY}, 0, 0, []
        for p in fetch_all_pages('invoice_payments'):
            ip = p.get('InvoicePayment', p)
            if ip.get('date', '') >= CLEANUP_CUTOFF and not should_exclude(ip.get('notes', '') or ''):
                r = requests.delete(f"{DAFTRA_BASE}/invoice_payments/{ip.get('id')}", headers=headers, timeout=30)
                if r.status_code in [200, 201, 204] or r.json().get('result') == 'successful': del_p += 1
                else: errors.append(f"payment {ip.get('id')}: {r.text[:50]}")
        for e in fetch_all_pages('expenses'):
            exp = e.get('Expense', e)
            desc, n = exp.get('description', '') or '', exp.get('notes', '') or ''
            if exp.get('date', '') >= CLEANUP_CUTOFF and not should_exclude(f"{desc} {n}"):
                r = requests.delete(f"{DAFTRA_BASE}/expenses/{exp.get('id')}", headers=headers, timeout=30)
                if r.status_code in [200, 201, 204] or r.json().get('result') == 'successful': del_e += 1
                else: errors.append(f"expense {exp.get('id')}: {r.text[:50]}")
        return cors(make_response(jsonify({'deleted_payments': del_p, 'deleted_expenses': del_e, 'total_deleted': del_p+del_e, 'errors': errors}), 200))
    except Exception as e:
        return cors(make_response(jsonify({'error': str(e)}), 500))

@app.route('/find-invoice/<invoice_no>', methods=['GET', 'OPTIONS'])
def find_invoice(invoice_no):
    if request.method == 'OPTIONS': return cors(make_response('', 200))
    try:
        r = requests.get(f"{DAFTRA_BASE}/invoices/{invoice_no}", headers={'APIKEY': APIKEY}, timeout=15)
        data = r.json()
        inv = data.get('data', {})
        if isinstance(inv, list): inv = inv[0] if inv else {}
        inv_obj = inv.get('Invoice', inv)
        if inv_obj.get('id'):
            return cors(make_response(jsonify({'found': True, 'invoice': inv_obj}), 200))
        search = requests.get(f"{DAFTRA_BASE}/invoices", headers={'APIKEY': APIKEY},
                              params={'no': invoice_no, 'limit': 5}, timeout=15)
        results = search.json().get('data', [])
        for item in results:
            i = item.get('Invoice', item)
            if i.get('no') == invoice_no or i.get('no') == invoice_no.lstrip('0') or str(i.get('id')) == invoice_no:
                return cors(make_response(jsonify({'found': True, 'invoice': i}), 200))
        return cors(make_response(jsonify({'found': False}), 200))
    except Exception as e:
        return cors(make_response(jsonify({'error': str(e)}), 500))

@app.route('/<path:endpoint>', methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'])
def proxy(endpoint):
    if request.method == 'OPTIONS': return cors(make_response('', 200))
    url = f"{DAFTRA_BASE}/{endpoint}"
    headers = {'APIKEY': APIKEY, 'Content-Type': 'application/json'}
    try:
        if request.method == 'GET': resp = requests.get(url, headers=headers, params=request.args, timeout=30)
        elif request.method == 'POST': resp = requests.post(url, headers=headers, json=request.get_json(), timeout=30)
        elif request.method == 'PUT': resp = requests.put(url, headers=headers, json=request.get_json(), timeout=30)
        elif request.method == 'DELETE': resp = requests.delete(url, headers=headers, timeout=30)
        return cors(make_response(jsonify(resp.json()), resp.status_code))
    except Exception as e:
        return cors(make_response(jsonify({'error': str(e)}), 500))

@app.route('/')
def health():
    return cors(make_response(jsonify({'status': 'ok'}), 200))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
